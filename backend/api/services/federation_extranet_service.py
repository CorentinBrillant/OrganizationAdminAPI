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
from dataclasses import dataclass
from http.cookiejar import CookieJar


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
        self._opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self._cookie_jar))

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
        code = binary % (10 ** digits)
        return str(code).zfill(digits)

    def extract_excel(self) -> ExtranetExcelExtraction:
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

        filename = _extract_filename(payload.headers.get("Content-Disposition", "")) or "export.xlsx"
        content_type = payload.headers.get(
            "Content-Type",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        if not payload.body:
            raise FederationExtranetExportError("The federation extranet returned an empty export file.")

        return ExtranetExcelExtraction(
            filename=filename,
            content_type=content_type,
            content=payload.body,
            token=token,
        )

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
                raise FederationExtranetAuthError("Token endpoint did not return valid JSON.") from exc

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
            raise FederationExtranetConfigError("Cannot send both form data and raw body in the same request.")
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
            raise FederationExtranetAuthError(f"Federation extranet network error: {exc.reason}") from exc

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
        chunks.append(
            f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode("utf-8")
        )
        chunks.append(val.encode("utf-8"))
        chunks.append(b"\r\n")

    chunks.append(f"--{boundary}--\r\n".encode("utf-8"))
    body = b"".join(chunks)
    return body, f"multipart/form-data; boundary={boundary}"
