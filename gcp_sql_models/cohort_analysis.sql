-- Cohort Analysis View Model
-- Grouping users by their earliest touch point
CREATE OR REPLACE TABLE `{{ gcp_project }}.{{ bq_dataset }}.cohort_metrics` AS
WITH SignupDates AS (
    SELECT 
        user_id, 
        DATE(MIN(timestamp)) as signup_date
    FROM `{{ gcp_project }}.{{ bq_dataset }}.events`
    GROUP BY user_id
)
SELECT 
    CAST(signup_date AS STRING) as cohort_day,
    COUNT(user_id) as user_count
FROM SignupDates
GROUP BY signup_date
ORDER BY signup_date ASC;
