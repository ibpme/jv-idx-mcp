"""Authentication modules for the MCP server."""

from auth.oauth import (
    OAuthAuthMiddleware,
    OAuthConfig,
    OAuthMetadataEndpoint,
    build_oauth_app,
)

__all__ = [
    "OAuthAuthMiddleware",
    "OAuthConfig",
    "OAuthMetadataEndpoint",
    "build_oauth_app",
]
