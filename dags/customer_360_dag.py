from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.utils.dates import days_ago
from datetime import timedelta
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

default_args = {
    'owner': 'data_engineering_team',
    'depends_on_past': False,
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

with DAG(
    'customer_360_orchestration_pipeline',
    default_args=default_args,
    description='A simple DAG for orchestrating the Analytics & ML Pipeline',
    schedule_interval=timedelta(days=1),
    start_date=days_ago(1),
    tags=['gcp', 'analytics', 'ml'],
    catchup=False,
) as dag:

    # 1. Transform Data using SQL / Local Python scripts
    task_ltv = BashOperator(
        task_id='calculate_ltv',
        bash_command=f'python {PROJECT_ROOT}/transformations/ltv_analysis.py'
    )
    
    task_retention = BashOperator(
        task_id='calculate_retention',
        bash_command=f'python {PROJECT_ROOT}/transformations/retention_analysis.py'
    )

    task_cohorts = BashOperator(
        task_id='calculate_cohorts',
        bash_command=f'python {PROJECT_ROOT}/transformations/cohort_analysis.py'
    )

    task_funnel = BashOperator(
        task_id='calculate_funnel',
        bash_command=f'python {PROJECT_ROOT}/transformations/funnel_analysis.py'
    )

    # 2. Re-train Machine Learning Models based on new transformed data
    task_ml_segmentation = BashOperator(
        task_id='train_kmeans_segmentation',
        bash_command=f'python {PROJECT_ROOT}/ml/segmentation.py'
    )

    task_ml_churn = BashOperator(
        task_id='predict_churn',
        bash_command=f'python {PROJECT_ROOT}/ml/churn_model.py'
    )

    # Define simple dependencies
    [task_ltv, task_retention, task_cohorts, task_funnel] >> task_ml_segmentation
    [task_ltv, task_retention, task_cohorts, task_funnel] >> task_ml_churn
