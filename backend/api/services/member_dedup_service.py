import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher

from django.db import transaction
from django.utils import timezone

from ..models import Campaign, FfckExportRow, HelloAssoItem, Member, MemberDuplicateSuggestion

NORMALIZE_SPACE_RE = re.compile(r"\s+")
PUNCT_RE = re.compile(r"[^a-z0-9 ]")


def _normalize_text(value: str) -> str:
    text = str(value or "").strip().lower()
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = text.replace("-", " ").replace("'", " ").replace("’", " ")
    text = PUNCT_RE.sub(" ", text)
    text = NORMALIZE_SPACE_RE.sub(" ", text).strip()
    return text


def _similarity(a: str, b: str) -> float:
    left = _normalize_text(a)
    right = _normalize_text(b)
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    return float(SequenceMatcher(None, left, right).ratio())


def _normalized_email(value: str) -> str:
    return str(value or "").strip().lower()


def _identity_score(left: Member, right: Member) -> tuple[float, list[str], int]:
    fn = _similarity(left.first_name, right.first_name)
    ln = _similarity(left.name, right.name)
    swapped_fn = _similarity(left.first_name, right.name)
    swapped_ln = _similarity(left.name, right.first_name)

    direct_name_score = (fn + ln) / 2
    swapped_name_score = (swapped_fn + swapped_ln) / 2
    name_score = max(direct_name_score, swapped_name_score)
    swapped = swapped_name_score > direct_name_score

    left_email = _normalized_email(left.email)
    right_email = _normalized_email(right.email)
    email_score = 1.0 if left_email and left_email == right_email else 0.0

    left_licence = _normalize_text(left.ffck_licence)
    right_licence = _normalize_text(right.ffck_licence)
    licence_score = 1.0 if left_licence and left_licence == right_licence else 0.0

    score = (0.9 * name_score) + (0.07 * email_score) + (0.03 * licence_score)
    score = min(1.0, max(0.0, score))

    reasons = []
    if name_score >= 0.95:
        reasons.append("nom_prenom_tres_proches")
    elif name_score >= 0.85:
        reasons.append("nom_prenom_proches")
    if swapped:
        reasons.append("inversion_nom_prenom_possible")
    if email_score == 1.0:
        reasons.append("email_identique")
    if licence_score == 1.0:
        reasons.append("licence_identique")

    left_conflict = bool(left_email and right_email and left_email != right_email)
    licence_conflict = bool(left_licence and right_licence and left_licence != right_licence)
    if left_conflict and licence_conflict and name_score < 0.97:
        return 0.0, ["conflit_email_et_licence"], left.id

    left_quality = int(bool(left.ffck_licence)) + int(bool(left.email))
    right_quality = int(bool(right.ffck_licence)) + int(bool(right.email))
    recommended_master_id = left.id if left_quality >= right_quality else right.id
    return score, reasons, recommended_master_id


