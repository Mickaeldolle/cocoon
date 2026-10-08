"""Deterministic mapping between memory meaning and storage layer."""

from app.modules.memory.conflicts import preference_subject
from app.modules.memory.text import normalize
from app.modules.neural.models import MemoryLayer, MemoryType


def classify_memory(summary: str) -> MemoryType:
    value = normalize(summary)
    if any(marker in value for marker in ("obligatoire", "imperativement", "doit ", "devra ")):
        return MemoryType.CONSTRAINT
    if preference_subject(summary):
        return MemoryType.PREFERENCE
    if any(marker in value for marker in ("objectif", "je souhaite", "je veux apprendre")):
        return MemoryType.GOAL
    if any(marker in value for marker in ("decide", "choisi", "retenu")):
        return MemoryType.DECISION
    return MemoryType.FACT


def layer_for_memory_type(memory_type: MemoryType) -> MemoryLayer:
    """Keep durable preferences separate from episodic observations."""
    if memory_type in {
        MemoryType.PREFERENCE,
        MemoryType.CONSTRAINT,
        MemoryType.FACT,
        MemoryType.GOAL,
        MemoryType.HABIT,
    }:
        return MemoryLayer.SEMANTIC
    return MemoryLayer.EPISODIC
