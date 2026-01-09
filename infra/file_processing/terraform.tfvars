aws_region  = "us-gov-west-1"
aws_profile = "etl-playground"

# foundation_network tag prefix (used to discover VPC/subnets by Name tag)
foundation_name_prefix = "etl-platform"

bucket_name             = "etl-ba-research-client-etl"
create_s3_notifications = false

cluster_name    = "file-processing-cluster"
node_group_name = "file-processing-nodes"

image = "270022076279.dkr.ecr.us-gov-west-1.amazonaws.com/file-processing:latest"

# Optional: override, if needed
# vpc_id = "vpc-xxxxxxxxxxxxxxxxx"

# Optional: only set this once you have a stable endpoint (e.g., HTTPS ALB/Ingress) for SNS to call.
# sns_endpoint_url = "https://<your-endpoint>/sns"
