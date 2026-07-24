import { useEffect, useMemo, useRef, useState } from "react";
import { useDispatch, useSelector } from "react-redux";

import { withApiAuthHeaders } from "../auth/token";
import {
	loadCampaignMembers,
	saveCampaignMembersManualEdition,
	upsertCampaignMemberPatch,
} from "../store/campaignsSlice";

const sourceColumns = [
	{ key: "statut", label: "Statut dossier" },
	{ key: "raison", label: "Raison" },
	{ key: "manual_review", label: "Vérification manuelle" },
	{ key: "nom", label: "Nom" },
	{ key: "prenom", label: "Prénom" },
	{ key: "licence", label: "Licence FFCK" },
	{ key: "email", label: "Email" },
	{ key: "certificat", label: "Certificat" },
	{ key: "autorisation_parentale", label: "Autorisation parentale" },
	{ key: "photo", label: "Photo" },
	{ key: "option_ia", label: "Option IA" },
	{ key: "badge_owned", label: "Badge possédé" },
	{ key: "badge_ordered", label: "Badge commandé" },
	{ key: "paiement", label: "Paiement" },
];

const statusOptions = ["Conforme", "À vérifier", "Bloquant"];

const reasonOptions = [
	{ value: "Certificat manquant", label: "Certificat manquant" },
	{ value: "Expiration certificat", label: "Expiration certificat" },
	{
		value: "Incohérence entre formulaire HelloAsso et type de licence FFCK",
		label: "Incohérence licence",
	},
	{ value: "Vérification manuelle requise", label: "Vérification manuelle" },
	{ value: "Aucune anomalie", label: "Aucune anomalie" },
];

const statusChartMeta = {
	Conforme: "ok",
	"À vérifier": "warn",
	Bloquant: "danger",
};

const lockedColumns = new Set(["statut", "raison"]);

function readCookie(name) {
	const prefix = `${name}=`;
	return (
		document.cookie
			.split(";")
			.map((part) => part.trim())
			.find((part) => part.startsWith(prefix))
			?.slice(prefix.length) || ""
	);
}

function formatDate(value) {
	const date = value ? new Date(value) : null;
	if (!date || Number.isNaN(date.getTime())) return "—";
	return new Intl.DateTimeFormat("fr-FR", {
		dateStyle: "short",
		timeStyle: "medium",
	}).format(date);
}

function normalize(value) {
	return String(value || "")
		.normalize("NFD")
		.replace(/[\u0300-\u036f]/g, "")
		.toLowerCase();
}

function hasMissingCertificate(row) {
	return !row.certificat_file_uploaded && !String(row.certificat || "").trim();
}

function getRowStatus(row) {
	if (hasMissingCertificate(row)) return "Bloquant";
	return row.manual_review === "vérifié" ? "Conforme" : "À vérifier";
}

function getRowReason(row) {
	const reasons = [];
	if (hasMissingCertificate(row)) reasons.push("Certificat manquant");

	const expiration = new Date(row.ffck_certificat_expiration);
	if (
		row.manual_review !== "vérifié" &&
		!Number.isNaN(expiration.getTime()) &&
		expiration.getFullYear() === new Date().getFullYear()
	) {
		reasons.push("Expiration certificat");
	}

	const formSlug = normalize(row.helloasso_form_slug);
	const licenceType = normalize(row.ffck_licence_type);
	if (
		row.manual_review !== "vérifié" &&
		((formSlug.includes("loisir") && licenceType.includes("competition")) ||
			(formSlug.includes("competition") && licenceType.includes("loisir")))
	) {
		reasons.push(
			"Incohérence entre formulaire HelloAsso et type de licence FFCK",
		);
	}

	if (row.manual_review !== "vérifié" && reasons.length === 0) {
		reasons.push("Vérification manuelle requise");
	}
	return reasons.length ? reasons.join(" | ") : "Aucune anomalie";
}

