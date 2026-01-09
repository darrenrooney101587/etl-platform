locals {
  name_prefix = "${var.environment}-postgres-on-demand"
  common_tags = merge({
    Name        = local.name_prefix,
    Environment = var.environment,
    ManagedBy   = "terraform-on-demand"
  }, var.tags)
}

resource "random_password" "db_password" {
  length           = 24
  override_char_set = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%&*()-_+="
  keepers = {
    # rotate only when explicit input password changes
    input_pass = var.db_password
  }
}

# Create a minimal VPC if vpc_id isn't provided
resource "aws_vpc" "minimal" {
  count             = var.vpc_id == "" ? 1 : 0
  cidr_block        = "10.100.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support = true
  tags              = local.common_tags
}

# Create two private subnets across two AZs for RDS
resource "aws_subnet" "private" {
  count = length(var.subnet_ids) > 0 ? 0 : (var.vpc_id == "" ? 2 : 0)
  vpc_id = aws_vpc.minimal[0].id
  cidr_block = cidrsubnet(aws_vpc.minimal[0].cidr_block, 8, count.index)
  availability_zone = data.aws_availability_zones.available.names[count.index]
  tags = merge(local.common_tags, { Name = "${local.name_prefix}-subnet-${count.index}" })
}

# If caller provided subnet_ids, use them. Otherwise, if we created subnets use them.
# If a vpc_id was provided and no subnet_ids, attempt to use discovered subnets from data.aws_subnets.
locals {
  rds_subnet_ids = length(var.subnet_ids) > 0 ? var.subnet_ids : (
    var.vpc_id == "" ? aws_subnet.private[*].id : (
      length(data.aws_subnets.vpc_subnets) > 0 ? data.aws_subnets.vpc_subnets[0].ids : []
    )
  )
}

# If vpc_id is provided but no subnets provided, attempt to discover private subnets
data "aws_availability_zones" "available" {}

data "aws_subnets" "vpc_subnets" {
  count = var.vpc_id != "" && length(var.subnet_ids) == 0 ? 1 : 0
  filter {
    name   = "vpc-id"
    values = [var.vpc_id]
  }
}

# Security group allowing access from caller's IP if provided via env or 0.0.0.0/0 for convenience when public_access=true
resource "aws_security_group" "db_sg" {
  name        = "${local.name_prefix}-sg"
  description = "Security group for on-demand postgres"
  vpc_id      = var.vpc_id != "" ? var.vpc_id : (aws_vpc.minimal[0].id)
  tags        = local.common_tags

  ingress {
    description = "Postgres access"
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = var.public_access ? ["0.0.0.0/0"] : []
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# RDS subnet group
resource "aws_db_subnet_group" "rds_subnet_group" {
  name       = "${local.name_prefix}-subnet-group"
  subnet_ids = local.rds_subnet_ids
  tags       = local.common_tags
}

# RDS instance
resource "aws_db_instance" "postgres" {
  identifier              = local.name_prefix
  engine                  = "postgres"
  engine_version          = "15.4"
  instance_class          = var.db_instance_class
  allocated_storage       = var.db_allocated_storage
  name                    = var.db_name
  username                = var.db_username
  password                = var.db_password != "" ? var.db_password : random_password.db_password.result
  skip_final_snapshot     = true
  publicly_accessible     = var.public_access
  multi_az                = false
  storage_encrypted       = true
  db_subnet_group_name    = aws_db_subnet_group.rds_subnet_group.name
  vpc_security_group_ids  = [aws_security_group.db_sg.id]
  tags                    = local.common_tags
  apply_immediately       = true
  deletion_protection     = false
}

# Outputs
output "db_endpoint" {
  value = aws_db_instance.postgres.address
}

output "db_port" {
  value = aws_db_instance.postgres.port
}

output "db_username" {
  value = aws_db_instance.postgres.username
}

output "db_password" {
  value     = var.db_password != "" ? var.db_password : random_password.db_password.result
  sensitive = true
}

output "rds_identifier" {
  value = aws_db_instance.postgres.id
}
