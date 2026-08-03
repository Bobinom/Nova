import unittest

from nova.voice.conversation import HandsFreeConversation


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


class HandsFreeConversationTests(unittest.TestCase):
    def test_stop_phrases_ignore_case_and_punctuation(self):
        self.assertTrue(HandsFreeConversation.is_stop_phrase("Nova, stop!"))
        self.assertTrue(HandsFreeConversation.is_stop_phrase("STOP listening."))
        self.assertFalse(HandsFreeConversation.is_stop_phrase("Stop the music"))

    def test_session_repeats_and_speaks_until_spoken_stop(self):
        voice = RecordingVoice(["Hello Nova", "Nova, stop"])
        handled = []
        transcripts = []
        responses = []
        errors = []

        def handle(text):
            handled.append(text)
            return {"response": "Hello Eric"}

        reason = HandsFreeConversation(voice, handle).run(
            on_listening=lambda: None,
            on_transcript=transcripts.append,
            on_response=responses.append,
            on_error=errors.append,
        )

        self.assertEqual(reason, "spoken_stop")
        self.assertEqual(handled, ["Hello Nova"])
        self.assertEqual(transcripts, ["Hello Nova", "Nova, stop"])
        self.assertEqual(responses, ["Hello Eric"])
        self.assertEqual(errors, [])
        self.assertEqual(voice.spoken, [
            ("Hello Eric", True),
            ("Hands-free conversation stopped.", True),
        ])

    def test_recognition_failure_recovers_and_control_c_interrupts(self):
        voice = RecordingVoice([
            RuntimeError("No speech recognized"),
            KeyboardInterrupt(),
        ])
        errors = []

        reason = HandsFreeConversation(voice, lambda text: {}).run(
            on_listening=lambda: None,
            on_transcript=lambda text: None,
            on_response=lambda text: None,
            on_error=errors.append,
        )

        self.assertEqual(reason, "interrupted")
        self.assertEqual(errors, ["No speech recognized"])

    def test_auto_speak_does_not_duplicate_response_audio(self):
        voice = RecordingVoice(["Question", "Nova stop"])
        voice.auto_speak = True

        HandsFreeConversation(
            voice,
            lambda text: {"response": "Answer"},
        ).run(
            on_listening=lambda: None,
            on_transcript=lambda text: None,
            on_response=lambda text: None,
            on_error=lambda text: None,
        )

        self.assertEqual(
            voice.spoken,
            [("Hands-free conversation stopped.", True)],
        )

    def test_spoken_confirmation_reaches_existing_message_router(self):
        voice = RecordingVoice(["Open Safari", "yes", "Nova stop"])
        handled = []

        def handle(text):
            handled.append(text)
            if text == "Open Safari":
                return {"response": "Confirm action: open Safari?"}
            return {"response": "Done. I opened Safari."}

        HandsFreeConversation(voice, handle).run(
            on_listening=lambda: None,
            on_transcript=lambda text: None,
            on_response=lambda text: None,
            on_error=lambda text: None,
        )

        self.assertEqual(handled, ["Open Safari", "yes"])

    def test_sourced_result_prints_links_but_speaks_concise_answer(self):
        voice = RecordingVoice(["Weather", "Nova stop"])
        responses = []
        HandsFreeConversation(
            voice,
            lambda text: {
                "response": "Sunny. Source: https://example.test",
                "spoken_response": "It is sunny.",
            },
        ).run(
            on_listening=lambda: None,
            on_transcript=lambda text: None,
            on_response=responses.append,
            on_error=lambda text: None,
        )
        self.assertEqual(responses, ["Sunny. Source: https://example.test"])
        self.assertEqual(voice.spoken[0], ("It is sunny.", True))


if __name__ == "__main__":
    unittest.main()
