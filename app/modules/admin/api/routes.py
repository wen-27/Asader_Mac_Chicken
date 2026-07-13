"""Admin panel API routes."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config.settings import Settings, get_settings
from app.modules.admin.infrastructure.models import AdminUserORM
from app.modules.admin.infrastructure.passwords import verify_password
from app.modules.admin.realtime import admin_realtime_hub
from app.modules.orders.application.payment_proofs import ensure_payment_proof_status, payment_proof_missing, payment_requires_proof
from app.modules.orders.infrastructure.models import OrderORM
from app.modules.orders.infrastructure.thermal_printer import ThermalPrinterError, print_order_receipt
from app.modules.telegram.infrastructure.models import TelegramMessageORM
from app.modules.whatsapp.infrastructure.whatsapp_cloud_client import WhatsAppCloudClient
from app.shared.domain.value_object import ChatId
from app.shared.infrastructure.database.session import get_async_session


SESSION_COOKIE = "asadero_admin_session"

router = APIRouter(prefix="/api", tags=["admin"])
ws_router = APIRouter(tags=["admin-realtime"])


class SignInEmailRequest(BaseModel):
    email: str
    password: str


class SendOrderMessageRequest(BaseModel):
    body: str
    withButtons: bool = False


@ws_router.websocket("/ws")
async def admin_realtime(websocket: WebSocket) -> None:
    await admin_realtime_hub.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        admin_realtime_hub.disconnect(websocket)


def _admin_user_payload(user: AdminUserORM) -> dict[str, object]:
    return {
        "user": {
            "id": str(user.id),
            "email": user.email,
            "name": user.name,
        }
    }


async def _current_admin_user(
    request: Request,
    session: AsyncSession,
) -> AdminUserORM | None:
    raw_user_id = request.cookies.get(SESSION_COOKIE)
    if raw_user_id is None or not raw_user_id.isdigit():
        return None
    result = await session.execute(
        select(AdminUserORM).where(
            AdminUserORM.id == int(raw_user_id),
            AdminUserORM.is_active.is_(True),
        )
    )
    return result.scalar_one_or_none()


@router.get("/auth/get-session")
async def get_session(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> dict[str, object] | None:
    user = await _current_admin_user(request, session)
    if user is None:
        return None
    return _admin_user_payload(user)


@router.post("/auth/sign-in/email")
async def sign_in_email(
    payload: SignInEmailRequest,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> dict[str, object]:
    email = payload.email.strip().lower()
    result = await session.execute(
        select(AdminUserORM).where(
            AdminUserORM.email == email,
            AdminUserORM.is_active.is_(True),
        )
    )
    user = result.scalar_one_or_none()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid credentials",
        )
    response.set_cookie(
        SESSION_COOKIE,
        str(user.id),
        httponly=True,
        samesite="lax",
        secure=False,
        max_age=60 * 60 * 12,
    )
    return _admin_user_payload(user)


@router.post("/auth/sign-out")
async def sign_out(response: Response) -> dict[str, bool]:
    response.delete_cookie(SESSION_COOKIE)
    return {"ok": True}


@router.get("/admin/orders/{kind}")
async def list_orders(
    kind: str,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> dict[str, list[dict[str, object]]]:
    await _require_admin(request, session)
    statuses_by_kind = {
        "incoming": {"PENDING", "CONFIRMED"},
        "accepted": {"PREPARING", "DELIVERED"},
        "rejected": {"CANCELLED"},
    }
    statuses = statuses_by_kind.get(kind)
    if statuses is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="unknown order list")
    result = await session.execute(
        select(OrderORM)
        .options(selectinload(OrderORM.items))
        .where(OrderORM.status.in_(statuses))
        .order_by(OrderORM.created_at.desc())
    )
    return {"data": [_order_payload(row) for row in result.scalars().all()]}


@router.get("/admin/order-details/{order_id}")
async def get_order_detail(
    order_id: str,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> dict[str, object]:
    await _require_admin(request, session)
    order = await _find_order(session, order_id)
    return {"data": _order_payload(order)}


@router.get("/admin/orders/{order_id}")
async def get_order(
    order_id: str,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> dict[str, object]:
    await _require_admin(request, session)
    order = await _find_order(session, order_id)
    return {"data": _order_payload(order)}


@router.post("/admin/orders/{order_id}/print")
async def print_order(
    order_id: str,
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> dict[str, object]:
    await _require_admin(request, session)
    order = await _find_order(session, order_id)
    try:
        await print_order_receipt(order, settings.thermal_printer_name)
    except ThermalPrinterError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"No se pudo imprimir en {settings.thermal_printer_name}: {exc}",
        ) from exc
    order.printed_at = datetime.now(timezone.utc)
    await session.commit()
    await admin_realtime_hub.broadcast({"type": "orders.changed", "orderId": order.order_number})
    return {"data": _order_payload(order)}


@router.patch("/admin/orders/{order_id}/accept")
async def accept_order(
    order_id: str,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> dict[str, object]:
    await _require_admin(request, session)
    order = await _find_order(session, order_id)
    if not await ensure_payment_proof_status(session, order):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Falta comprobante de pago para pasar este pedido a preparacion.",
        )
    order.status = "PREPARING"
    await session.commit()
    await admin_realtime_hub.broadcast({"type": "orders.changed", "orderId": order.order_number})
    return {"data": _order_payload(order)}


@router.patch("/admin/orders/{order_id}/reject")
async def reject_order(
    order_id: str,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> dict[str, object]:
    await _require_admin(request, session)
    order = await _find_order(session, order_id)
    order.status = "CANCELLED"
    await session.commit()
    await admin_realtime_hub.broadcast({"type": "orders.changed", "orderId": order.order_number})
    return {"data": _order_payload(order)}


@router.patch("/admin/orders/{order_id}/status")
async def update_order_status(
    order_id: str,
    payload: dict[str, str],
    request: Request,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> dict[str, object]:
    await _require_admin(request, session)
    order = await _find_order(session, order_id)
    next_status = payload.get("status", order.status)
    if next_status == "PREPARING" and not await ensure_payment_proof_status(session, order):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Falta comprobante de pago para pasar este pedido a preparacion.",
        )
    order.status = next_status
    await session.commit()
    await admin_realtime_hub.broadcast({"type": "orders.changed", "orderId": order.order_number})
    return {"data": _order_payload(order)}


@router.get("/admin/conversations")
async def list_conversations(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> dict[str, list[dict[str, object]]]:
    await _require_admin(request, session)
    result = await session.execute(
        select(TelegramMessageORM).order_by(TelegramMessageORM.created_at.desc()).limit(250)
    )
    chats: dict[int, TelegramMessageORM] = {}
    for message in result.scalars().all():
        chats.setdefault(message.chat_id, message)
    return {"data": [_chat_summary_payload(message) for message in chats.values()]}


@router.get("/admin/conversations/media/{media_id}")
async def get_conversation_media(
    media_id: str,
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> Response:
    await _require_admin(request, session)
    if not settings.whatsapp_access_token:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="whatsapp token is not configured")
    headers = {"Authorization": f"Bearer {settings.whatsapp_access_token}"}
    metadata_url = f"https://graph.facebook.com/{settings.whatsapp_graph_api_version}/{media_id}"
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            metadata_response = await client.get(metadata_url, headers=headers)
            metadata_response.raise_for_status()
            metadata = metadata_response.json()
            media_url = metadata.get("url")
            if not media_url:
                raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="whatsapp media url missing")
            media_response = await client.get(media_url, headers=headers)
            media_response.raise_for_status()
    except HTTPException:
        raise
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"whatsapp media request failed with status {exc.response.status_code}",
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="whatsapp media request failed") from exc
    media_type = metadata.get("mime_type") or media_response.headers.get("content-type") or "application/octet-stream"
    return Response(
        content=media_response.content,
        media_type=media_type,
        headers={"Cache-Control": "private, max-age=300"},
    )


@router.get("/admin/conversations/{chat_id}/messages")
async def list_conversation_messages(
    chat_id: str,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> dict[str, list[dict[str, object]]]:
    await _require_admin(request, session)
    result = await session.execute(
        select(TelegramMessageORM)
        .where(TelegramMessageORM.chat_id == _chat_id_to_int(chat_id))
        .order_by(TelegramMessageORM.created_at.desc(), TelegramMessageORM.id.desc())
        .limit(200)
    )
    messages = list(reversed(result.scalars().all()))
    return {"data": [_message_payload(message) for message in messages]}


@router.post("/admin/conversations/{chat_id}/messages")
async def send_conversation_message(
    chat_id: str,
    payload: dict[str, str],
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> dict[str, object]:
    await _require_admin(request, session)
    body = payload.get("body", "").strip()
    if not body:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="body is required")
    sent_message = await WhatsAppCloudClient(settings).send_text_message(ChatId(_chat_id_to_int(chat_id)), body)
    row = TelegramMessageORM(
        chat_id=sent_message.chat_id.value,
        direction="outbound",
        message_text=sent_message.text_raw,
        normalized_message_text=sent_message.text_normalized,
        message_type="admin_text",
        telegram_message_id=sent_message.message_id,
        update_id=0,
        created_at=sent_message.received_at,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    await admin_realtime_hub.broadcast({"type": "conversations.changed", "chatId": chat_id})
    return {"data": _message_payload(row)}


@router.get("/admin/conversations/{chat_id}/control")
async def get_conversation_control(
    chat_id: str,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> dict[str, dict[str, object]]:
    await _require_admin(request, session)
    return {"data": {"aiEnabled": True, "aiActive": True, "aiPausedUntil": None, "pausedUntil": None}}


@router.put("/admin/conversations/{chat_id}/control")
async def update_conversation_control(
    chat_id: str,
    payload: dict[str, bool],
    request: Request,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> dict[str, dict[str, object]]:
    await _require_admin(request, session)
    data = {
        "aiEnabled": bool(payload.get("aiEnabled", True)),
        "aiActive": bool(payload.get("aiEnabled", True)),
        "aiPausedUntil": None,
        "pausedUntil": None,
    }
    await admin_realtime_hub.broadcast({"type": "conversations.changed", "chatId": chat_id})
    return {"data": data}


@router.get("/admin/conversations/orders/{order_id}/messages")
async def list_order_messages(
    order_id: str,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> dict[str, list[dict[str, object]]]:
    await _require_admin(request, session)
    order = await _find_order(session, order_id)
    result = await session.execute(
        select(TelegramMessageORM)
        .where(
            TelegramMessageORM.chat_id == order.chat_id,
            TelegramMessageORM.created_at >= order.created_at,
        )
        .order_by(TelegramMessageORM.created_at.desc(), TelegramMessageORM.id.desc())
        .limit(200)
    )
    messages = list(reversed(result.scalars().all()))
    return {"data": [_message_payload(message, order_id=str(order.id)) for message in messages]}


@router.post("/admin/conversations/orders/{order_id}/messages")
async def send_order_message(
    order_id: str,
    payload: SendOrderMessageRequest,
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> dict[str, object]:
    await _require_admin(request, session)
    order = await _find_order(session, order_id)
    body = payload.body.strip()
    if not body:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="body is required")
    client = WhatsAppCloudClient(settings)
    if payload.withButtons:
        sent_message = await client.send_yes_no_message(
            ChatId(order.chat_id),
            body,
            yes_id=f"admin_preparing_yes:{order.id}",
            no_id=f"admin_preparing_no:{order.id}",
        )
    else:
        sent_message = await client.send_text_message(ChatId(order.chat_id), body)
    row = TelegramMessageORM(
        chat_id=sent_message.chat_id.value,
        direction="outbound",
        message_text=sent_message.text_raw,
        normalized_message_text=sent_message.text_normalized,
        message_type="admin_text",
        telegram_message_id=sent_message.message_id,
        update_id=0,
        created_at=sent_message.received_at,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    await admin_realtime_hub.broadcast({"type": "conversations.changed", "chatId": str(order.chat_id)})
    return {"data": _message_payload(row, order_id=str(order.id))}


async def _require_admin(request: Request, session: AsyncSession) -> AdminUserORM:
    user = await _current_admin_user(request, session)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not authenticated")
    return user


async def _find_order(session: AsyncSession, order_id: str) -> OrderORM:
    filters = [OrderORM.order_number == order_id]
    if order_id.isdigit():
        filters.append(OrderORM.id == int(order_id))
    result = await session.execute(
        select(OrderORM)
        .options(selectinload(OrderORM.items))
        .where(or_(*filters))
    )
    order = result.scalar_one_or_none()
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="order not found")
    return order


def _order_payload(order: OrderORM) -> dict[str, object]:
    display_number = f"MC-{order.id:04d}"
    fulfillment_type = order.fulfillment_type or "DELIVERY"
    proof_required = fulfillment_type == "DELIVERY" and payment_requires_proof(order.payment_method)
    proof_missing = proof_required and payment_proof_missing(order)
    return {
        "id": str(order.id),
        "orderNumber": display_number,
        "invoiceNumber": display_number,
        "status": _frontend_status(order.status),
        "fulfillmentType": fulfillment_type,
        "customer": {
            "fullName": order.customer_name,
            "phone": order.phone,
            "address": order.address,
            "neighborhood": order.neighborhood,
        },
        "paymentMethod": order.payment_method,
        "observations": order.observations,
        "items": [
            {
                "id": str(item.id),
                "productCode": item.product_code,
                "productName": item.product_name,
                "quantity": item.quantity,
                "unitPrice": item.unit_price_cop,
                "subtotal": item.subtotal_cop,
            }
            for item in order.items
        ],
        "subtotal": order.subtotal_cop,
        "deliveryFee": order.delivery_price_cop,
        "total": order.total_cop,
        "createdAt": order.created_at.isoformat(),
        "paymentProofRequired": proof_required,
        "paymentProofReceived": proof_required and order.payment_proof_received_at is not None,
        "paymentProofReceivedAt": order.payment_proof_received_at.isoformat()
        if order.payment_proof_received_at
        else None,
        "paymentProofMissing": proof_missing,
        "canMoveToPreparing": not proof_missing,
    }


def _frontend_status(status_value: str) -> str:
    if status_value == "PENDING":
        return "CONFIRMED"
    return status_value


def _chat_summary_payload(message: TelegramMessageORM) -> dict[str, object]:
    return {
        "chatId": str(message.chat_id),
        "customerId": None,
        "customerName": None,
        "customerPhone": str(message.chat_id),
        "lastMessage": _message_payload(message),
        "aiEnabled": True,
        "aiPausedUntil": None,
    }


def _message_payload(message: TelegramMessageORM, order_id: str | None = None) -> dict[str, object]:
    is_inbound = message.direction == "inbound"
    is_admin = message.message_type == "admin_text"
    attachment = None
    if message.media_id:
        attachment = {
            "type": message.media_type or message.message_type,
            "mediaId": message.media_id,
            "mimeType": message.media_mime_type,
            "sha256": message.media_sha256,
            "url": f"/api/admin/conversations/media/{message.media_id}",
        }
    return {
        "id": str(message.id),
        "orderId": order_id,
        "chatId": str(message.chat_id),
        "direction": "INBOUND" if is_inbound else "OUTBOUND",
        "sender": "CUSTOMER" if is_inbound else "ADMIN" if is_admin else "BOT",
        "body": message.message_text,
        "sentAt": (message.created_at or datetime.now(timezone.utc)).isoformat(),
        "attachment": attachment,
    }


def _chat_id_to_int(chat_id: str) -> int:
    digits = "".join(ch for ch in chat_id if ch.isdigit())
    if not digits:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid chat id")
    return int(digits)
