import asyncio

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, status

from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.realtime.service import connections, tickets

router = APIRouter(tags=["realtime"])


@router.post("/api/realtime/ticket", status_code=status.HTTP_201_CREATED)
def issue_ticket(current_user: User = Depends(get_current_user)) -> dict[str, str]:
    return {"ticket": tickets.issue(current_user.id)}


@router.websocket("/api/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
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
        while True:
            incoming = await websocket.receive_json()
            if incoming.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
    except (WebSocketDisconnect, TimeoutError):
        pass
    finally:
        if user_id is not None:
            await connections.disconnect(user_id, websocket)
