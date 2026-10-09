from pathlib import Path

from app.modules.investigations.evidence_ledger import (
    independence_groups,
    staleness_flag,
    validate_excerpt,
    validate_sentence_citations,
)


def test_syndicated_reuters_excerpt_copies_share_one_independence_group():
    result = independence_groups(
        [
            {
                "id": "a",
                "url": "https://wire.example/a",
                "publisher": "Daily One",
                "title": "Reuters: Budget decision",
                "excerpt": (
                    "Reuters reports the ministry published its annual budget on Tuesday "
                    "after a cabinet meeting."
                ),
            },
            {
                "id": "b",
                "url": "https://paper.example/b",
                "publisher": "Daily Two",
                "title": "Budget decision",
                "excerpt": (
                    "The ministry published its annual budget on Tuesday after a cabinet "
                    "meeting, Reuters reports."
                ),
            },
        ]
    )
    assert result["a"] == result["b"]


def test_grouping_handles_shared_domain_and_similar_copy_independently():
    same_domain = independence_groups(
        [
            {"id": "domain-a", "url": "https://news.example.co.ke/a", "publisher": "Outlet A"},
            {"id": "domain-b", "url": "https://www.news.example.co.ke/b", "publisher": "Outlet B"},
        ]
    )
    assert same_domain["domain-a"] == same_domain["domain-b"]

    similar_copy = independence_groups(
        [
            {
                "id": "copy-a",
                "url": "https://alpha.example/a",
                "publisher": "Alpha",
                "excerpt": (
                    "A cabinet committee published the annual budget after its Tuesday meeting."
                ),
            },
            {
                "id": "copy-b",
                "url": "https://beta.example/b",
                "publisher": "Beta",
                "excerpt": (
                    "A cabinet committee published the annual budget after Tuesday's meeting."
                ),
            },
        ]
    )
    assert similar_copy["copy-a"] == similar_copy["copy-b"]


def test_excerpt_validation_records_exact_character_offsets():
    text = "Opening paragraph. Kenya gained independence in 1963. Closing paragraph."
    excerpt = "Kenya gained independence in 1963."
    valid, start, end = validate_excerpt(excerpt, text)
    assert valid is True
    assert text[start:end] == excerpt
    assert validate_excerpt("Kenya became free in 1963.", text) == (False, None, None)


def test_sentence_citations_reject_missing_unretrieved_and_other_run_items():
    evidence = {
        "ok": {
            "retrieved_url": "https://example.org/article",
            "excerpt_validated": True,
            "run_id": "run-1",
        },
        "bad": {"retrieved_url": None, "excerpt_validated": False, "run_id": "run-1"},
    }
    accepted, dropped = validate_sentence_citations(
        [
            {"sentence": "The record confirms the date.", "evidence_ids": ["ok"]},
            {"sentence": "A second unsupported assertion.", "evidence_ids": ["bad"]},
            {"sentence": "Evidence from a prior case.", "evidence_ids": ["old"]},
            {"sentence": "One citation is invalid.", "evidence_ids": ["ok", "bad"]},
            {"sentence": "Missing citation.", "evidence_ids": []},
        ],
        evidence,
        run_id="run-1",
    )
    assert accepted == [{"sentence": "The record confirms the date.", "evidence_ids": ["ok"]}]
    assert dropped is True


def test_staleness_is_only_set_for_old_statistical_evidence():
    from datetime import date

    assert staleness_flag("2024-01-01", "STATISTICAL", reference_date=date(2026, 1, 2)) is True
    assert staleness_flag("2025-12-01", "STATISTICAL", reference_date=date(2026, 1, 2)) is False
    assert staleness_flag("2020-01-01", "CHECKABLE_EVENT", reference_date=date(2026, 1, 2)) is None


def test_unknown_legacy_evidence_defaults_do_not_upgrade_tier_or_stance():
    from app.modules.investigations.models import Evidence

    assert Evidence.__table__.c.source_tier.default.arg == "UNKNOWN"
    assert Evidence.__table__.c.stance.default.arg == "UNKNOWN"
    assert Evidence.__table__.c.independence_group_id.default.arg == "unknown"
    assert Evidence.__table__.c.excerpt_validated.default.arg is False


def test_0014_migration_maps_legacy_rows_to_unknown_and_rolls_back():
    import importlib.util

    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, insert, select

    migration_path = (
        Path(__file__).parents[1] / "migrations" / "versions" / "0014_evidence_ledger.py"
    )
    spec = importlib.util.spec_from_file_location("slice2_migration", migration_path)
    migration = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(migration)
    engine = create_engine("sqlite+pysqlite:///:memory:")
    metadata = MetaData()
    evidence = Table(
        "evidence",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("content", String),
        Column("method", String),
    )
    Table("findings", metadata, Column("id", Integer, primary_key=True))
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(insert(evidence).values(id=1, content="legacy", method="test"))
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
        evidence_after_upgrade = Table("evidence", MetaData(), autoload_with=connection)
        row = connection.execute(select(evidence_after_upgrade)).mappings().one()
        assert row["source_tier"] == "UNKNOWN"
        assert row["stance"] == "UNKNOWN"
        assert row["independence_group_id"] == "unknown"
        assert row["excerpt_validated"] is False
        with Operations.context(MigrationContext.configure(connection)):
            migration.downgrade()
        evidence_after_downgrade = Table("evidence", MetaData(), autoload_with=connection)
        assert "source_tier" not in evidence_after_downgrade.c


def test_jina_reader_is_enabled_by_default():
    from app.core.config import Settings

    assert Settings(_env_file=None).source_reader_provider == "jina_reader"
