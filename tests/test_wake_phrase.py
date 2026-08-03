import unittest

from nova.voice.wake import WakePhraseSession


class RecordingVoice:
    def __init__(self, events):
        self.events = iter(events)
        self.spoken = []
        self.auto_speak = False

    def listen(self):
        event = next(self.events)
        if isinstance(event, BaseException):
            raise event
        return event

    def speak(self, text, *, force=False):
        self.spoken.append((text, force))
        return True

    def status(self):
        return {"auto_speak": self.auto_speak}


class WakePhraseSessionTests(unittest.TestCase):
    def test_extracts_request_only_when_phrase_starts_transcript(self):
        session = WakePhraseSession(RecordingVoice([]), lambda text: {})
        self.assertEqual(
            session.request_after_wake_phrase("Nova, open Safari"),
            "open Safari",
        )
        self.assertEqual(session.request_after_wake_phrase("NOVA!"), "")
        self.assertIsNone(
            session.request_after_wake_phrase("Tell Nova to open Safari")
        )

        custom = WakePhraseSession(
            RecordingVoice([]),
            lambda text: {},
            "Hey Nova",
        )
        self.assertEqual(
            custom.request_after_wake_phrase("Hey Nova, take a note"),
            "take a note",
        )

    def test_ignores_background_speech_and_handles_wake_request(self):
        voice = RecordingVoice([
            "Background conversation",
            "Nova, what time is it?",
            "Nova, go to sleep",
        ])
        handled = []
        reason = WakePhraseSession(
            voice,
            lambda text: handled.append(text) or {"response": "It is noon."},
        ).run(
            on_activation=lambda text: None,
            on_transcript=lambda text: None,
            on_response=lambda text: None,
            on_error=lambda text: None,
        )
        self.assertEqual(reason, "spoken_stop")
        self.assertEqual(handled, ["what time is it?"])
        self.assertEqual(voice.spoken, [
            ("It is noon.", True),
            ("Wake phrase mode stopped.", True),
        ])

    def test_phrase_alone_arms_the_next_utterance(self):
        voice = RecordingVoice(["Nova", "Open Notes", "Nova stop"])
        handled = []
        WakePhraseSession(
            voice,
            lambda text: handled.append(text) or {"response": "Done."},
        ).run(
            on_activation=lambda text: None,
            on_transcript=lambda text: None,
            on_response=lambda text: None,
            on_error=lambda text: None,
        )
        self.assertEqual(handled, ["Open Notes"])
        self.assertEqual(voice.spoken[0], ("Yes?", True))

    def test_action_confirmation_does_not_require_second_wake_phrase(self):
        voice = RecordingVoice(["Nova open Safari", "yes", "Nova stop"])
        handled = []

        def handle(text):
            handled.append(text)
            if text == "open Safari":
                return {
                    "response": "Confirm action: open Safari?",
                    "action_status": "pending_confirmation",
                }
            return {"response": "Done.", "action_status": "completed"}

        WakePhraseSession(voice, handle).run(
            on_activation=lambda text: None,
            on_transcript=lambda text: None,
            on_response=lambda text: None,
            on_error=lambda text: None,
        )
        self.assertEqual(handled, ["open Safari", "yes"])

    def test_silence_is_quiet_and_other_errors_are_reported(self):
        voice = RecordingVoice([
            RuntimeError("No speech was recognized"),
            RuntimeError("Microphone disconnected"),
            KeyboardInterrupt(),
        ])
        errors = []
        reason = WakePhraseSession(voice, lambda text: {}).run(
            on_activation=lambda text: None,
            on_transcript=lambda text: None,
            on_response=lambda text: None,
            on_error=errors.append,
        )
        self.assertEqual(reason, "interrupted")
        self.assertEqual(errors, ["Microphone disconnected"])

    def test_sourced_result_speaks_without_reading_url(self):
        voice = RecordingVoice(["Nova weather", "Nova stop"])
        WakePhraseSession(
            voice,
            lambda text: {
                "response": "Sunny. Source: https://example.test",
                "spoken_response": "It is sunny.",
            },
        ).run(
            on_activation=lambda text: None,
            on_transcript=lambda text: None,
            on_response=lambda text: None,
            on_error=lambda text: None,
        )
        self.assertEqual(voice.spoken[0], ("It is sunny.", True))


if __name__ == "__main__":
    unittest.main()
