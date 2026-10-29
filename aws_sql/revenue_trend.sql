-- Athena revenue trend. Hour buckets use date_trunc and date_parse.
SELECT
    date_trunc('hour', date_parse(timestamp, '%Y-%m-%d %H:%i:%s')) AS revenue_hour,
    COUNT(CASE WHEN event_type = 'purchase' THEN 1 END) AS purchase_count,
    SUM(CASE WHEN event_type = 'purchase' THEN amount ELSE 0 END) AS total_revenue
FROM {{database}}.events
WHERE event_type = 'purchase'
GROUP BY date_trunc('hour', date_parse(timestamp, '%Y-%m-%d %H:%i:%s'))
ORDER BY revenue_hour DESC
