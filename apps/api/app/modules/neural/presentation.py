"""Response mapping used by neural HTTP routes and the capture worker."""

from app.modules.neural.models import NeuralProposal
from app.modules.neural.schemas import ProposalResponse


def proposal_response(item: NeuralProposal) -> ProposalResponse:
    return ProposalResponse(
        id=item.id,
        capability=item.capability,
        payload=item.payload,
        payload_version=item.payload_version,
        reason=item.reason,
        status=item.status,
        confirmed_at=item.confirmed_at,
        label=str(item.payload.get("label") or item.payload.get("title") or item.capability),
    )
