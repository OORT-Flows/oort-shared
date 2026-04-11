class TokenError(Exception):
    """Raised when a JWT cannot be decoded, validated, or has missing claims."""


class AccessDeniedError(Exception):
    """Raised when the caller is authenticated but lacks the required product access."""
