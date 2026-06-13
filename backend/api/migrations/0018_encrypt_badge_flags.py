# Generated manually for badge flags encryption

import django_cryptography.fields
from django.db import migrations, models


def _forward(apps, schema_editor):
    Member = apps.get_model("api", "Member")
    BadgeImportRow = apps.get_model("api", "BadgeImportRow")

    for row in Member.objects.all().iterator():
        row.badge_owned = bool(getattr(row, "old_badge_owned", False))
        row.badge_ordered = bool(getattr(row, "old_badge_ordered", False))
        row.save(update_fields=["badge_owned", "badge_ordered"])

    for row in BadgeImportRow.objects.all().iterator():
        row.badge_owned = bool(getattr(row, "old_badge_owned", False))
        row.badge_ordered = bool(getattr(row, "old_badge_ordered", False))
        row.save(update_fields=["badge_owned", "badge_ordered"])


def _reverse(apps, schema_editor):
    Member = apps.get_model("api", "Member")
    BadgeImportRow = apps.get_model("api", "BadgeImportRow")

    for row in Member.objects.all().iterator():
        row.old_badge_owned = bool(getattr(row, "badge_owned", False))
        row.old_badge_ordered = bool(getattr(row, "badge_ordered", False))
        row.save(update_fields=["old_badge_owned", "old_badge_ordered"])

    for row in BadgeImportRow.objects.all().iterator():
        row.old_badge_owned = bool(getattr(row, "badge_owned", False))
        row.old_badge_ordered = bool(getattr(row, "badge_ordered", False))
        row.save(update_fields=["old_badge_owned", "old_badge_ordered"])


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0017_auto_20260613_1750"),
    ]

    operations = [
        migrations.RenameField(
            model_name="member",
            old_name="badge_owned",
            new_name="old_badge_owned",
        ),
        migrations.RenameField(
            model_name="member",
            old_name="badge_ordered",
            new_name="old_badge_ordered",
        ),
        migrations.RenameField(
            model_name="badgeimportrow",
            old_name="badge_owned",
            new_name="old_badge_owned",
        ),
        migrations.RenameField(
            model_name="badgeimportrow",
            old_name="badge_ordered",
            new_name="old_badge_ordered",
        ),
        migrations.AddField(
            model_name="member",
            name="badge_owned",
            field=django_cryptography.fields.encrypt(models.BooleanField(default=False)),
        ),
        migrations.AddField(
            model_name="member",
            name="badge_ordered",
            field=django_cryptography.fields.encrypt(models.BooleanField(default=False)),
        ),
        migrations.AddField(
            model_name="badgeimportrow",
            name="badge_owned",
            field=django_cryptography.fields.encrypt(models.BooleanField(default=False)),
        ),
        migrations.AddField(
            model_name="badgeimportrow",
            name="badge_ordered",
            field=django_cryptography.fields.encrypt(models.BooleanField(default=False)),
        ),
        migrations.RunPython(_forward, _reverse),
        migrations.RemoveField(
            model_name="member",
            name="old_badge_owned",
        ),
        migrations.RemoveField(
            model_name="member",
            name="old_badge_ordered",
        ),
        migrations.RemoveField(
            model_name="badgeimportrow",
            name="old_badge_owned",
        ),
        migrations.RemoveField(
            model_name="badgeimportrow",
            name="old_badge_ordered",
        ),
    ]
