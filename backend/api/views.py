import hashlib
import json
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .models import (
    Campaign,
    FfckExport,
    FfckExportRow,
    HelloAssoImport,
    HelloAssoItem,
    Member,
    MemberDuplicateSuggestion,
)
from .services.helloasso_service import (
    HelloAssoAPIError,
    HelloAssoConfigError,
    HelloAssoService,
)
from .services.federation_extranet_service import (
    FederationExtranetAuthError,
    FederationExtranetConfigError,
    FederationExtranetExportError,
    FederationExtranetService,
)
from .services.ffck_export_import_service import FfckExportImportError, FfckExportImportService
from .services.member_dedup_service import MemberDedupService
from .services.member_sync_service import FfckMemberSyncService, HelloAssoMemberSyncService


def _nested_get(obj, *keys):
    current = obj
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
        if current is None:
            return None
    return current


def _extract_items(payload):
    data = payload.get("data") if isinstance(payload, dict) else None
    return data if isinstance(data, list) else []


def _extract_helloasso_id(item):
    candidates = [
        item.get("id"),
        item.get("itemId"),
        _nested_get(item, "order", "id"),
        _nested_get(item, "payment", "id"),
        _nested_get(item, "registration", "id"),
    ]

    for candidate in candidates:
        if candidate not in (None, ""):
            return str(candidate)

    fingerprint = hashlib.sha256(
        json.dumps(item, sort_keys=True, ensure_ascii=True, default=str).encode("utf-8")
    ).hexdigest()
    return f"hash:{fingerprint}"


def _extract_email(item):
    candidates = [
        item.get("payerEmail"),
        _nested_get(item, "payer", "email"),
        _nested_get(item, "user", "email"),
        _nested_get(item, "purchaser", "email"),
    ]
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return ""


def _extract_status(item):
    candidates = [item.get("status"), item.get("state"), _nested_get(item, "order", "status")]
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return ""


def _extract_amount(item):
    amount_value = item.get("amount")

    if isinstance(amount_value, dict):
        for key in ("total", "totalAmount", "amount", "value"):
            raw = amount_value.get(key)
            if raw is None:
                continue
            try:
                return Decimal(str(raw))
            except (InvalidOperation, ValueError):
                continue
        return None

    if amount_value is None:
        return None

    try:
        return Decimal(str(amount_value))
    except (InvalidOperation, ValueError):
        return None


def _extract_paid_at(item):
    candidates = [
        item.get("paidAt"),
        item.get("paymentDate"),
        item.get("date"),
        _nested_get(item, "order", "date"),
    ]

    for candidate in candidates:
        if not isinstance(candidate, str):
            continue
        parsed = parse_datetime(candidate)
        if parsed is not None:
            return parsed

    return None


def _mark_campaign_last_merge(campaign):
    campaign.last_merge = timezone.now()
    campaign.save(update_fields=["last_merge"])


def _resolve_campaign(request):
    raw_campaign_id = request.GET.get(
        "campaignId",
        str(getattr(settings, "HELLOASSO_CAMPAIGN_ID", "")).strip(),
    ).strip()

    if not raw_campaign_id:
        return None, JsonResponse(
            {
                "error": (
                    "campaignId is required (query param or HELLOASSO_CAMPAIGN_ID setting)."
                )
            },
            status=400,
        )

    try:
        campaign_id = int(raw_campaign_id)
    except ValueError:
        return None, JsonResponse({"error": "campaignId must be an integer."}, status=400)

    campaign = Campaign.objects.filter(id=campaign_id).first()
    if campaign is None:
        return None, JsonResponse({"error": f"Campaign {campaign_id} not found."}, status=404)

    return campaign, None

