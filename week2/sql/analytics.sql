-- week2/sql/analytics.sql
-- 按 §10 降级：本周只保 1 条窗口函数（排名三兄弟），Q2-Q8 全砍，理由见 NOTES.md
-- 业务问题：四个渠道按 SLA 超时率排名，遇到并列时三种排名函数分别怎么处理？
-- 运行：docker cp week2\sql\analytics.sql pg_meridia:/tmp/analytics.sql
--       docker exec pg_meridia psql -U postgres -d meridia -f /tmp/analytics.sql

WITH c AS (
  SELECT channel, count(*) AS n, round(avg(missed::int), 3) AS r
  FROM fact_requests GROUP BY channel)
SELECT channel, n, r,
       row_number() OVER (ORDER BY r DESC) AS row_number,
       rank()       OVER (ORDER BY r DESC) AS rank,
       dense_rank() OVER (ORDER BY r DESC) AS dense_rank
FROM c ORDER BY r DESC;
