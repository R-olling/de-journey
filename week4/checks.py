"""数据质量校验：pre（入库前）与 post（入库后）。

两道防线分工：
- pre  在写库之前看「这一批数据本身」，不过就不写 —— 挡住"错的数据进去"；
- post 在写库之后看「库里的事实」，不过就告警 —— 挡住"库里的状态慢慢变坏"。

两者不能互相替代：pre 看不到历史（行数突变要靠 post），
post 看到的是已经落库的数据（拦不住写入）。

用法：
    python week4\\checks.py --stage post --start 2026-11-15 --end 2026-11-21
    python week4\\checks.py --stage pre  --start 2026-11-15 --end 2026-11-21
    python week4\\checks.py --stage both --start 2026-11-15 --end 2026-11-21 --rows-loaded 56

退出码：0 全部通过 / 1 有校验失败 / 2 环境或配置问题
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path
from statistics import median

import psycopg
from dotenv import load_dotenv

# 复用 week3 的模块：transform.validate 的 6 条 + 连接参数
ROOT = Path(__file__).resolve().parent
WEEK3 = ROOT.parent / "week3"
sys.path.insert(0, str(WEEK3))

from src import load as w3load  # noqa: E402
from src import transform as w3transform  # noqa: E402

# ---- 阈值：全部是可解释的业务常量，不是拍脑袋的数字 ------------------------
TEMP_MIN, TEMP_MAX = -50.0, 60.0      # 地球上有人居住地区的日极值域，超出必是数据错
PRECIP_MAX_MM = 300.0                 # 单日 300mm 已是特大暴雨量级
WIND_MAX_KMH = 250.0                  # 超强台风上限
PRECIP_H_MAX = 24.0                   # 一天只有 24 小时
NULL_RATE_MAX = 0.01                  # 关键列空值率 1%
ROW_SWING_MAX = 0.50                  # 每城每天行数偏离中位数 50% 就告警
FRESHNESS_LAG_DAYS = 2                # 库里的最新日期距今不得超过 2 天
HISTORY_MIN_RUNS = 3                  # 历史不足 3 次不做突变判定（SKIP，不判失败）
HISTORY_WINDOW = 5


def _q1(conn: psycopg.Connection, sql: str, params: tuple = ()) -> object:
    row = conn.execute(sql, params).fetchone()
    return row[0] if row else None


# ---- pre：入库前 -------------------------------------------------------------
def pre_checks(df, start: str, end: str, dim_min: date, dim_max: date) -> list[dict]:
    """8 条：week3 的 6 条 + 温度值域 + 日历维覆盖。

    返回值固定为 [{"stage","check","ok","detail"}]，方便日志、入库、渲染共用。
    """
    results = [
        {"stage": "pre", "check": c["check"], "ok": bool(c["ok"]), "detail": ""}
        for c in w3transform.validate(df, start, end)
    ]

    temp_cols = ["tmax_c", "tmin_c", "tmean_c", "app_max_c", "app_min_c"]
    lo = float(df[temp_cols].min().min())
    hi = float(df[temp_cols].max().max())
    results.append({
        "stage": "pre",
        "check": f"温度值域 [{TEMP_MIN:g}, {TEMP_MAX:g}]",
        "ok": TEMP_MIN <= lo and hi <= TEMP_MAX,
        "detail": f"min={lo:.1f} max={hi:.1f}",
    })

    s, e = date.fromisoformat(start), date.fromisoformat(end)
    results.append({
        "stage": "pre",
        "check": "窗口在 dim_date 覆盖内",
        "ok": dim_min <= s and e <= dim_max,
        "detail": f"窗口 {s}~{e}，日历 {dim_min}~{dim_max}",
    })
    return results


# ---- post：入库后 ------------------------------------------------------------
def post_checks(conn: psycopg.Connection, start: str, end: str,
                rows_loaded: int | None = None,
                history: list[tuple[int, int]] | None = None) -> list[dict]:
    """6 条：新鲜度 / 覆盖率 / 重复键 / 空值率 / 值域 / 行数突变。

    history 是 [(rows_loaded, days), ...]，用于「每城每天行数」的突变判定。
    """
    s, e = date.fromisoformat(start), date.fromisoformat(end)
    days = (e - s).days + 1
    city_n = int(_q1(conn, "SELECT count(*) FROM mart.dim_city"))
    res: list[dict] = []

    # 1. 新鲜度：库里最新日期距今不能太远
    max_d = _q1(conn, "SELECT max(date_key) FROM mart.fact_weather_daily")
    lag = (date.today() - max_d).days if max_d else 999
    res.append({"stage": "post", "check": "新鲜度（最新日期距今）",
                "ok": lag <= FRESHNESS_LAG_DAYS,
                "detail": f"max(date_key)={max_d}，滞后 {lag} 天（阈值 {FRESHNESS_LAG_DAYS}）"})

    # 2. 覆盖率：窗口内每个城市都应有 days 天
    full = int(_q1(conn, """
        SELECT count(*) FROM (
            SELECT city_id FROM mart.fact_weather_daily
            WHERE date_key BETWEEN %s AND %s
            GROUP BY city_id HAVING count(*) = %s) t""", (s, e, days)))
    res.append({"stage": "post", "check": "窗口覆盖率（城 × 天）",
                "ok": full == city_n,
                "detail": f"{full}/{city_n} 城 × {days} 天 = {full * days} 行"})

    # 3. 重复键：主键唯一性（upsert 的理论保证，实测兜底）
    dup = int(_q1(conn, """
        SELECT count(*) - count(DISTINCT (city_id, date_key))
        FROM mart.fact_weather_daily"""))
    res.append({"stage": "post", "check": "主键无重复", "ok": dup == 0, "detail": f"重复 {dup} 行"})

    # 4. 空值率：关键列
    null_rate = float(_q1(conn, """
        SELECT count(*) FILTER (
                   WHERE tmax_c IS NULL OR tmin_c IS NULL
                      OR tmean_c IS NULL OR precip_mm IS NULL)::float
               / greatest(count(*), 1)
        FROM mart.fact_weather_daily"""))
    res.append({"stage": "post", "check": f"关键列空值率 <= {NULL_RATE_MAX:.0%}",
                "ok": null_rate <= NULL_RATE_MAX, "detail": f"空值率 {null_rate:.2%}"})

    # 5. 值域：库里已有的坏值（999 这种能绕过表级 CHECK 的值）
    bad = int(_q1(conn, """
        SELECT count(*) FROM mart.fact_weather_daily
        WHERE tmax_c NOT BETWEEN %s AND %s OR tmin_c NOT BETWEEN %s AND %s
           OR tmean_c NOT BETWEEN %s AND %s
           OR precip_mm < 0 OR precip_mm > %s
           OR precip_h  < 0 OR precip_h  > %s
           OR wind_max_kmh < 0 OR wind_max_kmh > %s""",
                  (TEMP_MIN, TEMP_MAX, TEMP_MIN, TEMP_MAX, TEMP_MIN, TEMP_MAX,
                   PRECIP_MAX_MM, PRECIP_H_MAX, WIND_MAX_KMH)))
    res.append({"stage": "post", "check": "值域（库内越界行数）",
                "ok": bad == 0, "detail": f"越界 {bad} 行"})

    # 6. 行数突变：比「每城每天行数」，不是比总行数
    if rows_loaded is None:
        res.append({"stage": "post", "check": "行数突变", "ok": True,
                    "detail": "SKIP：未提供本次行数"})
    elif not history or len(history) < HISTORY_MIN_RUNS:
        res.append({"stage": "post", "check": "行数突变", "ok": True,
                    "detail": f"SKIP：历史仅 {len(history or [])} 次（需 {HISTORY_MIN_RUNS} 次）"})
    else:
        per_day = [rows / d for rows, d in history if d]
        base = median(per_day)
        cur = rows_loaded / days
        dev = abs(cur - base) / base if base else 0.0
        res.append({"stage": "post", "check": f"行数突变 <= {ROW_SWING_MAX:.0%}",
                    "ok": dev <= ROW_SWING_MAX,
                    "detail": f"本次 {cur:.1f} 行/天，历史中位数 {base:.1f}，偏离 {dev:.1%}"})
    return res


def run_history(conn: psycopg.Connection, exclude_run_id: int | None = None) -> list[tuple[int, int]]:
    """取最近几次 (行数, 天数)。拼 SQL 而不是写 `%s IS NULL`——
    后者会让 Postgres 报 `could not determine data type of parameter $1`（实测）。"""
    sql = """SELECT rows_loaded, (window_end - window_start) + 1 AS days
             FROM ops.pipeline_run
             WHERE rows_loaded IS NOT NULL"""
    params: list[object] = []
    if exclude_run_id is not None:
        sql += " AND run_id <> %s"
        params.append(exclude_run_id)
    sql += " ORDER BY run_id DESC LIMIT %s"
    params.append(HISTORY_WINDOW)
    rows = conn.execute(sql, params).fetchall()
    return [(int(r[0]), int(r[1])) for r in rows]


# ---- 输出与记账 --------------------------------------------------------------
def render(results: list[dict]) -> str:
    lines = []
    for r in results:
        flag = "OK  " if r["ok"] else "FAIL"
        lines.append(f"[{flag}] {r['stage']:<4} {r['check']:<28} {r['detail']}")
    failed = sum(1 for r in results if not r["ok"])
    lines.append(f"-- {len(results)} 条校验，{failed} 条失败")
    return "\n".join(lines)


def record(conn: psycopg.Connection, run_id: int, results: list[dict]) -> None:
    with conn.cursor() as cur:
        cur.executemany(
            """INSERT INTO ops.check_result (run_id, stage, check_name, ok, detail)
               VALUES (%s, %s, %s, %s, %s)""",
            [(run_id, r["stage"], r["check"], r["ok"], r["detail"]) for r in results])
    conn.commit()


def connect() -> psycopg.Connection:
    load_dotenv(WEEK3 / ".env")
    return w3load.connect()


def main() -> int:
    ap = argparse.ArgumentParser(description="weather-pipeline 数据质量校验")
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--stage", choices=["pre", "post", "both"], default="both")
    ap.add_argument("--rows-loaded", type=int, default=None)
    ap.add_argument("--run-id", type=int, default=None, help="给了才写 ops.check_result")
    args = ap.parse_args()

    try:
        conn = connect()
    except psycopg.OperationalError as exc:
        print(f"[ERR] 连不上库：{exc}", file=sys.stderr)
        return 2

    results: list[dict] = []
    try:
        if args.stage in ("pre", "both"):
            df = w3transform.transform(w3transform.RAW_DIR, args.start, args.end)
            dim_min, dim_max = conn.execute(
                "SELECT min(date_key), max(date_key) FROM mart.dim_date").fetchone()
            results += pre_checks(df, args.start, args.end, dim_min, dim_max)
        if args.stage in ("post", "both"):
            hist = run_history(conn, args.run_id)
            results += post_checks(conn, args.start, args.end, args.rows_loaded, hist)
        # 记账要在关连接之前（psycopg3 的 `with conn:` 会关连接，这里不用它）
        if args.run_id is not None:
            record(conn, args.run_id, results)
    finally:
        conn.close()

    print(render(results))
    failed = [r for r in results if not r["ok"]]
    for r in failed:
        print(f"ALERT {r['stage']} {r['check']}: {r['detail']}", file=sys.stderr)
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
