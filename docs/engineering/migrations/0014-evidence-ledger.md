# Migration 0014: Evidence ledger

Upgrade adds source tier, stance, exact excerpt offsets, independence group,
publication date, nullable staleness, retrieval timestamp, case run ID, and quote
validation fields to `evidence`. It also adds sentence-level explanation JSON and
the unsupported-statement removal flag to `findings`.

Existing evidence is mapped conservatively: tier and stance are `UNKNOWN`, group
is `unknown`, date/timestamps/offsets/run ID/staleness remain null, and quote
validation is false. Existing explanations are empty arrays; old `statement`
text remains available for legacy records but is not converted into cited
sentences.

Rollback: stop workers, back up the database, then run `alembic downgrade
0013_slice1_verdict_contract`. This drops all new columns and therefore removes
the ledger metadata and sentence citation mapping. Existing evidence content and
finding statements remain intact.
