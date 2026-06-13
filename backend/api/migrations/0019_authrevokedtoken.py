# Generated manually for token revocation support

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0018_encrypt_badge_flags"),
    ]

    operations = [
        migrations.CreateModel(
            name="AuthRevokedToken",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("token_hash", models.CharField(max_length=64, unique=True)),
                ("revoked_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "ordering": ("-revoked_at",),
            },
        ),
    ]
