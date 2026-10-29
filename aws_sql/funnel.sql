-- Athena funnel. Zero-count stages are kept so the result matches the Python job.
WITH stages(stage, stage_order) AS (
    SELECT 'login', 1
    UNION ALL
    SELECT 'product_view', 2
    UNION ALL
    SELECT 'add_to_cart', 3
    UNION ALL
    SELECT 'purchase', 4
),
counts AS (
    SELECT
        event_type AS stage,
        COUNT(DISTINCT user_id) AS user_count
    FROM {{database}}.events
    GROUP BY event_type
)
SELECT
    stages.stage,
    COALESCE(counts.user_count, 0) AS user_count
FROM stages
LEFT JOIN counts ON stages.stage = counts.stage
ORDER BY stages.stage_order
