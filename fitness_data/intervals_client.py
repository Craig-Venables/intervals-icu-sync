"""HTTP client for the intervals.icu REST API."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import requests

from fitness_data.config import Settings


class IntervalsClient:
    """HTTP client using Basic auth (username ``API_KEY``, password is your API key)."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings.from_env()
        self._session = requests.Session()
        # intervals.icu personal API: username is literal "API_KEY", password is your key
        self._session.auth = ("API_KEY", self.settings.api_key)
        self._session.headers["Accept"] = "application/json"

    def _url(self, path: str) -> str:
        return f"{self.settings.base_url.rstrip('/')}/{path.lstrip('/')}"

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        response = self._session.request(method, self._url(path), timeout=60, **kwargs)
        response.raise_for_status()
        if not response.content:
            return None
        content_type = response.headers.get("Content-Type", "")
        if "application/json" in content_type:
            return response.json()
        return response.text

    def _get(self, path: str, **params: Any) -> Any:
        return self._request("GET", path, params=params)

    def _put(self, path: str, payload: dict[str, Any]) -> Any:
        return self._request(
            "PUT",
            path,
            json=payload,
            headers={"Content-Type": "application/json"},
        )

    @property
    def athlete_id(self) -> str:
        return self.settings.athlete_id

    def get_athlete(self) -> dict[str, Any]:
        return self._get(f"athlete/{self.athlete_id}")

    def get_wellness(self, day: date) -> dict[str, Any] | None:
        try:
            return self._get(f"athlete/{self.athlete_id}/wellness/{day.isoformat()}")
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 404:
                return None
            raise

    def update_wellness(self, day: date, payload: dict[str, Any]) -> dict[str, Any] | None:
        body = {**payload, "id": day.isoformat()}
        return self._put(f"athlete/{self.athlete_id}/wellness/{day.isoformat()}", body)

    def list_activities(
        self,
        oldest: date,
        newest: date | None = None,
        *,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"oldest": oldest.isoformat()}
        if newest is not None:
            params["newest"] = newest.isoformat()
        if limit is not None:
            params["limit"] = limit

        data = self._get(f"athlete/{self.athlete_id}/activities", **params)
        if data is None:
            return []
        return data

    def get_activity(self, activity_id: int | str, *, intervals: bool = False) -> dict[str, Any]:
        params = {"intervals": "true"} if intervals else {}
        return self._get(f"activity/{activity_id}", **params)

    def list_wellness(
        self,
        oldest: date,
        newest: date | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"oldest": oldest.isoformat()}
        if newest is not None:
            params["newest"] = newest.isoformat()

        data = self._get(f"athlete/{self.athlete_id}/wellness", **params)
        if data is None:
            return []
        return data

    def download_activities_csv(self, oldest: date, newest: date | None = None) -> str:
        params: dict[str, Any] = {"oldest": oldest.isoformat()}
        if newest is not None:
            params["newest"] = newest.isoformat()

        return self._get(f"athlete/{self.athlete_id}/activities.csv", **params)


    def get_streams(self, activity_id: int | str) -> dict[str, list[Any]]:
        """Return activity streams as {type: data_list}.

        intervals.icu returns a JSON list of stream objects with ``type`` and ``data``.
        """
        raw = self._get(f"activity/{activity_id}/streams")
        if raw is None:
            return {}
        if isinstance(raw, dict):
            # Already type->list, or wrapped
            if all(isinstance(v, list) for v in raw.values()):
                return {str(k): v for k, v in raw.items()}
            return {}
        out: dict[str, list[Any]] = {}
        if isinstance(raw, list):
            for item in raw:
                if not isinstance(item, dict):
                    continue
                stype = item.get("type")
                data = item.get("data")
                if stype is None or not isinstance(data, list):
                    continue
                out[str(stype)] = data
        return out

    def download_fit(self, activity_id: int | str, dest_path: Path) -> Path:
        """Download the original FIT file to ``dest_path``.

        Writes response bytes; gunzips when the payload still has gzip magic
        (``requests`` often already decompresses Content-Encoding: gzip).
        """
        import gzip

        dest = Path(dest_path)
        dest.parent.mkdir(parents=True, exist_ok=True)

        response = self._session.get(
            self._url(f"activity/{activity_id}/file"),
            timeout=120,
        )
        response.raise_for_status()
        payload = response.content or b""

        # Gunzip if bytes still look like gzip (magic 1f 8b)
        while len(payload) >= 2 and payload[0] == 0x1F and payload[1] == 0x8B:
            payload = gzip.decompress(payload)

        dest.write_bytes(payload)
        return dest
