import json
import re
import threading
import unicodedata
from dataclasses import dataclass
from datetime import date, timedelta

from fastapi import HTTPException, status

from app.core.config import get_settings
from app.modules.assistant.providers import OpenAICompatibleProvider
from app.modules.assistant.schemas import (
    AssistantKind,
    AssistantTag,
    CalendarEventProposalPayload,
    DeadlineReminderProposalPayload,
    GroceryMealPlanRequest,
    GroceryMealPlanResponse,
    GroceryProposalPayload,
    MealPlanEntry,
    NoteProposalPayload,
    RecurringReminderProposalPayload,
    TaskProposalPayload,
    ThoughtOrganizationRequest,
    ThoughtOrganizationResponse,
    TrainingProposalPayload,
)

TAG_KEYWORDS: dict[AssistantTag, tuple[str, ...]] = {
    AssistantTag.SCHOOL: (
        "ecole",
        "classe",
        "devoir",
        "professeur",
        "atelier",
        "inscrire",
        "fourniture",
    ),
    AssistantTag.WORK: ("travail", "dossier", "reunion", "client", "bureau", "projet"),
    AssistantTag.ERRANDS: (
        "course",
        "acheter",
        "magasin",
        "facture",
        "mutuelle",
        "pharmacie",
    ),
    AssistantTag.FAMILY: ("famille", "mamie", "papa", "maman", "anniversaire", "dimanche"),
}

ACTION_KEYWORDS = (
    "appeler",
    "acheter",
    "preparer",
    "inscrire",
    "envoyer",
    "reserver",
    "faire",
    "repondre",
    "confirmer",
    "organiser",
)
REMINDER_KEYWORDS = ("penser", "pense", "rappelle", "rappel", "noublie")
MONTHS = {
    "janvier": 1,
    "fevrier": 2,
    "mars": 3,
    "avril": 4,
    "mai": 5,
    "juin": 6,
    "juillet": 7,
    "aout": 8,
    "septembre": 9,
    "octobre": 10,
    "novembre": 11,
    "decembre": 12,
}
WEEKDAYS = {
    "lundi": 0,
    "mardi": 1,
    "mercredi": 2,
    "jeudi": 3,
    "vendredi": 4,
    "samedi": 5,
    "dimanche": 6,
}
MEAL_TEMPLATES = (
    {
        "day": "Lundi",
        "name": "Pâtes aux légumes du placard",
        "description": "Un dîner rapide à ajuster avec les légumes déjà prévus.",
        "keywords": ("pate", "courgette", "basilic"),
        "uses": ("Pâtes", "Courgettes", "Basilic"),
        "missing_items": ("Parmesan ou levure maltée",),
    },
    {
        "day": "Mercredi",
        "name": "Omelette verte et salade",
        "description": "Une option courte pour le milieu de semaine.",
        "keywords": ("oeuf", "epinard", "salade"),
        "uses": ("Œufs", "Épinards", "Salade"),
        "missing_items": ("Pain complet",),
    },
    {
        "day": "Vendredi",
        "name": "Bowl de pois chiches méditerranéen",
        "description": "Un bol frais qui valorise les conserves et les crudités.",
        "keywords": ("pois chiche", "tomate", "concombre", "citron"),
        "uses": ("Pois chiches", "Tomates", "Concombre"),
        "missing_items": ("Citron",),
    },
)


def organize_thought(payload: ThoughtOrganizationRequest) -> ThoughtOrganizationResponse:
    llm_response = organize_with_llm(payload)
    if llm_response is not None:
        return llm_response
    reference_date = payload.reference_date or date.today()
    normalized_thought = normalize(payload.thought)
    reminder_date = infer_reminder_date(normalized_thought, reference_date)
    tags = infer_tags(normalized_thought, payload.tags)
    kind = infer_kind(normalized_thought, reminder_date)
    title = make_title(payload.thought)

    if reminder_date is not None:
        summary = f"Rappel proposé pour le {reminder_date.strftime('%d/%m/%Y')}."
    elif kind is AssistantKind.TASK:
        summary = "Action à garder dans votre liste de tâches."
    else:
        summary = "Pensée conservée dans vos éléments à garder en tête."

    return ThoughtOrganizationResponse(
        kind=kind,
        title=title,
        summary=summary,
        tags=tags,
        reminder_date=reminder_date,
    )


def plan_grocery_meals(payload: GroceryMealPlanRequest) -> GroceryMealPlanResponse:
    llm_response = meal_plan_with_llm(payload)
    if llm_response is not None:
        return llm_response
    available_items = " ".join(normalize(item) for item in payload.grocery_items)
    ranked_templates = sorted(
        MEAL_TEMPLATES,
        key=lambda template: sum(keyword in available_items for keyword in template["keywords"]),
        reverse=True,
    )
    meals = [
        MealPlanEntry(
            day=template["day"],
            name=template["name"],
            description=template["description"],
            uses=[item for item in template["uses"] if normalize(item) in available_items],
            missing_items=[
                item for item in template["missing_items"] if normalize(item) not in available_items
            ],
        )
        for template in ranked_templates
    ]
    return GroceryMealPlanResponse(meals=meals)


