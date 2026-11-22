# 数据契约 · `mart.fact_weather_daily`

> 给下游（DS / 分析 / 面试官）的六个承诺。写契约的价值在于**边界**：说清"什么时候不能用"，比列十个"支持"更有用。
> 最后核对：2026-11-22（656 行 / 8 城 / 82 天，`2026-09-01 → 2026-11-21`）。

| 字段 | 值 | 说明 |
|---|---|---|
| **粒度** | 一城一天一行 | 主键 `(city_id, date_key)`。**不要按小时 join**，会放大 24 倍；表里没有任何小时级信息 |
| **主键** | `(city_id, date_key)` | 同城同日只可能一行，由 upsert 保证；`date_key` 有外键指向 `dim_date`，`city_id` 指向 `dim_city` |
| **新鲜度 SLA** | T+1（每天 07:00 之后取前一天） | 正常滞后 1 天；`post` 校验允许滞后 ≤ 2 天。**滞后 3 天以上说明调度死了**，别当成"上游慢" |
| **时区** | `date_key` = **城市本地日** | 抽取用 `timezone=auto`：武汉的 11/15 与巴黎的 11/15 不是同一绝对时刻（差 6–7 h）。跨城做"同一天"比较时，这是语义差异，不是 bug |
| **空值语义** | NULL = **上游没给**，不是 0 | `app_max_c` / `app_min_c` 可空；`tmax_c` / `tmin_c` / `tmean_c` / `precip_mm` 在 `pre` 阶段要求非空（缺了整批拒收），所以 mart 里实践上不会有 NULL |
| **修订窗口** | 7 天，靠 upsert 覆盖 | 同一 `(城, 日)` 重跑会**更新值**，不会产生第二行。7 天以前的修订不会自动生效，要显式回填 `--start --end` |
| **不可用场景** | ① 2027 年（`dim_date` 到 12/31）② 小时级分析 ③ 7 天以外的历史修订 ④ 2025 年及更早（日历维没有） | 跨年必须先扩 `dim_date`，否则写入时外键失败；回填 2025 年数据同样会死在外键上 |

## 可用的列（13 列）

2 个键 + 8 个原始值 + 3 个行内派生列：

`city_id` / `date_key` / `tmax_c` / `tmin_c` / `tmean_c` / `app_max_c` / `app_min_c` /
`precip_mm` / `precip_h` / `wind_max_kmh` / `temp_range_c` / `feels_like_c` / `is_precip`

三个派生列都是**行内**计算（只用到本行），不涉及跨行：

- `temp_range_c = tmax_c - tmin_c`
- `feels_like_c = (app_max_c + app_min_c) / 2`
- `is_precip = precip_mm >= 1.0`（阈值在 `week3/src/transform.py: PRECIP_THRESHOLD_MM`）

## 与 ML 课（第 17 周：特征工程 / 数据泄漏）的对接

**按时间切训练/测试集时，DE 的交付物必须保证两件事**：

1. **每一行只携带"当天及之前"的信息**。本项目没有跨行的派生列，因此天然满足——这一点要在交付时**明说**，因为 DS 拿到表第一件事就是确认它。
2. **特征计算不能"看到未来"**。所以"近 7 天均值"这类特征**必须在 SQL 里用窗口函数算，并明确 `ROWS BETWEEN 6 PRECEDING AND CURRENT ROW`**，不能用"整表均值"顶替；也不能先 `groupby` 全表再 join 回来。

这就是数据泄漏在 DE 侧的形态：**不是模型偷看答案，是管道把未来的行拼进了当天的特征**。

> **注意：上面这段是契约，不是已实现。** `mart` 层现在**没有任何滚动特征**，只有日粒度原始列 + 3 个行内派生列。
> 写清楚"没有"比假装有更重要——如果 DS 以为 `feels_like_c` 是 7 天均值，他的模型会从一开始就错。

## 下游怎么用（三行）

```sql
-- 训练集：按时间切，别随机切（相邻日高度相关，随机切 = 泄漏）
select * from mart.fact_weather_daily where date_key <  '2026-10-01';
select * from mart.fact_weather_daily where date_key >= '2026-10-01';

-- 滚动特征：窗口函数 + 明确边界，不能让 10/05 用到 10/06 的数据
select city_id, date_key,
       avg(tmean_c) over (partition by city_id order by date_key
                          rows between 6 preceding and current row) as tmean_7d
from mart.fact_weather_daily;
```
