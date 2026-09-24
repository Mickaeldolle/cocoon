import json
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException, status

from app.modules.assistant.service import llm_chat
from app.modules.neural.models import MemoryKind


@dataclass(frozen=True)
class Understanding:
    kind: MemoryKind
    summary: str
    reason: str
    capability: str | None
    payload: dict[str, object]
    valid_from: datetime | None = None
    review_at: datetime | None = None
    clarification: str | None = None
    mode: str = "rules"


def safe_timezone(value: str) -> ZoneInfo:
    try:
        return ZoneInfo(value)
    except ZoneInfoNotFoundError:
        return ZoneInfo("Europe/Paris")


def parse_reminder_at(text: str, timezone: str, due_date: datetime | None) -> datetime | None:
    """Parse only explicit, user-visible clock hints; never infer a hidden reminder time."""
    match = re.search(r"\b([01]?\d|2[0-3])(?:h|:)([0-5]\d)?\b", text.lower())
    if not match or due_date is None:
        return None
    try:
        local_date = due_date.astimezone(safe_timezone(timezone)).date()
        local = datetime(
            local_date.year,
            local_date.month,
            local_date.day,
            int(match.group(1)),
            int(match.group(2) or 0),
            tzinfo=safe_timezone(timezone),
        )
        return local.astimezone(UTC)
    except (ValueError, OverflowError):
        return None


def understand(text: str) -> Understanding:
    rules = understand_with_rules(text)
    return understand_with_llm(text, rules) or rules


WEEKDAYS = {
    "lundi": 0,
    "mardi": 1,
    "mercredi": 2,
    "jeudi": 3,
    "vendredi": 4,
    "samedi": 5,
    "dimanche": 6,
}
MONTHS = {
    "janvier": 1,
    "février": 2,
    "fevrier": 2,
    "mars": 3,
    "avril": 4,
    "mai": 5,
    "juin": 6,
    "juillet": 7,
    "août": 8,
    "aout": 8,
    "septembre": 9,
    "octobre": 10,
    "novembre": 11,
    "décembre": 12,
    "decembre": 12,
}


def infer_explicit_date(text: str, reference: date) -> date | None:
    """Resolve explicit French weekday/day or numeric date mentions."""
    match = re.search(
        r"\b(lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche)\s+(\d{1,2})"
        r"(?:\s+(?:de|du)\s+)?(janvier|février|fevrier|mars|avril|mai|juin|juillet|août|aout|"
        r"septembre|octobre|novembre|décembre|decembre)?\b",
        text.lower(),
    )
    if match:
        weekday = WEEKDAYS[match.group(1)]
        day = int(match.group(2))
        month = MONTHS.get(match.group(3) or "", reference.month)
        year = reference.year
        try:
            candidate = date(year, month, day)
        except ValueError:
            return None
        if candidate < reference:
            candidate = date(year + (1 if month <= reference.month else 0), month, day)
        # Keep the explicit weekday as a guardrail; if the number is inconsistent,
        # choose the next matching weekday rather than claiming the wrong date.
        if candidate.weekday() != weekday:
            delta = (weekday - candidate.weekday()) % 7
            candidate += timedelta(days=delta)
        return candidate

    numeric = re.search(
        r"\b(?:le\s+)?(0?[1-9]|[12]\d|3[01])[/.-](0?[1-9]|1[0-2])"
        r"(?:[/.-](\d{4}))?\b",
        text.lower(),
    )
    if not numeric:
        weekday_only = re.search(
            r"\b(lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche)\b", text.lower()
        )
        if not weekday_only:
            return None
        delta = (WEEKDAYS[weekday_only.group(1)] - reference.weekday()) % 7
        return reference + timedelta(days=delta)
    day, month = int(numeric.group(1)), int(numeric.group(2))
    year = int(numeric.group(3) or reference.year)
    try:
        candidate = date(year, month, day)
    except ValueError:
        return None
    if numeric.group(3) is None and candidate < reference:
        candidate = date(year + 1, month, day)
    return candidate


def infer_relative_date(text: str, reference: date) -> date | None:
    """Resolve only explicit relative date phrases, never vague temporal language."""
    lower = text.lower()
    if re.search(r"\baujourd'hui\b|\baujourd’hui\b", lower):
        return reference
    if "après-demain" in lower or "apres-demain" in lower:
        return reference + timedelta(days=2)
    if re.search(r"\bdemain\b|\bce soir\b", lower):
        return reference + timedelta(days=1)
    relative = re.search(r"\bdans\s+(\d{1,3})\s+jours?\b", lower)
    if relative:
        return reference + timedelta(days=int(relative.group(1)))
    return None


def format_date_fr(value: date) -> str:
    months = (
        "janvier",
        "février",
        "mars",
        "avril",
        "mai",
        "juin",
        "juillet",
        "août",
        "septembre",
        "octobre",
        "novembre",
        "décembre",
    )
    weekdays = tuple(WEEKDAYS)
    return f"{weekdays[value.weekday()]} {value.day} {months[value.month - 1]}"


def engagement_subject(text: str) -> str:
    for candidate in ("entretien", "rendez-vous", "réunion", "rdv"):
        if candidate in text.lower():
            return candidate
    return "événement"


