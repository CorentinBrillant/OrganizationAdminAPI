from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0032_member_autorisation_parentale_file_fields"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="UserActionToken",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                (
                    "action",
                    models.CharField(
                        choices=[
                            ("set_password", "Set password"),
                            ("password_reset", "Password reset"),
                        ],
                        max_length=32,
                    ),
                ),
                ("token_hash", models.CharField(max_length=64, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("expires_at", models.DateTimeField()),
                ("used_at", models.DateTimeField(blank=True, null=True)),
                ("invalidated_at", models.DateTimeField(blank=True, null=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="action_tokens",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ("-created_at",)},
        ),
        migrations.AddIndex(
            model_name="useractiontoken",
            index=models.Index(
                fields=["user", "action", "expires_at"], name="api_useract_user_id_4893fa_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="useractiontoken",
            index=models.Index(fields=["token_hash"], name="api_useract_token_h_4f64c5_idx"),
        ),
    ]
