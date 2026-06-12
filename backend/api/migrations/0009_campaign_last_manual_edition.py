from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0008_member_manual_review"),
    ]

    operations = [
        migrations.AddField(
            model_name="campaign",
            name="last_manual_edition",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
