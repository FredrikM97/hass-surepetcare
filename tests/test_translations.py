import json
from pathlib import Path


def flatten_keys(data, prefix=""):
    keys = set()
    for k, v in data.items():
        path = f"{prefix}.{k}" if prefix else k
        keys.add(path)
        if isinstance(v, dict):
            keys |= flatten_keys(v, path)
    return keys


def get_key_order(reference, target, prefix=""):
    mismatches = []
    if isinstance(reference, dict) and isinstance(target, dict):
        ref_keys = list(reference.keys())
        tgt_keys = list(target.keys())
        if ref_keys != tgt_keys:
            mismatches.append((prefix, ref_keys, tgt_keys))
        for k in reference:
            if k in target:
                mismatches += get_key_order(
                    reference[k], target[k], f"{prefix}.{k}" if prefix else k
                )
    return mismatches


def pytest_generate_tests(metafunc):
    if "translation_file" in metafunc.fixturenames:
        translations_dir = Path("custom_components/surepcha/translations")
        files = [f for f in translations_dir.glob("*.json") if f.name != "en.json"]
        metafunc.parametrize("translation_file", files)


def test_translation_files_exist():
    translations_dir = Path("custom_components/surepcha/translations")
    files = list(translations_dir.glob("*.json"))
    assert files, "No translation files found"
    assert any(
        f.name == "en.json" for f in files
    ), "en.json should exist as the main translation file"


def test_translation_key_consistency(translation_file):
    translations_dir = Path("custom_components/surepcha/translations")
    with open(translations_dir / "en.json", encoding="utf-8") as f:
        en_data = json.load(f)
    with open(translation_file, encoding="utf-8") as f:
        other_data = json.load(f)

    en_keys = flatten_keys(en_data)
    other_keys = flatten_keys(other_data)
    missing = sorted(en_keys - other_keys)
    extra = sorted(other_keys - en_keys)

    msg = []
    if missing:
        msg.append(f"\nMissing keys in {translation_file.name}:")
        msg.append("  | Key                                   | Action         |")
        msg.append("  |----------------------------------------|---------------|")
        for key in missing:
            msg.append(f"  | {key:<38} | Add from en.json |")
    if extra:
        msg.append(f"\nExtra keys in {translation_file.name}:")
        msg.append("  | Key                                   | Action         |")
        msg.append("  |----------------------------------------|---------------|")
        for key in extra:
            msg.append(f"  | {key:<38} | Remove           |")
    if msg:
        msg.append("\nHow to fix:")
        if missing:
            msg.append("  • Add the missing keys from en.json to this file.")
        if extra:
            msg.append("  • Remove the extra keys or add them to en.json if needed.")
        assert False, "\n".join(msg)


def test_translation_key_order_strict(translation_file):
    translations_dir = Path("custom_components/surepcha/translations")
    with open(translations_dir / "en.json", encoding="utf-8") as f:
        en_data = json.load(f)
    with open(translation_file, encoding="utf-8") as f:
        other_data = json.load(f)

    mismatches = get_key_order(en_data, other_data)
    if mismatches:
        msg = ["Key order mismatch detected:"]
        for path, en_keys, other_keys in mismatches:
            msg.append(f"\nSection: {path or '<root>'}")
            msg.append(f"  en.json:    {en_keys}")
            msg.append(f"  {translation_file.name}: {other_keys}")
        msg.append(
            "\nTo fix: Run scripts/reorder_translations.py to automatically reorder the keys in this file."
        )
        assert False, "\n".join(msg)
