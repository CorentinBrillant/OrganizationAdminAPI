import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("api", "0025_encrypt_existing_file_blob_values"),
    ]

    operations = [
        migrations.CreateModel(
            name="UserLogin",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("username", models.CharField(max_length=150)),
                ("ip_address", models.GenericIPAddressField(blank=True, null=True)),
                ("user_agent", models.CharField(blank=True, default="", max_length=512)),
                ("logged_in_at", models.DateTimeField(auto_now_add=True)),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="login_events",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ("-logged_in_at",)},
        ),
        migrations.AddIndex(
            model_name="userlogin",
            index=models.Index(
                fields=["user", "-logged_in_at"],
                name="api_userlog_user_id_a097c2_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="userlogin",
            index=models.Index(
                fields=["-logged_in_at"],
                name="api_userlog_logged__9aea96_idx",
            ),
        ),
    ]
