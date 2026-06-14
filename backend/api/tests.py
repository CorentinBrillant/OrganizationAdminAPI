import json
import os
import time
import urllib.parse
import zipfile
from io import BytesIO
from pathlib import Path
from unittest import skipUnless
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile

from django.test import TestCase, override_settings

from .auth import create_user_token
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
)
from .services.federation_extranet_service import ExtranetExcelExtraction, FederationExtranetService
from .services.badge_import_service import BadgeExcelExtraction, BadgeImportService
from .services.ffck_export_import_service import FfckExportImportService
from .services.helloasso_service import HelloAssoService
from .services.member_sync_service import (
    BadgeMemberSyncService,
    FfckMemberSyncService,
    HelloAssoMemberSyncService,
)


def build_test_xlsx(rows: list[list[str]]) -> bytes:
    escaped_rows = []
    for row_index, row in enumerate(rows, start=1):
        cells = []
        for col_index, value in enumerate(row, start=1):
            column = ""
            idx = col_index
            while idx > 0:
                idx, rem = divmod(idx - 1, 26)
                column = chr(65 + rem) + column
            cell_ref = f"{column}{row_index}"
            text = str(value or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            cells.append(f'<c r="{cell_ref}" t="inlineStr"><is><t>{text}</t></is></c>')
        escaped_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')

    worksheet_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"<sheetData>{''.join(escaped_rows)}</sheetData>"
        "</worksheet>"
    )
    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets>'
        "</workbook>"
    )
    workbook_rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        'Target="worksheets/sheet1.xml"/>'
        "</Relationships>"
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

    output = BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types_xml)
        zf.writestr("_rels/.rels", root_rels_xml)
        zf.writestr("xl/workbook.xml", workbook_xml)
        zf.writestr("xl/_rels/workbook.xml.rels", workbook_rels_xml)
        zf.writestr("xl/worksheets/sheet1.xml", worksheet_xml)
    return output.getvalue()


def _find_member(campaign: Campaign, **expected):
    for member in Member.objects.filter(campaign=campaign).order_by("id"):
        if all(getattr(member, key) == value for key, value in expected.items()):
            return member
    return None


class AuthenticatedApiTestCase(TestCase):
    def setUp(self):
        super().setUp()
        user_model = get_user_model()
        username = f"{self.__class__.__name__.lower()}-user"
        self.auth_user = user_model.objects.create_user(username=username, password="pass1234")
        self.auth_token = create_user_token(self.auth_user)
        self.client.defaults["HTTP_AUTHORIZATION"] = f"Bearer {self.auth_token}"


