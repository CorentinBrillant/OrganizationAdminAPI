import re
from dataclasses import dataclass

from django.db import transaction

from ..models import Campaign, FfckExport, FfckExportRow, HelloAssoImport, HelloAssoItem, Member

URL_RE = re.compile(r"https?://[^\s)]+")


def _pick_first_string(*candidates) -> str:
    for candidate in candidates:
        if isinstance(candidate, str):
            value = candidate.strip()
            if value:
                return value
    return ""


def _nested_get(obj, *keys):
    current = obj
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
        if current is None:
            return None
    return current


def _extract_member_identity(raw_item: dict) -> tuple[str, str, str]:
    first_name = _pick_first_string(
        _nested_get(raw_item, "user", "firstName"),
        _nested_get(raw_item, "payer", "firstName"),
        _nested_get(raw_item, "user", "first_name"),
        _nested_get(raw_item, "payer", "first_name"),
    )
    last_name = _pick_first_string(
        _nested_get(raw_item, "user", "lastName"),
        _nested_get(raw_item, "payer", "lastName"),
        _nested_get(raw_item, "user", "last_name"),
        _nested_get(raw_item, "payer", "last_name"),
    )
    email = _pick_first_string(
        raw_item.get("payerEmail") if isinstance(raw_item, dict) else None,
        _nested_get(raw_item, "user", "email"),
        _nested_get(raw_item, "payer", "email"),
    )

    return first_name, last_name, email.lower()


def _identity_key(first_name: str, last_name: str):
    if not first_name or not last_name:
        return None

    return (first_name.casefold(), last_name.casefold())


