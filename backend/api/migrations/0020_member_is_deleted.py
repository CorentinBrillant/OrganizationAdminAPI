from django.db import migrations, models
from django_cryptography.fields import encrypt


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0019_authrevokedtoken"),
    ]

    operations = [
        migrations.AddField(
            model_name="member",
            name="is_deleted",
            field=encrypt(models.BooleanField(default=False)),
        ),
    ]
