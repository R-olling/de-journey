"""加载层：DataFrame → stg（覆盖）→ fact（upsert）。

两条腿：
- 幂等：fact 的主键是 (city_id, date_key)，ON CONFLICT DO UPDATE → 同一区间跑两次，行数不变；
- 类型安全：把 NaN 显式转成 None，**不让 pandas 的缺失值漏进数据库**。

为什么不用 df.to_sql()：pandas 对非 SQLite 只支持 SQLAlchemy 引擎，裸 psycopg 连接会报
`ProgrammingError: the query has 0 placeholders but 1 parameters were passed`。
自己写 INSERT 多几十行，但语义全在眼皮底下。
"""

from __future__ import annotations

import os
from datetime import date

import pandas as pd
import psycopg

from .transform import COLS

DB_COLS = COLS

# 列名和占位符都由 COLS 生成 —— 手写 13 个 %s 是最容易错位的地方
STG_INSERT = f"""
INSERT INTO stg.weather_daily ({", ".join(DB_COLS)})
VALUES ({", ".join(["%s"] * len(DB_COLS))})
"""

# 13 列里更新 11 列：除两个键（city_id / date_key）以外的全部。
# 键不能改；派生列也更新，是因为它们由源列决定，一起写进去下游就不用再算一遍。
UPSERT = f"""
INSERT INTO mart.fact_weather_daily ({", ".join(DB_COLS)})
SELECT {", ".join(DB_COLS)} FROM stg.weather_daily
ON CONFLICT (city_id, date_key) DO UPDATE SET
    tmax_c       = EXCLUDED.tmax_c,
    tmin_c       = EXCLUDED.tmin_c,
    tmean_c      = EXCLUDED.tmean_c,
    app_max_c    = EXCLUDED.app_max_c,
    app_min_c    = EXCLUDED.app_min_c,
    precip_mm    = EXCLUDED.precip_mm,
    precip_h     = EXCLUDED.precip_h,
    wind_max_kmh = EXCLUDED.wind_max_kmh,
    temp_range_c = EXCLUDED.temp_range_c,
    feels_like_c = EXCLUDED.feels_like_c,
    is_precip    = EXCLUDED.is_precip
"""


def connect() -> psycopg.Connection:
    """连接参数全部来自环境变量（.env 由 run.py 提前加载）。

    密码的默认值是空串而不是真密码 —— 默认值写密码是最常见的泄漏点。
    """
    return psycopg.connect(
        host=os.environ.get("PG_HOST", "localhost"),
        port=int(os.environ.get("PG_PORT", "5432")),
        dbname=os.environ.get("PG_DB", "weather"),
        user=os.environ.get("PG_USER", "postgres"),
        password=os.environ.get("PG_PASSWORD", ""),
        connect_timeout=5,
    )


def to_rows(df: pd.DataFrame) -> list[tuple]:
    """DataFrame → 一组纯 Python 元组。

    这一步不是洁癖，实测有据：
    - pandas 的缺失值是 `nan`，psycopg 会把它当 float('nan') 发给 numeric 列，
      库里存的是 'NaN' 而不是 NULL —— 不报错，但 avg() 之后整列变成 NaN；
    - date 列要拿到 datetime.date，否则 pandas 的 Timestamp 会被当成 timestamp 发过去。
    """
    rows = []
    for rec in df.itertuples(index=False, name=None):
        row = []
        for value in rec:
            if value is None or (not isinstance(value, (str, date)) and pd.isna(value)):
                row.append(None)                 # NaN → SQL NULL
            elif isinstance(value, date):
                row.append(value)                # date 保持 date
            elif hasattr(value, "item"):
                row.append(value.item())         # numpy 标量 → Python 标量
            else:
                row.append(value)
        rows.append(tuple(row))
    return rows


def load(df: pd.DataFrame, conn: psycopg.Connection) -> dict[str, int]:
    """stg 覆盖写 → fact upsert。返回两个行数，供日志对账。

    TRUNCATE 是必须的：stg 是「本次运行」的缓冲区，不是历史。
    不 truncate，第二次跑 stg 变 1200 行，对账时你会误判成「写重复了」。
    """
    rows = to_rows(df)
    with conn.cursor() as cur:
        cur.execute("TRUNCATE stg.weather_daily")
        cur.executemany(STG_INSERT, rows)
        stg_n = cur.rowcount
        cur.execute(UPSERT)
        fact_n = cur.rowcount
    conn.commit()
    return {"stg_rows": stg_n, "fact_rows_affected": fact_n}


def count_fact(conn: psycopg.Connection) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM mart.fact_weather_daily")
        return int(cur.fetchone()[0])
