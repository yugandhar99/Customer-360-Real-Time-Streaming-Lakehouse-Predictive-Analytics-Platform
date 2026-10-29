-- Athena equivalent of the LTV metric used by transformations/ltv_analysis.py.
-- BigQuery SQL in gcp_sql_models/ and dbt_models/ is unchanged.
SELECT
    user_id,
    SUM(amount) AS total_ltv,
    COUNT(user_id) AS event_count
FROM {{database}}.events
GROUP BY user_id
HAVING SUM(amount) > 0
ORDER BY total_ltv DESC
