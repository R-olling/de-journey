# 用途：读config.json → 改端口/加城市/打时间戳 → 写回 → 读回校验
import json
from datetime import datetime
from pathlib import Path

CFG = Path(__file__).parent / "data" / "config.json"

def main() -> None :
    with open(CFG,encoding="utf-8") as f:
        cfg = json.load(f)

    cfg["db"]["port"] = 5433
    if "paris" not in cfg["cities"]:
        cfg["cities"].append("paris")
    cfg["updated_at"] = datetime.now().isoformat(timespec="seconds")

    with open(CFG,"w",encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

    with open(CFG,encoding="utf-8") as f:
        back = json.load(f)
    assert back == cfg,"round-trip 不一致"
    print(f"roundtrip ok: {back['project']} {back['db']['port']} {back['cities']}")

if __name__=="__main__":
    main()