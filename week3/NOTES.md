# week3 NOTES

## Day 2（11/17–11/18）抽取层

### 实测结果

```powershell
cd D:\code\de-journey\week3
python -m src.extract 2026-09-01 2026-11-14
```

- `8 files, 36025 bytes`（首次）/ `36023 bytes`（重跑），exit 0。
- 8 个 JSON 各 **75 天**（2026-09-01 ~ 11-14），`daily` 9 个 key（`time` + 8 变量），`error=False`；
  时区 `Asia/Shanghai` ×4 + `Europe/Paris` ×4 → 就是 4 中 4 法跨时区那个教学点。
- **计划里的 `36028 bytes` 不是硬判据**：响应体里 `generationtime_ms` 是浮点数，字符串长度每次浮动几字节，
  三次跑分别是 36025 / 36023 / 计划 11-15 那次 36028。真判据是 **8 城 × 75 天 = 600 行**。
- 重跑同一区间：仍是 8 个文件（覆盖同名，不新增）→ 文件名带 `start_end` 就是幂等的一部分。

### 故意打一次 400（判据）

```text
RuntimeError: wuhan: HTTP 400 Parameter 'start_date' is out of allowed range from 1940-01-01 to 2026-11-18
耗时 4.16s
```

三条结论：

1. **4.16s = 一次请求的时间**，没有多等 2+4=6 秒 → 4xx 确实没进重试循环。
2. `requests.raise_for_status()` 只会说 `400 Client Error`，**真正的原因在 body 的 `reason` 里**。
   所以加了 `_reason(resp)`，把 4xx（及重试耗尽的 429/5xx）统一抛成带 reason 的 `RuntimeError`。
3. 可取范围是 **1940-01-01 ~ "今天"**（计划写 11-15 是因为它在 11-15 写的，上限跟着日期走）。
   未来日期在抽取层就死，走不到入库那一层。

### 四个必答问题

| # | 答案要点 |
|---|---|
| 1 | raw 落 `resp.content` 字节，不落 `json.dump`：原文可重放；`json.load`→`dump` 会改键顺序、改浮点表示、丢掉不认识的字段 |
| 2 | `timeout=(5,30)`：5 = 连接超时，30 = 读取超时。只写一个数会把"连上了但服务器算得慢"误判成失败 |
| 3 | 400 不重试（是**我**参数错，重试 100 次一样）；429 / 5xx 退避重试（是**对方**暂时不行）。429 必须从 4xx 里单独排除，否则会被"直接炸"分支吃掉 |
| 4 | 文件名带 `start_end`：同一区间重跑覆盖同名（幂等），不同区间互不覆盖、能重放 |

### 今天踩的坑

- **`if __name__ == "&#8203;main__":`** —— 从聊天窗口复制代码时把 HTML 实体 `&#8203;` 当**字面字符**写进了文件，
  条件恒 False，程序**没有任何输出、也不报错**，静默什么都不干。
  诊断：`repr()` 打印那一行；全文件扫 `&#\d+;|&#x[0-9a-fA-F]+;|[\u200b-\u200f\ufeff]`（只扫零宽空格查不到它）。
  预防：复制含 `__main__` 的代码后手动重敲这一行。
- **open-meteo 偶发 500 / timeout**：10:16 那次 wuhan timeout + 3×500 直接炸；同一 URL 用 curl 和 requests
  （含禁用代理 env）复测全部 200、武汉 4537 bytes，10:20 重跑即成功 → 服务端抖动，不是代码问题。
  现有 `MAX_RETRY=3` + 2s/4s 退避只撑 6 秒，扛不住持续几十秒的抖动；重跑时北京有一次 29.40s，
  差点撞上 30 秒读取超时。**后续可考虑 5 次 + 更长退避**（本次未改，保持最小改动）。
- 代理偶发返回 **HTTP 200 但 body 是 72 字节纯错误文本**（`Unexpected error while streaming data...`），
  不是 JSON。落盘前可加一条「body 是否以 `{` 开头」的校验，防止把错误页当原始数据存下（本次未加）。

### 「写进去了 ≠ 生效了」系列（累计）

| 坑 | 正确判据 |
|---|---|
| pg_hba 改了文件 | 查 `pg_hba_file_rules`，不是看文件内容 |
| PowerShell `>>` 写 UTF-16LE | 查 `pg_hba_file_rules` |
| `.gitignore` 带 BOM | `git check-ignore -v <文件>` |
| `__main__` 里混进 HTML 实体 | `repr()` / 全文件扫实体字符 |

---

## Day 1 补记（11/16）

- `init.sql` 四张表跑通：`c=8  d=365  f=0`；`\d mart.fact_weather_daily` 13 列 / 2 FK / 5 CHECK / 1 索引。
- **pg_hba 三条生效规则**：124 `local ... trust`（`docker exec psql` 走它，免密）、125 `host 127.0.0.1 trust`、
  127 `host 172.16.0.0/12 scram-sha-256`（Windows 经发布端口连走它，来源被 NAT 成 `172.17.0.1`）。
  两个"本地"不是同一个本地。
