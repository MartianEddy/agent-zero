import json
import unittest
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.domain.investigation import InputType
from app.modules.investigations.models import (
    Claim,
    ClaimEvidence,
    Evidence,
    InvestigationUsage,
    Source,
    SourceRelationship,
)
from app.modules.investigations.orchestrator import (
    _detect_source_relationships,
    _evidence_packet,
    _persist_evidence,
    _retrieve_candidates,
)
from app.modules.investigations.service import DEV_USER_ID, InvestigationService
from app.modules.sources.evidence_extraction import extract_candidate_excerpts
from app.modules.sources.retrieval import RetrievedPage, excerpt_is_present
from app.modules.sources.source_prioritization import prioritize_sources

FIXTURES = Path(__file__).parent / "fixtures"
Q4_TEXT = (FIXTURES / "ca_sector_report_q4_2025_26.md").read_text()
Q2_TEXT = (FIXTURES / "ca_sector_report_q2_2025_26.md").read_text()
LONG_Q4_TEXT = (FIXTURES / "ca_sector_report_long_q4_2025_26.md").read_text()


class EvidenceLocalizationTests(unittest.TestCase):
    def candidates(self, claim: str, text: str, *, max_windows: int = 2):
        return extract_candidate_excerpts(
            claims=[("claim-1", claim)],
            page_text=text,
            max_chars=6_000,
            remaining_total_chars=24_000,
            max_windows=max_windows,
        )

    def test_exact_numeric_passage_outranks_generic_lexical_overlap(self) -> None:
        claim = "Smartphone connections reached 52.3 million by June 2026."
        text = (
            "The report provides information about smartphone connections and mobile services.\n\n"
            "At the end of June 2026, smartphone connections reached 52.3 million devices."
        )
        candidates = self.candidates(claim, text)
        self.assertIn("52.3 million", candidates[0].excerpt)

    def test_number_and_entity_match_outranks_number_only(self) -> None:
        claim = "The Communications Authority reported 52.3 million smartphones."
        text = "52.3\n\nThe Communications Authority reported 52.3 million smartphones."
        candidates = self.candidates(claim, text)
        self.assertIn("Communications Authority", candidates[0].excerpt)
        self.assertNotEqual(candidates[0].excerpt, "52.3")

    def test_numeric_variants_match_percentages_and_units(self) -> None:
        claim = (
            "Smartphones represented 63.7% of devices and broadband usage was "
            "800 million gigabytes."
        )
        text = (
            "Smartphones represented 63.7 percent of connected devices.\n\n"
            "Mobile broadband usage reached 800m GB."
        )
        candidates = self.candidates(claim, text)
        self.assertGreaterEqual(len(candidates), 1)
        self.assertTrue(any("63.7 percent" in item.excerpt for item in candidates))
        self.assertTrue(any("800m GB" in item.excerpt for item in candidates))

    def test_report_period_relevance_selects_q4_for_june_claim(self) -> None:
        claim = "By the end of June 2026, smartphones reached 52.3 million connections."
        candidates = self.candidates(claim, Q4_TEXT + "\n\n" + Q2_TEXT, max_windows=1)
        self.assertTrue(candidates)
        self.assertIn("52.3", candidates[0].excerpt)
        self.assertNotIn("74.1", candidates[0].excerpt)

    def test_boilerplate_loses_to_claim_relevant_body_passage(self) -> None:
        claim = "The Communications Authority said smartphones reached 52.3 million in June 2026."
        candidates = self.candidates(claim, Q4_TEXT, max_windows=1)
        self.assertIn("Smartphones", candidates[0].excerpt)
        self.assertIn("52.3", candidates[0].excerpt)
        self.assertNotIn("Disclaimer", candidates[0].excerpt)

    def test_table_of_contents_does_not_beat_relevant_report_body(self) -> None:
        claim = "Smartphones reached 52.3 million connected devices in June 2026."
        candidates = self.candidates(claim, Q4_TEXT, max_windows=1)
        self.assertIn("Smartphones", candidates[0].excerpt)
        self.assertNotIn("Table of Contents", candidates[0].excerpt)
        self.assertNotIn("Introduction ................................", candidates[0].excerpt)

    def test_relevant_table_block_is_selected_with_headers(self) -> None:
        claim = "Smartphones accounted for 52.3 million devices and 63.7 percent."
        candidates = self.candidates(claim, Q4_TEXT, max_windows=1)
        excerpt = candidates[0].excerpt
        self.assertIn("Device category", excerpt)
        self.assertIn("Smartphones", excerpt)
        self.assertIn("52.3", excerpt)
        self.assertIn("63.7%", excerpt)

    def test_relevant_heading_context_is_preserved(self) -> None:
        candidates = self.candidates(
            "Smartphone connections reached 52.3 million.",
            "## Mobile devices\n\nSmartphone connections reached 52.3 million.",
            max_windows=1,
        )
        self.assertTrue(candidates)
        self.assertIn("Mobile devices", candidates[0].excerpt)

    def test_excerpt_is_verbatim_after_whitespace_normalization(self) -> None:
        page = "## Mobile devices\n\nSmartphones reached 52.3 million in June 2026."
        candidates = self.candidates(
            "Smartphones reached 52.3 million in June 2026.",
            page,
            max_windows=1,
        )
        self.assertTrue(excerpt_is_present(candidates[0].excerpt, page))

    def test_maximum_evidence_windows_per_claim_is_respected(self) -> None:
        text = (
            "Smartphones reached 52.3 million in June 2026.\n\n"
            "Smartphones accounted for 63.7 percent of connected devices.\n\n"
            "The Communications Authority reported 52.3 million smartphones."
        )
        candidates = self.candidates(
            "The Communications Authority reported that smartphones reached 52.3 million "
            "and 63.7 percent by June 2026.",
            text,
            max_windows=2,
        )
        self.assertLessEqual(len(candidates), 2)

    def test_localization_keeps_relationship_unassigned(self) -> None:
        candidates = self.candidates("Smartphones reached 52.3 million.", Q4_TEXT, max_windows=1)
        self.assertTrue(candidates)
        self.assertFalse(hasattr(candidates[0], "relationship"))

    def test_weak_lexical_overlap_without_specific_anchor_is_rejected(self) -> None:
        candidates = self.candidates(
            "The Communications Authority reported 52.3 million smartphones in June 2026.",
            "The report includes information about communications, mobile services, and devices.",
        )
        self.assertEqual(candidates, [])

    def test_evidence_character_budget_is_respected(self) -> None:
        candidates = self.candidates(
            "Smartphones reached 52.3 million.",
            "Smartphones reached 52.3 million in June 2026 and this was a significant "
            "increase in connected devices.",
        )
        self.assertLessEqual(sum(len(item.excerpt) for item in candidates), 24_000)

    def test_late_pdf_evidence_is_discovered_with_location_and_bounded_regions(self) -> None:
        from app.modules.sources.evidence_extraction import select_claim_relevant_regions

        self.assertGreater(LONG_Q4_TEXT.index("52.3 million"), 6_000)
        regions = select_claim_relevant_regions(
            claim_id="claim-1",
            claim_text=(
                "The Communications Authority reported 52.3 million smartphones by June 2026."
            ),
            document_text=LONG_Q4_TEXT,
            max_regions=4,
            region_chars=6_000,
        )
        self.assertTrue(regions)
        self.assertLessEqual(len(regions), 4)
        self.assertTrue(any("52.3 million" in region.text for region in regions))
        self.assertTrue(any(region.page_number == 12 for region in regions))
        selected_text = "\n\n".join(region.text for region in regions)
        candidates = self.candidates(
            "The Communications Authority reported 52.3 million smartphones by June 2026.",
            selected_text,
            max_windows=1,
        )
        self.assertTrue(candidates)
        self.assertIn("52.3", candidates[0].excerpt)
        self.assertIn("Smartphones", candidates[0].excerpt)
        self.assertNotIn("Disclaimer", candidates[0].excerpt)
        self.assertTrue(excerpt_is_present(candidates[0].excerpt, LONG_Q4_TEXT))


