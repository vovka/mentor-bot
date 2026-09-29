"""KrokiRenderer: Mermaid -> PNG through a Kroki server (public kroki.io or self-hosted)."""

import urllib.error
import urllib.request

_TIMEOUT = 30


class KrokiRenderer:
    def __init__(self, base_url: str = "https://kroki.io"):
        self._url = f"{base_url.rstrip('/')}/mermaid/png"

    def render(self, mermaid: str) -> bytes:
        req = urllib.request.Request(
            self._url, data=mermaid.encode(), headers={"Content-Type": "text/plain"}
        )
        try:
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"kroki {exc.code}: {exc.read()[:200].decode(errors='replace')}")
        except (urllib.error.URLError, TimeoutError) as exc:
            raise RuntimeError(f"kroki unreachable: {exc}")
