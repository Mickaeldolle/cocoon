"""Authenticated, bounded client interaction events."""

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from app.modules.audit.service import note_request_details
from app.modules.auth.dependencies import AuthenticatedSession, get_authenticated_session

router = APIRouter(prefix="/api/audit", tags=["audit"])


class ButtonPress(BaseModel):
    action: str = Field(min_length=3, max_length=64)


# Only these stable identifiers can be stored. Never accept labels, text, URLs or IDs.
ALLOWED_BUTTON_ACTIONS = {
    "assistant.back",
    "assistant.memory.keep",
    "assistant.memory.skip",
    "assistant.suggestion.choose",
    "assistant.send",
    "assistant.stop",
    "assistant.composer.tap_empty",
    "assistant.voice.unavailable",
    "conversations.back",
    "conversations.create.toggle",
    "conversations.create.close",
    "conversations.create.submit",
    "conversations.open",
    "conversations.invite.accept",
    "conversations.invite.decline",
    "dashboard.back",
    "dashboard.profile.open",
    "dashboard.training.select",
    "dashboard.item.add",
    "dashboard.retry",
    "dashboard.item.toggle",
    "dashboard.meal.plan",
    "home.notifications.open",
    "home.profile.open",
    "home.capture.cancel",
    "home.retry",
    "home.proposal.confirm",
    "home.proposal.dismiss",
    "memory.back",
    "memory.retry",
    "memory.edit.save",
    "memory.edit.open",
    "memory.forget.prompt",
    "memory.forget.cancel",
    "memory.forget.confirm",
    "notifications.back",
    "notifications.enable",
    "notifications.disable.cancel",
    "notifications.disable.confirm",
    "notifications.disable.prompt",
    "notifications.retry",
    "notifications.open",
    "profile.back",
    "profile.theme.select",
    "profile.memory.open",
    "profile.projects.open",
    "profile.retry",
    "profile.logout",
    "profile.biometric.toggle",
    "profile.passkey.retry",
    "profile.passkey.create",
    "profile.passkey.revoke",
    "profile.device.revoke",
    "profile.save",
    "projects.back",
    "projects.create",
    "projects.retry",
    "projects.reopen",
    "projects.status.toggle",
    "projects.complete",
    "protected.press",
    "space.back",
    "space.role.select",
    "space.member.add",
    "spaces.back",
    "spaces.create.toggle",
    "spaces.create.submit",
    "spaces.open",
    "auth.password.visibility",
    "auth.submit",
    "auth.biometric",
    "auth.passkey",
    "conversation.back",
    "conversation.message.retry",
    "conversation.voice.discard",
    "conversation.voice.finish",
    "conversation.voice.play",
    "conversation.voice.record",
    "conversation.message.send",
}


@router.post("/button-press", status_code=status.HTTP_204_NO_CONTENT)
def button_press(
    body: ButtonPress,
    request: Request,
    authenticated: AuthenticatedSession = Depends(get_authenticated_session),
) -> Response:
    if body.action not in ALLOWED_BUTTON_ACTIONS:
        raise HTTPException(status_code=422, detail="Action inconnue.")
    note_request_details(request, ui_action=body.action)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
