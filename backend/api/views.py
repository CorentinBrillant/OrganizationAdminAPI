import hashlib
import ipaddress
import json
import mimetypes
from decimal import Decimal, InvalidOperation
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .auth import create_user_token, require_api_token, revoke_token
from .models import (
    BadgeImport,
    BadgeImportRow,
    Campaign,
    FfckExport,
    FfckExportRow,
    HelloAssoImport,
    HelloAssoItem,
    Member,
    MemberDuplicateSuggestion,
    UserLogin,
)
from .services.badge_import_service import (
    BadgeExcelExtraction,
    BadgeImportError,
    BadgeImportService,
)
from .services.federation_extranet_service import (
    FederationExtranetAuthError,
    FederationExtranetConfigError,
    FederationExtranetExportError,
    FederationExtranetService,
)
from .services.ffck_export_import_service import FfckExportImportError, FfckExportImportService
from .services.helloasso_service import (
    HelloAssoAPIError,
    HelloAssoConfigError,
    HelloAssoService,
)
from .services.member_dedup_service import MemberDedupService
from .services.member_sync_service import (
    BadgeMemberSyncService,
    FfckMemberSyncService,
    HelloAssoMemberSyncService,
)


def _nested_get(obj, *keys):
    current = obj
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
        if current is None:
            return None
    return current


def _request_ip_address(request):
    candidate = request.META.get("HTTP_X_REAL_IP") or request.META.get("REMOTE_ADDR")
    try:
        return str(ipaddress.ip_address(str(candidate)))
    except ValueError:
        return None


def _xlsx_column_name(index: int) -> str:
    name = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name


def _xlsx_text(value) -> str:
    text = str(value if value is not None else "")
    text = "".join(char for char in text if ord(char) >= 32 or char in "\t\n\r")
    if text.startswith(("=", "+", "-", "@")):
        text = f"'{text}"
    return escape(text)


def _build_xlsx(headers: list[str], rows: list[list[str]]) -> bytes:
    worksheet_rows = []
    for row_index, values in enumerate([headers, *rows], start=1):
        cells = "".join(
            (
                f'<c r="{_xlsx_column_name(column_index)}{row_index}" t="inlineStr">'
                f'<is><t xml:space="preserve">{_xlsx_text(value)}</t></is></c>'
            )
            for column_index, value in enumerate(values, start=1)
        )
        worksheet_rows.append(f'<row r="{row_index}">{cells}</row>')

    worksheet_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"<sheetData>{''.join(worksheet_rows)}</sheetData>"
        "</worksheet>"
    )
    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="Inscriptions" sheetId="1" r:id="rId1"/></sheets>'
        "</workbook>"
    )
    content_types_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        "</Types>"
    )
    root_rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="xl/workbook.xml"/>'
        "</Relationships>"
    )
    workbook_rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        'Target="worksheets/sheet1.xml"/>'
        "</Relationships>"
    )

    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types_xml)
        archive.writestr("_rels/.rels", root_rels_xml)
        archive.writestr("xl/workbook.xml", workbook_xml)
        archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels_xml)
        archive.writestr("xl/worksheets/sheet1.xml", worksheet_xml)
    return output.getvalue()


def _extract_items(payload):
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except (TypeError, ValueError):
            payload = {}
    data = payload.get("data") if isinstance(payload, dict) else None
    return data if isinstance(data, list) else []


def _coerce_dict(value):
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return {}
        if isinstance(parsed, dict):
            return parsed
    return {}


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


