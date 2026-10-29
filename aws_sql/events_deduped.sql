-- One row per event_id. Firehose and process retries can deliver the same event twice.
SELECT
    event_id,
    user_id,
    event_type,
    amount,
    timestamp
FROM (
    SELECT
        event_id,
        user_id,
        event_type,
        amount,
        timestamp,
        row_number() OVER (PARTITION BY event_id ORDER BY timestamp) AS row_num
    FROM {{database}}.events
) ranked
WHERE row_num = 1
