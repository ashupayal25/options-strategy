"""Secret lookup: environment variable first, then SSM Parameter Store when OTM_SSM_PREFIX is set."""
import logging
import os

log = logging.getLogger("otm.credentials")


def get_secret(name, ssm_leaf, *, env=None, ssm_client=None):
    env = os.environ if env is None else env
    value = (env.get(name) or "").strip()
    if value:
        return value
    prefix = (env.get("OTM_SSM_PREFIX") or "").rstrip("/")
    if not prefix:
        return None
    try:
        if ssm_client is None:
            import boto3
            ssm_client = boto3.client("ssm")
        resp = ssm_client.get_parameter(Name=f"{prefix}/{ssm_leaf}", WithDecryption=True)
        return resp["Parameter"]["Value"].strip()
    except Exception as e:
        log.warning("could not read SSM parameter %s/%s (%s)", prefix, ssm_leaf, type(e).__name__)
        return None
