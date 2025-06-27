import pytest
from dataclasses import dataclass
from enum import Enum
import time

from custom_components.surepetcare.entity_path import get_by_paths, _serialize_value


@dataclass
class Inner:
    foo: int
    bar: str


@dataclass
class Outer:
    inner: Inner
    items: list[int]
    mapping: dict[str, int]


class Color(Enum):
    RED = 1
    GREEN = 2
    BLUE = 3


@dataclass
class EnumHolder:
    color: Color
    name: str


@dataclass
class Bowl:
    id: int
    name: str
    weight: float


def test_traverse_path_dict():
    data = {"a": {"b": 42}}
    assert get_by_paths(data, {"b": "a.b"}) == {"b": 42}


def test_traverse_path_list():
    data = {"a": [10, 20, 30]}
    assert get_by_paths(data, {"a_1": "a.1"}) == {"a_1": 20}


def test_traverse_path_dataclass():
    data = Outer(inner=Inner(foo=5, bar="baz"), items=[1, 2], mapping={"x": 7})
    assert get_by_paths(data, {"inner_foo": "inner.foo"}) == {"inner_foo": 5}
    assert get_by_paths(data, {"items_1": "items.1"}) == {"items_1": 2}
    assert get_by_paths(data, {"mapping_x": "mapping.x"}) == {"mapping_x": 7}


def test_wildcard_dict():
    data = {"a": {"x": 1, "y": 2}}
    result = get_by_paths(data, {"a_x": "a.*"})
    assert result == {"a_x": 1, "a_x_a_y": 2}


def test_wildcard_dict_blank_key():
    data = {"a": {"x": 1, "y": 2}}
    result = get_by_paths(data, {"": "a.*"})
    assert result == {"a_x": 1, "a_y": 2}


def test_wildcard_list():
    data = {"a": [10, 20, 30]}
    result = get_by_paths(data, {"a": "a.*"})
    assert result == {"a_0": 10, "a_1": 20, "a_2": 30}


def test_wildcard_dataclass():
    data = Inner(foo=5, bar="baz")
    result = get_by_paths(data, {"": "*"})
    assert result == {"foo": 5, "bar": "baz"}


def test_wildcard_nested():
    data = {"a": [Inner(foo=1, bar="x"), Inner(foo=2, bar="y")]}
    result = get_by_paths(data, {"": "a.*.foo"})
    assert result == {"a_0_foo": 1, "a_1_foo": 2}


def test_serialize_enum():
    data = EnumHolder(color=Color.GREEN, name="test")
    result = get_by_paths(data, {"": "color"})
    assert result == {"color": "GREEN"}


def test_flatten():
    data = {"a": {"b": {"c": 1, "d": 2}}}
    result = get_by_paths(data, {"": "a.b.*"}, flatten=True)
    assert result == {"a_b_c": 1, "a_b_d": 2}


def test_native():
    data = {"a": {"b": 123}}
    # Only native, not flatten
    result = get_by_paths(data, {"": "a.b"}, native=True, flatten=False)
    assert result == 123


def test_serialize():
    data = Inner(foo=7, bar="hi")
    result = get_by_paths(data, {"": "foo"}, serialize=True)
    assert result == {"foo": 7}


def test_not_found():
    data = {"a": 1}
    assert get_by_paths(data, {"": "b"}) is None


def test_empty_list():
    data = {"a": []}
    assert get_by_paths(data, {"": "a"}) == {"a": []}


def test_last_index_list():
    data = {"a": [10, 20, 30]}
    # Should get the last item in the list using its actual index
    assert get_by_paths(data, {"": "a.2"}) == {"a_2": 30}


def test_negative_index_list():
    data = {"a": [10, 20, 30]}
    # Should get the last item in the list, but key should be the resolved index
    assert get_by_paths(data, {"": "a.-1"}) == {"a_2": 30}


def test_multiple_paths():
    data = {"a": [10, 20, 30], "b": {"x": 1}}
    result = get_by_paths(data, {"a_0": "a.0", "b_x": "b.x"})
    assert result == {"a_0": 10, "b_x": 1}


def test_wildcard_at_root():
    data = {"foo": 1, "bar": 2}
    result = get_by_paths(data, {"": "*"})
    assert result == {"foo": 1, "bar": 2}


def test_wildcard_on_list():
    data = {"a": [10, 20, 30]}
    result = get_by_paths(data, {"": "a.*"})
    assert result == {"a_0": 10, "a_1": 20, "a_2": 30}


def test_nonexistent_path():
    data = {"a": 1}
    assert get_by_paths(data, {"": "b_c"}) is None


def test_path_to_non_collection():
    data = {"a": 5}
    assert get_by_paths(data, {"": "a_b"}) is None


def test_empty_path_list():
    data = {"a": 1}
    assert get_by_paths(data, {"": []}) is None


