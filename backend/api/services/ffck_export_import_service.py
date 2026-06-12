import hashlib
import io
import re
import unicodedata
import urllib.parse
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass

from django.db import transaction

from ..models import Campaign, FfckExport, FfckExportRow
from .federation_extranet_service import ExtranetExcelExtraction

XLSX_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
OFFICE_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


class FfckExportImportError(Exception):
    """Raised when FFCK Excel import parsing or persistence fails."""


@dataclass
class FfckExportImportService:
    campaign: Campaign

    @transaction.atomic
    def import_extraction(
        self,
        extraction: ExtranetExcelExtraction,
        *,
        structure_select_path: str = "",
        export_path: str = "",
        export_method: str = "POST",
        export_payload: dict | None = None,
        source: str = "licences_excel",
    ) -> dict:
        rows = _read_xlsx_rows(extraction.content)
        if not rows:
            raise FfckExportImportError("FFCK export file contains no worksheet rows.")

        header = [str(v or "").strip() for v in rows[0]]
        data_rows = rows[1:] if len(rows) > 1 else []

        ffck_export = FfckExport.objects.create(
            campaign=self.campaign,
            source=source,
            structure_id=_extract_structure_id(structure_select_path),
            structure_select_path=str(structure_select_path or "").strip(),
            export_path=str(export_path or "").strip(),
            export_method=str(export_method or "POST").strip().upper() or "POST",
            export_payload=export_payload or {},
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

            nom = _pick_first(row_map, ["nom complet"])
            if not nom:
                nom_part = _pick_first(row_map, ["nom"]) 
                prenom_part = _pick_first(row_map, ["prenom", "prénom"])
                nom = " ".join([part for part in [nom_part, prenom_part] if part]).strip()

            categorie = _pick_first(
                row_map,
                [
                    "categorie age sportif",
                    "catégorie age sportif",
                    "categorie age",
                    "catégorie age",
                    "type licence",
                ],
            )
            type_certificat = _pick_first(row_map, ["type certificat"])
            certif_end = _pick_first(
                row_map,
                ["date de fin certificat medical", "date de fin certificat médical"],
            )
            certificat = type_certificat
            if certif_end and type_certificat:
                certificat = f"{type_certificat} ({certif_end})"
            elif certif_end:
                certificat = certif_end

            row_models.append(
                FfckExportRow(
                    ffck_export=ffck_export,
                    row_index=idx,
                    licence=_pick_first(
                        row_map,
                        [
                            "code adherent",
                            "code adhérent",
                            "n licence",
                            "numero licence",
                            "num licence",
                        ],
                    ),
                    nom=nom,
                    categorie=categorie,
                    certificat=certificat,
                    raw_row=row_map,
                )
            )

        if row_models:
            FfckExportRow.objects.bulk_create(row_models, batch_size=500)

        ffck_export.rows_count = len(row_models)
        ffck_export.save(update_fields=["rows_count"])

        return {
            "ffck_export_id": ffck_export.id,
            "campaign_id": self.campaign.id,
            "rows_count": ffck_export.rows_count,
            "filename": ffck_export.filename,
            "fetched_at": ffck_export.fetched_at.isoformat(),
        }


def _extract_structure_id(path_or_url: str) -> int | None:
    path = str(path_or_url or "").strip()
    if not path:
        return None

    parsed = urllib.parse.urlparse(path)
    raw_path = parsed.path if parsed.scheme and parsed.netloc else path
    match = re.search(r"/select-structure/(\d+)", raw_path)
    if not match:
        return None

    try:
        return int(match.group(1))
    except ValueError:
        return None


def _row_to_dict(header: list[str], cells: list[str]) -> dict:
    size = max(len(header), len(cells))
    data = {}
    for i in range(size):
        key = header[i] if i < len(header) else f"col_{i+1}"
        normalized = _normalize_header(key) or f"col_{i+1}"
        value = cells[i] if i < len(cells) else ""
        data[normalized] = "" if value is None else str(value).strip()
    return data


def _normalize_header(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _pick_first(row: dict, candidates: list[str]) -> str:
    for candidate in candidates:
        normalized = _normalize_header(candidate)
        value = row.get(normalized, "")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _read_xlsx_rows(content: bytes) -> list[list[str]]:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            shared_strings = _read_shared_strings(zf)
            worksheet_path = _first_worksheet_path(zf)
            if not worksheet_path:
                return []
            return _read_worksheet_rows(zf.read(worksheet_path), shared_strings)
    except zipfile.BadZipFile as exc:
        raise FfckExportImportError("File is not a valid XLSX archive.") from exc


def _read_shared_strings(zf: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in zf.namelist():
        return []

    root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    strings = []
    for si in root.findall(f"{{{XLSX_NS}}}si"):
        texts = si.findall(f".//{{{XLSX_NS}}}t")
        strings.append("".join((node.text or "") for node in texts))
    return strings


def _first_worksheet_path(zf: zipfile.ZipFile) -> str:
    workbook_xml = ET.fromstring(zf.read("xl/workbook.xml"))
    sheets = workbook_xml.find(f"{{{XLSX_NS}}}sheets")
    if sheets is None or len(list(sheets)) == 0:
        return ""

    first_sheet = list(sheets)[0]
    rel_id = first_sheet.attrib.get(f"{{{OFFICE_REL_NS}}}id", "")
    if not rel_id:
        return ""

    rels_xml = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
    for rel in rels_xml.findall(f"{{{REL_NS}}}Relationship"):
        if rel.attrib.get("Id") != rel_id:
            continue
        target = rel.attrib.get("Target", "").lstrip("/")
        if not target:
            return ""
        return target if target.startswith("xl/") else f"xl/{target}"

    return ""


def _read_worksheet_rows(xml_bytes: bytes, shared_strings: list[str]) -> list[list[str]]:
    root = ET.fromstring(xml_bytes)
    sheet_data = root.find(f"{{{XLSX_NS}}}sheetData")
    if sheet_data is None:
        return []

    rows = []
    for row in sheet_data.findall(f"{{{XLSX_NS}}}row"):
        cells = {}
        max_col = 0
        for cell in row.findall(f"{{{XLSX_NS}}}c"):
            ref = cell.attrib.get("r", "")
            col_index = _column_index_from_ref(ref)
            if col_index <= 0:
                continue

            value = _cell_value(cell, shared_strings)
            cells[col_index] = value
            if col_index > max_col:
                max_col = col_index

        if max_col <= 0:
            continue
        rows.append([cells.get(i, "") for i in range(1, max_col + 1)])

    return rows


def _cell_value(cell: ET.Element, shared_strings: list[str]) -> str:
    cell_type = cell.attrib.get("t", "")
    if cell_type == "inlineStr":
        inline = cell.find(f"{{{XLSX_NS}}}is")
        if inline is None:
            return ""
        texts = inline.findall(f".//{{{XLSX_NS}}}t")
        return "".join((node.text or "") for node in texts).strip()

    raw = cell.find(f"{{{XLSX_NS}}}v")
    if raw is None:
        return ""
    raw_text = (raw.text or "").strip()

    if cell_type == "s":
        try:
            idx = int(raw_text)
        except ValueError:
            return ""
        return shared_strings[idx].strip() if 0 <= idx < len(shared_strings) else ""

    if cell_type == "b":
        return "Oui" if raw_text == "1" else "Non"

    return raw_text


def _column_index_from_ref(ref: str) -> int:
    letters = "".join(ch for ch in str(ref or "") if ch.isalpha()).upper()
    if not letters:
        return 0
    index = 0
    for char in letters:
        index = index * 26 + (ord(char) - ord("A") + 1)
    return index
