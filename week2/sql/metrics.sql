-- week2/sql/metrics.sql
-- 7 个 KPI：pandas 与 PostgreSQL 的跨工具对账（§3.2 / §8.3）
-- 运行：docker cp week2\sql\metrics.sql pg_meridia:/tmp/metrics.sql
--       docker exec pg_meridia psql -U postgres -d meridia -f /tmp/metrics.sql
-- 答案键：31502 | 10972 | 0.348 | 0.619 | 0.381 | 72.258 | 4.199

SELECT count(*)                                            AS n_requests,
       count(citizen_rating)                               AS n_rated,
       round(avg((citizen_rating IS NOT NULL)::int), 3)     AS response_rate,
       round(1 - avg(missed::int), 3)                      AS on_time_rate,
       round(avg(missed::int), 3)                          AS miss_rate,
       round(percentile_cont(0.5) WITHIN GROUP (ORDER BY hours)::numeric, 3) AS median_hours,
       round(avg(citizen_rating), 3)                       AS mean_rating
FROM fact_requests;
