# week3 · 补 week2 的 EXPLAIN 债

> 为什么不用 `fact_weather_daily` 做：它只有 600 行，优化器**永远选全表扫**，看不出索引的价值。
> 用 `meridia.fact_requests`（31,502 行，`created_at` 上正好有索引）才跑得出差别。

## 实测环境

- PostgreSQL 16.15，容器 `pg_meridia`，库 `meridia`，表 `fact_requests` 31,502 行
- 实测时间：2026-11-22 14:41
- 命令：`EXPLAIN (ANALYZE, COSTS OFF)`

## 实验 1 · 可 sargable 的范围查询

```sql
SELECT count(*) FROM fact_requests
WHERE created_at >= '2025-07-01' AND created_at < '2025-08-01';
```

| 项 | 值 |
|---|---|
| 节点 | `Index Only Scan using idx_fact_created_at` |
| 关键行 | **`Index Cond`**（索引负责定位） |
| Heap Fetches | 0 |
| 命中行数 | 1545 |
| Execution Time | **1.979 ms** |

## 实验 2 · 函数包住列

```sql
SELECT count(*) FROM fact_requests
WHERE created_at::date >= '2025-07-01' AND created_at::date < '2025-08-01';
```

| 项 | 值 |
|---|---|
| 节点 | `Index Only Scan using idx_fact_created_at`（**同一个节点名**） |
| 关键行 | **`Filter`**（索引整段扫完再逐行算 `::date` 扔掉） |
| Rows Removed by Filter | **29,957**（占全表 95%） |
| Heap Fetches | 0 |
| Execution Time | **5.480 ms** |

## 结论（一句话）

> **`EXPLAIN` 看的不是节点名字，是这一行是 `Index Cond` 还是 `Filter`。**
> 前者是"索引帮我定位到 1545 行"，后者是"索引整棵扫完，再逐行算 `::date` 扔掉 29,957 行"。
> 同一个节点名，差 **2.77 倍**（1.979 ms vs 5.480 ms）。

## 数字会漂，判断不会

| 来源 | 实验 1 | 实验 2 | 倍数 |
|---|---|---|---|
| week2 计划（2026-11-14） | 0.423 ms | 2.821 ms | 6.7× |
| 本次（2026-11-22） | 1.979 ms | 5.480 ms | 2.8× |

差异来自缓存命中、统计信息和机器负载，**不是口径问题**。验收只认两件事：
① 关键行是 `Index Cond` 还是 `Filter`；② `Rows Removed by Filter` 是否接近总行数。

## 落到工程上的两条规则

1. **不要在 `WHERE` 里对索引列做函数/类型转换**（`created_at::date`、`to_char(...)`）——索引立刻失效，只剩扫描。
2. 要按"日期"过滤就写**半开区间** `>= 起点 AND < 终点`，而不是 `= 某天` 或 `::date`。
