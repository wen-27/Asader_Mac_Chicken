"""WhatsApp-only message interpretation before the deterministic conversation flow."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import re

from pydantic import BaseModel, Field, ValidationError

from app.modules.ai.application.ports import LLMClient


@dataclass(frozen=True)
class WhatsAppContextMessage:
    direction: str
    text: str


@dataclass(frozen=True)
class WhatsAppMessageInterpretation:
    conversation_text: str | None = None
    clarification_text: str | None = None
    confidence: float = 0.0
    notes: tuple[str, ...] = field(default_factory=tuple)


class _InterpreterPayload(BaseModel):
    action: str = Field(default="use_original")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    rewrittenMessage: str = ""
    clarificationQuestion: str = ""
    notes: list[str] = Field(default_factory=list)


class WhatsAppGeminiMessageInterpreter:
    MIN_CONFIDENCE = 0.70

    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm

    async def interpret(
        self,
        *,
        current_message: str,
        recent_messages: list[WhatsAppContextMessage],
    ) -> WhatsAppMessageInterpretation:
        raw_response = await self._llm.complete(
            _build_whatsapp_interpreter_prompt(current_message, recent_messages)
        )
        payload = _parse_payload(raw_response)
        notes = tuple(payload.notes)

        action = payload.action.strip().lower()
        rewritten = payload.rewrittenMessage.strip()
        clarification = payload.clarificationQuestion.strip()

        if action == "clarify" or payload.confidence < self.MIN_CONFIDENCE:
            if clarification:
                return WhatsAppMessageInterpretation(
                    clarification_text=clarification,
                    confidence=payload.confidence,
                    notes=notes,
                )
            return WhatsAppMessageInterpretation(confidence=payload.confidence, notes=notes)

        if action == "rewrite" and rewritten:
            return WhatsAppMessageInterpretation(
                conversation_text=rewritten,
                confidence=payload.confidence,
                notes=notes,
            )

        return WhatsAppMessageInterpretation(confidence=payload.confidence, notes=notes)


def interpret_whatsapp_message_locally(
    *,
    current_message: str,
    recent_messages: list[WhatsAppContextMessage],
) -> WhatsAppMessageInterpretation:
    advisor_handoff = _rewrite_fragmented_advisor_handoff(current_message, recent_messages)
    if advisor_handoff:
        return WhatsAppMessageInterpretation(
            conversation_text=advisor_handoff,
            confidence=0.9,
            notes=("local_fragmented_advisor_handoff",),
        )

    numbered_option = _rewrite_numbered_option(current_message, recent_messages)
    if numbered_option:
        return WhatsAppMessageInterpretation(
            conversation_text=numbered_option,
            confidence=0.85,
            notes=("local_numbered_context",),
        )

    normalized = _local_rewrite_text(current_message)
    if normalized != current_message:
        return WhatsAppMessageInterpretation(
            conversation_text=normalized,
            confidence=0.75,
            notes=("local_typo_rewrite",),
        )

    ambiguous_drink = _local_ambiguous_drink_question(current_message)
    if ambiguous_drink:
        return WhatsAppMessageInterpretation(
            clarification_text=ambiguous_drink,
            confidence=0.45,
            notes=("local_ambiguous_drink",),
        )

    return WhatsAppMessageInterpretation()


def _parse_payload(raw_response: str) -> _InterpreterPayload:
    text = raw_response.strip()
    if text.startswith("```"):
        text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return _InterpreterPayload(action="use_original", confidence=0.0, notes=["json_parse_error"])
    try:
        return _InterpreterPayload.model_validate(data)
    except ValidationError:
        return _InterpreterPayload(action="use_original", confidence=0.0, notes=["schema_error"])


def _rewrite_numbered_option(
    current_message: str,
    recent_messages: list[WhatsAppContextMessage],
) -> str | None:
    raw = current_message.strip()
    if not re.fullmatch(r"\d{1,2}", raw):
        return None
    selected = int(raw)
    for message in reversed(recent_messages):
        if message.direction != "outbound":
            continue
        options = _numbered_options(message.text)
        if selected in options:
            return options[selected]
    return None


def _rewrite_fragmented_advisor_handoff(
    current_message: str,
    recent_messages: list[WhatsAppContextMessage],
) -> str | None:
    current = _compact_lower(current_message)
    if current not in {"fabio", "fabio perez", "fabio pérez", "con fabio", "con fabio perez", "con fabio pérez"}:
        return None
    recent_inbound = [
        _compact_lower(message.text)
        for message in recent_messages[-5:]
        if message.direction == "inbound" and message.text.strip()
    ]
    phrase = " ".join(recent_inbound + [current])
    if "hablar" in phrase and "fabio" in phrase:
        return "puedo hablar con Fabio"
    return None


def _compact_lower(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower()).strip(" ¿?.,!¡")


def _numbered_options(text: str) -> dict[int, str]:
    options: dict[int, str] = {}
    for line in text.splitlines():
        match = re.match(r"\s*(\d{1,2})\.\s+(.+?)(?:\s+-\s+\$?\d[\d.]*.*)?$", line.strip())
        if not match:
            continue
        value = match.group(2).strip()
        if "volver" in value.lower():
            continue
        options[int(match.group(1))] = value
    return options


def _local_rewrite_text(text: str) -> str:
    rewritten = text
    replacements = (
        (r"\bm\s+regala\b", "me regala"),
        (r"\bpllo\b", "pollo"),
        (r"\bpolo\b", "pollo"),
        (r"\bpollio\b", "pollo"),
        (r"\basador\b", "asado"),
        (r"\bazado\b", "asado"),
        (r"\bazdo\b", "asado"),
        (r"\basda\b", "asado"),
        (r"\basda[oa]\b", "asado"),
        (r"\bbrostee?\b", "broster"),
        (r"\bbrosted\b", "broster"),
        (r"\bbroas?te+r?\b", "broster"),
        (r"\bcocacila\b", "cocacola"),
        (r"\bcocacola\b", "coca cola"),
        (r"\bperzonales\b", "personales"),
        (r"\bpersnal\b", "personal"),
        (r"\bperzonal\b", "personal"),
        (r"\bjit\b", "hit"),
        (r"\bagi\b", "aji"),
        (r"\btatara\b", "tartara"),
        (r"\badcional\b", "adicional"),
        (r"\bcozida\b", "cocida"),
        (r"\befetivo\b", "efectivo"),
        (r"\bnequi\b", "nequi"),
        (r"\bservidion\b", "servicio a domicilio"),
        (r"\btatdes\b", "tardes"),
        (r"\bola\b", "hola"),
        (r"\blasana\b", "lasaña"),
        (r"\blasañas\b", "lasaña"),
    )
    for pattern, replacement in replacements:
        rewritten = re.sub(pattern, replacement, rewritten, flags=re.IGNORECASE)
    rewritten = re.sub(
        r"\bmedio\s+pollo\s+asad[oa]\b",
        "medio asado",
        rewritten,
        flags=re.IGNORECASE,
    )
    rewritten = _strip_leading_greeting_for_order(rewritten)
    rewritten = _strip_embedded_questions_for_order(rewritten)
    return rewritten


def _strip_leading_greeting_for_order(text: str) -> str:
    lowered = text.lower()
    if not any(term in lowered for term in ("pollo", "asado", "broster", "broaster", "coca", "gaseosa", "jugo", "lasaña")):
        return text
    return re.sub(
        r"^\s*(hola|buenas|buenos dias|buenas tardes|muy buenas tardes|buen dia|ola)"
        r"(\s+(veci|vesi|porfa|por favor|me colaboras con|me colabora con|me regala|me regalas|me vende|me vendes))*\s+",
        "",
        text,
        flags=re.IGNORECASE,
    )


def _strip_embedded_questions_for_order(text: str) -> str:
    lowered = text.lower()
    if not any(term in lowered for term in ("pollo", "asado", "broster", "broaster", "lasaña")):
        return text
    cleaned = text
    for pattern in (
        r"\btiene\s+sopa\??",
        r"\bhay\s+sopa\??",
        r"\bhay\s+lasañ[ao]s?\??",
        r"\btiene\s+lasañ[ao]s?\??",
    ):
        cleaned = re.sub(pattern, " ", cleaned, flags=re.IGNORECASE)
    return re.sub(r"\s{2,}", " ", cleaned).strip()


def _local_ambiguous_drink_question(text: str) -> str | None:
    lowered = text.lower()
    if not any(term in lowered for term in ("gasiosa", "gaseosa", "bebida")):
        return None
    if "roja" not in lowered:
        return None
    return "Con gusto. Para no añadir una bebida equivocada, ¿deseas Coca-Cola, Kola o Colombiana?"


def _build_whatsapp_interpreter_prompt(
    current_message: str,
    recent_messages: list[WhatsAppContextMessage],
) -> str:
    context_lines = [
        f"{message.direction}: {message.text}"
        for message in recent_messages[-5:]
        if message.text.strip()
    ]
    context = "\n".join(context_lines) or "(sin contexto reciente)"
    schema = _InterpreterPayload.model_json_schema()
    return "\n".join(
        [
            "Eres un interprete interno para el WhatsApp de ASADERO MC CHICKEN EXPRESS.",
            "No eres el bot que responde al cliente. Tu trabajo es reescribir el mensaje del cliente",
            "a texto claro para que un flujo deterministico lo procese despues.",
            "Devuelve SOLO JSON valido, sin markdown.",
            "",
            "Acciones posibles:",
            "- rewrite: si entiendes el mensaje con confianza y puedes convertirlo a texto claro.",
            "- clarify: si hace falta preguntar para no agregar algo equivocado.",
            "- use_original: si el mensaje ya es claro o no conviene tocarlo.",
            "",
            "Reglas criticas:",
            "- No inventes productos, precios, domicilios ni datos del cliente.",
            "- No incluyas precios.",
            "- No respondas preguntas como asesor; solo reescribe o genera una pregunta corta de aclaracion.",
            "- Corrige ortografia fuerte: polo/pollo, asador/asado, broste/broster/broaster, cocacila/cocacola, agi/aji, tatara/tartara.",
            "- Si el cliente mezcla pedido y datos, ordena todo en lineas claras.",
            "- Mantén notas del cliente como notas: sin sopa, solo papa, solo yuca frita, solo tartara, con aji, recoger a las 12:30.",
            "- Si dice 'adicional', 'extra', 'aparte' o 'porcion', puede ser producto adicional.",
            "- Si NO dice adicional/extra/aparte/porcion, salsas, sopa incluida y cambios de acompañamiento son notas.",
            "- Mensajes de hora como 'a las 11:30', 'antes de las 12:30' o 'lo mas pronto' son notas, no nombres.",
            "- Si dice que recoge alguien, reescribe como pedido para recoger en local, con nombre si lo dio.",
            "- Si el mensaje actual es un numero, solo interpretalo si en el contexto reciente hay una lista numerada clara del bot.",
            "- Si el numero es respuesta a una lista, reescribelo como la opcion textual completa.",
            "- Si hay ambiguedad de bebida, parte, estilo asado/broaster o presentacion, usa clarify.",
            "- Si el cliente solo dice si/no/cancelar/menu/bebidas/adicionales/horario y no depende de una lista numerada, usa use_original.",
            "- Si el cliente escribe en mensajes partidos que quiere hablar con Fabio, reescribe a 'puedo hablar con Fabio'.",
            "- Si hay duda, confidence menor a 0.70 y action clarify.",
            "",
            "Ejemplos de rewrite:",
            'Cliente: "quiero dos asador y un broster"',
            'JSON: {"action":"rewrite","confidence":0.92,"rewrittenMessage":"quiero 2 pollos asados enteros y 1 pollo broaster entero","clarificationQuestion":"","notes":["ortografia_corregida"]}',
            'Cliente: "wendy 3022873946 el manantial efectivo"',
            'JSON: {"action":"rewrite","confidence":0.85,"rewrittenMessage":"nombre: wendy\\ntelefono: 3022873946\\nbarrio: el manantial\\nmetodo de pago: efectivo","clarificationQuestion":"","notes":[]}',
            'Cliente: "1", contexto bot con lista "1. Coca-Cola personal 400 ml - $3500"',
            'JSON: {"action":"rewrite","confidence":0.9,"rewrittenMessage":"una Coca-Cola personal 400 ml","clarificationQuestion":"","notes":["numero_resuelto_por_contexto"]}',
            'Cliente: "una gasiosa roja"',
            'JSON: {"action":"clarify","confidence":0.45,"rewrittenMessage":"","clarificationQuestion":"Con gusto. Para no añadir una bebida equivocada, ¿deseas Coca-Cola, Kola o Colombiana?","notes":["bebida_ambigua"]}',
            "",
            "Formato recomendado para datos mezclados:",
            "quiero 1/2 pollo broaster",
            "nombre: Wendy",
            "telefono: 3022873946",
            "direccion: cra28a#195-33",
            "barrio: el manantial",
            "metodo de pago: efectivo",
            "nota: solo tartara",
            "",
            "Contexto reciente:",
            context,
            "",
            "Mensaje actual del cliente:",
            current_message,
            "",
            "Schema esperado:",
            str(schema),
        ]
    )