def understand_with_rules(text: str) -> Understanding:
    normalized = " ".join(text.split())
    lower = normalized.lower()
    now = datetime.now(UTC)
    relative_date = infer_relative_date(normalized, now.date())
    date_hint = (
        datetime.combine(relative_date, datetime.min.time(), tzinfo=UTC)
        if relative_date is not None
        else None
    )
    explicit_date = infer_explicit_date(normalized, now.date())
    if re.search(r"\b(acheter|appeler|réserver|envoyer|préparer|faire)\b", lower):
        title = re.sub(r"^(?:pense(?:r)? à |rappelle(?:-moi)? de )", "", normalized, flags=re.I)[
            :160
        ]
        return Understanding(
            MemoryKind.INTENTION,
            title,
            "Vous l'avez formulé comme une action à réaliser.",
            "task",
            {"title": title, "due_date": date_hint.date().isoformat() if date_hint else None},
            review_at=date_hint,
        )
    if re.search(
        r"\b(mardi|lundi|mercredi|jeudi|vendredi|samedi|dimanche|rendez-vous|rdv)\b", lower
    ):
        engagement_date = explicit_date or (date_hint.date() if date_hint else None)
        subject = engagement_subject(normalized)
        engagement_summary = (
            f"Votre {subject} est prévu le {format_date_fr(engagement_date)}."
            if engagement_date
            else normalized[:240]
        )
        return Understanding(
            MemoryKind.ENGAGEMENT,
            engagement_summary,
            "J’ai repéré un engagement daté dans votre capture.",
            "reminder" if engagement_date else None,
            {
                "title": engagement_summary,
                "due_date": engagement_date.isoformat() if engagement_date else None,
            }
            if engagement_date
            else {},
            valid_from=(
                datetime.combine(engagement_date, datetime.min.time(), tzinfo=UTC)
                if engagement_date
                else date_hint
            ),
            review_at=(
                datetime.combine(engagement_date, datetime.min.time(), tzinfo=UTC)
                if engagement_date
                else date_hint
            ),
            clarification=(
                f"À quelle heure est prévu votre {subject} du {format_date_fr(engagement_date)} ?"
                if engagement_date
                and "heure" not in lower
                and not re.search(r"\b\d{1,2}[h:]\d{0,2}\b", lower)
                else None
            ),
        )
    if re.search(r"\b(est|utilise|préfère|habite|allergique|aime)\b", lower):
        return Understanding(
            MemoryKind.INFORMATION,
            normalized[:240],
            "Conservé comme information personnelle à vérifier si elle évolue.",
            None,
            {},
            review_at=now + timedelta(days=90),
        )
    return Understanding(
        MemoryKind.QUESTION,
        normalized[:240],
        "Conservé sans supposer de destination.",
        None,
        {},
        clarification=(
            "Souhaitez-vous que je vous le rappelle ou que je le garde simplement en mémoire ?"
        ),
    )


def understand_with_llm(text: str, rules: Understanding) -> Understanding | None:
    """Enrich a deterministic temporal reading with a strictly bounded LLM result."""
    try:
        content = llm_chat(
            [
                {
                    "role": "system",
                    "content": (
                        "Tu comprends une capture personnelle en français. Réponds strictement "
                        "avec un unique JSON, sans Markdown : "
                        '{"kind":"information|intention|engagement|question",'
                        '"summary":"texte court",'
                        '"reason":"explication courte et lisible",'
                        '"capability":"task|reminder ou null",'
                        '"clarification":"question courte ou null"}. '
                        "N'invente jamais de date, de personne ou de fait. Une capability task "
                        "n'est permise que pour une intention explicite. Pour un engagement, "
                        "reprends exactement le jour et le numéro présents dans la capture."
                    ),
                },
                {"role": "user", "content": text},
            ]
        )
    except HTTPException as error:
        if error.status_code == status.HTTP_503_SERVICE_UNAVAILABLE:
            return None
        raise
    if content is None:
        return None

    try:
        payload = json.loads(content.strip().removeprefix("```json").removesuffix("```").strip())
        model_kind = MemoryKind(payload["kind"])
        summary = payload["summary"].strip()[:240]
        reason = payload["reason"].strip()[:320]
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None
    if not summary or not reason:
        return None

    # A question or a low-signal acknowledgement is never a durable memory
    # candidate.  The model may be useful for wording, but it must not be able
    # to turn "Merci" or "Comment fonctionne Docker ?" into a personal fact.
    # Keep the deterministic clarification so the capture route produces no
    # note proposal for these inputs.
    if rules.kind is MemoryKind.QUESTION:
        return rules

    clarification = payload.get("clarification")
    if rules.kind == MemoryKind.ENGAGEMENT:
        # The model may enrich wording, but it must not erase the explicit date.
        summary = rules.summary
        clarification = rules.clarification
    elif not isinstance(clarification, str) or not clarification.strip():
        clarification = rules.clarification
    else:
        clarification = clarification.strip()[:240]
    # An explicit action detected deterministically must remain executable even
    # when the model mistakes it for an event or a generic note.
    kind = rules.kind if rules.kind in {MemoryKind.INTENTION, MemoryKind.ENGAGEMENT} else model_kind
    if rules.kind == MemoryKind.ENGAGEMENT:
        reason = rules.reason
    capability = rules.capability
    if kind == MemoryKind.INTENTION and payload.get("capability") == "task":
        capability = "task"
    if kind not in {MemoryKind.INTENTION, MemoryKind.ENGAGEMENT}:
        capability = None
    return Understanding(
        kind=kind,
        summary=summary,
        reason=reason,
        capability=capability,
        payload={"title": summary, "due_date": rules.payload.get("due_date")} if capability else {},
        valid_from=rules.valid_from,
        review_at=rules.review_at,
        clarification=clarification,
        mode="llm",
    )
