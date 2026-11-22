-- weather-pipeline / sql / metrics.sql
-- 三个业务指标 + 一条对账。全部用 mart 层的表，不碰 stg、不碰 raw。
-- 运行：docker cp week3\sql\metrics.sql pg_meridia:/tmp/metrics.sql
--       docker exec pg_meridia psql -U postgres -d weather -f /tmp/metrics.sql

\echo '--- S1 最近 7 天各城市平均温差（越大 = 昼夜温差越大）'
WITH w AS (SELECT max(date_key) AS d FROM mart.fact_weather_daily)
SELECT c.city_name, round(avg(f.temp_range_c), 2) AS avg_range_c, count(*) AS days
FROM mart.fact_weather_daily f
JOIN mart.dim_city c USING (city_id)
CROSS JOIN w
WHERE f.date_key > w.d - 7
GROUP BY c.city_name
ORDER BY avg_range_c DESC;

\echo '--- S2 11 月以来连续 >=3 天降水量 >= 1.0mm 的城市'
WITH d AS (
    SELECT city_id, date_key, precip_mm >= 1.0 AS wet
    FROM mart.fact_weather_daily
    WHERE date_key >= DATE '2026-11-01'),
islands AS (
    SELECT *, date_key - (row_number() OVER (PARTITION BY city_id ORDER BY date_key))::int AS grp
    FROM d WHERE wet),
runs AS (
    SELECT city_id, count(*) AS len, min(date_key) AS d0, max(date_key) AS d1
    FROM islands GROUP BY city_id, grp)
SELECT DISTINCT ON (r.city_id)
       c.city_name, r.len AS max_consec_wet, r.d0 AS run_start, r.d1 AS run_end
FROM runs r JOIN mart.dim_city c USING (city_id)
WHERE r.len >= 3
ORDER BY r.city_id, r.len DESC;

\echo '--- S3 10 月 vs 9 月均温环比（负 = 变冷）'
WITH m AS (
    SELECT f.city_id, dd.month, avg(f.tmean_c) AS t
    FROM mart.fact_weather_daily f
    JOIN mart.dim_date dd USING (date_key)
    WHERE dd.month IN ('2026-09', '2026-10')
    GROUP BY 1, 2)
SELECT c.city_name,
       round(avg(t) FILTER (WHERE month = '2026-09'), 2) AS sep_avg,
       round(avg(t) FILTER (WHERE month = '2026-10'), 2) AS oct_avg,
       round(avg(t) FILTER (WHERE month = '2026-10')
             - avg(t) FILTER (WHERE month = '2026-09'), 2) AS diff
FROM m JOIN mart.dim_city c USING (city_id)
GROUP BY c.city_name
ORDER BY diff;

\echo '--- S4 对账：行数 / 城市数 / 天数 / 重复键 / 日期范围'
SELECT count(*) AS total_rows,
       count(DISTINCT city_id) AS cities,
       count(DISTINCT date_key) AS dates,
       count(*) - count(DISTINCT (city_id, date_key)) AS dup_keys,
       min(date_key) AS min_date, max(date_key) AS max_date
FROM mart.fact_weather_daily;
