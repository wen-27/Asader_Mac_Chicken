"""Customer-data parser for free-form Telegram text. Keep it tolerant of human line-by-line messages."""

from __future__ import annotations

from app.modules.customers.application.customer_data import CustomerData, parse_payment_method
from app.shared.utils.text_normalizer import normalize_text


class ExtractCustomerData:
    def execute(self, raw_text: str) -> CustomerData:
        values: dict[str, str] = {}
        for raw_line in raw_text.splitlines():
            if ":" not in raw_line:
                continue
            key, value = raw_line.split(":", 1)
            values[normalize_text(key)] = value.strip()

        observations = (
            values.get("observaciones")
            or values.get("observacion")
            or values.get("notas")
            or "Ninguna"
        )
        return CustomerData(
            name=values.get("nombre completo") or values.get("nombre") or values.get("cliente"),
            phone=values.get("telefono") or values.get("celular") or values.get("número"),
            address=values.get("direccion") or values.get("dir"),
            neighborhood=values.get("barrio") or values.get("sector"),
            payment_method=parse_payment_method(
                values.get("metodo de pago") or values.get("pago") or values.get("medio de pago")
            ),
            observations=observations,
        )