@dataclass
class MemberDedupService:
    campaign: Campaign

    @transaction.atomic
    def generate_suggestions(self, min_score: float = 0.8) -> dict:
        members = list(Member.objects.filter(campaign=self.campaign).order_by("id"))
        pair_count = 0
        suggestion_ids = []

        for i in range(len(members)):
            left = members[i]
            for j in range(i + 1, len(members)):
                right = members[j]
                pair_count += 1

                score, reasons, recommended_master_id = _identity_score(left, right)
                if score < float(min_score):
                    continue

                suggestion, _created = MemberDuplicateSuggestion.objects.update_or_create(
                    campaign=self.campaign,
                    member_left=left,
                    member_right=right,
                    defaults={
                        "similarity_score": score,
                        "reasons": reasons,
                        "recommended_master_id": recommended_master_id,
                        "status": MemberDuplicateSuggestion.STATUS_PENDING,
                        "resolved_at": None,
                    },
                )
                suggestion_ids.append(suggestion.id)

        suggestions_qs = MemberDuplicateSuggestion.objects.filter(campaign=self.campaign)
        if suggestion_ids:
            suggestions_qs.exclude(id__in=suggestion_ids).update(
                status=MemberDuplicateSuggestion.STATUS_REJECTED,
                resolved_at=timezone.now(),
            )
        else:
            suggestions_qs.update(
                status=MemberDuplicateSuggestion.STATUS_REJECTED,
                resolved_at=timezone.now(),
            )

        return {
            "campaign_id": self.campaign.id,
            "evaluated_pairs": pair_count,
            "suggestions_count": len(suggestion_ids),
        }

    @transaction.atomic
    def merge_suggestion(self, suggestion: MemberDuplicateSuggestion, keep_member_id: int | None = None) -> dict:
        if suggestion.campaign_id != self.campaign.id:
            raise ValueError("Suggestion does not belong to this campaign.")
        if suggestion.status != MemberDuplicateSuggestion.STATUS_PENDING:
            raise ValueError("Suggestion is not pending.")

        left = suggestion.member_left
        right = suggestion.member_right
        if keep_member_id == left.id:
            keep = left
            drop = right
        elif keep_member_id == right.id:
            keep = right
            drop = left
        elif suggestion.recommended_master_id == right.id:
            keep = right
            drop = left
        else:
            keep = left
            drop = right

        update_fields = []
        if not keep.ffck_licence and drop.ffck_licence:
            keep.ffck_licence = drop.ffck_licence
            update_fields.append("ffck_licence")
        if not keep.email and drop.email:
            keep.email = drop.email
            update_fields.append("email")
        if not keep.certificat and drop.certificat:
            keep.certificat = drop.certificat
            update_fields.append("certificat")
        if not keep.autorisation_parentale and drop.autorisation_parentale:
            keep.autorisation_parentale = drop.autorisation_parentale
            update_fields.append("autorisation_parentale")
        if not keep.photo and drop.photo:
            keep.photo = drop.photo
            update_fields.append("photo")
        if not keep.option_ia and drop.option_ia:
            keep.option_ia = True
            update_fields.append("option_ia")
        if not keep.manual_review and drop.manual_review:
            keep.manual_review = True
            update_fields.append("manual_review")

        if update_fields:
            keep.save(update_fields=update_fields)

        helloasso_updated = HelloAssoItem.objects.filter(member=drop).update(member=keep)
        ffck_rows_updated = FfckExportRow.objects.filter(member=drop).update(member=keep)

        MemberDuplicateSuggestion.objects.filter(
            campaign=self.campaign,
            status=MemberDuplicateSuggestion.STATUS_PENDING,
        ).exclude(id=suggestion.id).filter(member_left=drop).update(
            status=MemberDuplicateSuggestion.STATUS_REJECTED,
            resolved_at=timezone.now(),
        )
        MemberDuplicateSuggestion.objects.filter(
            campaign=self.campaign,
            status=MemberDuplicateSuggestion.STATUS_PENDING,
        ).exclude(id=suggestion.id).filter(member_right=drop).update(
            status=MemberDuplicateSuggestion.STATUS_REJECTED,
            resolved_at=timezone.now(),
        )

        if suggestion.member_left_id == drop.id:
            suggestion.member_left = keep
        if suggestion.member_right_id == drop.id:
            suggestion.member_right = keep
        suggestion.status = MemberDuplicateSuggestion.STATUS_ACCEPTED
        suggestion.resolved_at = timezone.now()
        suggestion.recommended_master = keep
        suggestion.save(
            update_fields=[
                "member_left",
                "member_right",
                "status",
                "resolved_at",
                "recommended_master",
            ]
        )

        drop.delete()

        return {
            "campaign_id": self.campaign.id,
            "merged_into_member_id": keep.id,
            "deleted_member_id": drop.id,
            "helloasso_items_relinked": helloasso_updated,
            "ffck_rows_relinked": ffck_rows_updated,
        }
