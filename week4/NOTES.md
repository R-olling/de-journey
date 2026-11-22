# week4 · 运维层笔记

> 计划：`单元4_执行计划_2026-11-23_11-30.md`（八天 / 630 min）。
> **实际：2026-11-22（日）15:31–16:0x 一次收口**，和单元 3 一样是压缩执行。
> 下面按计划里的八个 Block 记账，但日期统一记为实际执行日；**没做到的写在最前面，不藏在最后**。

## 0. 先说没做到的（诚实清单）

| 计划要求 | 现状 | 什么时候补 |
|---|---|---|
| **连续两天 07:00 自动成功**（11/25、11/26 各一份 `daily-*.log`） | **做不到**：任务在 11/22 注册，第一次自动运行是 **11/23 07:00**。今晚只能说"任务已被系统接受、手动触发过一次是 0x0" | 11/23、11/24 早上各自看一眼 `ops.v_last_runs`；到 11/24 就有两天整的证据 |
| PR #3 合并（网页操作） | 未做（本机无 `gh` CLI） | 网页 4 步，见 §4 的清单 |
| PR #4 创建与合并 | 分支已 push，PR 待建 | 同上 |
| 3 分钟讲解录音 | 脚本 v2 已有（`week4/PLAN` 里没有，见 `interview.md` 与计划 §12.3），**没录音** | 11/23 早上通勤前 5 分钟录一遍 |

## 1. 做了什么的账（按 Block）

### Block A · ops 表（计划 §2.1 C）

`week4/sql/ops.sql` → `CREATE SCHEMA / TABLE ×2 / INDEX ×2 / VIEW ×2`，`\dt ops.*` 看到 `check_result` / `pipeline_run`，`\dv ops.*` 看到 `v_last_runs` / `v_open_alerts`。

**踩到的坑（已写进计划 §5 坑 10）**：Git Bash 会把 `/tmp/ops.sql` 改写成 `D:/DevOps-MLOps/Temp/ops.sql`，`psql -f` 报 `No such file`。用 `//tmp/ops.sql` 或走 PowerShell。

### Block B · 窗口口径（计划 §2.1 B）

一句话：**每天跑 `[今天-7, 昨天]` 的 7 天窗口：不碰不完整的今天，用 7 天覆盖上游回填，靠 upsert 的幂等把"重跑"变成"修复"。**
`--lookback` 是成本旋钮：`1` 省 7 倍行数但回填窗口缩到 1 天，`30` 是月底补数。ADR-04 已定稿。

### Block C · 第一次跑出 656（计划 §2.1 C）

```text
extract 8 cities, 8091 bytes
pre ×8 全 OK（温度值域 min=-5.4 max=19.6）
load stg=56 fact_affected=56 fact_total=656
post ×6 全 OK（新鲜度滞后 1 天；覆盖率 8/8×7；越界 0；突变 SKIP：历史仅 0 次）
done exit=0 in 14.81s
ops.run_id=1
```

### Block D · 幂等（计划 §2.1 D）

`--reuse-raw` 再跑：`stg=56 fact_affected=56 fact_total=**656**`，`exit=0 in 0.85s`。
**记住的不是 656，是"没变"**：第一次 56 行是 INSERT，第二次 56 行是 UPDATE，`rowcount` 把两者算成同一个数——所以 `fact_affected` 不能当"新增行数"用。

### Block E · 计划任务（计划 §2.2）

```text
TaskName : de-journey-weather-daily
State    : Ready
NextRunTime : 2026/11/23 7:00:00
LastRunTime : 1999/11/30 0:00:00     ← "从未运行"占位值
LastResult  : 0x41303 (267011)       ← SCHED_S_TASK_HAS_NOT_RUN，不是错误
```

`Start-ScheduledTask` 之后：`LastResult=0x41301`（正在跑）→ 25 s 后 `0x0`，任务自己写出 `daily-20261122-153512.log`，内容 `load stg=56 fact_total=656 / done exit=0 in 29.92s`。
**这 25 秒值钱**：同时证明路径对、工作目录对、解释器对、日志能落盘。任务比手动慢，因为 `docker info` + `pg_isready` 在任务环境里要重连一次（29.92 s vs 14.81 s）。

### Block F · 环境失败演练（计划 §2.2 C）

`Rename-Item` 把 `.env` 藏起来 → 触发 → `LastResult = 0x2`，日志：

```text
ERROR ENV 缺 D:\code\de-journey\week3\.env：从 .env.example 复制并填 PG_PASSWORD
```

`.env` 已恢复。顺带发现：`Rename-Item week3\.env week3\.env.bak` 会报"目标表示路径或设备名称"，要用 `-LiteralPath` + 绝对路径。

### Block G · 三层防线（计划 §2.4）

