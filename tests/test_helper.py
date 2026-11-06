"""Configuration and diagnostics remain independent of entity data."""

from pydantic import BaseModel

from custom_components.surepcha.helper import serialize


class _LegacyModel(BaseModel):
    value: str

    def __getattribute__(self, name: str) -> object:
        if name == "model_dump":
            raise AttributeError(name)
        return super().__getattribute__(name)


def test_serialize_uses_legacy_pydantic_dict():
    assert serialize(_LegacyModel(value="pet")) == {"value": "pet"}


def test_diagnostics_do_not_serialize_static_field_schemas():
    class Device:
        field_definitions = ("static metadata",)

        @property
        def name(self):
            return "Device"

    assert serialize(Device()) == {"name": "Device"}
