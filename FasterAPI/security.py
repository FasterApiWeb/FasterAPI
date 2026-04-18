"""Security utilities for FasterAPI — OAuth2, HTTP Basic, and API key authentication."""

from __future__ import annotations

import base64
import binascii
from typing import Any

from .exceptions import HTTPException
from .request import Request

__all__ = [
    "SecurityScopes",
    "OAuth2PasswordBearer",
    "OAuth2PasswordRequestForm",
    "HTTPBasicCredentials",
    "HTTPBasic",
    "APIKeyHeader",
    "APIKeyQuery",
    "APIKeyCookie",
]


class SecurityScopes:
    """Holds the list of OAuth2 security scopes required by a dependency tree."""

    __slots__ = ("scopes", "scope_str")

    def __init__(self, scopes: list[str] | None = None) -> None:
        self.scopes: list[str] = scopes or []
        self.scope_str: str = " ".join(self.scopes)

    def __repr__(self) -> str:
        return f"SecurityScopes(scopes={self.scopes!r})"


class OAuth2PasswordBearer:
    """Extracts a Bearer token from the Authorization header.

    Use as a dependency:

        oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/token")

        @app.get("/me")
        async def me(token: str = Depends(oauth2_scheme)):
            ...
    """

    __slots__ = ("tokenUrl", "scheme_name", "scopes", "auto_error")

    def __init__(
        self,
        tokenUrl: str,
        *,
        scheme_name: str | None = None,
        scopes: dict[str, str] | None = None,
        auto_error: bool = True,
    ) -> None:
        self.tokenUrl = tokenUrl
        self.scheme_name = scheme_name or self.__class__.__name__
        self.scopes: dict[str, str] = scopes or {}
        self.auto_error = auto_error

    async def __call__(self, request: Request) -> str | None:
        authorization = request.headers.get("authorization", "")
        if not authorization.startswith("Bearer "):
            if self.auto_error:
                raise HTTPException(
                    status_code=401,
                    detail="Not authenticated",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            return None
        return authorization[7:]


class OAuth2PasswordRequestForm:
    """Parses an OAuth2 password flow form submission.

    Use as a dependency:

        @app.post("/token")
        async def login(form: OAuth2PasswordRequestForm = Depends()):
            form.username, form.password, form.scopes
    """

    __slots__ = ("grant_type", "username", "password", "scopes", "client_id", "client_secret")

    def __init__(
        self,
        *,
        grant_type: str | None = None,
        username: str = "",
        password: str = "",
        scope: str = "",
        client_id: str | None = None,
        client_secret: str | None = None,
    ) -> None:
        self.grant_type = grant_type
        self.username = username
        self.password = password
        self.scopes: list[str] = scope.split() if scope else []
        self.client_id = client_id
        self.client_secret = client_secret

    @classmethod
    async def from_request(cls, request: Request) -> OAuth2PasswordRequestForm:
        """Parse form data from a request and return a populated instance."""
        form_data = await request.form()
        return cls(
            grant_type=str(form_data.get("grant_type")) if form_data.get("grant_type") is not None else None,
            username=str(form_data.get("username", "")),
            password=str(form_data.get("password", "")),
            scope=str(form_data.get("scope", "")),
            client_id=str(form_data.get("client_id")) if form_data.get("client_id") is not None else None,
            client_secret=str(form_data.get("client_secret")) if form_data.get("client_secret") is not None else None,
        )


class HTTPBasicCredentials:
    """Username and password extracted from an HTTP Basic Authorization header."""

    __slots__ = ("username", "password")

    def __init__(self, username: str, password: str) -> None:
        self.username = username
        self.password = password

    def __repr__(self) -> str:
        return f"HTTPBasicCredentials(username={self.username!r})"


class HTTPBasic:
    """Extracts credentials from an HTTP Basic Authorization header.

    Use as a dependency:

        http_basic = HTTPBasic()

        @app.get("/protected")
        async def protected(creds: HTTPBasicCredentials = Depends(http_basic)):
            ...
    """

    __slots__ = ("scheme_name", "realm", "auto_error")

    def __init__(
        self,
        *,
        scheme_name: str | None = None,
        realm: str | None = None,
        auto_error: bool = True,
    ) -> None:
        self.scheme_name = scheme_name or self.__class__.__name__
        self.realm = realm
        self.auto_error = auto_error

    async def __call__(self, request: Request) -> HTTPBasicCredentials | None:
        authorization = request.headers.get("authorization", "")
        if not authorization.startswith("Basic "):
            if self.auto_error:
                www_auth = f'Basic realm="{self.realm}"' if self.realm else "Basic"
                raise HTTPException(
                    status_code=401,
                    detail="Not authenticated",
                    headers={"WWW-Authenticate": www_auth},
                )
            return None
        try:
            decoded = base64.b64decode(authorization[6:]).decode("latin-1")
            username, _, password = decoded.partition(":")
        except (binascii.Error, UnicodeDecodeError) as exc:
            if self.auto_error:
                raise HTTPException(status_code=400, detail="Invalid authentication credentials") from exc
            return None
        return HTTPBasicCredentials(username=username, password=password)


class _APIKeyBase:
    """Shared base for API key security schemes."""

    __slots__ = ("name", "scheme_name", "auto_error")

    def __init__(self, name: str, *, scheme_name: str | None = None, auto_error: bool = True) -> None:
        self.name = name
        self.scheme_name = scheme_name or self.__class__.__name__
        self.auto_error = auto_error

    def _deny(self) -> None:
        if self.auto_error:
            raise HTTPException(status_code=403, detail="Not authenticated")

    async def __call__(self, request: Request) -> Any:
        raise NotImplementedError


class APIKeyHeader(_APIKeyBase):
    """API key extracted from an HTTP request header.

    api_key_header = APIKeyHeader(name="X-API-Key")

    @app.get("/secure")
    async def secure(key: str = Depends(api_key_header)):
        ...
    """

    async def __call__(self, request: Request) -> str | None:
        key = request.headers.get(self.name.lower())
        if key is None:
            self._deny()
            return None
        return key


class APIKeyQuery(_APIKeyBase):
    """API key extracted from a query parameter.

    api_key_query = APIKeyQuery(name="api_key")

    @app.get("/secure")
    async def secure(key: str = Depends(api_key_query)):
        ...
    """

    async def __call__(self, request: Request) -> str | None:
        raw = request.query_params.get(self.name)
        if raw is None:
            self._deny()
            return None
        key: str = str(raw)
        return key


class APIKeyCookie(_APIKeyBase):
    """API key extracted from a cookie.

    api_key_cookie = APIKeyCookie(name="session")

    @app.get("/secure")
    async def secure(key: str = Depends(api_key_cookie)):
        ...
    """

    async def __call__(self, request: Request) -> str | None:
        key = request.cookies.get(self.name)
        if key is None:
            self._deny()
            return None
        return key
