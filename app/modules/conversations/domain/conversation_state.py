"""Conversation orchestration code. It should coordinate state transitions and delegate business work to use cases/services."""

from __future__ import annotations

from enum import Enum


class ConversationState(str, Enum):
    MAIN_MENU = "MAIN_MENU"
    PRODUCT_CATEGORY = "PRODUCT_CATEGORY"
    SELECT_ASADO = "SELECT_ASADO"
    SELECT_BROASTER = "SELECT_BROASTER"
    SELECT_BEBIDA = "SELECT_BEBIDA"
    SELECT_ADICIONAL = "SELECT_ADICIONAL"
    SELECT_ESPECIAL = "SELECT_ESPECIAL"
    ASK_CHICKEN_PART = "ASK_CHICKEN_PART"
    ASK_PRODUCT_VARIANT = "ASK_PRODUCT_VARIANT"
    ASK_SIDE_EXTRA = "ASK_SIDE_EXTRA"
    ASK_QUANTITY = "ASK_QUANTITY"
    POST_ADD = "POST_ADD"
    CHECKOUT_CONFIRM = "CHECKOUT_CONFIRM"
    ASK_CUSTOMER_DATA = "ASK_CUSTOMER_DATA"
    CHECKOUT_REVIEW = "CHECKOUT_REVIEW"
    NATURAL_ORDER = "NATURAL_ORDER"
    ASK_NAME = "pedir_nombre"
    ASK_PHONE = "pedir_telefono"
    ASK_ADDRESS = "pedir_direccion"
    ASK_NEIGHBORHOOD = "pedir_barrio"
    ASK_OBSERVATIONS = "pedir_observaciones"
    ASK_PAYMENT = "pedir_pago"
    SHOW_CONFIRMATION = "mostrar_confirmacion"
