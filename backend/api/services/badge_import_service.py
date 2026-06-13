import hashlib
import re
import unicodedata
from dataclasses import dataclass

from django.db import transaction

from ..models import BadgeImport, BadgeImportRow, Campaign
from .ffck_export_import_service import FfckExportImportError, _read_xlsx_rows


class BadgeImportError(Exception):
    """Raised when badge Excel import parsing or persistence fails."""


def _normalize_header(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _row_to_dict(header: list[str], cells: list[str]) -> dict:
    size = max(len(header), len(cells))
    data = {}
    for i in range(size):
        key = header[i] if i < len(header) else f"col_{i + 1}"
        normalized = _normalize_header(key) or f"col_{i + 1}"
        value = cells[i] if i < len(cells) else ""
        data[normalized] = "" if value is None else str(value).strip()
    return data


def _pick_first(row: dict, candidates: list[str]) -> str:
    for candidate in candidates:
        value = row.get(_normalize_header(candidate), "")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _to_bool(value) -> bool:
    if isinstance(value, bool):
        return value

    text = str(value or "").strip().lower()
    if not text:
        return False

    return text in {
        "1",
        "true",
        "yes",
        "oui",
        "ok",
        "x",
        "v",
        "checked",
        "commande",
        "commandee",
        "commandé",
        "commandée",
        "possede",
        "possedee",
        "possédé",
        "possédée",
    }


@dataclass(frozen=True)
class BadgeExcelExtraction:
    filename: str
    content_type: str
    content: bytes


@dataclass
class BadgeImportService:
    campaign: Campaign

    @transaction.atomic
    def import_extraction(
        self,
        extraction: BadgeExcelExtraction,
        *,
        source: str = "badge_excel",
    ) -> dict:
        try:
            rows = _read_xlsx_rows(extraction.content)
        except FfckExportImportError as exc:
            raise BadgeImportError(str(exc)) from exc

        if not rows:
            raise BadgeImportError("Badge file contains no worksheet rows.")

        header = [str(v or "").strip() for v in rows[0]]
        data_rows = rows[1:] if len(rows) > 1 else []

        badge_import = BadgeImport.objects.create(
            campaign=self.campaign,
            source=source,
            rows_count=0,
            filename=str(extraction.filename or "").strip(),
            content_type=str(extraction.content_type or "").strip(),
            file_size=len(extraction.content),
            file_sha256=hashlib.sha256(extraction.content).hexdigest(),
            file_blob=extraction.content,
        )

        row_models = []
        for idx, cells in enumerate(data_rows, start=1):
            row_map = _row_to_dict(header, cells)
            if not any(str(v).strip() for v in row_map.values()):
                continue

            licence = _pick_first(
                row_map,
                ["licence", "n licence", "numero licence", "num licence", "code adherent"],
            )
            first_name = _pick_first(row_map, ["prenom", "prénom", "first name", "firstname"])
            name = _pick_first(row_map, ["nom", "last name", "lastname"])
            raw_status = _pick_first(
                row_map,
                ["statut badge", "badge statut", "badge status", "etat badge", "status badge"],
            ).lower()

            badge_owned = _to_bool(
                _pick_first(
                    row_map,
                    ["badge possede", "badge possédé", "possede", "possédé", "a un badge"],
                )
            )
            badge_ordered = _to_bool(
                _pick_first(
                    row_map,
                    [
                        "badge commande",
                        "badge commandé",
                        "commande badge",
                        "commandé",
                        "commande",
                    ],
                )
            )

            if "possed" in raw_status or "posséd" in raw_status:
                badge_owned = True
            if "command" in raw_status:
                badge_ordered = True

            # Fallback: if row is listed but no explicit status, keep a positive marker.
            if not badge_owned and not badge_ordered:
                badge_ordered = True

            row_models.append(
                BadgeImportRow(
                    badge_import=badge_import,
                    row_index=idx,
                    licence=licence,
                    first_name=first_name,
                    name=name,
                    badge_owned=badge_owned,
                    badge_ordered=badge_ordered,
                    raw_row=row_map,
                )
            )

        if row_models:
            BadgeImportRow.objects.bulk_create(row_models, batch_size=500)

        badge_import.rows_count = len(row_models)
        badge_import.save(update_fields=["rows_count"])

        return {
            "badge_import_id": badge_import.id,
            "campaign_id": self.campaign.id,
            "rows_count": badge_import.rows_count,
            "filename": badge_import.filename,
            "fetched_at": badge_import.fetched_at.isoformat(),
        }
