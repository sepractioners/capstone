"""Fast tests for local-LLM timeout and retry behavior (via agent_llm.client)."""
from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from agent_llm import client as llm_client
from extraction_agent import extraction_node
from extraction_agent.schema import PageExtraction


def _resp(parsed):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(parsed=parsed))])


class ExtractionNodeResilienceTest(unittest.IsolatedAsyncioTestCase):
    async def test_retries_empty_structured_response(self) -> None:
        complete = PageExtraction(page_number=1, title="Services Agreement")
        calls = AsyncMock(side_effect=[_resp(None), _resp(complete)])
        with patch.object(extraction_node, "LLM_MAX_ATTEMPTS", 2), patch.object(
            extraction_node, "LLM_RETRY_BACKOFF_SECONDS", 0
        ), patch.object(llm_client, "acompletion", new=calls):
            result = await extraction_node.extract_page(1, "A" * 300)

        self.assertEqual(result.title, "Services Agreement")
        self.assertEqual(calls.await_count, 2)

    async def test_retries_provider_error_then_returns_result(self) -> None:
        complete = PageExtraction(page_number=1, title="Services Agreement")
        calls = AsyncMock(side_effect=[asyncio.TimeoutError(), _resp(complete)])
        with patch.object(extraction_node, "LLM_MAX_ATTEMPTS", 2), patch.object(
            extraction_node, "LLM_RETRY_BACKOFF_SECONDS", 0
        ), patch.object(llm_client, "acompletion", new=calls):
            result = await extraction_node.extract_page(1, "A" * 300)

        self.assertEqual(result.title, "Services Agreement")
        self.assertEqual(calls.await_count, 2)


if __name__ == "__main__":
    unittest.main()
