from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0022_alter_member_certificat_file_content_type_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="ffckexport",
            name="file_blob",
            field=models.BinaryField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="badgeimport",
            name="file_blob",
            field=models.BinaryField(blank=True, null=True),
        ),
    ]
