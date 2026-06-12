from django.urls import path

from .views import (
    campaign_manual_edition,
    campaign_member_duplicate_merge,
    campaign_member_duplicate_suggestions,
    campaign_members,
    campaign_members_bulk_delete,
    campaigns,
    ffck_latest_rows,
    ffck_sync_campaign_members,
    federation_extranet_extract_excel,
    helloasso_import_campaign,
    helloasso_latest_items,
    helloasso_sync_campaign_members,
    sync_campaign_members,
)

urlpatterns = [
    path("campaigns/", campaigns, name="campaigns"),
    path("campaigns/<int:campaign_id>/members/", campaign_members, name="campaign-members"),
    path(
        "campaigns/<int:campaign_id>/members/bulk-delete/",
        campaign_members_bulk_delete,
        name="campaign-members-bulk-delete",
    ),
    path(
        "campaigns/<int:campaign_id>/manual-edition/",
        campaign_manual_edition,
        name="campaign-manual-edition",
    ),
    path(
        "campaigns/member-duplicates/",
        campaign_member_duplicate_suggestions,
        name="campaign-member-duplicates",
    ),
    path(
        "campaigns/member-duplicates/merge/",
        campaign_member_duplicate_merge,
        name="campaign-member-duplicates-merge",
    ),
    path("helloasso/items/latest/", helloasso_latest_items, name="helloasso-latest-items"),
    path("helloasso/import/", helloasso_import_campaign, name="helloasso-import-campaign"),
    path("helloasso/sync-members/", helloasso_sync_campaign_members, name="helloasso-sync-members"),
    path("campaigns/sync-members/", sync_campaign_members, name="campaigns-sync-members"),
    path("ffck/rows/latest/", ffck_latest_rows, name="ffck-latest-rows"),
    path("ffck/sync-members/", ffck_sync_campaign_members, name="ffck-sync-members"),
    path("federation/extract-excel/", federation_extranet_extract_excel, name="federation-extract-excel"),
]
