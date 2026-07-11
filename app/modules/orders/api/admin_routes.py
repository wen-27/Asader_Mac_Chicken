"""FastAPI router for restaurant administrative order/factura workflows."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.orders.api.schemas import AdminOrderSchema, AdminOrderStatus, RejectOrderRequest
from app.modules.orders.application.admin_orders import (
    ACCEPTED_ORDER_STATUSES,
    INCOMING_ORDER_STATUSES,
    REJECTED_ORDER_STATUSES,
    AdminOrderStateError,
    mark_order_accepted,
    mark_order_printed,
    mark_order_rejected,
)
from app.modules.orders.domain.enums import OrderStatus
from app.modules.orders.infrastructure.admin_order_repository import SqlAlchemyAdminOrderRepository
from app.modules.orders.infrastructure.models import OrderItemORM, OrderORM
from app.shared.infrastructure.database.session import get_async_session

router = APIRouter(prefix="/admin/orders", tags=["admin-orders"])


@router.get("/incoming", response_model=list[AdminOrderSchema])
async def list_incoming_orders(
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> list[AdminOrderSchema]:
    orders = await SqlAlchemyAdminOrderRepository(session).list_by_statuses(INCOMING_ORDER_STATUSES)
    return [_order_to_schema(order) for order in orders]


@router.get("/accepted", response_model=list[AdminOrderSchema])
async def list_accepted_orders(
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> list[AdminOrderSchema]:
    orders = await SqlAlchemyAdminOrderRepository(session).list_by_statuses(ACCEPTED_ORDER_STATUSES)
    return [_order_to_schema(order) for order in orders]


@router.get("/rejected", response_model=list[AdminOrderSchema])
async def list_rejected_orders(
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> list[AdminOrderSchema]:
    orders = await SqlAlchemyAdminOrderRepository(session).list_by_statuses(REJECTED_ORDER_STATUSES)
    return [_order_to_schema(order) for order in orders]


@router.get("/{order_id}", response_model=AdminOrderSchema)
async def get_order_detail(
    order_id: int,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> AdminOrderSchema:
    order = await _get_order_or_404(session, order_id)
    return _order_to_schema(order)


@router.patch("/{order_id}/accept", response_model=AdminOrderSchema)
async def accept_order(
    order_id: int,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> AdminOrderSchema:
    order = await _get_order_or_404(session, order_id)
    try:
        mark_order_accepted(order)
    except AdminOrderStateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    await SqlAlchemyAdminOrderRepository(session).save(order)
    await session.commit()
    return _order_to_schema(order)


@router.patch("/{order_id}/reject", response_model=AdminOrderSchema)
async def reject_order(
    order_id: int,
    payload: RejectOrderRequest,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> AdminOrderSchema:
    order = await _get_order_or_404(session, order_id)
    try:
        mark_order_rejected(order, payload.reason)
    except AdminOrderStateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    await SqlAlchemyAdminOrderRepository(session).save(order)
    await session.commit()
    return _order_to_schema(order)


@router.patch("/{order_id}/printed", response_model=AdminOrderSchema)
async def mark_printed(
    order_id: int,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> AdminOrderSchema:
    order = await _get_order_or_404(session, order_id)
    try:
        mark_order_printed(order)
    except AdminOrderStateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    await SqlAlchemyAdminOrderRepository(session).save(order)
    await session.commit()
    return _order_to_schema(order)


async def _get_order_or_404(session: AsyncSession, order_id: int) -> OrderORM:
    order = await SqlAlchemyAdminOrderRepository(session).get_by_id(order_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="order not found")
    return order


def _order_to_schema(order: OrderORM) -> AdminOrderSchema:
    return AdminOrderSchema(
        id=str(order.id),
        orderNumber=order.order_number,
        invoiceNumber=order.order_number,
        status=_admin_status(order.status),
        customer={
            "fullName": order.customer_name,
            "phone": order.phone,
            "address": order.address,
            "neighborhood": order.neighborhood,
        },
        paymentMethod=order.payment_method,
        observations=order.observations,
        items=[_item_to_schema(item) for item in order.items],
        subtotal=order.subtotal_cop,
        deliveryFee=order.delivery_price_cop,
        total=order.total_cop,
        createdAt=order.created_at,
        acceptedAt=order.accepted_at,
        rejectedAt=order.rejected_at,
        printedAt=order.printed_at,
        rejectionReason=order.rejection_reason,
    )


def _item_to_schema(item: OrderItemORM) -> dict[str, object]:
    return {
        "id": str(item.id),
        "productCode": item.product_code,
        "productName": item.product_name,
        "quantity": item.quantity,
        "unitPrice": item.unit_price_cop,
        "subtotal": item.subtotal_cop,
    }


def _admin_status(status_value: str) -> AdminOrderStatus:
    if status_value in {OrderStatus.ACCEPTED.value}:
        return AdminOrderStatus.ACCEPTED
    if status_value == OrderStatus.REJECTED.value:
        return AdminOrderStatus.REJECTED
    if status_value == OrderStatus.PRINTED.value:
        return AdminOrderStatus.PRINTED
    return AdminOrderStatus.PENDING

