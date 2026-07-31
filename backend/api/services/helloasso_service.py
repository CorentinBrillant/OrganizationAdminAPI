import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta


class HelloAssoConfigError(Exception):
    """Raised when required HelloAsso configuration is missing."""


class HelloAssoAPIError(Exception):
    """Raised when HelloAsso API returns an error."""


class HelloAssoAuthorizationRequiredError(HelloAssoAPIError):
    """Raised when an uploaded document requires a partner authorization."""


def _is_helloasso_host(hostname: str | None) -> bool:
    hostname = (hostname or "").lower()
    return hostname == "helloasso.com" or hostname.endswith(".helloasso.com")


class _DocumentRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, file_pointer, status_code, message, headers, new_url):
        redirected_request = super().redirect_request(
            request,
            file_pointer,
            status_code,
            message,
            headers,
            new_url,
        )
        if redirected_request is None:
            return None

        destination = urllib.parse.urlparse(new_url)
        if destination.scheme != "https":
            return None
        if not _is_helloasso_host(destination.hostname):
            redirected_request.remove_header("Authorization")
        return redirected_request


@dataclass(frozen=True)
class HelloAssoDocument:
    content: bytes
    content_type: str
    content_disposition: str


@dataclass
class HelloAssoService:
    client_id: str
    client_secret: str
    token_url: str = "https://api.helloasso.com/oauth2/token"
    api_base_url: str = "https://api.helloasso.com/v5"
    default_page_size: int = 100
    access_token: str = ""
    refresh_token: str = ""
    access_token_expires_at: datetime | None = None
    _access_token: str = field(default="", init=False, repr=False)
    _access_token_expires_at: float = field(default=0, init=False, repr=False)

    def _base_headers(self) -> dict:
        user_agent = os.getenv(
            "HELLOASSO_USER_AGENT",
            "OrganizationAdminAPI/1.0 (+https://example.org)",
        ).strip()
        return {
            "Accept": "application/json",
            "User-Agent": user_agent,
        }

    def __post_init__(self) -> None:
        if not self.client_id or not self.client_secret:
            raise HelloAssoConfigError(
                "HELLOASSO_CLIENT_ID and HELLOASSO_CLIENT_SECRET must be configured."
            )

    def _request_json(self, request: urllib.request.Request) -> dict:
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            try:
                payload = json.loads(body)
            except json.JSONDecodeError:
                payload = {"raw": body}

            detail = payload.get("message") or payload.get("error_description") or payload
            raise HelloAssoAPIError(f"HelloAsso HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise HelloAssoAPIError(f"HelloAsso network error: {exc.reason}") from exc

    def get_access_token(self) -> str:
        if self._access_token and time.monotonic() < self._access_token_expires_at:
            return self._access_token

        if self.access_token and self.access_token_expires_at:
            from django.utils import timezone

            if self.access_token_expires_at > timezone.now() + timedelta(seconds=60):
                self._access_token = self.access_token
                self._access_token_expires_at = time.monotonic() + 60
                return self._access_token

        if self.refresh_token:
            return self.refresh_access_token()

        return self._request_access_token(
            {
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            }
        )["access_token"]

    def _request_access_token(self, fields: dict[str, str]) -> dict:
        body = urllib.parse.urlencode(fields).encode("utf-8")

        request = urllib.request.Request(
            self.token_url,
            data=body,
            method="POST",
            headers={
                **self._base_headers(),
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )

        payload = self._request_json(request)
        token = payload.get("access_token")
        if not token:
            raise HelloAssoAPIError("No access_token returned by HelloAsso.")
        try:
            expires_in = int(payload.get("expires_in", 0))
        except (TypeError, ValueError):
            expires_in = 0
        self.access_token = str(token)
        refresh_token = payload.get("refresh_token")
        if refresh_token:
            self.refresh_token = str(refresh_token)
        self._access_token_expires_at = time.monotonic() + max(0, expires_in - 60)
        self._access_token = self.access_token
        from django.utils import timezone

        self.access_token_expires_at = timezone.now() + timedelta(seconds=expires_in)
        return {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "expires_in": expires_in,
            "organization_slug": str(payload.get("organization_slug") or ""),
        }

    def refresh_access_token(self) -> str:
        if not self.refresh_token:
            raise HelloAssoAuthorizationRequiredError("HelloAsso authorization is required.")
        return self._request_access_token(
            {
                "grant_type": "refresh_token",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": self.refresh_token,
            }
        )["access_token"]

    def exchange_authorization_code(
        self, *, code: str, redirect_uri: str, code_verifier: str
    ) -> dict:
        if not code or not redirect_uri or not code_verifier:
            raise HelloAssoConfigError(
                "Authorization code, redirect URI and PKCE verifier are required."
            )
        return self._request_access_token(
            {
                "grant_type": "authorization_code",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "code": code,
                "redirect_uri": redirect_uri,
                "code_verifier": code_verifier,
            }
        )

    def download_document(self, url: str) -> HelloAssoDocument:
        parsed_url = urllib.parse.urlparse(str(url or "").strip())
        hostname = (parsed_url.hostname or "").lower()
        if (
            parsed_url.scheme != "https"
            or not hostname
            or not _is_helloasso_host(hostname)
        ):
            raise HelloAssoAPIError("Document URL must use HTTPS on a HelloAsso domain.")

        token = self.get_access_token()
        request = urllib.request.Request(
            parsed_url.geturl(),
            method="GET",
            headers={
                **self._base_headers(),
                "Accept": "*/*",
                "Authorization": f"Bearer {token}",
            },
        )
        try:
            opener = urllib.request.build_opener(_DocumentRedirectHandler())
            with opener.open(request, timeout=30) as response:
                return HelloAssoDocument(
                    content=response.read(),
                    content_type=response.headers.get_content_type(),
                    content_disposition=response.headers.get("Content-Disposition", ""),
                )
        except urllib.error.HTTPError as exc:
            if exc.code == 403 and hostname == "docs.helloasso.com":
                raise HelloAssoAPIError(
                    "HelloAsso denied access to this uploaded document. "
                    "The API client must have the OrganizationAdmin role."
                ) from exc
            raise HelloAssoAPIError(
                f"HelloAsso HTTP {exc.code} while downloading document."
            ) from exc
        except urllib.error.URLError as exc:
            raise HelloAssoAPIError(f"HelloAsso network error: {exc.reason}") from exc

    def get_form_items(
        self,
        organization_slug: str,
        form_type: str,
        form_slug: str,
        *,
        with_details: bool = True,
    ) -> dict:
        if not organization_slug or not form_type or not form_slug:
            raise HelloAssoConfigError("organization_slug, form_type and form_slug are required.")

        token = self.get_access_token()
        query = urllib.parse.urlencode(
            {
                "withDetails": str(with_details).lower(),
                "pageSize": "100",
            }
        )
        url = (
            f"{self.api_base_url}/organizations/{organization_slug}/forms/"
            f"{form_type}/{form_slug}/items?{query}"
        )

        request = urllib.request.Request(
            url,
            method="GET",
            headers={
                **self._base_headers(),
                "Authorization": f"Bearer {token}",
            },
        )

        return self._request_json(request)

    def get_membership_forms(self, organization_slug: str) -> list[dict]:
        if not organization_slug:
            raise HelloAssoConfigError("organization_slug is required.")

        token = self.get_access_token()
        forms = []
        page_index = 1

        while True:
            query = urllib.parse.urlencode(
                {
                    "formTypes": "Membership",
                    "pageIndex": str(page_index),
                    "pageSize": str(self.default_page_size),
                }
            )
            url = f"{self.api_base_url}/organizations/{organization_slug}/forms?{query}"
            request = urllib.request.Request(
                url,
                method="GET",
                headers={
                    **self._base_headers(),
                    "Authorization": f"Bearer {token}",
                },
            )

            payload = self._request_json(request)
            page_data = payload.get("data") if isinstance(payload, dict) else None
            if not isinstance(page_data, list):
                page_data = []
            forms.extend(page_data)

            pagination = payload.get("pagination") if isinstance(payload, dict) else {}
            if not isinstance(pagination, dict):
                pagination = {}

            page_count = pagination.get("pageCount")
            if isinstance(page_count, int) and page_count > 0:
                if page_index >= page_count:
                    break
                page_index += 1
                continue

            total_pages = pagination.get("totalPages")
            if isinstance(total_pages, int) and total_pages > 0:
                if page_index >= total_pages:
                    break
                page_index += 1
                continue

            has_next_page = pagination.get("hasNextPage")
            if isinstance(has_next_page, bool):
                if not has_next_page:
                    break
                page_index += 1
                continue

            # Fallback when pagination metadata is missing:
            # if we received less than page size, we assume it's the last page.
            if len(page_data) < self.default_page_size:
                break
            page_index += 1

        normalized = []
        for form in forms:
            if not isinstance(form, dict):
                continue
            form_slug = str(form.get("formSlug") or form.get("slug") or "").strip()
            title = str(form.get("title") or "").strip()
            form_type = str(form.get("formType") or "").strip()
            state = str(form.get("state") or "").strip()
            if not form_slug:
                continue
            normalized.append(
                {
                    "form_slug": form_slug,
                    "title": title,
                    "form_type": form_type,
                    "state": state,
                }
            )

        return normalized