1. **外键**：`('wuhan','2027-01-01')` → `violates foreign key constraint "fact_weather_daily_date_key_fkey"` / `Key (date_key)=(2027-01-01) is not present in table "dim_date"`。
2. **pre**：raw 里 11/15 的 `tmax` 改 999 → `pre 温度值域 FAIL min=-5.4 max=999.0` / exit 1 / **库仍 656、max 38.5**。
3. **post**：绕过 pre 用 `week3/run.py` → 999 入库（`bad=1, max=999.0`）→ `post 值域 FAIL 越界 1 行` / exit 1；带 `--run-id 4` 重跑 → `v_open_alerts` 2 条。
4. **修复**：恢复 raw + 重放 → `越界 0 行`、656、`max=38.5`。

详细时间线见 `INCIDENT-2026-11-22.md`。

### Block H · 四档退出码（计划 §7.1 第 7 条）

| 码 | 怎么演出来的 | 日志特征 |
|---|---|---|
| 0 | 正常窗口 | `done exit=0` |
| 1 | raw 改 999（pre）/ 绕过 pre 写库（post）/ `--rows-loaded 20`（突变 64.3%） | `PRE 校验失败` / `POST 校验失败` / `ALERT` |
| 2 | `.env` 改名 | `ERROR ENV ...` |
| 3 | `--start 2026-11-29`（未来日期） | `UPSTREAM wuhan: HTTP 400 Parameter 'start_date' is out of allowed range from 1940-01-01 to 2026-11-22` |

### Block I · 盲写 `load.py`（计划 §2.6 A）

`week4/rewrite_load.py`：`connect / to_rows / load / count_fact` 四个函数，断言 `before == after == 656`、`stg_rows == 56` 通过。
和 `week3/src/load.py` 相比 62 行新增 / 66 行删除（不是抄的）。

**盲写时才想明白的一件事**：`isinstance(pd.Timestamp(...), datetime.date)` 是 **True**——所以"先判 date"的顺序会让 Timestamp 原样通过（发给 `date` 列时 Postgres 隐式转换，不报错，但 `type(x).__name__` 是 `Timestamp`）。真实管道里 `date_key` 已经是 `date`，所以两者跑起来一样；差别只在"有人直接喂 DataFrame"的时候。计划 §2.6 的用例正是要抓这个。

## 2. ops 记账实况（2026-11-22 16:00）

```text
 run_id | window_start | window_end | rows_loaded | exit_code | duration_s
      1 | 2026-11-15   | 2026-11-21 |          56 |         0 |      14.81   ← 手动，联网
      2 | 2026-11-15   | 2026-11-21 |          56 |         0 |       0.85   ← 手动，reuse
      3 | 2026-11-15   | 2026-11-21 |          56 |         0 |      29.92   ← 计划任务触发
      4 | 2026-11-15   | 2026-11-21 |             |         1 |       1.01   ← 999 被 pre 拦住
      5 | 2026-11-15   | 2026-11-21 |          56 |         0 |       1.31   ← 修复重放
      6 | 2026-11-29   | 2026-12-05 |             |         3 |       3.59   ← 上游 400

check_result: pre 40 行 / 1 失败，post 30 行 / 1 失败
```

**run 4 是最有用的一行**：`rows_loaded` 为 NULL、`exit_code=1`——"跑了但没写成"和"没跑"是两回事，这一行把前者留了下来。

## 3. 复盘三问

**① 卡在哪（这次是压缩执行，卡点来自"没预料到的环境细节"）**

- Git Bash 改写 `/tmp` 路径（1 次，10 秒定位，因为计划里写了）；
- `Rename-Item` 对 `.env` 报"路径或设备名称"（1 次，换 `-LiteralPath` 解决）；
- 计划任务里 `docker info` 要 20 秒，导致一次运行 29.92 s（不是 bug，是任务环境冷启动）。

**② 时间预估修正**

原计划 630 min / 8 天；实际约 **50 min** 一次收口。这个差值不是"效率高"，是**把八天的"等"压掉了**：

- 计划里 11/24 注册、11/25 才有第一次自动运行、11/26 才有第二次——这次一晚就注册了，但**证据不会因此提前**：`started_at` 落在哪一天是数据的属性，不是排期的属性。
- 所以 12 月要修正的一条：**"会自动跑"的东西，时间成本不在写代码，在等自然日；压缩执行能压掉代码，压不掉日历。**

**③ 下一阶段要改的一件事**

> 任何"会自动跑"的东西，第一天上岗必须 **人工触发一次 + 第二天核对一次**；不核对就不算上线。

具体到动作：11/23、11/24 早上 7:10 各跑一次
`docker exec pg_meridia psql -U postgres -d weather -c "select * from ops.v_last_runs limit 3;"`，把两行 `exit_code=0` 截图存档，再补进 `SELF-REVIEW`。

## 4. 留给下一手的清单（按顺序）

1. 网页合并 **PR #3**（base `main` ← `week3/pipeline`），然后 `git tag -a v0.3-pipeline` 并 push；
2. 网页建 **PR #4**（base `main` ← `week4/ops`），合并后 `git tag -a v0.4-ops` 并 push；
3. 11/23 07:10、11/24 07:10 各核对一次自动运行（见 §3 ③）；
4. 录 3 分钟讲解（脚本在计划 §12.3），回放检查是否 ≤3:30；
5. 12 月按 `PLAN-2026-12.md` 的第一周动作开工。
