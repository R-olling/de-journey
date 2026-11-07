# 用途：Meridia 服务请求的清洗与派生——单元 1 唯一可复用模块，单元 2 直接吃它产出的 parquet
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parent
RAW = ROOT / "data" / "raw"
CLEAN = ROOT / "data" / "clean"

# 原始数据里同一个服务有三种写法，共 636 行；不修就会在 merge 时凭空消失
CAT_MAP = {
    "Waste Collection": "waste_collection",
    "street light": "streetlight",
    "Streetlight": "streetlight",
}

REQ_COLS = ["request_id", "created_at", "closed_at", "status", "district_id", "channel",
            "category", "priority", "department", "target_hours", "citizen_rating"]
DIST_COLS = ["district_id", "district_name", "area_km2", "population_2025"]


def load(raw: Path = RAW) -> tuple[pd.DataFrame, pd.DataFrame]:
    """读原始 CSV。两个日期列在读入时解析，后面才用得上 .dt。"""
    req = pd.read_csv(raw / "service_requests.csv", usecols=REQ_COLS,
                      parse_dates=["created_at", "closed_at"])
    dist = pd.read_csv(raw / "districts.csv", usecols=DIST_COLS)
    return req, dist


def derive(df: pd.DataFrame) -> pd.DataFrame:
    """只加列、不删行：派生列与标签规范化。口径变化不在这里做。"""
    out = df.copy()
    out["cat"] = out["category"].replace(CAT_MAP)
    out["hours"] = (out["closed_at"] - out["created_at"]).dt.total_seconds() / 3600
    out["sla_ratio"] = out["hours"] / out["target_hours"]
    out["missed"] = out["sla_ratio"] > 1
    out["month"] = out["created_at"].dt.to_period("M").astype(str)
    return out


def clean(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """只删行，并留下可审计的日志：31801 → 31502 的每一步都要能解释。"""
    d = derive(df)
    steps = [("原始", len(d))]
    d = d[d["status"].eq("closed")]
    steps.append(("只留已结单", len(d)))
    d = d[d["hours"] >= 0]
    steps.append(("剔除负时长", len(d)))
    log = pd.DataFrame(steps, columns=["step", "rows"])
    log["dropped"] = log["rows"].shift(1).fillna(log["rows"]).astype(int) - log["rows"]
    return d.reset_index(drop=True), log


def save(d: pd.DataFrame, dist: pd.DataFrame, out: Path = CLEAN) -> None:
    """两种格式各存一份：parquet 给下游，csv 给 PostgreSQL COPY 和人看。"""
    out.mkdir(parents=True, exist_ok=True)
    fact = d[["request_id", "created_at", "closed_at", "district_id", "channel", "cat",
              "priority", "department", "target_hours", "hours", "sla_ratio", "missed",
              "citizen_rating", "month"]]
    fact.to_parquet(out / "fact_requests.parquet", index=False)
    fact.to_csv(out / "fact_requests.csv", index=False)
    dist.to_parquet(out / "dim_district.parquet", index=False)


if __name__ == "__main__":
    req, dist = load()
    fact, log = clean(req)
    print(log.to_string(index=False))
    # 七个 KPI 一行打全，直接对照执行计划 §3.2 的表
    print(f"n_requests={len(fact)} n_rated={int(fact['citizen_rating'].notna().sum())} "
          f"response_rate={fact['citizen_rating'].notna().mean():.3f} "
          f"on_time_rate={1 - fact['missed'].mean():.3f} "
          f"miss_rate={fact['missed'].mean():.3f} "
          f"median_hours={fact['hours'].median():.3f} "
          f"mean_rating={fact['citizen_rating'].mean():.3f}")
    save(fact, dist)
