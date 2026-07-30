import json
import re
import urllib.parse
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from api.services.federation_extranet_service import (
    FederationExtranetAuthError,
    FederationExtranetConfigError,
    FederationExtranetService,
)

AJAX_URL_RE = re.compile(r"['\"]([^'\"]+/licencies/ajax)['\"]", flags=re.IGNORECASE)
FILTER_FORM_RE = re.compile(
    r"<form\b[^>]*\bid=[\"']filtresLicenciesStructure[\"'][^>]*>(.*?)</form>",
    flags=re.IGNORECASE | re.DOTALL,
)
FORM_INPUT_RE = re.compile(
    r"<input\b[^>]*>|<select\b[^>]*>.*?</select>", flags=re.IGNORECASE | re.DOTALL
)
NAME_RE = re.compile(r"\bname=[\"']([^\"']+)[\"']", flags=re.IGNORECASE)
VALUE_RE = re.compile(r"\bvalue=[\"']([^\"']*)[\"']", flags=re.IGNORECASE)
CHECKED_RE = re.compile(r"\bchecked(?:=[\"']?checked[\"']?)?", flags=re.IGNORECASE)
SELECTED_OPTION_RE = re.compile(
    r"<option\b[^>]*\bselected(?:=[\"']?selected[\"']?)?[^>]*>", re.IGNORECASE
)
OPTION_VALUE_RE = re.compile(
    r"\bvalue=[\"']([^\"']*)[\"']",
    flags=re.IGNORECASE,
)
CSRF_TOKEN_RE = re.compile(
    r"<meta[^>]+name=[\"']csrf-token[\"'][^>]+content=[\"']([^\"']+)[\"']",
    flags=re.IGNORECASE,
)
PHOTO_URL_RE = re.compile(
    r"https://extranet\.ffck\.org/storage/photos_personnes/[^\"'\s<>]+",
    flags=re.IGNORECASE,
)
STANDARD_PHOTO_FILENAME_RE = re.compile(r"^\d+_.+\.[A-Za-z0-9]+$")
PAGE_SIZE = 50
DATATABLE_COLUMNS = (
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


class Command(BaseCommand):
    help = "Authenticates with the FFCK extranet and downloads member photos from a page."

    def add_arguments(self, parser):
        parser.add_argument(
            "--page-url",
            default="https://extranet.ffck.org/structures/fiche/2857/licencies",
            help="Authenticated FFCK page containing the member table.",
        )
        parser.add_argument(
            "--output-dir",
            default="media/members/ffck_photos",
            help="Directory where the downloaded photos are saved.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="List photo URLs without downloading files.",
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Print authentication, page retrieval, and scraping diagnostics.",
        )
        parser.add_argument(
            "--save-page",
            action="store_true",
            help="Save the retrieved member page HTML in the output directory.",
        )

    def handle(self, *args, **options):
        service = self._build_service()
        page_url = options["page_url"]
        output_dir = Path(options["output_dir"])
        verbose = options["verbose"]

        try:
            headers, page_html = self._authenticate_and_fetch_page(service, page_url, verbose)
            if options["save_page"]:
                output_dir.mkdir(parents=True, exist_ok=True)
                page_path = output_dir / "ffck_licencies_page.html"
                page_path.write_text(page_html, encoding="utf-8")
                self.stdout.write(f"Saved received page: {page_path}")

            ajax_url = self._extract_ajax_url(page_html, page_url)
            self._log(verbose, f"Fetching member rows from: {ajax_url}")
            csrf_token = self._extract_csrf_token(page_html)
            filters = self._extract_default_filters(page_html)
            self._log(verbose, f"Applying {len(filters)} default member filter(s): {filters}.")
            photos = self._fetch_photos(
                service, ajax_url, headers, csrf_token, filters, verbose
            )
        except (FederationExtranetAuthError, FederationExtranetConfigError) as exc:
            raise CommandError(str(exc)) from exc

        if not photos:
            raise CommandError("No FFCK member photo URLs were found in the AJAX response.")

        if options["dry_run"]:
            self.stdout.write("\n".join(photo_url for photo_url, _ in photos))
            self.stdout.write(self.style.SUCCESS(f"{len(photos)} photo URL(s) found."))
            return

        output_dir.mkdir(parents=True, exist_ok=True)
        downloaded = 0
        for photo_url, licence_number in photos:
            filename = self._photo_filename(photo_url, licence_number)
            destination = output_dir / filename
            if destination.exists():
                self.stdout.write(f"Skipped existing file: {destination}")
                continue

            try:
                photo = service._request(photo_url, method="GET", headers=headers)
            except FederationExtranetAuthError as exc:
                raise CommandError(f"Unable to download {photo_url}: {exc}") from exc

            if not photo.body:
                self.stderr.write(self.style.WARNING(f"Skipped empty response: {photo_url}"))
                continue

            destination.write_bytes(photo.body)
            downloaded += 1
            self.stdout.write(f"Downloaded: {destination}")

        self.stdout.write(self.style.SUCCESS(f"{downloaded} photo(s) downloaded."))

    def _authenticate_and_fetch_page(
        self, service: FederationExtranetService, page_url: str, verbose: bool
    ) -> tuple[dict, str]:
        self._log(verbose, f"Starting login step: {service._as_url(service.login_path)}")
        service._perform_login_step()
        self._log(verbose, f"Starting TOTP step: {service._as_url(service.totp_path)}")
        service._perform_totp_step()
        self._log(verbose, "Selecting FFCK structure.")
        service._select_structure_step()
        self._log(verbose, "Fetching authentication token.")
        token = service._fetch_token()
        self._log(
            verbose,
            f"Authentication completed (token returned: {'yes' if token else 'no'}).",
        )

        headers = {"Referer": service._as_url(service.totp_path)}
        if token:
            token_type = service.token_type.strip()
            headers["Authorization"] = f"{token_type} {token}" if token_type else token

        self._log(verbose, f"Fetching member page: {page_url}")
        page = service._request(page_url, method="GET", headers=headers)
        page_html = page.body.decode("utf-8", errors="ignore")
        self._log(
            verbose,
            "Member page received: "
            f"{len(page.body)} bytes, Content-Type={page.headers.get('Content-Type', 'unknown')}, "
            f"embedded photo URL matches={len(PHOTO_URL_RE.findall(page_html))}.",
        )
        return headers, page_html

    def _fetch_photos(
        self,
        service: FederationExtranetService,
        ajax_url: str,
        headers: dict,
        csrf_token: str,
        filters: dict[str, str],
        verbose: bool,
    ) -> list[tuple[str, str]]:
        start = 0
        total = None
        photos = {}
        while total is None or start < total:
            query_params = self._build_datatable_query(start, filters)
            query_params.update({f"filtres[{name}]": value for name, value in filters.items()})
            query = urllib.parse.urlencode(query_params)
            separator = "&" if "?" in ajax_url else "?"
            payload = service._request(
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
                raise CommandError("FFCK member AJAX endpoint did not return valid JSON.") from exc

            if isinstance(data, list):
                rows = data
                total = len(rows)
            elif isinstance(data, dict):
                rows = data.get("data", [])
                total = data.get("total", data.get("recordsFiltered", len(rows)))
            else:
                raise CommandError("FFCK member AJAX response must be a JSON object or list.")
            if not isinstance(rows, list):
                raise CommandError("FFCK member AJAX response has an invalid 'data' field.")
            try:
                total = int(total)
            except (TypeError, ValueError) as exc:
                raise CommandError("FFCK member AJAX response has an invalid total.") from exc

            page_photos = {
                str(row.get("photo_url", "")).strip(): str(row.get("code_adherent", "")).strip()
                for row in rows
                if isinstance(row, dict)
                and PHOTO_URL_RE.fullmatch(str(row.get("photo_url", "")).strip())
            }
            photos.update(page_photos)
            self._log(
                verbose,
                f"AJAX page {start // PAGE_SIZE + 1}: {len(rows)} row(s), "
                f"{len(page_photos)} photo URL(s), total={total}.",
            )
            if not rows:
                break
            start += len(rows)

        self._log(verbose, f"Found {len(photos)} unique member photo URL(s).")
        return sorted(photos.items())

    @staticmethod
    def _extract_ajax_url(page_html: str, page_url: str) -> str:
        match = AJAX_URL_RE.search(page_html)
        if not match:
            raise CommandError("Could not find the FFCK member AJAX endpoint in the page.")
        return urllib.parse.urljoin(page_url, match.group(1))

    @staticmethod
    def _extract_csrf_token(page_html: str) -> str:
        match = CSRF_TOKEN_RE.search(page_html)
        if not match:
            raise CommandError("Could not find the CSRF token required by the FFCK AJAX endpoint.")
        return match.group(1)

    @staticmethod
    def _extract_default_filters(page_html: str) -> dict[str, str]:
        form_match = FILTER_FORM_RE.search(page_html)
        if not form_match:
            raise CommandError("Could not find the FFCK member filters form.")

        filters = {}
        for element in FORM_INPUT_RE.findall(form_match.group(1)):
            name_match = NAME_RE.search(element)
            if not name_match:
                continue
            name = name_match.group(1)
            if name.endswith("[]"):
                continue
            if element.lower().startswith("<select"):
                selected_match = SELECTED_OPTION_RE.search(element)
                value_match = (
                    OPTION_VALUE_RE.search(selected_match.group(0)) if selected_match else None
                )
            else:
                input_type = re.search(r"\btype=[\"']([^\"']+)[\"']", element, re.IGNORECASE)
                if input_type and input_type.group(1).lower() in {"checkbox", "radio"}:
                    if not CHECKED_RE.search(element):
                        continue
                value_match = VALUE_RE.search(element)
            if value_match:
                filters[name] = value_match.group(1)
        return filters

    @staticmethod
    def _build_datatable_query(start: int, filters: dict[str, str]) -> dict[str, str | int]:
        query_params = {
            "draw": start // PAGE_SIZE + 1,
            "start": start,
            "length": PAGE_SIZE,
            "search[value]": "",
            "search[regex]": "false",
            "order[0][column]": 1,
            "order[0][dir]": "asc",
            "order[1][column]": 0,
            "order[1][dir]": "asc",
        }
        for index, (data, name) in enumerate(DATATABLE_COLUMNS):
            prefix = f"columns[{index}]"
            query_params.update(
                {
                    f"{prefix}[data]": data,
                    f"{prefix}[name]": name,
                    f"{prefix}[searchable]": "true",
                    f"{prefix}[orderable]": "true",
                    f"{prefix}[search][value]": "",
                    f"{prefix}[search][regex]": "false",
                }
            )
        query_params.update({f"filtres[{name}]": value for name, value in filters.items()})
        return query_params

    @staticmethod
    def _photo_filename(photo_url: str, licence_number: str) -> str:
        parsed = urllib.parse.urlparse(photo_url)
        filename = Path(urllib.parse.unquote(parsed.path)).name
        if not filename or filename in {".", ".."}:
            raise CommandError(f"Invalid FFCK photo URL: {photo_url}")
        if STANDARD_PHOTO_FILENAME_RE.fullmatch(filename):
            return filename

        extension = Path(filename).suffix.lower()
        if not licence_number or not licence_number.isdigit() or not extension:
            raise CommandError(
                f"Cannot derive a local filename for {photo_url}: missing valid licence number."
            )
        return f"{licence_number}{extension}"

    def _log(self, enabled: bool, message: str) -> None:
        if enabled:
            self.stdout.write(self.style.NOTICE(f"[FFCK photos] {message}"))

    @staticmethod
    def _build_service() -> FederationExtranetService:
        return FederationExtranetService(
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
            structure_select_path=getattr(settings, "FFCK_EXTRANET_STRUCTURE_SELECT_PATH", ""),
        )
