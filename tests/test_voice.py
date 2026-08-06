import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nova.app import NovaApplication
from nova.core.settings import SettingsManager
from nova.voice.service import (
    ElevenLabsSpeechOutput,
    MacOSKeychain,
    MacOSSpeechOutput,
    VoiceService,
)


class FakeKeychain:
    def __init__(self, value: str | None = None) -> None:
        self.value = value

    def get(self) -> str | None:
        return self.value

    def set(self, value: str) -> None:
        self.value = value


class RecordingOutput:
    def __init__(self, available: bool = True) -> None:
        self.is_available = available
        self.calls: list[tuple[str, str | None, int]] = []

    def available(self) -> bool:
        return self.is_available

    def speak(self, text: str, *, voice: str | None, rate: int) -> None:
        self.calls.append((text, voice, rate))


class RecordingInput:
    def __init__(self, transcript: str = "Hello Nova") -> None:
        self.transcript = transcript

    def available(self) -> bool:
        return True

    def listen(self) -> str:
        return self.transcript


class VoiceServiceTests(unittest.TestCase):
    def make_service(self, root: Path) -> tuple[VoiceService, RecordingOutput]:
        settings = SettingsManager(root / "settings.json")
        settings.load()
        output = RecordingOutput()
        return VoiceService(
            settings,
            output,
            RecordingInput(),
            keychain=FakeKeychain(),
        ), output

    def test_voice_is_disabled_by_default(self):
        with tempfile.TemporaryDirectory() as directory:
            service, output = self.make_service(Path(directory))

            self.assertFalse(service.speak("Hello"))
            self.assertEqual(output.calls, [])
            self.assertFalse(service.status()["enabled"])

    def test_natural_follow_up_is_enabled_by_default_and_persistent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            service, _ = self.make_service(root)

            self.assertTrue(service.status()["follow_up_enabled"])
            service.set_follow_up_enabled(False)

            reloaded, _ = self.make_service(root)
            self.assertFalse(reloaded.status()["follow_up_enabled"])

    def test_voice_speaks_with_persistent_rate_and_name(self):
        with tempfile.TemporaryDirectory() as directory:
            service, output = self.make_service(Path(directory))
            service.set_enabled(True)
            service.settings.set("voice.name", "Samantha")
            service.settings.set("voice.rate", 205)

            self.assertTrue(service.speak("Hello"))
            self.assertEqual(output.calls, [("Hello", "Samantha", 205)])

    def test_automatic_speech_requires_both_voice_switches(self):
        with tempfile.TemporaryDirectory() as directory:
            service, output = self.make_service(Path(directory))
            service.set_auto_speak(True)

            self.assertFalse(service.speak_response("First"))
            service.set_enabled(True)
            self.assertTrue(service.speak_response("Second"))
            self.assertEqual(output.calls[0][0], "Second")

    def test_listen_requires_voice_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            service, _ = self.make_service(Path(directory))

            with self.assertRaisesRegex(RuntimeError, "Voice mode is disabled"):
                service.listen()

            service.set_enabled(True)
            self.assertEqual(service.listen(), "Hello Nova")

    def test_voice_rate_is_clamped(self):
        with tempfile.TemporaryDirectory() as directory:
            service, output = self.make_service(Path(directory))
            service.set_enabled(True)
            service.settings.set("voice.rate", 900)

            service.speak("Fast")

            self.assertEqual(output.calls[0][2], 500)

    def test_input_command_is_persisted_as_an_argument_list(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            service, _ = self.make_service(root)

            service.set_input_command(["local-transcriber", "--once"])

            reloaded = SettingsManager(root / "settings.json")
            reloaded.load()
            self.assertEqual(
                reloaded.get("voice.input_command"),
                ["local-transcriber", "--once"],
            )

    def test_locale_and_duration_are_validated_and_persisted(self):
        with tempfile.TemporaryDirectory() as directory:
            service, _ = self.make_service(Path(directory))

            service.set_locale("sv-SE")
            service.set_duration(30)

            self.assertEqual(service.status()["locale"], "sv-SE")
            self.assertEqual(service.status()["listen_seconds"], 20)
            with self.assertRaises(ValueError):
                service.set_locale("not a locale")

    def test_recognition_mode_is_explicit_and_persisted(self):
        with tempfile.TemporaryDirectory() as directory:
            service, _ = self.make_service(Path(directory))

            self.assertEqual(service.status()["recognition_mode"], "on-device")
            service.set_recognition_mode("automatic")

            self.assertEqual(service.status()["recognition_mode"], "automatic")
            self.assertEqual(service.native_input.recognition_mode, "automatic")
            with self.assertRaises(ValueError):
                service.set_recognition_mode("online-only")

    def test_wake_phrase_is_validated_and_persisted(self):
        with tempfile.TemporaryDirectory() as directory:
            service, _ = self.make_service(Path(directory))
            service.set_wake_phrase("Hey Nova")
            self.assertEqual(service.status()["wake_phrase"], "Hey Nova")
            with self.assertRaises(ValueError):
                service.set_wake_phrase("this phrase has too many words")

    def test_wake_mode_is_opt_in_and_persisted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            service, _ = self.make_service(root)

            self.assertFalse(service.status()["wake_enabled"])
            service.set_wake_enabled(True)

            reloaded = SettingsManager(root / "settings.json")
            reloaded.load()
            self.assertTrue(reloaded.get("voice.wake_enabled"))

    def test_application_can_listen_respond_and_speak(self):
        with tempfile.TemporaryDirectory() as directory:
            app = NovaApplication(base_dir=Path(directory))
            output = RecordingOutput()
            app.voice.output = output
            app.voice.input = RecordingInput("My name is Eric")
            app.start()
            app.voice.set_enabled(True)
            app.voice.set_auto_speak(True)

            result = app.listen_and_respond()

            self.assertEqual(result["transcript"], "My name is Eric")
            self.assertIn("your name is Eric", result["response"])
            self.assertEqual(output.calls[0][0], result["response"])
            app.stop()

    def test_elevenlabs_configuration_keeps_api_key_out_of_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings = SettingsManager(root / "settings.json")
            settings.load()
            keychain = FakeKeychain()
            service = VoiceService(settings, keychain=keychain)

            service.configure_elevenlabs(
                "GmM3ucvssIf0NWKHkiyc",
                "secret-api-key",
            )

            self.assertEqual(keychain.get(), "secret-api-key")
            self.assertEqual(service.status()["output_provider"], "elevenlabs")
            self.assertNotIn(
                "secret-api-key",
                settings.path.read_text(encoding="utf-8"),
            )

    @patch("nova.voice.service.subprocess.run")
    @patch("nova.voice.service.shutil.which", return_value="/usr/bin/afplay")
    @patch("nova.voice.service.requests.post")
    def test_elevenlabs_generates_and_plays_temporary_audio(
        self,
        post,
        _,
        run,
    ):
        with tempfile.TemporaryDirectory() as directory:
            settings = SettingsManager(Path(directory) / "settings.json")
            settings.load()
            output = ElevenLabsSpeechOutput(
                settings,
                FakeKeychain("secret-api-key"),
            )
            response = post.return_value
            response.content = b"mp3-data"

            output.speak("Hello", voice=None, rate=190)

            request = post.call_args
            self.assertIn("GmM3ucvssIf0NWKHkiyc", request.args[0])
            self.assertEqual(
                request.kwargs["headers"]["xi-api-key"],
                "secret-api-key",
            )
            response.raise_for_status.assert_called_once()
            played_path = Path(run.call_args.args[0][1])
            self.assertFalse(played_path.exists())

    def test_elevenlabs_failure_falls_back_to_macos_voice(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = SettingsManager(Path(directory) / "settings.json")
            settings.load()
            service = VoiceService(
                settings,
                keychain=FakeKeychain("secret-api-key"),
            )
            service.set_enabled(True)
            service.set_output_provider("elevenlabs")

            def fail(*args, **kwargs):
                raise RuntimeError("offline")

            service.elevenlabs_output.speak = fail
            fallback = RecordingOutput()
            service.macos_output = fallback

            self.assertTrue(service.speak("Fallback please"))
            self.assertEqual(fallback.calls[0][0], "Fallback please")

    def test_elevenlabs_voice_id_is_validated(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = SettingsManager(Path(directory) / "settings.json")
            settings.load()
            service = VoiceService(settings, keychain=FakeKeychain("key"))

            with self.assertRaisesRegex(ValueError, "Voice ID"):
                service.configure_elevenlabs("not valid!")

    @patch("nova.voice.service.subprocess.run", side_effect=OSError("unavailable"))
    @patch("nova.voice.service.shutil.which", return_value="/usr/bin/security")
    def test_keychain_lookup_failure_is_safe(self, _, __):
        self.assertIsNone(MacOSKeychain().get())

    @patch("nova.voice.service.subprocess.run")
    @patch("nova.voice.service.shutil.which", return_value="/usr/bin/say")
    def test_macos_speech_uses_arguments_without_a_shell(self, _, run):
        output = MacOSSpeechOutput()

        output.speak("-dangerous looking text", voice="Samantha", rate=190)

        run.assert_called_once_with(
            ["say", "-r", "190", "-v", "Samantha"],
            check=True,
            input="-dangerous looking text",
            text=True,
            timeout=120,
        )


if __name__ == "__main__":
    unittest.main()