class ApiAuthenticationTests(TestCase):
    @override_settings(API_AUTH_ENFORCED=True, API_AUTH_TOKEN="")
    def test_login_returns_temporary_token_and_protects_api(self):
        user_model = get_user_model()
        user_model.objects.create_user(username="alice", password="pass1234")

        unauthorized = self.client.get("/api/campaigns/")
        self.assertEqual(unauthorized.status_code, 401)

        login_response = self.client.post(
            "/api/auth/login/",
            data={"username": "alice", "password": "pass1234"},
            content_type="application/json",
        )
        self.assertEqual(login_response.status_code, 200)
        body = login_response.json()
        token = str(body.get("token", "")).strip()
        self.assertTrue(token)
        self.assertEqual(body.get("token_type"), "Bearer")
        self.assertTrue(int(body.get("expires_in") or 0) > 0)

        authorized = self.client.get(
            "/api/campaigns/",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(authorized.status_code, 200)

    @override_settings(API_AUTH_ENFORCED=True, API_AUTH_TOKEN="")
    def test_logout_revokes_current_token(self):
        user_model = get_user_model()
        user_model.objects.create_user(username="bob", password="pass1234")

        login_response = self.client.post(
            "/api/auth/login/",
            data={"username": "bob", "password": "pass1234"},
            content_type="application/json",
        )
        self.assertEqual(login_response.status_code, 200)
        token = str(login_response.json().get("token", "")).strip()
        self.assertTrue(token)

        before_logout = self.client.get(
            "/api/campaigns/",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(before_logout.status_code, 200)

        logout_response = self.client.post(
            "/api/auth/logout/",
            data={},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(logout_response.status_code, 200)
        self.assertTrue(bool(logout_response.json().get("logged_out")))

        after_logout = self.client.get(
            "/api/campaigns/",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(after_logout.status_code, 401)


class HelloAssoMemberSyncServiceTests(TestCase):
    def setUp(self):
        self.campaign = Campaign.objects.create(
            title="Campagne test",
            status="active",
            helloasso_api_key="dummy",
            helloasso_form_slug="campagne-test",
        )
        self.import_record = HelloAssoImport.objects.create(
            campaign=self.campaign,
            source="form_items",
            organization_slug="org-test",
            form_type="Membership",
            form_slug="campagne-test",
            with_details=True,
            items_count=0,
            payload={"data": []},
        )

    def test_sync_links_item_to_existing_member_on_name_and_first_name_match(self):
        member = Member.objects.create(
            campaign=self.campaign,
            first_name="Alice",
            name="Durand",
            email="alice-existing@example.com",
            ffck_licence="",
        )
        item = HelloAssoItem.objects.create(
            helloasso_id="ha_1",
            organization_slug="org-test",
            form_type="Membership",
            form_slug="campagne-test",
            status="Paid",
            payer_email="alice-import@example.com",
            latest_import=self.import_record,
            raw_item={
                "user": {
                    "firstName": "Alice",
                    "lastName": "Durand",
                    "email": "alice-import@example.com",
                }
            },
        )

        summary = HelloAssoMemberSyncService(campaign=self.campaign).sync_latest_import(
            import_record=self.import_record
        )

        item.refresh_from_db()
        self.assertEqual(item.member_id, member.id)
        self.assertEqual(summary["created_members"], 0)
        self.assertEqual(summary["linked_items"], 1)


class HelloAssoServiceTests(TestCase):
    def setUp(self):
        self.campaign = Campaign.objects.create(
            title="Campagne test",
            status="active",
            helloasso_api_key="dummy",
            helloasso_form_slug="campagne-test",
        )
        self.import_record = HelloAssoImport.objects.create(
            campaign=self.campaign,
            source="form_items",
            organization_slug="org-test",
            form_type="Membership",
            form_slug="campagne-test",
            with_details=True,
            items_count=0,
            payload={"data": []},
        )

    def test_get_membership_forms_fetches_all_pages_and_normalizes_payload(self):
        service = HelloAssoService(
            client_id="client-id", client_secret="client-secret", default_page_size=2
        )
        called_urls = []

        def fake_request_json(request):
            called_urls.append(request.full_url)
            parsed = urllib.parse.urlparse(request.full_url)
            query = urllib.parse.parse_qs(parsed.query)
            page_index = int((query.get("pageIndex") or ["1"])[0])

            if page_index == 1:
                return {
                    "data": [
                        {
                            "formSlug": "adhesion-2026",
                            "title": "Adhésion 2026",
                            "formType": "Membership",
                            "state": "Public",
                        },
                        {
                            "formSlug": "",
                            "title": "Sans slug",
                            "formType": "Membership",
                            "state": "Draft",
                        },
                    ],
                    "pagination": {"pageCount": 2},
                }

            return {
                "data": [
                    {
                        "formSlug": "adhesion-jeunes-2026",
                        "title": "Adhésion Jeunes 2026",
                        "formType": "Membership",
                        "state": "Public",
                    }
                ],
                "pagination": {"pageCount": 2},
            }

        with (
            patch.object(service, "get_access_token", return_value="token"),
            patch.object(service, "_request_json", side_effect=fake_request_json),
        ):
            forms = service.get_membership_forms(organization_slug="my-org")

        self.assertEqual(len(called_urls), 2)
        self.assertTrue(all("formTypes=Membership" in url for url in called_urls))
        self.assertTrue(any("pageIndex=1" in url for url in called_urls))
        self.assertTrue(any("pageIndex=2" in url for url in called_urls))
        self.assertEqual(
            forms,
            [
                {
                    "form_slug": "adhesion-2026",
                    "title": "Adhésion 2026",
                    "form_type": "Membership",
                    "state": "Public",
                },
                {
                    "form_slug": "adhesion-jeunes-2026",
                    "title": "Adhésion Jeunes 2026",
                    "form_type": "Membership",
                    "state": "Public",
                },
            ],
        )

    def test_sync_creates_member_when_not_found(self):
        item = HelloAssoItem.objects.create(
            helloasso_id="ha_2",
            organization_slug="org-test",
            form_type="Membership",
            form_slug="campagne-test",
            status="Paid",
            payer_email="bob@example.com",
            latest_import=self.import_record,
            raw_item={
                "name": "inscription-loisir",
                "user": {
                    "firstName": "Bob",
                    "lastName": "Martin",
                    "email": "bob@example.com",
                },
            },
        )

        summary = HelloAssoMemberSyncService(campaign=self.campaign).sync_latest_import(
            import_record=self.import_record
        )

        item.refresh_from_db()
        created_member = _find_member(self.campaign, email="bob@example.com")
        self.assertIsNotNone(created_member)
        self.assertEqual(item.member_id, created_member.id)
        self.assertEqual(created_member.first_name, "Bob")
        self.assertEqual(created_member.name, "Martin")
        self.assertEqual(created_member.helloasso_form_slug, "inscription-loisir")
        self.assertEqual(summary["created_members"], 1)
        self.assertEqual(summary["linked_items"], 1)

    def test_sync_updates_member_with_latest_helloasso_form_slug(self):
        first_item = HelloAssoItem.objects.create(
            helloasso_id="ha_2a",
            organization_slug="org-test",
            form_type="Membership",
            form_slug="inscription-loisir",
            status="Paid",
            payer_email="bob@example.com",
            latest_import=self.import_record,
            raw_item={
                "name": "inscription-loisir",
                "user": {
                    "firstName": "Bob",
                    "lastName": "Martin",
                    "email": "bob@example.com",
                },
            },
        )
        second_item = HelloAssoItem.objects.create(
            helloasso_id="ha_2b",
            organization_slug="org-test",
            form_type="Membership",
            form_slug="inscription-competition",
            status="Paid",
            payer_email="bob@example.com",
            latest_import=self.import_record,
            raw_item={
                "name": "inscription-competition",
                "user": {
                    "firstName": "Bob",
                    "lastName": "Martin",
                    "email": "bob@example.com",
                },
            },
        )

        summary = HelloAssoMemberSyncService(campaign=self.campaign).sync_latest_import(
            import_record=self.import_record
        )

        first_item.refresh_from_db()
        second_item.refresh_from_db()
        member = _find_member(self.campaign, email="bob@example.com")
        self.assertIsNotNone(member)
        self.assertEqual(first_item.member_id, member.id)
        self.assertEqual(second_item.member_id, member.id)
        self.assertEqual(member.helloasso_form_slug, "inscription-competition")
        self.assertEqual(summary["linked_items"], 2)

    def test_sync_extracts_document_links_from_item_rows(self):
        item = HelloAssoItem.objects.create(
            helloasso_id="ha_4",
            organization_slug="org-test",
            form_type="Membership",
            form_slug="campagne-test",
            status="Paid",
            payer_email="emma@example.com",
            latest_import=self.import_record,
            raw_item={
                "user": {
                    "firstName": "Emma",
                    "lastName": "Petit",
                    "email": "emma@example.com",
                },
                "itemRow": [
                    {
                        "id": 6170824,
                        "name": "Un Certificat Médical ou Questionnaire de Santé (https://ckcergypontoise.fr/?inscriptions)  est à fournir chaque année. Sans ce document l'inscription restera incomplète !",
                        "type": "File",
                        "answer": "https://docs.helloasso.com/customFieldsAnswer/182720510",
                    },
                    {
                        "id": 6170825,
                        "name": "Autorisation parentale CKCP (https://ckcergypontoise.fr/site/file/source/documents/inscription_ckcp_2023-2024_.pdf)",
                        "type": "File",
                        "answer": "https://docs.helloasso.com/customFieldsAnswer/182720511",
                    },
                    {
                        "id": 6170826,
                        "name": "Photo d'identité",
                        "type": "File",
                        "answer": "https://docs.helloasso.com/customFieldsAnswer/182720512",
                    },
                ],
            },
        )

        HelloAssoMemberSyncService(campaign=self.campaign).sync_latest_import(
            import_record=self.import_record
        )

        item.refresh_from_db()
        member = item.member
        self.assertIsNotNone(member)
        self.assertEqual(
            member.certificat, "https://docs.helloasso.com/customFieldsAnswer/182720510"
        )
        self.assertEqual(
            member.autorisation_parentale,
            "https://docs.helloasso.com/customFieldsAnswer/182720511",
        )
        self.assertEqual(member.photo, "https://docs.helloasso.com/customFieldsAnswer/182720512")

    def test_sync_skips_item_without_complete_identity(self):
        item = HelloAssoItem.objects.create(
            helloasso_id="ha_3",
            organization_slug="org-test",
            form_type="Membership",
            form_slug="campagne-test",
            status="Paid",
            payer_email="",
            latest_import=self.import_record,
            raw_item={"user": {"firstName": "Charlie"}},
        )

        summary = HelloAssoMemberSyncService(campaign=self.campaign).sync_latest_import(
            import_record=self.import_record
        )

        item.refresh_from_db()
        self.assertIsNone(item.member_id)
        self.assertEqual(summary["created_members"], 0)
        self.assertEqual(summary["linked_items"], 0)
        self.assertEqual(summary["skipped_items"], 1)

    def test_sync_keeps_existing_linked_member_instead_of_recreating_old_identity(self):
        kept_member = Member.objects.create(
            campaign=self.campaign,
            first_name="Alice",
            name="Dupont",
            email="alice@example.com",
            ffck_licence="",
        )
        item = HelloAssoItem.objects.create(
            helloasso_id="ha_5",
            organization_slug="org-test",
            form_type="Membership",
            form_slug="campagne-test",
            status="Paid",
            payer_email="alice@example.com",
            member=kept_member,
            latest_import=self.import_record,
            raw_item={
                "user": {
                    "firstName": "Alyce",
                    "lastName": "Dupont",
                    "email": "alice@example.com",
                }
            },
        )

        summary = HelloAssoMemberSyncService(campaign=self.campaign).sync_latest_import(
            import_record=self.import_record
        )

        item.refresh_from_db()
        self.assertEqual(item.member_id, kept_member.id)
        self.assertEqual(summary["created_members"], 0)
        self.assertEqual(Member.objects.filter(campaign=self.campaign).count(), 1)


class HelloAssoSyncMembersViewTests(AuthenticatedApiTestCase):
    def test_sync_members_endpoint_runs_for_campaign(self):
        campaign = Campaign.objects.create(
            title="Campagne sync",
            status="active",
            helloasso_api_key="dummy",
            helloasso_form_slug="campagne-sync",
        )
        import_record = HelloAssoImport.objects.create(
            campaign=campaign,
            source="form_items",
            organization_slug="org-test",
            form_type="Membership",
            form_slug="campagne-sync",
            with_details=True,
            items_count=1,
            payload={"data": []},
        )
        HelloAssoItem.objects.create(
            helloasso_id="ha_sync_1",
            organization_slug="org-test",
            form_type="Membership",
            form_slug="campagne-sync",
            status="Paid",
            payer_email="john@example.com",
            latest_import=import_record,
            raw_item={
                "user": {
                    "firstName": "John",
                    "lastName": "Doe",
                    "email": "john@example.com",
                }
            },
        )

        response = self.client.get(f"/api/helloasso/sync-members/?campaignId={campaign.id}")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["campaign_id"], campaign.id)
        self.assertEqual(body["member_sync"]["linked_items"], 1)
        self.assertEqual(body["member_sync"]["created_members"], 1)
        self.assertIsNotNone(body.get("last_merge"))

        campaign.refresh_from_db()
        self.assertIsNotNone(campaign.last_merge)


class FfckSyncMembersViewTests(AuthenticatedApiTestCase):
    def test_sync_members_endpoint_links_rows_and_updates_member_licence(self):
        campaign = Campaign.objects.create(
            title="Campagne sync ffck",
            status="active",
            helloasso_api_key="dummy",
            helloasso_form_slug="campagne-sync-ffck",
        )
        member = Member.objects.create(
            campaign=campaign,
            first_name="Cyril",
            name="VAN",
            email="cyril@example.com",
            ffck_licence="",
        )
        ffck_export = FfckExport.objects.create(
            campaign=campaign,
            source="licences_excel",
            structure_id=2857,
            export_path="/extractions/licences/excel",
            export_method="POST",
            rows_count=1,
            filename="export.xlsx",
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            file_size=10,
            file_sha256="e" * 64,
            file_blob=b"xlsx",
        )
        ffck_row = FfckExportRow.objects.create(
            ffck_export=ffck_export,
            row_index=1,
            licence="528768",
            nom="VAN Cyril",
            categorie="Senior",
            certificat="Loisir",
            raw_row={
                "nom": "VAN",
                "prenom": "Cyril",
                "type certificat": "Questionnaire de sante",
                "date de fin certificat medical": "2027-02-01",
                "type licence": "Competition",
            },
        )

        response = self.client.get(f"/api/ffck/sync-members/?campaignId={campaign.id}")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["campaign_id"], campaign.id)
        self.assertEqual(body["member_sync"]["linked_rows"], 1)
        self.assertEqual(body["member_sync"]["updated_members"], 1)
        self.assertIsNotNone(body.get("last_merge"))

        ffck_row.refresh_from_db()
        member.refresh_from_db()
        campaign.refresh_from_db()
        self.assertEqual(ffck_row.member_id, member.id)
        self.assertEqual(member.ffck_licence, "528768")
        self.assertIsNotNone(campaign.last_merge)


class BadgeImportAndSyncServiceTests(TestCase):
    def setUp(self):
        self.campaign = Campaign.objects.create(
            title="Campagne badges",
            status="active",
            helloasso_api_key="dummy",
            helloasso_form_slug="campagne-badges",
        )
        self.member = Member.objects.create(
            campaign=self.campaign,
            first_name="John",
            name="Doe",
            email="john@example.com",
            ffck_licence="ABC123",
        )

    def test_import_and_sync_marks_member_badges(self):
        content = build_test_xlsx(
            [
                ["Nom", "Prénom", "Licence", "Badge possédé", "Badge commandé"],
                ["Doe", "John", "ABC123", "oui", ""],
                ["Unknown", "Person", "NOPE", "", "oui"],
            ]
        )
        extraction = BadgeExcelExtraction(
            filename="badges.xlsx",
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            content=content,
        )

        import_summary = BadgeImportService(campaign=self.campaign).import_extraction(extraction)
        sync_summary = BadgeMemberSyncService(campaign=self.campaign).sync_latest_import()

        self.assertEqual(import_summary["rows_count"], 2)
        self.assertEqual(sync_summary["linked_rows"], 1)
        self.assertEqual(sync_summary["skipped_rows"], 1)

        self.member.refresh_from_db()
        self.assertTrue(self.member.badge_owned)
        self.assertFalse(self.member.badge_ordered)

    def test_sync_matches_on_name_and_first_name_not_licence(self):
        content = build_test_xlsx(
            [
                ["Nom", "Prénom", "Licence", "Badge commandé"],
                ["Doe", "John", "DIFFERENT-LICENCE", "oui"],
            ]
        )
        extraction = BadgeExcelExtraction(
            filename="badges.xlsx",
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            content=content,
        )

        BadgeImportService(campaign=self.campaign).import_extraction(extraction)
        sync_summary = BadgeMemberSyncService(campaign=self.campaign).sync_latest_import()

        self.assertEqual(sync_summary["linked_rows"], 1)
        self.assertEqual(sync_summary["skipped_rows"], 0)
        self.member.refresh_from_db()
        self.assertTrue(self.member.badge_ordered)


class BadgeImportAndSyncViewTests(AuthenticatedApiTestCase):
    def test_badge_import_endpoint_imports_and_syncs_members(self):
        campaign = Campaign.objects.create(
            title="Campagne badges endpoint",
            status="active",
            helloasso_api_key="dummy",
            helloasso_form_slug="campagne-badges-endpoint",
        )
        member = Member.objects.create(
            campaign=campaign,
            first_name="Alice",
            name="Martin",
            email="alice@example.com",
            ffck_licence="LIC-999",
        )
        content = build_test_xlsx(
            [
                ["Nom", "Prénom", "Licence", "Statut badge"],
                ["Martin", "Alice", "LIC-999", "commandé"],
            ]
        )

        response = self.client.post(
            f"/api/badges/import/?campaignId={campaign.id}",
            data={
                "file": SimpleUploadedFile(
                    "badges.xlsx",
                    content,
                    content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["campaign_id"], campaign.id)
        self.assertEqual(body["import"]["rows_count"], 1)
        self.assertEqual(body["member_sync"]["linked_rows"], 1)

        member.refresh_from_db()
        self.assertFalse(member.badge_owned)
        self.assertTrue(member.badge_ordered)

    def test_badges_latest_rows_endpoint_returns_latest_import_rows(self):
        campaign = Campaign.objects.create(
            title="Campagne badges latest",
            status="active",
            helloasso_api_key="dummy",
            helloasso_form_slug="campagne-badges-latest",
        )
        badge_import = BadgeImport.objects.create(
            campaign=campaign,
            source="badge_excel",
            rows_count=1,
            filename="badges.xlsx",
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            file_size=10,
            file_sha256="b" * 64,
            file_blob=b"xlsx",
        )
        BadgeImportRow.objects.create(
            badge_import=badge_import,
            row_index=1,
            name="Durand",
            first_name="Bob",
            licence="L-1",
            badge_owned=True,
            badge_ordered=False,
            raw_row={"nom": "Durand", "prenom": "Bob"},
        )

        response = self.client.get(f"/api/badges/rows/latest/?campaignId={campaign.id}")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["campaign_id"], campaign.id)
        self.assertEqual(len(body["rows"]), 1)
        self.assertEqual(body["rows"][0]["licence"], "L-1")
        self.assertEqual(body["rows"][0]["badge_owned"], True)


class CampaignSyncMembersViewTests(AuthenticatedApiTestCase):
    def test_sync_members_endpoint_runs_helloasso_then_ffck(self):
        campaign = Campaign.objects.create(
            title="Campagne sync complete",
            status="active",
            helloasso_api_key="dummy",
            helloasso_form_slug="campagne-sync-complete",
        )
        import_record = HelloAssoImport.objects.create(
            campaign=campaign,
            source="form_items",
            organization_slug="org-test",
            form_type="Membership",
            form_slug="campagne-sync-complete",
            with_details=True,
            items_count=1,
            payload={"data": []},
        )
        HelloAssoItem.objects.create(
            helloasso_id="ha_complete_1",
            organization_slug="org-test",
            form_type="Membership",
            form_slug="campagne-sync-complete",
            status="Paid",
            payer_email="john@example.com",
            latest_import=import_record,
            raw_item={
                "user": {
                    "firstName": "John",
                    "lastName": "Doe",
                    "email": "john@example.com",
                }
            },
        )
        ffck_export = FfckExport.objects.create(
            campaign=campaign,
            source="licences_excel",
            structure_id=2857,
            export_path="/extractions/licences/excel",
            export_method="POST",
            rows_count=1,
            filename="export.xlsx",
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            file_size=10,
            file_sha256="f" * 64,
            file_blob=b"xlsx",
        )
        ffck_row = FfckExportRow.objects.create(
            ffck_export=ffck_export,
            row_index=1,
            licence="123456",
            nom="DOE John",
            categorie="Senior",
            certificat="Loisir",
            raw_row={"nom": "Doe", "prenom": "John"},
        )

        response = self.client.get(f"/api/campaigns/sync-members/?campaignId={campaign.id}")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["campaign_id"], campaign.id)
        self.assertEqual(body["helloasso_member_sync"]["created_members"], 1)
        self.assertEqual(body["helloasso_member_sync"]["linked_items"], 1)
        self.assertEqual(body["ffck_member_sync"]["linked_rows"], 1)
        self.assertEqual(body["ffck_member_sync"]["updated_members"], 1)
        self.assertIn("badge_member_sync", body)
        self.assertIsNotNone(body.get("last_merge"))

        member = _find_member(campaign, first_name="John", name="Doe")
        self.assertIsNotNone(member)
        ffck_row.refresh_from_db()
        member.refresh_from_db()
        campaign.refresh_from_db()
        self.assertEqual(ffck_row.member_id, member.id)
        self.assertEqual(member.ffck_licence, "123456")
        self.assertIsNotNone(campaign.last_merge)


class CampaignMemberDedupViewsTests(AuthenticatedApiTestCase):
    def test_member_duplicate_suggestions_endpoint_detects_similar_names(self):
        campaign = Campaign.objects.create(
            title="Campagne dedup",
            status="active",
            helloasso_api_key="dummy",
            helloasso_form_slug="campagne-dedup",
        )
        Member.objects.create(
            campaign=campaign,
            first_name="Cyril",
            name="Van",
            email="cyril.van@example.com",
            ffck_licence="",
        )
        Member.objects.create(
            campaign=campaign,
            first_name="Cyríl",
            name="Vân",
            email="",
            ffck_licence="",
        )

        response = self.client.get(
            f"/api/campaigns/member-duplicates/?campaignId={campaign.id}&refresh=1&minScore=0.8"
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["campaign_id"], campaign.id)
        self.assertEqual(len(body["suggestions"]), 1)
        suggestion = body["suggestions"][0]
        self.assertGreaterEqual(suggestion["similarity_score"], 0.8)
        self.assertEqual(suggestion["status"], "pending")

    def test_member_duplicate_merge_endpoint_relinks_rows_and_items(self):
        campaign = Campaign.objects.create(
            title="Campagne merge dedup",
            status="active",
            helloasso_api_key="dummy",
            helloasso_form_slug="campagne-merge-dedup",
        )
        keep_member = Member.objects.create(
            campaign=campaign,
            first_name="Alice",
            name="Dupont",
            email="alice@example.com",
            ffck_licence="",
        )
        duplicate_member = Member.objects.create(
            campaign=campaign,
            first_name="Alyce",
            name="Dupont",
            email="",
            ffck_licence="123456",
        )
        helloasso_item = HelloAssoItem.objects.create(
            helloasso_id="ha_dedup_1",
            organization_slug="org-test",
            form_type="Membership",
            form_slug="campagne-merge-dedup",
            status="Paid",
            payer_email="alice@example.com",
            member=duplicate_member,
            raw_item={},
        )
        ffck_export = FfckExport.objects.create(
            campaign=campaign,
            source="licences_excel",
            structure_id=2857,
            export_path="/extractions/licences/excel",
            export_method="POST",
            rows_count=1,
            filename="export.xlsx",
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            file_size=10,
            file_sha256="a" * 64,
            file_blob=b"xlsx",
        )
        ffck_row = FfckExportRow.objects.create(
            ffck_export=ffck_export,
            row_index=1,
            licence="123456",
            nom="Dupont Alyce",
            categorie="Senior",
            certificat="Loisir",
            member=duplicate_member,
            raw_row={"nom": "Dupont", "prenom": "Alyce"},
        )
        suggestion = MemberDuplicateSuggestion.objects.create(
            campaign=campaign,
            member_left=keep_member,
            member_right=duplicate_member,
            recommended_master=keep_member,
            similarity_score=0.92,
            reasons=["nom_prenom_proches"],
            status=MemberDuplicateSuggestion.STATUS_PENDING,
        )

        response = self.client.post(
            f"/api/campaigns/member-duplicates/merge/?campaignId={campaign.id}",
            data=json.dumps({"suggestion_id": suggestion.id, "keep_member_id": keep_member.id}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        helloasso_item.refresh_from_db()
        ffck_row.refresh_from_db()
        keep_member.refresh_from_db()
        self.assertFalse(Member.objects.filter(id=duplicate_member.id).exists())
        self.assertEqual(helloasso_item.member_id, keep_member.id)
        self.assertEqual(ffck_row.member_id, keep_member.id)
        self.assertEqual(keep_member.ffck_licence, "123456")
        self.assertFalse(MemberDuplicateSuggestion.objects.filter(id=suggestion.id).exists())

    def test_member_duplicate_merge_allows_multiple_merges_into_same_master(self):
        campaign = Campaign.objects.create(
            title="Campagne merge dedup multiple",
            status="active",
            helloasso_api_key="dummy",
            helloasso_form_slug="campagne-merge-dedup-multiple",
        )
        keep_member = Member.objects.create(
            campaign=campaign,
            first_name="Alice",
            name="Dupont",
            email="alice@example.com",
            ffck_licence="",
        )
        duplicate_1 = Member.objects.create(
            campaign=campaign,
            first_name="Alyce",
            name="Dupont",
            email="",
            ffck_licence="111111",
        )
        duplicate_2 = Member.objects.create(
            campaign=campaign,
            first_name="Alise",
            name="Dupont",
            email="",
            ffck_licence="222222",
        )
        suggestion_1 = MemberDuplicateSuggestion.objects.create(
            campaign=campaign,
            member_left=keep_member,
            member_right=duplicate_1,
            recommended_master=keep_member,
            similarity_score=0.92,
            reasons=["nom_prenom_proches"],
            status=MemberDuplicateSuggestion.STATUS_PENDING,
        )
        suggestion_2 = MemberDuplicateSuggestion.objects.create(
            campaign=campaign,
            member_left=keep_member,
            member_right=duplicate_2,
            recommended_master=keep_member,
            similarity_score=0.90,
            reasons=["nom_prenom_proches"],
            status=MemberDuplicateSuggestion.STATUS_PENDING,
        )

        response_1 = self.client.post(
            f"/api/campaigns/member-duplicates/merge/?campaignId={campaign.id}",
            data=json.dumps({"suggestion_id": suggestion_1.id, "keep_member_id": keep_member.id}),
            content_type="application/json",
        )
        response_2 = self.client.post(
            f"/api/campaigns/member-duplicates/merge/?campaignId={campaign.id}",
            data=json.dumps({"suggestion_id": suggestion_2.id, "keep_member_id": keep_member.id}),
            content_type="application/json",
        )

        self.assertEqual(response_1.status_code, 200)
        self.assertEqual(response_2.status_code, 200)
        self.assertFalse(Member.objects.filter(id=duplicate_1.id).exists())
        self.assertFalse(Member.objects.filter(id=duplicate_2.id).exists())
        self.assertTrue(Member.objects.filter(id=keep_member.id).exists())

    def test_member_duplicate_merge_fills_blank_fields_from_dropped_member(self):
        campaign = Campaign.objects.create(
            title="Campagne merge dedup fill-blanks",
            status="active",
            helloasso_api_key="dummy",
            helloasso_form_slug="campagne-merge-dedup-fill-blanks",
        )
        keep_member = Member.objects.create(
            campaign=campaign,
            first_name="Alice",
            name="Dupont",
            email="   ",
            ffck_licence="",
            certificat="",
            autorisation_parentale="",
            photo="",
            option_ia=False,
            manual_review=False,
        )
        duplicate_member = Member.objects.create(
            campaign=campaign,
            first_name="Alice",
            name="Dupont",
            email="alice@example.com",
            ffck_licence="987654",
            certificat="https://docs.example.com/certif.pdf",
            autorisation_parentale="https://docs.example.com/autorisation.pdf",
            photo="https://docs.example.com/photo.jpg",
            option_ia=True,
            manual_review=True,
        )
        suggestion = MemberDuplicateSuggestion.objects.create(
            campaign=campaign,
            member_left=keep_member,
            member_right=duplicate_member,
            recommended_master=keep_member,
            similarity_score=0.99,
            reasons=["nom_prenom_tres_proches"],
            status=MemberDuplicateSuggestion.STATUS_PENDING,
        )

        response = self.client.post(
            f"/api/campaigns/member-duplicates/merge/?campaignId={campaign.id}",
            data=json.dumps({"suggestion_id": suggestion.id, "keep_member_id": keep_member.id}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        keep_member.refresh_from_db()
        self.assertEqual(keep_member.email, "alice@example.com")
        self.assertEqual(keep_member.ffck_licence, "987654")
        self.assertEqual(keep_member.certificat, "https://docs.example.com/certif.pdf")
        self.assertEqual(
            keep_member.autorisation_parentale, "https://docs.example.com/autorisation.pdf"
        )
        self.assertEqual(keep_member.photo, "https://docs.example.com/photo.jpg")
        self.assertTrue(keep_member.option_ia)
        self.assertTrue(keep_member.manual_review)


class CampaignMembersViewManualReviewTests(AuthenticatedApiTestCase):
    def test_campaign_members_returns_manual_review_with_labels(self):
        campaign = Campaign.objects.create(
            title="Campagne membres",
            status="active",
            helloasso_api_key="dummy",
            helloasso_form_slug="campagne-membres",
        )
        member_default = Member.objects.create(
            campaign=campaign,
            first_name="Alice",
            name="Durand",
            email="alice@example.com",
            ffck_licence="",
        )
        member_reviewed = Member.objects.create(
            campaign=campaign,
            first_name="Bob",
            name="Martin",
            email="bob@example.com",
            ffck_licence="",
            manual_review=True,
        )

        response = self.client.get(f"/api/campaigns/{campaign.id}/members/")

        self.assertEqual(response.status_code, 200)
        members = response.json().get("members", [])
        self.assertEqual(len(members), 2)

        by_id = {row["id"]: row for row in members}
        self.assertEqual(by_id[member_default.id]["manual_review"], False)
        self.assertEqual(by_id[member_default.id]["manual_review_label"], "non vérifié")
        self.assertEqual(by_id[member_default.id]["helloasso_form_slug"], "")
        self.assertEqual(by_id[member_reviewed.id]["manual_review"], True)
        self.assertEqual(by_id[member_reviewed.id]["manual_review_label"], "vérifié")
        self.assertEqual(by_id[member_reviewed.id]["helloasso_form_slug"], "")


class CampaignManualEditionViewTests(AuthenticatedApiTestCase):
    def test_manual_edition_updates_members_and_campaign_timestamp(self):
        campaign = Campaign.objects.create(
            title="Campagne édition",
            status="active",
            helloasso_api_key="dummy",
            helloasso_form_slug="campagne-edition",
        )
        member = Member.objects.create(
            campaign=campaign,
            first_name="Alice",
            name="Durand",
            email="alice@example.com",
            ffck_licence="",
            manual_review=False,
        )

        response = self.client.post(
            f"/api/campaigns/{campaign.id}/manual-edition/",
            data={
                "members": [
                    {
                        "id": member.id,
                        "first_name": "Alicia",
                        "manual_review": True,
                    }
                ]
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["campaign_id"], campaign.id)
        self.assertEqual(body["updated_count"], 1)
        self.assertIn(member.id, body["updated_member_ids"])
        self.assertIsNotNone(body.get("last_manual_edition"))

        member.refresh_from_db()
        campaign.refresh_from_db()
        self.assertEqual(member.first_name, "Alicia")
        self.assertEqual(member.manual_review, True)
        self.assertIsNotNone(campaign.last_manual_edition)

    def test_manual_edition_updates_member_helloasso_form_slug(self):
        campaign = Campaign.objects.create(
            title="Campagne édition slug",
            status="active",
            helloasso_api_key="dummy",
            helloasso_form_slug="campagne-edition-slug",
        )
        member = Member.objects.create(
            campaign=campaign,
            first_name="Alice",
            name="Durand",
            email="alice@example.com",
            ffck_licence="",
            helloasso_form_slug="inscription-loisir",
        )

        response = self.client.post(
            f"/api/campaigns/{campaign.id}/manual-edition/",
            data={
                "members": [
                    {
                        "id": member.id,
                        "helloasso_form_slug": "inscription-competition",
                    }
                ]
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        member.refresh_from_db()
        self.assertEqual(member.helloasso_form_slug, "inscription-competition")


class CampaignMembersCreateViewTests(AuthenticatedApiTestCase):
    def test_create_member_for_campaign(self):
        campaign = Campaign.objects.create(
            title="Campagne création membre",
            status="active",
            helloasso_api_key="dummy",
            helloasso_form_slug="campagne-create-member",
        )

        response = self.client.post(
            f"/api/campaigns/{campaign.id}/members/",
            data={
                "first_name": "Camille",
                "name": "Dupont",
                "email": "camille.dupont@example.com",
                "ffck_licence": "ABC123",
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        body = response.json()
        created = body.get("member", {})
        self.assertEqual(created.get("first_name"), "Camille")
        self.assertEqual(created.get("name"), "Dupont")
        self.assertEqual(created.get("email"), "camille.dupont@example.com")
        self.assertEqual(created.get("campaign_id"), campaign.id)
        self.assertIsNotNone(
            _find_member(
                campaign,
                email="camille.dupont@example.com",
                first_name="Camille",
                name="Dupont",
            )
        )

    def test_create_member_requires_email(self):
        campaign = Campaign.objects.create(
            title="Campagne validation membre",
            status="active",
            helloasso_api_key="dummy",
            helloasso_form_slug="campagne-validation-member",
        )

        response = self.client.post(
            f"/api/campaigns/{campaign.id}/members/",
            data={
                "first_name": "Camille",
                "name": "Dupont",
                "email": "   ",
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json().get("error"), "'email' is required.")


class CampaignMembersBulkDeleteViewTests(AuthenticatedApiTestCase):
    def test_bulk_delete_members_for_campaign(self):
        campaign = Campaign.objects.create(
            title="Campagne suppression membre",
            status="active",
            helloasso_api_key="dummy",
            helloasso_form_slug="campagne-delete-member",
        )
        other_campaign = Campaign.objects.create(
            title="Campagne autre",
            status="active",
            helloasso_api_key="dummy",
            helloasso_form_slug="campagne-other-member",
        )
        member_1 = Member.objects.create(
            campaign=campaign,
            first_name="Alice",
            name="Durand",
            email="alice@example.com",
            ffck_licence="",
        )
        member_2 = Member.objects.create(
            campaign=campaign,
            first_name="Bob",
            name="Martin",
            email="bob@example.com",
            ffck_licence="",
        )
        other_member = Member.objects.create(
            campaign=other_campaign,
            first_name="Claire",
            name="Petit",
            email="claire@example.com",
            ffck_licence="",
        )

        response = self.client.post(
            f"/api/campaigns/{campaign.id}/members/bulk-delete/",
            data={"member_ids": [member_1.id, member_2.id, other_member.id]},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body.get("campaign_id"), campaign.id)
        self.assertEqual(body.get("deleted_count"), 2)
        self.assertEqual(body.get("deleted_member_ids"), [member_1.id, member_2.id])
        self.assertFalse(Member.objects.filter(id=member_1.id).exists())
        self.assertFalse(Member.objects.filter(id=member_2.id).exists())
        self.assertTrue(Member.objects.filter(id=other_member.id).exists())

    def test_bulk_delete_requires_member_ids_array(self):
        campaign = Campaign.objects.create(
            title="Campagne suppression validation",
            status="active",
            helloasso_api_key="dummy",
            helloasso_form_slug="campagne-delete-validation",
        )

        response = self.client.post(
            f"/api/campaigns/{campaign.id}/members/bulk-delete/",
            data={"member_ids": "not-a-list"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json().get("error"), "'member_ids' must be an array.")


class CampaignCreateViewTests(AuthenticatedApiTestCase):
    def test_create_campaign_with_defaults(self):
        response = self.client.post(
            "/api/campaigns/",
            data={"title": "2027"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        body = response.json()
        campaign = body.get("campaign", {})
        self.assertEqual(campaign.get("title"), "2027")
        self.assertEqual(campaign.get("status"), "active")
        self.assertEqual(campaign.get("helloasso_api_key"), "")
        self.assertEqual(campaign.get("helloasso_form_slug"), "")
        self.assertTrue(any(item.title == "2027" for item in Campaign.objects.all()))

    def test_create_campaign_requires_title(self):
        response = self.client.post(
            "/api/campaigns/",
            data={"title": "   "},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json().get("error"), "'title' is required.")


class FederationExtranetServiceTests(TestCase):
    def test_totp_generation_matches_rfc_vector(self):
        secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
        code = FederationExtranetService.generate_totp(
            secret,
            digits=8,
            period=30,
            for_time=59,
        )

        self.assertEqual(code, "94287082")


class FederationExtranetExtractExcelViewTests(AuthenticatedApiTestCase):
    @override_settings(
        FFCK_EXTRANET_BASE_URL="https://extranet.example.test",
        FFCK_EXTRANET_LOGIN_PATH="/login",
        FFCK_EXTRANET_TOTP_PATH="/totp",
        FFCK_EXTRANET_EXPORT_PATH="/exports/members.xlsx",
        FFCK_EXTRANET_USERNAME="demo-user",
        FFCK_EXTRANET_PASSWORD="demo-password",
        FFCK_EXTRANET_TOTP_SECRET="JBSWY3DPEHPK3PXP",
    )
    @patch("api.views.FederationExtranetService")
    def test_extract_excel_returns_attachment(self, mock_service_class):
        mock_service = mock_service_class.return_value
        mock_service.extract_excel.return_value = ExtranetExcelExtraction(
            filename="members.xlsx",
            content_type=("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            content=b"fake-xlsx-content",
            token="hidden-token",
        )

        response = self.client.get("/api/federation/extract-excel/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Content-Type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        self.assertEqual(
            response["Content-Disposition"],
            'attachment; filename="members.xlsx"',
        )
        self.assertEqual(response.content, b"fake-xlsx-content")

    @patch("api.views.FederationExtranetService")
    def test_extract_excel_returns_502_on_auth_error(self, mock_service_class):
        from api.services.federation_extranet_service import FederationExtranetAuthError

        mock_service = mock_service_class.return_value
        mock_service.extract_excel.side_effect = FederationExtranetAuthError(
            "Authentication failed"
        )

        response = self.client.get("/api/federation/extract-excel/")

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json().get("error"), "Authentication failed")


class FfckLatestRowsViewTests(AuthenticatedApiTestCase):
    def test_returns_latest_export_rows_for_campaign(self):
        campaign = Campaign.objects.create(
            title="Campagne FFCK rows",
            status="active",
            helloasso_api_key="dummy",
            helloasso_form_slug="campagne-ffck-rows",
        )
        old_export = FfckExport.objects.create(
            campaign=campaign,
            source="licences_excel",
            export_path="/extractions/licences/excel",
            export_method="POST",
            rows_count=1,
            filename="old.xlsx",
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            file_size=10,
            file_sha256="a" * 64,
            file_blob=b"old",
        )
        latest_export = FfckExport.objects.create(
            campaign=campaign,
            source="licences_excel",
            structure_id=2857,
            export_path="/extractions/licences/excel",
            export_method="POST",
            rows_count=2,
            filename="latest.xlsx",
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            file_size=20,
            file_sha256="b" * 64,
            file_blob=b"latest",
        )
        FfckExportRow.objects.create(
            ffck_export=old_export,
            row_index=1,
            licence="OLD1",
            nom="Old User",
            categorie="Senior",
            certificat="Loisir",
            raw_row={"code adherent": "OLD1"},
        )
        FfckExportRow.objects.create(
            ffck_export=latest_export,
            row_index=1,
            licence="NEW1",
            nom="Alice Dupont",
            categorie="Senior",
            certificat="Loisir",
            raw_row={"code adherent": "NEW1"},
        )
        FfckExportRow.objects.create(
            ffck_export=latest_export,
            row_index=2,
            licence="NEW2",
            nom="Bob Martin",
            categorie="Jeune",
            certificat="Questionnaire Santé",
            raw_row={"code adherent": "NEW2"},
        )

        response = self.client.get(f"/api/ffck/rows/latest/?campaignId={campaign.id}")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["campaign_id"], campaign.id)
        self.assertEqual(body["export"]["id"], latest_export.id)
        self.assertEqual(body["export"]["filename"], "latest.xlsx")
        self.assertEqual(len(body["rows"]), 2)
        self.assertEqual(body["rows"][0]["licence"], "NEW1")
        self.assertEqual(body["rows"][1]["licence"], "NEW2")

    def test_returns_empty_when_no_export_for_campaign(self):
        campaign = Campaign.objects.create(
            title="Campagne sans export",
            status="active",
            helloasso_api_key="dummy",
            helloasso_form_slug="campagne-empty-ffck",
        )

        response = self.client.get(f"/api/ffck/rows/latest/?campaignId={campaign.id}")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["campaign_id"], campaign.id)
        self.assertEqual(body["rows"], [])
        self.assertIsNone(body["export"])

    def test_requires_integer_campaign_id(self):
        response = self.client.get("/api/ffck/rows/latest/?campaignId=abc")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json().get("error"), "campaignId must be an integer.")


@skipUnless(
    os.getenv("FFCK_RUN_REAL_EXTRANET_TEST", "").strip().lower() in {"1", "true", "yes"},
    "Set FFCK_RUN_REAL_EXTRANET_TEST=1 to run real FFCK extranet integration test.",
)
class FederationExtranetRealIntegrationTests(AuthenticatedApiTestCase):
    def test_real_extract_excel_from_ffck_extranet(self):
        required_settings = [
            "FFCK_EXTRANET_BASE_URL",
            "FFCK_EXTRANET_LOGIN_PATH",
            "FFCK_EXTRANET_TOTP_PATH",
            "FFCK_EXTRANET_EXPORT_PATH",
            "FFCK_EXTRANET_USERNAME",
            "FFCK_EXTRANET_PASSWORD",
            "FFCK_EXTRANET_TOTP_SECRET",
        ]
        missing = [key for key in required_settings if not str(getattr(settings, key, "")).strip()]
        if missing:
            self.fail(
                "Missing required FFCK settings for real integration test: " + ", ".join(missing)
            )

        response = self.client.get("/api/federation/extract-excel/")

        self.assertEqual(
            response.status_code,
            200,
            msg=f"Unexpected status {response.status_code}: {response.content[:400]!r}",
        )

        content_type = response["Content-Type"].split(";")[0].strip()
        self.assertEqual(
            content_type,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        content = bytes(response.content)
        self.assertGreater(
            len(content),
            1024,
            "Exported file is unexpectedly small.",
        )
        self.assertTrue(
            content.startswith(b"PK"),
            "Returned file does not look like an XLSX/ZIP payload.",
        )

        output_dir = Path(os.getenv("FFCK_REAL_TEST_OUTPUT_DIR", "/tmp/ffck-real-tests"))
        output_dir.mkdir(parents=True, exist_ok=True)

        disposition = response.get("Content-Disposition", "")
        suggested_name = ""
        if "filename=" in disposition:
            suggested_name = disposition.split("filename=", 1)[1].strip().strip('"')

        filename = suggested_name or f"ffck_extraction_real_{int(time.time())}.xlsx"
        artifact_path = output_dir / filename
        artifact_path.write_bytes(content)

        self.assertTrue(artifact_path.exists())
        self.assertGreater(artifact_path.stat().st_size, 1024)


def _build_minimal_xlsx_bytes(rows):
    content_types = """<?xml version='1.0' encoding='UTF-8'?>
<Types xmlns='http://schemas.openxmlformats.org/package/2006/content-types'>
  <Default Extension='rels' ContentType='application/vnd.openxmlformats-package.relationships+xml'/>
  <Default Extension='xml' ContentType='application/xml'/>
  <Override PartName='/xl/workbook.xml' ContentType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml'/>
  <Override PartName='/xl/worksheets/sheet1.xml' ContentType='application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml'/>
</Types>"""
    rels = """<?xml version='1.0' encoding='UTF-8'?>
<Relationships xmlns='http://schemas.openxmlformats.org/package/2006/relationships'>
  <Relationship Id='rId1' Type='http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument' Target='xl/workbook.xml'/>
</Relationships>"""
    workbook = """<?xml version='1.0' encoding='UTF-8'?>
<workbook xmlns='http://schemas.openxmlformats.org/spreadsheetml/2006/main' xmlns:r='http://schemas.openxmlformats.org/officeDocument/2006/relationships'>
  <sheets>
    <sheet name='Sheet1' sheetId='1' r:id='rId1'/>
  </sheets>
</workbook>"""
    workbook_rels = """<?xml version='1.0' encoding='UTF-8'?>
<Relationships xmlns='http://schemas.openxmlformats.org/package/2006/relationships'>
  <Relationship Id='rId1' Type='http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet' Target='worksheets/sheet1.xml'/>
</Relationships>"""

    def col_name(i):
        out = ""
        while i > 0:
            i, r = divmod(i - 1, 26)
            out = chr(ord("A") + r) + out
        return out

    sheet_rows = []
    for idx, row in enumerate(rows, start=1):
        cells = []
        for col_idx, value in enumerate(row, start=1):
            ref = f"{col_name(col_idx)}{idx}"
            txt = str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            cells.append(f"<c r='{ref}' t='inlineStr'><is><t>{txt}</t></is></c>")
        sheet_rows.append(f"<row r='{idx}'>" + "".join(cells) + "</row>")

    worksheet = (
        "<?xml version='1.0' encoding='UTF-8'?>"
        "<worksheet xmlns='http://schemas.openxmlformats.org/spreadsheetml/2006/main'>"
        "<sheetData>" + "".join(sheet_rows) + "</sheetData>"
        "</worksheet>"
    )

    from io import BytesIO
    from zipfile import ZIP_DEFLATED, ZipFile

    buffer = BytesIO()
    with ZipFile(buffer, mode="w", compression=ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("xl/workbook.xml", workbook)
        zf.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        zf.writestr("xl/worksheets/sheet1.xml", worksheet)

    return buffer.getvalue()


class FfckExportImportServiceTests(TestCase):
    def test_import_extraction_creates_export_and_rows(self):
        campaign = Campaign.objects.create(
            title="Campagne FFCK",
            status="active",
            helloasso_api_key="dummy",
            helloasso_form_slug="campagne-ffck",
        )

        xlsx_content = _build_minimal_xlsx_bytes(
            [
                ["Code adhérent", "Nom", "Prénom", "Catégorie âge sportif", "Type certificat"],
                ["12345", "Dupont", "Alice", "Senior", "Loisir"],
                ["67890", "Martin", "Bob", "Jeune", "Questionnaire Santé"],
            ]
        )

        extraction = ExtranetExcelExtraction(
            filename="export.xlsx",
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            content=xlsx_content,
            token="",
        )

        summary = FfckExportImportService(campaign=campaign).import_extraction(
            extraction,
            structure_select_path="/auth/select-structure/2857",
            export_path="/extractions/licences/excel",
            export_method="POST",
            export_payload={"saison": "2026"},
        )

        ffck_export = FfckExport.objects.get(id=summary["ffck_export_id"])
        rows = list(FfckExportRow.objects.filter(ffck_export=ffck_export).order_by("row_index"))

        self.assertEqual(ffck_export.campaign_id, campaign.id)
        self.assertEqual(ffck_export.structure_id, 2857)
        self.assertEqual(ffck_export.rows_count, 2)
        self.assertEqual(summary["rows_count"], 2)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].licence, "12345")
        self.assertEqual(rows[0].nom, "Dupont Alice")
        self.assertEqual(rows[0].categorie, "Senior")
        self.assertEqual(rows[0].certificat, "Loisir")
        self.assertEqual(rows[1].licence, "67890")
        self.assertEqual(rows[1].nom, "Martin Bob")


class FfckMemberSyncServiceTests(TestCase):
    def test_sync_latest_export_links_rows_and_updates_member_licence(self):
        campaign = Campaign.objects.create(
            title="Campagne FFCK sync",
            status="active",
            helloasso_api_key="dummy",
            helloasso_form_slug="campagne-ffck-sync",
        )
        member = Member.objects.create(
            campaign=campaign,
            first_name="Cyril",
            name="VAN",
            email="cyril@example.com",
            ffck_licence="",
        )
        ffck_export = FfckExport.objects.create(
            campaign=campaign,
            source="licences_excel",
            structure_id=2857,
            export_path="/extractions/licences/excel",
            export_method="POST",
            rows_count=1,
            filename="export.xlsx",
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            file_size=12,
            file_sha256="c" * 64,
            file_blob=b"xlsx",
        )
        ffck_row = FfckExportRow.objects.create(
            ffck_export=ffck_export,
            row_index=1,
            licence="528768",
            nom="VAN Cyril",
            categorie="Senior",
            certificat="Loisir",
            raw_row={
                "nom": "VAN",
                "prenom": "Cyril",
                "type certificat": "Questionnaire de sante",
                "date de fin certificat medical": "2027-02-01",
                "type licence": "Competition",
            },
        )

        summary = FfckMemberSyncService(campaign=campaign).sync_latest_export()

        ffck_row.refresh_from_db()
        member.refresh_from_db()
        self.assertEqual(ffck_row.member_id, member.id)
        self.assertEqual(member.ffck_licence, "528768")
        self.assertEqual(member.ffck_certificat, "Questionnaire de sante")
        self.assertEqual(member.ffck_certificat_expiration, "2027-02-01")
        self.assertEqual(member.ffck_licence_type, "Competition")
        self.assertEqual(summary["linked_rows"], 1)
        self.assertEqual(summary["updated_members"], 1)
        self.assertEqual(summary["skipped_rows"], 0)

    def test_sync_latest_export_creates_member_when_missing_and_skips_rows_without_identity(self):
        campaign = Campaign.objects.create(
            title="Campagne FFCK sync skip",
            status="active",
            helloasso_api_key="dummy",
            helloasso_form_slug="campagne-ffck-sync-skip",
        )
        ffck_export = FfckExport.objects.create(
            campaign=campaign,
            source="licences_excel",
            export_path="/extractions/licences/excel",
            export_method="POST",
            rows_count=2,
            filename="export.xlsx",
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            file_size=12,
            file_sha256="d" * 64,
            file_blob=b"xlsx",
        )
        row_without_identity = FfckExportRow.objects.create(
            ffck_export=ffck_export,
            row_index=1,
            licence="000001",
            nom="",
            categorie="",
            certificat="",
            raw_row={},
        )
        row_without_member = FfckExportRow.objects.create(
            ffck_export=ffck_export,
            row_index=2,
            licence="000002",
            nom="Dupont Alice",
            categorie="",
            certificat="",
            raw_row={
                "nom": "Dupont",
                "prenom": "Alice",
                "type certificat": "Certificat medical",
                "date de fin certificat medical": "2026-12-31",
                "type licence": "Loisir",
            },
        )

        summary = FfckMemberSyncService(campaign=campaign).sync_latest_export()

        row_without_identity.refresh_from_db()
        row_without_member.refresh_from_db()
        self.assertIsNone(row_without_identity.member_id)
        self.assertIsNotNone(row_without_member.member_id)
        created_member = Member.objects.get(id=row_without_member.member_id)
        self.assertEqual(created_member.first_name, "Alice")
        self.assertEqual(created_member.name, "Dupont")
        self.assertEqual(created_member.ffck_licence, "000002")
        self.assertEqual(created_member.ffck_certificat, "Certificat medical")
        self.assertEqual(created_member.ffck_certificat_expiration, "2026-12-31")
        self.assertEqual(created_member.ffck_licence_type, "Loisir")
        self.assertEqual(summary["linked_rows"], 1)
        self.assertEqual(summary["updated_members"], 1)
        self.assertEqual(summary["created_members"], 1)
        self.assertEqual(summary["skipped_rows"], 1)

    def test_sync_latest_export_keeps_existing_row_member_instead_of_recreating_old_identity(self):
        campaign = Campaign.objects.create(
            title="Campagne FFCK sync keep-link",
            status="active",
            helloasso_api_key="dummy",
            helloasso_form_slug="campagne-ffck-sync-keep-link",
        )
        kept_member = Member.objects.create(
            campaign=campaign,
            first_name="Alice",
            name="Dupont",
            email="alice@example.com",
            ffck_licence="",
        )
        ffck_export = FfckExport.objects.create(
            campaign=campaign,
            source="licences_excel",
            export_path="/extractions/licences/excel",
            export_method="POST",
            rows_count=1,
            filename="export.xlsx",
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            file_size=12,
            file_sha256="f" * 64,
            file_blob=b"xlsx",
        )
        ffck_row = FfckExportRow.objects.create(
            ffck_export=ffck_export,
            row_index=1,
            licence="000003",
            nom="Dupont Alyce",
            categorie="",
            certificat="",
            member=kept_member,
            raw_row={"nom": "Dupont", "prenom": "Alyce"},
        )

        summary = FfckMemberSyncService(campaign=campaign).sync_latest_export()

        ffck_row.refresh_from_db()
        self.assertEqual(ffck_row.member_id, kept_member.id)
        self.assertEqual(summary["created_members"], 0)
        self.assertEqual(Member.objects.filter(campaign=campaign).count(), 1)
