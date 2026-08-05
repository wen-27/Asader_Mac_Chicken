from app.modules.whatsapp.api.routes import (
    _is_order_timing_query,
    _should_answer_order_timing_query_in_webhook,
)


def test_real_customer_order_status_phrases_are_timing_queries() -> None:
    examples = [
        "Mi pedido llegó ?",
        "Si llevaron el domicilio ?",
        "Lo pedí hace una hora exactamente",
        "Una hora y 3 minutos y no lo han enviado o ya se envió ?",
        "Es que estamos a 4 cuadras y llevo una hora esperando que salga",
    ]

    for text in examples:
        assert _is_order_timing_query(text)
        assert _should_answer_order_timing_query_in_webhook(text)


def test_direct_eta_questions_go_through_conversation_graph() -> None:
    examples = [
        "Cuánto se demora?",
        "Cuanto demora",
        "Cuando llega?",
        "Tiempo de espera",
    ]

    for text in examples:
        assert _is_order_timing_query(text)
        assert not _should_answer_order_timing_query_in_webhook(text)
