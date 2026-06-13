from functools import wraps
import hashlib
import secrets

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
from django.http import JsonResponse

from .models import AuthRevokedToken

USER_TOKEN_PREFIX = "user"


def _extract_request_token(request) -> str:
    auth_header = str(request.headers.get("Authorization", "")).strip()
    if auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()
        if token:
            return token

    x_api_token = str(request.headers.get("X-API-Token", "")).strip()
    if x_api_token:
        return x_api_token

    cookie_token = str(request.COOKIES.get("api_token", "")).strip()
    if cookie_token:
        return cookie_token

    query_token = str(request.GET.get("api_token", "")).strip()
    if query_token:
        return query_token

    return ""


def _signer() -> TimestampSigner:
    salt = str(
        getattr(settings, "API_AUTH_TOKEN_SALT", "organization-admin-api-user-token")
    ).strip()
    return TimestampSigner(salt=salt)


def create_user_token(user) -> str:
    payload = f"{USER_TOKEN_PREFIX}:{user.pk}:{user.password}"
    return _signer().sign(payload)


def validate_user_token(token: str):
    if not token:
        return None

    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    if AuthRevokedToken.objects.filter(token_hash=token_hash).exists():
        return None

    ttl = int(getattr(settings, "API_AUTH_TOKEN_TTL_SECONDS", 3600))
    try:
        payload = _signer().unsign(token, max_age=ttl)
    except (BadSignature, SignatureExpired):
        return None

    parts = str(payload).split(":", 2)
    if len(parts) != 3:
        return None

    kind, raw_user_id, password_hash = parts
    if kind != USER_TOKEN_PREFIX:
        return None

    try:
        user_id = int(raw_user_id)
    except (TypeError, ValueError):
        return None

    User = get_user_model()
    user = User.objects.filter(id=user_id, is_active=True).first()
    if user is None:
        return None

    if not secrets.compare_digest(str(user.password), str(password_hash)):
        return None

    return user


def _is_static_token_valid(token: str) -> bool:
    expected = str(getattr(settings, "API_AUTH_TOKEN", "")).strip()
    if not expected or not token:
        return False
    return secrets.compare_digest(token, expected)


def revoke_token(token: str) -> None:
    if not token:
        return
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    AuthRevokedToken.objects.get_or_create(token_hash=token_hash)


def require_api_token(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not bool(getattr(settings, "API_AUTH_ENFORCED", True)):
            return view_func(request, *args, **kwargs)

        provided = _extract_request_token(request)
        if _is_static_token_valid(provided):
            request.auth_user = None
            request.auth_via = "static_token"
            request.auth_token = provided
            return view_func(request, *args, **kwargs)

        user = validate_user_token(provided)
        if user is not None:
            request.auth_user = user
            request.auth_via = "user_token"
            request.auth_token = provided
            return view_func(request, *args, **kwargs)

        return JsonResponse({"error": "Unauthorized."}, status=401)

    return _wrapped
