"""Every string the code assigns to a model column must fit that column.

SQLite ignores VARCHAR lengths, so unit tests pass even when PostgreSQL would reject
the value. This scans the app for `obj.<column> = "LITERAL"` and checks the literal
against the longest String(n) column of that name (names such as `state` are shared
by tables of different widths, so this only flags values that fit none of them).
"""

import ast
from pathlib import Path

from sqlalchemy import String

from app.db.base import Base
from app.modules.investigations import models  # noqa: F401

APP = Path(__file__).resolve().parents[1] / "app"


def _column_lengths() -> dict[str, int]:
    lengths: dict[str, int] = {}
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, String) and column.type.length:
                current = lengths.get(column.name)
                lengths[column.name] = max(current or 0, column.type.length)
    return lengths


def _literal_assignments():
    for path in APP.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            value = node.value
            if not (isinstance(value, ast.Constant) and isinstance(value.value, str)):
                continue
            for target in node.targets:
                if isinstance(target, ast.Attribute):
                    yield path, node.lineno, target.attr, value.value


def test_assigned_status_literals_fit_their_columns():
    lengths = _column_lengths()
    too_long = [
        f"{path.relative_to(APP)}:{line} {attr}={text!r} ({len(text)} > {lengths[attr]})"
        for path, line, attr, text in _literal_assignments()
        if attr in lengths and len(text) > lengths[attr]
    ]
    assert not too_long, "\n".join(too_long)


def test_retrieval_status_column_fits_deadline_status():
    column = Base.metadata.tables["sources"].columns["retrieval_status"]
    assert column.type.length >= len("NOT_ATTEMPTED_DEADLINE")
