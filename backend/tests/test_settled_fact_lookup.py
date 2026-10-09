import json
import unittest
from contextlib import contextmanager
from unittest.mock import patch

from app.modules.sources.settled_fact import lookup_settled_fact


class _Response:
    def __init__(self, value):
        self.payload = json.dumps(value).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self, _size=-1):
        return self.payload


class SettledFactLookupTests(unittest.TestCase):
    def test_queries_both_apis_and_keeps_wikidata_context_only(self) -> None:
        def fake_urlopen(request, timeout):
            self.assertGreater(timeout, 0)
            if "en.wikipedia.org" in request.full_url:
                return _Response({"query": {"pages": [{
                    "title": "Nairobi", "fullurl": "https://en.wikipedia.org/wiki/Nairobi",
                    "extract": "Nairobi is the capital city of Kenya.",
                }]}})
            return _Response({"search": [{
                "label": "Nairobi", "description": "capital and largest city of Kenya",
                "concepturi": "https://www.wikidata.org/entity/Q3870",
            }]})

        with patch("app.modules.sources.settled_fact.urlopen", side_effect=fake_urlopen):
            result = lookup_settled_fact("Nairobi is the capital of Kenya")

        self.assertEqual(len(result.excerpts), 2)
        self.assertEqual(result.excerpts[0].provider, "wikipedia_api")
        self.assertEqual(result.excerpts[0].stance, "CONTEXT")
        self.assertEqual(result.excerpts[1].provider, "wikidata_api")
        self.assertEqual(result.excerpts[1].stance, "CONTEXT")
        self.assertLess(result.elapsed_seconds, 5)

    def test_provider_failure_is_reported_without_fabricating_a_source(self) -> None:
        with patch("app.modules.sources.settled_fact.urlopen", side_effect=OSError("offline")):
            result = lookup_settled_fact("mango is a fruit")
        self.assertEqual(result.excerpts, [])
        self.assertTrue(any("Wikipedia" in message for message in result.unavailable))
        self.assertTrue(any("Wikidata" in message for message in result.unavailable))


if __name__ == "__main__":
    unittest.main()
