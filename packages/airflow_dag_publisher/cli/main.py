"""CLI for airflow-dag-publisher."""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from airflow_dag_publisher.generator import DAGGenerator
from airflow_dag_publisher.publisher import DAGPublisher
from airflow_dag_publisher.validators import DAGValidator


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def cmd_generate(args: argparse.Namespace) -> int:
    """Generate a DAG file from template."""
    generator = DAGGenerator()

    output_path = Path(args.output)

    try:
        generator.generate_kubernetes_pod_dag(
            package_name=args.package_name,
            dag_id=args.dag_id,
            job_name=args.job_name,
            image_tag=args.image_tag,
            output_path=output_path,
            description=args.description or "",
            schedule_interval=args.schedule or "@daily",
            retries=args.retries,
            retry_delay_minutes=args.retry_delay,
            execution_timeout_minutes=args.timeout,
            kubernetes_namespace=args.namespace,
            service_account_name=args.service_account,
            cpu_request=args.cpu_request,
            cpu_limit=args.cpu_limit,
            memory_request=args.memory_request,
            memory_limit=args.memory_limit,
            image_pull_policy=args.image_pull_policy,
            env_vars=_parse_env_vars(args.env_vars),
            extra_args=args.job_args or [],
            tags=args.tags or [args.package_name],
            email_on_failure=args.email_on_failure,
            catchup=args.catchup,
            max_active_runs=args.max_active_runs,
        )

        logger.info("DAG generated successfully: %s", output_path)
        return 0

    except Exception as e:
        logger.error("Failed to generate DAG: %s", e)
        return 1


def cmd_validate(args: argparse.Namespace) -> int:
    """Validate a DAG file."""
    validator = DAGValidator(args.package_name)

    try:
        dag_file = Path(args.dag_file)
        validator.validate_file(dag_file)
        logger.info("DAG validation passed: %s", dag_file)
        return 0

    except Exception as e:
        logger.error("DAG validation failed: %s", e)
        return 1


def cmd_publish(args: argparse.Namespace) -> int:
    """Publish DAG files to S3."""
    publisher = DAGPublisher(
        bucket=args.bucket,
        environment=args.environment,
        package_name=args.package_name,
        aws_region=args.aws_region,
    )

    # Verify bucket exists
    if not publisher.verify_bucket_exists():
        logger.error("Cannot access S3 bucket: %s", args.bucket)
        return 1

    # Validate DAGs before publishing
    if args.validate:
        validator = DAGValidator(args.package_name)
        for dag_file in _get_dag_files(args.dag_path):
            try:
                validator.validate_file(dag_file)
            except Exception as e:
                logger.error("Validation failed for %s: %s", dag_file, e)
                return 1

    try:
        dag_path = Path(args.dag_path)

        if dag_path.is_file():
            s3_key = publisher.publish_dag_file(dag_path)
            logger.info("Published: %s", s3_key)
        else:
            s3_keys = publisher.publish_directory(dag_path)
            logger.info("Published %d DAGs:", len(s3_keys))
            for key in s3_keys:
                logger.info("  - %s", key)

        return 0

    except Exception as e:
        logger.error("Failed to publish DAGs: %s", e)
        return 1


def cmd_list(args: argparse.Namespace) -> int:
    """List published DAGs."""
    publisher = DAGPublisher(
        bucket=args.bucket,
        environment=args.environment,
        package_name=args.package_name,
        aws_region=args.aws_region,
    )

    try:
        dags = publisher.list_published_dags()
        if dags:
            logger.info("Published DAGs for %s:", args.package_name)
            for dag in dags:
                print(dag)
        else:
            logger.info("No DAGs found for %s", args.package_name)
        return 0

    except Exception as e:
        logger.error("Failed to list DAGs: %s", e)
        return 1


def _parse_env_vars(env_vars: list[str] | None) -> dict[str, str]:
    """Parse environment variables from KEY=VALUE format."""
    if not env_vars:
        return {}

    result = {}
    for item in env_vars:
        if "=" not in item:
            logger.warning("Ignoring invalid env var (no '='): %s", item)
            continue
        key, value = item.split("=", 1)
        result[key] = value

    return result


def _get_dag_files(path: Path | str) -> list[Path]:
    """Get list of DAG files from path."""
    path = Path(path)
    if path.is_file():
        return [path]
    return list(path.glob("*.py"))


