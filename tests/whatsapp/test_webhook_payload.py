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


def test_whatsapp_payload_maps_soup_continue_button_reply_to_text() -> None:
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
                                        "id": "wamid.SOUP",
                                        "type": "interactive",
                                        "interactive": {
                                            "type": "button_reply",
                                            "button_reply": {
                                                "id": "soup_continue",
                                                "title": "Seguir",
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
    assert messages[0].text == "seguir"


def test_whatsapp_payload_maps_half_combo_order_button_reply_to_text() -> None:
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
                                        "id": "wamid.COMBO",
                                        "type": "interactive",
                                        "interactive": {
                                            "type": "button_reply",
                                            "button_reply": {
                                                "id": "half_combo_order",
                                                "title": "Ordenar",
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
    assert messages[0].text == "ordenar"


def test_whatsapp_payload_maps_admin_preparing_button_reply() -> None:
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
                                        "id": "wamid.ADMIN_BUTTON",
                                        "type": "interactive",
                                        "interactive": {
                                            "type": "button_reply",
                                            "button_reply": {
                                                "id": "admin_preparing_yes",
                                                "title": "Si",
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
    assert messages[0].text == "Si"
    assert messages[0].button_reply_id == "admin_preparing_yes"


def test_whatsapp_payload_maps_image_message_to_media() -> None:
    payload = WhatsAppWebhookPayload.model_validate(
        {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "contacts": [
                                    {
                                        "wa_id": "573153327502",
                                        "profile": {"name": "Wendy"},
                                    }
                                ],
                                "messages": [
                                    {
                                        "from": "573153327502",
                                        "id": "wamid.IMAGE",
                                        "timestamp": "1783710000",
                                        "type": "image",
                                        "image": {
                                            "id": "1234567890",
                                            "mime_type": "image/jpeg",
                                            "sha256": "abc123",
                                            "caption": "pago nequi",
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

    text_messages = payload.iter_text_messages()
    media_messages = payload.iter_media_messages()

    assert text_messages == []
    assert len(media_messages) == 1
    assert media_messages[0].chat_id == 573153327502
    assert media_messages[0].media_id == "1234567890"
    assert media_messages[0].media_type == "image"
    assert media_messages[0].mime_type == "image/jpeg"
    assert media_messages[0].caption == "pago nequi"
    assert media_messages[0].first_name == "Wendy"


def test_whatsapp_payload_maps_audio_message_to_media() -> None:
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
                                        "id": "wamid.AUDIO",
                                        "timestamp": "1783710000",
                                        "type": "audio",
                                        "audio": {
                                            "id": "audio123",
                                            "mime_type": "audio/ogg",
                                            "sha256": "hash-audio",
                                            "voice": True,
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

    text_messages = payload.iter_text_messages()
    media_messages = payload.iter_media_messages()

    assert text_messages == []
    assert len(media_messages) == 1
    assert media_messages[0].chat_id == 573153327502
    assert media_messages[0].media_id == "audio123"
    assert media_messages[0].media_type == "audio"
    assert media_messages[0].mime_type == "audio/ogg"
    assert media_messages[0].sha256 == "hash-audio"
    assert media_messages[0].caption is None


def test_whatsapp_payload_maps_call_event() -> None:
    payload = WhatsAppWebhookPayload.model_validate(
        {
            "entry": [
                {
                    "changes": [
                        {
                            "field": "calls",
                            "value": {
                                "contacts": [
                                    {
                                        "wa_id": "573153327502",
                                        "profile": {"name": "Wendy"},
                                    }
                                ],
                                "calls": [
                                    {
                                        "from": "573153327502",
                                        "id": "wacid.CALL",
                                        "timestamp": "1783710000",
                                        "status": "missed",
                                    }
                                ],
                            },
                        }
                    ]
                }
            ]
        }
    )

    call_events = payload.iter_call_events()

    assert len(call_events) == 1
    assert call_events[0].chat_id == 573153327502
    assert call_events[0].external_message_id == "wacid.CALL"
    assert call_events[0].phone == "573153327502"
    assert call_events[0].sent_at_epoch == 1783710000
    assert call_events[0].status == "missed"
    assert call_events[0].first_name == "Wendy"
