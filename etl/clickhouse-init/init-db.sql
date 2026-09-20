-- Сырая телеметрия: пишется потоком с чипов протезов через 4G.
CREATE TABLE IF NOT EXISTS bionic.telemetry
(
    user_id        String,
    prosthesis_id  String,
    event_time     DateTime,
    gesture        LowCardinality(String),
    response_ms    UInt16,
    signal_quality Float32,
    battery_pct    UInt8,
    error_code     LowCardinality(String)
    )
    ENGINE = MergeTree
    PARTITION BY toYYYYMM(event_time)
    ORDER BY (user_id, event_time);

-- Реплика справочника клиентов из CRM, наполняется Airflow.
CREATE TABLE IF NOT EXISTS bionic.crm_clients
(
    user_id      String,
    full_name    String,
    city         String,
    model        LowCardinality(String),
    purchased_at Date,
    updated_at   DateTime DEFAULT now()
    )
    ENGINE = ReplacingMergeTree(updated_at)
    ORDER BY user_id;

-- Витрина отчётности. Ключ сортировки начинается с user_id,
CREATE TABLE IF NOT EXISTS bionic.report_mart
(
    user_id         String,
    report_date     Date,
    full_name       String,
    model           LowCardinality(String),
    events_total    UInt64,
    avg_response_ms Float32,
    p95_response_ms Float32,
    avg_signal      Float32,
    min_battery_pct UInt8,
    errors_total    UInt64,
    built_at        DateTime DEFAULT now()
    )
    ENGINE = ReplacingMergeTree(built_at)
    PARTITION BY toYYYYMM(report_date)
    ORDER BY (user_id, report_date);

-- Граница обработанных данных: API не отдаёт периоды правее last_loaded_date.
CREATE TABLE IF NOT EXISTS bionic.etl_watermark
(
    mart_name        String,
    last_loaded_date Date,
    updated_at       DateTime DEFAULT now()
    )
    ENGINE = ReplacingMergeTree(updated_at)
    ORDER BY mart_name;

-- Тестовая телеметрия: 3 пользователя, около 10 дней истории.
INSERT INTO bionic.telemetry
(user_id, prosthesis_id, event_time, gesture, response_ms, signal_quality, battery_pct, error_code)
SELECT
    ['prothetic1', 'prothetic2', 'prothetic3'][(number % 3) + 1],
    concat('PR-', toString((number % 3) + 1)),
    now() - toIntervalSecond(number * 7),
    ['grip', 'pinch', 'open', 'rotate'][(number % 4) + 1],
    toUInt16(60 + (number % 90)),
    toFloat32(0.70 + (number % 30) / 100),
    toUInt8(100 - (number % 60)),
    if(number % 250 = 0, 'E_SIGNAL_LOST', '')
FROM numbers(120000);