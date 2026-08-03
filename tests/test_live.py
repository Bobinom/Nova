import tempfile
import unittest
from pathlib import Path

import requests

from nova.app import NovaApplication
from nova.core.settings import SettingsManager
from nova.live.service import LiveInformationService


class FakeResponse:
    def __init__(self, payload, status_error=None):
        self.payload = payload
        self.status_error = status_error

    def raise_for_status(self):
        if self.status_error is not None:
            raise self.status_error

    def json(self):
        return self.payload


class QueuedHTTP:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def __call__(self, url, **kwargs):
        self.calls.append((url, kwargs))
        response = next(self.responses)
        if isinstance(response, BaseException):
            raise response
        return FakeResponse(response)


class LiveInformationTests(unittest.TestCase):
    def make_service(self, root, responses=()):
        settings = SettingsManager(root / "settings.json")
        settings.load()
        http = QueuedHTTP(responses)
        return LiveInformationService(settings, http), http

    def test_live_queries_are_disabled_by_default(self):
        with tempfile.TemporaryDirectory() as directory:
            service, http = self.make_service(Path(directory))

            result = service.process("What's the weather in Malmö?")

            self.assertEqual(result["intent"], "live_information_blocked")
            self.assertEqual(http.calls, [])

    def test_unrelated_conversation_does_not_use_web(self):
        with tempfile.TemporaryDirectory() as directory:
            service, http = self.make_service(Path(directory))
            service.set_enabled(True)

            self.assertEqual(service.process("Tell me a joke"), {"handled": False})
            self.assertEqual(http.calls, [])

    def test_weather_uses_fixed_open_meteo_endpoints_and_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            service, http = self.make_service(Path(directory), [
                {
                    "results": [{
                        "name": "Malmö",
                        "country": "Sweden",
                        "latitude": 55.605,
                        "longitude": 13.0038,
                    }],
                },
                {
                    "current": {
                        "temperature_2m": 18.5,
                        "apparent_temperature": 17.9,
                        "weather_code": 2,
                        "wind_speed_10m": 11.2,
                    },
                    "current_units": {
                        "temperature_2m": "°C",
                        "wind_speed_10m": "km/h",
                    },
                },
            ])
            service.set_enabled(True)

            result = service.process("What's the weather in Malmö?")

            self.assertEqual(result["intent"], "live_weather")
            self.assertIn("18.5°C", result["response"])
            self.assertIn("partly cloudy", result["spoken_response"])
            self.assertIn("https://open-meteo.com/", result["response"])
            self.assertEqual(http.calls[0][0], service.WEATHER_GEOCODING_URL)
            self.assertEqual(http.calls[1][0], service.WEATHER_URL)

    def test_weather_here_uses_saved_default_location(self):
        with tempfile.TemporaryDirectory() as directory:
            service, http = self.make_service(Path(directory), [
                {
                    "results": [{
                        "name": "Malmö",
                        "country": "Sweden",
                        "latitude": 55.605,
                        "longitude": 13.0038,
                    }],
                },
                {
                    "current": {
                        "temperature_2m": 18.5,
                        "apparent_temperature": 17.9,
                        "weather_code": 2,
                        "wind_speed_10m": 11.2,
                    },
                    "current_units": {
                        "temperature_2m": "°C",
                        "wind_speed_10m": "km/h",
                    },
                },
            ])
            service.set_enabled(True)

            result = service.process(
                "What's the weather like here?",
                default_location="Malmö Sweden",
            )

            self.assertEqual(result["intent"], "live_weather")
            self.assertEqual(
                http.calls[0][1]["params"]["name"],
                "Malmö Sweden",
            )

    def test_weather_here_without_saved_location_gives_clear_prompt(self):
        with tempfile.TemporaryDirectory() as directory:
            service, http = self.make_service(Path(directory))
            service.set_enabled(True)

            result = service.process("What's the weather like here?")

            self.assertEqual(result["intent"], "live_weather_location_missing")
            self.assertEqual(http.calls, [])

    def test_search_uses_duckduckgo_answer_with_source(self):
        with tempfile.TemporaryDirectory() as directory:
            service, http = self.make_service(Path(directory), [{
                "Heading": "Sweden",
                "AbstractText": "Sweden is a country in Northern Europe.",
                "AbstractURL": "https://example.test/sweden",
            }])
            service.set_enabled(True)

            result = service.process("Look up Sweden")

            self.assertEqual(result["intent"], "live_search")
            self.assertIn("Northern Europe", result["response"])
            self.assertIn("https://example.test/sweden", result["response"])
            self.assertEqual(http.calls[0][0], service.DUCKDUCKGO_URL)

    def test_long_search_answer_is_shorter_when_spoken(self):
        with tempfile.TemporaryDirectory() as directory:
            long_answer = " ".join(["A sourced fact about Sweden."] * 40)
            service, _ = self.make_service(Path(directory), [{
                "Heading": "Sweden",
                "AbstractText": long_answer,
                "AbstractURL": "https://example.test/sweden",
            }])
            service.set_enabled(True)

            result = service.process("Look up Sweden")

            self.assertLess(len(result["spoken_response"]), 350)
            self.assertLess(len(result["response"]), 800)
            self.assertIn("https://example.test/sweden", result["response"])

    def test_search_falls_back_to_wikipedia(self):
        with tempfile.TemporaryDirectory() as directory:
            service, http = self.make_service(Path(directory), [
                {},
                {
                    "query": {
                        "pages": [{
                            "index": 1,
                            "title": "Sweden",
                            "extract": "Sweden is a Nordic country.",
                        }],
                    },
                },
            ])
            service.set_enabled(True)

            result = service.process("Search the web for Sweden")

            self.assertIn("Sweden is a Nordic country", result["response"])
            self.assertIn("en.wikipedia.org/wiki/Sweden", result["response"])
            self.assertEqual(http.calls[1][0], service.WIKIPEDIA_URL)

    def test_network_failure_has_clear_offline_response(self):
        with tempfile.TemporaryDirectory() as directory:
            service, _ = self.make_service(
                Path(directory),
                [requests.ConnectionError("offline")],
            )
            service.set_enabled(True)

            result = service.process("Look up Sweden")

            self.assertEqual(result["intent"], "live_information_error")
            self.assertIn("internet connection", result["response"])

    def test_application_routes_live_result_before_ollama(self):
        with tempfile.TemporaryDirectory() as directory:
            app = NovaApplication(base_dir=Path(directory))
            app.live.http_get = QueuedHTTP([{
                "Heading": "Sweden",
                "AbstractText": "Sweden is in Northern Europe.",
                "AbstractURL": "https://example.test/sweden",
            }])
            app.start()
            app.live.set_enabled(True)

            result = app.handle_message("Look up Sweden")

            self.assertEqual(result["intent"], "live_search")
            self.assertEqual(len(app.conversation.history()), 2)
            self.assertTrue(app.conversation.privacy_status()["allow_web_access"])
            app.stop()


if __name__ == "__main__":
    unittest.main()
