import json
from pathlib import Path


def reorder_dict(reference, target):
    if not isinstance(reference, dict) or not isinstance(target, dict):
        return target
    reordered = {}
    for key in reference:
        if key in target:
            reordered[key] = reorder_dict(reference[key], target[key])
    for key in target:
        if key not in reordered:
            reordered[key] = target[key]
    return reordered


def main():
    translations_dir = Path("custom_components/surepcha/translations")
    with open(translations_dir / "en.json", encoding="utf-8") as f:
        en_data = json.load(f)

    for file_path in translations_dir.glob("*.json"):
        if file_path.name == "en.json":
            continue
        with open(file_path, encoding="utf-8") as f:
            other_data = json.load(f)
        reordered = reorder_dict(en_data, other_data)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(reordered, f, ensure_ascii=False, indent=2)
        print(f"Reordered {file_path.name}")


if __name__ == "__main__":
    main()