- **维表倒推三条路径**：① 下游指标问题 → 粒度 → `city_id`；② 数据源元数据 → `timezone` / `elevation_m`；
  ③ 业务口径 → `city_name` / `country` / `lat` / `lon`。倒推对象是**问题**，不是"已经建好的表"。
- 外键指向维表 → **维表必须先建 + 先灌数**，否则写入时炸（外键查的是行，不只是表）。
- `.env` 只在本地，`.env.example` 进 Git 且密码永远留空；`.gitignore` 用 `ascii` 写，避免 BOM。

---

## Day 3–7 合并完成（11/22，一次性收口）

> 本周前两天的节奏被打断（周三起没跟上），11/22 下午把 Day3–Day7 合并做完。
> 下面只记**判断与实测数字**，不记流水。

### Day3 transform（`src/transform.py`）

- `(600, 13) 8 2026-09-01 2026-11-14` + 6 个 `OK`，前三行与计划 §8 参考输出逐位一致。
- **列式 → 行式一个循环都没写**：9 个等长 list 直接当列，行数天然是 75。
- 踩坑：`AttributeError: 'DatetimeIndex' object has no attribute 'dt'` ——
  `pd.to_datetime(列表)` 返回 `DatetimeIndex`（`.dt` 只属于 Series），改成 `.date`。
- `COLS` 定序 + `sort_values` + `reset_index(drop=True)`：让输出可复现（不然 concat 顺序靠运气）。
- 阈值实验：`is_precip` 真值数 **1.0mm → 169 / 0.1mm → 265**。

### Day4 load + run（`src/load.py` / `run.py`）

- `stg=600 fact_affected=600 fact_total=600`；`--reuse-raw` 再跑一次 → 仍 **600**（幂等成立）。
- 全链路（含 8 城抽取）**12.93s**，比计划的 3.03s 慢 4 倍——纯网络，抽取每城 1.3–1.9s；
  `--reuse-raw` **0.09–0.20s**，说明慢的全在 IO 不在计算。
- `extract.py` 补了 `extract_all(start, end, raw_dir)`：原文件只有 CLI `main`，
  且 `main` 里自己调 `logging.basicConfig`——被 `run.py` 调用会覆盖 run 的日志配置（屏幕+文件双写）。
  **函数里不配日志，谁调用谁配**。
- `to_rows` 的 `hasattr(value, "item")` 分支不能少：numpy 标量直接进 psycopg 也能过，
  但 `date` 判断必须放在它前面，否则 `datetime.date` 会被当作普通对象原样传。

### Day5 指标 + 增量 + EXPLAIN 债

- S1 8 行 / S2 4 行 / S3 8 行 / S4 `600|8|75|0`，与答案键**逐行一致**（含 Lyon 11/10–11/13 四天）。
- 增量 `--start 2026-11-15 --end 2026-11-15` → `stg=8 fact_total=608`，`max(date_key)=2026-11-15`；
  演示完 `delete where date_key > '2026-11-14'` 再全量重跑，回到 600。
- EXPLAIN 债（`meridia.fact_requests` 31,502 行）：
  `Index Cond` **1.979 ms** vs `Filter` + `Rows Removed by Filter: 29957` **5.480 ms**，差 2.77 倍。
  详见 `EXPLAIN-debt.md`。

### Day6 文档与配置

- `README.md`（架构 + 六条命令 + 三个取舍 + 已知限制）、`DATA_DICTIONARY.md`（13 列 + 2 维表）、
  `EXPLAIN-debt.md`、`quiz.md` 四份补齐。
- 密码只在 `.env`（未入库）与 `load.py` 的 `os.environ.get("PG_PASSWORD", "")` 默认空串。

### 今天新踩的坑

- **Git Bash 下 `docker cp` / `psql -f` 的 `/tmp` 被 MSYS 改写成 `D:/DevOps-MLOps/Temp`**：
  `docker exec ... psql -f /tmp/metrics.sql` → `psql: error: D:/DevOps-MLOps/Temp/metrics.sql: No such file`。
  `MSYS_NO_PATHCONV=1` 对它无效，正确写法是 **`//tmp/metrics.sql`**（双斜杠）或 `MSYS2_ARG_CONV_EXCL='*'`。
  PowerShell 里不会出现这个问题——这也是 README 里写 PowerShell 版本的原因。

### 复盘三问（答完填这里）

1. **卡在哪**：周三到周六整段没推进（不是"不会"，是**时间没排进去**）。原计划把 5 个 Block 摊在 5 个晚上，
   任何一天断掉就整周顺延——**单点故障，没有缓冲**。
2. **时间预估修正**：11/22 实际投入约 3.5 h 完成 Day3–Day7（计划值 470 min ≈ 7.8 h）。
   压缩来源是"不再逐行自己写"，代价是**少了手写时的排错经验**——这笔账要在单元 4 用"重写一遍 `load.py`"补回来。
3. **下单元要改的一件事**：把"写进去了"换成"生效证据"落实到命令上——每次改配置/SQL/DDL 后，
   必须跟一条**查询**（`pg_hba_file_rules` / `\d 表名` / `count(*)`），不接受"文件内容看起来对了"。
