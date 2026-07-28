from django.contrib import admin

from .models import (
    Campaign,
    FfckExport,
    FfckExportRow,
    HelloAssoImport,
    HelloAssoItem,
    Member,
    MemberDuplicateSuggestion,
    UserLogin,
)


@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "title",
        "status",
        "helloasso_form_slug",
        "last_merge",
        "last_manual_edition",
        "created_at",
    )
    list_filter = ("last_merge", "last_manual_edition", "created_at")
    search_fields = ("id",)
    ordering = ("-created_at",)


@admin.register(Member)
class MemberAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "first_name",
        "name",
        "email",
        "photo",
        "option_ia",
        "manual_review",
        "ffck_licence",
        "campaign",
        "created_at",
    )
    list_filter = ("campaign", "option_ia", "manual_review", "created_at")
    search_fields = ("id", "campaign__id")
    ordering = ("-created_at",)


@admin.register(HelloAssoImport)
class HelloAssoImportAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "campaign",
        "source",
        "organization_slug",
        "form_type",
        "form_slug",
        "with_details",
        "items_count",
        "fetched_at",
    )
    list_filter = ("campaign", "with_details", "fetched_at")
    search_fields = ("id", "campaign__id")
    ordering = ("-fetched_at",)


@admin.register(HelloAssoItem)
class HelloAssoItemAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "helloasso_id",
        "member",
        "organization_slug",
        "form_type",
        "form_slug",
        "status",
        "payer_email",
        "amount",
        "paid_at",
        "last_synced_at",
    )
    list_filter = ("member", "last_synced_at")
    search_fields = ("id", "member__id", "helloasso_lookup_key")
    ordering = ("-last_synced_at",)


@admin.register(FfckExport)
class FfckExportAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "campaign",
        "source",
        "structure_id",
        "filename",
        "rows_count",
        "file_size",
        "fetched_at",
    )
    list_filter = ("campaign", "structure_id", "fetched_at")
    search_fields = ("id", "campaign__id")
    ordering = ("-fetched_at",)


@admin.register(FfckExportRow)
class FfckExportRowAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "ffck_export",
        "row_index",
        "licence",
        "nom",
        "categorie",
        "member",
        "created_at",
    )
    list_filter = ("ffck_export__campaign", "created_at")
    search_fields = ("id", "member__id", "ffck_export__campaign__id")
    ordering = ("ffck_export", "row_index")


@admin.register(MemberDuplicateSuggestion)
class MemberDuplicateSuggestionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "campaign",
        "member_left",
        "member_right",
        "recommended_master",
        "similarity_score",
        "status",
        "created_at",
        "resolved_at",
    )
    list_filter = ("campaign", "status", "created_at", "resolved_at")
    search_fields = ("id", "campaign__id", "member_left__id", "member_right__id")
    ordering = ("-similarity_score", "-created_at")


@admin.register(UserLogin)
class UserLoginAdmin(admin.ModelAdmin):
    list_display = ("id", "username", "user", "ip_address", "logged_in_at")
    list_filter = ("logged_in_at",)
    search_fields = ("username", "ip_address", "user__username")
    ordering = ("-logged_in_at",)
    readonly_fields = ("user", "username", "ip_address", "user_agent", "logged_in_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
