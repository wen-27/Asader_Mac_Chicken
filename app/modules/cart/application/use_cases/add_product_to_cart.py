"""Cart use case for validating product availability and adding price snapshots to the session cart."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

from app.modules.cart.application.use_cases.results import CartOperationStatus, CartResult
from app.modules.cart.domain.cart_item import CartItem
from app.modules.catalog.application.ports import ProductRepository
from app.modules.catalog.domain.specifications import ProductAvailabilitySpecification
from app.modules.conversations.application.ports import TelegramSessionRepository
from app.modules.conversations.domain.telegram_session import TelegramSession
from app.shared.domain.money import MoneyCOP
from app.shared.domain.value_object import ChatId, ProductCode


@dataclass(frozen=True)
class AddProductToCartCommand:
    chat_id: int
    product_code: str
    quantity: int
    business_date: date


class AddProductToCart:
    def __init__(
        self,
        sessions: TelegramSessionRepository,
        products: ProductRepository,
        is_holiday: Callable[[date], bool],
    ) -> None:
        self._sessions = sessions
        self._products = products
        self._availability = ProductAvailabilitySpecification(is_holiday=is_holiday)

    async def execute(self, command: AddProductToCartCommand) -> CartResult:
        if command.quantity <= 0:
            return CartResult(CartOperationStatus.INVALID_QUANTITY, tuple(), 0)

        product = await self._products.get_by_code(ProductCode(command.product_code))
        if product is None:
            return CartResult(CartOperationStatus.PRODUCT_NOT_FOUND, tuple(), 0)
        if not self._availability.is_satisfied_by(product, command.business_date):
            return CartResult(CartOperationStatus.PRODUCT_RESTRICTED, tuple(), 0)

        chat_id = ChatId(command.chat_id)
        session = await self._get_or_create_session(chat_id)
        item = CartItem(
            product_code=product.code,
            product_name=product.name,
            unit_price=MoneyCOP(product.price.amount),
            quantity=command.quantity,
        )
        session.add_cart_item(item)
        session.clear_selected_product()
        await self._sessions.save(session)

        return CartResult(
            status=CartOperationStatus.OK,
            items=tuple(session.cart),
            total_cop=session.cart_total.amount,
            added_item=item,
        )

    async def _get_or_create_session(self, chat_id: ChatId) -> TelegramSession:
        session = await self._sessions.get_by_chat_id(chat_id)
        if session is not None:
            return session
        return await self._sessions.add(TelegramSession(chat_id=chat_id))

