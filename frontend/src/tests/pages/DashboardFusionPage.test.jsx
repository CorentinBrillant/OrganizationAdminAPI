import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const {
	dispatchMock,
	loadCampaignFfckRowsMock,
	loadCampaignMembersMock,
	useDispatchMock,
	useSelectorMock,
} = vi.hoisted(() => ({
	dispatchMock: vi.fn(),
	loadCampaignFfckRowsMock: vi.fn(),
	loadCampaignMembersMock: vi.fn(),
	useDispatchMock: vi.fn(),
	useSelectorMock: vi.fn(),
}));

useDispatchMock.mockReturnValue(dispatchMock);

vi.mock("react-redux", () => ({
	useDispatch: () => useDispatchMock(),
	useSelector: (selector) => useSelectorMock(selector),
}));

vi.mock("../../auth/token", () => ({
	withApiAuthHeaders: vi.fn(() => ({})),
}));

vi.mock("../../api/campaigns", () => ({
	exportCampaignMembers: vi.fn(),
}));

vi.mock("../../api/helloasso", () => ({
	fetchHelloAssoAuthorizationStatus: vi.fn(),
	startHelloAssoAuthorization: vi.fn(),
}));

vi.mock("../../store/campaignsSlice", () => ({
	loadCampaignFfckRows: (...args) => loadCampaignFfckRowsMock(...args),
	loadCampaignMembers: (...args) => loadCampaignMembersMock(...args),
	saveCampaignMembersManualEdition: vi.fn(),
	upsertCampaignMemberPatch: vi.fn(),
}));

import DashboardFusionPage from "../../pages/DashboardFusionPage";

const members = [
	{
		id: 1,
		first_name: "Alice",
		name: "Majeure",
		ffck_licence: "LIC-ADULT",
		certificat: "https://documents.example/certificat-adulte.pdf",
		autorisation_parentale: "https://documents.example/autorisation-adulte.pdf",
		manual_review: true,
	},
	{
		id: 2,
		first_name: "Benoit",
		name: "MineurSansAutorisation",
		ffck_licence: "LIC-MINOR-MISSING",
		certificat: "https://documents.example/certificat-mineur.pdf",
		autorisation_parentale: "",
		manual_review: true,
	},
	{
		id: 3,
		first_name: "Chloe",
		name: "MineureAvecAutorisation",
		ffck_licence: "LIC-MINOR-OK",
		certificat: "https://documents.example/certificat-mineure.pdf",
		autorisation_parentale: "https://documents.example/autorisation-mineure.pdf",
		manual_review: true,
	},
	{
		id: 4,
		first_name: "David",
		name: "LicenceSansCertificat",
		ffck_licence: "LIC-NO-CERTIFICATE",
		certificat: "",
		autorisation_parentale: "",
		manual_review: false,
	},
];

const ffckRows = [
	{ member_id: 1, raw_row: { ddn: "2008-08-02" } },
	{ member_id: 2, raw_row: { ddn: "2010-01-01" } },
	{ member_id: 3, raw_row: { ddn: "2010-01-01" } },
];

function createState() {
	return {
		campaigns: {
			activeCampaign: "2026",
			activeCampaignId: 11,
			catalog: [{ id: 11, title: "2026" }],
			membersByCampaignId: { 11: members },
			ffckRowsByCampaignId: { 11: ffckRows },
			uiFiltersByPage: {
				dashboard: { search: "", status: "all", reason: "all" },
			},
		},
	};
}

function getMemberRow(name) {
	return screen
		.getAllByDisplayValue(name)
		.map((element) => element.closest("tr"))
		.find(Boolean);
}

describe("DashboardFusionPage", () => {
	beforeEach(() => {
		vi.clearAllMocks();
		vi.useFakeTimers();
		vi.setSystemTime(new Date("2026-08-02T12:00:00"));
		vi.stubGlobal(
			"ResizeObserver",
			class {
				observe() {}
				disconnect() {}
			},
		);
		useSelectorMock.mockImplementation((selector) => selector(createState()));
		dispatchMock.mockImplementation((action) => action);
		loadCampaignMembersMock.mockImplementation((payload) => ({
			type: "members/load",
			payload,
		}));
		loadCampaignFfckRowsMock.mockImplementation((payload) => ({
			type: "ffck/load",
			payload,
		}));
	});

	afterEach(() => {
		cleanup();
		vi.useRealTimers();
		vi.unstubAllGlobals();
	});

	it("applique les règles d'autorisation parentale depuis raw_row.ddn", () => {
		render(<DashboardFusionPage />);

		const adultRow = getMemberRow("Majeure");
		expect(adultRow).not.toBeNull();
		expect(within(adultRow).getByText("NA")).toBeInTheDocument();
		expect(
			within(adultRow).getByRole("button", { name: "Conforme" }),
		).toBeInTheDocument();

		const missingAuthorizationRow = getMemberRow("MineurSansAutorisation");
		expect(missingAuthorizationRow).not.toBeNull();
		expect(
			within(missingAuthorizationRow).getByRole("button", {
				name: "Bloquant",
			}),
		).toBeInTheDocument();
		expect(
			within(missingAuthorizationRow).getByText(
				"Autorisation parentale manquante",
			),
		).toBeInTheDocument();

		const authorizedMinorRow = getMemberRow("MineureAvecAutorisation");
		expect(authorizedMinorRow).not.toBeNull();
		expect(
			within(authorizedMinorRow).getByRole("button", { name: "Conforme" }),
		).toBeInTheDocument();
		expect(
			within(authorizedMinorRow).queryByText(
				"Autorisation parentale manquante",
			),
		).not.toBeInTheDocument();

		expect(loadCampaignFfckRowsMock).toHaveBeenCalledWith({ campaignId: 11 });
	});

	it("met à vérifier un certificat manquant lorsqu'un numéro de licence existe", () => {
		render(<DashboardFusionPage />);

		const memberRow = getMemberRow("LicenceSansCertificat");
		expect(memberRow).not.toBeNull();
		expect(
			within(memberRow).getByRole("button", { name: "À vérifier" }),
		).toBeInTheDocument();
		expect(
			within(memberRow).getByText("Certificat manquant"),
		).toBeInTheDocument();
	});
});
