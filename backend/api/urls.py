from django.urls import path

from .auth import require_api_token
from .views import (
    auth_login,
    auth_logout,
    auth_session,
    badge_import_campaign,
    badge_latest_rows,
    badge_sync_campaign_members,
    campaign_manual_edition,
    campaign_settings,
    campaign_member_duplicate_merge,
    campaign_member_duplicate_suggestions,
    campaign_members,
    campaign_members_bulk_delete,
    campaigns,
    ffck_latest_rows,
    ffck_sync_campaign_members,
    federation_extranet_extract_excel,
    helloasso_import_campaign,
    helloasso_membership_forms,
    helloasso_latest_items,
    helloasso_sync_campaign_members,
    sync_campaign_members,
)


def _protected(view):
    return require_api_token(view)


urlpatterns = [
    path("auth/login/", auth_login, name="auth-login"),
    path("auth/session/", _protected(auth_session), name="auth-session"),
    path("auth/logout/", _protected(auth_logout), name="auth-logout"),
    path("campaigns/", _protected(campaigns), name="campaigns"),
    path(
        "campaigns/<int:campaign_id>/settings/",
        _protected(campaign_settings),
        name="campaign-settings",
    ),
    path(
        "campaigns/<int:campaign_id>/members/",
        _protected(campaign_members),
        name="campaign-members",
    ),
    path(
        "campaigns/<int:campaign_id>/members/bulk-delete/",
        _protected(campaign_members_bulk_delete),
        name="campaign-members-bulk-delete",
    ),
    path(
        "campaigns/<int:campaign_id>/manual-edition/",
        _protected(campaign_manual_edition),
        name="campaign-manual-edition",
    ),
    path(
        "campaigns/member-duplicates/",
        _protected(campaign_member_duplicate_suggestions),
        name="campaign-member-duplicates",
    ),
    path(
        "campaigns/member-duplicates/merge/",
        _protected(campaign_member_duplicate_merge),
        name="campaign-member-duplicates-merge",
    ),
    path(
        "helloasso/items/latest/", _protected(helloasso_latest_items), name="helloasso-latest-items"
    ),
    path(
        "helloasso/import/", _protected(helloasso_import_campaign), name="helloasso-import-campaign"
    ),
    path(
        "helloasso/membership-forms/",
        _protected(helloasso_membership_forms),
        name="helloasso-membership-forms",
    ),
    path(
        "helloasso/sync-members/",
        _protected(helloasso_sync_campaign_members),
        name="helloasso-sync-members",
    ),
    path(
        "campaigns/sync-members/", _protected(sync_campaign_members), name="campaigns-sync-members"
    ),
    path("ffck/rows/latest/", _protected(ffck_latest_rows), name="ffck-latest-rows"),
    path("ffck/sync-members/", _protected(ffck_sync_campaign_members), name="ffck-sync-members"),
    path("badges/rows/latest/", _protected(badge_latest_rows), name="badges-latest-rows"),
    path("badges/import/", _protected(badge_import_campaign), name="badges-import-campaign"),
    path(
        "badges/sync-members/", _protected(badge_sync_campaign_members), name="badges-sync-members"
    ),
    path(
        "federation/extract-excel/",
        _protected(federation_extranet_extract_excel),
        name="federation-extract-excel",
    ),
]
