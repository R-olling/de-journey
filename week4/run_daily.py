"""调度入口：计划任务每天跑的是这个文件，不是 run.py。

    python week4\\run_daily.py                       # 窗口 = 昨天往前 lookback 天
    python week4\\run_daily.py --lookback 3
    python week4\\run_daily.py --start 2026-11-15 --end 2026-11-21 --reuse-raw
    python week4\\run_daily.py --dry-run               # 只算窗口、做 preflight，不写库

为什么默认跑「昨天往前 7 天」而不是只跑昨天：
1. 日聚合当天不完整（当天的 max/min 还在变）→ 不碰今天；
2. 上游会回填/修订（迟到数据、观测站补传）→ 窗口越宽，漏数据越少；
3. upsert 是幂等的 → 重复跑 7 天不会重复计数，代价只是 8 次请求。
代价：每天多算 7 倍的行，用 --lookback 1 可以回到"只补昨天"。

退出码（调度器只认这个）：
    0  成功
    1  数据质量问题（pre 不过 = 没写库；post 不过 = 库里可能已有坏数据）
    2  环境问题（Docker 没起 / 库连不上 / .env 缺 / ops 表不存在）
    3  上游抽取失败（HTTP 4xx/5xx、超时重试耗尽）
"""

from __future__ import annotations

import argparse
import logging
import shutil
import subprocess
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
WEEK3 = ROOT.parent / "week3"
sys.path.insert(0, str(WEEK3))

from src import extract, load, transform  # noqa: E402

import checks  # noqa: E402

CONTAINER = "pg_meridia"
LOG_DIR = ROOT / "logs"
DEFAULT_LOOKBACK = 7
READY_TIMEOUT_S = 90


class EnvError(RuntimeError):
    """环境/配置问题 → 退出码 2。"""


def setup_logging() -> Path:
    LOG_DIR.mkdir(exist_ok=True)
    logfile = LOG_DIR / f"daily-{time.strftime('%Y%m%d-%H%M%S')}.log"
    handlers: list[logging.Handler] = [logging.FileHandler(logfile, encoding="utf-8")]
    # 计划任务里没有控制台，sys.stdout 可能不可用；文件句柄才是唯一可靠的出口
    if sys.stdout is not None:
        handlers.insert(0, logging.StreamHandler(sys.stdout))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-5s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=handlers,
    )
    return logfile


def preflight(log: logging.Logger) -> None:
    """Docker、容器、.env、ops 表 —— 四件事缺一件就退出 2，不要等到 psycopg 报错。"""
    if not shutil.which("docker"):
        raise EnvError("PATH 里找不到 docker（计划任务的环境变量和终端不一样）")

    try:
        subprocess.run(["docker", "info"], capture_output=True, timeout=20, check=True)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        raise EnvError("Docker daemon 没起：先手动启动 Docker Desktop，"
                       "或在设置里勾选 'Start Docker Desktop when you sign in'")

    ps = subprocess.run(["docker", "ps", "-a", "--filter", f"name={CONTAINER}",
                         "--format", "{{.Names}} {{.Status}}"],
                        capture_output=True, text=True, timeout=20)
    if CONTAINER not in ps.stdout:
        raise EnvError(f"容器 {CONTAINER} 不存在：先跑 week3 的 docker run")
    if "Up" not in ps.stdout:
        log.warning("容器是停的，自动启动：%s", ps.stdout.strip())
        subprocess.run(["docker", "start", CONTAINER], capture_output=True, timeout=60)

    deadline = time.time() + READY_TIMEOUT_S
    while time.time() < deadline:
        r = subprocess.run(["docker", "exec", CONTAINER, "pg_isready", "-U", "postgres"],
                           capture_output=True, text=True)
        if "accepting connections" in r.stdout:
            log.info("preflight: PostgreSQL ready（%.1fs）", READY_TIMEOUT_S - (deadline - time.time()))
            break
        time.sleep(2)
    else:
        raise EnvError(f"pg_isready 等了 {READY_TIMEOUT_S}s 仍未就绪")

    if not (WEEK3 / ".env").exists():
        raise EnvError(f"缺 {WEEK3 / '.env'}：从 .env.example 复制并填 PG_PASSWORD")

    log.info("preflight: docker / container / .env 全部就绪")


def window(lookback: int) -> tuple[str, str]:
    """默认窗口：[今天-lookback, 昨天]。不碰今天（日聚合不完整）。"""
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=lookback - 1)
    return start.isoformat(), end.isoformat()


