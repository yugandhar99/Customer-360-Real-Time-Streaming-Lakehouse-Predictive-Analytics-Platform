-- Customer-level features consumed by the existing churn heuristic.
-- The heuristic itself remains event_count <= 2 and purchase_count = 0.
SELECT
    user_id,
    COUNT(timestamp) AS event_count,
    SUM(CASE WHEN event_type = 'purchase' THEN 1 ELSE 0 END) AS purchase_count
FROM {{database}}.events
GROUP BY user_id
