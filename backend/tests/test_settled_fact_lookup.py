import json
import unittest
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


def test_best_matching_passage_finds_the_fact_beyond_the_intro():
    from app.modules.sources.settled_fact import best_matching_passage

    article = (
        "Kenya is a country in East Africa. Its capital is Nairobi. "
        "It has many national parks. Kenya gained independence on 12 December 1963. "
        "Jomo Kenyatta led the new government."
    )
    passage = best_matching_passage("Kenya gained independence in 1963.", article)
    assert "gained independence on 12 December 1963" in passage
    assert passage in article
    assert best_matching_passage("Unrelated words here.", article) is None


def test_named_phrase_finds_what_the_claim_is_about():
    from app.modules.sources.settled_fact import named_phrase

    assert named_phrase("Kenya won the 2022 FIFA World Cup.") == "2022 FIFA World Cup"
    assert named_phrase("William Ruto became President of Kenya in 2022.") == "William Ruto"
    assert named_phrase("The 2019 Kenya census counted 47.6 million people.") == "2019 Kenya"
    assert named_phrase("Nairobi is the capital of Kenya.") is None


def test_named_article_goes_first_only_when_its_title_matches_the_phrase():
    from unittest.mock import patch

    from app.modules.sources import settled_fact

    def page(title, index, extract):
        url = f"https://en.wikipedia.org/wiki/{title}"
        return {"title": title, "index": index, "fullurl": url, "extract": extract}

    def search(query, *, limit, deadline):
        if query == "2022 FIFA World Cup":
            return [page("2022 FIFA World Cup", 1, "The 2022 FIFA World Cup was held in Qatar.")]
        if query == "2019 Kenya":
            return [page("Kenya Barris", 1, "Kenya Barris is a television writer.")]
        return [page("FIFA U-17 Women's World Cup", 1, "A youth tournament.")]

    with (
        patch.object(settled_fact, "_wikipedia_search", side_effect=search),
        patch.object(settled_fact, "_full_extract", return_value=None),
        patch.object(settled_fact.time, "monotonic", return_value=0.0),
    ):
        won = settled_fact.lookup_settled_fact("Kenya won the 2022 FIFA World Cup.")
        census = settled_fact.lookup_settled_fact("The 2019 Kenya census counted 47.6 million.")
    assert won.excerpts[0].title == "2022 FIFA World Cup"
    assert census.excerpts[0].title == "FIFA U-17 Women's World Cup"
    assert all(item.title != "Kenya Barris" for item in census.excerpts)


def test_passage_choice_prefers_rare_claim_words_over_the_article_subject():
    from app.modules.sources.settled_fact import best_matching_passage

    article = (
        "The census was run by the bureau. The census used tablets. The census took a week. "
        "The census had staff. The census was costly. Kenya's population was 47.6 million "
        "during the 2019 census."
    )
    passage = best_matching_passage(
        "The 2019 Kenya census counted about 47.6 million people.", article, sentences=1
    )
    assert passage == "Kenya's population was 47.6 million during the 2019 census."
