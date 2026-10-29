-- Athena cohorts. The first ten characters of the earliest timestamp are the cohort day.
WITH signups AS (
    SELECT
        user_id,
        MIN(timestamp) AS signup_date
    FROM {{database}}.events
    GROUP BY user_id
)
SELECT
    substr(CAST(signup_date AS VARCHAR), 1, 10) AS cohort_day,
    COUNT(user_id) AS user_count
FROM signups
GROUP BY substr(CAST(signup_date AS VARCHAR), 1, 10)
ORDER BY cohort_day ASC
