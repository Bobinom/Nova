import io
import json
import unittest

from nova.gui_bridge import NovaGUIBridge, run_bridge


class FakeConversation:
    def __init__(self):
        self.episode_auto_save = True
        self.confirm_semantic_memory = False

    def handle(self, text):
        return {"handled": True, "response": "Hello"}

    def history(self, limit):
        return [{"role": "assistant", "text": "Hello", "limit": limit}]

    def privacy_status(self):
        return {
            "episode_auto_save": self.episode_auto_save,
            "confirm_semantic_memory": self.confirm_semantic_memory,
        }

    def set_episode_auto_save(self, enabled):
        self.episode_auto_save = enabled

    def set_semantic_confirmation(self, enabled):
        self.confirm_semantic_memory = enabled


class FakeStatus:
    def __init__(self, value):
        self.value = value

    def status(self):
        return self.value

    def set_enabled(self, enabled):
        self.value["enabled"] = enabled


class FakeMemory:
    class Record:
        value = "Malmö"

    def recall(self, key):
        return self.Record() if key == "user.location" else None


class FakeLive(FakeStatus):
    def process(self, text):
        return {
            "handled": True,
            "intent": "live_weather",
            "spoken_response": "In Malmö, it is 18°C and clear.",
        }


class FakeVoice(FakeStatus):
    def __init__(self):
        super().__init__({
            "enabled": True,
            "auto_speak": True,
            "input_available": True,
        })
        self.spoken = []

    def listen(self):
        return "Hello Nova"

    def speak(self, text):
        self.spoken.append(text)
        return True

    def set_auto_speak(self, enabled):
        self.value["auto_speak"] = enabled


class FakeApp:
    def __init__(self):
        self.conversation = FakeConversation()
        self.started = False
        self.stopped = False
        self.voice = FakeVoice()
        self.actions = FakeStatus({"enabled": True})
        self.live = FakeLive({"enabled": True})
        self.memory = FakeMemory()

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True

    def status(self):
        return {"version": "7.3.0", "running": self.started}

    def handle_message(self, text):
        return {"handled": True, "response": f"Reply to {text}"}

    def listen_and_respond(self):
        return {"transcript": "Hello Nova", "response": "Hello"}


class GUIBridgeTests(unittest.TestCase):
    def test_bridge_routes_messages_to_nova_application(self):
        app = FakeApp()
        bridge = NovaGUIBridge(app)
        bridge.start()

        response = bridge.process({
            "id": "one",
            "command": "message",
            "text": "Hello Nova",
        })

        self.assertTrue(app.started)
        self.assertEqual(response["id"], "one")
        self.assertEqual(response["result"]["response"], "Reply to Hello Nova")

    def test_bridge_exposes_bounded_history(self):
        response = NovaGUIBridge(FakeApp()).process({
            "command": "history",
            "limit": 500,
        })

        self.assertEqual(response["result"][0]["limit"], 100)

    def test_line_protocol_returns_errors_and_stops_cleanly(self):
        app = FakeApp()
        requests = io.StringIO(
            '{"id":"bad","command":"unknown"}\n'
            '{"id":"status","command":"status"}\n'
            '{"id":"done","command":"shutdown"}\n'
        )
        output = io.StringIO()

        run_bridge(app=app, input_stream=requests, output_stream=output)

        responses = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertFalse(responses[0]["ok"])
        self.assertTrue(responses[1]["result"]["running"])
        self.assertTrue(responses[2]["shutdown"])
        self.assertTrue(app.stopped)

    def test_dashboard_combines_local_service_status(self):
        result = NovaGUIBridge(FakeApp()).process({"command": "dashboard"})[
            "result"
        ]

        self.assertTrue(result["voice"]["enabled"])
        self.assertTrue(result["actions"]["enabled"])
        self.assertTrue(result["live_information"]["enabled"])
        self.assertEqual(result["ollama_model"], "llama3.2")

    def test_bridge_updates_only_allowlisted_preferences(self):
        app = FakeApp()
        bridge = NovaGUIBridge(app)

        result = bridge.process({
            "command": "set_preference",
            "key": "voice.auto_speak",
            "value": False,
        })["result"]

        self.assertFalse(result["voice"]["auto_speak"])
        with self.assertRaisesRegex(ValueError, "Unsupported preference"):
            bridge.process({
                "command": "set_preference",
                "key": "ollama.model",
                "value": True,
            })

    def test_weather_uses_saved_location(self):
        result = NovaGUIBridge(FakeApp()).process({"command": "weather"})[
            "result"
        ]

        self.assertTrue(result["available"])
        self.assertEqual(result["location"], "Malmö")
        self.assertIn("18°C", result["spoken_response"])

    def test_listen_returns_transcript_and_response(self):
        result = NovaGUIBridge(FakeApp()).process({"command": "listen"})[
            "result"
        ]

        self.assertEqual(result["transcript"], "Hello Nova")
        self.assertEqual(result["response"], "Hello")

    def test_gui_listen_separates_response_from_speech(self):
        app = FakeApp()
        result = NovaGUIBridge(app).process({"command": "listen_gui"})[
            "result"
        ]

        self.assertEqual(result["transcript"], "Hello Nova")
        self.assertTrue(result["should_speak"])
        self.assertEqual(app.voice.spoken, [])

        NovaGUIBridge(app).process({
            "command": "speak",
            "text": result["speech_text"],
        })
        self.assertEqual(app.voice.spoken, ["Hello"])


if __name__ == "__main__":
    unittest.main()
