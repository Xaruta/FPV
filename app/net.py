"""Kleiner HTTP-Helfer (nur Standardbibliothek)."""
from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.parse
import urllib.request

from app import config

_CTX = ssl.create_default_context()


class NetError(RuntimeError):
    def __init__(self, msg: str, status: int | None = None):
        super().__init__(msg)
        self.status = status


def get_json(url: str, params: dict | None = None, timeout: int | None = None):
    """Gibt (json, headers) zurück. Fehler als NetError mit deutscher Meldung."""
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": config.USER_AGENT, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout or config.HTTP_TIMEOUT, context=_CTX) as r:
            return json.loads(r.read().decode("utf-8")), dict(r.headers)
    except urllib.error.HTTPError as e:
        raise NetError(f"HTTP {e.code} von {urllib.parse.urlparse(url).netloc}", e.code) from e
    except urllib.error.URLError as e:
        raise NetError(f"Keine Verbindung zu {urllib.parse.urlparse(url).netloc} ({e.reason})") from e
    except TimeoutError as e:
        raise NetError(f"Zeitüberschreitung bei {urllib.parse.urlparse(url).netloc}") from e
    except json.JSONDecodeError as e:
        raise NetError("Antwort war kein gültiges JSON") from e
