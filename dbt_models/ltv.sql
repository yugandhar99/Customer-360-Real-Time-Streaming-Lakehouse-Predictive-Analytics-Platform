-- LTV Analysis Model (dbt style)
-- Aggregates customer lifetime value from raw events

WITH order_data AS (
    SELECT 
        user_id,
        MIN(timestamp) AS first_order_date,
        MAX(timestamp) AS last_order_date,
        COUNT(CASE WHEN event_type = 'purchase' THEN 1 END) AS total_orders,
        SUM(CASE WHEN event_type = 'purchase' THEN amount ELSE 0 END) AS total_ltv
    FROM `{{ config.GCP_PROJECT_ID }}.{{ config.GCP_BQ_DATASET }}.events`
    GROUP BY user_id
)
SELECT 
    user_id,
    first_order_date,
    last_order_date,
    total_orders,
    total_ltv,
    SAFE_DIVIDE(total_ltv, total_orders) AS avg_order_value,
    TIMESTAMP_DIFF(last_order_date, first_order_date, DAY) AS customer_lifespan_days
FROM order_data
WHERE total_ltv > 0
ORDER BY total_ltv DESC;
