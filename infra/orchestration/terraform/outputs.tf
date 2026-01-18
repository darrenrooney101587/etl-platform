output "dag_bucket_name" {
  description = "Name of the S3 bucket for DAGs"
  value       = aws_s3_bucket.dags.id
}

output "dag_bucket_arn" {
  description = "ARN of the S3 bucket for DAGs"
  value       = aws_s3_bucket.dags.arn
}

output "airflow_service_account_role_arn" {
  description = "ARN of the IAM role for Airflow service account (IRSA)"
  value       = aws_iam_role.airflow_service_account.arn
}

output "package_dag_write_policy_arn" {
  description = "ARN of the IAM policy for package CI to write DAGs"
  value       = aws_iam_policy.package_dag_write.arn
}

output "s3_dag_prefix" {
  description = "S3 prefix for DAGs in this environment"
  value       = "s3://${aws_s3_bucket.dags.id}/${var.environment}"
}
