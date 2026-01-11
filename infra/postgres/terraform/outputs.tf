output "db_connection_url" {
  description = "Postgres connection URL"
  value       = "postgresql://${aws_db_instance.postgres.username}:${var.db_password != "" ? var.db_password : random_password.db_password.result}@${aws_db_instance.postgres.address}:${aws_db_instance.postgres.port}/${aws_db_instance.postgres.db_name}"
  sensitive   = true
}

output "rds_endpoint" {
  value = aws_db_instance.postgres.address
}
