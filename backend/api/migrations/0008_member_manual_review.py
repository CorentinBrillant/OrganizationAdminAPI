from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0007_member_photo"),
    ]

    operations = [
        migrations.AddField(
            model_name="member",
            name="manual_review",
            field=models.BooleanField(default=False),
        ),
    ]
