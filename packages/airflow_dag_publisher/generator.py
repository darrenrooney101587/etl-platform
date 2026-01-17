"""DAG template generator.

Generates Airflow DAG files from Jinja2 templates.
"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from jinja2 import Environment, FileSystemLoader, Template


logger = logging.getLogger(__name__)


class DAGGenerator:
    """Generates Airflow DAG files from templates."""

    def __init__(self, template_dir: Optional[Path] = None):
        """Initialize the generator.

        Args:
            template_dir: Directory containing Jinja2 templates.
                         Defaults to the templates/ directory in this package.
        """
        if template_dir is None:
            template_dir = Path(__file__).parent / "templates"

        self.template_dir = template_dir
        self.env = Environment(
            loader=FileSystemLoader(str(template_dir)),
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def generate_kubernetes_pod_dag(
        self,
        package_name: str,
        dag_id: str,
        job_name: str,
        image_tag: str,
        output_path: Path,
        description: str = "",
        schedule_interval: str = "@daily",
        retries: int = 2,
        retry_delay_minutes: int = 5,
        execution_timeout_minutes: int = 60,
        kubernetes_namespace: str = "etl-jobs",
        service_account_name: Optional[str] = None,
        cpu_request: str = "500m",
        cpu_limit: str = "1000m",
        memory_request: str = "512Mi",
        memory_limit: str = "1Gi",
        image_pull_policy: str = "IfNotPresent",
        env_vars: Optional[Dict[str, str]] = None,
        extra_args: Optional[list[str]] = None,
        tags: Optional[list[str]] = None,
        email_on_failure: bool = False,
        catchup: bool = False,
        max_active_runs: int = 1,
    ) -> Path:
        """Generate a DAG using KubernetesPodOperator.

        Args:
            package_name: Name of the package.
            dag_id: Unique DAG identifier.
            job_name: Name of the job to run.
            image_tag: Full container image URI with tag.
            output_path: Path where the generated DAG file will be written.
            description: Human-readable description of the DAG.
            schedule_interval: Cron expression or preset (@daily, @hourly, etc).
            retries: Number of retries on failure.
            retry_delay_minutes: Minutes to wait between retries.
            execution_timeout_minutes: Maximum execution time before timeout.
            kubernetes_namespace: K8s namespace for job execution.
            service_account_name: K8s service account (for IRSA).
            cpu_request: CPU resource request.
            cpu_limit: CPU resource limit.
            memory_request: Memory resource request.
            memory_limit: Memory resource limit.
            image_pull_policy: Image pull policy (IfNotPresent, Always, Never).
            env_vars: Environment variables as dict.
            extra_args: Additional CLI arguments for the job.
            tags: List of tags for the DAG.
            email_on_failure: Whether to send email on failure.
            catchup: Whether to catch up on missed runs.
            max_active_runs: Maximum number of concurrent runs.

        Returns:
            Path to the generated DAG file.
        """
        template = self.env.get_template("kubernetes_pod_dag.py.j2")

        # Default values
        if service_account_name is None:
            service_account_name = package_name.replace("_", "-")

        if tags is None:
            tags = [package_name]

        if env_vars is None:
            env_vars = {}

        if extra_args is None:
            extra_args = []

        # Build command and arguments
        cmds = [job_name]
        arguments = extra_args

        # Start date (default to current date)
        now = datetime.now()

        context = {
            "package_name": package_name,
            "dag_id": dag_id,
            "task_id": f"run_{job_name}",
            "job_name": job_name,
            "image_tag": image_tag,
            "description": description or f"Run {job_name} from {package_name}",
            "timestamp": datetime.now().isoformat(),
            "schedule_interval": schedule_interval,
            "start_year": now.year,
            "start_month": now.month,
            "start_day": now.day,
            "retries": retries,
            "retry_delay_minutes": retry_delay_minutes,
            "execution_timeout_minutes": execution_timeout_minutes,
            "kubernetes_namespace": kubernetes_namespace,
            "service_account_name": service_account_name,
            "cpu_request": cpu_request,
            "cpu_limit": cpu_limit,
            "memory_request": memory_request,
            "memory_limit": memory_limit,
            "image_pull_policy": image_pull_policy,
            "cmds": repr(cmds),
            "arguments": repr(arguments),
            "env_vars": repr(env_vars),
            "tags": repr(tags),
            "email_on_failure": email_on_failure,
            "catchup": catchup,
            "max_active_runs": max_active_runs,
        }

        rendered = template.render(**context)

        # Write to output file
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            f.write(rendered)

        logger.info("Generated DAG file: %s", output_path)
        return output_path