def _helloasso_lookup_key(
    helloasso_id: str, organization_slug: str, form_type: str, form_slug: str
) -> str:
    payload = "|".join(
        [
            str(helloasso_id or "").strip(),
            str(organization_slug or "").strip(),
            str(form_type or "").strip(),
            str(form_slug or "").strip(),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


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
            {"error": ("campaignId is required (query param or HELLOASSO_CAMPAIGN_ID setting).")},
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


def _resolve_campaign_member(campaign_id, member_id):
    campaign = Campaign.objects.filter(id=campaign_id).first()
    if campaign is None:
        return None, None, JsonResponse({"error": f"Campaign {campaign_id} not found."}, status=404)

    member = Member.objects.filter(campaign_id=campaign_id, id=member_id).first()
    if member is None or member.is_deleted:
        return campaign, None, JsonResponse({"error": f"Member {member_id} not found."}, status=404)

    return campaign, member, None


def _serialize_member(member: Member) -> dict:
    certificat_file_name = member.certificat_file.name if member.certificat_file else ""
    return {
        "id": member.id,
        "first_name": member.first_name,
        "name": member.name,
        "ffck_licence": member.ffck_licence,
        "ffck_certificat": member.ffck_certificat,
        "ffck_certificat_expiration": member.ffck_certificat_expiration,
        "ffck_licence_type": member.ffck_licence_type,
        "helloasso_form_slug": member.helloasso_form_slug,
        "email": member.email,
        "created_at": member.created_at.isoformat(),
        "campaign_id": member.campaign_id,
        "certificat": member.certificat,
        "certificat_file": {
            "uploaded": bool(certificat_file_name),
            "filename": member.certificat_file_original_name if certificat_file_name else "",
            "content_type": member.certificat_file_content_type if certificat_file_name else "",
            "size": member.certificat_file_size if certificat_file_name else 0,
            "uploaded_at": (
                member.certificat_file_uploaded_at.isoformat()
                if member.certificat_file_uploaded_at and certificat_file_name
                else None
            ),
        },
        "autorisation_parentale": member.autorisation_parentale,
        "photo": member.photo,
        "option_ia": member.option_ia,
        "manual_review": member.manual_review,
        "manual_review_label": "vérifié" if member.manual_review else "non vérifié",
        "badge_owned": member.badge_owned,
        "badge_ordered": member.badge_ordered,
    }


def _validate_certificat_upload(upload):
    original_name = str(getattr(upload, "name", "")).strip()
    extension = Path(original_name).suffix.lower()
    content_type = str(getattr(upload, "content_type", "")).strip().lower()
    size = int(getattr(upload, "size", 0) or 0)

    allowed_extensions = set(getattr(settings, "MEMBER_CERTIFICAT_ALLOWED_EXTENSIONS", []))
    allowed_types = set(getattr(settings, "MEMBER_CERTIFICAT_ALLOWED_CONTENT_TYPES", []))
    max_size = int(getattr(settings, "MEMBER_CERTIFICAT_MAX_BYTES", 0) or 0)

    if not original_name:
        return "Uploaded file name is required."
    if allowed_extensions and extension not in allowed_extensions:
        return (
            "Unsupported file extension. Allowed extensions: "
            + ", ".join(sorted(allowed_extensions))
            + "."
        )
    if allowed_types and content_type not in allowed_types:
        return (
            "Unsupported content type. Allowed content types: "
            + ", ".join(sorted(allowed_types))
            + "."
        )
    if max_size > 0 and size > max_size:
        return f"File is too large. Maximum allowed size is {max_size} bytes."
    return None


def _build_member_certificat_fernet():
    key = str(getattr(settings, "MEMBER_CERTIFICAT_ENCRYPTION_KEY", "")).strip()
    if not key:
        return None, "MEMBER_CERTIFICAT_ENCRYPTION_KEY must be configured."

    try:
        return Fernet(key.encode("utf-8")), None
    except Exception:
        return (
            None,
            "MEMBER_CERTIFICAT_ENCRYPTION_KEY is invalid. Expected a URL-safe base64 key.",
        )


@csrf_exempt
@require_POST
def auth_login(request):
    try:
        payload = json.loads(request.body.decode("utf-8") if request.body else "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        return JsonResponse({"error": "Invalid JSON payload."}, status=400)

    if not isinstance(payload, dict):
        return JsonResponse({"error": "Invalid JSON payload."}, status=400)

    username = str(payload.get("username", "")).strip()
    password = str(payload.get("password", "")).strip()
    if not username or not password:
        return JsonResponse({"error": "'username' and 'password' are required."}, status=400)

    user = authenticate(request, username=username, password=password)
    if user is None or not getattr(user, "is_active", False):
        return JsonResponse({"error": "Invalid credentials."}, status=401)

    UserLogin.objects.create(
        user=user,
        username=user.get_username(),
        ip_address=_request_ip_address(request),
        user_agent=str(request.META.get("HTTP_USER_AGENT", ""))[:512],
    )
    token = create_user_token(user)
    ttl = int(getattr(settings, "API_AUTH_TOKEN_TTL_SECONDS", 3600))

    return JsonResponse(
        {
            "token": token,
            "token_type": "Bearer",
            "expires_in": ttl,
            "user": {
                "id": user.id,
                "username": user.get_username(),
            },
        }
    )


@require_GET
def auth_session(request):
    user = getattr(request, "auth_user", None)
    return JsonResponse(
        {
            "authenticated": True,
            "auth_via": getattr(request, "auth_via", "unknown"),
            "user": (
                {
                    "id": user.id,
                    "username": user.get_username(),
                }
                if user is not None
                else None
            ),
        }
    )


@require_POST
@require_api_token
def auth_change_password(request):
    if getattr(request, "auth_via", "") != "user_token":
        return JsonResponse(
            {"error": "Password changes require an authenticated user session."}, status=403
        )

    try:
        payload = json.loads(request.body.decode("utf-8") if request.body else "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        return JsonResponse({"error": "Invalid JSON payload."}, status=400)

    if not isinstance(payload, dict):
        return JsonResponse({"error": "Invalid JSON payload."}, status=400)

    current_password = payload.get("current_password")
    new_password = payload.get("new_password")
    new_password_confirmation = payload.get("new_password_confirmation")
    if not all(isinstance(value, str) and value for value in (current_password, new_password)):
        return JsonResponse({"error": "Current and new passwords are required."}, status=400)
    if new_password != new_password_confirmation:
        return JsonResponse({"error": "New passwords do not match."}, status=400)

    user = getattr(request, "auth_user", None)
    if user is None or not user.check_password(current_password):
        return JsonResponse({"error": "Current password is incorrect."}, status=400)

    try:
        validate_password(new_password, user=user)
    except ValidationError as exc:
        return JsonResponse({"error": " ".join(exc.messages)}, status=400)

    user.set_password(new_password)
    user.save(update_fields=["password"])
    return JsonResponse({"password_changed": True})


@require_POST
@require_api_token
def auth_logout(request):
    if getattr(request, "auth_via", "") == "static_token":
        return JsonResponse({"error": "Static token cannot be revoked."}, status=400)

    token = str(getattr(request, "auth_token", "")).strip()
    revoke_token(token)
    response = JsonResponse({"logged_out": True})
    response.delete_cookie("api_token", path="/")
    return response


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


@require_http_methods(["POST"])
def campaign_settings(request, campaign_id):
    campaign = Campaign.objects.filter(id=campaign_id).first()
    if campaign is None:
        return JsonResponse({"error": f"Campaign {campaign_id} not found."}, status=404)

    try:
        payload = json.loads(request.body.decode("utf-8") if request.body else "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        return JsonResponse({"error": "Invalid JSON payload."}, status=400)

    if not isinstance(payload, dict):
        return JsonResponse({"error": "Invalid JSON payload."}, status=400)

    helloasso_form_slug = str(payload.get("helloasso_form_slug", "")).strip()
    campaign.helloasso_form_slug = helloasso_form_slug
    campaign.save(update_fields=["helloasso_form_slug"])

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
        }
    )


@require_POST
def campaign_members_export(request, campaign_id):
    get_object_or_404(Campaign, id=campaign_id)
    try:
        payload = json.loads(request.body.decode("utf-8") if request.body else "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        return JsonResponse({"error": "Invalid JSON payload."}, status=400)

    headers = payload.get("headers") if isinstance(payload, dict) else None
    rows = payload.get("rows") if isinstance(payload, dict) else None
    if not isinstance(headers, list) or not headers or not isinstance(rows, list):
        return JsonResponse({"error": "'headers' and 'rows' are required."}, status=400)
    if len(headers) > 30 or len(rows) > 10000:
        return JsonResponse({"error": "Export exceeds the allowed size."}, status=400)
    if not all(isinstance(header, str) and header.strip() for header in headers):
        return JsonResponse({"error": "Export headers are invalid."}, status=400)
    if any(not isinstance(row, list) or len(row) != len(headers) for row in rows):
        return JsonResponse({"error": "Export rows are invalid."}, status=400)

    content = _build_xlsx(headers, rows)
    response = HttpResponse(
        content,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f'attachment; filename="inscriptions-{campaign_id}.xlsx"'
    return response


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

        member_payload = (
            payload.get("member") if isinstance(payload.get("member"), dict) else payload
        )

        first_name = _coerce_text(member_payload.get("first_name"))
        name = _coerce_text(member_payload.get("name"))
        email = _coerce_text(member_payload.get("email"))
        ffck_licence = _coerce_text(member_payload.get("ffck_licence"))
        ffck_certificat = _coerce_text(member_payload.get("ffck_certificat"))
        ffck_certificat_expiration = _coerce_text(member_payload.get("ffck_certificat_expiration"))
        ffck_licence_type = _coerce_text(member_payload.get("ffck_licence_type"))
        helloasso_form_slug = _coerce_text(member_payload.get("helloasso_form_slug"))
        certificat = _coerce_text(member_payload.get("certificat"))
        autorisation_parentale = _coerce_text(member_payload.get("autorisation_parentale"))
        photo = _coerce_text(member_payload.get("photo"))
        option_ia = _coerce_bool(member_payload.get("option_ia"))
        manual_review = _coerce_bool(member_payload.get("manual_review"))
        badge_owned = _coerce_bool(member_payload.get("badge_owned"))
        badge_ordered = _coerce_bool(member_payload.get("badge_ordered"))

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
            ffck_certificat=ffck_certificat,
            ffck_certificat_expiration=ffck_certificat_expiration,
            ffck_licence_type=ffck_licence_type,
            helloasso_form_slug=helloasso_form_slug,
            email=email,
            certificat=certificat,
            autorisation_parentale=autorisation_parentale,
            photo=photo,
            option_ia=option_ia,
            manual_review=manual_review,
            badge_owned=badge_owned,
            badge_ordered=badge_ordered,
        )

        return JsonResponse(
            {"member": _serialize_member(member)},
            status=201,
        )

    members = [
        member
        for member in Member.objects.filter(campaign=campaign).order_by("id")
        if not member.is_deleted
    ]

    data = [_serialize_member(member) for member in members]

    return JsonResponse({"members": data})


@require_POST
def campaign_member_certificat_upload(request, campaign_id, member_id):
    _, member, error_response = _resolve_campaign_member(campaign_id, member_id)
    if error_response is not None:
        return error_response

    upload = request.FILES.get("file")
    if upload is None:
        return JsonResponse({"error": "'file' is required as multipart upload."}, status=400)

    validation_error = _validate_certificat_upload(upload)
    if validation_error:
        return JsonResponse({"error": validation_error}, status=400)

    fernet, key_error = _build_member_certificat_fernet()
    if key_error:
        return JsonResponse({"error": key_error}, status=500)

    raw_content = upload.read()
    if not raw_content:
        return JsonResponse({"error": "Uploaded file is empty."}, status=400)

    encrypted_content = fernet.encrypt(raw_content)
    old_file_name = member.certificat_file.name if member.certificat_file else ""
    member.certificat_file.save(
        f"{upload.name}.enc",
        ContentFile(encrypted_content),
        save=False,
    )
    member.certificat_file_original_name = str(getattr(upload, "name", "")).strip()
    member.certificat_file_content_type = str(getattr(upload, "content_type", "")).strip().lower()
    member.certificat_file_size = len(raw_content)
    member.certificat_file_uploaded_at = timezone.now()
    member.save(
        update_fields=[
            "certificat_file",
            "certificat_file_original_name",
            "certificat_file_content_type",
            "certificat_file_size",
            "certificat_file_uploaded_at",
        ]
    )

    if old_file_name and old_file_name != member.certificat_file.name:
        member.certificat_file.storage.delete(old_file_name)

    return JsonResponse({"member": _serialize_member(member)})


@require_GET
def campaign_member_certificat_download(request, campaign_id, member_id):
    _, member, error_response = _resolve_campaign_member(campaign_id, member_id)
    if error_response is not None:
        return error_response

    if not member.certificat_file:
        return JsonResponse({"error": "No uploaded certificate for this member."}, status=404)

    fernet, key_error = _build_member_certificat_fernet()
    if key_error:
        return JsonResponse({"error": key_error}, status=500)

    encrypted_content = member.certificat_file.read()
    try:
        decrypted_content = fernet.decrypt(encrypted_content)
    except InvalidToken:
        return JsonResponse(
            {
                "error": (
                    "Failed to decrypt certificate file. "
                    "Ensure MEMBER_CERTIFICAT_ENCRYPTION_KEY matches the upload key."
                )
            },
            status=500,
        )

    download_name = member.certificat_file_original_name or Path(member.certificat_file.name).name
    response = HttpResponse(
        decrypted_content,
        content_type=member.certificat_file_content_type or "application/octet-stream",
    )
    response["Content-Disposition"] = f'attachment; filename="{download_name}"'
    return response


@require_http_methods(["DELETE"])
def campaign_member_certificat_delete(request, campaign_id, member_id):
    _, member, error_response = _resolve_campaign_member(campaign_id, member_id)
    if error_response is not None:
        return error_response

    if not member.certificat_file:
        return JsonResponse({"deleted": False, "reason": "no_file"})

    member.certificat_file.delete(save=False)
    member.certificat_file_original_name = ""
    member.certificat_file_content_type = ""
    member.certificat_file_size = 0
    member.certificat_file_uploaded_at = None
    member.save(
        update_fields=[
            "certificat_file",
            "certificat_file_original_name",
            "certificat_file_content_type",
            "certificat_file_size",
            "certificat_file_uploaded_at",
        ]
    )
    return JsonResponse({"deleted": True})


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

    members_to_delete = [
        member
        for member in Member.objects.filter(campaign=campaign, id__in=member_ids).order_by("id")
        if not member.is_deleted
    ]
    deleted_member_ids = [member.id for member in members_to_delete]
    if not deleted_member_ids:
        return JsonResponse(
            {"deleted_member_ids": [], "deleted_count": 0, "campaign_id": campaign.id}
        )

    for member in members_to_delete:
        member.is_deleted = True
        member.save(update_fields=["is_deleted"])

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
        for member in Member.objects.filter(
            campaign=campaign,
            id__in=requested_ids,
        ).order_by("id")
        if not member.is_deleted
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
            if "ffck_certificat" in item:
                next_value = _coerce_text(item.get("ffck_certificat"))
                if member.ffck_certificat != next_value:
                    member.ffck_certificat = next_value
                    update_fields.append("ffck_certificat")
            if "ffck_certificat_expiration" in item:
                next_value = _coerce_text(item.get("ffck_certificat_expiration"))
                if member.ffck_certificat_expiration != next_value:
                    member.ffck_certificat_expiration = next_value
                    update_fields.append("ffck_certificat_expiration")
            if "ffck_licence_type" in item:
                next_value = _coerce_text(item.get("ffck_licence_type"))
                if member.ffck_licence_type != next_value:
                    member.ffck_licence_type = next_value
                    update_fields.append("ffck_licence_type")
            if "helloasso_form_slug" in item:
                next_value = _coerce_text(item.get("helloasso_form_slug"))
                if member.helloasso_form_slug != next_value:
                    member.helloasso_form_slug = next_value
                    update_fields.append("helloasso_form_slug")
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
            if "badge_owned" in item:
                next_value = _coerce_bool(item.get("badge_owned"))
                if member.badge_owned != next_value:
                    member.badge_owned = next_value
                    update_fields.append("badge_owned")
            if "badge_ordered" in item:
                next_value = _coerce_bool(item.get("badge_ordered"))
                if member.badge_ordered != next_value:
                    member.badge_ordered = next_value
                    update_fields.append("badge_ordered")

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
    suggestions = [
        suggestion
        for suggestion in suggestions_qs
        if not suggestion.member_left.is_deleted and not suggestion.member_right.is_deleted
    ]

    return JsonResponse(
        {
            "campaign_id": campaign.id,
            "min_score": min_score,
            "generation": generation_summary,
            "suggestions": [
                _serialize_duplicate_suggestion(suggestion) for suggestion in suggestions
            ],
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
        MemberDuplicateSuggestion.objects.filter(
            id=suggestion_id,
            campaign=campaign,
        )
        .select_related("member_left", "member_right", "recommended_master")
        .first()
    )
    if (
        suggestion is None
        or suggestion.member_left.is_deleted
        or suggestion.member_right.is_deleted
    ):
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

    latest_import = (
        HelloAssoImport.objects.filter(campaign=campaign).order_by("-fetched_at").first()
    )
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

                helloasso_id = _extract_helloasso_id(item)
                lookup_key = _helloasso_lookup_key(
                    helloasso_id=helloasso_id,
                    organization_slug=organization_slug,
                    form_type=form_type,
                    form_slug=form_slug,
                )
                payer_email = _extract_email(item)

                HelloAssoItem.objects.update_or_create(
                    helloasso_lookup_key=lookup_key,
                    defaults={
                        "helloasso_id": helloasso_id,
                        "organization_slug": organization_slug,
                        "form_type": form_type,
                        "form_slug": form_slug,
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
def helloasso_membership_forms(request):
    organization_slug = getattr(settings, "HELLOASSO_ORGANIZATION_SLUG", "").strip()
    if not organization_slug:
        return JsonResponse(
            {"error": "HELLOASSO_ORGANIZATION_SLUG must be configured."},
            status=500,
        )

    try:
        service = HelloAssoService(
            client_id=getattr(settings, "HELLOASSO_CLIENT_ID", "").strip(),
            client_secret=getattr(settings, "HELLOASSO_CLIENT_SECRET", "").strip(),
        )
        forms = service.get_membership_forms(organization_slug=organization_slug)
    except HelloAssoConfigError as exc:
        return JsonResponse({"error": str(exc)}, status=500)
    except HelloAssoAPIError as exc:
        return JsonResponse({"error": str(exc)}, status=502)

    return JsonResponse(
        {
            "organization_slug": organization_slug,
            "forms": forms,
        }
    )


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

    latest_export = (
        FfckExport.objects.filter(campaign=campaign).order_by("-fetched_at", "-id").first()
    )
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
            "photo": row.photo.name,
            "member_id": row.member_id,
            "raw_row": _coerce_dict(row.raw_row),
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
def ffck_row_photo_download(request, row_id):
    row = get_object_or_404(FfckExportRow, id=row_id)
    if not row.photo:
        return JsonResponse({"error": "No FFCK photo for this row."}, status=404)

    filename = row.photo_original_name or Path(row.photo.name).name
    try:
        with row.photo.open("rb") as photo_file:
            content = photo_file.read()
    except FileNotFoundError:
        return JsonResponse({"error": "FFCK photo file not found."}, status=404)

    if row.photo.name.endswith(".enc"):
        fernet, key_error = _build_member_certificat_fernet()
        if key_error:
            return JsonResponse({"error": key_error}, status=500)
        try:
            content = fernet.decrypt(content)
        except InvalidToken:
            return JsonResponse({"error": "Failed to decrypt FFCK photo file."}, status=500)

    response = HttpResponse(
        content,
        content_type=mimetypes.guess_type(filename)[0] or "application/octet-stream",
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@require_GET
def badge_latest_rows(request):
    campaign, error_response = _resolve_campaign(request)
    if error_response is not None:
        return error_response

    latest_import = (
        BadgeImport.objects.filter(campaign=campaign).order_by("-fetched_at", "-id").first()
    )
    if latest_import is None:
        return JsonResponse(
            {
                "campaign_id": campaign.id,
                "rows": [],
                "import": None,
            }
        )

    rows = [
        {
            "id": row.id,
            "row_index": row.row_index,
            "licence": row.licence,
            "first_name": row.first_name,
            "name": row.name,
            "badge_owned": row.badge_owned,
            "badge_ordered": row.badge_ordered,
            "member_id": row.member_id,
            "raw_row": _coerce_dict(row.raw_row),
        }
        for row in BadgeImportRow.objects.filter(badge_import=latest_import)
        .select_related("member")
        .order_by("row_index", "id")
    ]

    return JsonResponse(
        {
            "campaign_id": campaign.id,
            "rows": rows,
            "import": {
                "id": latest_import.id,
                "fetched_at": latest_import.fetched_at.isoformat(),
                "rows_count": latest_import.rows_count,
                "filename": latest_import.filename,
                "content_type": latest_import.content_type,
                "file_size": latest_import.file_size,
            },
        }
    )


@require_POST
def badge_import_campaign(request):
    campaign, error_response = _resolve_campaign(request)
    if error_response is not None:
        return error_response

    upload = request.FILES.get("file")
    if upload is None:
        return JsonResponse({"error": "'file' is required as multipart upload."}, status=400)

    raw_content = upload.read()
    if not raw_content:
        return JsonResponse({"error": "Uploaded file is empty."}, status=400)

    extraction = BadgeExcelExtraction(
        filename=getattr(upload, "name", "badges.xlsx"),
        content_type=getattr(
            upload,
            "content_type",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ),
        content=raw_content,
    )

    try:
        import_summary = BadgeImportService(campaign=campaign).import_extraction(extraction)
        sync_summary = BadgeMemberSyncService(campaign=campaign).sync_latest_import()
        _mark_campaign_last_merge(campaign)
        return JsonResponse(
            {
                "campaign_id": campaign.id,
                "import": import_summary,
                "member_sync": sync_summary,
                "last_merge": campaign.last_merge.isoformat() if campaign.last_merge else None,
            }
        )
    except BadgeImportError as exc:
        return JsonResponse({"error": str(exc)}, status=400)


@require_GET
def badge_sync_campaign_members(request):
    campaign, error_response = _resolve_campaign(request)
    if error_response is not None:
        return error_response

    sync_summary = BadgeMemberSyncService(campaign=campaign).sync_latest_import()
    _mark_campaign_last_merge(campaign)

    return JsonResponse(
        {
            "campaign_id": campaign.id,
            "member_sync": sync_summary,
            "last_merge": campaign.last_merge.isoformat() if campaign.last_merge else None,
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
    badge_sync_summary = BadgeMemberSyncService(campaign=campaign).sync_latest_import()
    _mark_campaign_last_merge(campaign)

    return JsonResponse(
        {
            "campaign_id": campaign.id,
            "helloasso_member_sync": helloasso_sync_summary,
            "ffck_member_sync": ffck_sync_summary,
            "badge_member_sync": badge_sync_summary,
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
            member_page_path=getattr(settings, "FFCK_EXTRANET_MEMBER_PAGE_PATH", ""),
        )
        extraction = service.extract_excel(download_member_photos=campaign is not None)

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
