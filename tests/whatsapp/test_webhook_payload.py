from app.modules.whatsapp.api.schemas import WhatsAppWebhookPayload


def test_whatsapp_payload_accepts_contact_without_profile() -> None:
    payload = WhatsAppWebhookPayload.model_validate(
        {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "contacts": [{"wa_id": "573153327502"}],
                                "messages": [
                                    {
                                        "from": "573153327502",
                                        "id": "wamid.TEST",
                                        "type": "text",
                                        "text": {"body": "hola"},
                                    }
                                ],
                            }
                        }
                    ]
                }
            ]
        }
    )

    messages = payload.iter_text_messages()

    assert len(messages) == 1
    assert messages[0].first_name is None
    assert messages[0].text == "hola"


def test_whatsapp_payload_maps_confirmation_button_reply_to_text() -> None:
    payload = WhatsAppWebhookPayload.model_validate(
        {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "messages": [
                                    {
                                        "from": "573153327502",
                                        "id": "wamid.BUTTON",
                                        "type": "interactive",
                                        "interactive": {
                                            "type": "button_reply",
                                            "button_reply": {
                                                "id": "confirm_order_yes",
                                                "title": "Si, confirmar",
                                            },
                                        },
                                    }
                                ],
                            }
                        }
                    ]
                }
            ]
        }
    )

    messages = payload.iter_text_messages()

    assert len(messages) == 1
    assert messages[0].text == "si"
