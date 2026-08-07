"""MinIO / S3-compatible object storage client for permanent document storage.

Replaces v1's local ``data/uploads`` disk storage (architecture review §3):
raw files live at ``orgs/{org_id}/docs/{doc_id}/original.pdf`` so documents
survive redeploys and are never resolvable without the owning org's id.
"""

from __future__ import annotations

import uuid
from functools import lru_cache

import boto3
from botocore.client import BaseClient, Config
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import get_settings

PRESIGNED_URL_EXPIRY_SECONDS = 3600


class StorageError(Exception):
    """Raised when object storage operations fail."""


@lru_cache
def get_s3_client() -> BaseClient:
    """Return a cached boto3 client configured for the MinIO/S3 endpoint."""
    settings = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name=settings.s3_region,
        config=Config(signature_version="s3v4"),
        use_ssl=settings.s3_use_ssl,
    )


def ensure_bucket_exists() -> None:
    """Create the configured bucket if it does not already exist."""
    settings = get_settings()
    client = get_s3_client()
    try:
        client.head_bucket(Bucket=settings.s3_bucket_name)
    except ClientError:
        try:
            client.create_bucket(Bucket=settings.s3_bucket_name)
        except (ClientError, BotoCoreError) as exc:
            raise StorageError(f"Failed to create bucket '{settings.s3_bucket_name}': {exc}") from exc


def build_object_key(org_id: uuid.UUID, doc_id: uuid.UUID, filename: str) -> str:
    """Return the deterministic storage path for a document's original file."""
    return f"orgs/{org_id}/docs/{doc_id}/{filename}"


def upload_bytes(object_key: str, file_bytes: bytes, content_type: str = "application/pdf") -> None:
    """Upload raw bytes to the configured bucket at the given key."""
    settings = get_settings()
    client = get_s3_client()
    try:
        client.put_object(
            Bucket=settings.s3_bucket_name,
            Key=object_key,
            Body=file_bytes,
            ContentType=content_type,
        )
    except (ClientError, BotoCoreError) as exc:
        raise StorageError(f"Failed to upload '{object_key}' to object storage: {exc}") from exc


def download_bytes(object_key: str) -> bytes:
    """Download raw bytes for the given object key."""
    settings = get_settings()
    client = get_s3_client()
    try:
        response = client.get_object(Bucket=settings.s3_bucket_name, Key=object_key)
        return response["Body"].read()
    except (ClientError, BotoCoreError) as exc:
        raise StorageError(f"Failed to download '{object_key}' from object storage: {exc}") from exc


def generate_presigned_url(object_key: str, expires_in: int = PRESIGNED_URL_EXPIRY_SECONDS) -> str:
    """Generate a time-limited download URL for an object."""
    settings = get_settings()
    client = get_s3_client()
    try:
        return client.generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.s3_bucket_name, "Key": object_key},
            ExpiresIn=expires_in,
        )
    except (ClientError, BotoCoreError) as exc:
        raise StorageError(f"Failed to generate presigned URL for '{object_key}': {exc}") from exc
