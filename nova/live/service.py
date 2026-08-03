from __future__ import annotations

import html
import re
from collections.abc import Callable
from typing import Any
from urllib.parse import quote

import requests

from nova.core.settings import SettingsManager


class LiveInformationService:
    WEATHER_GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
    WEATHER_URL = "https://api.open-meteo.com/v1/forecast"
    DUCKDUCKGO_URL = "https://api.duckduckgo.com/"
    WIKIPEDIA_URL = "https://en.wikipedia.org/w/api.php"

    def __init__(
        self,
        settings: SettingsManager,
        http_get: Callable[..., Any] = requests.get,
    ) -> None:
        self.settings = settings
        self.http_get = http_get

    def status(self) -> dict[str, Any]:
        return {
            "enabled": bool(
                self.settings.get("privacy.allow_web_access", False)
            ),
            "providers": ["Open-Meteo", "DuckDuckGo", "Wikipedia"],
            "weather_provider": "Open-Meteo",
            "search_providers": ["DuckDuckGo", "Wikipedia"],
        }

    def set_enabled(self, enabled: bool) -> None:
        self.settings.set("privacy.allow_web_access", enabled)

    def process(self, text: str) -> dict[str, Any]:
        weather_location = self._weather_location(text)
        search_query = self._search_query(text)
        if weather_location is None and search_query is None:
            return {"handled": False}
        if not self.status()["enabled"]:
            return {
                "handled": True,
                "intent": "live_information_blocked",
                "response": (
                    "Live information is disabled. Use live-on to allow "
                    "queries to approved information providers."
                ),
            }
        try:
            if weather_location is not None:
                return self._weather(weather_location)
            return self._search(str(search_query))
        except (OSError, ValueError, requests.RequestException) as exc:
            return {
                "handled": True,
                "intent": "live_information_error",
                "response": (
                    "I couldn't reach the live information providers. "
                    "Check this Mac's internet connection and try again."
                ),
                "error": str(exc),
            }

    def _weather(self, location: str) -> dict[str, Any]:
        place_data = self._json(
            self.WEATHER_GEOCODING_URL,
            params={
                "name": location,
                "count": 1,
                "language": "en",
                "format": "json",
            },
        )
        places = place_data.get("results") or []
        if not places:
            return {
                "handled": True,
                "intent": "live_weather",
                "response": f"I couldn't find a weather location named {location}.",
            }
        place = places[0]
        forecast = self._json(
            self.WEATHER_URL,
            params={
                "latitude": place["latitude"],
                "longitude": place["longitude"],
                "current": (
                    "temperature_2m,apparent_temperature,weather_code,"
                    "wind_speed_10m"
                ),
                "timezone": "auto",
            },
        )
        current = forecast.get("current") or {}
        units = forecast.get("current_units") or {}
        name = str(place.get("name") or location)
        country = str(place.get("country") or "").strip()
        place_name = f"{name}, {country}" if country else name
        temperature = current.get("temperature_2m")
        apparent = current.get("apparent_temperature")
        wind = current.get("wind_speed_10m")
        description = self._weather_description(current.get("weather_code"))
        temp_unit = units.get("temperature_2m", "°C")
        wind_unit = units.get("wind_speed_10m", "km/h")
        spoken = (
            f"In {place_name}, it is {temperature}{temp_unit} and {description}. "
            f"It feels like {apparent}{temp_unit}, with wind at {wind} {wind_unit}."
        )
        source = "https://open-meteo.com/"
        return {
            "handled": True,
            "intent": "live_weather",
            "response": f"{spoken}\nSource: Open-Meteo — {source}",
            "spoken_response": spoken,
            "sources": [{"title": "Open-Meteo", "url": source}],
        }

    def _search(self, query: str) -> dict[str, Any]:
        duck = self._json(
            self.DUCKDUCKGO_URL,
            params={
                "q": query,
                "format": "json",
                "no_html": 1,
                "no_redirect": 1,
                "skip_disambig": 1,
            },
        )
        abstract = str(duck.get("AbstractText") or "").strip()
        abstract_url = str(duck.get("AbstractURL") or "").strip()
        heading = str(duck.get("Heading") or query).strip()
        if abstract and abstract_url:
            return self._search_result(
                heading,
                abstract,
                [{"title": heading, "url": abstract_url}],
            )

        wiki = self._json(
            self.WIKIPEDIA_URL,
            params={
                "action": "query",
                "generator": "search",
                "gsrsearch": query,
                "gsrlimit": 3,
                "prop": "extracts",
                "exintro": 1,
                "explaintext": 1,
                "exsentences": 3,
                "format": "json",
                "formatversion": 2,
            },
        )
        pages = (wiki.get("query") or {}).get("pages") or []
        pages = sorted(pages, key=lambda page: page.get("index", 999))
        usable = [page for page in pages if str(page.get("extract") or "").strip()]
        if not usable:
            return {
                "handled": True,
                "intent": "live_search",
                "response": f"I couldn't find a sourced result for {query}.",
            }
        page = usable[0]
        title = str(page.get("title") or query)
        extract = html.unescape(str(page.get("extract") or "").strip())
        url = f"https://en.wikipedia.org/wiki/{quote(title.replace(' ', '_'))}"
        return self._search_result(
            title,
            extract,
            [{"title": f"Wikipedia: {title}", "url": url}],
        )

    def _search_result(
        self,
        title: str,
        summary: str,
        sources: list[dict[str, str]],
    ) -> dict[str, Any]:
        display_summary = self._truncate_summary(summary, 700)
        spoken_summary = self._truncate_summary(summary, 320)
        source_lines = "\n".join(
            f"- {source['title']}: {source['url']}" for source in sources
        )
        displayed = f"{title}: {display_summary}"
        spoken = f"{title}: {spoken_summary}"
        return {
            "handled": True,
            "intent": "live_search",
            "response": f"{displayed}\nSources:\n{source_lines}",
            "spoken_response": spoken,
            "sources": sources,
        }

    @staticmethod
    def _truncate_summary(summary: str, limit: int) -> str:
        cleaned = re.sub(r"\s+", " ", summary).strip()
        if len(cleaned) <= limit:
            return cleaned
        candidate = cleaned[:limit + 1]
        sentence = max(
            candidate.rfind(". "),
            candidate.rfind("! "),
            candidate.rfind("? "),
        )
        if sentence >= limit // 2:
            return candidate[:sentence + 1]
        word = candidate.rfind(" ")
        return candidate[:word].rstrip(" ,.;:") + "…"

    def _json(self, url: str, *, params: dict[str, Any]) -> dict[str, Any]:
        response = self.http_get(
            url,
            params=params,
            headers={"User-Agent": "Nova/7.2 (+https://github.com/Bobinom/Nova)"},
            timeout=12,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Live provider returned invalid data.")
        return payload

    @staticmethod
    def _weather_location(text: str) -> str | None:
        normalized = text.strip().rstrip("?.!")
        match = re.search(
            r"\b(?:weather|temperature|forecast)(?:\s+like)?(?:\s+today)?"
            r"\s+(?:in|for|at)\s+(.+)$",
            normalized,
            re.I,
        )
        return match.group(1).strip() if match else None

    @staticmethod
    def _search_query(text: str) -> str | None:
        cleaned = text.strip().rstrip("?.!")
        explicit = re.match(
            r"^(?:search (?:the )?web for|search online for|look up)\s+(.+)$",
            cleaned,
            re.I,
        )
        if explicit:
            return explicit.group(1).strip()
        if re.match(r"^how many people (?:live|are) in\s+.+$", cleaned, re.I):
            return cleaned
        if re.search(r"\b(?:current|latest|today|right now)\b", cleaned, re.I):
            return cleaned
        return None

    @staticmethod
    def _weather_description(code: Any) -> str:
        descriptions = {
            0: "clear",
            1: "mostly clear",
            2: "partly cloudy",
            3: "overcast",
            45: "foggy",
            48: "foggy",
            51: "light drizzle",
            53: "drizzle",
            55: "heavy drizzle",
            61: "light rain",
            63: "rainy",
            65: "heavy rain",
            71: "light snow",
            73: "snowy",
            75: "heavy snow",
            80: "light rain showers",
            81: "rain showers",
            82: "heavy rain showers",
            95: "thunderstorms",
        }
        try:
            return descriptions.get(int(code), "conditions are unavailable")
        except (TypeError, ValueError):
            return "conditions are unavailable"
