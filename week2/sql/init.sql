-- week2/sql/init.sql
-- 从空库一条命令重建 4 张表（含两张维表的数据）
-- 前置：districts.csv 已在容器 /tmp/ 下（手动 docker cp，因为本轮砍掉了 db.ps1）
-- 运行：docker cp week2\sql\init.sql pg_meridia:/tmp/init.sql
--       docker exec pg_meridia psql -U postgres -d meridia -f /tmp/init.sql
-- 期望：DROP TABLE / 4x CREATE TABLE / 2x CREATE INDEX / COPY 12 / INSERT 0 731

DROP TABLE IF EXISTS fact_requests, stg_requests, dim_date, dim_district CASCADE;

CREATE TABLE dim_district (
    district_id     text PRIMARY KEY,
    district_name   text NOT NULL UNIQUE,
    profile         text,
    area_km2        numeric(6,1) NOT NULL CHECK (area_km2 > 0),
    population_2024 integer,
    population_2025 integer      NOT NULL CHECK (population_2025 > 0),
    centroid_lat    numeric(9,5),
    centroid_lon    numeric(9,5)
);

CREATE TABLE dim_date (
    date_key   date PRIMARY KEY,
    year       smallint NOT NULL,
    month      text     NOT NULL CHECK (month ~ '^\d{4}-\d{2}$'),
    quarter    smallint NOT NULL CHECK (quarter BETWEEN 1 AND 4),
    iso_dow    smallint NOT NULL CHECK (iso_dow BETWEEN 1 AND 7),
    is_weekend boolean  NOT NULL
);

-- stg：全 text、零约束。让脏数据先落地，转换失败时可定位到具体行
CREATE TABLE stg_requests (
    request_id text, created_at text, closed_at text, district_id text,
    channel text, cat text, priority text, department text,
    target_hours text, hours text, sla_ratio text, missed text,
    citizen_rating text, month text
);

-- fact：带类型与约束。外键指向 dim_district，所以维表必须先建、先灌
CREATE TABLE fact_requests (
    request_id     text PRIMARY KEY,
    created_at     timestamp NOT NULL,
    closed_at      timestamp NOT NULL,
    district_id    text NOT NULL REFERENCES dim_district (district_id),
    channel        text NOT NULL,
    cat            text NOT NULL,
    priority       text NOT NULL CHECK (priority IN ('low', 'medium', 'high')),
    department     text NOT NULL,
    target_hours   integer NOT NULL CHECK (target_hours > 0),
    hours          numeric(12,6) NOT NULL CHECK (hours >= 0),
    sla_ratio      numeric(12,6) NOT NULL,
    missed         boolean NOT NULL,
    citizen_rating numeric(2,1) CHECK (citizen_rating BETWEEN 1 AND 5),
    month          text NOT NULL CHECK (month ~ '^\d{4}-\d{2}$'),
    CONSTRAINT closed_after_created CHECK (closed_at >= created_at)
);

CREATE INDEX idx_fact_district_month ON fact_requests (district_id, month);
CREATE INDEX idx_fact_created_at     ON fact_requests (created_at);

COPY dim_district FROM '/tmp/districts.csv' WITH (FORMAT csv, HEADER true);

-- 731 = 2024 闰年 366 天 + 2025 年 365 天；generate_series 是闭区间
INSERT INTO dim_date (date_key, year, month, quarter, iso_dow, is_weekend)
SELECT d::date,
       EXTRACT(year FROM d)::smallint,
       to_char(d, 'YYYY-MM'),
       EXTRACT(quarter FROM d)::smallint,
       EXTRACT(isodow FROM d)::smallint,
       EXTRACT(isodow FROM d) IN (6, 7)
FROM generate_series('2024-01-01'::date, '2025-12-31'::date, interval '1 day') AS d;
