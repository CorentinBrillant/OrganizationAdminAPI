import { useEffect } from "react";
import { useDispatch, useSelector } from "react-redux";

import {
	loadCampaignFfckRows,
	loadCampaignMembers,
	loadCampaigns,
} from "../store/campaignsSlice";

const CAMPAIGN_STORE_KEY = "ffck:campaign";

const navItems = [
	{
		page: "dashboard",
		label: "Inscriptions",
		compact: "IN",
		compactImage: "/ckcp.png",
	},
	{
		page: "helloasso",
		label: "Source HelloAsso",
		compact: "HA",
		compactImage: "/HA.png",
	},
	{
		page: "ffck",
		label: "Source FFCK",
		compact: "FF",
		compactImage: "/ffck.jpg",
	},
	{
		page: "badges",
		label: "Source Badges",
		compact: "BA",
		compactImage: "/badges.png",
	},
	{
		page: "dedup",
		label: "Dedoublonnage",
		compact: "DD",
		compactImage: "/dedup.png",
	},
	{
		page: "settings",
		label: "Settings Campagne",
		compact: "SC",
		compactImage: "/set.jpg",
	},
	{
		page: "monitoring",
		label: "Monitoring des campagnes",
		compact: "MC",
		compactImage: "/mon.png",
	},
];

export default function Sidebar({
	activePage,
	onPageChange,
}) {
	const dispatch = useDispatch();
	const activeCampaign = useSelector((state) => state.campaigns.activeCampaign);
	const activeCampaignId = useSelector(
		(state) => state.campaigns.activeCampaignId,
	);

	useEffect(() => {
		dispatch(loadCampaigns());
	}, [dispatch]);

	useEffect(() => {
		if (!activeCampaign) return;
		localStorage.setItem(CAMPAIGN_STORE_KEY, activeCampaign);
	}, [activeCampaign]);

	useEffect(() => {
		if (!activeCampaignId) return;
		dispatch(loadCampaignMembers({ campaignId: activeCampaignId }));
		dispatch(loadCampaignFfckRows({ campaignId: activeCampaignId }));
	}, [dispatch, activeCampaignId]);

	return (
		<aside className="shared-sidebar">
			<div className="sidebar-main">
				<nav className="nav" aria-label="Navigation">
					{navItems.map((item) => (
						<button
							className={`nav-item-${item.page}${activePage === item.page ? " active" : ""}`}
							key={item.page}
							title={item.label}
							type="button"
							onClick={() => onPageChange(item.page)}
						>
							<span className="nav-compact" aria-hidden="true">
								{item.compactImage ? (
									<img
										className="nav-compact-image"
										src={item.compactImage}
										alt=""
									/>
								) : (
									item.compact
								)}
							</span>
							<span className="sidebar-expanded-label">{item.label}</span>
						</button>
					))}
				</nav>
			</div>
		</aside>
	);
}
