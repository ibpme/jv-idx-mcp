"""OAuth 2.0 authentication support for the MCP server.

Implements MCP authorization specification requirements:
- OAuth 2.0 Protected Resource Metadata (RFC9728)
- JWT access token validation via JWKS
- WWW-Authenticate headers with resource_metadata parameter
"""

from __future__ import annotations

import fnmatch
import os
import time
from typing import Any

import httpx
import jwt
from jwt import PyJWKClient
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


class OAuthConfig:
    """Configuration for OAuth 2.0 resource server behavior."""

    def __init__(
        self,
        issuer: str,
        jwks_uri: str | None = None,
        audience: str | None = None,
        required_scopes: list[str] | None = None,
        public_paths: list[str] | None = None,
    ) -> None:
        self.issuer = issuer.rstrip("/")
        self.jwks_uri = jwks_uri
        self.audience = audience
        self.required_scopes = set(required_scopes or ["mcp:read"])
        self.public_paths = public_paths or [
            "/.well-known/oauth-protected-resource",
            "/health",
        ]
        self._jwks_client: PyJWKClient | None = None
        self._jwks_fetched_at: float = 0.0
        self._jwks_ttl: float = 3600.0  # 1 hour

    @classmethod
    def from_env(cls) -> "OAuthConfig | None":
        """Load OAuth config from environment variables.

        Expected variables:
            OAUTH_ISSUER      - OAuth/OIDC issuer URL (required)
            OAUTH_JWKS_URI    - JWKS endpoint URI (optional; defaults to issuer + /.well-known/jwks.json)
            OAUTH_AUDIENCE    - Expected audience claim (optional)
            OAUTH_SCOPES      - Comma-separated required scopes (default: mcp:read)
            OAUTH_PUBLIC_PATHS - Comma-separated public path patterns (optional)
        """
        issuer = os.getenv("OAUTH_ISSUER", "").strip()
        if not issuer:
            return None

        jwks_uri = os.getenv("OAUTH_JWKS_URI", "").strip() or None
        audience = os.getenv("OAUTH_AUDIENCE", "").strip() or None
        scopes_raw = os.getenv("OAUTH_SCOPES", "mcp:read")
        required_scopes = [s.strip() for s in scopes_raw.split(",") if s.strip()]

        public_paths = [
            "/.well-known/oauth-protected-resource",
            "/health",
        ]
        public_raw = os.getenv("OAUTH_PUBLIC_PATHS", "").strip()
        if public_raw:
            public_paths.extend([p.strip() for p in public_raw.split(",") if p.strip()])

        return cls(
            issuer=issuer,
            jwks_uri=jwks_uri,
            audience=audience,
            required_scopes=required_scopes,
            public_paths=public_paths,
        )

    def get_jwks_uri(self) -> str:
        """Return the JWKS URI, inferring from issuer if not explicitly set."""
        if self.jwks_uri:
            return self.jwks_uri
        return f"{self.issuer}/.well-known/jwks.json"

    def get_jwks_client(self) -> PyJWKClient:
        """Return a cached PyJWKClient, refreshing if TTL expired."""
        now = time.monotonic()
        if self._jwks_client is None or (now - self._jwks_fetched_at) > self._jwks_ttl:
            self._jwks_client = PyJWKClient(
                self.get_jwks_uri(),
                cache_keys=True,
                max_cached_keys=20,
            )
            self._jwks_fetched_at = now
        return self._jwks_client

    def is_public_path(self, path: str) -> bool:
        """Check if a path matches any public path pattern."""
        for pattern in self.public_paths:
            if fnmatch.fnmatch(path, pattern):
                return True
        return False

    def resource_metadata(self, base_url: str) -> dict[str, Any]:
        """Build the OAuth 2.0 Protected Resource Metadata document (RFC9728)."""
        return {
            "resource": base_url,
            "authorization_servers": [self.issuer],
            "scopes_supported": sorted(self.required_scopes),
            "bearer_methods_supported": ["header"],
            "resource_signing_alg_values_supported": [
                "RS256",
                "RS384",
                "RS512",
                "ES256",
                "ES384",
                "ES512",
            ],
        }


def _build_www_authenticate(config: OAuthConfig, base_url: str) -> str:
    """Build the WWW-Authenticate header value per MCP auth spec.

    Includes resource_metadata parameter pointing to the Protected Resource Metadata endpoint.
    """
    resource_meta_url = f"{base_url}/.well-known/oauth-protected-resource"
    scope_str = " ".join(sorted(config.required_scopes))
    return (
        f'Bearer realm="mcp", '
        f'resource_metadata="{resource_meta_url}", '
        f'scope="{scope_str}"'
    )


