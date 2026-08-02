from __future__ import annotations

import pytest

from app.modules.whatsapp.application.message_interpreter import (
    WhatsAppContextMessage,
    WhatsAppGeminiMessageInterpreter,
    interpret_whatsapp_message_locally,
)


class FakeLLM:
    def __init__(self, response: str) -> None:
        self.response = response
        self.prompt = ""

    async def complete(self, prompt: str) -> str:
        self.prompt = prompt
        return self.response


@pytest.mark.asyncio
async def test_whatsapp_interpreter_rewrites_messy_order() -> None:
    llm = FakeLLM(
        '{"action":"rewrite","confidence":0.92,'
        '"rewrittenMessage":"quiero 2 pollos asados enteros y 1 pollo broaster entero",'
        '"clarificationQuestion":"","notes":["ortografia_corregida"]}'
    )
    interpreter = WhatsAppGeminiMessageInterpreter(llm)

    result = await interpreter.interpret(
        current_message="quiero dos asador y un broster",
        recent_messages=[],
    )

    assert result.conversation_text == "quiero 2 pollos asados enteros y 1 pollo broaster entero"
    assert result.clarification_text is None
    assert "ortografia_corregida" in result.notes


@pytest.mark.asyncio
async def test_whatsapp_interpreter_asks_clarification_on_low_confidence() -> None:
    llm = FakeLLM(
        '{"action":"clarify","confidence":0.45,'
        '"rewrittenMessage":"",'
        '"clarificationQuestion":"Con gusto. Para no añadir una bebida equivocada, ¿deseas Coca-Cola, Kola o Colombiana?",'
        '"notes":["bebida_ambigua"]}'
    )
    interpreter = WhatsAppGeminiMessageInterpreter(llm)

    result = await interpreter.interpret(
        current_message="una gasiosa roja",
        recent_messages=[],
    )

    assert result.conversation_text is None
    assert result.clarification_text
    assert "bebida equivocada" in result.clarification_text


@pytest.mark.asyncio
async def test_whatsapp_interpreter_includes_recent_numbered_context() -> None:
    llm = FakeLLM(
        '{"action":"rewrite","confidence":0.91,'
        '"rewrittenMessage":"una Coca-Cola personal 400 ml",'
        '"clarificationQuestion":"","notes":["numero_resuelto_por_contexto"]}'
    )
    interpreter = WhatsAppGeminiMessageInterpreter(llm)

    result = await interpreter.interpret(
        current_message="1",
        recent_messages=[
            WhatsAppContextMessage(
                direction="outbound",
                text="1. Coca-Cola personal 400 ml - $3500\n2. Coca-Cola 1.5 L - $8500",
            )
        ],
    )

    assert result.conversation_text == "una Coca-Cola personal 400 ml"
    assert "1. Coca-Cola personal 400 ml" in llm.prompt


def test_local_whatsapp_interpreter_rewrites_common_typos() -> None:
    result = interpret_whatsapp_message_locally(
        current_message="quiero dos asador y un broste",
        recent_messages=[],
    )

    assert result.conversation_text == "quiero dos asado y un broster"
    assert "local_typo_rewrite" in result.notes


def test_local_whatsapp_interpreter_rewrites_ambiguous_half_asado_typo() -> None:
    result = interpret_whatsapp_message_locally(
        current_message="medio polo asada con agi y tatara",
        recent_messages=[],
    )

    assert result.conversation_text == "medio asado con aji y tartara"


def test_local_whatsapp_interpreter_strips_greeting_when_message_has_order() -> None:
    result = interpret_whatsapp_message_locally(
        current_message="ola veci m regala 1 pllo azdo y 2 cocacila perzonales",
        recent_messages=[],
    )

    assert result.conversation_text == "1 pollo asado y 2 coca cola personales"


def test_local_whatsapp_interpreter_strips_embedded_questions_from_order() -> None:
    result = interpret_whatsapp_message_locally(
        current_message=(
            "muy buenas tardes me colaboras con una lasana tres cuartos de asado "
            "2 pechugas 1 pierna tiene sopa hay lasañas"
        ),
        recent_messages=[],
    )

    assert result.conversation_text == "una lasaña tres cuartos de asado 2 pechugas 1 pierna"


def test_local_whatsapp_interpreter_resolves_numbered_context() -> None:
    result = interpret_whatsapp_message_locally(
        current_message="1",
        recent_messages=[
            WhatsAppContextMessage(
                direction="outbound",
                text="1. Coca-Cola personal 400 ml - $3500\n2. Coca-Cola 1.5 L - $8500",
            )
        ],
    )

    assert result.conversation_text == "Coca-Cola personal 400 ml"


def test_local_whatsapp_interpreter_clarifies_ambiguous_red_soda() -> None:
    result = interpret_whatsapp_message_locally(
        current_message="una gasiosa roja",
        recent_messages=[],
    )

    assert result.clarification_text
    assert "Coca-Cola" in result.clarification_text