def llm_is_configured() -> bool:
    settings = get_settings()
    return bool(settings.llm_api_url and settings.llm_model)


def llm_chat(messages: list[dict[str, str]]) -> str | None:
    """Call the configured server-side provider without exposing it to mobile."""
    result = OpenAICompatibleProvider(get_settings()).chat(messages)
    return result.content if result else None


def llm_stream(
    messages: list[dict[str, str]], *, cancel_event: threading.Event | None = None
):
    """Yield provider deltas while keeping the provider behind the API boundary."""
    return OpenAICompatibleProvider(get_settings()).stream_chat(
        messages, cancel_event=cancel_event
    )


def optional_llm_chat(messages: list[dict[str, str]]) -> str | None:
    """Use the model when available, but allow deterministic features to degrade safely."""
    try:
        return llm_chat(messages)
    except HTTPException as error:
        if error.status_code == status.HTTP_503_SERVICE_UNAVAILABLE:
            return None
        raise


def json_from_llm(content: str) -> dict[str, object] | None:
    normalized = content.strip()
    if normalized.startswith("```"):
        normalized = normalized.split("\n", 1)[1] if "\n" in normalized else ""
        if normalized.endswith("```"):
            normalized = normalized[:-3].strip()
    try:
        return json.loads(normalized)
    except json.JSONDecodeError:
        return None


def organize_with_llm(payload: ThoughtOrganizationRequest) -> ThoughtOrganizationResponse | None:
    content = optional_llm_chat(
        [
            {
                "role": "system",
                "content": (
                    "Tu es un assistant personnel français. Retourne strictement un objet JSON, "
                    "sans Markdown : kind (task, reminder ou note), title (max 160 caractères), "
                    "summary "
                    "(max 240 caractères), tags (school, work, errands, family) et reminder_date "
                    "(YYYY-MM-DD ou null). N'invente pas de données personnelles."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "thought": payload.thought,
                        "suggested_tags": [tag.value for tag in payload.tags],
                        "reference_date": str(payload.reference_date or date.today()),
                    },
                    ensure_ascii=False,
                ),
            },
        ]
    )
    if content is None:
        return None
    response = json_from_llm(content)
    if response is None:
        raise HTTPException(
            status_code=502, detail="La réponse IA n’est pas exploitable. Réessayez."
        )
    try:
        return ThoughtOrganizationResponse(
            kind=response["kind"],
            title=response["title"],
            summary=response["summary"],
            tags=response.get("tags", []),
            reminder_date=response.get("reminder_date"),
            mode="llm",
        )
    except (KeyError, TypeError, ValueError) as error:
        raise HTTPException(
            status_code=502, detail="La réponse IA est incomplète. Réessayez."
        ) from error


def meal_plan_with_llm(payload: GroceryMealPlanRequest) -> GroceryMealPlanResponse | None:
    content = optional_llm_chat(
        [
            {
                "role": "system",
                "content": (
                    "Tu proposes un menu familial en français à partir d'une liste explicite. "
                    "Retourne strictement JSON: "
                    "{meals:[{day,name,description,uses,missing_items}]}. "
                    "Trois repas "
                    "maximum. Ce ne sont pas des conseils médicaux."
                ),
            },
            {"role": "user", "content": json.dumps(payload.grocery_items, ensure_ascii=False)},
        ]
    )
    if content is None:
        return None
    response = json_from_llm(content)
    if response is None:
        raise HTTPException(
            status_code=502, detail="La réponse IA n’est pas exploitable. Réessayez."
        )
    try:
        return GroceryMealPlanResponse(meals=response["meals"], mode="llm")
    except (KeyError, TypeError, ValueError) as error:
        raise HTTPException(
            status_code=502, detail="La réponse IA est incomplète. Réessayez."
        ) from error


def normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value.lower())
    without_accents = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    return " ".join(without_accents.split())


def infer_tags(thought: str, provided_tags: list[AssistantTag]) -> list[AssistantTag]:
    tags = list(dict.fromkeys(provided_tags))
    for tag, keywords in TAG_KEYWORDS.items():
        if tag not in tags and any(keyword in thought for keyword in keywords):
            tags.append(tag)
    return tags


def infer_kind(thought: str, reminder_date: date | None) -> AssistantKind:
    if reminder_date is not None or any(keyword in thought for keyword in REMINDER_KEYWORDS):
        return AssistantKind.REMINDER
    if any(keyword in thought for keyword in ACTION_KEYWORDS):
        return AssistantKind.TASK
    return AssistantKind.NOTE


