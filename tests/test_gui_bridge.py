import io
import json
import threading
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
            "wake_enabled": False,
            "wake_phrase": "Hey Nova",
            "follow_up_enabled": True,
        })
        self.spoken = []
        self.transcript = "Hello Nova"

    def listen(self):
        return self.transcript

    def speak(self, text):
        self.spoken.append(text)
        return True

    def set_auto_speak(self, enabled):
        self.value["auto_speak"] = enabled

    def set_wake_enabled(self, enabled):
        self.value["wake_enabled"] = enabled

    def set_follow_up_enabled(self, enabled):
        self.value["follow_up_enabled"] = enabled

    def setup_input(self):
        return {
            "available": True,
            "message": "Microphone and speech recognition are ready.",
        }

    def configure_elevenlabs(self, voice_id, api_key=""):
        self.value["output_provider"] = "elevenlabs"
        self.value["elevenlabs_voice_id"] = voice_id
        self.value["elevenlabs_configured"] = bool(api_key)

    def set_output_provider(self, provider):
        self.value["output_provider"] = provider

    def test_output(self):
        return {
            "spoken": True,
            "provider": self.value.get("output_provider", "macos"),
        }


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

    def test_line_protocol_survives_malformed_json(self):
        app = FakeApp()
        requests = io.StringIO(
            'not-json\n'
            '{"id":"status","command":"status"}\n'
            '{"id":"done","command":"shutdown"}\n'
        )
        output = io.StringIO()

        run_bridge(app=app, input_stream=requests, output_stream=output)

        responses = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertFalse(responses[0]["ok"])
        self.assertTrue(responses[1]["result"]["running"])
        self.assertTrue(responses[2]["shutdown"])

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

    def test_voice_setup_uses_native_voice_diagnostics(self):
        result = NovaGUIBridge(FakeApp()).process({"command": "voice_setup"})[
            "result"
        ]

        self.assertTrue(result["available"])
        self.assertIn("ready", result["message"].lower())

    def test_bridge_configures_elevenlabs_without_returning_api_key(self):
        response = NovaGUIBridge(FakeApp()).process({
            "command": "configure_elevenlabs",
            "voice_id": "GmM3ucvssIf0NWKHkiyc",
            "api_key": "secret-api-key",
        })

        voice = response["result"]["voice"]
        self.assertEqual(voice["output_provider"], "elevenlabs")
        self.assertEqual(
            voice["elevenlabs_voice_id"],
            "GmM3ucvssIf0NWKHkiyc",
        )
        self.assertNotIn("secret-api-key", str(response))

    def test_bridge_switches_and_tests_voice_provider(self):
        app = FakeApp()
        bridge = NovaGUIBridge(app)

        bridge.process({"command": "set_voice_provider", "provider": "macos"})
        result = bridge.process({"command": "test_voice"})["result"]

        self.assertTrue(result["spoken"])
        self.assertEqual(result["provider"], "macos")

    def test_wake_listener_emits_request_without_blocking_bridge(self):
        app = FakeApp()
        app.voice.value["wake_enabled"] = True
        app.voice.transcript = "Hey Nova, open Safari"
        events = []
        received = threading.Event()

        def collect(event):
            events.append(event)
            received.set()

        bridge = NovaGUIBridge(app, event_sink=collect)
        response = bridge.process({"command": "wake_listen_start"})
        bridge.release_wake_listener()

        self.assertTrue(response["result"]["listening"])
        self.assertTrue(received.wait(timeout=1))
        self.assertEqual(events[0]["kind"], "request")
        self.assertEqual(events[0]["request"], "open Safari")

    def test_wake_message_returns_speech_without_speaking_in_worker(self):
        app = FakeApp()
        result = NovaGUIBridge(app).process({
            "command": "wake_message",
            "text": "What time is it?",
        })["result"]

        self.assertEqual(result["response"], "Hello")
        self.assertTrue(result["should_speak"])
        self.assertEqual(result["speech_text"], "Hello")
        self.assertTrue(result["follow_up_active"])
        self.assertEqual(app.voice.spoken, [])

    def test_natural_follow_up_does_not_require_wake_phrase(self):
        app = FakeApp()
        app.voice.value["wake_enabled"] = True
        events = []
        received = threading.Event()
        bridge = NovaGUIBridge(
            app,
            event_sink=lambda event: (events.append(event), received.set()),
        )
        bridge.process({"command": "wake_message", "text": "First question"})
        app.voice.transcript = "And what about tomorrow?"

        bridge.process({"command": "wake_listen_start"})
        bridge.release_wake_listener()

        self.assertTrue(received.wait(timeout=1))
        self.assertEqual(events[0]["kind"], "request")
        self.assertEqual(events[0]["request"], "And what about tomorrow?")
        self.assertTrue(events[0]["follow_up"])

    def test_spoken_stop_ends_follow_up_but_keeps_wake_mode_enabled(self):
        app = FakeApp()
        app.voice.value["wake_enabled"] = True
        events = []
        received = threading.Event()
        bridge = NovaGUIBridge(
            app,
            event_sink=lambda event: (events.append(event), received.set()),
        )
        bridge.process({"command": "wake_message", "text": "First question"})
        app.voice.transcript = "that's all"

        bridge.process({"command": "wake_listen_start"})
        bridge.release_wake_listener()

        self.assertTrue(received.wait(timeout=1))
        self.assertEqual(events[0]["kind"], "conversation_end")
        self.assertEqual(events[0]["reason"], "spoken_stop")
        self.assertTrue(app.voice.value["wake_enabled"])

    def test_plain_sleep_command_turns_off_wake_during_follow_up(self):
        app = FakeApp()
        app.voice.value["wake_enabled"] = True
        events = []
        received = threading.Event()
        bridge = NovaGUIBridge(
            app,
            event_sink=lambda event: (events.append(event), received.set()),
        )
        bridge.process({"command": "wake_message", "text": "First question"})
        app.voice.transcript = "go to sleep"

        bridge.process({"command": "wake_listen_start"})
        bridge.release_wake_listener()

        self.assertTrue(received.wait(timeout=1))
        self.assertEqual(events[0]["kind"], "sleep")
        self.assertFalse(app.voice.value["wake_enabled"])

    def test_follow_up_silence_returns_to_wake_standby(self):
        app = FakeApp()
        app.voice.value["wake_enabled"] = True
        events = []
        received = threading.Event()
        bridge = NovaGUIBridge(
            app,
            event_sink=lambda event: (events.append(event), received.set()),
        )
        bridge.process({"command": "wake_message", "text": "First question"})

        def silence():
            raise RuntimeError("No speech was recognized.")

        app.voice.listen = silence
        bridge.process({"command": "wake_listen_start"})
        bridge.release_wake_listener()

        self.assertTrue(received.wait(timeout=1))
        self.assertEqual(events[0]["kind"], "conversation_end")
        self.assertEqual(events[0]["reason"], "silence")
        self.assertTrue(app.voice.value["wake_enabled"])

    def test_wake_sleep_phrase_disables_persistent_listener(self):
        app = FakeApp()
        app.voice.value["wake_enabled"] = True
        app.voice.transcript = "Hey Nova, go to sleep"
        events = []
        received = threading.Event()
        bridge = NovaGUIBridge(
            app,
            event_sink=lambda event: (events.append(event), received.set()),
        )

        bridge.process({"command": "wake_listen_start"})
        bridge.release_wake_listener()

        self.assertTrue(received.wait(timeout=1))
        self.assertEqual(events[0]["kind"], "sleep")
        self.assertFalse(app.voice.value["wake_enabled"])


if __name__ == "__main__":
    unittest.main()
