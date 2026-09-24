"""Shared lifecycle values for every user-confirmed proposal."""

from collections.abc import Iterable
from enum import StrEnum


class ProposalStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    FAILED = "failed"


def proposal_status_values(values: Iterable[ProposalStatus]) -> list[str]:
    """Persist enum values, not Python member names, for legacy String columns."""
    return [status.value for status in values]
