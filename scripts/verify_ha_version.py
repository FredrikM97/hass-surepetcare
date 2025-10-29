import json
from pathlib import Path
import sys
import tomllib


def get_homeassistant_version_from_pyproject(pyproject):
    deps = pyproject["project"]["dependencies"]
    for dep in deps:
        if dep.startswith("homeassistant"):
            version = dep.split("=", 1)[-1].lstrip(">")
            return version.strip()
    return None


def main():
    repo_root = Path(__file__).parent.parent
    pyproject_path = repo_root / "pyproject.toml"
    hacs_path = repo_root / "hacs.json"

    try:
        with open(pyproject_path, "rb") as f:
            pyproject = tomllib.load(f)
        ha_version = get_homeassistant_version_from_pyproject(pyproject)
        if not ha_version:
            print("Home Assistant version not found in pyproject.toml dependencies.")
            sys.exit(1)
    except Exception as e:
        print(f"Error reading pyproject.toml: {e}")
        sys.exit(1)

    try:
        with open(hacs_path, encoding="utf-8") as f:
            hacs = json.load(f)
        hacs_ha_version = hacs.get("homeassistant", {})
        if not hacs_ha_version:
            print("Home Assistant min_version not found in hacs.json.")
            sys.exit(1)
    except Exception as e:
        print(f"Error reading hacs.json: {e}")
        sys.exit(1)

    assert (
        ha_version == hacs_ha_version
    ), f"Version mismatch: pyproject.toml={ha_version} hacs.json={hacs_ha_version}"


if __name__ == "__main__":
    main()
