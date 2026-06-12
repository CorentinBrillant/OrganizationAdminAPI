from django.contrib import admin

from .models import (
    Campaign,
    FfckExport,
    FfckExportRow,
    HelloAssoImport,
    HelloAssoItem,
    MemberDuplicateSuggestion,
    Member,
)


@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "status", "helloasso_form_slug", "last_merge", "last_manual_edition", "created_at")
    list_filter = ("status", "last_merge", "last_manual_edition", "created_at")
    search_fields = ("title", "status", "helloasso_form_slug")
    ordering = ("-created_at",)


@admin.register(Member)
class MemberAdmin(admin.ModelAdmin):
    list_display = ("id", "first_name", "name", "email", "photo", "option_ia", "manual_review", "ffck_licence", "campaign", "created_at")
    list_filter = ("campaign", "option_ia", "manual_review", "created_at")
    search_fields = ("first_name", "name", "email", "certificat", "autorisation_parentale", "photo", "ffck_licence", "campaign__title")
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
    list_filter = ("campaign", "source", "with_details", "form_type", "fetched_at")
    search_fields = ("campaign__title", "organization_slug", "form_slug")
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
    list_filter = ("member", "form_type", "status", "last_synced_at")
    search_fields = (
        "helloasso_id",
        "member__first_name",
        "member__name",
        "member__email",
        "payer_email",
        "organization_slug",
        "form_slug",
    )
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
    list_filter = ("campaign", "source", "structure_id", "export_method", "fetched_at")
    search_fields = ("campaign__title", "filename", "structure_select_path", "export_path", "file_sha256")
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
    list_filter = ("ffck_export__campaign", "categorie", "created_at")
    search_fields = ("licence", "nom", "categorie", "member__email", "ffck_export__campaign__title")
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
    search_fields = (
        "campaign__title",
        "member_left__first_name",
        "member_left__name",
        "member_right__first_name",
        "member_right__name",
    )
    ordering = ("-similarity_score", "-created_at")
