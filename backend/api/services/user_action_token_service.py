import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from api.models import UserActionToken


class InvalidActionTokenError(Exception):
    pass


class UserActionTokenService:
    @staticmethod
    def _hash(raw_token: str) -> str:
        return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    @classmethod
    def create(cls, user, action: str) -> tuple[UserActionToken, str]:
        raw_token = secrets.token_urlsafe(48)
        with transaction.atomic():
            locked_user = get_user_model().objects.select_for_update().get(pk=user.pk)
            now = timezone.now()
            UserActionToken.objects.filter(
                user=locked_user,
                action=action,
                used_at__isnull=True,
                invalidated_at__isnull=True,
                expires_at__gt=now,
            ).update(invalidated_at=now)
            token = UserActionToken.objects.create(
                user=locked_user,
                action=action,
                token_hash=cls._hash(raw_token),
                expires_at=now
                + timedelta(seconds=int(getattr(settings, "USER_ACTION_TOKEN_TTL_SECONDS", 86400))),
            )
        return token, raw_token

    @classmethod
    def set_password(cls, raw_token: str, password: str) -> None:
        token_hash = cls._hash(raw_token)
        with transaction.atomic():
            token = (
                UserActionToken.objects.select_for_update()
                .select_related("user")
                .filter(token_hash=token_hash)
                .first()
            )
            if (
                token is None
                or token.used_at is not None
                or token.invalidated_at is not None
                or token.expires_at <= timezone.now()
                or not token.user.is_active
            ):
                raise InvalidActionTokenError
            try:
                validate_password(password, user=token.user)
            except ValidationError:
                raise
            token.user.set_password(password)
            token.user.save(update_fields=["password"])
            token.used_at = timezone.now()
            token.save(update_fields=["used_at"])
