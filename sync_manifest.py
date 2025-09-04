import toml
import json

manifest_path = "custom_components/surepetcare/manifest.json"

def parse_pkg(dep):
    return dep.split("==")[0].split(">=")[0].split("<=")[0].strip()

with open("pyproject.toml", "r") as py_f, open(manifest_path, "r+") as man_f:
    pyproject = toml.load(py_f)
    deps = pyproject.get("project", {}).get("dependencies", [])
    dep_map = {parse_pkg(dep): dep for dep in deps}
    manifest = json.load(man_f)

    new_reqs = []
    for req in manifest.get("requirements", []):
        pkg = parse_pkg(req)
        if pkg in dep_map:
            new_reqs.append(dep_map[pkg])
        else:
            new_reqs.append(req)
    manifest["requirements"] = new_reqs

    man_f.seek(0)
    json.dump(manifest, man_f, indent=4)
    man_f.truncate()
