import asyncio
from time import monotonic
from uuid import UUID

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.core.database import get_session
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.conversations.models import ConversationMember, ConversationMemberStatus
from app.modules.realtime.service import connections, tickets

router = APIRouter(tags=["realtime"])


def typing_recipients(session: Session, conversation_id: UUID, user_id: UUID) -> list[UUID]:
    members = list(
        session.scalars(
            select(ConversationMember).where(
                ConversationMember.conversation_id == conversation_id,
                ConversationMember.is_hidden.is_(False),
                ConversationMember.status == ConversationMemberStatus.ACCEPTED,
            )
        )
    )
    member_ids = [member.user_id for member in members]
    session.rollback()
    if user_id not in member_ids:
        return []
    return [member_id for member_id in member_ids if member_id != user_id]


@router.post("/api/realtime/ticket", status_code=status.HTTP_201_CREATED)
def issue_ticket(current_user: User = Depends(get_current_user)) -> dict[str, str]:
    return {"ticket": tickets.issue(current_user.id)}


@router.websocket("/api/ws")
async def websocket_endpoint(websocket: WebSocket, session: Session = Depends(get_session)) -> None:
    await websocket.accept()
    user_id = None
    try:
        payload = await asyncio.wait_for(websocket.receive_json(), timeout=5)
        if payload.get("type") != "authenticate" or not isinstance(payload.get("ticket"), str):
            await websocket.close(code=4401)
            return
        user_id = tickets.consume(payload["ticket"])
        if user_id is None:
            await websocket.close(code=4401)
            return
        await connections.connect(user_id, websocket)
        await websocket.send_json({"type": "authenticated"})
        last_typing_at = 0.0
        while True:
            incoming = await websocket.receive_json()
            if incoming.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
            elif incoming.get("type") == "conversation.typing":
                try:
                    conversation_id = UUID(incoming.get("conversation_id", ""))
                except (TypeError, ValueError, AttributeError):
                    continue
                is_typing = incoming.get("is_typing")
                if not isinstance(is_typing, bool):
                    continue
                if is_typing:
                    now = monotonic()
                    if now - last_typing_at < 0.75:
                        continue
                    last_typing_at = now
                recipients = await run_in_threadpool(
                    typing_recipients, session, conversation_id, user_id
                )
                if recipients:
                    await connections.broadcast(
                        recipients,
                        {
                            "type": "conversation.typing",
                            "conversation_id": str(conversation_id),
                            "user_id": str(user_id),
                            "is_typing": is_typing,
                        },
                    )
    except (WebSocketDisconnect, TimeoutError):
        pass
    finally:
        if user_id is not None:
            await connections.disconnect(user_id, websocket)
