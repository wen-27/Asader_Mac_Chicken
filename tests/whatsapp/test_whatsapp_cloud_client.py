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
    assert buttons[1]["reply"]["id"] == "confirm_order_no"
