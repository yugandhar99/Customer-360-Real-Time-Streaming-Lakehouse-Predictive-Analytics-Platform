-- Funnel Analysis Model
-- Tracks conversion across the e-commerce funnel stages

SELECT 
    event_type AS stage,
    COUNT(user_id) AS total_events,
    COUNT(DISTINCT user_id) AS unique_users
FROM `{{ config.GCP_PROJECT_ID }}.{{ config.GCP_BQ_DATASET }}.events`
GROUP BY event_type
ORDER BY 
    CASE event_type
        WHEN 'product_view' THEN 1
        WHEN 'add_to_cart' THEN 2
        WHEN 'purchase' THEN 3
        ELSE 4
    END ASC;
