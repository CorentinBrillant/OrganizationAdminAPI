import hashlib
import uuid
from pathlib import Path

from django.conf import settings
from django.db import models
from django_cryptography.fields import encrypt

from .services.file_blob_encryption import decrypt_file_blob, encrypt_file_blob


def member_certificat_upload_to(instance, filename):
    extension = Path(str(filename or "")).suffix.lower()
    return f"members/certificats/{uuid.uuid4().hex}{extension}"


def ffck_photo_upload_to(instance, filename):
    return f"members/ffck_photos/{uuid.uuid4().hex}.enc"


class EncryptedFileBlobMixin(models.Model):
    class Meta:
        abstract = True

    file_blob: bytes | None

    def set_decrypted_file_blob(self, raw_content: bytes | None) -> None:
        self.file_blob = encrypt_file_blob(raw_content)

    def get_decrypted_file_blob(self) -> bytes | None:
        return decrypt_file_blob(self.file_blob)

    def save(self, *args, **kwargs):
        self.file_blob = encrypt_file_blob(self.file_blob)
        return super().save(*args, **kwargs)


class Campaign(models.Model):
    title = encrypt(models.CharField(max_length=255))
    status = encrypt(models.CharField(max_length=100))
    created_at = models.DateTimeField(auto_now_add=True)
    helloasso_api_key = encrypt(models.CharField(max_length=255))
    helloasso_form_slug = encrypt(models.CharField(max_length=255, blank=True, default=""))
    last_merge = models.DateTimeField(null=True, blank=True)
    last_manual_edition = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return self.title


class Member(models.Model):
    first_name = encrypt(models.CharField(max_length=150))
    name = encrypt(models.CharField(max_length=150))
    ffck_licence = encrypt(models.CharField(max_length=100))
    ffck_certificat = encrypt(models.CharField(max_length=255, blank=True, default=""))
    ffck_certificat_expiration = encrypt(models.CharField(max_length=100, blank=True, default=""))
    ffck_licence_type = encrypt(models.CharField(max_length=150, blank=True, default=""))
    helloasso_form_slug = encrypt(models.CharField(max_length=255, blank=True, default=""))
    email = encrypt(models.EmailField())
    certificat = encrypt(models.URLField(blank=True, default=""))
    certificat_file = models.FileField(
        upload_to=member_certificat_upload_to,
        blank=True,
        default="",
    )
    certificat_file_uploaded_at = models.DateTimeField(null=True, blank=True)
    certificat_file_original_name = models.CharField(max_length=255, blank=True, default="")
    certificat_file_content_type = models.CharField(max_length=255, blank=True, default="")
    certificat_file_size = models.PositiveIntegerField(default=0)
    autorisation_parentale = encrypt(models.URLField(blank=True, default=""))
    photo = encrypt(models.URLField(blank=True, default=""))
    option_ia = models.BooleanField(default=False)
    manual_review = models.BooleanField(default=False)
    badge_owned = encrypt(models.BooleanField(default=False))
    badge_ordered = encrypt(models.BooleanField(default=False))
    is_deleted = encrypt(models.BooleanField(default=False))
    created_at = models.DateTimeField(auto_now_add=True)
    campaign = models.ForeignKey(
        Campaign,
        on_delete=models.CASCADE,
        related_name="members",
    )

    def __str__(self) -> str:
        return f"{self.first_name} {self.name}".strip()


class MemberDuplicateSuggestion(models.Model):
    STATUS_PENDING = "pending"
    STATUS_ACCEPTED = "accepted"
    STATUS_REJECTED = "rejected"
    STATUS_CHOICES = (
        (STATUS_PENDING, "Pending"),
        (STATUS_ACCEPTED, "Accepted"),
        (STATUS_REJECTED, "Rejected"),
    )

    campaign = models.ForeignKey(
        Campaign,
        on_delete=models.CASCADE,
        related_name="member_duplicate_suggestions",
    )
    member_left = models.ForeignKey(
        Member,
        on_delete=models.CASCADE,
        related_name="duplicate_suggestions_left",
    )
    member_right = models.ForeignKey(
        Member,
        on_delete=models.CASCADE,
        related_name="duplicate_suggestions_right",
    )
    recommended_master = models.ForeignKey(
        Member,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recommended_duplicate_merges",
    )
    similarity_score = models.FloatField(default=0.0)
    reasons = encrypt(models.JSONField(default=list, blank=True))
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-similarity_score", "-created_at")
        constraints = [
            models.UniqueConstraint(
                fields=("campaign", "member_left", "member_right"),
                name="uniq_member_duplicate_suggestion_pair",
            )
        ]
        indexes = [
            models.Index(fields=("campaign", "status")),
            models.Index(fields=("similarity_score",)),
        ]


class HelloAssoImport(models.Model):
    campaign = models.ForeignKey(
        Campaign,
        on_delete=models.PROTECT,
        related_name="helloasso_imports",
    )
    source = encrypt(models.CharField(max_length=50, default="form_items"))
    organization_slug = encrypt(models.CharField(max_length=255))
    form_type = encrypt(models.CharField(max_length=50))
    form_slug = encrypt(models.CharField(max_length=255))
    with_details = models.BooleanField(default=True)
    items_count = models.PositiveIntegerField(default=0)
    fetched_at = models.DateTimeField(auto_now_add=True)
    payload = encrypt(models.JSONField())

    class Meta:
        ordering = ("-fetched_at",)


