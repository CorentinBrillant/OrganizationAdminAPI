import { useEffect, useState } from "react";
import { useDispatch, useSelector } from "react-redux";

import {
	createCampaign,
	loadCampaignFfckRows,
	loadCampaignMembers,
	loadCampaigns,
	setActiveCampaign,
} from "../store/campaignsSlice";

const THEME_STORE_KEY = "ffck:theme";
const CAMPAIGN_STORE_KEY = "ffck:campaign";

function formatCampaignLabel(value) {
	return /^\d{4}$/.test(value) ? `Campagne ${value}` : value;
}

const navItems = [
	{ page: "dashboard", label: "Inscriptions", compact: "IN" },
	{ page: "helloasso", label: "Source HelloAsso", compact: "HA" },
	{ page: "ffck", label: "Source FFCK", compact: "FF" },
	{ page: "badges", label: "Source Badges", compact: "BA" },
	{ page: "dedup", label: "Dedoublonnage", compact: "DD" },
	{ page: "settings", label: "Settings Campagne", compact: "SC" },
	{ page: "monitoring", label: "Monitoring des campagnes", compact: "MC" },
];

export default function Sidebar({
	activePage,
	onPageChange,
	user = null,
	onLogout = null,
}) {
	const dispatch = useDispatch();
	const campaigns = useSelector((state) => state.campaigns.items);
	const campaignCatalog = useSelector((state) => state.campaigns.catalog);
	const activeCampaign = useSelector((state) => state.campaigns.activeCampaign);
	const activeCampaignId = useSelector(
		(state) => state.campaigns.activeCampaignId,
	);

	const [theme, setTheme] = useState("dark");

	useEffect(() => {
		dispatch(loadCampaigns());

		const storedTheme = localStorage.getItem(THEME_STORE_KEY) || "dark";
		setTheme(storedTheme === "light" ? "light" : "dark");
	}, [dispatch]);

	useEffect(() => {
		const onStorage = () => {
			const nextTheme = localStorage.getItem(THEME_STORE_KEY) || "dark";
			setTheme(nextTheme === "light" ? "light" : "dark");
		};

		window.addEventListener("storage", onStorage);
		return () => window.removeEventListener("storage", onStorage);
	}, []);

	const handleAddCampaign = () => {
		const next = window.prompt("Nom de la campagne (ex: 2027)");
		const title = String(next || "").trim();
		if (!title) return;
		dispatch(createCampaign({ title }))
			.unwrap()
			.catch(() => {
				window.alert(
					"Impossible de créer la campagne. Vérifie le backend API.",
				);
			});
	};

	const toggleTheme = () => {
		const nextTheme = theme === "dark" ? "light" : "dark";
		setTheme(nextTheme);
		localStorage.setItem(THEME_STORE_KEY, nextTheme);
	};

	useEffect(() => {
		document.documentElement.style.colorScheme = theme;
	}, [theme]);

	useEffect(() => {
		if (!activeCampaign) return;
		localStorage.setItem(CAMPAIGN_STORE_KEY, activeCampaign);
	}, [activeCampaign]);

	useEffect(() => {
		if (!activeCampaignId) return;
		dispatch(loadCampaignMembers({ campaignId: activeCampaignId }));
		dispatch(loadCampaignFfckRows({ campaignId: activeCampaignId }));
	}, [dispatch, activeCampaignId]);

	const handleCampaignChange = (event) => {
		const nextCampaign = String(event.target.value || "").trim();
		dispatch(setActiveCampaign(nextCampaign));

		const selectedCampaign = campaignCatalog.find(
			(campaign) => campaign.title === nextCampaign,
		);
		const selectedCampaignId = Number(selectedCampaign?.id);
		if (Number.isFinite(selectedCampaignId)) {
			dispatch(
				loadCampaignMembers({ campaignId: selectedCampaignId, force: true }),
			);
			dispatch(
				loadCampaignFfckRows({ campaignId: selectedCampaignId, force: true }),
			);
		}
	};

	const handleLogoutClick = () => {
		if (typeof onLogout === "function") onLogout();
	};

	return (
		<aside className="shared-sidebar">
			<div className="sidebar-main">
				<div className="brand">
					<span className="brand-compact" aria-hidden="true">
						SI
					</span>
					<span className="sidebar-expanded-label">Suivi des inscriptions</span>
				</div>
				<nav className="nav" aria-label="Navigation">
					{navItems.map((item) => (
						<button
							className={activePage === item.page ? "active" : ""}
							key={item.page}
							title={item.label}
							type="button"
							onClick={() => onPageChange(item.page)}
						>
							<span className="nav-compact" aria-hidden="true">
								{item.compact}
							</span>
							<span className="sidebar-expanded-label">{item.label}</span>
						</button>
					))}
				</nav>
				<div className="campaign-switch">
					<label htmlFor="campaignSelect">Campagne</label>
					<select
						id="campaignSelect"
						className="campaign-select"
						value={activeCampaign || ""}
						onChange={handleCampaignChange}
					>
						{campaigns.map((campaign) => (
							<option key={campaign} value={campaign}>
								{formatCampaignLabel(campaign)}
							</option>
						))}
					</select>
					<div className="campaign-actions">
						<button
							className="btn-subtle"
							type="button"
							onClick={handleAddCampaign}
						>
							Nouvelle campagne
						</button>
					</div>
				</div>
				<section className="aside-tools" aria-label="Préférences utilisateur">
					<button className="theme-toggle" type="button" onClick={toggleTheme}>
						{theme === "dark"
							? "Activer le mode clair"
							: "Activer le mode sombre"}
					</button>
				</section>
			</div>

			<div className="sidebar-footer">
				<div className="identity">
					{user?.name ? (
						<>
							<strong>{user.name}</strong>
							<span>{user.role || "Connecté"}</span>
						</>
					) : (
						"Aucun utilisateur connecté"
					)}
				</div>
				<button
					className="btn-subtle"
					type="button"
					onClick={handleLogoutClick}
				>
					Se déconnecter
				</button>
			</div>
		</aside>
	);
}
