-- Funnel Analysis View Model
-- Maps conversion volume across key steps
CREATE OR REPLACE TABLE `{{ gcp_project }}.{{ bq_dataset }}.funnel_metrics` AS
SELECT 
    event_type as stage,
    COUNT(DISTINCT user_id) as user_count
FROM `{{ gcp_project }}.{{ bq_dataset }}.events`
GROUP BY event_type
ORDER BY 
    CASE event_type
        WHEN 'login' THEN 1
        WHEN 'product_view' THEN 2
        WHEN 'add_to_cart' THEN 3
        WHEN 'purchase' THEN 4
        ELSE 5
    END;
