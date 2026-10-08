"""French normalization for exact terms; PostgreSQL additionally supplies stemming."""

import re
import unicodedata

STOP_WORDS = frozenset(
    "a au aux avec ce ces cet cette chez comment dans de des du elle en est et fait "
    "il ils je j la le les leur lui ma mais me mes mon ne nos notre nous on ou par pas "
    "pour pourquoi que quel quelle quels quelles qui sa sans se ses son sur te tes toi "
    "ton tu un une vos votre vous y personne utilisateur prefere aime besoin voudrais "
    "souhaite veux peux peut dois donne rappelle trouve concernant propos".split()
)


def normalize(value: str) -> str:
    raw = unicodedata.normalize("NFKD", value.casefold())
    return " ".join(
        re.findall(r"[a-z0-9]+", "".join(char for char in raw if not unicodedata.combining(char)))
    )


def terms(value: str) -> set[str]:
    return {word for word in normalize(value).split() if len(word) > 2 and word not in STOP_WORDS}


def summary_key(value: str) -> str:
    return normalize(value)
