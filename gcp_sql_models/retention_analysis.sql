-- Retention Metrics View Model
-- Identifies users taking more than distinct standard events
CREATE OR REPLACE TABLE `{{ gcp_project }}.{{ bq_dataset }}.retention_metrics` AS
WITH ActivityCounts AS (
    SELECT 
        user_id,
        COUNT(timestamp) as total_interactions
    FROM `{{ gcp_project }}.{{ bq_dataset }}.events`
    GROUP BY user_id
)
SELECT 
    (SELECT COUNT(*) FROM ActivityCounts) as total_users,
    (SELECT COUNT(*) FROM ActivityCounts WHERE total_interactions > 3) as retained_users,
    ROUND(
        (SELECT COUNT(*) FROM ActivityCounts WHERE total_interactions > 3) * 100.0 / NULLIF((SELECT COUNT(*) FROM ActivityCounts), 0),
        2
    ) as retention_rate;