def test_list_of_dataclass_wildcard_explicit():
    data = {
        "bowls": [Bowl(id=1, name="A", weight=10.5), Bowl(id=2, name="B", weight=20.0)]
    }
    result = get_by_paths(
        data,
        {
            "bowls_0_id": "bowls.0.id",
            "bowls_0_name": "bowls.0.name",
            "bowls_0_weight": "bowls.0.weight",
        },
    )
    assert result == {"bowls_0_id": 1, "bowls_0_name": "A", "bowls_0_weight": 10.5}


def test_list_of_dataclass_wildcard_wildcard():
    data = {
        "bowls": [Bowl(id=1, name="A", weight=10.5), Bowl(id=2, name="B", weight=20.0)]
    }
    result = get_by_paths(data, {"": "bowls.*.id"})
    assert result == {"bowls_0_id": 1, "bowls_1_id": 2}
    result = get_by_paths(data, {"": "bowls.*.name"})
    assert result == {"bowls_0_name": "A", "bowls_1_name": "B"}
    result = get_by_paths(data, {"": "bowls.*.weight"})
    assert result == {"bowls_0_weight": 10.5, "bowls_1_weight": 20.0}


def test_serialize_custom_object_with_dict():
    class Custom:
        def __init__(self):
            self.x = 1
            self.y = 2

    obj = Custom()
    assert _serialize_value(obj) == {"x": 1, "y": 2}


def test_serialize_object_no_dict():
    class NoDict:
        __slots__ = ("foo",)

        def __init__(self):
            self.foo = 42

    obj = NoDict()
    # Should just return the object itself (not serializable)
    assert _serialize_value(obj) is obj


def test_recursive_get_else_branch():
    # Should not add anything to result if path does not match any type

    class Dummy:
        pass

    data = Dummy()
    assert get_by_paths(data, {"": "foo"}) is None


def test_get_by_paths_typeerror():
    # Pass an invalid type (int) as path
    with pytest.raises(TypeError):
        get_by_paths({}, 123)


def test_flatten_dict_and_dataclass():
    from dataclasses import dataclass

    @dataclass
    class D:
        a: int
        b: int

    data = {"d": {"x": 1, "y": 2}, "c": [D(1, 2)]}
    # Flatten dict
    assert get_by_paths(data, {"": "d"}, flatten=True) == {"d_x": 1, "d_y": 2}
    # Flatten dataclass in list
    assert get_by_paths(data, {"": "c.0"}, flatten=True) == {"c_0_a": 1, "c_0_b": 2}


class FoodType(Enum):
    WET = 1
    DRY = 2


@dataclass
class BowlTargetWeight:
    food_type: FoodType
    full_weight: int


class Device:
    @property
    def bowl_targets(self):
        return [
            BowlTargetWeight(food_type=FoodType.WET, full_weight=0),
            BowlTargetWeight(food_type=FoodType.WET, full_weight=0),
        ]


def test_property_list_of_dataclass_flatten():
    device = Device()
    # Get the list as a whole
    result = get_by_paths(device, {"": "bowl_targets"})
    assert result == {
        "bowl_targets": [
            {"food_type": "WET", "full_weight": 0},
            {"food_type": "WET", "full_weight": 0},
        ]
    }
    # Get each item in the list, fully flattened
    result = get_by_paths(device, {"": "bowl_targets.*"}, flatten=True)
    assert result == {
        "bowl_targets_0_food_type": "WET",
        "bowl_targets_0_full_weight": 0,
        "bowl_targets_1_food_type": "WET",
        "bowl_targets_1_full_weight": 0,
    }
    # Flatten each item in the list (same as above)
    result = get_by_paths(device, {"": "bowl_targets.*"}, flatten=True)
    assert result == {
        "bowl_targets_0_food_type": "WET",
        "bowl_targets_0_full_weight": 0,
        "bowl_targets_1_food_type": "WET",
        "bowl_targets_1_full_weight": 0,
    }


def test_wildcard_dict_key_same_as_path():
    data = {"a": {"x": 1, "y": 2}}
    # If the key is the same as the first part of the path, should still prefix both
    result = get_by_paths(data, {"a": "a.*"})
    assert result == {"a_x": 1, "a_y": 2}


def test_get_by_paths_path_cache_speed():
    data = {"a": {"b": {"c": 123}}}
    path = {"": "a.b.c"}
    # First batch (cache miss)
    t0 = time.perf_counter()
    for _ in range(1000):
        get_by_paths(data, path)
    t1 = time.perf_counter()
    # Second batch (cache hit)
    for _ in range(1000):
        get_by_paths(data, path)
    t2 = time.perf_counter()
    print("First batch:", t1 - t0, "Second batch:", t2 - t1)
    # The second batch should not be slower than the first (allow some noise)
    assert (t2 - t1) <= (t1 - t0) * 1.2


def test_get_by_paths_path_cache_info():
    data = {"a": {"b": {"c": 123}}}
    path = {"": "a.b.c"}
    get_by_paths(data, path)
    cache_info = get_by_paths.__globals__["_parse_path_str"].cache_info()
    print("Cache info:", cache_info)
    assert cache_info.hits >= 0
    assert cache_info.misses >= 1
