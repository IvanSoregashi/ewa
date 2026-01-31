from pathlib import Path

import pandas as pd


def compose_strings_df(df: pd.DataFrame) -> pd.Series:
    return df["filepath"].apply(lambda x: Path(x).stem)
