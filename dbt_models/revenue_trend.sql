-- Revenue Trends Model
-- Time-based aggregation using TIMESTAMP_TRUNC for Tableau time-series charts

SELECT 
    TIMESTAMP_TRUNC(timestamp, HOUR) AS revenue_hour,
    COUNT(CASE WHEN event_type = 'purchase' THEN 1 END) AS purchase_count,
    SUM(CASE WHEN event_type = 'purchase' THEN amount ELSE 0 END) AS total_revenue
FROM `{{ config.GCP_PROJECT_ID }}.{{ config.GCP_BQ_DATASET }}.events`
WHERE event_type = 'purchase'
GROUP BY revenue_hour
ORDER BY revenue_hour DESC;
