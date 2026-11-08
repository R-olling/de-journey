# de-journey

数据工程学习仓库。`week0/` 是 Python 最小可用集练习（三个 ≤30 行脚本，只用标准库、不装第三方包）；`week1/` 把一张 31,801 行的真实脏表清洗成 31,502 行的事实表，并用 7 个 KPI 证明口径没错。

## 文件一览

| 文件 | 用途 |
|---|---|
| `week0/temp_table.py` | -40~100°F 转摄氏，双列右对齐（顺带输出 cold/mild/hot 等级） |
| `week0/csv_stats.py` | 读 `week0/data/temps.csv`，算行数/均值/最大/最小（标准库版） |
| `week0/config_json.py` | 读 JSON → 改端口/加城市/打时间戳 → 写回 → 读回校验 |
| `week0/retest_csv.py` | 盲写测试留证：2026-11-01，14 分 20 秒，未查笔记 |
| `week0/retest2.py` | 单元 1 门槛自检：`.txt` 盲写 CSV 统计，`mean=16.76` |
| `week1/rewrite_csv_stats.py` | 脚本 2 的 pandas 版：20 行 → 8 行，输出一字不差 |
| `week1/clean.py` | **本单元唯一可复用模块**：`load / derive / clean / save` 四函数 + 清洗日志 + 7 KPI 对账 |
| `week1/analysis.ipynb` | 六问的探索与实验记录（Run All 全绿） |
| `week1/answers.md` | 六问结论：每问一句话 + 一个数字；另附四条清洗口径 |
| `week1/quiz.py` | 11/8 闭卷小测（换数据集），9 行，4 题全对 |
| `week1/NOTES.md` | 卡点、时间预估修正、下一步改进 |
| `week1/data/raw/` | 三份原始 CSV：31,801×13 工单 / 12×8 区域 / 8×3 类别维表 |
| `week1/data/clean/` | 交付物：`fact_requests.parquet` / `.csv` / `dim_district.parquet` |

## 快速开始（Windows PowerShell）

```powershell
cd D:\code\de-journey
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt     # pandas 3.1.1 / pyarrow 26.0.1 / ipykernel 7.4.0

python week1\clean.py                          # ← 一条命令跑完整条清洗链
```

`week0` 的三个脚本不需要装包，`python week0\csv_stats.py` 直接能跑。

**期望输出**（这就是本单元的硬验收）：

```text
 step  rows  dropped
   原始 31801        0
只留已结单 31565      236
剔除负时长 31502       63
n_requests=31502 n_rated=10972 response_rate=0.348 on_time_rate=0.619
miss_rate=0.381 median_hours=72.258 mean_rating=4.199
```

想看六问是怎么推出来的，用 VS Code 打开 `week1/analysis.ipynb`，Kernel 选 **Python (de-journey .venv)**，然后 `Restart & Run All`。
（若列表里没有这个内核：`.venv\Scripts\python.exe -m ipykernel install --user --name de-journey --display-name "Python (de-journey .venv)"`，再 Reload Window。）

## 设计取舍

### week0

- **只用标准库**：这一周练的是「在终端里跑脚本」，不是调包。pandas 从第 1 单元开始。
- **路径一律 `pathlib`**：`Path(__file__).parent / "data" / "temps.csv"`，从任何目录调用都能找到数据，不依赖当前工作目录。
- **编码一律 `encoding="utf-8"`**；`csv` 额外带 `newline=""`（Windows 上不加会读出空行）。
- **`config_json.py` 是幂等的**：连跑两次，`cities` 里不会出现两个 `paris`——这是「同一输入跑两次结果一致」的第一次实践。

### week1

- **`derive` 只加列、`clean` 只删行**：加列写错会看到错的数，删行写错则那些数根本看不见，出错后果不同，所以拆成两个函数，对账时能一步定位。
- **四条清洗口径先定、再写实现**：只留已结单（删 236）、剔除负时长（删 63）、`citizen_rating` 缺失**保留 NaN 不填**、三个脏标签归一（636 行 → 8 个规范值）。详见 `week1/answers.md`。
- **236 行不该填、该删**：`closed_at` 为空就是未结单，没有结束时间算不出处理时长。
- **`citizen_rating` 一个 `fillna` 都没有**：中位数恰好是满分 5.0，用它填 20,809 个空洞会让均值 4.200 → 4.723、5 分评价 5,719 → 26,528，且零报错零警告。
- **3.5 MB 原始 CSV 入库是有意的**：真实项目该用对象存储或 LFS，但学习仓库优先保证「clone 下来就能复现」。
- **csv 与 parquet 两份都留**：csv 是交换格式（下周 `COPY` 灌 PostgreSQL、人也能打开），parquet 是存储格式（保 dtype、体积小 4.2 倍）。csv 读回 `closed_at` 会退化成 `str`，parquet 仍是 `datetime64[us]`。
- **合并必带 `validate="m:1"` 与 `indicator=True`**：前者防右表键重复导致行数爆炸（31,801 → 44,246），后者查键对不上导致的静默丢行（inner 31,801 → 31,165）。

## 环境备注

Python 3.13.16。本仓库锁的是 **pandas 3.1.1 / pyarrow 26.0.1**，课程答案键基于 3.0.6 / 25.0.1；已实测 shape、缺失率、dtypes、CSV 统计、7 个 KPI 全部一致，版本差异不影响判据，故不降级。详见 `week1/NOTES.md`。
