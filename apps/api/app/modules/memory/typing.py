"""Deterministic mapping between memory meaning and storage layer."""

from app.modules.neural.models import MemoryLayer, MemoryType


def layer_for_memory_type(memory_type: MemoryType) -> MemoryLayer:
    """Keep durable preferences separate from episodic observations."""
    if memory_type in {MemoryType.PREFERENCE, MemoryType.CONSTRAINT}:
        return MemoryLayer.SEMANTIC
    if memory_type is MemoryType.HABIT:
        return MemoryLayer.PROCEDURAL
    return MemoryLayer.EPISODIC