class SourcePrioritizationTests(unittest.TestCase):
    def source(
        self,
        *,
        domain,
        title,
        source_type="UNKNOWN",
        source_role="UNKNOWN",
        status="CANDIDATE",
        url=None,
        published_at=None,
    ):
        return SimpleNamespace(
            id=uuid4(),
            url=url or f"https://{domain}/{title.lower().replace(' ', '-')}",
            canonical_url=None,
            title=title,
            domain=domain,
            source_type=source_type,
            source_role=source_role,
            retrieval_status=status,
            published_at=published_at,
        )

    def test_relevant_official_q4_source_outranks_older_q2_source(self) -> None:
        claim = "CA reported smartphones reached 52.3 million by June 2026."
        q2 = self.source(
            domain="ca.go.ke",
            title="Sector Statistics Report Q2 FY 2025/2026",
            source_type="OFFICIAL",
        )
        q4 = self.source(
            domain="ca.go.ke",
            title="Sector Statistics Report Q4 FY 2025/2026 Smartphones June 2026",
            source_type="OFFICIAL",
        )
        self.assertEqual(prioritize_sources([q2, q4], [claim]), [q4, q2])

    def test_registry_authority_match_affects_retrieval_priority_only(self) -> None:
        claim = "Communications Authority statistics show smartphone connections."
        official = self.source(domain="ca.go.ke", title="Statistics", source_type="OFFICIAL")
        news = self.source(
            domain="citizen.digital",
            title="Communications Authority statistics",
            source_type="NEWS",
        )
        ranked = prioritize_sources([news, official], [claim])
        self.assertEqual(ranked[0], official)
        no_evidence = self.candidates_for(claim, "The Authority publishes annual reports.")
        self.assertEqual(no_evidence, [])

    @staticmethod
    def candidates_for(claim, content):
        return extract_candidate_excerpts(
            claims=[("claim", claim)],
            page_text=content,
            max_chars=1000,
            remaining_total_chars=1000,
        )

    def test_search_result_title_and_highlights_affect_claim_priority(self) -> None:
        claim = "Smartphone connections reached 52.3 million in June 2026."
        generic = self.source(domain="ca.go.ke", title="Sector statistics")
        relevant = self.source(domain="ca.go.ke", title="Report")
        ranked = prioritize_sources(
            [generic, relevant],
            [claim],
            context_by_source={
                generic.id: "annual report contact details",
                relevant.id: "Smartphones 52.3 million June 2026",
            },
        )
        self.assertEqual(ranked[0], relevant)

    def test_publication_recency_only_boosts_current_intent_searches(self) -> None:
        today = date.today()
        older = self.source(
            domain="news.example",
            title="County update",
            source_type="NEWS",
            published_at=(today - timedelta(days=800)).isoformat(),
        )
        recent = self.source(
            domain="news.example",
            title="County update",
            source_type="NEWS",
            published_at=today.isoformat(),
        )
        claim = "County announces a new school closure policy."
        current = prioritize_sources(
            [older, recent],
            [claim],
            context_by_source={
                older.id: "prioritize current information and dated sources",
                recent.id: "prioritize current information and dated sources",
            },
        )
        historical = prioritize_sources([older, recent], [claim])
        self.assertEqual(current[0], recent)
        self.assertEqual(historical[0], older)

    def test_duplicate_canonical_urls_are_ranked_once(self) -> None:
        first = self.source(
            domain="ca.go.ke",
            title="Official report",
            source_type="OFFICIAL",
            url="https://ca.go.ke/report",
        )
        duplicate = self.source(
            domain="mirror.example", title="Mirror report", url="https://mirror.example/report"
        )
        duplicate.canonical_url = first.url
        self.assertEqual(prioritize_sources([duplicate, first], ["official report"]), [first])

    def test_previously_retrieved_source_is_first_and_kept_once(self) -> None:
        retrieved = self.source(
            domain="ca.go.ke", title="Official report", source_type="OFFICIAL", status="RETRIEVED"
        )
        candidate = self.source(domain="news.example", title="New report")
        ranked = prioritize_sources([candidate, retrieved, retrieved], ["official report"])
        self.assertEqual(ranked.count(retrieved), 1)
        self.assertEqual(ranked[0], retrieved)

    def test_source_priorities_do_not_change_evidence_relationships(self) -> None:
        source = self.source(
            domain="ca.go.ke", title="Smartphones 52.3 million", source_type="OFFICIAL"
        )
        self.assertTrue(prioritize_sources([source], ["Smartphones 52.3 million"]))
        candidate = self.candidates_for(
            "Smartphones 52.3 million", "Smartphones reached 52.3 million in June 2026."
        )[0]
        self.assertFalse(hasattr(candidate, "relationship"))

    def test_duplicate_source_does_not_raise_candidate_retrieval_capacity(self) -> None:
        primary = self.source(domain="ca.go.ke", title="Official report", source_type="OFFICIAL")
        duplicate = self.source(domain="mirror.example", title="Mirror report", url=primary.url)
        ranked = prioritize_sources([primary, duplicate], ["official report"])
        self.assertEqual(ranked, [primary])

    def test_prioritization_is_stable_for_equal_priority(self) -> None:
        first = self.source(domain="news.example", title="General report")
        second = self.source(domain="news.example", title="General report 2")
        self.assertEqual(prioritize_sources([first, second], ["unrelated claim"]), [first, second])

    def test_source_limit_is_not_expanded_by_prioritization(self) -> None:
        sources = [self.source(domain="ca.go.ke", title=f"Report {index}") for index in range(8)]
        self.assertEqual(len(prioritize_sources(sources, ["smartphones June 2026"])), 8)


class EvidencePipelineIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session = Session(self.engine, expire_on_commit=False)
        self.investigation = InvestigationService(self.session).create(
            owner_id=DEV_USER_ID,
            content="Communications Authority smartphone figures for June 2026",
            input_type=InputType.TEXT,
            idempotency_key=f"evidence-localization-{uuid4()}",
        )
        self.claim = Claim(
            investigation_id=self.investigation.id,
            text="The Communications Authority reported 52.3 million smartphones by June 2026.",
            normalized_text="communications authority reported 52.3 million smartphones june 2026",
            claim_type="FACTUAL",
        )
        self.session.add(self.claim)
        self.session.commit()
        self.settings = SimpleNamespace(
            max_retrieved_sources=5,
            max_retrieved_document_chars=60_000,
            max_matching_regions_per_claim=4,
            max_source_chars_per_source=6000,
            max_total_evidence_chars=24000,
            max_evidence_windows_per_source_per_claim=2,
            source_reader_provider="jina_reader",
        )
        self.object_store: dict[str, bytes] = {}

    def tearDown(self) -> None:
        self.session.close()
        self.engine.dispose()

    def add_source(
        self,
        *,
        url: str,
        title: str,
        source_type: str = "OFFICIAL",
        status: str = "CANDIDATE",
        canonical_url=None,
    ):
        source = Source(
            investigation_id=self.investigation.id,
            url=url,
            title=title,
            domain=url.split("/")[2],
            source_type=source_type,
            source_role="UNKNOWN",
            discovery_method="EXA",
            retrieval_status=status,
            canonical_url=canonical_url,
            content_storage_key=f"stored/{uuid4()}" if status == "RETRIEVED" else None,
        )
        self.session.add(source)
        self.session.commit()
        return source

    def test_q4_candidate_is_retrieved_before_older_sources_under_same_limit(self) -> None:
        q2 = self.add_source(url="https://ca.go.ke/q2", title="Sector Statistics Q2 FY 2025/2026")
        q4 = self.add_source(
            url="https://ca.go.ke/q4",
            title="Sector Statistics Q4 FY 2025/2026 Smartphones June 2026",
        )
        older = self.add_source(url="https://old.example/report", title="Mobile statistics 2024")
        self.settings.max_retrieved_sources = 2
        retrieved_urls: list[str] = []

        def read(url, **_kwargs):
            retrieved_urls.append(url)
            return RetrievedPage(
                requested_url=url, text="Smartphones reached 52.3 million in June 2026."
            )

        with (
            patch(
                "app.modules.investigations.orchestrator.get_settings", return_value=self.settings
            ),
            patch("app.modules.investigations.orchestrator.read_public_page", side_effect=read),
            patch(
                "app.modules.investigations.orchestrator.put_private_object",
                side_effect=lambda *, key, data, content_type: self.object_store.__setitem__(
                    key, data
                ),
            ),
        ):
            _retrieve_candidates(self.session, self.investigation)
        self.assertIn(q4.url, retrieved_urls)
        self.assertNotIn(older.url, retrieved_urls)
        self.assertEqual(len(retrieved_urls), 2)
        self.assertIsNotNone(q2)

    def test_duplicate_candidate_does_not_consume_a_retrieval_slot(self) -> None:
        primary = self.add_source(url="https://ca.go.ke/report", title="CA report")
        duplicate = self.add_source(
            url="https://mirror.example/report",
            title="Mirror report",
            canonical_url=primary.url,
        )
        candidate = self.add_source(url="https://news.example/story", title="News report")
        self.settings.max_retrieved_sources = 2
        calls: list[str] = []
        with (
            patch(
                "app.modules.investigations.orchestrator.get_settings", return_value=self.settings
            ),
            patch(
                "app.modules.investigations.orchestrator.read_public_page",
                side_effect=lambda url, **_kwargs: (
                    calls.append(url)
                    or RetrievedPage(
                        requested_url=url, text="A relevant report about the Authority."
                    )
                ),
            ),
            patch(
                "app.modules.investigations.orchestrator.put_private_object",
                side_effect=lambda *, key, data, content_type: self.object_store.__setitem__(
                    key, data
                ),
            ),
        ):
            _retrieve_candidates(self.session, self.investigation)
        self.assertNotIn(duplicate.url, calls)
        self.assertEqual(len(calls), 2)
        self.assertIn(primary.url, calls)
        self.assertIn(candidate.url, calls)

    def test_already_retrieved_source_is_loaded_without_an_extra_retrieval_call(self) -> None:
        usage = self.session.scalar(
            select(InvestigationUsage).where(
                InvestigationUsage.investigation_id == self.investigation.id
            )
        )
        stored = self.add_source(
            url="https://ca.go.ke/already-retrieved", title="Official source", status="RETRIEVED"
        )
        self.object_store[stored.content_storage_key] = b"Previously retrieved report passage."
        usage.sources_retrieved = 1
        candidate = self.add_source(url="https://news.example/new", title="New source")
        self.settings.max_retrieved_sources = 2
        calls: list[str] = []
        with (
            patch(
                "app.modules.investigations.orchestrator.get_settings", return_value=self.settings
            ),
            patch(
                "app.modules.investigations.orchestrator.get_private_object",
                side_effect=lambda *, key: self.object_store[key],
            ),
            patch(
                "app.modules.investigations.orchestrator.read_public_page",
                side_effect=lambda url, **_kwargs: (
                    calls.append(url)
                    or RetrievedPage(
                        requested_url=url, text="A new source passage with the Authority."
                    )
                ),
            ),
            patch(
                "app.modules.investigations.orchestrator.put_private_object",
                side_effect=lambda *, key, data, content_type: self.object_store.__setitem__(
                    key, data
                ),
            ),
        ):
            pages = _retrieve_candidates(self.session, self.investigation)
        self.assertEqual(calls, [candidate.url])
        self.assertIn(stored.id, pages)
        self.assertIn(candidate.id, pages)
        self.assertEqual(usage.sources_retrieved, 2)

    def test_persisted_windows_keep_unknown_relationship_and_respect_per_pair_limit(self) -> None:
        source = self.add_source(url="https://ca.go.ke/report", title="CA sector statistics")
        page = (
            "## Mobile devices\n\nSmartphones reached 52.3 million in June 2026.\n\n"
            "Smartphones accounted for 63.7 percent of connected devices, with 52.3 "
            "million smartphones recorded in June 2026."
        )
        with patch(
            "app.modules.investigations.orchestrator.get_settings", return_value=self.settings
        ):
            _persist_evidence(self.session, self.investigation, {source.id: page})
        rows = list(self.session.scalars(select(Evidence).where(Evidence.source_id == source.id)))
        links = list(
            self.session.scalars(
                select(ClaimEvidence).where(ClaimEvidence.claim_id == self.claim.id)
            )
        )
        self.assertEqual(len(rows), 2)
        self.assertEqual(len(links), 2)
        self.assertTrue(all(link.relationship == "UNKNOWN" for link in links))
        self.assertTrue(all(row.method == "CLAIM_ANCHOR_MATCH" for row in rows))

    def test_long_retrieved_document_is_stored_raw_but_only_late_excerpt_is_evidence(self) -> None:
        source = self.add_source(url="https://ca.go.ke/q4.pdf", title="CA report")
        self.settings.max_retrieved_document_chars = 60_000
        self.settings.max_matching_regions_per_claim = 4
        with (
            patch(
                "app.modules.investigations.orchestrator.get_settings", return_value=self.settings
            ),
            patch(
                "app.modules.investigations.orchestrator.read_public_page",
                return_value=RetrievedPage(requested_url=source.url, text=LONG_Q4_TEXT),
            ),
            patch(
                "app.modules.investigations.orchestrator.put_private_object",
                side_effect=lambda *, key, data, content_type: self.object_store.__setitem__(
                    key, data
                ),
            ),
            patch(
                "app.modules.investigations.orchestrator.get_private_object",
                side_effect=lambda *, key: self.object_store[key],
            ),
        ):
            retrieved = _retrieve_candidates(self.session, self.investigation)
            _persist_evidence(self.session, self.investigation, retrieved)
        raw = self.object_store[source.content_storage_key].decode()
        rows = list(self.session.scalars(select(Evidence).where(Evidence.source_id == source.id)))
        self.assertEqual(raw, LONG_Q4_TEXT)
        self.assertGreater(len(raw), 6_000)
        self.assertTrue(rows)
        self.assertTrue(any("52.3" in row.content and "Smartphones" in row.content for row in rows))
        self.assertTrue(all(excerpt_is_present(row.content, raw) for row in rows))
        self.assertLessEqual(sum(len(row.content) for row in rows), 24_000)
        packet = _evidence_packet(self.session, self.investigation)
        self.assertLess(len(packet), len(raw))
        self.assertNotIn("Contact: info@example.invalid", packet)

    def test_evidence_packet_contains_selected_windows_not_full_retrieved_document(self) -> None:
        source = self.add_source(
            url="https://ca.go.ke/report", title="CA sector statistics", status="RETRIEVED"
        )
        evidence = Evidence(
            investigation_id=self.investigation.id,
            source_id=source.id,
            content="Smartphones reached 52.3 million in June 2026.",
            method="CLAIM_ANCHOR_MATCH",
            limitations="Localization does not establish support.",
        )
        self.session.add(evidence)
        self.session.flush()
        self.session.add(
            ClaimEvidence(claim_id=self.claim.id, evidence_id=evidence.id, relationship="UNKNOWN")
        )
        self.session.commit()
        bulk_page = "DISCLAIMER CONTACTS TABLE OF CONTENTS " + ("irrelevant page text " * 500)
        self.object_store[source.content_storage_key] = bulk_page.encode()
        with patch(
            "app.modules.investigations.orchestrator.get_settings", return_value=self.settings
        ):
            packet = _evidence_packet(self.session, self.investigation)
        decoded = json.loads(packet)
        self.assertEqual(len(decoded["evidence"]), 1)
        self.assertIn("52.3 million", decoded["evidence"][0]["excerpt"])
        self.assertNotIn("DISCLAIMER CONTACTS", packet)
        self.assertNotIn("irrelevant page text", packet)

    def test_evidence_packet_respects_total_evidence_context_limit(self) -> None:
        self.settings.max_total_evidence_chars = 250
        source = self.add_source(
            url="https://ca.go.ke/report", title="CA sector statistics", status="RETRIEVED"
        )
        evidence = Evidence(
            investigation_id=self.investigation.id,
            source_id=source.id,
            content="Smartphones " + ("evidence " * 200),
            method="CLAIM_ANCHOR_MATCH",
            limitations="Localization does not establish support.",
        )
        self.session.add(evidence)
        self.session.flush()
        self.session.add(
            ClaimEvidence(claim_id=self.claim.id, evidence_id=evidence.id, relationship="UNKNOWN")
        )
        self.session.commit()
        with patch(
            "app.modules.investigations.orchestrator.get_settings",
            return_value=self.settings,
        ):
            packet = _evidence_packet(self.session, self.investigation)
        decoded = json.loads(packet)
        self.assertLessEqual(sum(len(item["excerpt"]) for item in decoded["evidence"]), 250)

    def test_duplicate_hash_relationship_detection_is_unchanged(self) -> None:
        first = self.add_source(url="https://ca.go.ke/first", title="First")
        second = self.add_source(url="https://mirror.example/copy", title="Copy")
        first.content_sha256 = "same-hash"
        second.content_sha256 = "same-hash"
        self.session.commit()
        with patch(
            "app.modules.investigations.orchestrator.get_settings", return_value=self.settings
        ):
            _detect_source_relationships(
                self.session, self.investigation, {first.id: "first", second.id: "second"}
            )
        relation = self.session.scalar(
            select(SourceRelationship).where(SourceRelationship.source_id == second.id)
        )
        self.assertEqual(relation.relationship_type, "DUPLICATES")
        self.assertEqual(second.source_role, "DERIVATIVE")


if __name__ == "__main__":
    unittest.main()
