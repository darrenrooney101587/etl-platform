aws_region  = "us-gov-west-1"
aws_profile = "etl-playground"
environment = "dev"

db_name              = "etl_db"
db_username          = "etl_user"
db_allocated_storage = 20
db_instance_class    = "db.t3.medium"

# Network configuration reusing foundation
vpc_id        = "vpc-02ce49f37b7574a7f"
subnet_ids    = ["subnet-04e1c3f2691081ac7", "subnet-00e5ce2dff9918453"]
public_access = true

# NOTE: RDS master password must not contain '/', '@', '"' or spaces
# Use only printable ASCII except those characters.
db_password = "Password123!#"
