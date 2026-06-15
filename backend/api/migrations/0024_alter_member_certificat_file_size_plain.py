from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0023_alter_file_blob_unencrypted"),
    ]

    operations = [
        migrations.AlterField(
            model_name="member",
            name="certificat_file_size",
            field=models.PositiveIntegerField(default=0),
        ),
    ]
