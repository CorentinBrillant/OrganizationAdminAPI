import base64
import hashlib
import hmac
import html
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from http.cookiejar import CookieJar
from pathlib import Path

from cryptography.fernet import Fernet
from django.conf import settings


class FederationExtranetConfigError(Exception):
    """Raised when required federation extranet settings are missing or invalid."""


class FederationExtranetAuthError(Exception):
    """Raised when authentication to the federation extranet fails."""


class FederationExtranetExportError(Exception):
    """Raised when Excel export retrieval fails."""


@dataclass(frozen=True)
class ExtranetExcelExtraction:
    filename: str
    content_type: str
    content: bytes
    token: str
    photo_paths: dict[str, str] | None = None
    photo_original_names: dict[str, str] | None = None


@dataclass(frozen=True)
class _HTTPPayload:
    headers: dict
    body: bytes


HIDDEN_INPUT_RE = re.compile(
    r"<input[^>]*type=[\"']hidden[\"'][^>]*>",
    flags=re.IGNORECASE,
)
NAME_ATTR_RE = re.compile(r"name=[\"']([^\"']+)[\"']", flags=re.IGNORECASE)
VALUE_ATTR_RE = re.compile(r"value=[\"']([^\"']*)[\"']", flags=re.IGNORECASE)
AJAX_URL_RE = re.compile(r"['\"]([^'\"]+/licencies/ajax)['\"]", flags=re.IGNORECASE)
CSRF_TOKEN_RE = re.compile(
    r"<meta[^>]+name=[\"']csrf-token[\"'][^>]+content=[\"']([^\"']+)[\"']",
    flags=re.IGNORECASE,
)
FILTER_FORM_RE = re.compile(
    r"<form\b[^>]*\bid=[\"']filtresLicenciesStructure[\"'][^>]*>(.*?)</form>",
    flags=re.IGNORECASE | re.DOTALL,
)
FORM_INPUT_RE = re.compile(
    r"<input\b[^>]*>|<select\b[^>]*>.*?</select>", flags=re.IGNORECASE | re.DOTALL
)
SELECTED_OPTION_RE = re.compile(
    r"<option\b[^>]*\bselected(?:=[\"']?selected[\"']?)?[^>]*>", re.IGNORECASE
)
CHECKED_RE = re.compile(r"\bchecked(?:=[\"']?checked[\"']?)?", flags=re.IGNORECASE)
PHOTO_URL_RE = re.compile(
    r"https://extranet\.ffck\.org/storage/photos_personnes/[^\"'\s<>]+",
    flags=re.IGNORECASE,
)
STANDARD_PHOTO_FILENAME_RE = re.compile(r"^\d+_.+\.[A-Za-z0-9]+$")
PHOTO_PAGE_SIZE = 50
PHOTO_UPLOAD_DIRECTORY = "members/ffck_photos"
PHOTO_DATATABLE_COLUMNS = (
    ("code_adherent", "personnes.code_adherent"),
    ("nom", "personnes.nom"),
    ("prenom", "personnes.prenom"),
    ("sexe", "personnes.sexe"),
    ("ddn", "personnes.ddn"),
    ("photo", ""),
    ("etat", "licences.etat"),
    ("date_demande", "licences.date_demande"),
    ("date_debut_validite", "licences.date_debut_validite"),
    ("date_fin", "licences.date_fin"),
    ("saisie_par", "licences.saisie_par"),
    ("ia", "licences.no_ia"),
    ("type_libelle", "licences_types.libelle"),
    ("discipline", "licences_types.libelle"),
    ("categorie_age", "licences_types.libelle"),
    ("mutation", "licences_types.libelle"),
    ("surclassement", "licences_types.libelle"),
    ("mail", "adresses.mail"),
    ("telephone", "adresses.tel"),
    ("adresse", "adresses.num_voie"),
    ("code_postal", "adresses.code_postal_fr"),
    ("commune", "adresses.commune"),
    ("representant_legal_1", "licences.date_demande"),
    ("representant_legal_2", "licences.date_demande"),
)


