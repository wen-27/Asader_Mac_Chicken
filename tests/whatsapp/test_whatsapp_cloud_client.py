from app.modules.whatsapp.infrastructure.whatsapp_cloud_client import _confirmation_buttons_payload
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
