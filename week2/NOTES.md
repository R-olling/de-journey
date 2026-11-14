# week2 复盘（按 §10 降级）

## 交付
- `sql/init.sql`：从空库建 4 张表（`dim_district` / `dim_date` / `stg_requests` / `fact_requests`），`COPY 12` + `INSERT 0 731`
- `sql/load.sql`：`stg` → `fact` 带类型转换，`COPY 31502` + `INSERT 0 31502`；重跑一次 `count(*)` 仍是 31502（幂等 upsert）
- `sql/metrics.sql`：7 KPI 与 pandas 逐位一致 `31502 / 10972 / 0.348 / 0.619 / 0.381 / 72.258 / 4.199`
- `sql/analytics.sql`：排名三兄弟（`ROW_NUMBER` / `RANK` / `DENSE_RANK`），按渠道超时率排名

## 降级说明
砍掉：Q2–Q8 业务 SQL、EXPLAIN 四组实验、组件地图、闭卷小测、`sql_notes` / `EXPLAIN` / `components` / `quiz` 四份文档、`db.ps1` 脚本。原计划「`week2/` 10 份文件、commit ≥5」的验收要求同步降级。

原因：实习可到岗时间提前到 12 月下旬（12/18 结课、12/20 可到岗），简历与投递占用 11 月上旬；本周有效学习时间不足原计划 13.5 h 的三分之一，且 SQL 概念密度高于 pandas（一个真懂的概念需 30–60 分钟追问，一晚最多 1–2 个）。

**§10 三条「不可砍」全部保留**：7 KPI 对账 ✅、幂等 upsert ✅、窗口三兄弟 ✅。

## 卡点记录
- 容器名冲突：`docker run` 是「新建 + 启动」，已停止的同名容器仍占着名字。修法是 `docker start`，不要 `docker rm -f`——数据在命名卷 `meridia_pgdata` 里没丢。
- `docker cp` 的目标写反斜杠，Windows 客户端会规范化，但容器内 `psql -f` 只认正斜杠。**冒号后一律写 `/`**。
- `psql -d` 会真的连进那个库（库名错即报 `FATAL: database ... does not exist`）；`pg_isready -d` 只是把名字填进请求，不检查库是否存在。
- PowerShell 的 `$LASTEXITCODE` 记录上一条外部程序的退出码，`0` = 成功；脚本靠它判断能否往下走，屏幕上的字给人看、数字给机器看。
- 选项大小写敏感：`-U`（username）≠ `-u`，后者 psql 不认。

## 交给单元 3
四张表 + `ON CONFLICT` 幂等 + 7 KPI 对账，就是管道自动化校验的雏形。

**下一单元前补**：`EXPLAIN` / `EXPLAIN ANALYZE` 读执行计划——本单元最值钱、本周被砍掉的一格。