def main() -> int:
    ap = argparse.ArgumentParser(description="weather-pipeline 每日调度入口")
    ap.add_argument("--start", help="YYYY-MM-DD；给了就别给 --lookback")
    ap.add_argument("--end", help="YYYY-MM-DD")
    ap.add_argument("--lookback", type=int, default=DEFAULT_LOOKBACK,
                    help=f"从昨天往前几天（默认 {DEFAULT_LOOKBACK}）")
    ap.add_argument("--reuse-raw", action="store_true", help="跳过抽取，重放本地 raw")
    ap.add_argument("--dry-run", action="store_true", help="只算窗口 + preflight，不跑管道")
    args = ap.parse_args()

    logfile = setup_logging()
    log = logging.getLogger("daily")

    if bool(args.start) != bool(args.end):
        log.error("--start 与 --end 必须成对出现")
        return 2
    start, end = (args.start, args.end) if args.start else window(args.lookback)

    log.info("run_daily start window=%s..%s lookback=%d reuse_raw=%s",
             start, end, args.lookback, args.reuse_raw)
    t0 = time.perf_counter()

    try:
        preflight(log)
        load_dotenv(WEEK3 / ".env")
        conn = load.connect()
    except (EnvError, psycopg.OperationalError) as exc:
        log.error("ENV %s", exc)
        return 2

    try:
        run_id = int(conn.execute(
            """INSERT INTO ops.pipeline_run (window_start, window_end, log_file)
               VALUES (%s, %s, %s) RETURNING run_id""",
            (start, end, logfile.name)).fetchone()[0])
        conn.commit()
    except psycopg.errors.UndefinedTable:
        log.error("ENV 缺 ops 表：先跑 week4/sql/ops.sql")
        conn.close()
        return 2

    log.info("ops.run_id=%d", run_id)
    exit_code = 0
    results: list[dict] = []
    rows_loaded = None

    try:
        if args.dry_run:
            log.info("dry-run：窗口 %s..%s，不写库", start, end)
            return 0

        if not args.reuse_raw:
            try:
                recs = extract.extract_all(start, end, extract.RAW_DIR)
                log.info("extract %d cities, %d bytes",
                         len(recs), sum(r["bytes"] for r in recs))
            except (RuntimeError, OSError) as exc:
                log.error("UPSTREAM %s", exc)
                exit_code = 3
                return exit_code

        df = transform.transform(extract.RAW_DIR, start, end)
        dim_min, dim_max = conn.execute(
            "SELECT min(date_key), max(date_key) FROM mart.dim_date").fetchone()
        results = checks.pre_checks(df, start, end, dim_min, dim_max)
        for r in results:
            log.info("pre  %-28s %s %s", r["check"], "OK" if r["ok"] else "FAIL", r["detail"])
        if any(not r["ok"] for r in results):
            log.error("PRE 校验失败：不写库（数据留在 data/raw，修好后 --reuse-raw 重放）")
            exit_code = 1
            return exit_code

        # 注意：psycopg3 的 `with conn:` 在退出时**关连接**（psycopg2 只提交）。
        # 这里不能包块，load.load() 自己 commit。
        counts = load.load(df, conn)
        total = load.count_fact(conn)
        rows_loaded = counts["fact_rows_affected"]
        log.info("load stg=%d fact_affected=%d fact_total=%d（affected 含 UPDATE，不是新增行数）",
                 counts["stg_rows"], rows_loaded, total)

        hist = checks.run_history(conn, run_id)
        post = checks.post_checks(conn, start, end, rows_loaded, hist)
        results += post
        for r in post:
            log.info("post %-28s %s %s", r["check"], "OK" if r["ok"] else "FAIL", r["detail"])
        if any(not r["ok"] for r in post):
            log.error("POST 校验失败：数据已入库，按 ops.v_open_alerts 处理")
            exit_code = 1
        return exit_code

    finally:
        dur = time.perf_counter() - t0
        if not conn.closed:
            try:
                conn.execute(
                    """UPDATE ops.pipeline_run
                       SET finished_at = now(), rows_loaded = %s,
                           exit_code = %s, duration_s = %s
                       WHERE run_id = %s""",
                    (rows_loaded, exit_code, round(dur, 2), run_id))
                if results:
                    checks.record(conn, run_id, results)
                conn.commit()
            except psycopg.Error:
                log.exception("记账失败（不影响退出码，但 ops 会缺这一行）")
            conn.close()
        log.info("done exit=%d in %.2fs | log=%s", exit_code, dur, logfile.name)


if __name__ == "__main__":
    raise SystemExit(main())
