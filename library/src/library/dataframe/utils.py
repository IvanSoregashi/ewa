import pandas as pd


def join_dfs(df1: pd.DataFrame, df2: pd.DataFrame) -> pd.DataFrame:
    assert len(df1) == len(df2), "DataFrames must have the same length"
    return pd.concat([df1.reset_index(drop=True), df2.reset_index(drop=True)], axis=1)
