-- Athena retention. A user is retained when total interactions are greater than 3.
-- NULLIF keeps the rate null instead of failing when the event table is empty.
WITH activity AS (
    SELECT
        user_id,
        COUNT(timestamp) AS total_interactions
    FROM {{database}}.events
    GROUP BY user_id
)
SELECT
    COUNT(*) AS total_users,
    SUM(CASE WHEN total_interactions > 3 THEN 1 ELSE 0 END) AS retained_users,
    ROUND(
        CAST(SUM(CASE WHEN total_interactions > 3 THEN 1 ELSE 0 END) AS DOUBLE)
        * 100.0
        / NULLIF(COUNT(*), 0),
        2
    ) AS retention_rate
FROM activity
