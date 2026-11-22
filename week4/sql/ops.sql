-- week4 / sql / ops.sql
-- 运维元数据：每次运行一行记录 + 每条校验一行结果。
-- 运行：docker cp week4\sql\ops.sql pg_meridia:/tmp/ops.sql
--       docker exec pg_meridia psql -U postgres -d weather -v ON_ERROR_STOP=1 -f /tmp/ops.sql
-- 幂等：全部 IF NOT EXISTS，可反复跑，不会清掉历史
--
-- 为什么不 DROP SCHEMA：ops 里存的是「历史证据」（11/25 那天到底跑没跑）。
-- init.sql 可以 DROP mart（那是可重建的数据），运维表重建就等于把日志删了。

CREATE SCHEMA IF NOT EXISTS ops;

-- 一次运行 = 一行。exit_code 先占位、跑完再更新，所以中途崩了也留痕。
CREATE TABLE IF NOT EXISTS ops.pipeline_run (
    run_id        bigserial PRIMARY KEY,
    started_at    timestamptz NOT NULL DEFAULT now(),
    finished_at   timestamptz,
    window_start  date        NOT NULL,
    window_end    date        NOT NULL,
    rows_loaded   integer,
    exit_code     integer,
    duration_s    numeric(8,2),
    log_file      text
);

-- 一条校验 = 一行。ok=false 就是一条告警。
CREATE TABLE IF NOT EXISTS ops.check_result (
    id          bigserial PRIMARY KEY,
    run_id      bigint REFERENCES ops.pipeline_run (run_id) ON DELETE CASCADE,
    stage       text    NOT NULL CHECK (stage IN ('pre', 'post')),
    check_name  text    NOT NULL,
    ok          boolean NOT NULL,
    detail      text,
    checked_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_check_result_run  ON ops.check_result (run_id);
CREATE INDEX IF NOT EXISTS idx_check_result_time ON ops.check_result (checked_at DESC);

-- 最近 10 次运行：一眼看出「昨天成没成」
CREATE OR REPLACE VIEW ops.v_last_runs AS
SELECT run_id,
       started_at,
       window_start,
       window_end,
       rows_loaded,
       exit_code,
       duration_s
FROM ops.pipeline_run
ORDER BY run_id DESC
LIMIT 10;

-- 未通过的校验（告警队列）
CREATE OR REPLACE VIEW ops.v_open_alerts AS
SELECT c.id,
       c.run_id,
       r.started_at,
       c.stage,
       c.check_name,
       c.detail
FROM ops.check_result c
JOIN ops.pipeline_run r USING (run_id)
WHERE NOT c.ok
ORDER BY c.checked_at DESC;
