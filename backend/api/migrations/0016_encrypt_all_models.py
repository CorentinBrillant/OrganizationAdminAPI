# Generated manually for data encryption rollout

import hashlib

import django_cryptography.fields
from django.db import migrations, models


ENCRYPTED_FIELDS = {
    "campaign": [
        "title",
        "status",
        "helloasso_api_key",
        "helloasso_form_slug",
    ],
    "member": [
        "first_name",
        "name",
        "ffck_licence",
        "ffck_certificat",
        "ffck_certificat_expiration",
        "ffck_licence_type",
        "helloasso_form_slug",
        "email",
        "certificat",
        "autorisation_parentale",
        "photo",
    ],
    "memberduplicatesuggestion": [
        "reasons",
    ],
    "helloassoimport": [
        "source",
        "organization_slug",
        "form_type",
        "form_slug",
        "payload",
    ],
    "helloassoitem": [
        "helloasso_id",
        "organization_slug",
        "form_type",
        "form_slug",
        "status",
        "payer_email",
        "amount",
        "paid_at",
        "raw_item",
    ],
    "ffckexport": [
        "source",
        "structure_select_path",
        "export_path",
        "export_method",
        "export_payload",
        "filename",
        "content_type",
        "file_sha256",
        "file_blob",
    ],
    "ffckexportrow": [
        "licence",
        "nom",
        "categorie",
        "certificat",
        "raw_row",
    ],
    "badgeimport": [
        "source",
        "filename",
        "content_type",
        "file_sha256",
        "file_blob",
    ],
    "badgeimportrow": [
        "licence",
        "first_name",
        "name",
        "raw_row",
    ],
}


