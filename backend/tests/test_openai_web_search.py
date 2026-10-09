import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.modules.sources.openai_web_search import search_openai_web


class OpenAIWebSearchTests(unittest.TestCase):
    def test_required_search_returns_provider_sources_as_candidates(self) -> None:
        source = {"url": "https://example.org/record", "title": "Official record"}
        citation = {
            "type": "url_citation",
            "url_citation": {"url": source["url"], "title": source["title"]},
        }
        response = SimpleNamespace(
            id="resp_test",
            output=[
                SimpleNamespace(
                    type="web_search_call",
                    action={"type": "search", "sources": [source]},
                ),
                {
                    "type": "message",
                    "content": [{"type": "output_text", "annotations": [citation]}],
                },
            ],
        )
        calls: list[dict[str, object]] = []

        class FakeClient:
            def __init__(self, *, api_key: str, timeout: float) -> None:
                self.responses = SimpleNamespace(create=self.create)

            def create(self, **kwargs):
                calls.append(kwargs)
                return response

        with patch.dict(sys.modules, {"openai": SimpleNamespace(OpenAI=FakeClient)}):
            result = search_openai_web(
                api_key="test-key",
                model="gpt-test",
                query="Kenya independence primary records",
            )

        self.assertEqual(result.request_id, "resp_test")
        self.assertEqual(len(result.results), 1)
        self.assertEqual(result.results[0]["url"], source["url"])
        self.assertEqual(result.results[0]["title"], source["title"])
        self.assertEqual(result.citations, [source])
        self.assertEqual(calls[0]["tool_choice"], "required")
        self.assertEqual(calls[0]["tools"][0]["type"], "web_search")
        self.assertIn("web_search_call.action.sources", calls[0]["include"])


if __name__ == "__main__":
    unittest.main()