def _unauthorized_response(config: OAuthConfig, base_url: str) -> Response:
    """Return a 401 Unauthorized response with proper WWW-Authenticate header."""
    return Response(
        content="Unauthorized",
        status_code=401,
        headers={"WWW-Authenticate": _build_www_authenticate(config, base_url)},
    )


def _validate_token(
    token: str,
    config: OAuthConfig,
) -> dict[str, Any]:
    """Validate a JWT access token and return its claims.

    Raises jwt.PyJWTError on invalid or expired tokens.
    """
    jwks_client = config.get_jwks_client()
    signing_key = jwks_client.get_signing_key_from_jwt(token)

    options = {
        "verify_signature": True,
        "verify_exp": True,
        "verify_iat": True,
        "verify_nbf": True,
        "require": ["exp"],
    }

    audience = config.audience
    if audience:
        options["verify_aud"] = True
    else:
        options["verify_aud"] = False

    payload = jwt.decode(
        token,
        key=signing_key.key,
        algorithms=["RS256", "RS384", "RS512", "ES256", "ES384", "ES512"],
        audience=audience,
        issuer=config.issuer,
        options=options,
    )

    # Validate scopes if present
    token_scopes: set[str] = set()
    scope_claim = payload.get("scope", "")
    if isinstance(scope_claim, str):
        token_scopes = set(scope_claim.split())
    elif isinstance(scope_claim, list):
        token_scopes = set(str(s) for s in scope_claim)

    if config.required_scopes and not config.required_scopes.issubset(token_scopes):
        missing = config.required_scopes - token_scopes
        raise jwt.InvalidTokenError(
            f"Insufficient scopes. Missing: {', '.join(missing)}"
        )

    return payload


class OAuthAuthMiddleware:
    """ASGI middleware that enforces OAuth 2.0 Bearer token auth."""

    def __init__(self, app, config: OAuthConfig) -> None:
        self.app = app
        self.config = config

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)
        path = request.url.path

        # Allow public paths without auth
        if self.config.is_public_path(path):
            await self.app(scope, receive, send)
            return

        # Extract Bearer token from Authorization header
        auth = request.headers.get("authorization", "")
        if not auth.lower().startswith("bearer "):
            base_url = str(request.base_url).rstrip("/")
            response = _unauthorized_response(self.config, base_url)
            await response(scope, receive, send)
            return

        token = auth[7:].strip()
        if not token:
            base_url = str(request.base_url).rstrip("/")
            response = _unauthorized_response(self.config, base_url)
            await response(scope, receive, send)
            return

        try:
            _validate_token(token, self.config)
        except jwt.ExpiredSignatureError:
            base_url = str(request.base_url).rstrip("/")
            response = Response(
                content="Token expired",
                status_code=401,
                headers={
                    "WWW-Authenticate": _build_www_authenticate(self.config, base_url)
                },
            )
            await response(scope, receive, send)
            return
        except jwt.InvalidTokenError as exc:
            base_url = str(request.base_url).rstrip("/")
            response = Response(
                content=f"Invalid token: {exc}",
                status_code=401,
                headers={
                    "WWW-Authenticate": _build_www_authenticate(self.config, base_url)
                },
            )
            await response(scope, receive, send)
            return
        except httpx.HTTPError as exc:
            base_url = str(request.base_url).rstrip("/")
            response = Response(
                content=f"Unable to validate token: {exc}",
                status_code=503,
                headers={
                    "WWW-Authenticate": _build_www_authenticate(self.config, base_url)
                },
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)


class OAuthMetadataEndpoint:
    """ASGI app fragment that serves the Protected Resource Metadata document."""

    def __init__(self, config: OAuthConfig) -> None:
        self.config = config

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await Response("Not Found", status_code=404)(scope, receive, send)
            return

        request = Request(scope, receive)
        path = request.url.path

        if path != "/.well-known/oauth-protected-resource":
            await Response("Not Found", status_code=404)(scope, receive, send)
            return

        base_url = str(request.base_url).rstrip("/")
        metadata = self.config.resource_metadata(base_url)
        response = JSONResponse(
            content=metadata,
            headers={
                "Content-Type": "application/json",
                "Cache-Control": "public, max-age=3600",
            },
        )
        await response(scope, receive, send)


def build_oauth_app(app, config: OAuthConfig):
    """Wrap an ASGI app with OAuth metadata endpoint and auth middleware.

    The metadata endpoint is mounted at /.well-known/oauth-protected-resource
    and the auth middleware protects all other routes.
    """
    metadata = OAuthMetadataEndpoint(config)

    async def combined_app(scope, receive, send):
        if scope["type"] == "http":
            request = Request(scope, receive)
            if request.url.path == "/.well-known/oauth-protected-resource":
                await metadata(scope, receive, send)
                return
        await OAuthAuthMiddleware(app, config)(scope, receive, send)

    return combined_app
