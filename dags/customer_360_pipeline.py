from airflow import DAG
from airflow.providers.google.cloud.operators.bigquery import BigQueryInsertJobOperator
from airflow.operators.bash import BashOperator
from airflow.operators.empty import EmptyOperator
from airflow.utils.dates import days_ago
from datetime import timedelta
import os
import sys

# Resolve paths from this repository so the DAG works from any checkout.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)

try:
    from config import config
    PROJECT_ID = config.GCP_PROJECT_ID
    DATASET = config.GCP_BQ_DATASET
except ImportError:
    PROJECT_ID = "customer-360-492614"
    DATASET = "customer_360"

DBT_DIR = os.path.join(PROJECT_ROOT, "dbt_models")

def read_sql_file(filename):
    """Utility to read raw SQL from folder and inject environments."""
    file_path = os.path.join(DBT_DIR, filename)
    if not os.path.exists(file_path):
        return f"SELECT 'Missing file: {filename}'"
    with open(file_path, 'r') as f:
        sql = f.read()
        sql = sql.replace('{{ config.GCP_PROJECT_ID }}', PROJECT_ID)
        sql = sql.replace('{{ config.GCP_BQ_DATASET }}', DATASET) # Handle dbt-like config injection
        return sql

default_args = {
    'owner': 'data_engineering',
    'depends_on_past': False,
    'email_on_failure': True,
    'email_on_retry': False,
    'retries': 2,
    'retry_delay': timedelta(minutes=5),
}

with DAG(
    'enterprise_customer_360_pipeline',
    default_args=default_args,
    description='Enterprise Airflow DAG for streaming analytics & ML pipelines',
    schedule_interval='@daily',
    start_date=days_ago(1),
    tags=['gcp', 'bigquery', 'ml', 'dbt'],
    catchup=False,
) as dag:

    # ==========================
    # Phase 1: Pipeline Intention
    # ==========================
    start_pipeline = EmptyOperator(task_id='start_pipeline')
    verify_extraction = EmptyOperator(task_id='verify_pubsub_to_bq_ingestion', doc_md="Extraction is handled automatically via async PubSub consumer script running as a streaming agent.")

    # ==========================
    # Phase 2: Transformation (dbt-style SQL mapping over to BigQuery Table views)
    # ==========================
    transform_ltv = BigQueryInsertJobOperator(
        task_id='dbt_model_ltv',
        configuration={
            "query": {
                "query": f"CREATE OR REPLACE TABLE `{PROJECT_ID}.{DATASET}.ltv_metrics` AS \n" + read_sql_file('ltv.sql'),
                "useLegacySql": False,
            }
        }
    )

    transform_funnel = BigQueryInsertJobOperator(
        task_id='dbt_model_funnel',
        configuration={
            "query": {
                "query": f"CREATE OR REPLACE TABLE `{PROJECT_ID}.{DATASET}.funnel_metrics` AS \n" + read_sql_file('funnel.sql'),
                "useLegacySql": False,
            }
        }
    )

    transform_retention = BigQueryInsertJobOperator(
        task_id='dbt_model_retention',
        configuration={
            "query": {
                "query": f"CREATE OR REPLACE TABLE `{PROJECT_ID}.{DATASET}.retention_metrics` AS \n" + read_sql_file('retention.sql'),
                "useLegacySql": False,
            }
        }
    )
    
    transform_revenue = BigQueryInsertJobOperator(
        task_id='dbt_model_revenue',
        configuration={
            "query": {
                "query": f"CREATE OR REPLACE TABLE `{PROJECT_ID}.{DATASET}.revenue_trend` AS \n" + read_sql_file('revenue_trend.sql'),
                "useLegacySql": False,
            }
        }
    )

    # ==========================
    # Phase 3: Machine Learning Models
    # ==========================
    train_segmentation = BashOperator(
        task_id='ml_customer_segmentation',
        bash_command=f'python {PROJECT_ROOT}/ml/segmentation.py'
    )

    train_churn = BashOperator(
        task_id='ml_predict_churn',
        bash_command=f'python {PROJECT_ROOT}/ml/churn_model.py'
    )
    
    end_pipeline = EmptyOperator(task_id='end_pipeline')

    # ==========================
    # Task Dependencies execution hierarchy
    # ==========================
    start_pipeline >> verify_extraction
    
    verify_extraction >> [transform_ltv, transform_funnel, transform_retention, transform_revenue]
    
    [transform_ltv, transform_funnel, transform_retention, transform_revenue] >> train_segmentation
    [transform_ltv, transform_funnel, transform_retention, transform_revenue] >> train_churn
    
    [train_segmentation, train_churn] >> end_pipeline
