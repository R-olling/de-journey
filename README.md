# de-journey

数据工程实习冲刺仓库。`week0/` 是 Python 最小可用集练习：三个 ≤30 行的脚本，只用标准库，不装任何第三方包。

| 脚本 | 用途 |
|---|---|
| `week0/temp_table.py` | -40~100°F 转摄氏，双列右对齐（顺带输出 cold/mild/hot 等级） |
| `week0/csv_stats.py` | 读 `week0/data/temps.csv`，算行数/均值/最大/最小 |
| `week0/config_json.py` | 读 JSON → 改端口/加城市/打时间戳 → 写回 → 读回校验 |
| `week0/retest_csv.py` | 盲写测试留证：2026-11-01，14 分 20 秒，未查笔记 |

## 快速开始（Windows PowerShell）

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python week0\temp_table.py
python week0\csv_stats.py
python week0\config_json.py
```

环境：Python 3.13.16（本项目实测）。**不需要 `pip install`**，标准库够用。

## 设计取舍

- **只用标准库**：这一周练的是「在终端里跑脚本」，不是调包。pandas 从第 1 单元开始。
- **路径一律 `pathlib`**：`Path(__file__).parent / "data" / "temps.csv"`，从任何目录调用都能找到数据，不依赖当前工作目录。
- **编码一律 `encoding="utf-8"`**；`csv` 额外带 `newline=""`（Windows 上不加会读出空行）。
- **`config_json.py` 是幂等的**：连跑两次，`cities` 里不会出现两个 `paris`——这是「同一输入跑两次结果一致」的第一次实践。
