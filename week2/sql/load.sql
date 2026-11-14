-- week2/sql/load.sql
-- stg（全 text）→ fact（带类型与约束）。重复执行不会让行数翻倍
-- 前置：week1/data/clean/fact_requests.csv 已 docker cp 到容器 /tmp/
-- 运行：docker cp week2\sql\load.sql pg_meridia:/tmp/load.sql
--       docker exec pg_meridia psql -U postgres -d meridia -f /tmp/load.sql
-- 期望：TRUNCATE TABLE / COPY 31502 / INSERT 0 31502；再跑一次仍是 31502

-- 先清空落地点，避免第二次跑时 stg 变成 63004 行
TRUNCATE stg_requests;

-- COPY 是服务端命令，文件必须在容器里；HEADER true 跳过表头
COPY stg_requests FROM '/tmp/fact_requests.csv' WITH (FORMAT csv, HEADER true);

-- 六处类型转换 + 幂等写入
INSERT INTO fact_requests
SELECT request_id,
       created_at::timestamp,                       -- 文本 → 时间戳（不用 timestamptz，源数据没有时区）
       closed_at::timestamp,
       district_id,                                -- 外键指向 dim_district
       channel,
       cat,
       priority,
       department,
       target_hours::integer,                      -- 文本 → 整数
       hours::numeric(12,6),                       -- 定点小数，才能和 pandas 对账到小数点后 3 位
       sla_ratio::numeric(12,6),
       missed::boolean,                            -- 'True'/'False' → true/false
       NULLIF(citizen_rating, '')::numeric(2,1),   -- 空串 → NULL，再转小数；「没评价」不是「评价 0」
       month
FROM stg_requests
ON CONFLICT (request_id) DO UPDATE                 -- 主键撞了就更新，而不是报错或跳过
   SET closed_at      = EXCLUDED.closed_at,
       hours          = EXCLUDED.hours,
       sla_ratio      = EXCLUDED.sla_ratio,
       missed         = EXCLUDED.missed,
       citizen_rating = EXCLUDED.citizen_rating;
