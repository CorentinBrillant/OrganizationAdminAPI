from django.db import migrations, models

import api.models


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0031_helloasso_authorization_request"),
    ]

    operations = [
        migrations.AddField(
            model_name="member",
            name="autorisation_parentale_file",
            field=models.FileField(
                blank=True,
                default="",
                upload_to=api.models.member_autorisation_parentale_upload_to,
            ),
        ),
        migrations.AddField(
            model_name="member",
            name="autorisation_parentale_file_content_type",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="member",
            name="autorisation_parentale_file_original_name",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="member",
            name="autorisation_parentale_file_size",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="member",
            name="autorisation_parentale_file_uploaded_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
