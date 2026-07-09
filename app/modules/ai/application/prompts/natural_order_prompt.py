"""Gemini prompt template for fallback natural-order parsing when deterministic rules are not enough."""

from __future__ import annotations

from app.modules.ai.application.schemas import NaturalLanguageOrderParse


def build_natural_order_prompt(message: str, catalog_context: str) -> str:
    schema = NaturalLanguageOrderParse.model_json_schema()
    return "\n".join(
        [
            "Eres un parser de pedidos para ASADERO MC CHICKEN EXPRESS.",
            "Devuelve SOLO JSON valido, sin markdown.",
            "Reglas:",
            "- Usa SOLO codigos existentes del catalogo proporcionado.",
            "- Si no hay cantidad, usa quantity 1.",
            "- quantity representa unidades del producto, no fracciones del pollo.",
            "- Las fracciones del pollo cambian el codigo del producto, no la cantidad.",
            "- No inventes productos, codigos, precios ni domicilios.",
            "- Si el mensaje pide finalizar, usa wantsCheckout=true.",
            "- Si no estas seguro, baja confidence por debajo de 0.70.",
            "- Si el cliente pide un pollo 'con' algo que no viene incluido y ese algo existe en catalogo, agregalo como item adicional separado.",
            "- Ignora saludos y cortesias como 'hola', 'buenos dias', 'por favor', 'me regala', 'me puede regalar'.",
            "- Extrae TODOS los productos del mismo mensaje. No te quedes solo con el primero.",
            "",
            "Equivalencias obligatorias:",
            "- 'un pollo asado', 'uno asado', 'pollo asado entero' => ASADO_ENTERO quantity 1.",
            "- 'medio pollo', 'medio asado', '1/2 asado' => ASADO_MEDIO quantity 1.",
            "- 'tres cuartos', '3/4 asado' => ASADO_34 quantity 1.",
            "- 'cuarto pollo', '1/4 asado' => ASADO_CUARTO quantity 1.",
            "- 'un broaster', 'broaster entero' => BROASTER_ENTERO quantity 1.",
            "- 'medio broaster', '1/2 broaster', 'medio brosted' => BROASTER_MEDIO quantity 1.",
            "- '3/4 broaster', 'tres cuartos broaster' => BROASTER_34 quantity 1.",
            "- 'cuarto broaster', '1/4 broaster' => BROASTER_CUARTO quantity 1.",
            "- 'coca-cola 1.5', 'coca 1.5' => COCA_COLA_15 quantity 1.",
            "- 'postobon 2.5' => POSTOBON_25 quantity 1.",
            "- 'quatro 1.5', 'cuatro 1.5' => QUATRO_15 quantity 1.",
            "- 'gaseosa litro y medio' sin marca es ambiguo; no inventes producto.",
            "- 'coca 3 litros', 'gaseosa tres litros' => TRES_LITROS quantity 1.",
            "- 'dos papas francesas' => PAPA_FRANCESA quantity 2.",
            "- 'papas fritas', 'adicional de papas fritas', 'porcion de francesa' => PAPA_FRANCESA quantity 1.",
            "- 'una sopa' => SOPA_ADICIONAL quantity 1.",
            "",
            "Ejemplos:",
            'Mensaje: "Necesito un pollo asado con una Cocacola 1.5"',
            'JSON: {"intent":"order_items","items":[{"code":"ASADO_ENTERO","quantity":1},{"code":"COCA_COLA_15","quantity":1}],"customer":{"name":"","phone":"","address":"","neighborhood":"","paymentMethod":""},"wantsCheckout":false,"confidence":0.95,"notes":[]}',
            'Mensaje: "Quiero un pollo asado con adicional de papas fritas y una Cocacola 1.5"',
            'JSON: {"intent":"order_items","items":[{"code":"ASADO_ENTERO","quantity":1},{"code":"PAPA_FRANCESA","quantity":1},{"code":"COCA_COLA_15","quantity":1}],"customer":{"name":"","phone":"","address":"","neighborhood":"","paymentMethod":""},"wantsCheckout":false,"confidence":0.95,"notes":[]}',
            'Mensaje: "hola buenos dias me regala medio broaster una sopa y una gatorade"',
            'JSON: {"intent":"order_items","items":[{"code":"BROASTER_MEDIO","quantity":1},{"code":"SOPA_ADICIONAL","quantity":1},{"code":"GATORADE","quantity":1}],"customer":{"name":"","phone":"","address":"","neighborhood":"","paymentMethod":""},"wantsCheckout":false,"confidence":0.95,"notes":[]}',
            'Mensaje: "agrega dos medios pollos y tres papas francesas"',
            'JSON: {"intent":"order_items","items":[{"code":"ASADO_MEDIO","quantity":2},{"code":"PAPA_FRANCESA","quantity":3}],"customer":{"name":"","phone":"","address":"","neighborhood":"","paymentMethod":""},"wantsCheckout":false,"confidence":0.95,"notes":[]}',
            "",
            "Catalogo permitido:",
            catalog_context,
            "",
            "Mensaje:",
            message,
            "",
            "Schema esperado:",
            str(schema),
        ]
    )
