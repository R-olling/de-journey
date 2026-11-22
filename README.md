# de-journey

数据工程学习仓库，五个单元一条线：**week0** Python 最小可用集（三个 ≤30 行脚本，只用标准库）→ **week1** 把 31,801 行脏表洗成 31,502 行并用 7 个 KPI 证明口径没错 → **week2** 同一份数据搬进 PostgreSQL（4 张表 + 窗口函数）→ **week3** 一条可重跑的天气管道（600 行，重跑不变）→ **week4** 让它每天 07:00 自己跑（14 条校验 + 三层防线 + 5 条 ADR）。

## 单元一览

| 单元 | 产出 | 硬判据 | 从哪读 |
|---|---|---|---|
| **week0** | 3 个标准库脚本（温度表 / CSV 统计 / JSON 配置） | `mean=16.76` | 本页「文件明细」 |
| **week1** | 31,801 → 31,502 行事实表 + 7 KPI | `on_time_rate=0.619 miss_rate=0.381 median_hours=72.258` | `week1/answers.md` |
| **week2** | PostgreSQL 4 张表 + 7 KPI 与 pandas 逐位一致 | `31502 / 10972 / 0.348 / 0.619 / 4.199` | `week2/NOTES.md` |
| **week3** | open-meteo 8 城 × 75 天 → 600 行，upsert 幂等 | 同区间跑两次 `fact_total` 都是 **600** | `week3/README.md` |
| **week4** | 07:00 调度 + 14 条校验 + 三层防线 + `ops` 记账 | `exit 0`、`fact_total=656`、`LastTaskResult=0x0` | `week4/NOTES.md` |

> 两个 tag 是交付快照：`v0.3-pipeline`（600 行管道）、`v0.4-ops`（每日调度与双防线）。`git show v0.4-ops --stat` 能一次看完单元 4 改了什么。

## 文件明细（week0 / week1）

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

## 快速开始（week1 · 清洗链，Windows PowerShell）

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

## week2 · SQL 层（4 张表 + 7 KPI + 窗口函数）

`week2/sql/` 四个脚本按顺序跑在 `meridia` 库上：`init`（重建 4 张表 + 维表）→ `load`（stg → fact）→ `metrics`（7 KPI）→ `analytics`（排名三兄弟）。

```powershell
docker start pg_meridia
docker cp week1\data\clean\dim_district.csv   pg_meridia:/tmp/districts.csv
docker cp week1\data\clean\fact_requests.csv  pg_meridia:/tmp/fact_requests.csv

docker cp week2\sql\init.sql pg_meridia:/tmp/init.sql
docker exec pg_meridia psql -U postgres -d meridia -v ON_ERROR_STOP=1 -f /tmp/init.sql
# 期望：4× CREATE TABLE / 2× CREATE INDEX / COPY 12 / INSERT 0 731

docker cp week2\sql\load.sql pg_meridia:/tmp/load.sql
docker exec pg_meridia psql -U postgres -d meridia -v ON_ERROR_STOP=1 -f /tmp/load.sql
# 期望：COPY 31502 / INSERT 0 31502（重跑一次仍是 31502）

docker cp week2\sql\metrics.sql pg_meridia:/tmp/metrics.sql
docker exec pg_meridia psql -U postgres -d meridia -f /tmp/metrics.sql
# 期望：7 KPI 与 pandas 逐位一致
```

判据、卡点（容器名冲突 / `COPY` 路径只能用正斜杠 / `psql -d` 真的会连库）与降级说明见 `week2/NOTES.md`。

## week3 · 第一条可重跑的管道

`week3/` 把 open-meteo 的 8 城 × 75 天天气抽到 PostgreSQL：一条命令 600 行，重跑仍是 600。

```powershell
docker start pg_meridia
cd week3
python run.py --start 2026-09-01 --end 2026-11-14
# 期望：check ×6 OK / transform rows=600 / load stg=600 fact_total=600
```

架构图、六条命令、三个取舍与已知限制见 `week3/README.md`；列定义见 `week3/DATA_DICTIONARY.md`。

## week4 · 让它每天自己跑

`week4/` 不新增功能，只加运维一层：调度、14 条校验、三层防线、文档。

```powershell
docker start pg_meridia
docker cp week4\sql\ops.sql pg_meridia:/tmp/ops.sql
docker exec pg_meridia psql -U postgres -d weather -v ON_ERROR_STOP=1 -f /tmp/ops.sql
python week4\run_daily.py --start 2026-09-01 --end 2026-11-14 --reuse-raw  # 首次回填：600 行
python week4\run_daily.py --reuse-raw                                      # 每日窗口：656 行
cd week4\scripts; .\register_task.ps1 -Time 07:00 -RunNow                  # 每天 07:00 + 立刻验证一次
```

（Git Bash 里 `/tmp/ops.sql` 会被改写成 Windows 路径，要写 `//tmp/ops.sql`。）

**空库必须先回填**：每日窗口只跑 7 天（56 行），656 = 600 行的历史 + 56 行的当日窗口。跳过回填会看到 `fact_total=56`，那不是 bug。

退出码 `0/1/2/3` = 成功 / 数据质量 / 环境 / 上游；设计与取舍见 `week4/decisions.md`，契约见 `week4/DATA_CONTRACT.md`，事故演练见 `week4/INCIDENT-2026-11-22.md`。

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

### week2–week4

- **week2**：4 张表、`ON CONFLICT` 幂等、7 KPI 对账 → `week2/NOTES.md`
- **week3**：raw 存响应原文 / stg 全可空 + 每次 TRUNCATE / 手写 upsert 不用 `to_sql` → `week3/README.md`「三个取舍」
- **week4**：7 天滚动窗口、计划任务不上 Airflow 等 **5 条 ADR**（每条都有"什么时候推翻"）→ `week4/decisions.md`

## 环境备注

Python 3.13.16。本仓库锁的是 **pandas 3.1.1 / pyarrow 26.0.1**，课程答案键基于 3.0.6 / 25.0.1；已实测 shape、缺失率、dtypes、CSV 统计、7 个 KPI 全部一致，版本差异不影响判据，故不降级。详见 `week1/NOTES.md`。

单元 2–4 另外需要：**Docker Desktop**（容器 `pg_meridia`，PostgreSQL 16.15，库 `meridia` 与 `weather`）、psycopg 3.3.9、requests 2.34.2、python-dotenv 1.2.4；单元 4 的调度用 Windows 自带的「任务计划程序」，不需要额外装东西。
