-- weather-pipeline / sql / init.sql
-- 从空库重建三层：stg（落地点，无约束）+ mart（维表 + 事实表）
-- 运行：docker cp week3\sql\init.sql pg_meridia:/tmp/init_weather.sql
--       docker exec pg_meridia psql -U postgres -d weather -v ON_ERROR_STOP=1 -f /tmp/init_weather.sql
-- 期望：2x CREATE SCHEMA / 4x CREATE TABLE / 1x CREATE INDEX / INSERT 0 8 / INSERT 0 365

DROP SCHEMA IF EXISTS mart CASCADE;
DROP SCHEMA IF EXISTS stg  CASCADE;
CREATE SCHEMA stg;
CREATE SCHEMA mart;

-- 维表 1：城市。8 行，手写 INSERT（8 行比一个 CSV 文件便宜）
CREATE TABLE mart.dim_city (
    city_id     text PRIMARY KEY,
    city_name   text NOT NULL UNIQUE,
    country     text NOT NULL CHECK (country IN ('CN', 'FR')),
    latitude    numeric(8,4) NOT NULL CHECK (latitude  BETWEEN  -90 AND  90),
    longitude   numeric(8,4) NOT NULL CHECK (longitude BETWEEN -180 AND 180),
    timezone    text NOT NULL,
    elevation_m numeric(6,1)
);

INSERT INTO mart.dim_city (city_id, city_name, country, latitude, longitude, timezone, elevation_m) VALUES
 ('wuhan',     'Wuhan',     'CN', 30.5928, 114.3055, 'Asia/Shanghai', 15.0),
 ('shanghai',  'Shanghai',  'CN', 31.2304, 121.4737, 'Asia/Shanghai',  5.0),
 ('beijing',   'Beijing',   'CN', 39.9042, 116.4074, 'Asia/Shanghai', 47.0),
 ('chengdu',   'Chengdu',   'CN', 30.5728, 104.0668, 'Asia/Shanghai', 485.0),
 ('paris',     'Paris',     'FR', 48.8566,   2.3522, 'Europe/Paris',  36.0),
 ('lyon',      'Lyon',      'FR', 45.7640,   4.8357, 'Europe/Paris', 184.0),
 ('marseille', 'Marseille', 'FR', 43.2965,   5.3698, 'Europe/Paris',   6.0),
 ('toulouse',  'Toulouse',  'FR', 43.6047,   1.4442, 'Europe/Paris', 153.0);

-- 维表 2：日历。365 行由 generate_series 生成，不手打
CREATE TABLE mart.dim_date (
    date_key   date PRIMARY KEY,
    year       smallint NOT NULL,
    month      text     NOT NULL CHECK (month ~ '^\d{4}-\d{2}$'),
    quarter    smallint NOT NULL CHECK (quarter BETWEEN 1 AND 4),
    iso_dow    smallint NOT NULL CHECK (iso_dow BETWEEN 1 AND 7),
    is_weekend boolean  NOT NULL
);

-- 2026 不是闰年 → 365 天。week2 那张 dim_date 是 2024–2025，直接复用会 join 出 0 行
INSERT INTO mart.dim_date (date_key, year, month, quarter, iso_dow, is_weekend)
SELECT d::date,
       EXTRACT(year FROM d)::smallint,
       to_char(d, 'YYYY-MM'),
       EXTRACT(quarter FROM d)::smallint,
       EXTRACT(isodow FROM d)::smallint,
       EXTRACT(isodow FROM d) IN (6, 7)
FROM generate_series('2026-01-01'::date, '2026-12-31'::date, interval '1 day') AS d;

-- 落地点：stg。全列可空、零约束 —— 它必须能装下脏数据
CREATE TABLE stg.weather_daily (
    city_id       text,
    date_key      date,
    tmax_c        numeric(4,1),
    tmin_c        numeric(4,1),
    tmean_c       numeric(4,1),
    app_max_c     numeric(4,1),
    app_min_c     numeric(4,1),
    precip_mm     numeric(6,1),
    precip_h      numeric(4,1),
    wind_max_kmh  numeric(5,1),
    temp_range_c  numeric(4,1),
    feels_like_c  numeric(4,1),
    is_precip     boolean
);

-- 事实表：带类型与约束。两张维表必须先建、先灌
CREATE TABLE mart.fact_weather_daily (
    city_id       text    NOT NULL REFERENCES mart.dim_city (city_id),
    date_key      date    NOT NULL REFERENCES mart.dim_date (date_key),
    tmax_c        numeric(4,1) NOT NULL,
    tmin_c        numeric(4,1) NOT NULL,
    tmean_c       numeric(4,1) NOT NULL,
    app_max_c     numeric(4,1),
    app_min_c     numeric(4,1),
    precip_mm     numeric(6,1) NOT NULL CHECK (precip_mm >= 0),
    precip_h      numeric(4,1) NOT NULL CHECK (precip_h BETWEEN 0 AND 24),
    wind_max_kmh  numeric(5,1) NOT NULL CHECK (wind_max_kmh >= 0),
    temp_range_c  numeric(4,1) NOT NULL CHECK (temp_range_c >= 0),
    feels_like_c  numeric(4,1),
    is_precip     boolean      NOT NULL,
    PRIMARY KEY (city_id, date_key),
    CONSTRAINT tmax_ge_tmin CHECK (tmax_c >= tmin_c)
);

CREATE INDEX idx_fact_weather_date ON mart.fact_weather_daily (date_key);
