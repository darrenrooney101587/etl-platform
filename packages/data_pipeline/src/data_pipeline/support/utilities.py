import os

def get_env_s3_field() -> str:
    """Return the S3 slug field name for the current environment.

    :returns: Column name used to select S3 slug in reporting.ref_agency_designations
    :rtype: str
    """
    env = os.getenv("ENVIRONMENT", "qa")
    env_map = {
        "production": "prod_s3_slug",
        "etl": "prod_s3_slug",
        "prod-staging": "prod_s3_slug",
        "sandbox2": "sandbox_s3_slug",
        "uat": "sandbox_s3_slug",
    }
    return env_map.get(env, "qa_s3_slug")

def get_env_bms_id_field() -> str:
    """Return the BMS ID field name for the current environment.

    :returns: Field name used to match agency id in reporting.ref_agency_designations
    :rtype: str
    """
    env = os.getenv("ENVIRONMENT", "qa")
    id_map = {
        "production": "prod_bms_id",
        "prod-etl": "prod_bms_id",
        "prod-staging": "prod_bms_id",
        "sandbox2": "sandbox_bms_id",
        "uat": "sandbox_bms_id",
    }
    return id_map.get(env, "qa_bms_id")
