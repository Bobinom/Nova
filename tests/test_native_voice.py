import plistlib
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nova.voice.native import MacOSSpeechInput


class NativeVoiceTests(unittest.TestCase):
    def test_native_helper_keeps_main_run_loop_active_for_callbacks(self):
        source = (
            Path(__file__).parents[1]
            / "nova" / "voice" / "macos" / "NovaSpeechInput.m"
        ).read_text(encoding="utf-8")

        self.assertIn("RunLoopFor(seconds);", source)
        self.assertIn("!recognitionFinished", source)
        self.assertNotIn("usleep(", source)

    def test_native_helper_uses_core_audio_native_input_format(self):
        source = (
            Path(__file__).parents[1]
            / "nova" / "voice" / "macos" / "NovaSpeechInput.m"
        ).read_text(encoding="utf-8")

        tap = source.split(
            'Selector("installTapOnBus:bufferSize:format:block:")', 1
        )[1]
        self.assertIn("1024,\n        nil,\n        audioTap", tap)

    def test_setup_builds_permission_declared_signed_app_bundle(self):
        with tempfile.TemporaryDirectory() as directory:
            provider = MacOSSpeechInput(Path(directory))

            def fake_run(command, **kwargs):
                if "-o" in command:
                    executable = Path(command[command.index("-o") + 1])
                    executable.write_bytes(b"native helper")
                    executable.chmod(0o755)
                return subprocess.CompletedProcess(command, 0, "", "")

            with (
                patch("nova.voice.native.sys.platform", "darwin"),
                patch(
                    "nova.voice.native.shutil.which",
                    side_effect=lambda name: f"/usr/bin/{name}",
                ),
                patch("nova.voice.native.subprocess.run", side_effect=fake_run) as run,
            ):
                bundle = provider.setup()

            info = plistlib.loads(
                (bundle / "Contents" / "Info.plist").read_bytes()
            )
            self.assertEqual(
                info["CFBundleIdentifier"],
                "com.bobinom.nova.speechinput",
            )
            self.assertIn("NSMicrophoneUsageDescription", info)
            self.assertIn("NSSpeechRecognitionUsageDescription", info)
            self.assertTrue(info["LSUIElement"])
            self.assertTrue(provider.installed())
            commands = [call.args[0] for call in run.call_args_list]
            self.assertTrue(any("-framework" in command for command in commands))
            self.assertTrue(any("--sign" in command for command in commands))

    def test_check_uses_on_device_helper_without_requesting_audio(self):
        with tempfile.TemporaryDirectory() as directory:
            provider = MacOSSpeechInput(Path(directory), locale="sv-SE")
            completed = subprocess.CompletedProcess([], 0, "ready\n", "")

            with (
                patch.object(provider, "setup"),
                patch.object(provider, "installed", return_value=True),
                patch("nova.voice.native.subprocess.run", return_value=completed) as run,
            ):
                status = provider.check()

            self.assertTrue(status["ready"])
            command = run.call_args.args[0]
            self.assertEqual(command[1:], [
                "--check", "--locale", "sv-SE",
                "--recognition-mode", "on-device",
            ])

    def test_listen_returns_only_the_transcript(self):
        with tempfile.TemporaryDirectory() as directory:
            provider = MacOSSpeechInput(Path(directory), duration=5)
            provider.bundle.parent.mkdir(parents=True)

            def fake_run(command, **kwargs):
                output = Path(command[command.index("--output") + 1])
                output.write_text("Open Safari\n", encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, "", "")

            with (
                patch.object(provider, "setup"),
                patch("nova.voice.native.shutil.which", return_value="/usr/bin/open"),
                patch("nova.voice.native.subprocess.run", side_effect=fake_run) as run,
            ):
                transcript = provider.listen()

            self.assertEqual(transcript, "Open Safari")
            command = run.call_args.args[0]
            self.assertEqual(command[:4], [
                "/usr/bin/open", "-W", "-n", str(provider.bundle),
            ])
            self.assertIn("--locale", command)
            self.assertIn("--output", command)

    def test_automatic_recognition_mode_is_forwarded_to_helper(self):
        with tempfile.TemporaryDirectory() as directory:
            provider = MacOSSpeechInput(
                Path(directory), recognition_mode="automatic"
            )
            provider.bundle.parent.mkdir(parents=True)

            def fake_run(command, **kwargs):
                output = Path(command[command.index("--output") + 1])
                output.write_text("Hello Nova\n", encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, "", "")

            with (
                patch.object(provider, "setup"),
                patch("nova.voice.native.shutil.which", return_value="/usr/bin/open"),
                patch("nova.voice.native.subprocess.run", side_effect=fake_run) as run,
            ):
                provider.listen()

            command = run.call_args.args[0]
            mode = command.index("--recognition-mode")
            self.assertEqual(command[mode + 1], "automatic")

    def test_native_errors_are_cleaned_for_the_user(self):
        with tempfile.TemporaryDirectory() as directory:
            provider = MacOSSpeechInput(Path(directory))
            provider.bundle.parent.mkdir(parents=True)

            def fake_run(command, **kwargs):
                error_path = Path(command[command.index("--error") + 1])
                error_path.write_text(
                    "Microphone permission was denied.\n",
                    encoding="utf-8",
                )
                return subprocess.CompletedProcess(command, 0, "", "")

            with (
                patch.object(provider, "setup"),
                patch("nova.voice.native.shutil.which", return_value="/usr/bin/open"),
                patch("nova.voice.native.subprocess.run", side_effect=fake_run),
            ):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "Microphone permission was denied",
                ):
                    provider.listen()


if __name__ == "__main__":
    unittest.main()
