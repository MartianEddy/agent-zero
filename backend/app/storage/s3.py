import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from app.core.config import get_settings


def s3_client():
    settings = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=settings.object_storage_endpoint,
        aws_access_key_id=settings.object_storage_access_key,
        aws_secret_access_key=settings.object_storage_secret_key,
        region_name=settings.object_storage_region,
        use_ssl=settings.object_storage_secure,
        config=Config(s3={"addressing_style": "path"}),
    )


def check_bucket() -> None:
    settings = get_settings()
    s3_client().head_bucket(Bucket=settings.object_storage_bucket)


def put_private_object(*, key: str, data: bytes, content_type: str) -> None:
    settings = get_settings()
    options: dict[str, str] = {}
    if settings.object_storage_secure:
        options["ServerSideEncryption"] = "AES256"
    s3_client().put_object(
        Bucket=settings.object_storage_bucket,
        Key=key,
        Body=data,
        ContentType=content_type,
        **options,
    )


def get_private_object(*, key: str) -> bytes:
    settings = get_settings()
    response = s3_client().get_object(Bucket=settings.object_storage_bucket, Key=key)
    return response["Body"].read()


def delete_private_object(*, key: str) -> None:
    settings = get_settings()
    try:
        s3_client().delete_object(Bucket=settings.object_storage_bucket, Key=key)
    except ClientError:
        raise
