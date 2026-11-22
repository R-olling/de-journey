"""入口：一条命令串起 extract → transform → load。

用法：
    python run.py --start 2026-09-01 --end 2026-11-14
    python run.py --start 2026-11-15 --end 2026-11-15                  # 增量一天
    python run.py --start 2026-11-15 --end 2026-11-15 --reuse-raw      # 跳过抽取，重放本地 raw
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

from src import extract, load, transform

ROOT = Path(__file__).parent
RAW = ROOT / "data" / "raw"
LOG_DIR = ROOT / "logs"


def setup_logging() -> Path:
    """屏幕给人看，文件给调度看。两份同一格式，不引入第三方库。"""
    LOG_DIR.mkdir(exist_ok=True)
    logfile = LOG_DIR / f"run-{time.strftime('%Y%m%d-%H%M%S')}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-5s %(message)s",
        datefmt="%H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout),
                  logging.FileHandler(logfile, encoding="utf-8")],
    )
    return logfile


def main() -> int:
    ap = argparse.ArgumentParser(description="weather-pipeline: open-meteo → PostgreSQL")
    ap.add_argument("--start", required=True, help="YYYY-MM-DD")
    ap.add_argument("--end", required=True, help="YYYY-MM-DD")
    ap.add_argument("--reuse-raw", action="store_true",
                    help="跳过抽取，用 data/raw 里已有的文件")
    args = ap.parse_args()

    load_dotenv(ROOT / ".env")          # 必须在 connect() 之前
    logfile = setup_logging()
    log = logging.getLogger("run")
    t0 = time.perf_counter()
    log.info("run start %s .. %s (reuse_raw=%s)", args.start, args.end, args.reuse_raw)

    if not args.reuse_raw:
        extract.extract_all(args.start, args.end, RAW)

    df = transform.transform(RAW, args.start, args.end)
    checks = transform.validate(df, args.start, args.end)
    for c in checks:
        log.info("check %-28s %s", c["check"], "OK" if c["ok"] else "FAIL")

    # 校验不过就不写库，并返回非 0 —— 宁可今天不加载，也不要灌脏数据
    if not all(c["ok"] for c in checks):
        log.error("校验失败，终止加载（数据留在 data/raw，修复后 --reuse-raw 重放）")
        return 1

    with load.connect() as conn:
        counts = load.load(df, conn)
        total = load.count_fact(conn)

    log.info("transform rows=%d cities=%d dates=%d",
             len(df), df["city_id"].nunique(), df["date_key"].nunique())
    log.info("load stg=%d fact_affected=%d fact_total=%d",
             counts["stg_rows"], counts["fact_rows_affected"], total)
    log.info("done in %.2fs | log=%s", time.perf_counter() - t0, logfile.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