function memberToRow(member) {
	const certificateFile = member?.certificat_file || {};
	const row = {
		member_id: Number(member?.id),
		nom: member?.name || "—",
		prenom: member?.first_name || "—",
		licence: member?.ffck_licence || "—",
		email: member?.email || "—",
		certificat: member?.certificat || "",
		certificat_file_uploaded: Boolean(certificateFile.uploaded),
		certificat_file_name: certificateFile.filename || "",
		autorisation_parentale: member?.autorisation_parentale || "",
		photo: member?.photo || "",
		option_ia: member?.option_ia ? "Oui" : "Non",
		badge_owned: member?.badge_owned ? "Oui" : "Non",
		badge_ordered: member?.badge_ordered ? "Oui" : "Non",
		manual_review: member?.manual_review ? "vérifié" : "non vérifié",
		paiement: "—",
		ffck_licence_type: member?.ffck_licence_type || "",
		ffck_certificat_expiration: member?.ffck_certificat_expiration || "",
		helloasso_form_slug: member?.helloasso_form_slug || "",
	};
	return { ...row, statut: getRowStatus(row), raison: getRowReason(row) };
}

function rowToPatch(row) {
	const booleanValue = (value) =>
		["oui", "vérifié", "true", "1"].includes(
			String(value).trim().toLowerCase(),
		);
	const optionalLink = (value) =>
		String(value || "").trim() === "—" ? "" : String(value || "").trim();
	return {
		id: row.member_id,
		first_name: String(row.prenom || "").trim(),
		name: String(row.nom || "").trim(),
		ffck_licence: String(row.licence || "").trim(),
		email: String(row.email || "").trim(),
		certificat: optionalLink(row.certificat),
		autorisation_parentale: optionalLink(row.autorisation_parentale),
		photo: optionalLink(row.photo),
		option_ia: booleanValue(row.option_ia),
		manual_review: booleanValue(row.manual_review),
		badge_owned: booleanValue(row.badge_owned),
		badge_ordered: booleanValue(row.badge_ordered),
	};
}

function badgeClass(status) {
	if (status === "Conforme" || status === "vérifié") return "ok";
	if (status === "À vérifier" || status === "non vérifié") return "warn";
	return "danger";
}

function pieGradient(items, total) {
	if (!total) return "conic-gradient(var(--border) 0 100%)";
	let cursor = 0;
	return `conic-gradient(${items
		.filter((item) => item.count > 0)
		.map((item) => {
			const start = cursor;
			cursor += (item.count / total) * 100;
			return `var(--chart-${item.tone}) ${start}% ${cursor}%`;
		})
		.join(", ")})`;
}

function PieChartCard({
	title,
	subtitle,
	total,
	items,
	activeValue,
	allLabel,
	onSelect,
}) {
	return (
		<article className="dashboard-chart-card">
			<div className="dashboard-chart-head">
				<div>
					<span>{title}</span>
					<strong>{total}</strong>
				</div>
				<p>{subtitle}</p>
			</div>
			<div className="dashboard-chart-body">
				<div
					className="dashboard-pie"
					style={{ background: pieGradient(items, total) }}
					role="img"
					aria-label={`${title} : ${items.map((item) => `${item.label} ${item.count}`).join(", ")}`}
				>
					<span>{total}</span>
				</div>
				<div className="dashboard-chart-legend">
					<button
						type="button"
						className={activeValue === "all" ? "active" : ""}
						onClick={() => onSelect("all")}
					>
						<i className="muted" aria-hidden="true" />
						{allLabel}
					</button>
					{items.map((item) => (
						<button
							key={item.value}
							type="button"
							className={activeValue === item.value ? "active" : ""}
							onClick={() => onSelect(item.value)}
						>
							<i className={item.tone} aria-hidden="true" />
							<span>{item.label}</span>
							<strong>{item.count}</strong>
						</button>
					))}
				</div>
			</div>
		</article>
	);
}