class HelloAssoItem(models.Model):
    helloasso_lookup_key = models.CharField(max_length=64, blank=True, default="")
    helloasso_id = encrypt(models.CharField(max_length=120))
    organization_slug = encrypt(models.CharField(max_length=255))
    form_type = encrypt(models.CharField(max_length=50))
    form_slug = encrypt(models.CharField(max_length=255))
    status = encrypt(models.CharField(max_length=100, blank=True))
    payer_email = encrypt(models.EmailField(blank=True))
    amount = encrypt(models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True))
    paid_at = encrypt(models.DateTimeField(null=True, blank=True))
    member = models.ForeignKey(
        Member,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="helloasso_items",
    )
    last_synced_at = models.DateTimeField(auto_now=True)
    latest_import = models.ForeignKey(
        HelloAssoImport,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="normalized_items",
    )
    raw_item = encrypt(models.JSONField())

    class Meta:
        ordering = ("-last_synced_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("helloasso_lookup_key",),
                name="uniq_helloasso_item_lookup_key",
            ),
        ]

    def save(self, *args, **kwargs):
        payload = "|".join(
            [
                str(self.helloasso_id or "").strip(),
                str(self.organization_slug or "").strip(),
                str(self.form_type or "").strip(),
                str(self.form_slug or "").strip(),
            ]
        )
        self.helloasso_lookup_key = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        return super().save(*args, **kwargs)


class FfckExport(EncryptedFileBlobMixin, models.Model):
    campaign = models.ForeignKey(
        Campaign,
        on_delete=models.PROTECT,
        related_name="ffck_exports",
    )
    source = encrypt(models.CharField(max_length=50, default="licences_excel"))
    structure_id = models.PositiveIntegerField(null=True, blank=True)
    structure_select_path = encrypt(models.CharField(max_length=255, blank=True, default=""))
    export_path = encrypt(models.CharField(max_length=255))
    export_method = encrypt(models.CharField(max_length=10, default="POST"))
    export_payload = encrypt(models.JSONField(default=dict, blank=True))
    rows_count = models.PositiveIntegerField(default=0)
    filename = encrypt(models.CharField(max_length=255, blank=True, default=""))
    content_type = encrypt(models.CharField(max_length=255, blank=True, default=""))
    file_size = models.PositiveIntegerField(default=0)
    file_sha256 = encrypt(models.CharField(max_length=64, blank=True, default=""))
    file_blob = models.BinaryField(null=True, blank=True)
    fetched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-fetched_at",)
        indexes = [
            models.Index(fields=("campaign", "-fetched_at")),
            models.Index(fields=("structure_id",)),
        ]


class FfckExportRow(models.Model):
    ffck_export = models.ForeignKey(
        FfckExport,
        on_delete=models.CASCADE,
        related_name="rows",
    )
    row_index = models.PositiveIntegerField()
    licence = encrypt(models.CharField(max_length=100, blank=True, default=""))
    nom = encrypt(models.CharField(max_length=255, blank=True, default=""))
    categorie = encrypt(models.CharField(max_length=120, blank=True, default=""))
    certificat = encrypt(models.CharField(max_length=500, blank=True, default=""))
    photo = models.FileField(
        upload_to=ffck_photo_upload_to,
        blank=True,
        default="",
    )
    photo_original_name = models.CharField(max_length=255, blank=True, default="")
    member = models.ForeignKey(
        Member,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ffck_export_rows",
    )
    raw_row = encrypt(models.JSONField(default=dict, blank=True))
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("row_index", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("ffck_export", "row_index"),
                name="uniq_ffck_export_row_index",
            )
        ]


class BadgeImport(EncryptedFileBlobMixin, models.Model):
    id = models.AutoField(primary_key=True, serialize=False)
    campaign = models.ForeignKey(
        Campaign,
        on_delete=models.PROTECT,
        related_name="badge_imports",
    )
    source = encrypt(models.CharField(max_length=50, default="badge_excel"))
    rows_count = models.PositiveIntegerField(default=0)
    filename = encrypt(models.CharField(max_length=255, blank=True, default=""))
    content_type = encrypt(models.CharField(max_length=255, blank=True, default=""))
    file_size = models.PositiveIntegerField(default=0)
    file_sha256 = encrypt(models.CharField(max_length=64, blank=True, default=""))
    file_blob = models.BinaryField(null=True, blank=True)
    fetched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-fetched_at",)
        indexes = [
            models.Index(fields=("campaign", "-fetched_at"), name="api_badgeim_campaig_41dc19_idx"),
        ]


class BadgeImportRow(models.Model):
    id = models.AutoField(primary_key=True, serialize=False)
    badge_import = models.ForeignKey(
        BadgeImport,
        on_delete=models.CASCADE,
        related_name="rows",
    )
    row_index = models.PositiveIntegerField()
    licence = encrypt(models.CharField(max_length=100, blank=True, default=""))
    first_name = encrypt(models.CharField(max_length=150, blank=True, default=""))
    name = encrypt(models.CharField(max_length=150, blank=True, default=""))
    badge_owned = encrypt(models.BooleanField(default=False))
    badge_ordered = encrypt(models.BooleanField(default=False))
    member = models.ForeignKey(
        Member,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="badge_import_rows",
    )
    raw_row = encrypt(models.JSONField(default=dict, blank=True))
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("row_index", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("badge_import", "row_index"),
                name="uniq_badge_import_row_index",
            )
        ]


class AuthRevokedToken(models.Model):
    token_hash = models.CharField(max_length=64, unique=True)
    revoked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-revoked_at",)


class UserLogin(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="login_events",
    )
    username = models.CharField(max_length=150)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=512, blank=True, default="")
    logged_in_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-logged_in_at",)
        indexes = [
            models.Index(fields=("user", "-logged_in_at")),
            models.Index(fields=("-logged_in_at",)),
        ]
