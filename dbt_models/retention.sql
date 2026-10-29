-- Retention Metrics Model
-- Calculates user activity frequency (DAU-style engagement metrics)

WITH user_daily_activity AS (
    SELECT 
        user_id,
        TIMESTAMP_TRUNC(timestamp, DAY) AS activity_date
    FROM `{{ config.GCP_PROJECT_ID }}.{{ config.GCP_BQ_DATASET }}.events`
    GROUP BY user_id, activity_date
)
SELECT 
    user_id,
    COUNT(DISTINCT activity_date) AS active_days,
    MIN(activity_date) AS first_active,
    MAX(activity_date) AS last_active
FROM user_daily_activity
GROUP BY user_id
ORDER BY active_days DESC;
