"""Credential-safe URL handling independent of Home Assistant."""

from urllib.parse import urlsplit, urlunsplit


def normalize_base_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("SurvNG URL must use HTTP or HTTPS and include a host")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("SurvNG URL cannot contain credentials, query, or fragment")
    path = parsed.path.rstrip("/")
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def require_secure_transport(url: str, allow_insecure_http: bool) -> str:
    """Normalize a configured URL and require an explicit HTTP opt-in."""
    normalized = normalize_base_url(url)
    if urlsplit(normalized).scheme == "http" and not allow_insecure_http:
        raise ValueError("HTTPS is required unless insecure HTTP is explicitly allowed")
    return normalized
