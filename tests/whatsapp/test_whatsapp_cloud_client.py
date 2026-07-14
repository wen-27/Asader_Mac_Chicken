from app.modules.whatsapp.infrastructure.whatsapp_cloud_client import (
    _confirmation_buttons_payload,
    _half_combo_buttons_payload,
    _soup_unavailable_buttons_payload,
)
from app.shared.domain.value_object import ChatId


def test_confirmation_summary_uses_reply_buttons() -> None:
    payload = _confirmation_buttons_payload(
        ChatId(573153327502),
        "Resumen\n\nResponde SI para confirmar o NO para cancelar.",
    )

    assert payload is not None
    assert payload["type"] == "interactive"
    buttons = payload["interactive"]["action"]["buttons"]  # type: ignore[index]
    assert buttons[0]["reply"]["id"] == "confirm_order_yes"
    assert buttons[0]["reply"]["title"] == "Sí"
    assert buttons[1]["reply"]["id"] == "confirm_order_no"
    assert buttons[1]["reply"]["title"] == "No"
    assert payload["interactive"]["body"]["text"] == "Resumen"  # type: ignore[index]


def test_inline_confirmation_text_uses_reply_buttons_without_instruction() -> None:
    payload = _confirmation_buttons_payload(
        ChatId(573153327502),
        "🧾 Resumen de tu pedido:\n\nTotal: $45000\n\n¿Deseas confirmar el pedido? Responde SI para confirmar o NO para cancelar.",
    )

    assert payload is not None
    body = payload["interactive"]["body"]["text"]  # type: ignore[index]
    buttons = payload["interactive"]["action"]["buttons"]  # type: ignore[index]
    assert "Responde SI" not in body
    assert "¿Deseas confirmar el pedido?" in body
    assert buttons[0]["reply"]["title"] == "Sí"
    assert buttons[1]["reply"]["title"] == "No"


def test_soup_unavailable_prompt_uses_continue_cancel_buttons() -> None:
    payload = _soup_unavailable_buttons_payload(
        ChatId(573153327502),
        "En este momento no contamos con sopas debido a que ya se agotaron.\n\n"
        "¿Quieres seguir con tu pedido o prefieres cancelarlo?",
    )

    assert payload is not None
    buttons = payload["interactive"]["action"]["buttons"]  # type: ignore[index]
    assert buttons[0]["reply"]["id"] == "soup_continue"
    assert buttons[0]["reply"]["title"] == "Seguir"
    assert buttons[1]["reply"]["id"] == "soup_cancel"
    assert buttons[1]["reply"]["title"] == "Cancelar"


def test_half_combo_prompt_uses_order_menu_buttons() -> None:
    payload = _half_combo_buttons_payload(
        ChatId(573153327502),
        "Si, puedes pedir medio asado y medio broaster.\n\n"
        "¿Deseas pedirlos ahora o prefieres seguir viendo el menu?",
    )

    assert payload is not None
    buttons = payload["interactive"]["action"]["buttons"]  # type: ignore[index]
    assert buttons[0]["reply"]["id"] == "half_combo_order"
    assert buttons[0]["reply"]["title"] == "Pedir"
    assert buttons[1]["reply"]["id"] == "half_combo_menu"
    assert buttons[1]["reply"]["title"] == "Menú"
