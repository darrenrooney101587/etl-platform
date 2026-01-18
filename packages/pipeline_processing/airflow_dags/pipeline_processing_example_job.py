"""
Pipeline Processing Example Job DAG

This DAG executes the pipeline_processing example_job using KubernetesPodOperator.
It demonstrates the pattern for independent package deployment.
"""
from datetime import datetime, timedelta

from airflow import DAG
from airflow.providers.cncf.kubernetes.operators.kubernetes_pod import (
    KubernetesPodOperator,
)
from kubernetes.client import models as k8s


default_args = {
    "owner": "pipeline_processing",
    "depends_on_past": False,
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "execution_timeout": timedelta(minutes=30),
}

with DAG(
    dag_id="pipeline_processing_example_job",
    default_args=default_args,
    description="Run example_job from pipeline_processing package",
    schedule_interval="@daily",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["pipeline_processing", "example"],
    max_active_runs=1,
) as dag:

    run_example_job = KubernetesPodOperator(
        task_id="run_example_job",
        name="pipeline-processing-example-job",
        namespace="etl-jobs",
        # Replace with actual image tag from CI
        image="270022076279.dkr.ecr.us-gov-west-1.amazonaws.com/pipeline-processing:latest",
        image_pull_policy="IfNotPresent",
        cmds=["pipeline-processing"],
        arguments=["run", "example_job", "--name", "Airflow", "--repeat", "3"],
        env_vars={
            "ENVIRONMENT": "dev",
        },
        container_resources=k8s.V1ResourceRequirements(
            requests={
                "cpu": "500m",
                "memory": "512Mi",
            },
            limits={
                "cpu": "1000m",
                "memory": "1Gi",
            },
        ),
        service_account_name="pipeline-processing",
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
