import json
import sys
import re
from pathlib import Path
from importlib.metadata import version as get_version, PackageNotFoundError


def parse_version(version):
    return tuple(map(int, re.findall(r"\d+", version)))


def get_min_ha_version(hacs):
    ha = hacs.get("homeassistant")
    return ha.get("min_version") if isinstance(ha, dict) else ha


def get_manifest_requirement(manifest, name):
    for req in manifest.get("requirements", []):
        if name in req:
            match = re.search(rf"{name}[>=!~]=?([\w\.\-]+)", req)
            if match:
                return match.group(1).replace("-", ".")
    return None


def main():
    root = Path(__file__).parent.parent

    with open(root / "hacs.json", encoding="utf-8") as f:
        hacs = json.load(f)
    min_ha = get_min_ha_version(hacs)
    try:
        ha_inst = get_version("homeassistant")
    except PackageNotFoundError:
        sys.exit("homeassistant is not installed")
    assert parse_version(ha_inst) >= parse_version(
        min_ha
    ), f"Installed homeassistant ({ha_inst}) < hacs.json min_version ({min_ha})"

    with open(root / "custom_components/surepcha/manifest.json") as f:
        manifest = json.load(f)
    manifest_ver = get_manifest_requirement(manifest, "py-surepetcare")
    assert (
        manifest_ver
    ), "py-surepetcare not found or version missing in manifest.json requirements"
    try:
        installed_ver = get_version("py-surepetcare").replace("-", ".")
    except PackageNotFoundError:
        sys.exit("py-surepetcare is not installed")
    assert (
        installed_ver == manifest_ver
    ), f"py-surepetcare: manifest.json ({manifest_ver}) != installed ({installed_ver})"


if __name__ == "__main__":
    main()
