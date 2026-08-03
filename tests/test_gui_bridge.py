import io
import json
import unittest

from nova.gui_bridge import NovaGUIBridge, run_bridge


class FakeConversation:
    def history(self, limit):
        return [{"role": "assistant", "text": "Hello", "limit": limit}]

    def privacy_status(self):
        return {"episode_auto_save": True}


class FakeStatus:
    def __init__(self, value):
        self.value = value

    def status(self):
        return self.value


class FakeApp:
    def __init__(self):
        self.conversation = FakeConversation()
        self.started = False
        self.stopped = False
        self.voice = FakeStatus({"enabled": True})
        self.actions = FakeStatus({"enabled": True})
        self.live = FakeStatus({"enabled": False})

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True

    def status(self):
        return {"version": "7.2.0", "running": self.started}

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
        self.assertFalse(result["live_information"]["enabled"])

    def test_listen_returns_transcript_and_response(self):
        result = NovaGUIBridge(FakeApp()).process({"command": "listen"})[
            "result"
        ]

        self.assertEqual(result["transcript"], "Hello Nova")
        self.assertEqual(result["response"], "Hello")


if __name__ == "__main__":
    unittest.main()
