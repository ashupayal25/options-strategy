"""Where app state lives: local files or an S3 prefix. State is positions.json, report text files and cached bars."""
import logging
from pathlib import Path
from urllib.parse import urlparse

from .paths import ROOT

log = logging.getLogger("otm.storage")


class LocalStore:
    def __init__(self, root):
        self.root = Path(root)

    def read_text(self, key):
        path = self.root / key
        return path.read_text(encoding="utf-8") if path.exists() else None

    def write_text(self, key, text):
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def describe(self, key):
        return str(self.root / key)


class S3Store:
    def __init__(self, bucket, prefix="", client=None):
        self.bucket = bucket
        self.prefix = prefix.strip("/")
        self._client = client

    @property
    def client(self):
        if self._client is None:
            import boto3
            self._client = boto3.client("s3")
        return self._client

    def _key(self, key):
        return f"{self.prefix}/{key}" if self.prefix else key

    def read_text(self, key):
        try:
            obj = self.client.get_object(Bucket=self.bucket, Key=self._key(key))
            return obj["Body"].read().decode("utf-8")
        except Exception as e:
            code = getattr(e, "response", {}).get("Error", {}).get("Code", "")
            if code in ("NoSuchKey", "404", "NotFound"):
                return None
            raise

    def write_text(self, key, text):
        self.client.put_object(Bucket=self.bucket, Key=self._key(key), Body=text.encode("utf-8"),
                               ContentType="text/plain; charset=utf-8")

    def describe(self, key):
        return f"s3://{self.bucket}/{self._key(key)}"


def make_store(spec=None):
    """spec: 's3://bucket/prefix', a folder path, or None/'' for the project folder. Falls back to OTM_STORE."""
    import os
    spec = os.environ.get("OTM_STORE", "") if spec is None else spec
    if spec.startswith("s3://"):
        u = urlparse(spec)
        return S3Store(u.netloc, u.path)
    return LocalStore(spec if spec else ROOT)
