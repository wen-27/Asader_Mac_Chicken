from app.modules.whatsapp.api.routes import _is_order_timing_query


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
