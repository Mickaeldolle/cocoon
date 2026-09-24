from app.modules.assistant.models import AssistantProposalStatus
from app.modules.assistant.proposal_types import ProposalStatus
from app.modules.neural.models import NeuralProposal


def test_assistant_and_capture_proposals_share_the_same_lifecycle_values() -> None:
    assert AssistantProposalStatus is ProposalStatus
    assert [status.value for status in ProposalStatus] == [
        "pending",
        "confirmed",
        "cancelled",
        "expired",
        "failed",
    ]
    assert NeuralProposal.__table__.c.status.type.enums == [
        status.value for status in ProposalStatus
    ]
