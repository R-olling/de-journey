"""load 层的「盲写」版本（单元 4 补单元 3 的债，不参与日常运行）。

规则：不看 week3/src/load.py、不搜 ON CONFLICT 语法，只看 COLS 和 \\d mart.fact_weather_daily。
行为必须与 week3 一致：同一区间跑两次，fact 行数不变；NaN 进库是 NULL，不是 'NaN'。

和原实现的唯一差别，是把 `pd.Timestamp` 显式转成 `date`：
`isinstance(pd.Timestamp(...), datetime.date)` 是 **True**，所以「先判 date」的顺序会让
Timestamp 原样通过（发给 date 列时 Postgres 会隐式转换，不报错），但类型语义是错的——
`type(x).__name__` 会是 `Timestamp`，下游 `.isoformat()` 之类仍能用，肉眼看不出来。
真实管道里 `date_key` 已经是 `to_datetime(...).date` 得到的 `date`，所以两者跑起来完全一样；
差别只在「有人拿 DataFrame 直接喂它」的时候。这正是盲写时该自己踩出来的坑。
"""

from __future__ import annotations

import os
import sys
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "week3"))

from src.transform import COLS  # noqa: E402

# 键列不能被 UPDATE 改（改了就不是同一行），其余 11 列全部由 EXCLUDED 覆盖
KEY_COLS = {"city_id", "date_key"}
UPDATE_COLS = [c for c in COLS if c not in KEY_COLS]

STG_INSERT = (
    f"INSERT INTO stg.weather_daily ({', '.join(COLS)}) "
    f"VALUES ({', '.join(['%s'] * len(COLS))})"
)

UPSERT = (
    f"INSERT INTO mart.fact_weather_daily ({', '.join(COLS)}) "
    f"SELECT {', '.join(COLS)} FROM stg.weather_daily "
    "ON CONFLICT (city_id, date_key) DO UPDATE SET "
    + ", ".join(f"{c} = EXCLUDED.{c}" for c in UPDATE_COLS)
)


def connect() -> psycopg.Connection:
    """5 个参数全从环境变量读；密码默认空串（默认值写密码是最常见的泄漏点）。"""
    return psycopg.connect(
        host=os.environ.get("PG_HOST", "localhost"),
        port=int(os.environ.get("PG_PORT", "5432")),
        dbname=os.environ.get("PG_DB", "weather"),
        user=os.environ.get("PG_USER", "postgres"),
        password=os.environ.get("PG_PASSWORD", ""),
        connect_timeout=5,
    )


def _cell(value):
    """单个单元格 → psycopg 能安全发送的 Python 对象。

    顺序有讲究：
    1. None / NaN 必须先判 —— psycopg 会把 float('nan') 当 'NaN' 发给 numeric，
       Postgres 接受它且它不等于 NULL，于是 count() 当非空、avg() 变 NaN，全链路不报错；
    2. pd.Timestamp 是 datetime.date 的子类，必须在「通用 date」之前拦下来转成 date；
    3. 其余日期原样过；
    4. numpy 标量（int64/float64/bool_）要 .item() 成 Python 标量，否则 psycopg 类型不适配。
    """
    if value is None:
        return None
    if isinstance(value, pd.Timestamp):
        return value.date()                       # ① Timestamp 先拦（它是 date 的子类）
    if isinstance(value, datetime):
        return value if value.time() != datetime.min.time() else value.date()
    if isinstance(value, date):
        return value                              # ② date 保持 date
    if not isinstance(value, (str, bytes)) and pd.isna(value):
        return None                               # ③ NaN → SQL NULL
    if hasattr(value, "item"):
        return value.item()                       # ④ numpy 标量 → Python 标量
    return value


def to_rows(df: pd.DataFrame) -> list[tuple]:
    """DataFrame → 纯 Python 元组列表。用 itertuples 而不是 iterrows：后者会把整行变成 Series。"""
    return [tuple(_cell(v) for v in rec) for rec in df.itertuples(index=False, name=None)]


def load(df: pd.DataFrame, conn: psycopg.Connection) -> dict[str, int]:
    """TRUNCATE stg → executemany INSERT → INSERT ... ON CONFLICT → 返回两个行数。

    stg 必须 TRUNCATE：它是「本次运行」的缓冲区，留着上次的数据会让对账变成本次 120 行。
    返回的 fact_rows_affected 是「受影响行数」，INSERT 和 UPDATE 都算，**不是新增行数**。
    """
    rows = to_rows(df)
    with conn.cursor() as cur:
        cur.execute("TRUNCATE stg.weather_daily")
        cur.executemany(STG_INSERT, rows)
        stg_rows = cur.rowcount
        cur.execute(UPSERT)
        fact_affected = cur.rowcount
    conn.commit()
    return {"stg_rows": stg_rows, "fact_rows_affected": fact_affected}


def count_fact(conn: psycopg.Connection) -> int:
    return int(conn.execute("SELECT count(*) FROM mart.fact_weather_daily").fetchone()[0])