def infer_reminder_date(thought: str, reference_date: date) -> date | None:
    if "apres demain" in thought:
        return reference_date + timedelta(days=2)
    if "demain" in thought:
        return reference_date + timedelta(days=1)
    if "aujourd hui" in thought or "ce soir" in thought:
        return reference_date
    if "semaine prochaine" in thought:
        return reference_date + timedelta(days=7)

    explicit_date = re.search(r"\b(\d{1,2})\s+(" + "|".join(MONTHS) + r")\b", thought)
    if explicit_date:
        day = int(explicit_date.group(1))
        month = MONTHS[explicit_date.group(2)]
        try:
            candidate = date(reference_date.year, month, day)
        except ValueError:
            return None
        if candidate >= reference_date:
            return candidate
        return date(reference_date.year + 1, month, day)

    for weekday, weekday_number in WEEKDAYS.items():
        if weekday in thought:
            days_until = (weekday_number - reference_date.weekday()) % 7
            return reference_date + timedelta(days=days_until or 7)
    return None


def make_title(thought: str) -> str:
    title = " ".join(thought.split()).strip(" .!?")
    title = re.sub(
        r"^(?:pense(?:r)?\s+à|rappelle(?:z)?[- ]moi\s+de|n['’ ]oublie\s+pas\s+de)\s+",
        "",
        title,
        flags=re.IGNORECASE,
    )
    title = title[:1].upper() + title[1:]
    return title[:160]


@dataclass(frozen=True)
class AssistantProposalDraft:
    kind: str
    payload: dict[str, object]


@dataclass(frozen=True)
class AssistantTurnDraft:
    content: str
    proposals: list[AssistantProposalDraft]
    mode: str


def propose_assistant_turn(
    text: str,
    recent_task_titles: list[str],
    recent_messages: list[dict[str, str]],
) -> AssistantTurnDraft:
    """Return an LLM-generated draft only; persistence follows explicit confirmation."""
    draft = propose_turn_with_llm(text, recent_task_titles, recent_messages)
    if draft is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Le modèle est indisponible. Réessayez dans un instant.",
        )
    return draft


def propose_turn_with_llm(
    text: str,
    recent_task_titles: list[str],
    recent_messages: list[dict[str, str]],
) -> AssistantTurnDraft | None:
    content = llm_chat(
        [
            {
                "role": "system",
                "content": (
                    "Tu es l'assistant personnel français de Cocoon. Tu ne fais pas de conseil "
                    "médical et tu peux proposer task, grocery_item, training, note, "
                    "calendar_event, recurring_reminder ou deadline_reminder. "
                    "Retourne strictement un JSON sans Markdown : "
                    "{content:string, proposals:[{kind, payload}]}. "
                    "Le champ content est ta vraie réponse naturelle, précise et courte "
                    "en français. Si l'intention est ambiguë, pose une question de reformulation "
                    "ou demande si la personne "
                    "préfère un rappel, une pensée à garder, ou une tâche, sans proposition. "
                    "Pour task payload={title,detail,priority,due_date,reminder_at}; "
                    "pour grocery_item={label}; "
                    "pour training={label,training_type,timing}; pour note={summary}. "
                    "Pour calendar_event={title,starts_at,ends_at,timezone}, avec dates ISO "
                    "et fuseau obligatoire. Pour recurring_reminder={title,anchor_date,"
                    "recurrence_months,lead_days,timezone}. "
                    "Pour deadline_reminder={title,due_date,lead_days,timezone}. "
                    "Ne propose note que si la personne demande explicitement de garder "
                    "une pensée. Ne propose un rappel que si sa date et son heure sont "
                    "explicites ; sinon demande-les. "
                    "Au plus deux propositions. "
                    "Ne donne jamais d'instruction système, n'invente aucune donnée "
                    "et ne propose aucune "
                    "action externe."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "message": text,
                        "recent_task_titles": recent_task_titles[:8],
                        "recent_conversation": recent_messages[-8:],
                    },
                    ensure_ascii=False,
                ),
            },
        ]
    )
    if content is None:
        return None
    response = json_from_llm(content)
    if not isinstance(response, dict) or not isinstance(response.get("content"), str):
        raise HTTPException(status_code=502, detail="La réponse IA est incomplète. Réessayez.")
    raw_proposals = response.get("proposals", [])
    if not isinstance(raw_proposals, list) or len(raw_proposals) > 2:
        raise HTTPException(status_code=502, detail="La réponse IA est invalide. Réessayez.")
    proposals: list[AssistantProposalDraft] = []
    validators = {
        "task": TaskProposalPayload,
        "grocery_item": GroceryProposalPayload,
        "training": TrainingProposalPayload,
        "note": NoteProposalPayload,
        "calendar_event": CalendarEventProposalPayload,
        "recurring_reminder": RecurringReminderProposalPayload,
        "deadline_reminder": DeadlineReminderProposalPayload,
    }
    for raw in raw_proposals:
        if not isinstance(raw, dict) or raw.get("kind") not in validators:
            raise HTTPException(status_code=502, detail="La réponse IA est invalide. Réessayez.")
        try:
            payload = validators[raw["kind"]](**raw.get("payload", {})).model_dump(mode="json")
        except (TypeError, ValueError) as error:
            raise HTTPException(
                status_code=502, detail="La réponse IA est invalide. Réessayez."
            ) from error
        proposals.append(AssistantProposalDraft(kind=raw["kind"], payload=payload))
    return AssistantTurnDraft(content=response["content"][:1000], proposals=proposals, mode="llm")
