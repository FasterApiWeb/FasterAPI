"""JWT bearer authentication and OAuth2-style access token helpers (optional ``PyJWT``)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Any

from .exceptions import HTTPException
from .request import Request
from .security import OAuth2PasswordRequestForm

__all__ = [
    "JWTBearer",
    "create_access_token",
    "oauth2_access_token_json",
    "oauth2_password_token_response",
]


def _jwt_module() -> Any:
    try:
        import jwt
    except ImportError as exc:
        raise ImportError("PyJWT is required. Install with: pip install PyJWT") from exc
    return jwt


def create_access_token(
    subject: str | dict[str, Any],
    secret: str,
    *,
    algorithm: str = "HS256",
    expires_delta: timedelta | None = None,
    expires_minutes: int = 60,
    audience: str | None = None,
    issuer: str | None = None,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """Create a signed JWT string (``sub`` claim from *subject* or merge *subject* dict)."""
    from datetime import datetime, timezone

    jwt = _jwt_module()
    now = datetime.now(timezone.utc)
    exp = now + (expires_delta or timedelta(minutes=expires_minutes))

    if isinstance(subject, str):
        payload: dict[str, Any] = {"sub": subject}
    else:
        payload = dict(subject)
    payload["exp"] = exp
    payload.setdefault("iat", now)
    if audience is not None:
        payload["aud"] = audience
    if issuer is not None:
        payload["iss"] = issuer
    if extra_claims:
        payload.update(extra_claims)

    return jwt.encode(payload, secret, algorithm=algorithm)


def oauth2_access_token_json(
    access_token: str,
    *,
    token_type: str = "bearer",
    expires_in: int | None = None,
) -> dict[str, str | int]:
    """JSON body shape for ``POST /token`` OAuth2 password / client responses (RFC 6749 §5.1)."""
    body: dict[str, str | int] = {"access_token": access_token, "token_type": token_type}
    if expires_in is not None:
        body["expires_in"] = expires_in
    return body


async def oauth2_password_token_response(
    form: OAuth2PasswordRequestForm,
    *,
    secret: str,
    authenticate: Callable[[str, str], Awaitable[str | None]],
    expires_minutes: int = 60,
) -> dict[str, str | int]:
    """Validate credentials via *authenticate* and return an OAuth2-style token JSON dict.

    Typical handler::

        @app.post(\"/token\")
        async def token(form: OAuth2PasswordRequestForm = Depends(OAuth2PasswordRequestForm)):
            return await oauth2_password_token_response(form, secret=SECRET, authenticate=verify_user)

    *authenticate* should return a subject string (e.g. user id) or ``None`` if invalid.
    """
    uid = await authenticate(form.username, form.password)
    if uid is None:
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    token = create_access_token(uid, secret, expires_minutes=expires_minutes)
    return oauth2_access_token_json(token, expires_in=expires_minutes * 60)


class JWTBearer:
    """Decode a Bearer JWT from ``Authorization`` and inject claims as a ``dict``.

    Usage::

        jwt_scheme = JWTBearer(secret=settings.jwt_secret)

        @app.get(\"/me\")
        async def me(claims: dict = Depends(jwt_scheme)):
            user_id = claims.get(\"sub\")
    """

    __slots__ = ("secret", "public_key", "algorithms", "audience", "issuer", "auto_error", "scheme_name")

    def __init__(
        self,
        secret: str | None = None,
        *,
        algorithms: list[str] | None = None,
        audience: str | None = None,
        issuer: str | None = None,
        auto_error: bool = True,
        scheme_name: str | None = None,
        public_key: str | None = None,
    ) -> None:
        if secret is None and public_key is None:
            raise ValueError("JWTBearer requires secret (HMAC) or public_key (asymmetric)")
        if secret is not None and public_key is not None:
            raise ValueError("Provide either secret or public_key, not both")
        self.secret = secret
        self.public_key = public_key
        self.algorithms = algorithms or ["HS256"]
        self.audience = audience
        self.issuer = issuer
        self.auto_error = auto_error
        self.scheme_name = scheme_name or self.__class__.__name__

    async def __call__(self, request: Request) -> dict[str, Any] | None:
        authorization = request.headers.get("authorization", "")
        if not authorization.startswith("Bearer "):
            if self.auto_error:
                raise HTTPException(
                    status_code=401,
                    detail="Not authenticated",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            return None

        token = authorization[7:]
        jwt_mod = _jwt_module()
        key = self.secret if self.public_key is None else self.public_key
        try:
            return jwt_mod.decode(
                token,
                key,
                algorithms=self.algorithms,
                audience=self.audience,
                issuer=self.issuer,
                options={"require": ["exp"]},
            )
        except getattr(getattr(jwt_mod, "exceptions", jwt_mod), "InvalidTokenError", Exception) as exc:
            if self.auto_error:
                raise HTTPException(
                    status_code=401,
                    detail="Could not validate credentials",
                    headers={"WWW-Authenticate": "Bearer"},
                ) from exc
            return None
