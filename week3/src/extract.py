"""抽取层：open-meteo archive API → data/raw/<city>_<start>_<end>.json

设计约束（三条）：
1. 落盘的是响应原文，一个字节都不加工 —— 原始层要能重放；
2. 一个城市一次请求、按日期区间取，不是一天一请求 —— 8 城 × 75 天 = 8 次请求；
3. 超时、重试、状态码都必须显式处理 —— 失败要炸，不能静默返回空表。
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

import requests

log = logging.getLogger(__name__)

BASE = "https://archive-api.open-meteo.com/v1/archive"

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"

DAILY_FIELDS = (
    "temperature_2m_max,temperature_2m_min,temperature_2m_mean,"
    "apparent_temperature_max,apparent_temperature_min,"
    "precipitation_sum,precipitation_hours,wind_speed_10m_max"
)

# 城市清单是「配置」，不是代码：坐标只在这里出现一次
CITIES: dict[str, dict] = {
    "wuhan":     {"lat": 30.5928, "lon": 114.3055},
    "shanghai":  {"lat": 31.2304, "lon": 121.4737},
    "beijing":   {"lat": 39.9042, "lon": 116.4074},
    "chengdu":   {"lat": 30.5728, "lon": 104.0668},
    "paris":     {"lat": 48.8566, "lon":   2.3522},
    "lyon":      {"lat": 45.7640, "lon":   4.8357},
    "marseille": {"lat": 43.2965, "lon":   5.3698},
    "toulouse":  {"lat": 43.6047, "lon":   1.4442},
}

TIMEOUT = (5, 30)      # (连接超时, 读取超时)
MAX_RETRY = 3
BACKOFF = 2.0          # 退避基数（秒）


def _reason(resp: requests.Response) -> str:
    """open-meteo 把真正的原因放在 body 的 reason 里，不在状态码里。"""
    try:
        return str(resp.json().get("reason", ""))[:200]
    except ValueError:
        return resp.text[:200]


def fetch_city(city_id: str, lat: float, lon: float, start: str, end: str) -> bytes:
    """请求一个城市在 [start, end] 区间的日数据，返回响应原文字节。"""
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start,
        "end_date": end,
        "daily": DAILY_FIELDS,
        "timezone": "auto",
    }

    for attempt in range(1, MAX_RETRY + 1):
        try:
            r = requests.get(BASE, params=params, timeout=TIMEOUT)
        except requests.Timeout:
            log.warning("%s: timeout (第 %d 次)", city_id, attempt)
            if attempt == MAX_RETRY:
                raise
            time.sleep(BACKOFF * attempt)
            continue

        # 4xx 是调用方的错（参数不对），重试无用，立刻炸；原因要从 body 里解出来
        if 400 <= r.status_code < 500 and r.status_code != 429:
            raise RuntimeError(f"{city_id}: HTTP {r.status_code} {_reason(r)}")

        # 429 / 5xx 是对方暂时不可用，退避后重试
        if r.status_code == 429 or r.status_code >= 500:
            log.warning("%s: HTTP %d (第 %d 次)", city_id, r.status_code, attempt)
            if attempt == MAX_RETRY:
                raise RuntimeError(f"{city_id}: HTTP {r.status_code} {_reason(r)}")
            time.sleep(BACKOFF * attempt)
            continue

        r.raise_for_status()      # 其余 2xx/3xx 的兜底
        return r.content           # ← 原文字节，不加工

    raise RuntimeError(f"{city_id}: 重试 {MAX_RETRY} 次仍失败")


def save_city(city_id: str, content: bytes, start: str, end: str,
              raw_dir: Path = RAW_DIR) -> Path:
    """把响应原文落盘。纯 IO，不发网络请求，可以单独测。"""
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / f"{city_id}_{start}_{end}.json"
    path.write_bytes(content)      # ← 写字节，不是 write_text
    return path


def extract_all(start: str, end: str, raw_dir: Path = RAW_DIR) -> list[dict]:
    """遍历全部城市抽取并落盘，返回每城一条记录。

    这个函数**不配置 logging** —— 谁调用它谁负责配置（run.py 要同时写屏幕和文件，
    CLI 只要屏幕）。函数里一配置，调用方的设置就被覆盖了。
    """
    records = []
    for city_id, geo in CITIES.items():
        t0 = time.perf_counter()
        content = fetch_city(city_id, geo["lat"], geo["lon"], start, end)
        path = save_city(city_id, content, start, end, raw_dir)
        elapsed = time.perf_counter() - t0
        log.info(
            "extract %-10s %6d bytes %.2fs -> %s",
            city_id, len(content), elapsed, path.name,
        )
        records.append({"city_id": city_id, "path": path,
                        "bytes": len(content), "seconds": elapsed})
    return records


def main(start: str, end: str) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-5s %(message)s",
        datefmt="%H:%M:%S",
    )

    records = extract_all(start, end)
    total_bytes = sum(r["bytes"] for r in records)
    log.info("%d files, %d bytes", len(records), total_bytes)
    return 0


if __name__ == "__main__":
    # 用法：python -m src.extract 2026-09-01 2026-11-14
    if len(sys.argv) != 3:
        print("用法: python -m src.extract <start> <end>", file=sys.stderr)
        sys.exit(2)
    raise SystemExit(main(sys.argv[1], sys.argv[2]))
