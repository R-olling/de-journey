# week3 · 第一条可重跑的管道

一句话：open-meteo → 8 城 × 75 天 → PostgreSQL，一条命令 600 行，重跑不变。

## 架构

```text
open-meteo archive API
        │  8 次请求（一城一次，不是一天一次）
        ▼
   data/raw/*.json          原文落盘，一个字节都不改 —— 可重放
        │  transform：列式 9 数组 × 75 天 → 行式 600 × 13
        ▼
   stg.weather_daily        全列可空、零约束，每次 TRUNCATE —— 缓冲区
        │  INSERT ... ON CONFLICT (city_id, date_key) DO UPDATE
        ▼
   mart.fact_weather_daily  13 列 + PK + 2 FK + 5 CHECK —— 600 行
        ▲
   mart.dim_city (8)        mart.dim_date (365)
```

## 快速开始（六条命令）

```powershell
cd D:\code\de-journey\week3

# 1) 起容器
docker start pg_meridia

# 2) 建库（只需一次）
docker exec pg_meridia psql -U postgres -c "CREATE DATABASE weather;"

# 3) 建表（DROP + CREATE，可反复跑）
docker cp sql\init.sql pg_meridia:/tmp/init_weather.sql
docker exec pg_meridia psql -U postgres -d weather -v ON_ERROR_STOP=1 -f /tmp/init_weather.sql
# 期望：CREATE SCHEMA ×2 / CREATE TABLE ×4 / CREATE INDEX ×1 / INSERT 0 8 / INSERT 0 365

# 4) 装依赖
python -m pip install -r ..\requirements.txt

# 5) 跑管道（先复制 .env.example 成 .env 并填 PG_PASSWORD）
python run.py --start 2026-09-01 --end 2026-11-14
# 期望：check ×6 OK / transform rows=600 / load stg=600 fact_total=600

# 6) 跑指标
docker cp sql\metrics.sql pg_meridia:/tmp/metrics.sql
docker exec pg_meridia psql -U postgres -d weather -f /tmp/metrics.sql
# 期望：S1 8 行 / S2 4 行 / S3 8 行 / S4 600|8|75|0
```

**幂等自证**：第 5 条再跑一遍（加 `--reuse-raw` 更快），`fact_total` 仍是 600。

## 指标（三条 + 一句结论）

| # | 业务问题 | 结论 |
|---|---|---|
| S1 | 最近 7 天哪个城市昼夜温差最大 | 北京 10.30°C，是武汉（4.86°C）的 2.1 倍——北方秋季昼夜温差大，**不是数据有问题** |
| S2 | 11 月以来谁连续 ≥3 天真在下雨（≥1mm） | 4 个城市；里昂最长（11/10–11/13，4 天）。**注意是"连续"不是"累计"** |
| S3 | 10 月比 9 月冷了多少 | 8 城全部变冷，北京 -8.69°C 最多、成都 -3.99°C 最少。方向一致、幅度不同 |
| S4 | 对账 | 600 / 8 / 75 / 0，日期范围正好是请求区间 |

## 三个取舍

1. **raw 存响应原文，不存清洗结果**
   不这样做：排错时回不到原文，接口字段一变就无法重放，抽取与清洗被绑死在同一层。
2. **stg 全列可空 + 每次 TRUNCATE**
   不这样做：落地层装不下脏数据，一行坏数据就让整批失败；不清空则行数累加，第二次跑会看到 `stg=1200` 而怀疑自己写重复了。
3. **psycopg 手写 upsert，不用 `df.to_sql()`**
   不这样做：`to_sql` 对非 SQLite 只支持 SQLAlchemy 引擎；且 `DO UPDATE` 更新哪 11 列、`NaN→NULL` 怎么转，都在别人代码里，出问题查不到。

## 每日运行与排错（单元 4 加的）

这条管道现在由 `week4/run_daily.py` 每天跑，本目录的 `run.py` 降级为"手动全量/回填"入口。

```powershell
# 一次性：建运维表（幂等，可反复跑）
docker cp week4\sql\ops.sql pg_meridia:/tmp/ops.sql
docker exec pg_meridia psql -U postgres -d weather -v ON_ERROR_STOP=1 -f /tmp/ops.sql

# 一次性（空库才需要）：回填 9/1–11/14 的 600 行基线
python week4\run_daily.py --start 2026-09-01 --end 2026-11-14 --reuse-raw

# 注册每天 07:00（窗口 = 昨天往前 7 天；-RunNow 会立刻触发一次做验证）
cd week4\scripts; .\register_task.ps1 -Time 07:00

# 手动跑一次（等价于 07:00 那次；--reuse-raw 不联网重放本地 raw）
python week4\run_daily.py

# 看结果
docker exec pg_meridia psql -U postgres -d weather -c "select * from ops.v_last_runs;"
docker exec pg_meridia psql -U postgres -d weather -c "select * from ops.v_open_alerts;"
```

> **空库为什么先回填**：每日窗口只覆盖 7 天（56 行）。656 = 600 行历史 + 56 行窗口；不回填会看到 `fact_total=56`。
> Git Bash 里 `/tmp/ops.sql` 会被改写成 Windows 路径，要写 `//tmp/ops.sql`。

**退出码**：`0` 成功 ｜ `1` 数据质量 ｜ `2` 环境（Docker/.env/连不上库）｜ `3` 上游（HTTP 4xx/5xx）。
计划任务的 `LastTaskResult` 不是 `0x0` 就是失败——**别用"去看看日志"代替看退出码**，那正是 07:00 无人值守时没人做的事。

**三条排查命令（按顺序）**：

1. `(Get-ScheduledTaskInfo -TaskName de-journey-weather-daily).LastTaskResult` —— 跑没跑、成没成（`0x41303` = 从未运行，不是错误）；
2. `Get-ChildItem week4\logs -Filter daily-*.log | Sort-Object LastWriteTime -Descending | Select -First 1` —— 最后一次的完整过程；
3. `select * from ops.v_open_alerts;` —— 哪条校验没过、具体数值。

> 为什么要写退出码而不是"命令怎么跑"：命令只在你记得的时候有用，退出码是**无人值守时的唯一信号**。

## 已知限制

- **调度依赖"用户已登录 + Docker Desktop 已起"**：07:00 关机/注销不会跑；`StartWhenAvailable` 只补"错过的触发"，不补"跑失败了"（无重试）。
- **600 行用 `executemany`**：到 600 万行要换 `COPY`，upsert 会产生表膨胀，指标查询要加索引。
- **`date_key` 是城市本地日**（`timezone=auto`）：跨城比较"同一天"时，中法两地差 6–7 小时，含义不同。
- **指标 SQL 里阈值仍是字面量 1.0**：`transform.py` 有 `PRECIP_THRESHOLD_MM` 常量，但 `metrics.sql` 是独立文件，改口径要两边同时改（单元 4 用参数化 SQL 收口）。
