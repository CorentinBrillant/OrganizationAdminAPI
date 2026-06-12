from django.db import migrations, models
import django.db.models.deletion


def link_imports_to_campaign(apps, schema_editor):
    Campaign = apps.get_model("api", "Campaign")
    HelloAssoImport = apps.get_model("api", "HelloAssoImport")

    imports = HelloAssoImport.objects.filter(campaign__isnull=True)

    for import_row in imports:
        target_campaign = None

        if import_row.form_slug:
            matches = list(Campaign.objects.filter(helloasso_api_key=import_row.form_slug)[:2])
            if len(matches) == 1:
                target_campaign = matches[0]

        if target_campaign is None:
            campaigns = list(Campaign.objects.all().order_by("id")[:2])
            if len(campaigns) == 1:
                target_campaign = campaigns[0]

        if target_campaign is None:
            raise RuntimeError(
                "Unable to link existing HelloAssoImport rows to Campaign. "
                "Create/fix campaigns first or empty helloassoimport table, then re-run migrations."
            )

        import_row.campaign_id = target_campaign.id
        import_row.save(update_fields=["campaign"])


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0002_auto_20260612_1522"),
    ]

    operations = [
        migrations.AddField(
            model_name="helloassoimport",
            name="campaign",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="helloasso_imports",
                to="api.campaign",
            ),
        ),
        migrations.AddField(
            model_name="helloassoitem",
            name="member",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="helloasso_items",
                to="api.member",
            ),
        ),
        migrations.RunPython(link_imports_to_campaign, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="helloassoimport",
            name="campaign",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="helloasso_imports",
                to="api.campaign",
            ),
        ),
    ]
