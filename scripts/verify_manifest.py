import json
import re
import importlib.metadata

def normalize_version(version):
    return version.replace("-", ".")

def test_manifest_and_installed_dependency_match():
    with open("custom_components/surepcha/manifest.json") as f:
        manifest = json.load(f)
    manifest_req = next((r for r in manifest["requirements"] if "py-surepetcare" in r), None)
    assert manifest_req, "py-surepetcare not found in manifest.json requirements"

    m = re.search(r"py-surepetcare>=(\S+)", manifest_req)
    assert m, "Version not found in manifest requirement"
    manifest_version = m.group(1)

    try:
        installed_version = importlib.metadata.version("py-surepetcare")
    except importlib.metadata.PackageNotFoundError as e:
        raise AssertionError(f"py-surepetcare is not installed: {e}")

    manifest_version_norm = normalize_version(manifest_version)
    installed_version_norm = normalize_version(installed_version)

    assert installed_version_norm == manifest_version_norm, (
        f"Installed version ({installed_version}) does not match manifest version ({manifest_version})"
    )

if __name__ == "__main__":
    test_manifest_and_installed_dependency_match()
    print("Manifest and installed dependency versions match.")