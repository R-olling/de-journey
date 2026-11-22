# week3 · 数据字典

> 13 列 + 2 张维表。"更新频率"这一列是给单元 4 的调度看的：
> 事实表每天追加/更新一天，`dim_city` 几乎不变，`dim_date` 年初生成一次。

## 事实表 `mart.fact_weather_daily`（600 行）

| 列 | 类型 | 含义 | 来源 | 约束 | 更新频率 |
|---|---|---|---|---|---|
| `city_id` | text | 城市键（`wuhan`…） | 配置 `CITIES` | PK / FK → `dim_city` | 不变 |
| `date_key` | date | **城市本地日期** | `daily.time` | PK / FK → `dim_date` | 每天新增 1 天 |
| `tmax_c` | numeric(4,1) | 日最高气温 | `temperature_2m_max` | NOT NULL | 每天 |
| `tmin_c` | numeric(4,1) | 日最低气温 | `temperature_2m_min` | NOT NULL | 每天 |
| `tmean_c` | numeric(4,1) | 日平均气温 | `temperature_2m_mean` | NOT NULL | 每天 |
| `app_max_c` | numeric(4,1) | 最高体感温度 | `apparent_temperature_max` | 可空 | 每天 |
| `app_min_c` | numeric(4,1) | 最低体感温度 | `apparent_temperature_min` | 可空 | 每天 |
| `precip_mm` | numeric(6,1) | 日降水量（mm） | `precipitation_sum` | `>= 0` | 每天 |
| `precip_h` | numeric(4,1) | 日降水小时数 | `precipitation_hours` | `0–24` | 每天 |
| `wind_max_kmh` | numeric(5,1) | 日最大风速 | `wind_speed_10m_max` | `>= 0` | 每天 |
| `temp_range_c` | numeric(4,1) | 昼夜温差 = tmax − tmin | 派生（行内） | `>= 0` | 每天 |
| `feels_like_c` | numeric(4,1) | 日均体感 = (app_max+app_min)/2 | 派生（行内） | 可空 | 每天 |
| `is_precip` | boolean | 是否降水（≥ **1.0** mm） | 派生（阈值常量） | NOT NULL | 每天 |

**主键**：`(city_id, date_key)` —— 幂等的全部依据。
**表级 CHECK**：`tmax_c >= tmin_c`。

## 维表 1 `mart.dim_city`（8 行）

| 列 | 类型 | 说明 |
|---|---|---|
| `city_id` | text PK | 与 `CITIES` 配置同名，两处必须一致 |
| `city_name` | text UNIQUE | 展示用名（`Wuhan` / `Paris`） |
| `country` | text | `CN` / `FR`，CHECK 限制 |
| `latitude` / `longitude` | numeric(8,4) | 坐标，与抽取参数同源 |
| `timezone` | text | `Asia/Shanghai` / `Europe/Paris` |
| `elevation_m` | numeric(6,1) | 海拔，暂时没用于计算 |

## 维表 2 `mart.dim_date`（365 行）

| 列 | 类型 | 说明 |
|---|---|---|
| `date_key` | date PK | 2026-01-01 ~ 2026-12-31（2026 不是闰年） |
| `year` / `month` / `quarter` | smallint / text / smallint | `month` 形如 `2026-09`，S3 环比按它分组 |
| `iso_dow` | smallint | 1=周一 … 7=周日 |
| `is_weekend` | boolean | `iso_dow IN (6,7)` |

> **为什么 365 而不是 75**：日历维是通用的，跨月、跨季度都能用；只生成 75 行的话，下个月再跑就得重建维表。
> **维表宁可多生成，不要按需补。**

## 极值参考（写结论时用）

| 项 | 值 |
|---|---|
| 最高 `tmax` | 38.5°C（Toulouse，2026-09-06） |
| 最低 `tmin` | -1.2°C（Beijing，2026-11-09） |
| 最大单日降水 | 179.3 mm（Marseille，2026-10-20，地中海秋季暴雨） |
| 无降水日 | 335 / 600 |
| `is_precip` 为真 | 169 / 600 |

两个"不能删"：179.3 mm 是真实极端事件，-1.2°C 是 11 月北京的正常低温。
**判据**：值"不可能"发生 → 删；值"可能但极端" → 留并单列观察。
