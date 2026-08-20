from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.text import slugify

from .user_action_token_service import UserActionTokenService


class UserAlreadyExistsError(Exception):
    pass


class UserNameRequiredError(Exception):
    pass


class PasswordEmailDeliveryError(Exception):
    pass


class UserService:
    @staticmethod
    def _password_url(raw_token: str) -> str:
        base_url = str(getattr(settings, "FRONTEND_URL", "")).rstrip("/")
        return f"{base_url}/set-password#{urlencode({'token': raw_token})}"

    @classmethod
    def _send_password_email(cls, user, raw_token: str, action: str, expires_at) -> None:
        url = cls._password_url(raw_token)
        expiration = timezone.localtime(expires_at).strftime("%d/%m/%Y à %H:%M")
        subject = (
            "Définissez votre mot de passe"
            if action == "set_password"
            else "Réinitialisez votre mot de passe"
        )
        body = (
            "Un lien sécurisé vous permet de choisir votre mot de passe :\n\n"
            f"{url}\n\n"
            f"Votre identifiant : {user.username}\n"
            f"Ce lien est à usage unique et expire le {expiration}."
        )
        try:
            sent = send_mail(
                subject,
                body,
                str(getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@localhost")),
                [user.email],
                fail_silently=False,
            )
        except Exception as exc:
            raise PasswordEmailDeliveryError from exc
        if sent != 1:
            raise PasswordEmailDeliveryError

    @classmethod
    def send_password_link(cls, user, action: str) -> None:
        if not user.is_active:
            raise ValueError("Cet utilisateur est désactivé.")
        with transaction.atomic():
            token, raw_token = UserActionTokenService.create(user, action)
            cls._send_password_email(user, raw_token, action, token.expires_at)

    @staticmethod
    def _username(first_name: str, last_name: str) -> str:
        base_username = f"{slugify(first_name)}.{slugify(last_name)}".strip(".")
        if not base_username or "." not in base_username:
            raise UserNameRequiredError

        User = get_user_model()
        username = base_username
        suffix = 2
        while User.objects.filter(username=username).exists():
            username = f"{base_username}.{suffix}"
            suffix += 1
        return username

    @classmethod
    def create_user(
        cls, *, email: str, first_name: str, last_name: str, send_password_email: bool = True
    ):
        User = get_user_model()
        normalized_email = email.strip().lower()
        normalized_first_name = first_name.strip()
        normalized_last_name = last_name.strip()
        existing_user = User.objects.filter(
            Q(email__iexact=normalized_email) | Q(username__iexact=normalized_email)
        ).exists()
        if existing_user:
            raise UserAlreadyExistsError
        username = cls._username(normalized_first_name, normalized_last_name)
        with transaction.atomic():
            user = User(
                username=username,
                email=normalized_email,
                first_name=normalized_first_name,
                last_name=normalized_last_name,
                is_active=True,
            )
            user.set_unusable_password()
            user.save()
            if send_password_email:
                cls.send_password_link(user, "set_password")
        return user
