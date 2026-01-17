"""
Reporting Seeder Refresh All DAG

This DAG executes the reporting_seeder refresh_all job using KubernetesPodOperator.
"""
from datetime import datetime, timedelta

from airflow import DAG
from airflow.providers.cncf.kubernetes.operators.kubernetes_pod import (
    KubernetesPodOperator,
)
from kubernetes.client import models as k8s


default_args = {
    "owner": "reporting_seeder",
    "depends_on_past": False,
    "email_on_failure": True,
    "email_on_retry": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=10),
    "execution_timeout": timedelta(hours=2),
}

with DAG(
    dag_id="reporting_seeder_refresh_all",
    default_args=default_args,
    description="Refresh all reporting tables",
    schedule_interval="0 2 * * *",  # Daily at 2 AM
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["reporting_seeder", "refresh"],
    max_active_runs=1,
) as dag:

    refresh_all_tables = KubernetesPodOperator(
        task_id="refresh_all_tables",
        name="reporting-seeder-refresh-all",
        namespace="etl-jobs",
        # Replace with actual image tag from CI
        image="270022076279.dkr.ecr.us-gov-west-1.amazonaws.com/reporting-seeder:latest",
        image_pull_policy="IfNotPresent",
        cmds=["reporting-seeder"],
        arguments=["run", "refresh_all"],
        env_vars={
            "ENVIRONMENT": "dev",
            "DJANGO_SETTINGS_MODULE": "reporting_seeder.settings",
        },
        container_resources=k8s.V1ResourceRequirements(
            requests={
                "cpu": "1000m",
                "memory": "2Gi",
            },
            limits={
                "cpu": "2000m",
                "memory": "4Gi",
            },
        ),
        service_account_name="reporting-seeder",
        get_logs=True,
        log_events_on_failure=True,
        is_delete_operator_pod=True,
        security_context={
            "runAsNonRoot": True,
            "runAsUser": 1000,
            "fsGroup": 1000,
        },
        restart_policy="Never",
    )
