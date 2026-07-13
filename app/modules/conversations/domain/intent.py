"""Conversation orchestration code. It should coordinate state transitions and delegate business work to use cases/services."""

from __future__ import annotations

from enum import Enum


class ConversationIntent(str, Enum):
    MOSTRAR_MENU = "mostrar_menu"
    VER_MENU = "ver_menu"
    MENU_BROASTER = "menu_broaster"
    MENU_ASADO = "menu_asado"
    MENU_BEBIDAS = "menu_bebidas"
    MENU_ADICIONALES = "menu_adicionales"
    MENU_ESPECIALES = "menu_especiales"
    PEDIR_CANTIDAD = "pedir_cantidad"
    AGREGAR_PRODUCTO = "agregar_producto"
    MOSTRAR_CARRITO = "mostrar_carrito"
    VACIAR_CARRITO = "vaciar_carrito"
    ELIMINAR_PRODUCTO = "eliminar_producto"
    RESUMEN_CHECKOUT = "resumen_checkout"
    PEDIR_DATOS_CLIENTE = "pedir_datos_cliente"
    PROCESAR_DATOS_CLIENTE = "procesar_datos_cliente"
    CONFIRMAR_PEDIDO = "confirmar_pedido"
    CANCELAR = "cancelar"
    PRODUCTO_RESTRINGIDO = "producto_restringido"
    PRODUCTO_INEXISTENTE = "producto_inexistente"
    HORARIOS = "horarios"
    FUERA_HORARIO = "fuera_horario"
    INICIAR_DOMICILIO = "iniciar_domicilio"
    LENGUAJE_NATURAL = "lenguaje_natural"
    GENERAR_FACTURA = "generar_factura"
    VOLVER = "volver"
    RESPONDER_CONSULTA = "responder_consulta"
