import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings

FILE_BLOB_ENCRYPTION_PREFIX = b"OAENC1:"


def _coerce_bytes(value) -> bytes:
    if value is None:
        return b""
    if isinstance(value, memoryview):
        return bytes(value)
    if isinstance(value, bytearray):
        return bytes(value)
    if isinstance(value, bytes):
        return value
    return bytes(value)


def _derive_fernet_key(raw_key: str) -> bytes:
    digest = hashlib.sha256(raw_key.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def get_file_blob_fernet() -> Fernet:
    raw_key = str(getattr(settings, "IMPORT_FILE_BLOB_ENCRYPTION_KEY", "") or "").strip()
    if not raw_key:
        raw_key = str(getattr(settings, "MEMBER_CERTIFICAT_ENCRYPTION_KEY", "") or "").strip()
    if not raw_key:
        raw_key = str(getattr(settings, "SECRET_KEY", "") or "").strip()

    if not raw_key:
        raise ValueError("No encryption key available for import file blobs.")

    try:
        return Fernet(raw_key.encode("utf-8"))
    except Exception:
        return Fernet(_derive_fernet_key(raw_key))


def is_file_blob_encrypted(value) -> bool:
    raw = _coerce_bytes(value)
    return bool(raw) and raw.startswith(FILE_BLOB_ENCRYPTION_PREFIX)


def encrypt_file_blob(value) -> bytes | None:
    if value is None:
        return None

    raw = _coerce_bytes(value)
    if not raw:
        return b""
    if is_file_blob_encrypted(raw):
        return raw

    token = get_file_blob_fernet().encrypt(raw)
    return FILE_BLOB_ENCRYPTION_PREFIX + token


def decrypt_file_blob(value) -> bytes | None:
    if value is None:
        return None

    raw = _coerce_bytes(value)
    if not raw:
        return b""
    if not is_file_blob_encrypted(raw):
        return raw

    token = raw[len(FILE_BLOB_ENCRYPTION_PREFIX) :]
    try:
        return get_file_blob_fernet().decrypt(token)
    except InvalidToken as exc:
        raise ValueError("Unable to decrypt file blob with configured key.") from exc