export default function DashboardFusionPage() {
	const dispatch = useDispatch();
	const fileInputRef = useRef(null);
	const tableScrollTopRef = useRef(null);
	const tableWrapRef = useRef(null);
	const tableRef = useRef(null);
	const [tableWidth, setTableWidth] = useState(0);
	const activeCampaignId = useSelector(
		(state) => state.campaigns.activeCampaignId,
	);
	const activeCampaign = useSelector((state) => state.campaigns.activeCampaign);
	const catalog = useSelector((state) => state.campaigns.catalog);
	const members = useSelector(
		(state) => state.campaigns.membersByCampaignId[activeCampaignId] || [],
	);
	const filters = useSelector(
		(state) => state.campaigns.uiFiltersByPage.dashboard,
	);

	const [columns, setColumns] = useState(sourceColumns);
	const [search, setSearch] = useState(filters.search || "");
	const [statusFilter, setStatusFilter] = useState(filters.status || "all");
	const [reasonFilter, setReasonFilter] = useState(filters.reason || "all");
	const [ascending, setAscending] = useState(true);
	const [selectedIds, setSelectedIds] = useState(new Set());
	const [edits, setEdits] = useState({});
	const [selectedMemberId, setSelectedMemberId] = useState(null);
	const [pendingCertificateMemberId, setPendingCertificateMemberId] =
		useState(null);
	const [busyAction, setBusyAction] = useState("");
	const [message, setMessage] = useState("");

	const activeCatalogItem = catalog.find(
		(campaign) => Number(campaign.id) === Number(activeCampaignId),
	);
	const rows = useMemo(
		() =>
			members
				.map(memberToRow)
				.map((row) => ({ ...row, ...(edits[row.member_id] || {}) })),
		[members, edits],
	);

	const visibleRows = useMemo(() => {
		const query = search.trim().toLowerCase();
		return rows
			.map((row) => ({
				...row,
				statut: getRowStatus(row),
				raison: getRowReason(row),
			}))
			.filter((row) => {
				const matchesSearch =
					!query || Object.values(row).join(" ").toLowerCase().includes(query);
				return (
					matchesSearch &&
					(statusFilter === "all" || row.statut === statusFilter) &&
					(reasonFilter === "all" || row.raison.includes(reasonFilter))
				);
			})
			.sort(
				(left, right) =>
					(ascending ? 1 : -1) * left.nom.localeCompare(right.nom, "fr"),
			);
	}, [ascending, reasonFilter, rows, search, statusFilter]);

	const kpis = useMemo(
		() => ({
			merged: rows.length,
		}),
		[rows],
	);

	const statusChartItems = useMemo(
		() =>
			statusOptions.map((status) => ({
				value: status,
				label: status,
				count: rows.filter((row) => getRowStatus(row) === status).length,
				tone: statusChartMeta[status],
			})),
		[rows],
	);

	const reasonChartItems = useMemo(
		() =>
			reasonOptions.map((reason, index) => ({
				value: reason.value,
				label: reason.label,
				count: rows.filter((row) => getRowReason(row).includes(reason.value))
					.length,
				tone: `reason-${index + 1}`,
			})),
		[rows],
	);

	const reasonChartTotal = reasonChartItems.reduce(
		(total, item) => total + item.count,
		0,
	);

	const selectedRow = useMemo(() => {
		if (!visibleRows.length) return null;
		return (
			visibleRows.find((row) => row.member_id === selectedMemberId) ||
			visibleRows[0]
		);
	}, [selectedMemberId, visibleRows]);

	const editedCount = Object.keys(edits).length;

	useEffect(() => {
		if (Number.isFinite(Number(activeCampaignId))) {
			dispatch(loadCampaignMembers({ campaignId: activeCampaignId }));
		}
		setEdits({});
		setSelectedIds(new Set());
		setSelectedMemberId(null);
	}, [activeCampaignId, dispatch]);

	useEffect(() => {
		setSearch(filters.search || "");
		setStatusFilter(filters.status || "all");
		setReasonFilter(filters.reason || "all");
	}, [filters]);

	useEffect(() => {
		const table = tableRef.current;
		const tableWrap = tableWrapRef.current;
		if (!table || !tableWrap) return undefined;

		const updateScrollWidth = () => setTableWidth(table.scrollWidth);
		const observer = new ResizeObserver(updateScrollWidth);
		observer.observe(table);
		observer.observe(tableWrap);
		updateScrollWidth();

		return () => observer.disconnect();
	}, []);

	const syncHorizontalScroll = (source) => {
		const topScroll = tableScrollTopRef.current;
		const tableWrap = tableWrapRef.current;
		if (!topScroll || !tableWrap) return;
		if (source === "top") tableWrap.scrollLeft = topScroll.scrollLeft;
		else topScroll.scrollLeft = tableWrap.scrollLeft;
	};

	const updateFilters = (next) => {
		dispatch({
			type: "campaigns/setPageFilters",
			payload: { page: "dashboard", filters: next },
		});
	};

	const updateEdit = (memberId, key, value) => {
		setEdits((current) => ({
			...current,
			[memberId]: { ...(current[memberId] || {}), [key]: value },
		}));
	};

	const saveEdits = async () => {
		const changedRows = rows.filter((row) => edits[row.member_id]);
		if (!changedRows.length || !Number.isFinite(Number(activeCampaignId)))
			return;
		setBusyAction("save");
		try {
			await dispatch(
				saveCampaignMembersManualEdition({
					campaignId: activeCampaignId,
					members: changedRows.map(rowToPatch),
				}),
			).unwrap();
			changedRows.forEach((row) => {
				dispatch(
					upsertCampaignMemberPatch({
						campaignId: activeCampaignId,
						member: rowToPatch(row),
					}),
				);
			});
			setEdits({});
			setMessage("Modifications enregistrées.");
		} catch (error) {
			setMessage(
				error?.message || "Impossible d’enregistrer les modifications.",
			);
		} finally {
			setBusyAction("");
		}
	};

	const runFusion = async () => {
		if (!Number.isFinite(Number(activeCampaignId))) return;
		setBusyAction("fusion");
		setMessage("");
		try {
			const query = `?campaignId=${encodeURIComponent(String(activeCampaignId))}`;
			let response = await fetch(`/api/campaigns/sync-members/${query}`, {
				headers: withApiAuthHeaders(),
			});
			if (response.status === 404) {
				const helloAsso = await fetch(`/api/helloasso/sync-members/${query}`, {
					headers: withApiAuthHeaders(),
				});
				if (!helloAsso.ok) throw new Error(`HTTP ${helloAsso.status}`);
				response = await fetch(`/api/ffck/sync-members/${query}`, {
					headers: withApiAuthHeaders(),
				});
			}
			if (!response.ok) throw new Error(`HTTP ${response.status}`);
			await dispatch(
				loadCampaignMembers({ campaignId: activeCampaignId, force: true }),
			).unwrap();
			setMessage("Fusion terminée.");
		} catch (error) {
			setMessage(error?.message || "La fusion a échoué.");
		} finally {
			setBusyAction("");
		}
	};

	const createMember = async () => {
		const firstName = window.prompt("Prénom du nouveau membre ?");
		const name = firstName && window.prompt("Nom du nouveau membre ?");
		const email = name && window.prompt("Email du nouveau membre ?");
		if (
			!firstName ||
			!name ||
			!email ||
			!Number.isFinite(Number(activeCampaignId))
		)
			return;
		setBusyAction("create");
		try {
			const csrfToken = readCookie("csrftoken");
			const headers = withApiAuthHeaders({
				"Content-Type": "application/json",
			});
			if (csrfToken) headers["X-CSRFToken"] = decodeURIComponent(csrfToken);
			const response = await fetch(
				`/api/campaigns/${activeCampaignId}/members/`,
				{
					method: "POST",
					headers,
					body: JSON.stringify({
						first_name: firstName.trim(),
						name: name.trim(),
						email: email.trim(),
					}),
				},
			);
			if (!response.ok) throw new Error(`HTTP ${response.status}`);
			await dispatch(
				loadCampaignMembers({ campaignId: activeCampaignId, force: true }),
			).unwrap();
		} catch (error) {
			setMessage(error?.message || "Impossible de créer le membre.");
		} finally {
			setBusyAction("");
		}
	};

	const deleteSelected = async () => {
		if (!selectedIds.size || !Number.isFinite(Number(activeCampaignId))) return;
		if (
			!window.confirm(
				`Supprimer ${selectedIds.size} membre(s) de la campagne « ${activeCampaign} » ?`,
			)
		)
			return;
		setBusyAction("delete");
		try {
			const csrfToken = readCookie("csrftoken");
			const headers = withApiAuthHeaders({
				"Content-Type": "application/json",
			});
			if (csrfToken) headers["X-CSRFToken"] = decodeURIComponent(csrfToken);
			const response = await fetch(
				`/api/campaigns/${activeCampaignId}/members/bulk-delete/`,
				{
					method: "POST",
					headers,
					body: JSON.stringify({ member_ids: [...selectedIds] }),
				},
			);
			if (!response.ok) throw new Error(`HTTP ${response.status}`);
			setSelectedIds(new Set());
			await dispatch(
				loadCampaignMembers({ campaignId: activeCampaignId, force: true }),
			).unwrap();
		} catch (error) {
			setMessage(error?.message || "Impossible de supprimer la sélection.");
		} finally {
			setBusyAction("");
		}
	};

	const uploadCertificate = async (event) => {
		const file = event.target.files?.[0];
		const memberId = pendingCertificateMemberId;
		setPendingCertificateMemberId(null);
		event.target.value = "";
		if (
			!file ||
			!Number.isFinite(Number(memberId)) ||
			!Number.isFinite(Number(activeCampaignId))
		)
			return;
		setBusyAction(`upload-${memberId}`);
		try {
			const csrfToken = readCookie("csrftoken");
			const headers = withApiAuthHeaders();
			if (csrfToken) headers["X-CSRFToken"] = decodeURIComponent(csrfToken);
			const form = new FormData();
			form.append("file", file);
			const response = await fetch(
				`/api/campaigns/${activeCampaignId}/members/${memberId}/certificat-file/`,
				{
					method: "POST",
					headers,
					body: form,
				},
			);
			if (!response.ok) throw new Error(`HTTP ${response.status}`);
			await dispatch(
				loadCampaignMembers({ campaignId: activeCampaignId, force: true }),
			).unwrap();
		} catch (error) {
			setMessage(error?.message || "Upload du certificat impossible.");
		} finally {
			setBusyAction("");
		}
	};

	const moveColumn = (index, direction) => {
		setColumns((current) => {
			const target = index + direction;
			if (target < 0 || target >= current.length) return current;
			const next = [...current];
			[next[index], next[target]] = [next[target], next[index]];
			return next;
		});
	};

	const allVisibleSelected =
		visibleRows.length > 0 &&
		visibleRows.every((row) => selectedIds.has(row.member_id));

	const setStatus = (nextStatus) => {
		setStatusFilter(nextStatus);
		updateFilters({ status: nextStatus });
	};

	const setReason = (nextReason) => {
		setReasonFilter(nextReason);
		updateFilters({ reason: nextReason });
	};

	const renderCertificateControl = (row) => {
		if (row.certificat) {
			return (
				<a href={row.certificat} target="_blank" rel="noreferrer">
					Ouvrir
				</a>
			);
		}
		if (row.certificat_file_uploaded) {
			return (
				<a
					href={`/api/campaigns/${activeCampaignId}/members/${row.member_id}/certificat-file/download/`}
					target="_blank"
					rel="noreferrer"
				>
					Télécharger {row.certificat_file_name || "le fichier"}
				</a>
			);
		}
		return (
			<button
				type="button"
				className="btn-subtle"
				disabled={busyAction === `upload-${row.member_id}`}
				onClick={() => {
					setPendingCertificateMemberId(row.member_id);
					fileInputRef.current?.click();
				}}
			>
				Uploader
			</button>
		);
	};

	const renderRowField = (row, column) => {
		const value = row[column.key] ?? "";
		if (column.key === "statut" || column.key === "manual_review") {
			return (
				<td key={column.key}>
					<button
						type="button"
						className={`dashboard-badge ${badgeClass(value)}`}
						onClick={() =>
							column.key === "manual_review" &&
							updateEdit(
								row.member_id,
								"manual_review",
								value === "vérifié" ? "non vérifié" : "vérifié",
							)
						}
					>
						{value}
					</button>
				</td>
			);
		}
		if (column.key === "certificat")
			return <td key={column.key}>{renderCertificateControl(row)}</td>;
		if (
			["autorisation_parentale", "photo"].includes(column.key) &&
			/^https?:\/\//i.test(value)
		) {
			return (
				<td key={column.key}>
					<a href={value} target="_blank" rel="noreferrer">
						Ouvrir
					</a>
				</td>
			);
		}
		if (lockedColumns.has(column.key)) return <td key={column.key}>{value}</td>;
		return (
			<td key={column.key}>
				<input
					aria-label={`${column.label} pour ${row.prenom} ${row.nom}`}
					value={value}
					onChange={(event) =>
						updateEdit(row.member_id, column.key, event.target.value)
					}
				/>
			</td>
		);
	};

	return (
		<section className="dashboard-fusion">
			<header className="dashboard-hero">
				<div>
					<p className="dashboard-eyebrow">Campagne active</p>
					<h1>Consolidation des membres</h1>
					<p className="dashboard-lead">
						Contrôlez les lignes issues de HelloAsso, FFCK et badges, corrigez
						les écarts, puis relancez la fusion sans quitter la liste.
					</p>
					<div className="dashboard-meta">
						<span>
							Dernière fusion : {formatDate(activeCatalogItem?.last_merge)}
						</span>
						<span>
							Dernière modification :{" "}
							{formatDate(activeCatalogItem?.last_manual_edition)}
						</span>
					</div>
				</div>
				<div className="dashboard-primary-actions">
					<article className="dashboard-total-card dashboard-hero-stat">
						<span>Lignes</span>
						<strong>{kpis.merged}</strong>
						<small>membres consolidés</small>
					</article>
					{editedCount > 0 && (
						<button
							type="button"
							disabled={busyAction === "save"}
							onClick={saveEdits}
						>
							Sauvegarder {editedCount}
						</button>
					)}
					<button
						type="button"
						disabled={busyAction === "fusion"}
						onClick={runFusion}
					>
						{busyAction === "fusion"
							? "Fusion en cours..."
							: "Lancer la fusion"}
					</button>
					<button
						type="button"
						className="btn-subtle"
						disabled={busyAction === "refresh"}
						onClick={async () => {
							setBusyAction("refresh");
							await dispatch(
								loadCampaignMembers({
									campaignId: activeCampaignId,
									force: true,
								}),
							);
							setBusyAction("");
						}}
					>
						Rafraîchir
					</button>
				</div>
			</header>

			<section className="dashboard-workbar" aria-label="Pilotage de la liste">
				<div className="dashboard-kpis">
					<PieChartCard
						title="Statuts"
						subtitle="Répartition des dossiers de la campagne."
						total={kpis.merged}
						items={statusChartItems}
						activeValue={statusFilter}
						allLabel="Tous les statuts"
						onSelect={setStatus}
					/>
					<PieChartCard
						title="Raisons"
						subtitle="Anomalies ou absence d’anomalie détectées."
						total={reasonChartTotal}
						items={reasonChartItems}
						activeValue={reasonFilter}
						allLabel="Toutes les raisons"
						onSelect={setReason}
					/>
				</div>

				<div className="dashboard-filters">
					<label className="dashboard-search">
						<span>Recherche</span>
						<input
							value={search}
							type="search"
							placeholder="Nom, email, licence..."
							onChange={(event) => {
								setSearch(event.target.value);
								updateFilters({ search: event.target.value });
							}}
						/>
					</label>
				</div>
			</section>

			<div className="dashboard-layout">
				<section
					className="dashboard-panel dashboard-table-card"
					aria-label="Tableau consolidé"
				>
					<header className="dashboard-panel-head">
						<div>
							<p className="dashboard-eyebrow">File de contrôle</p>
							<h2>
								{visibleRows.length} membre{visibleRows.length > 1 ? "s" : ""}{" "}
								affiché{visibleRows.length > 1 ? "s" : ""}
							</h2>
							<p>
								{selectedIds.size} sélectionné{selectedIds.size > 1 ? "s" : ""}{" "}
								· {editedCount} ligne{editedCount > 1 ? "s" : ""} modifiée
								{editedCount > 1 ? "s" : ""}
							</p>
						</div>
						<div className="dashboard-controls">
							<button
								type="button"
								className="btn-subtle"
								onClick={() => setAscending((value) => !value)}
								title="Trier par nom"
							>
								{ascending ? "A-Z" : "Z-A"}
							</button>
							<button
								type="button"
								className="btn-subtle"
								disabled={!selectedIds.size || busyAction === "delete"}
								onClick={deleteSelected}
								title="Supprimer la sélection"
							>
								Supprimer
							</button>
							<button
								type="button"
								className="btn-subtle"
								disabled={busyAction === "create"}
								onClick={createMember}
								title="Créer un membre"
							>
								Créer
							</button>
						</div>
						<p className="dashboard-hint">
							Déplacez ou masquez les colonnes depuis l’en-tête. Cliquez une
							cellule pour corriger la donnée source consolidée.
						</p>
						{message && (
							<p className="dashboard-message" role="status">
								{message}
							</p>
						)}
					</header>

					<div
						ref={tableScrollTopRef}
						className="dashboard-table-scroll-top"
						aria-hidden="true"
						onScroll={() => syncHorizontalScroll("top")}
					>
						<div style={{ width: tableWidth }} />
					</div>
					<div
						ref={tableWrapRef}
						className="dashboard-table-wrap"
						onScroll={() => syncHorizontalScroll("table")}
					>
						<table ref={tableRef}>
							<thead>
								<tr>
									<th>
										<input
											type="checkbox"
											aria-label="Sélectionner tous les membres visibles"
											checked={allVisibleSelected}
											onChange={(event) => {
												setSelectedIds((current) => {
													const next = new Set(current);
													visibleRows.forEach((row) => {
														if (event.target.checked) next.add(row.member_id);
														else next.delete(row.member_id);
													});
													return next;
												});
											}}
										/>
									</th>
									{columns.map((column, index) => (
										<th key={column.key}>
											<div className="dashboard-column-head">
												<span>{column.label}</span>
												<span>
													<button
														type="button"
														disabled={index === 0}
														onClick={() => moveColumn(index, -1)}
													>
														←
													</button>
													<button
														type="button"
														disabled={index === columns.length - 1}
														onClick={() => moveColumn(index, 1)}
													>
														→
													</button>
													<button
														type="button"
														disabled={columns.length === 1}
														onClick={() =>
															setColumns((current) =>
																current.filter(
																	(item) => item.key !== column.key,
																),
															)
														}
													>
														×
													</button>
												</span>
											</div>
										</th>
									))}
								</tr>
							</thead>
							<tbody>
								{visibleRows.map((row) => (
									<tr
										key={row.member_id}
										className={
											selectedRow?.member_id === row.member_id
												? "is-focused"
												: ""
										}
										onClick={() => setSelectedMemberId(row.member_id)}
									>
										<td>
											<input
												type="checkbox"
												aria-label={`Sélectionner ${row.prenom} ${row.nom}`}
												checked={selectedIds.has(row.member_id)}
												onChange={(event) =>
													setSelectedIds((current) => {
														const next = new Set(current);
														if (event.target.checked) next.add(row.member_id);
														else next.delete(row.member_id);
														return next;
													})
												}
											/>
										</td>
										{columns.map((column) => renderRowField(row, column))}
									</tr>
								))}
							</tbody>
						</table>
					</div>

					<ul
						className="dashboard-mobile-list"
						aria-label="Liste mobile des membres"
					>
						{visibleRows.map((row) => (
							<li key={row.member_id} className="dashboard-member-card">
								<header>
									<input
										type="checkbox"
										aria-label={`Sélectionner ${row.prenom} ${row.nom}`}
										checked={selectedIds.has(row.member_id)}
										onChange={(event) =>
											setSelectedIds((current) => {
												const next = new Set(current);
												if (event.target.checked) next.add(row.member_id);
												else next.delete(row.member_id);
												return next;
											})
										}
									/>
									<div>
										<strong>
											{row.prenom} {row.nom}
										</strong>
										<span>{row.email}</span>
									</div>
									<button
										type="button"
										className={`dashboard-badge ${badgeClass(row.statut)}`}
										onClick={() => setSelectedMemberId(row.member_id)}
									>
										{row.statut}
									</button>
								</header>
								<dl>
									<div>
										<dt>Licence</dt>
										<dd>{row.licence}</dd>
									</div>
									<div>
										<dt>Raison</dt>
										<dd>{row.raison}</dd>
									</div>
									<div>
										<dt>Certificat</dt>
										<dd>{renderCertificateControl(row)}</dd>
									</div>
									<div>
										<dt>Badge</dt>
										<dd>
											Possédé {row.badge_owned} · Commandé {row.badge_ordered}
										</dd>
									</div>
								</dl>
								<button
									type="button"
									className="btn-subtle"
									onClick={() =>
										updateEdit(
											row.member_id,
											"manual_review",
											row.manual_review === "vérifié"
												? "non vérifié"
												: "vérifié",
										)
									}
								>
									Marquer{" "}
									{row.manual_review === "vérifié" ? "non vérifié" : "vérifié"}
								</button>
							</li>
						))}
					</ul>
				</section>

				<aside
					className="dashboard-detail-panel"
					aria-label="Détail membre sélectionné"
				>
					{selectedRow ? (
						<>
							<p className="dashboard-eyebrow">Dossier membre</p>
							<h2>
								{selectedRow.prenom} {selectedRow.nom}
							</h2>
							<button
								type="button"
								className={`dashboard-badge ${badgeClass(selectedRow.statut)}`}
							>
								{selectedRow.statut}
							</button>
							<div className="dashboard-detail-grid">
								<span>Email</span>
								<strong>{selectedRow.email}</strong>
								<span>Licence FFCK</span>
								<strong>{selectedRow.licence}</strong>
								<span>Type licence</span>
								<strong>{selectedRow.ffck_licence_type || "—"}</strong>
								<span>Formulaire HelloAsso</span>
								<strong>{selectedRow.helloasso_form_slug || "—"}</strong>
								<span>Certificat</span>
								<strong>{renderCertificateControl(selectedRow)}</strong>
							</div>
							<section className="dashboard-review-box">
								<h3>Contrôle à effectuer</h3>
								<p>{selectedRow.raison}</p>
								<button
									type="button"
									onClick={() =>
										updateEdit(
											selectedRow.member_id,
											"manual_review",
											selectedRow.manual_review === "vérifié"
												? "non vérifié"
												: "vérifié",
										)
									}
								>
									{selectedRow.manual_review === "vérifié"
										? "Retirer la vérification"
										: "Marquer comme vérifié"}
								</button>
							</section>
							<section className="dashboard-source-stack">
								<h3>Sources consolidées</h3>
								<article>
									<span>HelloAsso</span>
									<strong>
										{selectedRow.helloasso_form_slug ||
											"Formulaire non renseigné"}
									</strong>
								</article>
								<article>
									<span>FFCK</span>
									<strong>
										{selectedRow.ffck_licence_type || "Licence non qualifiée"}
									</strong>
								</article>
								<article>
									<span>Badges</span>
									<strong>
										Possédé {selectedRow.badge_owned} · Commandé{" "}
										{selectedRow.badge_ordered}
									</strong>
								</article>
							</section>
						</>
					) : (
						<p className="dashboard-empty">
							Aucun membre ne correspond aux filtres actuels.
						</p>
					)}
				</aside>
			</div>
			<input
				ref={fileInputRef}
				hidden
				type="file"
				accept=".pdf,.jpg,.jpeg,.png"
				onChange={uploadCertificate}
			/>
		</section>
	);
}
