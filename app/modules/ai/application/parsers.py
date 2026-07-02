"""Application-layer code. It defines use cases, DTOs and ports between domain and infrastructure."""

from __future__ import annotations

import json

from app.modules.ai.application.ports import LLMClient
from app.modules.ai.application.prompts.natural_order_prompt import build_natural_order_prompt
from app.modules.ai.application.schemas import NaturalLanguageOrderParse


class LangChainNaturalLanguageOrderParser:
    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm

    async def parse(self, message: str, catalog_context: str) -> NaturalLanguageOrderParse:
        try:
            from langchain_core.prompts import PromptTemplate

            prompt_template = PromptTemplate.from_template("{prompt}")
            prompt = prompt_template.format(
                prompt=build_natural_order_prompt(message, catalog_context)
            )
        except Exception:
            prompt = build_natural_order_prompt(message, catalog_context)

        raw_response = await self._llm.complete(prompt)
        payload = _clean_json_response(raw_response)
        try:
            return NaturalLanguageOrderParse.model_validate_json(payload)
        except Exception:
            return NaturalLanguageOrderParse(
                intent="unknown",
                confidence=0.0,
                notes=["json_parse_error"],
            )


def _clean_json_response(raw_response: str) -> str:
    text = raw_response.strip()
    if text.startswith("```"):
        text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return text
    return json.dumps(parsed)