def main() -> int:
    """Main CLI entrypoint."""
    parser = argparse.ArgumentParser(
        prog="airflow-dag-publisher",
        description="Generate and publish Airflow DAGs to S3",
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Generate command
    gen_parser = subparsers.add_parser("generate", help="Generate a DAG file")
    gen_parser.add_argument(
        "--package-name",
        required=True,
        help="Package name (e.g., data_pipeline)",
    )
    gen_parser.add_argument(
        "--dag-id",
        required=True,
        help="Unique DAG ID (e.g., data_pipeline_example)",
    )
    gen_parser.add_argument(
        "--job-name",
        required=True,
        help="Job name to run (e.g., example_job)",
    )
    gen_parser.add_argument(
        "--image-tag",
        required=True,
        help="Full container image with tag (e.g., 123456.dkr.ecr.../data-pipeline:v1.0.0)",
    )
    gen_parser.add_argument(
        "--output",
        required=True,
        help="Output path for generated DAG file",
    )
    gen_parser.add_argument(
        "--description",
        help="DAG description",
    )
    gen_parser.add_argument(
        "--schedule",
        default="@daily",
        help="Schedule interval (cron or preset) [default: @daily]",
    )
    gen_parser.add_argument(
        "--retries",
        type=int,
        default=2,
        help="Number of retries [default: 2]",
    )
    gen_parser.add_argument(
        "--retry-delay",
        type=int,
        default=5,
        help="Retry delay in minutes [default: 5]",
    )
    gen_parser.add_argument(
        "--timeout",
        type=int,
        default=60,
        help="Execution timeout in minutes [default: 60]",
    )
    gen_parser.add_argument(
        "--namespace",
        default="etl-jobs",
        help="Kubernetes namespace [default: etl-jobs]",
    )
    gen_parser.add_argument(
        "--service-account",
        help="Kubernetes service account (defaults to package name)",
    )
    gen_parser.add_argument(
        "--cpu-request",
        default="500m",
        help="CPU request [default: 500m]",
    )
    gen_parser.add_argument(
        "--cpu-limit",
        default="1000m",
        help="CPU limit [default: 1000m]",
    )
    gen_parser.add_argument(
        "--memory-request",
        default="512Mi",
        help="Memory request [default: 512Mi]",
    )
    gen_parser.add_argument(
        "--memory-limit",
        default="1Gi",
        help="Memory limit [default: 1Gi]",
    )
    gen_parser.add_argument(
        "--image-pull-policy",
        default="IfNotPresent",
        choices=["IfNotPresent", "Always", "Never"],
        help="Image pull policy [default: IfNotPresent]",
    )
    gen_parser.add_argument(
        "--env-vars",
        nargs="*",
        help="Environment variables as KEY=VALUE pairs",
    )
    gen_parser.add_argument(
        "--job-args",
        nargs="*",
        help="Additional arguments to pass to the job",
    )
    gen_parser.add_argument(
        "--tags",
        nargs="*",
        help="DAG tags",
    )
    gen_parser.add_argument(
        "--email-on-failure",
        action="store_true",
        help="Send email on failure",
    )
    gen_parser.add_argument(
        "--catchup",
        action="store_true",
        help="Enable catchup for missed runs",
    )
    gen_parser.add_argument(
        "--max-active-runs",
        type=int,
        default=1,
        help="Maximum concurrent runs [default: 1]",
    )

    # Validate command
    val_parser = subparsers.add_parser("validate", help="Validate a DAG file")
    val_parser.add_argument(
        "--package-name",
        required=True,
        help="Package name",
    )
    val_parser.add_argument(
        "--dag-file",
        required=True,
        help="Path to DAG file to validate",
    )

    # Publish command
    pub_parser = subparsers.add_parser("publish", help="Publish DAGs to S3")
    pub_parser.add_argument(
        "--bucket",
        required=True,
        help="S3 bucket name",
    )
    pub_parser.add_argument(
        "--environment",
        required=True,
        choices=["dev", "staging", "prod"],
        help="Environment name",
    )
    pub_parser.add_argument(
        "--package-name",
        required=True,
        help="Package name",
    )
    pub_parser.add_argument(
        "--dag-path",
        required=True,
        help="Path to DAG file or directory",
    )
    pub_parser.add_argument(
        "--aws-region",
        default="us-gov-west-1",
        help="AWS region [default: us-gov-west-1]",
    )
    pub_parser.add_argument(
        "--no-validate",
        dest="validate",
        action="store_false",
        default=True,
        help="Skip validation before publishing",
    )

    # List command
    list_parser = subparsers.add_parser("list", help="List published DAGs")
    list_parser.add_argument(
        "--bucket",
        required=True,
        help="S3 bucket name",
    )
    list_parser.add_argument(
        "--environment",
        required=True,
        choices=["dev", "staging", "prod"],
        help="Environment name",
    )
    list_parser.add_argument(
        "--package-name",
        required=True,
        help="Package name",
    )
    list_parser.add_argument(
        "--aws-region",
        default="us-gov-west-1",
        help="AWS region [default: us-gov-west-1]",
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    # Dispatch to command handler
    commands = {
        "generate": cmd_generate,
        "validate": cmd_validate,
        "publish": cmd_publish,
        "list": cmd_list,
    }

    return commands[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