def _iter_dict_nodes(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _iter_dict_nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from _iter_dict_nodes(child)


def _extract_urls_from_text(text: str) -> list[str]:
    if not isinstance(text, str) or not text:
        return []
    return [match.strip() for match in URL_RE.findall(text)]


def _pick_node_answer_url(node: dict) -> str:
    # For HelloAsso custom fields, the uploaded document URL is usually in `answer`.
    for key in (
        "answer",
        "file",
        "fileUrl",
        "fileURL",
        "documentUrl",
        "downloadUrl",
        "url",
        "href",
        "value",
    ):
        value = node.get(key)
        if isinstance(value, str):
            extracted = _extract_urls_from_text(value)
            if extracted:
                return extracted[0]
    return ""


def _extract_document_links(raw_item: dict) -> tuple[str, str, str]:
    certificat_url = ""
    autorisation_url = ""
    photo_url = ""

    for node in _iter_dict_nodes(raw_item):
        texts = [
            value.strip()
            for value in node.values()
            if isinstance(value, str) and value.strip()
        ]
        if not texts:
            continue

        lowered = " ".join(texts).casefold()
        answer_url = _pick_node_answer_url(node)

        if not certificat_url and (
            "certificat médical" in lowered or "questionnaire de santé" in lowered
        ):
            if answer_url:
                certificat_url = answer_url

        if not autorisation_url and "autorisation parentale ckcp" in lowered:
            if answer_url:
                autorisation_url = answer_url

        if not photo_url and ("photo d'identité" in lowered or "photo d’identité" in lowered):
            if answer_url:
                photo_url = answer_url

        if certificat_url and autorisation_url and photo_url:
            break

    return certificat_url, autorisation_url, photo_url


@dataclass
class HelloAssoMemberSyncService:
    campaign: Campaign

    @transaction.atomic
    def sync_latest_import(self, import_record: HelloAssoImport | None = None) -> dict:
        latest_import = import_record
        if latest_import is None:
            latest_import = (
                HelloAssoImport.objects.filter(campaign=self.campaign)
                .order_by("-fetched_at")
                .first()
            )

        if latest_import is None:
            return {
                "import_id": None,
                "processed_items": 0,
                "linked_items": 0,
                "created_members": 0,
                "skipped_items": 0,
            }

        members_by_identity = {}
        for member in Member.objects.filter(campaign=self.campaign).order_by("id"):
            key = _identity_key(member.first_name, member.name)
            if key and key not in members_by_identity:
                members_by_identity[key] = member

        processed_items = 0
        linked_items = 0
        created_members = 0
        skipped_items = 0

        items = HelloAssoItem.objects.filter(latest_import=latest_import).order_by("id")

        for helloasso_item in items:
            raw_item = helloasso_item.raw_item
            if not isinstance(raw_item, dict):
                skipped_items += 1
                continue

            first_name, last_name, email = _extract_member_identity(raw_item)
            key = _identity_key(first_name, last_name)
            if key is None:
                skipped_items += 1
                continue

            linked_member = helloasso_item.member
            if linked_member is not None and linked_member.campaign_id == self.campaign.id:
                member = linked_member
                if key not in members_by_identity:
                    members_by_identity[key] = member
            else:
                member = members_by_identity.get(key)
                if member is None:
                    member = Member.objects.create(
                        campaign=self.campaign,
                        first_name=first_name,
                        name=last_name,
                        email=email,
                        ffck_licence="",
                    )
                    members_by_identity[key] = member
                    created_members += 1

            certificat_url, autorisation_url, photo_url = _extract_document_links(raw_item)
            helloasso_item_name = _pick_first_string(raw_item.get("name"))
            member_updates = []
            if certificat_url and member.certificat != certificat_url:
                member.certificat = certificat_url
                member_updates.append("certificat")
            if autorisation_url and member.autorisation_parentale != autorisation_url:
                member.autorisation_parentale = autorisation_url
                member_updates.append("autorisation_parentale")
            if photo_url and member.photo != photo_url:
                member.photo = photo_url
                member_updates.append("photo")
            if helloasso_item_name and member.helloasso_form_slug != helloasso_item_name:
                member.helloasso_form_slug = helloasso_item_name
                member_updates.append("helloasso_form_slug")
            if member_updates:
                member.save(update_fields=member_updates)

            if helloasso_item.member_id != member.id:
                helloasso_item.member = member
                helloasso_item.save(update_fields=["member", "last_synced_at"])

            processed_items += 1
            linked_items += 1

        return {
            "import_id": latest_import.id,
            "processed_items": processed_items,
            "linked_items": linked_items,
            "created_members": created_members,
            "skipped_items": skipped_items,
        }


def _extract_ffck_row_identity(row: FfckExportRow) -> tuple[str, str]:
    raw_row = row.raw_row if isinstance(row.raw_row, dict) else {}
    first_name = _pick_first_string(
        raw_row.get("prenom"),
        raw_row.get("prénom"),
    )
    last_name = _pick_first_string(raw_row.get("nom"))

    # Fallback for legacy rows where `nom` may have been stored as "LAST FIRST".
    if not first_name and not last_name and isinstance(row.nom, str):
        parts = [part for part in row.nom.strip().split() if part]
        if len(parts) >= 2:
            last_name = parts[0]
            first_name = " ".join(parts[1:])
        elif len(parts) == 1:
            last_name = parts[0]

    return first_name, last_name


@dataclass
class FfckMemberSyncService:
    campaign: Campaign

    @transaction.atomic
    def sync_latest_export(self, export_record: FfckExport | None = None) -> dict:
        latest_export = export_record
        if latest_export is None:
            latest_export = (
                FfckExport.objects.filter(campaign=self.campaign)
                .order_by("-fetched_at", "-id")
                .first()
            )

        if latest_export is None:
            return {
                "export_id": None,
                "processed_rows": 0,
                "linked_rows": 0,
                "updated_members": 0,
                "created_members": 0,
                "skipped_rows": 0,
            }

        members_by_identity = {}
        for member in Member.objects.filter(campaign=self.campaign).order_by("id"):
            key = _identity_key(member.first_name, member.name)
            if key and key not in members_by_identity:
                members_by_identity[key] = member

        processed_rows = 0
        linked_rows = 0
        updated_members = 0
        created_members = 0
        skipped_rows = 0

        rows = FfckExportRow.objects.filter(ffck_export=latest_export).order_by("row_index", "id")
        for row in rows:
            first_name, last_name = _extract_ffck_row_identity(row)
            key = _identity_key(first_name, last_name)
            if key is None:
                skipped_rows += 1
                continue

            linked_member = row.member
            if linked_member is not None and linked_member.campaign_id == self.campaign.id:
                member = linked_member
                if key not in members_by_identity:
                    members_by_identity[key] = member
            else:
                member = members_by_identity.get(key)
                if member is None:
                    member = Member.objects.create(
                        campaign=self.campaign,
                        first_name=first_name,
                        name=last_name,
                        email="",
                        ffck_licence="",
                    )
                    members_by_identity[key] = member
                    created_members += 1

            if row.member_id != member.id:
                row.member = member
                row.save(update_fields=["member"])
            linked_rows += 1

            licence = _pick_first_string(row.licence)
            raw_row = row.raw_row if isinstance(row.raw_row, dict) else {}
            ffck_certificat = _pick_first_string(raw_row.get("type certificat"))
            ffck_certificat_expiration = _pick_first_string(
                raw_row.get("date de fin certificat medical"),
                raw_row.get("date de fin certificat médical"),
            )
            ffck_licence_type = _pick_first_string(raw_row.get("type licence"))

            update_fields = []
            if licence and member.ffck_licence != licence:
                member.ffck_licence = licence
                update_fields.append("ffck_licence")
            if member.ffck_certificat != ffck_certificat:
                member.ffck_certificat = ffck_certificat
                update_fields.append("ffck_certificat")
            if member.ffck_certificat_expiration != ffck_certificat_expiration:
                member.ffck_certificat_expiration = ffck_certificat_expiration
                update_fields.append("ffck_certificat_expiration")
            if member.ffck_licence_type != ffck_licence_type:
                member.ffck_licence_type = ffck_licence_type
                update_fields.append("ffck_licence_type")

            if update_fields:
                member.save(update_fields=update_fields)
                updated_members += 1

            processed_rows += 1

        return {
            "export_id": latest_export.id,
            "processed_rows": processed_rows,
            "linked_rows": linked_rows,
            "updated_members": updated_members,
            "created_members": created_members,
            "skipped_rows": skipped_rows,
        }
