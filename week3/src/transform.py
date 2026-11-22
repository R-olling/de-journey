"""转换层：data/raw/*.json（列式）→ 内存里的长表（600 行 x 13 列）+ 6 条入库前校验

设计约束（三条）：
1. 只做「形状 + 类型 + 派生列」，不删行、不改口径 —— 删除要有依据，依据没出现就不写；
2. 派生列只用「同一行」的信息 —— 跨行（连续 N 天、近 7 天均值）属于 SQL 窗口函数；
3. validate 只回答「能不能入库」，绝不修改数据 —— 它返回结论，由调用方决定退不退出。
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import date
from pathlib import Path

import pandas as pd

from .extract import CITIES, RAW_DIR

log = logging.getLogger(__name__)

# 口径参数：>= 1.0mm 才算「今天真下雨了」（0.1mm 只算「有降水」，含毛毛雨）
# 写成常量而不是散在代码里，是为了别人问「为什么是 4 个城市」时能指着这一行回答
PRECIP_THRESHOLD_MM = 1.0

# API 字段 → 目标列名。改名只在这一个地方发生，键的顺序就是最终列的顺序
FIELD_MAP: dict[str, str] = {
    "temperature_2m_max":       "tmax_c",
    "temperature_2m_min":       "tmin_c",
    "temperature_2m_mean":      "tmean_c",
    "apparent_temperature_max": "app_max_c",
    "apparent_temperature_min": "app_min_c",
    "precipitation_sum":        "precip_mm",
    "precipitation_hours":      "precip_h",
    "wind_speed_10m_max":       "wind_max_kmh",
}

# 13 列的最终顺序：2 个键 + 8 个原始值 + 3 个派生列
COLS = ["city_id", "date_key", *FIELD_MAP.values(),
           "temp_range_c", "feels_like_c", "is_precip"]


def parse_one(path: Path, city_id: str) -> pd.DataFrame:
    """一个 JSON → 一个城市的长表（75 行）。

    关键点：`daily` 是「列式」的 —— 9 个 key，每个是长度 75 的 list。
    把每个 key 当成一列、长度天然就是行数，所以直接构造 DataFrame 就是 75 行，
    不需要任何循环。这是接口设计（省流量），不是数据质量问题。
    """
    payload = json.loads(path.read_text(encoding="utf-8"))
    daily = payload["daily"]

    df = pd.DataFrame({dst: daily[src] for src, dst in FIELD_MAP.items()})

    # date_key 必须是 date，不是 datetime64：
    # 库里是 date 类型；留 timestamp 会带出时间部分、JOIN 要 cast、语义也错
    # 注意：pd.to_datetime(列表) 返回的是 DatetimeIndex，它没有 .dt（.dt 只属于 Series）
    #       所以这里直接取 .date，得到一串 datetime.date 对象
    df["date_key"] = pd.to_datetime(daily["time"]).date
    df["city_id"] = city_id
    return df


def transform(raw_dir: Path = RAW_DIR,
              start: str = "2026-09-01",
              end: str = "2026-11-14") -> pd.DataFrame:
    """8 个 JSON → 一张 600 行的长表，并补 3 个派生列。"""
    frames = []
    for city_id in CITIES:                      # 用配置里的顺序，保证输出稳定
        path = raw_dir / f"{city_id}_{start}_{end}.json"
        if not path.exists():
            raise FileNotFoundError(f"缺少抽取结果：{path}，先跑 python -m src.extract")
        frames.append(parse_one(path, city_id))

    df = pd.concat(frames, ignore_index=True)

    # 8 个数值列统一转成数字；errors="coerce" 让脏值变 NaN 而不是让脚本崩
    num_cols = list(FIELD_MAP.values())
    for col in num_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # 派生列：只看本行
    df["temp_range_c"] = (df["tmax_c"] - df["tmin_c"]).round(1)
    df["feels_like_c"] = ((df["app_max_c"] + df["app_min_c"]) / 2).round(1)
    df["is_precip"] = df["precip_mm"] >= PRECIP_THRESHOLD_MM

    # 列定序 + 排序：先按城市、再按日期，输出才可复现（不然 concat 顺序靠运气）
    df = df[COLS].sort_values(["city_id", "date_key"]).reset_index(drop=True)
    return df


def validate(df: pd.DataFrame, start: str, end: str) -> list[dict]:
    """6 条入库前校验。只读，不改 df。返回 [{"ok": bool, "check": str}, ...]"""
    expected_days = (date.fromisoformat(end) - date.fromisoformat(start)).days + 1
    n_city = df["city_id"].nunique()

    checks = [
        # 只抓「整体」少几天；单城少一天抓不到（nunique 仍是对的），下一行才管这个
        ("日期覆盖 = 请求区间",
         df["date_key"].min() == date.fromisoformat(start)
         and df["date_key"].max() == date.fromisoformat(end)
         and df["date_key"].nunique() == expected_days),

        ("行数 = 城市数 x 天数", len(df) == expected_days * n_city),

        ("主键 (city_id, date_key) 无重复",
         not df.duplicated(["city_id", "date_key"]).any()),

        ("温度无缺失",
         df[["tmax_c", "tmin_c", "tmean_c"]].notna().all().all()),

        ("tmax >= tmin", bool((df["tmax_c"] >= df["tmin_c"]).all())),

        ("降水与风速非负",
         bool((df["precip_mm"] >= 0).all()
              and (df["precip_h"] >= 0).all()
              and (df["wind_max_kmh"] >= 0).all())),
    ]
    return [{"ok": bool(ok), "check": name} for name, ok in checks]


def main(start: str, end: str) -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)-5s %(message)s",
                        datefmt="%H:%M:%S")

    df = transform(RAW_DIR, start, end)
    print(f"({len(df)}, {len(df.columns)})",
          df["city_id"].nunique(), df["date_key"].min(), df["date_key"].max())

    results = validate(df, start, end)
    for r in results:
        print(("OK   " if r["ok"] else "FAIL ") + r["check"])

    print(df.head(3).to_string(index=False))
    return 0 if all(r["ok"] for r in results) else 1


if __name__ == "__main__":
    # 用法：python -m src.transform 2026-09-01 2026-11-14
    s = sys.argv[1] if len(sys.argv) > 2 else "2026-09-01"
    e = sys.argv[2] if len(sys.argv) > 2 else "2026-11-14"
    raise SystemExit(main(s, e))