@require_http_methods(["GET", "POST"])
def campaigns(request):
    if request.method == "POST":
        try:
            payload = json.loads(request.body.decode("utf-8") if request.body else "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            return JsonResponse({"error": "Invalid JSON payload."}, status=400)

        if not isinstance(payload, dict):
            return JsonResponse({"error": "Invalid JSON payload."}, status=400)

        title = str(payload.get("title", "")).strip()
        if not title:
            return JsonResponse({"error": "'title' is required."}, status=400)

        status = str(payload.get("status", "active")).strip() or "active"
        helloasso_api_key = str(payload.get("helloasso_api_key", "")).strip()
        helloasso_form_slug = str(payload.get("helloasso_form_slug", "")).strip()

        campaign = Campaign.objects.create(
            title=title,
            status=status,
            helloasso_api_key=helloasso_api_key,
            helloasso_form_slug=helloasso_form_slug,
        )

        return JsonResponse(
            {
                "campaign": {
                    "id": campaign.id,
                    "title": campaign.title,
                    "status": campaign.status,
                    "created_at": campaign.created_at.isoformat(),
                    "helloasso_api_key": campaign.helloasso_api_key,
                    "helloasso_form_slug": campaign.helloasso_form_slug,
                    "last_merge": campaign.last_merge.isoformat() if campaign.last_merge else None,
                    "last_manual_edition": (
                        campaign.last_manual_edition.isoformat()
                        if campaign.last_manual_edition
                        else None
                    ),
                }
            },
            status=201,
        )

    campaigns_qs = Campaign.objects.all().order_by("id")

    data = [
        {
            "id": campaign.id,
            "title": campaign.title,
            "status": campaign.status,
            "created_at": campaign.created_at.isoformat(),
            "helloasso_api_key": campaign.helloasso_api_key,
            "helloasso_form_slug": campaign.helloasso_form_slug,
            "last_merge": campaign.last_merge.isoformat() if campaign.last_merge else None,
            "last_manual_edition": (
                campaign.last_manual_edition.isoformat() if campaign.last_manual_edition else None
            ),
        }
        for campaign in campaigns_qs
    ]

    return JsonResponse({"campaigns": data})


@require_http_methods(["GET", "POST"])
def campaign_members(request, campaign_id):
    campaign = Campaign.objects.filter(id=campaign_id).first()
    if campaign is None:
        return JsonResponse({"error": f"Campaign {campaign_id} not found."}, status=404)

    if request.method == "POST":
        try:
            payload = json.loads(request.body.decode("utf-8") if request.body else "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            return JsonResponse({"error": "Invalid JSON payload."}, status=400)

        if not isinstance(payload, dict):
            return JsonResponse({"error": "Invalid JSON payload."}, status=400)

        member_payload = payload.get("member") if isinstance(payload.get("member"), dict) else payload

        first_name = _coerce_text(member_payload.get("first_name"))
        name = _coerce_text(member_payload.get("name"))
        email = _coerce_text(member_payload.get("email"))
        ffck_licence = _coerce_text(member_payload.get("ffck_licence"))
        certificat = _coerce_text(member_payload.get("certificat"))
        autorisation_parentale = _coerce_text(member_payload.get("autorisation_parentale"))
        photo = _coerce_text(member_payload.get("photo"))
        option_ia = _coerce_bool(member_payload.get("option_ia"))
        manual_review = _coerce_bool(member_payload.get("manual_review"))

        if not first_name:
            return JsonResponse({"error": "'first_name' is required."}, status=400)
        if not name:
            return JsonResponse({"error": "'name' is required."}, status=400)
        if not email:
            return JsonResponse({"error": "'email' is required."}, status=400)

        member = Member.objects.create(
            campaign=campaign,
            first_name=first_name,
            name=name,
            ffck_licence=ffck_licence,
            email=email,
            certificat=certificat,
            autorisation_parentale=autorisation_parentale,
            photo=photo,
            option_ia=option_ia,
            manual_review=manual_review,
        )

        return JsonResponse(
            {
                "member": {
                    "id": member.id,
                    "first_name": member.first_name,
                    "name": member.name,
                    "ffck_licence": member.ffck_licence,
                    "email": member.email,
                    "created_at": member.created_at.isoformat(),
                    "campaign_id": member.campaign_id,
                    "certificat": member.certificat,
                    "autorisation_parentale": member.autorisation_parentale,
                    "photo": member.photo,
                    "option_ia": member.option_ia,
                    "manual_review": member.manual_review,
                    "manual_review_label": "vérifié" if member.manual_review else "non vérifié",
                }
            },
            status=201,
        )

    members = Member.objects.filter(campaign=campaign).order_by("id")

    data = [
        {
            "id": member.id,
            "first_name": member.first_name,
            "name": member.name,
            "ffck_licence": member.ffck_licence,
            "email": member.email,
            "created_at": member.created_at.isoformat(),
            "campaign_id": member.campaign_id,
            "certificat": member.certificat,
            "autorisation_parentale": member.autorisation_parentale,
            "photo": member.photo,
            "option_ia": member.option_ia,
            "manual_review": member.manual_review,
            "manual_review_label": "vérifié" if member.manual_review else "non vérifié",
        }
        for member in members
    ]

    return JsonResponse({"members": data})


@require_POST
def campaign_members_bulk_delete(request, campaign_id):
    campaign = Campaign.objects.filter(id=campaign_id).first()
    if campaign is None:
        return JsonResponse({"error": f"Campaign {campaign_id} not found."}, status=404)

    try:
        payload = json.loads(request.body.decode("utf-8") if request.body else "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        return JsonResponse({"error": "Invalid JSON payload."}, status=400)

    if not isinstance(payload, dict):
        return JsonResponse({"error": "Invalid JSON payload."}, status=400)

    raw_ids = payload.get("member_ids")
    if not isinstance(raw_ids, list):
        return JsonResponse({"error": "'member_ids' must be an array."}, status=400)

    member_ids = []
    for item in raw_ids:
        try:
            member_id = int(item)
        except (TypeError, ValueError):
            continue
        member_ids.append(member_id)

    member_ids = sorted(set(member_ids))
    if not member_ids:
        return JsonResponse({"error": "No valid member id provided."}, status=400)

    members_to_delete = list(
        Member.objects.filter(campaign=campaign, id__in=member_ids).order_by("id")
    )
    deleted_member_ids = [member.id for member in members_to_delete]
    if not deleted_member_ids:
        return JsonResponse(
            {"deleted_member_ids": [], "deleted_count": 0, "campaign_id": campaign.id}
        )

    Member.objects.filter(id__in=deleted_member_ids, campaign=campaign).delete()

    return JsonResponse(
        {
            "campaign_id": campaign.id,
            "deleted_member_ids": deleted_member_ids,
            "deleted_count": len(deleted_member_ids),
        }
    )


def _coerce_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        return normalized in {"1", "true", "yes", "oui", "vérifié", "verifie", "verified"}
    return False


def _coerce_text(value):
    if value is None:
        return ""
    return str(value).strip()


def _serialize_duplicate_suggestion(suggestion: MemberDuplicateSuggestion) -> dict:
    return {
        "id": suggestion.id,
        "campaign_id": suggestion.campaign_id,
        "similarity_score": suggestion.similarity_score,
        "reasons": suggestion.reasons if isinstance(suggestion.reasons, list) else [],
        "status": suggestion.status,
        "created_at": suggestion.created_at.isoformat(),
        "resolved_at": suggestion.resolved_at.isoformat() if suggestion.resolved_at else None,
        "recommended_master_id": suggestion.recommended_master_id,
        "member_left": {
            "id": suggestion.member_left_id,
            "first_name": suggestion.member_left.first_name,
            "name": suggestion.member_left.name,
            "email": suggestion.member_left.email,
            "ffck_licence": suggestion.member_left.ffck_licence,
        },
        "member_right": {
            "id": suggestion.member_right_id,
            "first_name": suggestion.member_right.first_name,
            "name": suggestion.member_right.name,
            "email": suggestion.member_right.email,
            "ffck_licence": suggestion.member_right.ffck_licence,
        },
    }


@require_POST
def campaign_manual_edition(request, campaign_id):
    campaign = Campaign.objects.filter(id=campaign_id).first()
    if campaign is None:
        return JsonResponse({"error": f"Campaign {campaign_id} not found."}, status=404)

    try:
        payload = json.loads(request.body.decode("utf-8") if request.body else "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        return JsonResponse({"error": "Invalid JSON payload."}, status=400)

    members_payload = payload.get("members")
    if not isinstance(members_payload, list):
        return JsonResponse({"error": "'members' must be an array."}, status=400)

    requested_ids = []
    for item in members_payload:
        if not isinstance(item, dict):
            continue
        try:
            member_id = int(item.get("id"))
        except (TypeError, ValueError):
            continue
        requested_ids.append(member_id)

    members_by_id = {
        member.id: member
        for member in Member.objects.filter(campaign=campaign, id__in=requested_ids).order_by("id")
    }
    updated_member_ids = []

    with transaction.atomic():
        for item in members_payload:
            if not isinstance(item, dict):
                continue
            try:
                member_id = int(item.get("id"))
            except (TypeError, ValueError):
                continue
            member = members_by_id.get(member_id)
            if member is None:
                continue

            update_fields = []

            if "first_name" in item:
                next_value = _coerce_text(item.get("first_name"))
                if member.first_name != next_value:
                    member.first_name = next_value
                    update_fields.append("first_name")
            if "name" in item:
                next_value = _coerce_text(item.get("name"))
                if member.name != next_value:
                    member.name = next_value
                    update_fields.append("name")
            if "ffck_licence" in item:
                next_value = _coerce_text(item.get("ffck_licence"))
                if member.ffck_licence != next_value:
                    member.ffck_licence = next_value
                    update_fields.append("ffck_licence")
            if "email" in item:
                next_value = _coerce_text(item.get("email"))
                if member.email != next_value:
                    member.email = next_value
                    update_fields.append("email")
            if "certificat" in item:
                next_value = _coerce_text(item.get("certificat"))
                if member.certificat != next_value:
                    member.certificat = next_value
                    update_fields.append("certificat")
            if "autorisation_parentale" in item:
                next_value = _coerce_text(item.get("autorisation_parentale"))
                if member.autorisation_parentale != next_value:
                    member.autorisation_parentale = next_value
                    update_fields.append("autorisation_parentale")
            if "photo" in item:
                next_value = _coerce_text(item.get("photo"))
                if member.photo != next_value:
                    member.photo = next_value
                    update_fields.append("photo")
            if "option_ia" in item:
                next_value = _coerce_bool(item.get("option_ia"))
                if member.option_ia != next_value:
                    member.option_ia = next_value
                    update_fields.append("option_ia")
            if "manual_review" in item:
                next_value = _coerce_bool(item.get("manual_review"))
                if member.manual_review != next_value:
                    member.manual_review = next_value
                    update_fields.append("manual_review")

            if update_fields:
                member.save(update_fields=update_fields)
                updated_member_ids.append(member.id)

        campaign.last_manual_edition = timezone.now()
        campaign.save(update_fields=["last_manual_edition"])

    return JsonResponse(
        {
            "campaign_id": campaign.id,
            "updated_member_ids": updated_member_ids,
            "updated_count": len(updated_member_ids),
            "last_manual_edition": (
                campaign.last_manual_edition.isoformat() if campaign.last_manual_edition else None
            ),
        }
    )


@require_GET
@ensure_csrf_cookie
def campaign_member_duplicate_suggestions(request):
    campaign, error_response = _resolve_campaign(request)
    if error_response is not None:
        return error_response

    raw_min_score = str(request.GET.get("minScore", "0.8")).strip()
    try:
        min_score = float(raw_min_score)
    except ValueError:
        return JsonResponse({"error": "minScore must be a float."}, status=400)

    min_score = max(0.0, min(1.0, min_score))
    refresh = str(request.GET.get("refresh", "1")).strip().lower() not in {"0", "false", "no"}

    generation_summary = None
    service = MemberDedupService(campaign=campaign)
    if refresh:
        generation_summary = service.generate_suggestions(min_score=min_score)

    suggestions_qs = (
        MemberDuplicateSuggestion.objects.filter(
            campaign=campaign,
            status=MemberDuplicateSuggestion.STATUS_PENDING,
            similarity_score__gte=min_score,
        )
        .select_related("member_left", "member_right", "recommended_master")
        .order_by("-similarity_score", "-created_at")
    )

    return JsonResponse(
        {
            "campaign_id": campaign.id,
            "min_score": min_score,
            "generation": generation_summary,
            "suggestions": [_serialize_duplicate_suggestion(suggestion) for suggestion in suggestions_qs],
        }
    )


@require_POST
def campaign_member_duplicate_merge(request):
    campaign, error_response = _resolve_campaign(request)
    if error_response is not None:
        return error_response

    try:
        payload = json.loads(request.body.decode("utf-8") if request.body else "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        return JsonResponse({"error": "Invalid JSON payload."}, status=400)

    if not isinstance(payload, dict):
        return JsonResponse({"error": "Invalid JSON payload."}, status=400)

    raw_suggestion_id = payload.get("suggestion_id")
    try:
        suggestion_id = int(raw_suggestion_id)
    except (TypeError, ValueError):
        return JsonResponse({"error": "'suggestion_id' must be an integer."}, status=400)

    keep_member_id = payload.get("keep_member_id")
    if keep_member_id is not None:
        try:
            keep_member_id = int(keep_member_id)
        except (TypeError, ValueError):
            return JsonResponse({"error": "'keep_member_id' must be an integer."}, status=400)

    suggestion = (
        MemberDuplicateSuggestion.objects.filter(id=suggestion_id, campaign=campaign)
        .select_related("member_left", "member_right", "recommended_master")
        .first()
    )
    if suggestion is None:
        return JsonResponse({"error": f"Suggestion {suggestion_id} not found."}, status=404)

    try:
        merge_summary = MemberDedupService(campaign=campaign).merge_suggestion(
            suggestion=suggestion,
            keep_member_id=keep_member_id,
        )
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    campaign.last_manual_edition = timezone.now()
    campaign.save(update_fields=["last_manual_edition"])

    return JsonResponse(
        {
            "campaign_id": campaign.id,
            "merge": merge_summary,
            "last_manual_edition": (
                campaign.last_manual_edition.isoformat() if campaign.last_manual_edition else None
            ),
        }
    )


@require_GET
def helloasso_latest_items(request):
    campaign, error_response = _resolve_campaign(request)
    if error_response is not None:
        return error_response

    latest_import = HelloAssoImport.objects.filter(campaign=campaign).order_by("-fetched_at").first()
    if latest_import is None:
        return JsonResponse(
            {
                "campaign_id": campaign.id,
                "items": [],
                "import": None,
            }
        )

    items = _extract_items(latest_import.payload)
    return JsonResponse(
        {
            "campaign_id": campaign.id,
            "items": items,
            "import": {
                "id": latest_import.id,
                "fetched_at": latest_import.fetched_at.isoformat(),
                "items_count": latest_import.items_count,
                "organization_slug": latest_import.organization_slug,
                "form_type": latest_import.form_type,
                "form_slug": latest_import.form_slug,
                "with_details": latest_import.with_details,
            },
        }
    )


@require_GET
def helloasso_sync_campaign_members(request):
    campaign, error_response = _resolve_campaign(request)
    if error_response is not None:
        return error_response

    sync_summary = HelloAssoMemberSyncService(campaign=campaign).sync_latest_import()
    _mark_campaign_last_merge(campaign)

    return JsonResponse(
        {
            "campaign_id": campaign.id,
            "member_sync": sync_summary,
            "last_merge": campaign.last_merge.isoformat() if campaign.last_merge else None,
        }
    )



@require_GET
def helloasso_import_campaign(request):
    campaign, error_response = _resolve_campaign(request)
    if error_response is not None:
        return error_response

    organization_slug = getattr(settings, "HELLOASSO_ORGANIZATION_SLUG", "").strip()
    form_type = getattr(settings, "HELLOASSO_FORM_TYPE", "Membership").strip() or "Membership"
    form_slug = campaign.helloasso_form_slug.strip()

    if not form_slug:
        return JsonResponse(
            {
                "error": (
                    "Campaign.helloasso_form_slug is empty. It must contain the HelloAsso form slug."
                )
            },
            status=400,
        )

    with_details_raw = request.GET.get("withDetails", "true").strip().lower()
    with_details = with_details_raw not in {"0", "false", "no"}

    try:
        service = HelloAssoService(
            client_id=getattr(settings, "HELLOASSO_CLIENT_ID", ""),
            client_secret=getattr(settings, "HELLOASSO_CLIENT_SECRET", ""),
        )
        payload = service.get_form_items(
            organization_slug=organization_slug,
            form_type=form_type,
            form_slug=form_slug,
            with_details=with_details,
        )

        items = _extract_items(payload)

        with transaction.atomic():
            import_record = HelloAssoImport.objects.create(
                campaign=campaign,
                source="form_items",
                organization_slug=organization_slug,
                form_type=form_type,
                form_slug=form_slug,
                with_details=with_details,
                items_count=len(items),
                payload=payload,
            )

            for item in items:
                if not isinstance(item, dict):
                    continue

                payer_email = _extract_email(item)

                HelloAssoItem.objects.update_or_create(
                    helloasso_id=_extract_helloasso_id(item),
                    organization_slug=organization_slug,
                    form_type=form_type,
                    form_slug=form_slug,
                    defaults={
                        "status": _extract_status(item),
                        "payer_email": payer_email,
                        "amount": _extract_amount(item),
                        "paid_at": _extract_paid_at(item),
                        "latest_import": import_record,
                        "raw_item": item,
                    },
                )

            sync_summary = HelloAssoMemberSyncService(campaign=campaign).sync_latest_import(
                import_record=import_record
            )
            _mark_campaign_last_merge(campaign)

        return JsonResponse(
            {
                "import_id": import_record.id,
                "campaign_id": campaign.id,
                "items_count": len(items),
                "payload": payload,
                "member_sync": sync_summary,
                "last_merge": campaign.last_merge.isoformat() if campaign.last_merge else None,
            }
        )
    except HelloAssoConfigError as exc:
        return JsonResponse({"error": str(exc)}, status=500)
    except HelloAssoAPIError as exc:
        return JsonResponse({"error": str(exc)}, status=502)


@require_GET
def ffck_latest_rows(request):
    raw_campaign_id = str(request.GET.get("campaignId", "")).strip()
    if not raw_campaign_id:
        return JsonResponse({"error": "campaignId is required."}, status=400)

    try:
        campaign_id = int(raw_campaign_id)
    except ValueError:
        return JsonResponse({"error": "campaignId must be an integer."}, status=400)

    campaign = Campaign.objects.filter(id=campaign_id).first()
    if campaign is None:
        return JsonResponse({"error": f"Campaign {campaign_id} not found."}, status=404)

    latest_export = FfckExport.objects.filter(campaign=campaign).order_by("-fetched_at", "-id").first()
    if latest_export is None:
        return JsonResponse(
            {
                "campaign_id": campaign.id,
                "rows": [],
                "export": None,
            }
        )

    rows = [
        {
            "id": row.id,
            "row_index": row.row_index,
            "licence": row.licence,
            "nom": row.nom,
            "categorie": row.categorie,
            "certificat": row.certificat,
            "member_id": row.member_id,
            "raw_row": row.raw_row,
        }
        for row in FfckExportRow.objects.filter(ffck_export=latest_export)
        .select_related("member")
        .order_by("row_index", "id")
    ]

    return JsonResponse(
        {
            "campaign_id": campaign.id,
            "rows": rows,
            "export": {
                "id": latest_export.id,
                "fetched_at": latest_export.fetched_at.isoformat(),
                "rows_count": latest_export.rows_count,
                "filename": latest_export.filename,
                "structure_id": latest_export.structure_id,
                "content_type": latest_export.content_type,
                "file_size": latest_export.file_size,
            },
        }
    )


@require_GET
def ffck_sync_campaign_members(request):
    campaign, error_response = _resolve_campaign(request)
    if error_response is not None:
        return error_response

    sync_summary = FfckMemberSyncService(campaign=campaign).sync_latest_export()
    _mark_campaign_last_merge(campaign)

    return JsonResponse(
        {
            "campaign_id": campaign.id,
            "member_sync": sync_summary,
            "last_merge": campaign.last_merge.isoformat() if campaign.last_merge else None,
        }
    )


@require_GET
def sync_campaign_members(request):
    campaign, error_response = _resolve_campaign(request)
    if error_response is not None:
        return error_response

    helloasso_sync_summary = HelloAssoMemberSyncService(campaign=campaign).sync_latest_import()
    ffck_sync_summary = FfckMemberSyncService(campaign=campaign).sync_latest_export()
    _mark_campaign_last_merge(campaign)

    return JsonResponse(
        {
            "campaign_id": campaign.id,
            "helloasso_member_sync": helloasso_sync_summary,
            "ffck_member_sync": ffck_sync_summary,
            "last_merge": campaign.last_merge.isoformat() if campaign.last_merge else None,
        }
    )


@require_GET
def federation_extranet_extract_excel(request):
    campaign = None
    raw_campaign_id = str(request.GET.get("campaignId", "")).strip()
    if raw_campaign_id:
        try:
            campaign_id = int(raw_campaign_id)
        except ValueError:
            return JsonResponse({"error": "campaignId must be an integer."}, status=400)
        campaign = Campaign.objects.filter(id=campaign_id).first()
        if campaign is None:
            return JsonResponse({"error": f"Campaign {campaign_id} not found."}, status=404)

    try:
        service = FederationExtranetService(
            base_url=getattr(settings, "FFCK_EXTRANET_BASE_URL", ""),
            login_path=getattr(settings, "FFCK_EXTRANET_LOGIN_PATH", ""),
            totp_path=getattr(settings, "FFCK_EXTRANET_TOTP_PATH", ""),
            token_path=getattr(settings, "FFCK_EXTRANET_TOKEN_PATH", ""),
            export_path=getattr(settings, "FFCK_EXTRANET_EXPORT_PATH", ""),
            username=getattr(settings, "FFCK_EXTRANET_USERNAME", ""),
            password=getattr(settings, "FFCK_EXTRANET_PASSWORD", ""),
            totp_secret=getattr(settings, "FFCK_EXTRANET_TOTP_SECRET", ""),
            token_field=getattr(settings, "FFCK_EXTRANET_TOKEN_FIELD", "access_token"),
            token_cookie_name=getattr(settings, "FFCK_EXTRANET_TOKEN_COOKIE_NAME", ""),
            username_field=getattr(settings, "FFCK_EXTRANET_USERNAME_FIELD", "username"),
            password_field=getattr(settings, "FFCK_EXTRANET_PASSWORD_FIELD", "password"),
            totp_field=getattr(settings, "FFCK_EXTRANET_TOTP_FIELD", "code"),
            token_type=getattr(settings, "FFCK_EXTRANET_TOKEN_TYPE", "Bearer"),
            login_extra_payload=getattr(settings, "FFCK_EXTRANET_LOGIN_EXTRA_PAYLOAD", ""),
            totp_extra_payload=getattr(settings, "FFCK_EXTRANET_TOTP_EXTRA_PAYLOAD", ""),
            export_method=getattr(settings, "FFCK_EXTRANET_EXPORT_METHOD", "POST"),
            export_form_path=getattr(settings, "FFCK_EXTRANET_EXPORT_FORM_PATH", ""),
            export_extra_payload=getattr(settings, "FFCK_EXTRANET_EXPORT_EXTRA_PAYLOAD", ""),
            structure_select_path=getattr(settings, "FFCK_EXTRANET_STRUCTURE_SELECT_PATH", ""),
        )
        extraction = service.extract_excel()

        import_summary = None
        if campaign is not None:
            export_payload = {}
            raw_payload = str(getattr(settings, "FFCK_EXTRANET_EXPORT_EXTRA_PAYLOAD", "")).strip()
            if raw_payload:
                try:
                    parsed = json.loads(raw_payload)
                    if isinstance(parsed, dict):
                        export_payload = parsed
                except json.JSONDecodeError:
                    export_payload = {}

            import_summary = FfckExportImportService(campaign=campaign).import_extraction(
                extraction,
                structure_select_path=getattr(settings, "FFCK_EXTRANET_STRUCTURE_SELECT_PATH", ""),
                export_path=getattr(settings, "FFCK_EXTRANET_EXPORT_PATH", ""),
                export_method=getattr(settings, "FFCK_EXTRANET_EXPORT_METHOD", "POST"),
                export_payload=export_payload,
            )

        response = HttpResponse(extraction.content, content_type=extraction.content_type)
        response["Content-Disposition"] = f'attachment; filename="{extraction.filename}"'
        response["Content-Length"] = str(len(extraction.content))
        if import_summary is not None:
            response["X-FFCK-Export-Id"] = str(import_summary["ffck_export_id"])
            response["X-FFCK-Rows-Count"] = str(import_summary["rows_count"])
        return response
    except FederationExtranetConfigError as exc:
        return JsonResponse({"error": str(exc)}, status=500)
    except FederationExtranetAuthError as exc:
        return JsonResponse({"error": str(exc)}, status=502)
    except FederationExtranetExportError as exc:
        return JsonResponse({"error": str(exc)}, status=502)
    except FfckExportImportError as exc:
        return JsonResponse({"error": str(exc)}, status=502)
