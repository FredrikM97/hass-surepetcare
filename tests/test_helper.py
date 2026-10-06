"""Tests for shared SurePetCare helper functions."""

from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from custom_components.surepcha.helper import ensure_list, index_attr, serialize


@pytest.mark.parametrize(
    ("sequence", "index", "attribute", "default"),
    [([], 0, None, "missing"), (None, 0, None, "invalid")],
)
def test_index_attr_returns_default_for_invalid_index(
    sequence: object, index: int, attribute: str | None, default: str
) -> None:
    """Invalid sequences and indexes return the caller's default."""
    assert index_attr(sequence, index, attribute, default) == default


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, []),
        (["pet", None], ["pet"]),
        ({"first": "pet", "second": None}, ["pet"]),
        ("pet", ["pet"]),
    ],
)
def test_ensure_list_normalizes_values(value: object, expected: list[object]) -> None:
    """Missing values become empty lists; collections filter out None."""
    assert ensure_list(value) == expected


def test_ensure_list_returns_empty_for_missing_attribute() -> None:
    """Attribute traversal stops when a requested attribute is missing."""
    assert ensure_list(SimpleNamespace(value=None), "value", "child") == []


class _LegacyModel(BaseModel):
    value: str

    def __getattribute__(self, name: str) -> object:
        if name == "model_dump":
            raise AttributeError(name)
        return super().__getattribute__(name)


def test_serialize_uses_legacy_pydantic_dict() -> None:
    """Pydantic models without model_dump use the compatibility fallback."""
    assert serialize(_LegacyModel(value="pet")) == {"value": "pet"}
