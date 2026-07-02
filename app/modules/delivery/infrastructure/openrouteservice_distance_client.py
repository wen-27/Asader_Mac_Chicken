"""OpenRouteService adapter used to estimate delivery distance when no manual zone matches."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import httpx

from app.config.settings import Settings
from app.shared.domain.exceptions import InvalidValueError


@dataclass(frozen=True)
class Coordinates:
    longitude: float
    latitude: float


class OpenRouteServiceDistanceClient:
    def __init__(self, settings: Settings, client: Optional[httpx.AsyncClient] = None) -> None:
        if not settings.openrouteservice_api_key:
            raise InvalidValueError("openrouteservice api key is not configured")
        self._api_key = settings.openrouteservice_api_key
        self._base_url = settings.openrouteservice_base_url.rstrip("/")
        self._client = client

    async def driving_distance_km(self, origin: str, destination: str) -> float:
        origin_coordinates = await self._geocode(origin)
        destination_coordinates = await self._geocode(destination, focus=origin_coordinates)
        distance_meters = await self._route_distance_meters(
            origin_coordinates,
            destination_coordinates,
        )
        return distance_meters / 1000

    async def _geocode(self, text: str, focus: Optional[Coordinates] = None) -> Coordinates:
        params = {
            "text": text,
            "boundary.country": "COL",
            "size": "1",
        }
        if focus is not None:
            params.update(
                {
                    "focus.point.lon": str(focus.longitude),
                    "focus.point.lat": str(focus.latitude),
                    "boundary.circle.lon": str(focus.longitude),
                    "boundary.circle.lat": str(focus.latitude),
                    "boundary.circle.radius": "35",
                }
            )
        if self._client is None:
            async with httpx.AsyncClient(timeout=15) as client:
                data = await self._get(client, "/geocode/search", params)
        else:
            data = await self._get(self._client, "/geocode/search", params)
        features = data.get("features", [])
        if not isinstance(features, list) or not features:
            raise InvalidValueError(f"openrouteservice could not geocode address: {text}")
        first = features[0]
        if not isinstance(first, dict):
            raise InvalidValueError("openrouteservice geocode response is invalid")
        geometry = first.get("geometry", {})
        coordinates = geometry.get("coordinates") if isinstance(geometry, dict) else None
        if not isinstance(coordinates, list) or len(coordinates) < 2:
            raise InvalidValueError("openrouteservice geocode coordinates are missing")
        return Coordinates(longitude=float(coordinates[0]), latitude=float(coordinates[1]))

    async def _route_distance_meters(
        self,
        origin: Coordinates,
        destination: Coordinates,
    ) -> float:
        payload = {
            "coordinates": [
                [origin.longitude, origin.latitude],
                [destination.longitude, destination.latitude],
            ],
            "units": "m",
        }
        if self._client is None:
            async with httpx.AsyncClient(timeout=20) as client:
                data = await self._post(client, "/v2/directions/driving-car", payload)
        else:
            data = await self._post(self._client, "/v2/directions/driving-car", payload)
        routes = data.get("routes", [])
        if isinstance(routes, list) and routes:
            first_route = routes[0]
            summary = first_route.get("summary", {}) if isinstance(first_route, dict) else {}
            distance = summary.get("distance") if isinstance(summary, dict) else None
            if isinstance(distance, (int, float)):
                return float(distance)
        features = data.get("features", [])
        if isinstance(features, list) and features:
            properties = features[0].get("properties", {}) if isinstance(features[0], dict) else {}
            segments = properties.get("segments", []) if isinstance(properties, dict) else []
            if isinstance(segments, list) and segments:
                distance = segments[0].get("distance") if isinstance(segments[0], dict) else None
                if isinstance(distance, (int, float)):
                    return float(distance)
        raise InvalidValueError("openrouteservice route distance is missing")

    async def _get(
        self,
        client: httpx.AsyncClient,
        path: str,
        params: dict[str, str],
    ) -> dict[str, object]:
        try:
            response = await client.get(
                f"{self._base_url}{path}",
                params=params,
                headers={"Authorization": self._api_key, "Accept": "application/json"},
            )
        except httpx.HTTPError as exc:
            raise InvalidValueError("openrouteservice get request failed") from exc
        return self._response_json(response, "get")

    async def _post(
        self,
        client: httpx.AsyncClient,
        path: str,
        payload: dict[str, object],
    ) -> dict[str, object]:
        try:
            response = await client.post(
                f"{self._base_url}{path}",
                json=payload,
                headers={
                    "Authorization": self._api_key,
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
            )
        except httpx.HTTPError as exc:
            raise InvalidValueError("openrouteservice post request failed") from exc
        return self._response_json(response, "post")

    def _response_json(self, response: httpx.Response, method: str) -> dict[str, object]:
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise InvalidValueError(
                f"openrouteservice {method} request failed with status {exc.response.status_code}"
            ) from exc
        data = response.json()
        if not isinstance(data, dict):
            raise InvalidValueError("openrouteservice response is invalid")
        return data