def _lookup_key(helloasso_id: str, organization_slug: str, form_type: str, form_slug: str) -> str:
    payload = "|".join(
        [
            str(helloasso_id or "").strip(),
            str(organization_slug or "").strip(),
            str(form_type or "").strip(),
            str(form_slug or "").strip(),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _normalize_for_encryption(value):
    # PostgreSQL can return BinaryField values as memoryview.
    # django-cryptography pickles values before encrypting, and memoryview
    # is not picklable.
    if isinstance(value, memoryview):
        return value.tobytes()
    return value


def _copy_forward(apps, schema_editor):
    model_map = {
        "campaign": "Campaign",
        "member": "Member",
        "memberduplicatesuggestion": "MemberDuplicateSuggestion",
        "helloassoimport": "HelloAssoImport",
        "helloassoitem": "HelloAssoItem",
        "ffckexport": "FfckExport",
        "ffckexportrow": "FfckExportRow",
        "badgeimport": "BadgeImport",
        "badgeimportrow": "BadgeImportRow",
    }

    for model_key, model_name in model_map.items():
        Model = apps.get_model("api", model_name)
        field_names = ENCRYPTED_FIELDS.get(model_key, [])

        for row in Model.objects.all().iterator():
            update_fields = []
            for field_name in field_names:
                raw_value = getattr(row, f"old_{field_name}")
                setattr(row, field_name, _normalize_for_encryption(raw_value))
                update_fields.append(field_name)

            if model_key == "helloassoitem":
                row.helloasso_lookup_key = _lookup_key(
                    getattr(row, "helloasso_id", ""),
                    getattr(row, "organization_slug", ""),
                    getattr(row, "form_type", ""),
                    getattr(row, "form_slug", ""),
                )
                update_fields.append("helloasso_lookup_key")

            if update_fields:
                row.save(update_fields=update_fields)


def _copy_reverse(apps, schema_editor):
    model_map = {
        "campaign": "Campaign",
        "member": "Member",
        "memberduplicatesuggestion": "MemberDuplicateSuggestion",
        "helloassoimport": "HelloAssoImport",
        "helloassoitem": "HelloAssoItem",
        "ffckexport": "FfckExport",
        "ffckexportrow": "FfckExportRow",
        "badgeimport": "BadgeImport",
        "badgeimportrow": "BadgeImportRow",
    }

    for model_key, model_name in model_map.items():
        Model = apps.get_model("api", model_name)
        field_names = ENCRYPTED_FIELDS.get(model_key, [])

        for row in Model.objects.all().iterator():
            update_fields = []
            for field_name in field_names:
                setattr(row, f"old_{field_name}", getattr(row, field_name))
                update_fields.append(f"old_{field_name}")

            if update_fields:
                row.save(update_fields=update_fields)


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0015_badges"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="helloassoitem",
            name="uniq_helloasso_item_per_form",
        ),
        migrations.RemoveIndex(
            model_name="helloassoitem",
            name="api_helloas_organiz_8e1606_idx",
        ),
        migrations.RemoveIndex(
            model_name="helloassoitem",
            name="api_helloas_payer_e_7cd8b5_idx",
        ),
        migrations.RemoveIndex(
            model_name="helloassoitem",
            name="api_helloas_status_ab003b_idx",
        ),
        migrations.RemoveIndex(
            model_name="ffckexportrow",
            name="api_ffckexp_licence_343326_idx",
        ),
        migrations.RemoveIndex(
            model_name="ffckexportrow",
            name="api_ffckexp_nom_331b0d_idx",
        ),
        migrations.RemoveIndex(
            model_name="badgeimportrow",
            name="api_badgeim_licence_1af4f0_idx",
        ),
        migrations.RemoveIndex(
            model_name="badgeimportrow",
            name="api_badgeim_name_17b28c_idx",
        ),
        *[
            migrations.RenameField(
                model_name=model_name,
                old_name=field_name,
                new_name=f"old_{field_name}",
            )
            for model_name, field_names in ENCRYPTED_FIELDS.items()
            for field_name in field_names
        ],
        migrations.AddField(
            model_name="campaign",
            name="title",
            field=django_cryptography.fields.encrypt(models.CharField(default="", max_length=255)),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="campaign",
            name="status",
            field=django_cryptography.fields.encrypt(models.CharField(default="", max_length=100)),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="campaign",
            name="helloasso_api_key",
            field=django_cryptography.fields.encrypt(models.CharField(default="", max_length=255)),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="campaign",
            name="helloasso_form_slug",
            field=django_cryptography.fields.encrypt(
                models.CharField(blank=True, default="", max_length=255)
            ),
        ),
        migrations.AddField(
            model_name="member",
            name="first_name",
            field=django_cryptography.fields.encrypt(models.CharField(default="", max_length=150)),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="member",
            name="name",
            field=django_cryptography.fields.encrypt(models.CharField(default="", max_length=150)),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="member",
            name="ffck_licence",
            field=django_cryptography.fields.encrypt(models.CharField(default="", max_length=100)),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="member",
            name="ffck_certificat",
            field=django_cryptography.fields.encrypt(
                models.CharField(blank=True, default="", max_length=255)
            ),
        ),
        migrations.AddField(
            model_name="member",
            name="ffck_certificat_expiration",
            field=django_cryptography.fields.encrypt(
                models.CharField(blank=True, default="", max_length=100)
            ),
        ),
        migrations.AddField(
            model_name="member",
            name="ffck_licence_type",
            field=django_cryptography.fields.encrypt(
                models.CharField(blank=True, default="", max_length=150)
            ),
        ),
        migrations.AddField(
            model_name="member",
            name="helloasso_form_slug",
            field=django_cryptography.fields.encrypt(
                models.CharField(blank=True, default="", max_length=255)
            ),
        ),
        migrations.AddField(
            model_name="member",
            name="email",
            field=django_cryptography.fields.encrypt(models.EmailField(default="", max_length=254)),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="member",
            name="certificat",
            field=django_cryptography.fields.encrypt(models.URLField(blank=True, default="")),
        ),
        migrations.AddField(
            model_name="member",
            name="autorisation_parentale",
            field=django_cryptography.fields.encrypt(models.URLField(blank=True, default="")),
        ),
        migrations.AddField(
            model_name="member",
            name="photo",
            field=django_cryptography.fields.encrypt(models.URLField(blank=True, default="")),
        ),
        migrations.AddField(
            model_name="memberduplicatesuggestion",
            name="reasons",
            field=django_cryptography.fields.encrypt(models.JSONField(blank=True, default=list)),
        ),
        migrations.AddField(
            model_name="helloassoimport",
            name="source",
            field=django_cryptography.fields.encrypt(
                models.CharField(default="form_items", max_length=50)
            ),
        ),
        migrations.AddField(
            model_name="helloassoimport",
            name="organization_slug",
            field=django_cryptography.fields.encrypt(models.CharField(default="", max_length=255)),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="helloassoimport",
            name="form_type",
            field=django_cryptography.fields.encrypt(models.CharField(default="", max_length=50)),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="helloassoimport",
            name="form_slug",
            field=django_cryptography.fields.encrypt(models.CharField(default="", max_length=255)),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="helloassoimport",
            name="payload",
            field=django_cryptography.fields.encrypt(models.JSONField(default=dict)),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="helloassoitem",
            name="helloasso_lookup_key",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="helloassoitem",
            name="helloasso_id",
            field=django_cryptography.fields.encrypt(models.CharField(default="", max_length=120)),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="helloassoitem",
            name="organization_slug",
            field=django_cryptography.fields.encrypt(models.CharField(default="", max_length=255)),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="helloassoitem",
            name="form_type",
            field=django_cryptography.fields.encrypt(models.CharField(default="", max_length=50)),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="helloassoitem",
            name="form_slug",
            field=django_cryptography.fields.encrypt(models.CharField(default="", max_length=255)),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="helloassoitem",
            name="status",
            field=django_cryptography.fields.encrypt(models.CharField(blank=True, max_length=100)),
        ),
        migrations.AddField(
            model_name="helloassoitem",
            name="payer_email",
            field=django_cryptography.fields.encrypt(models.EmailField(blank=True, max_length=254)),
        ),
        migrations.AddField(
            model_name="helloassoitem",
            name="amount",
            field=django_cryptography.fields.encrypt(
                models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)
            ),
        ),
        migrations.AddField(
            model_name="helloassoitem",
            name="paid_at",
            field=django_cryptography.fields.encrypt(models.DateTimeField(blank=True, null=True)),
        ),
        migrations.AddField(
            model_name="helloassoitem",
            name="raw_item",
            field=django_cryptography.fields.encrypt(models.JSONField(default=dict)),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="ffckexport",
            name="source",
            field=django_cryptography.fields.encrypt(
                models.CharField(default="licences_excel", max_length=50)
            ),
        ),
        migrations.AddField(
            model_name="ffckexport",
            name="structure_select_path",
            field=django_cryptography.fields.encrypt(
                models.CharField(blank=True, default="", max_length=255)
            ),
        ),
        migrations.AddField(
            model_name="ffckexport",
            name="export_path",
            field=django_cryptography.fields.encrypt(models.CharField(default="", max_length=255)),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="ffckexport",
            name="export_method",
            field=django_cryptography.fields.encrypt(
                models.CharField(default="POST", max_length=10)
            ),
        ),
        migrations.AddField(
            model_name="ffckexport",
            name="export_payload",
            field=django_cryptography.fields.encrypt(models.JSONField(blank=True, default=dict)),
        ),
        migrations.AddField(
            model_name="ffckexport",
            name="filename",
            field=django_cryptography.fields.encrypt(
                models.CharField(blank=True, default="", max_length=255)
            ),
        ),
        migrations.AddField(
            model_name="ffckexport",
            name="content_type",
            field=django_cryptography.fields.encrypt(
                models.CharField(blank=True, default="", max_length=255)
            ),
        ),
        migrations.AddField(
            model_name="ffckexport",
            name="file_sha256",
            field=django_cryptography.fields.encrypt(
                models.CharField(blank=True, default="", max_length=64)
            ),
        ),
        migrations.AddField(
            model_name="ffckexport",
            name="file_blob",
            field=django_cryptography.fields.encrypt(models.BinaryField(blank=True, null=True)),
        ),
        migrations.AddField(
            model_name="ffckexportrow",
            name="licence",
            field=django_cryptography.fields.encrypt(
                models.CharField(blank=True, default="", max_length=100)
            ),
        ),
        migrations.AddField(
            model_name="ffckexportrow",
            name="nom",
            field=django_cryptography.fields.encrypt(
                models.CharField(blank=True, default="", max_length=255)
            ),
        ),
        migrations.AddField(
            model_name="ffckexportrow",
            name="categorie",
            field=django_cryptography.fields.encrypt(
                models.CharField(blank=True, default="", max_length=120)
            ),
        ),
        migrations.AddField(
            model_name="ffckexportrow",
            name="certificat",
            field=django_cryptography.fields.encrypt(
                models.CharField(blank=True, default="", max_length=500)
            ),
        ),
        migrations.AddField(
            model_name="ffckexportrow",
            name="raw_row",
            field=django_cryptography.fields.encrypt(models.JSONField(blank=True, default=dict)),
        ),
        migrations.AddField(
            model_name="badgeimport",
            name="source",
            field=django_cryptography.fields.encrypt(
                models.CharField(default="badge_excel", max_length=50)
            ),
        ),
        migrations.AddField(
            model_name="badgeimport",
            name="filename",
            field=django_cryptography.fields.encrypt(
                models.CharField(blank=True, default="", max_length=255)
            ),
        ),
        migrations.AddField(
            model_name="badgeimport",
            name="content_type",
            field=django_cryptography.fields.encrypt(
                models.CharField(blank=True, default="", max_length=255)
            ),
        ),
        migrations.AddField(
            model_name="badgeimport",
            name="file_sha256",
            field=django_cryptography.fields.encrypt(
                models.CharField(blank=True, default="", max_length=64)
            ),
        ),
        migrations.AddField(
            model_name="badgeimport",
            name="file_blob",
            field=django_cryptography.fields.encrypt(models.BinaryField(blank=True, null=True)),
        ),
        migrations.AddField(
            model_name="badgeimportrow",
            name="licence",
            field=django_cryptography.fields.encrypt(
                models.CharField(blank=True, default="", max_length=100)
            ),
        ),
        migrations.AddField(
            model_name="badgeimportrow",
            name="first_name",
            field=django_cryptography.fields.encrypt(
                models.CharField(blank=True, default="", max_length=150)
            ),
        ),
        migrations.AddField(
            model_name="badgeimportrow",
            name="name",
            field=django_cryptography.fields.encrypt(
                models.CharField(blank=True, default="", max_length=150)
            ),
        ),
        migrations.AddField(
            model_name="badgeimportrow",
            name="raw_row",
            field=django_cryptography.fields.encrypt(models.JSONField(blank=True, default=dict)),
        ),
        migrations.RunPython(_copy_forward, _copy_reverse),
        migrations.AddConstraint(
            model_name="helloassoitem",
            constraint=models.UniqueConstraint(
                fields=("helloasso_lookup_key",), name="uniq_helloasso_item_lookup_key"
            ),
        ),
        *[
            migrations.RemoveField(
                model_name=model_name,
                name=f"old_{field_name}",
            )
            for model_name, field_names in ENCRYPTED_FIELDS.items()
            for field_name in field_names
        ],
    ]
