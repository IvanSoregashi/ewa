from pathlib import Path

import pandas as pd


def compose_strings_df(df: pd.DataFrame) -> pd.Series:
    return df["filepath"].apply(lambda x: Path(x).stem)


def translate_chapter_naive(chapter: str, translator: dict) -> str:
    return "".join(translator.get(ch, ch) for ch in chapter)


def translate_chapter_str(chapter: str, translator: dict) -> str:
    table = str.maketrans(translator)
    new_text = chapter.translate(table)
    return new_text
