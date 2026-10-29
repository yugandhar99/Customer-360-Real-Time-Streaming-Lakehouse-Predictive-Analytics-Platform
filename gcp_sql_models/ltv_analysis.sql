-- Customer Lifetime Value (LTV) View Model
-- Designed for BigQuery execution

CREATE OR REPLACE TABLE `{{ gcp_project }}.{{ bq_dataset }}.ltv_metrics` AS
SELECT 
    user_id, 
    SUM(amount) as total_ltv, 
    COUNT(user_id) as event_count
FROM `{{ gcp_project }}.{{ bq_dataset }}.events`
GROUP BY user_id
HAVING SUM(amount) > 0
ORDER BY total_ltv DESC;
