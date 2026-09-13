"""Per-MDN credentials are injected from a private file, never from telemetry payloads."""
import json
import hashlib
import os
import re
import stat
import time
import uuid
from dataclasses import dataclass, field
from urllib.parse import urlsplit


@dataclass(frozen=True)
class CredentialBinding:
    """Queue identity only: no raw key, and no fingerprint in repr/log output."""
    mdn: str = field(repr=False)
    device_id: int
    fingerprint: str = field(repr=False)


@dataclass(frozen=True)
class DeviceCredentialSnapshot:
    """Short-lived request credentials; never retain this object in a pending queue."""
    binding: CredentialBinding
    _key: str = field(repr=False)

    def headers(self) -> dict:
        return {"X-Device-Id": str(self.binding.device_id), "X-Device-Key": self._key,
                "X-Request-Id": str(uuid.uuid4()), "X-Request-Timestamp": str(int(time.time()))}


def validate_backend_url(backend_url: str) -> str:
    """Validate before any logging or HTTP, including the unauthenticated startup probe."""
    error_message = "HTTPS backend origin required (loopback HTTP allowed); userinfo/query/fragment prohibited"
    try:
        if not isinstance(backend_url, str) or any(character.isspace() for character in backend_url):
            raise ValueError(error_message)
        target = urlsplit(backend_url)
        if (target.username is not None or target.password is not None or target.query or target.fragment
                or not target.hostname or target.path not in ("", "/")
                or (target.port is not None and target.port == 0)
                or not (target.scheme == "https" or (
                    target.scheme == "http" and target.hostname in ("localhost", "127.0.0.1", "::1")))):
            raise ValueError(error_message)
    except ValueError:
        # Parser errors may contain input; only a fixed message crosses this boundary.
        raise ValueError(error_message) from None
    return backend_url.rstrip("/")


def load_device_credential(mdn: str, backend_url: str) -> DeviceCredentialSnapshot:
    validate_backend_url(backend_url)
    path = os.environ.get("DEVICE_CREDENTIALS_FILE")
    if not path:
        raise ValueError("DEVICE_CREDENTIALS_FILE required")
    try:
        with open(path, encoding="utf-8") as source:
            metadata = os.fstat(source.fileno())
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_mode & 0o077 or metadata.st_size > 1_048_576:
                raise ValueError("Private credential file required")
            values = json.loads(source.read(1_048_577))
        entry = values[mdn]
        device_id, key = entry["device_id"], entry["key"]
        if (type(device_id) is not int or not 0 < device_id <= 9223372036854775807
                or not isinstance(key, str) or not re.fullmatch(r"twdev_[A-Za-z0-9_-]{43}", key)):
            raise ValueError("Invalid credential")
    except (OSError, ValueError, TypeError, KeyError):
        raise ValueError("Device credential unavailable or invalid") from None
    binding = CredentialBinding(mdn, device_id, hashlib.sha256(key.encode("utf-8")).hexdigest())
    return DeviceCredentialSnapshot(binding, key)


def device_headers(mdn: str, backend_url: str) -> dict:
    return load_device_credential(mdn, backend_url).headers()
