import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass


class HelloAssoConfigError(Exception):
    """Raised when required HelloAsso configuration is missing."""


class HelloAssoAPIError(Exception):
    """Raised when HelloAsso API returns an error."""


@dataclass
class HelloAssoService:
    client_id: str
    client_secret: str
    token_url: str = "https://api.helloasso.com/oauth2/token"
    api_base_url: str = "https://api.helloasso.com/v5"

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
        body = urllib.parse.urlencode(
            {
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            }
        ).encode("utf-8")

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
        return token

    def get_form_items(
        self,
        organization_slug: str,
        form_type: str,
        form_slug: str,
        *,
        with_details: bool = True,
    ) -> dict:
        if not organization_slug or not form_type or not form_slug:
            raise HelloAssoConfigError(
                "organization_slug, form_type and form_slug are required."
            )

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
