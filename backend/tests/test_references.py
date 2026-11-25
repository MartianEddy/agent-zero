import re

import pytest

from app.modules.investigations.references import ALPHABET, new_reference, parse_reference


def test_new_references_are_short_and_readable():
    for _ in range(200):
        reference = new_reference(lambda _candidate: False)
        assert re.fullmatch(r"AZ-[0-9A-HJKMNP-TV-Z]{5}", reference)
        assert not set(reference[3:]) & set("ILOU")
    assert len(ALPHABET) == 32


def test_a_taken_reference_is_redrawn():
    taken = {"first"}
    seen = []

    def is_taken(candidate):
        seen.append(candidate)
        return len(seen) == 1 and bool(taken)

    reference = new_reference(is_taken)
    assert len(seen) == 2 and reference == seen[1]


def test_running_out_of_draws_fails_loudly():
    with pytest.raises(RuntimeError):
        new_reference(lambda _candidate: True, attempts=3)


@pytest.mark.parametrize(
    "typed",
    ["AZ-7KQ2F", "az-7kq2f", "AZ 7KQ2F", "az7kq2f", "7KQ2F", " 7kq2f ", "#7KQ2F", "AZ-7KQ-2F"],
)
def test_typed_forms_resolve_to_the_stored_reference(typed):
    assert parse_reference(typed) == "AZ-7KQ2F"


def test_look_alike_letters_are_read_as_digits():
    assert parse_reference("AZ-O1LI0") == "AZ-01110"


def test_older_references_still_resolve():
    assert parse_reference("AZ-261028-ED24C0") == "AZ-261028-ED24C0"
    assert parse_reference("az-261028-ed24c0") == "AZ-261028-ED24C0"
    assert parse_reference("AZ261028ED24C0") == "AZ-261028-ED24C0"


@pytest.mark.parametrize("typed", ["", None, "AZ-12", "AZ-7KQ2FX9", "AZ-7KQ2U", "results"])
def test_non_references_are_rejected(typed):
    assert parse_reference(typed) is None