@dataclass
class FederationExtranetService:
    base_url: str
    login_path: str
    totp_path: str
    export_path: str
    username: str
    password: str
    totp_secret: str
    token_path: str = ""
    token_field: str = "access_token"
    token_cookie_name: str = ""
    username_field: str = "username"
    password_field: str = "password"
    totp_field: str = "code"
    token_type: str = "Bearer"
    login_extra_payload: str = ""
    totp_extra_payload: str = ""
    export_method: str = "POST"
    export_form_path: str = ""
    export_extra_payload: str = ""
    structure_select_path: str = ""
    member_page_path: str = ""

    def __post_init__(self) -> None:
        required_fields = {
            "base_url": self.base_url,
            "login_path": self.login_path,
            "totp_path": self.totp_path,
            "export_path": self.export_path,
            "username": self.username,
            "password": self.password,
            "totp_secret": self.totp_secret,
        }

        missing = [name for name, value in required_fields.items() if not str(value).strip()]
        if missing:
            raise FederationExtranetConfigError(
                "Missing federation extranet settings: " + ", ".join(sorted(missing))
            )

        self._cookie_jar = CookieJar()
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self._cookie_jar)
        )

    @staticmethod
    def generate_totp(
        secret: str,
        *,
        digits: int = 6,
        period: int = 30,
        for_time: int | None = None,
    ) -> str:
        normalized = re.sub(r"\s+", "", str(secret or "")).upper()
        if not normalized:
            raise FederationExtranetConfigError("TOTP secret is empty.")

        padded = normalized + "=" * ((8 - (len(normalized) % 8)) % 8)
        try:
            key = base64.b32decode(padded, casefold=True)
        except Exception as exc:  # pragma: no cover - defensive for malformed secrets
            raise FederationExtranetConfigError("TOTP secret is not valid base32.") from exc

        timestamp = int(time.time() if for_time is None else for_time)
        counter = timestamp // period
        msg = counter.to_bytes(8, "big")
        digest = hmac.new(key, msg, hashlib.sha1).digest()
        offset = digest[-1] & 0x0F
        binary = int.from_bytes(digest[offset : offset + 4], "big") & 0x7FFFFFFF
        code = binary % (10**digits)
        return str(code).zfill(digits)

    def extract_excel(self, *, download_member_photos: bool = False) -> ExtranetExcelExtraction:
        self._perform_login_step()
        self._perform_totp_step()
        self._select_structure_step()

        token = self._fetch_token()
        common_headers = {}
        if token:
            token_type = self.token_type.strip()
            common_headers["Authorization"] = f"{token_type} {token}" if token_type else token

        export_page_path = self.export_form_path or _parent_path(self.export_path)
        export_page_url = self._as_url(export_page_path)
        export_page = self._request(
            export_page_url,
            method="GET",
            headers={
                **common_headers,
                "Referer": self._as_url(self.totp_path),
            },
        )

        export_fields = _extract_hidden_fields(export_page.body)
        export_fields.update(_parse_extra_payload(self.export_extra_payload, context="export"))

        xsrf_cookie = self._get_cookie("XSRF-TOKEN")
        export_headers = {
            **common_headers,
            "Referer": export_page_url,
        }
        if xsrf_cookie:
            export_headers["X-XSRF-TOKEN"] = urllib.parse.unquote(xsrf_cookie)

        export_url = self._as_url(self.export_path)
        export_method = (self.export_method or "POST").strip().upper()

        if export_method == "GET":
            payload = self._request(export_url, method="GET", headers=export_headers)
        elif export_method == "POST":
            body, content_type = _encode_multipart_formdata(export_fields)
            payload = self._request(
                export_url,
                method="POST",
                raw_body=body,
                headers={
                    **export_headers,
                    "Content-Type": content_type,
                },
            )
        else:
            raise FederationExtranetConfigError(
                f"Unsupported FFCK_EXTRANET_EXPORT_METHOD '{export_method}'. Use GET or POST."
            )

        filename = (
            _extract_filename(payload.headers.get("Content-Disposition", "")) or "export.xlsx"
        )
        content_type = payload.headers.get(
            "Content-Type",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        if not payload.body:
            raise FederationExtranetExportError(
                "The federation extranet returned an empty export file."
            )

        photo_paths, photo_original_names = (
            self.download_member_photos(common_headers) if download_member_photos else ({}, {})
        )

        return ExtranetExcelExtraction(
            filename=filename,
            content_type=content_type,
            content=payload.body,
            token=token,
            photo_paths=photo_paths,
            photo_original_names=photo_original_names,
        )

    def download_member_photos(
        self, headers: dict[str, str]
    ) -> tuple[dict[str, str], dict[str, str]]:
        """Downloads FFCK member photos once and returns their paths keyed by licence."""
        page_url = self._member_page_url()
        page = self._request(
            page_url,
            method="GET",
            headers={**headers, "Referer": self._as_url(self.totp_path)},
        )
        page_html = page.body.decode("utf-8", errors="ignore")
        ajax_url = self._extract_photo_ajax_url(page_html, page_url)
        csrf_token = self._extract_photo_csrf_token(page_html)
        photos = self._fetch_member_photos(
            ajax_url, headers, csrf_token, self._extract_member_filters(page_html)
        )
        output_dir = Path(settings.MEDIA_ROOT) / PHOTO_UPLOAD_DIRECTORY
        output_dir.mkdir(parents=True, exist_ok=True)

        photo_paths = {}
        photo_original_names = {}
        existing_photos = self._existing_photo_paths_by_licence()
        for licence, photo_url in photos.items():
            existing_photo = existing_photos.get(licence)
            if existing_photo:
                photo_paths[licence], photo_original_names[licence] = existing_photo
                continue

            original_name = self._photo_filename(photo_url, licence)
            photo = self._request(photo_url, method="GET", headers=headers)
            if not photo.body:
                continue
            stored_name = f"{uuid.uuid4().hex}.enc"
            destination = output_dir / stored_name
            destination.write_bytes(self._encrypt_photo(photo.body))
            photo_paths[licence] = f"{PHOTO_UPLOAD_DIRECTORY}/{stored_name}"
            photo_original_names[licence] = original_name

        return photo_paths, photo_original_names

    @staticmethod
    def _encrypt_photo(content: bytes) -> bytes:
        key = str(getattr(settings, "MEMBER_CERTIFICAT_ENCRYPTION_KEY", "")).strip()
        if not key:
            raise FederationExtranetConfigError(
                "MEMBER_CERTIFICAT_ENCRYPTION_KEY must be configured."
            )
        try:
            return Fernet(key.encode("utf-8")).encrypt(content)
        except Exception as exc:
            raise FederationExtranetConfigError(
                "MEMBER_CERTIFICAT_ENCRYPTION_KEY is invalid. Expected a URL-safe base64 key."
            ) from exc

    @classmethod
    def _existing_photo_paths_by_licence(cls) -> dict[str, tuple[str, str]]:
        from ..models import FfckExportRow

        photos = {}
        for row in FfckExportRow.objects.exclude(photo="").only(
            "licence", "photo", "photo_original_name"
        ):
            licence = str(row.licence or "").strip()
            photo_path = str(row.photo.name or "").strip()
            if licence and photo_path and row.photo.storage.exists(photo_path):
                original_name = str(row.photo_original_name or Path(photo_path).name).strip()
                if not photo_path.endswith(".enc"):
                    encrypted_path = f"{PHOTO_UPLOAD_DIRECTORY}/{uuid.uuid4().hex}.enc"
                    with row.photo.storage.open(photo_path, "rb") as source:
                        encrypted_content = cls._encrypt_photo(source.read())
                    with row.photo.storage.open(encrypted_path, "wb") as destination:
                        destination.write(encrypted_content)
                    row.photo.name = encrypted_path
                    row.photo_original_name = original_name
                    row.save(update_fields=["photo", "photo_original_name"])
                    row.photo.storage.delete(photo_path)
                    photo_path = encrypted_path
                photos.setdefault(licence, (photo_path, original_name))
        return photos

    def _member_page_url(self) -> str:
        configured = str(self.member_page_path or "").strip()
        if configured:
            return self._as_url(configured)

        match = re.search(r"/select-structure/(\d+)", str(self.structure_select_path or ""))
        if not match:
            raise FederationExtranetConfigError(
                "FFCK member photo page requires FFCK_EXTRANET_MEMBER_PAGE_PATH "
                "or a structure selection path."
            )
        return self._as_url(f"/structures/fiche/{match.group(1)}/licencies")

    def _fetch_member_photos(
        self, ajax_url: str, headers: dict[str, str], csrf_token: str, filters: dict[str, str]
    ) -> dict[str, str]:
        start = 0
        total = None
        photos = {}
        while total is None or start < total:
            query_params = self._photo_datatable_query(start)
            query_params.update({f"filtres[{name}]": value for name, value in filters.items()})
            query = urllib.parse.urlencode(query_params)
            separator = "&" if "?" in ajax_url else "?"
            payload = self._request(
                f"{ajax_url}{separator}{query}",
                method="GET",
                headers={
                    **headers,
                    "Accept": "application/json",
                    "Referer": ajax_url,
                    "X-CSRF-TOKEN": csrf_token,
                    "X-Requested-With": "XMLHttpRequest",
                },
            )
            try:
                data = json.loads(payload.body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise FederationExtranetExportError(
                    "FFCK member photo endpoint did not return valid JSON."
                ) from exc

            if isinstance(data, list):
                rows, total = data, len(data)
            elif isinstance(data, dict):
                rows = data.get("data", [])
                total = data.get("total", data.get("recordsFiltered", len(rows)))
            else:
                raise FederationExtranetExportError(
                    "FFCK member photo response has an invalid format."
                )
            if not isinstance(rows, list):
                raise FederationExtranetExportError(
                    "FFCK member photo response has an invalid data field."
                )
            try:
                total = int(total)
            except (TypeError, ValueError) as exc:
                raise FederationExtranetExportError(
                    "FFCK member photo response has an invalid total."
                ) from exc

            for row in rows:
                if not isinstance(row, dict):
                    continue
                licence = str(row.get("code_adherent", "")).strip()
                photo_url = str(row.get("photo_url", "")).strip()
                if licence and PHOTO_URL_RE.fullmatch(photo_url):
                    photos[licence] = photo_url
            if not rows:
                break
            start += len(rows)
        return photos

    @staticmethod
    def _extract_photo_ajax_url(page_html: str, page_url: str) -> str:
        match = AJAX_URL_RE.search(page_html)
        if not match:
            raise FederationExtranetExportError("Could not find the FFCK member photo endpoint.")
        return urllib.parse.urljoin(page_url, match.group(1))

    @staticmethod
    def _extract_photo_csrf_token(page_html: str) -> str:
        match = CSRF_TOKEN_RE.search(page_html)
        if not match:
            raise FederationExtranetExportError("Could not find the FFCK member photo CSRF token.")
        return match.group(1)

    @staticmethod
    def _extract_member_filters(page_html: str) -> dict[str, str]:
        form_match = FILTER_FORM_RE.search(page_html)
        if not form_match:
            raise FederationExtranetExportError("Could not find the FFCK member filters form.")

        filters = {}
        for element in FORM_INPUT_RE.findall(form_match.group(1)):
            name_match = NAME_ATTR_RE.search(element)
            if not name_match:
                continue
            name = name_match.group(1)
            if name.endswith("[]"):
                continue
            if element.lower().startswith("<select"):
                selected_match = SELECTED_OPTION_RE.search(element)
                value_match = (
                    VALUE_ATTR_RE.search(selected_match.group(0)) if selected_match else None
                )
            else:
                input_type = re.search(r"\btype=[\"']([^\"']+)[\"']", element, re.IGNORECASE)
                if input_type and input_type.group(1).lower() in {"checkbox", "radio"}:
                    if not CHECKED_RE.search(element):
                        continue
                value_match = VALUE_ATTR_RE.search(element)
            if value_match:
                filters[name] = value_match.group(1)
        return filters

    @staticmethod
    def _photo_datatable_query(start: int) -> dict[str, str | int]:
        query = {
            "draw": start // PHOTO_PAGE_SIZE + 1,
            "start": start,
            "length": PHOTO_PAGE_SIZE,
            "search[value]": "",
            "search[regex]": "false",
            "order[0][column]": 1,
            "order[0][dir]": "asc",
            "order[1][column]": 0,
            "order[1][dir]": "asc",
        }
        for index, (data, name) in enumerate(PHOTO_DATATABLE_COLUMNS):
            prefix = f"columns[{index}]"
            query.update(
                {
                    f"{prefix}[data]": data,
                    f"{prefix}[name]": name,
                    f"{prefix}[searchable]": "true",
                    f"{prefix}[orderable]": "true",
                    f"{prefix}[search][value]": "",
                    f"{prefix}[search][regex]": "false",
                }
            )
        return query

    @staticmethod
    def _photo_filename(photo_url: str, licence: str) -> str:
        filename = Path(urllib.parse.unquote(urllib.parse.urlparse(photo_url).path)).name
        if STANDARD_PHOTO_FILENAME_RE.fullmatch(filename):
            return filename
        extension = Path(filename).suffix.lower()
        if not licence.isdigit() or not extension:
            raise FederationExtranetExportError(
                f"Cannot derive a local filename for FFCK photo {photo_url}."
            )
        return f"{licence}{extension}"

    def _perform_login_step(self) -> None:
        login_url = self._as_url(self.login_path)
        page = self._request(login_url, method="GET")

        fields = _extract_hidden_fields(page.body)
        fields[self.username_field] = self.username
        fields[self.password_field] = self.password
        fields.update(_parse_extra_payload(self.login_extra_payload, context="login"))

        self._request(
            login_url,
            method="POST",
            data=fields,
            headers={"Referer": login_url},
        )

    def _perform_totp_step(self) -> None:
        totp_url = self._as_url(self.totp_path)
        page = self._request(totp_url, method="GET")

        fields = _extract_hidden_fields(page.body)
        fields[self.totp_field] = self.generate_totp(self.totp_secret)
        fields.update(_parse_extra_payload(self.totp_extra_payload, context="totp"))

        self._request(
            totp_url,
            method="POST",
            data=fields,
            headers={"Referer": totp_url},
        )

    def _select_structure_step(self) -> None:
        path = str(self.structure_select_path or "").strip()
        if not path:
            return

        select_url = self._as_url(path)
        self._request(
            select_url,
            method="GET",
            headers={"Referer": self._as_url(self.totp_path)},
        )

    def _fetch_token(self) -> str:
        if self.token_path:
            token_url = self._as_url(self.token_path)
            payload = self._request(token_url, method="GET", headers={"Accept": "application/json"})
            try:
                data = json.loads(payload.body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise FederationExtranetAuthError(
                    "Token endpoint did not return valid JSON."
                ) from exc

            token = _extract_string(data, self.token_field)
            if token:
                return token

            raise FederationExtranetAuthError(
                f"Token endpoint response does not contain '{self.token_field}'."
            )

        if self.token_cookie_name:
            for cookie in self._cookie_jar:
                if cookie.name == self.token_cookie_name:
                    value = (cookie.value or "").strip()
                    if value:
                        return value

            raise FederationExtranetAuthError(
                f"No '{self.token_cookie_name}' cookie found after authentication."
            )

        return ""

    def _request(
        self,
        url: str,
        *,
        method: str,
        data: dict | None = None,
        raw_body: bytes | None = None,
        headers: dict | None = None,
    ) -> _HTTPPayload:
        request_headers = {
            "Accept": "*/*",
            "User-Agent": os.getenv(
                "FFCK_EXTRANET_USER_AGENT",
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            ).strip(),
        }
        if headers:
            request_headers.update(headers)

        encoded_data = None
        if data is not None and raw_body is not None:
            raise FederationExtranetConfigError(
                "Cannot send both form data and raw body in the same request."
            )
        if data is not None:
            encoded_data = urllib.parse.urlencode(data).encode("utf-8")
            request_headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
        elif raw_body is not None:
            encoded_data = raw_body

        req = urllib.request.Request(
            url,
            data=encoded_data,
            method=method,
            headers=request_headers,
        )

        try:
            with self._opener.open(req, timeout=30) as response:
                return _HTTPPayload(
                    headers=dict(response.headers.items()),
                    body=response.read(),
                )
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise FederationExtranetAuthError(
                f"Federation extranet HTTP {exc.code}: {body[:500]}"
            ) from exc
        except urllib.error.URLError as exc:
            raise FederationExtranetAuthError(
                f"Federation extranet network error: {exc.reason}"
            ) from exc

    def _as_url(self, path_or_url: str) -> str:
        candidate = str(path_or_url or "").strip()
        if not candidate:
            raise FederationExtranetConfigError("A required federation extranet URL is empty.")
        if candidate.startswith("http://") or candidate.startswith("https://"):
            return candidate

        base = self.base_url.rstrip("/")
        path = candidate if candidate.startswith("/") else f"/{candidate}"
        return f"{base}{path}"

    def _get_cookie(self, name: str) -> str:
        for cookie in self._cookie_jar:
            if cookie.name == name:
                return (cookie.value or "").strip()
        return ""


def _parse_extra_payload(raw: str, *, context: str) -> dict:
    value = str(raw or "").strip()
    if not value:
        return {}

    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise FederationExtranetConfigError(
            f"FFCK_EXTRANET_{context.upper()}_EXTRA_PAYLOAD must be a valid JSON object."
        ) from exc

    if not isinstance(parsed, dict):
        raise FederationExtranetConfigError(
            f"FFCK_EXTRANET_{context.upper()}_EXTRA_PAYLOAD must be a JSON object."
        )

    normalized = {}
    for key, candidate in parsed.items():
        normalized[str(key)] = "" if candidate is None else str(candidate)

    return normalized


def _extract_hidden_fields(body: bytes) -> dict:
    try:
        html_text = body.decode("utf-8", errors="ignore")
    except Exception:  # pragma: no cover - defensive fallback
        return {}

    fields = {}
    for tag in HIDDEN_INPUT_RE.findall(html_text):
        name_match = NAME_ATTR_RE.search(tag)
        if not name_match:
            continue
        value_match = VALUE_ATTR_RE.search(tag)
        name = html.unescape(name_match.group(1).strip())
        value = html.unescape(value_match.group(1).strip()) if value_match else ""
        if name:
            fields[name] = value

    return fields


def _extract_string(payload: dict, dotted_key: str) -> str:
    if not isinstance(payload, dict):
        return ""

    current = payload
    for segment in str(dotted_key or "").split("."):
        segment = segment.strip()
        if not segment:
            continue
        if not isinstance(current, dict):
            return ""
        current = current.get(segment)
        if current is None:
            return ""

    return current.strip() if isinstance(current, str) else ""


def _extract_filename(content_disposition: str) -> str:
    raw = str(content_disposition or "")
    if not raw:
        return ""

    match = re.search(r"filename\*=UTF-8''([^;]+)", raw, flags=re.IGNORECASE)
    if match:
        return urllib.parse.unquote(match.group(1).strip())

    match = re.search(r'filename="?([^";]+)"?', raw, flags=re.IGNORECASE)
    if match:
        return match.group(1).strip()

    return ""


def _parent_path(path_or_url: str) -> str:
    path = str(path_or_url or "").strip()
    if not path:
        return "/"

    parsed = urllib.parse.urlparse(path)
    raw_path = parsed.path if parsed.scheme and parsed.netloc else path
    if not raw_path.startswith("/"):
        raw_path = f"/{raw_path}"

    parts = [segment for segment in raw_path.split("/") if segment]
    if len(parts) <= 1:
        return "/"

    return "/" + "/".join(parts[:-1])


def _encode_multipart_formdata(fields: dict[str, str]) -> tuple[bytes, str]:
    boundary = f"----CodexBoundary{os.urandom(12).hex()}"
    chunks: list[bytes] = []

    for name, value in fields.items():
        key = str(name)
        val = "" if value is None else str(value)
        chunks.append(f"--{boundary}\r\n".encode("utf-8"))
        chunks.append(f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode("utf-8"))
        chunks.append(val.encode("utf-8"))
        chunks.append(b"\r\n")

    chunks.append(f"--{boundary}--\r\n".encode("utf-8"))
    body = b"".join(chunks)
    return body, f"multipart/form-data; boundary={boundary}"
