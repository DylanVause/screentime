"""HTTP uploader — sends buffered sessions to the ScreenTime server."""

import logging
from typing import Any

import requests

log = logging.getLogger(__name__)


class Uploader:
    def __init__(self, config: dict) -> None:
        self._base_url = config["server"]["url"].rstrip("/")
        self._api_key = config["server"]["api_key"]
        self._device_name = config["device"]["name"]
        self._timeout = config["server"].get("timeout_seconds", 30)
        self._verify_ssl = config["server"].get("verify_ssl", True)

    def _headers(self) -> dict[str, str]:
        return {
            "X-API-Key": self._api_key,
            "Content-Type": "application/json",
        }

    def upload(self, sessions: list[dict]) -> tuple[bool, int]:
        """Upload a list of sessions.  Returns (success, accepted_count)."""
        payload: dict[str, Any] = {
            "device_name": self._device_name,
            "sessions": [
                {
                    "session_uuid": s["session_uuid"],
                    "start": s["start"],
                    "end": s["end"],
                    "app": s["app"],
                    "title": s["title"],
                    "duration_seconds": s["duration_seconds"],
                }
                for s in sessions
            ],
        }
        try:
            resp = requests.post(
                f"{self._base_url}/api/v1/sessions",
                json=payload,
                headers=self._headers(),
                timeout=self._timeout,
                verify=self._verify_ssl,
            )
            if resp.status_code == 200:
                data = resp.json()
                return True, data.get("accepted", len(sessions))
            log.warning("Server returned %d: %s", resp.status_code, resp.text[:200])
            return False, 0
        except requests.exceptions.ConnectionError:
            log.warning("Cannot reach server at %s", self._base_url)
            return False, 0
        except Exception as exc:
            log.warning("Upload error: %s", exc)
            return False, 0
