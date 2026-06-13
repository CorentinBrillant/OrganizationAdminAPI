from django.db import models


class Campaign(models.Model):
    title = models.CharField(max_length=255)
    status = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
    helloasso_api_key = models.CharField(max_length=255)
    helloasso_form_slug = models.CharField(max_length=255, blank=True, default="")
    last_merge = models.DateTimeField(null=True, blank=True)
    last_manual_edition = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return self.title


class Member(models.Model):
    first_name = models.CharField(max_length=150)
    name = models.CharField(max_length=150)
    ffck_licence = models.CharField(max_length=100)
    ffck_certificat = models.CharField(max_length=255, blank=True, default="")
    ffck_certificat_expiration = models.CharField(max_length=100, blank=True, default="")
    ffck_licence_type = models.CharField(max_length=150, blank=True, default="")
    helloasso_form_slug = models.CharField(max_length=255, blank=True, default="")
    email = models.EmailField()
    certificat = models.URLField(blank=True, default="")
    autorisation_parentale = models.URLField(blank=True, default="")
    photo = models.URLField(blank=True, default="")
    option_ia = models.BooleanField(default=False)
    manual_review = models.BooleanField(default=False)
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
    reasons = models.JSONField(default=list, blank=True)
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
    source = models.CharField(max_length=50, default="form_items")
    organization_slug = models.CharField(max_length=255)
    form_type = models.CharField(max_length=50)
    form_slug = models.CharField(max_length=255)
    with_details = models.BooleanField(default=True)
    items_count = models.PositiveIntegerField(default=0)
    fetched_at = models.DateTimeField(auto_now_add=True)
    payload = models.JSONField()

    class Meta:
        ordering = ("-fetched_at",)


class HelloAssoItem(models.Model):
    helloasso_id = models.CharField(max_length=120)
    organization_slug = models.CharField(max_length=255)
    form_type = models.CharField(max_length=50)
    form_slug = models.CharField(max_length=255)
    status = models.CharField(max_length=100, blank=True)
    payer_email = models.EmailField(blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
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
    raw_item = models.JSONField()

    class Meta:
        ordering = ("-last_synced_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("helloasso_id", "organization_slug", "form_type", "form_slug"),
                name="uniq_helloasso_item_per_form",
            ),
        ]
        indexes = [
            models.Index(fields=("organization_slug", "form_type", "form_slug")),
            models.Index(fields=("payer_email",)),
            models.Index(fields=("status",)),
        ]


class FfckExport(models.Model):
    campaign = models.ForeignKey(
        Campaign,
        on_delete=models.PROTECT,
        related_name="ffck_exports",
    )
    source = models.CharField(max_length=50, default="licences_excel")
    structure_id = models.PositiveIntegerField(null=True, blank=True)
    structure_select_path = models.CharField(max_length=255, blank=True, default="")
    export_path = models.CharField(max_length=255)
    export_method = models.CharField(max_length=10, default="POST")
    export_payload = models.JSONField(default=dict, blank=True)
    rows_count = models.PositiveIntegerField(default=0)
    filename = models.CharField(max_length=255, blank=True, default="")
    content_type = models.CharField(max_length=255, blank=True, default="")
    file_size = models.PositiveIntegerField(default=0)
    file_sha256 = models.CharField(max_length=64, blank=True, default="")
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
    licence = models.CharField(max_length=100, blank=True, default="")
    nom = models.CharField(max_length=255, blank=True, default="")
    categorie = models.CharField(max_length=120, blank=True, default="")
    certificat = models.CharField(max_length=500, blank=True, default="")
    member = models.ForeignKey(
        Member,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ffck_export_rows",
    )
    raw_row = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("row_index", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("ffck_export", "row_index"),
                name="uniq_ffck_export_row_index",
            )
        ]
        indexes = [
            models.Index(fields=("licence",)),
            models.Index(fields=("nom",)),
        ]
