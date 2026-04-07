import json
import sys
import re
import tomllib
from pathlib import Path
from importlib.metadata import version as get_version, PackageNotFoundError


def parse_version(version):
    return tuple(map(int, re.findall(r"\d+", version)))


def get_min_ha_version(hacs):
    ha = hacs.get("homeassistant")
    return ha.get("min_version") if isinstance(ha, dict) else ha


def get_requirement_version(requirements, name):
    """Extract version from requirement string list."""
    for req in requirements:
        if name in req:
            # Try git URL format first (e.g., package@git+https://...@v1.2.3)
            git_match = re.search(rf"{name}@git\+https://[^@]+@v?([\w\.\-]+)", req)
            if git_match:
                return git_match.group(1).replace("-", ".")
            # Fall back to standard format (e.g., package==1.2.3)
            match = re.search(rf"{name}(?:==|~=|>=|<=|!=|>|<)\s*([\w\.\-]+)", req)
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

    with open(root / "pyproject.toml", "rb") as f:
        pyproject = tomllib.load(f)

    with open(root / "custom_components/surepcha/manifest.json") as f:
        manifest = json.load(f)

    # Get versions from both files
    dev_deps = pyproject.get("dependency-groups", {}).get("dev", [])
    assert dev_deps, "dependency-groups.dev not found in pyproject.toml"
    pyproject_ver = get_requirement_version(dev_deps, "py-surepetcare")
    manifest_ver = get_requirement_version(
        manifest.get("requirements", []), "py-surepetcare"
    )

    assert pyproject_ver, "py-surepetcare not found in pyproject.toml dev dependencies"
    assert manifest_ver, "py-surepetcare not found in manifest.json requirements"

    assert (
        manifest_ver == pyproject_ver
    ), f"py-surepetcare: manifest.json ({manifest_ver}) != pyproject.toml ({pyproject_ver})"


if __name__ == "__main__":
    main()
