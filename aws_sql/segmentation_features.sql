-- Customer-level features consumed by K-Means segmentation.
SELECT
    user_id,
    COUNT(timestamp) AS frequency,
    SUM(amount) AS monetary
FROM {{database}}.events
GROUP BY user_id
