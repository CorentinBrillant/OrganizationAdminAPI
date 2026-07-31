from django.urls import path

from .auth import require_api_token
from .views import (
    auth_change_password,
    auth_login,
    auth_logout,
    auth_session,
    badge_export_orders,
    badge_import_campaign,
    badge_latest_rows,
    badge_sync_campaign_members,
    campaign_manual_edition,
    campaign_member_autorisation_parentale_download,
    campaign_member_certificat_delete,
    campaign_member_certificat_download,
    campaign_member_certificat_upload,
    campaign_member_duplicate_merge,
    campaign_member_duplicate_suggestions,
    campaign_member_photo_download,
    campaign_members,
    campaign_members_bulk_delete,
    campaign_members_export,
    campaign_settings,
    campaigns,
    federation_extranet_extract_excel,
    ffck_latest_rows,
    ffck_row_photo_download,
    ffck_sync_campaign_members,
    helloasso_authorization_callback,
    helloasso_authorization_start,
    helloasso_authorization_status,
    helloasso_import_campaign,
    helloasso_latest_items,
    helloasso_membership_forms,
    helloasso_sync_campaign_members,
    sync_campaign_members,
)


def _protected(view):
    return require_api_token(view)


urlpatterns = [
    path("auth/login/", auth_login, name="auth-login"),
    path("auth/session/", _protected(auth_session), name="auth-session"),
    path("auth/password/", _protected(auth_change_password), name="auth-change-password"),
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
        "campaigns/<int:campaign_id>/members/export/",
        _protected(campaign_members_export),
        name="campaign-members-export",
    ),
    path(
        "campaigns/<int:campaign_id>/members/<int:member_id>/certificat-file/",
        _protected(campaign_member_certificat_upload),
        name="campaign-member-certificat-upload",
    ),
    path(
        "campaigns/<int:campaign_id>/members/<int:member_id>/certificat-file/download/",
        _protected(campaign_member_certificat_download),
        name="campaign-member-certificat-download",
    ),
    path(
        "campaigns/<int:campaign_id>/members/<int:member_id>/photo/download/",
        _protected(campaign_member_photo_download),
        name="campaign-member-photo-download",
    ),
    path(
        "campaigns/<int:campaign_id>/members/<int:member_id>/autorisation-parentale/download/",
        _protected(campaign_member_autorisation_parentale_download),
        name="campaign-member-autorisation-parentale-download",
    ),
    path(
        "campaigns/<int:campaign_id>/members/<int:member_id>/certificat-file/delete/",
        _protected(campaign_member_certificat_delete),
        name="campaign-member-certificat-delete",
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
        "helloasso/authorization/start/",
        _protected(helloasso_authorization_start),
        name="helloasso-authorization-start",
    ),
    path(
        "helloasso/authorization/<str:authorization_id>/status/",
        _protected(helloasso_authorization_status),
        name="helloasso-authorization-status",
    ),
    path(
        "helloasso/authorization/callback/",
        helloasso_authorization_callback,
        name="helloasso-authorization-callback",
    ),
    path(
        "campaigns/sync-members/", _protected(sync_campaign_members), name="campaigns-sync-members"
    ),
    path("ffck/rows/latest/", _protected(ffck_latest_rows), name="ffck-latest-rows"),
    path(
        "ffck/rows/<int:row_id>/photo/download/",
        _protected(ffck_row_photo_download),
        name="ffck-row-photo-download",
    ),
    path("ffck/sync-members/", _protected(ffck_sync_campaign_members), name="ffck-sync-members"),
    path("badges/rows/latest/", _protected(badge_latest_rows), name="badges-latest-rows"),
    path("badges/export-orders/", _protected(badge_export_orders), name="badges-export-orders"),
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
