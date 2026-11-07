# 用途：Meridia 服务请求的清洗与派生——单元 1 唯一可复用模块
from pathlib import Path

import pandas as pd


def load(raw: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """读原始 CSV，返回 (请求表, 区域维表)。"""
    ...


def derive(df: pd.DataFrame) -> pd.DataFrame:
    """只加列、不删行：派生列与标签规范化。"""
    ...


def clean(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """只删行，并返回可审计的日志。"""
    ...


def save(d: pd.DataFrame, dist: pd.DataFrame, out: Path) -> None:
    """写出 parquet + csv。"""
    ...
