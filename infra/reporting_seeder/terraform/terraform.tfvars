region = "us-gov-west-1"
foundation_state_bucket = "<foundation-state-bucket>"
foundation_state_key    = "foundation_network/terraform.tfstate"
foundation_state_region = "us-gov-west-1"

name_prefix = "reporting-seeder"

image = "<account>.dkr.ecr.us-gov-west-1.amazonaws.com/reporting-seeder:latest"

db_host = "localhost"
db_port = 5432
db_name = "postgres"
db_user = "postgres"
db_password = "postgres"

cron_schedule = "0 8 * * *"
