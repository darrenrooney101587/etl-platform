output "vpc_id" {
  value       = aws_vpc.main.id
  description = "VPC id"
}

output "public_subnet_ids" {
  value       = [for s in aws_subnet.public : s.id]
  description = "Public subnet ids"
}

output "private_subnet_ids" {
  value       = [for s in aws_subnet.private : s.id]
  description = "Private subnet ids"
}
