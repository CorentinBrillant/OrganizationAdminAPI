import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.db import migrations

FILE_BLOB_ENCRYPTION_PREFIX = b"OAENC1:"


def _coerce_bytes(value):
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


def _build_fernet() -> Fernet:
    raw_key = str(getattr(settings, "IMPORT_FILE_BLOB_ENCRYPTION_KEY", "") or "").strip()
    if not raw_key:
        raw_key = str(getattr(settings, "MEMBER_CERTIFICAT_ENCRYPTION_KEY", "") or "").strip()
    if not raw_key:
        raw_key = str(getattr(settings, "SECRET_KEY", "") or "").strip()

    if not raw_key:
        raise ValueError("No encryption key available for import file blobs migration.")

    try:
        return Fernet(raw_key.encode("utf-8"))
    except Exception:
        return Fernet(_derive_fernet_key(raw_key))


def _is_encrypted(value) -> bool:
    raw = _coerce_bytes(value)
    return bool(raw) and raw.startswith(FILE_BLOB_ENCRYPTION_PREFIX)


def _encrypt_rows(apps, schema_editor):
    fernet = _build_fernet()
    FfckExport = apps.get_model("api", "FfckExport")
    BadgeImport = apps.get_model("api", "BadgeImport")

    for model in (FfckExport, BadgeImport):
        qs = (
            model.objects.using(schema_editor.connection.alias)
            .exclude(file_blob__isnull=True)
            .only("id", "file_blob")
        )
        for row in qs.iterator(chunk_size=200):
            raw = _coerce_bytes(row.file_blob)
            if not raw or _is_encrypted(raw):
                continue
            encrypted = FILE_BLOB_ENCRYPTION_PREFIX + fernet.encrypt(raw)
            model.objects.using(schema_editor.connection.alias).filter(id=row.id).update(
                file_blob=encrypted
            )


def _decrypt_rows(apps, schema_editor):
    fernet = _build_fernet()
    FfckExport = apps.get_model("api", "FfckExport")
    BadgeImport = apps.get_model("api", "BadgeImport")

    for model in (FfckExport, BadgeImport):
        qs = (
            model.objects.using(schema_editor.connection.alias)
            .exclude(file_blob__isnull=True)
            .only("id", "file_blob")
        )
        for row in qs.iterator(chunk_size=200):
            raw = _coerce_bytes(row.file_blob)
            if not raw or not _is_encrypted(raw):
                continue
            token = raw[len(FILE_BLOB_ENCRYPTION_PREFIX) :]
            try:
                decrypted = fernet.decrypt(token)
            except InvalidToken as exc:
                raise ValueError(
                    "Unable to decrypt stored encrypted file_blob during rollback."
                ) from exc
            model.objects.using(schema_editor.connection.alias).filter(id=row.id).update(
                file_blob=decrypted
            )


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0024_alter_member_certificat_file_size_plain"),
    ]

    operations = [
        migrations.RunPython(_encrypt_rows, _decrypt_rows),
    ]
