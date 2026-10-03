"""Restrict browser push delivery to known browser push services."""

from urllib.parse import urlsplit


def valid_web_push_endpoint(endpoint: str) -> bool:
    try:
        parsed = urlsplit(endpoint)
        host = parsed.hostname or ""
        return (
            parsed.scheme == "https"
            and parsed.port is None
            and parsed.username is None
            and parsed.password is None
            and bool(parsed.path)
            and (
                host == "fcm.googleapis.com"
                or host.endswith(".push.services.mozilla.com")
                or host.endswith(".push.apple.com")
            )
        )
    except ValueError:
        return False
