from dataclasses import dataclass, is_dataclass, fields, asdict
from typing import Any
from collections.abc import Mapping
from enum import Enum
from functools import lru_cache
import logging

logger = logging.getLogger(__name__)
WILDCARD = "*"


@dataclass
class TraversalOptions:
    native: bool = False
    serialize: bool = True
    flatten: bool = False


class PathWildcard(Enum):
    WILDCARD = "*"


def is_structured(obj):
    return isinstance(obj, Mapping) or is_dataclass(obj)


def _serialize_value(obj):
    if isinstance(obj, Enum):
        return obj.name
    if is_dataclass(obj):
        return {f.name: _serialize_value(getattr(obj, f.name)) for f in fields(obj)}
    if isinstance(obj, dict):
        return {k: _serialize_value(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_serialize_value(v) for v in obj]
    if hasattr(obj, "__dict__"):
        return {k: _serialize_value(v) for k, v in obj.__dict__.items()}
    return obj


def _flatten_dict(d, prefix=()):
    if is_dataclass(d):
        d = {f.name: getattr(d, f.name) for f in fields(d)}
    for k, v in d.items():
        new_key = prefix + (k,)
        if isinstance(v, dict) or is_dataclass(v):
            yield from _flatten_dict(v, new_key)
        else:
            yield (
                "_".join(str(x) for x in new_key),
                v.name if isinstance(v, Enum) else v,
            )


def _traverse(data, path, key_path=()):
    if is_dataclass(data):
        data = asdict(data)
    if not path:
        yield ("_".join(str(x) for x in key_path), data)
        return

    if not data:
        return data

    key, *rest = path
    if isinstance(data, dict):
        if key == PathWildcard.WILDCARD:
            for k, v in data.items():
                yield from _traverse(v, rest, (*key_path, k))
            return
        if key in data:
            yield from _traverse(data[key], rest, (*key_path, key))
            return
        return
    if isinstance(data, list):
        if key == PathWildcard.WILDCARD:
            for i, v in enumerate(data):
                yield from _traverse(v, rest, (*key_path, i))
            return
        idx = int(key)
        if idx < 0:
            idx += len(data)
        if 0 <= idx < len(data):
            yield from _traverse(data[idx], rest, (*key_path, idx))
        else:
            return

        return

    if hasattr(data, key):
        if key == PathWildcard.WILDCARD:
            for k, v in data.items():
                yield from _traverse(v, rest, (*key_path, k))
            return

        yield from _traverse(getattr(data, key, object()), rest, (*key_path, key))
        return
    logger.debug(
        "Key '%s' not found in data structure at path %s",
        key,
        ".".join(str(x) for x in key_path),
    )


@lru_cache(maxsize=128)
def _parse_path_str(path_str):
    return tuple(
        PathWildcard.WILDCARD if p == WILDCARD else p for p in path_str.split(".")
    )


def get_by_paths(
    data: object,
    path: dict[str, str] | str,
    **kwargs,
) -> Any | None:
    """Traverse and extract values from nested data structures (dicts, dataclasses, lists, objects) using dot-separated paths.
    Supports options for serialization, flattening, and list expansion via keyword arguments.

    Args:
        data: The root object or data structure to traverse.
        path: List of dot-separated string paths to extract (e.g., ["foo.bar", "baz.0"]).
        **kwargs: TraversalOptions fields as keyword arguments (e.g., flatten=True, serialize=True).

    Returns:
        A dict mapping path strings to extracted values, or None if nothing found.

    """
    options = TraversalOptions(**kwargs)
    if options.native and options.flatten:
        raise ValueError("native and flatten cannot both be True")

    if not isinstance(path, (dict, str)):
        raise TypeError(f"paths must be a dict or str, got {type(path).__name__}")

    if isinstance(path, str):
        path = {path: path}

    path_items = list(path.items())

    pairs = []
    for out_key, path_str in path_items:
        if not isinstance(path_str, str):
            continue  # skip non-string paths (e.g., empty list)
        keys = _parse_path_str(path_str)
        is_wildcard = any(p == PathWildcard.WILDCARD for p in keys)
        for k, v in _traverse(data, keys):
            # If the output key is blank, use the traversal key as the output key
            if out_key == "":
                full_key = k
            elif is_wildcard and k and (k.startswith(out_key) or out_key in k):
                full_key = k
            elif is_wildcard and k and out_key != k:
                full_key = f"{out_key}_{k}"
            else:
                full_key = out_key
            pairs.append((full_key, v))
    results = dict(pairs) if pairs else None
    if results:

        def normalize(v):
            if isinstance(v, list):
                if v and is_dataclass(v[0]):
                    return [asdict(i) for i in v]
                return v
            if isinstance(v, Enum):
                return v.name
            if is_dataclass(v):
                return asdict(v)
            return v

        results = {k: normalize(v) for k, v in results.items()}
    if options.serialize and results:
        results = {k: _serialize_value(v) for k, v in results.items()}
    if options.flatten and results and not options.native:
        flat = {}
        for k, v in results.items():
            v = asdict(v) if is_dataclass(v) else v
            if isinstance(v, dict):
                for fk, fv in _flatten_dict(v, (k,)):
                    flat[fk] = fv
            else:
                flat[k] = v
        results = flat or None
    if options.native and results:
        return next(iter(results.values()))
    return results


def build_nested_dict(field_path: str, value: float | int | str) -> dict:
    """Build a nested dict/list structure from a dotted field path, handling list indices.
    Skips the top-level 'control' key.
    """
    parts = field_path.split(".")
    if parts and parts[0] == "control":
        parts = parts[1:]
    result: object = value
    for part in reversed(parts):
        if part.isdigit():
            idx = int(part)
            lst: list = []
            while len(lst) <= idx:
                lst.append(None)
            lst[idx] = result
            result = lst
        else:
            result = {part: result}
    return result if isinstance(result, dict) else {parts[0]: result}
