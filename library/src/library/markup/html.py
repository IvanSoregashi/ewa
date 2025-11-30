from pathlib import Path


def translate_text_file(filepath: Path, translation: dict[str, str]):
    text = filepath.read_text(encoding="utf-8")
    result = ""
    for i in text:
        result += translation.get(i, i)
    filepath.write_text(result, encoding="utf-8")
