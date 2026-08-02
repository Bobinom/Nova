from __future__ import annotations

import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


class MacOSSpeechInput:
    """Build and run Nova's local Apple Speech-framework helper."""

    HELPER_VERSION = "2"

    def __init__(
        self,
        data_dir: Path,
        *,
        locale: str = "en-US",
        duration: int = 7,
    ) -> None:
        self.data_dir = data_dir
        self.locale = locale
        self.duration = duration
        self.source = Path(__file__).with_name("macos") / "NovaSpeechInput.m"
        self.bundle = (
            data_dir / "voice" /
            f"NovaSpeechInput-{self.HELPER_VERSION}.app"
        )
        self.executable = self.bundle / "Contents" / "MacOS" / "NovaSpeechInput"

    def available(self) -> bool:
        return (
            sys.platform == "darwin"
            and self.source.exists()
            and (self.executable.exists() or shutil.which("clang") is not None)
        )

    def installed(self) -> bool:
        return self.executable.is_file() and os.access(self.executable, os.X_OK)

    def setup(self) -> Path:
        if self.installed():
            return self.bundle
        compiler = shutil.which("clang")
        if sys.platform != "darwin" or compiler is None:
            raise RuntimeError(
                "Apple Command Line Tools are required for built-in microphone input."
            )
        if not self.source.exists():
            raise RuntimeError("Nova's native speech source file is missing.")

        voice_dir = self.bundle.parent
        voice_dir.mkdir(parents=True, exist_ok=True)
        staging = voice_dir / f".{self.bundle.name}.building-{os.getpid()}"
        if staging.exists():
            shutil.rmtree(staging)
        executable = staging / "Contents" / "MacOS" / "NovaSpeechInput"
        executable.parent.mkdir(parents=True)
        resources = staging / "Contents" / "Resources"
        resources.mkdir()
        self._write_info_plist(staging / "Contents" / "Info.plist")

        environment = os.environ.copy()
        module_cache = voice_dir / "clang-module-cache"
        module_cache.mkdir(exist_ok=True)
        environment["CLANG_MODULE_CACHE_PATH"] = str(module_cache)
        command = [
            compiler,
            "-fblocks",
            "-mmacosx-version-min=13.0",
            str(self.source),
            "-o",
            str(executable),
            "-framework",
            "Foundation",
            "-framework",
            "Speech",
            "-framework",
            "AVFoundation",
        ]
        try:
            subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
                timeout=120,
                env=environment,
            )
            codesign = shutil.which("codesign")
            if codesign is None:
                raise RuntimeError(
                    "Apple codesign is required for microphone permissions."
                )
            subprocess.run(
                [codesign, "--force", "--sign", "-", str(staging)],
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
            )
            os.replace(staging, self.bundle)
        except (OSError, subprocess.SubprocessError) as exc:
            details = ""
            if isinstance(exc, subprocess.CalledProcessError):
                details = (exc.stderr or exc.stdout or "").strip()
            raise RuntimeError(
                f"Could not build Nova Speech Input: {details or exc}"
            ) from exc
        finally:
            if staging.exists():
                shutil.rmtree(staging)
        return self.bundle

    def check(self) -> dict[str, Any]:
        self.setup()
        completed = self._run(["--check", "--locale", self.locale], timeout=20)
        return {
            "ready": completed.stdout.strip() == "ready",
            "locale": self.locale,
            "installed": self.installed(),
            "bundle": str(self.bundle),
        }

    def listen(self) -> str:
        self.setup()
        launcher = shutil.which("open")
        if launcher is None:
            raise RuntimeError("macOS Launch Services are unavailable.")
        with tempfile.TemporaryDirectory(
            prefix="nova-listen-",
            dir=self.bundle.parent,
        ) as directory:
            result_path = Path(directory) / "transcript.txt"
            error_path = Path(directory) / "error.txt"
            command = [
                launcher,
                "-W",
                "-n",
                str(self.bundle),
                "--args",
                "--locale",
                self.locale,
                "--seconds",
                str(self.duration),
                "--output",
                str(result_path),
                "--error",
                str(error_path),
            ]
            try:
                subprocess.run(
                    command,
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=self.duration + 140,
                )
            except (OSError, subprocess.SubprocessError) as exc:
                raise RuntimeError(
                    f"Native speech recognition failed: {exc}"
                ) from exc
            if error_path.exists():
                message = error_path.read_text(encoding="utf-8").strip()
                if message:
                    raise RuntimeError(message)
            transcript = (
                result_path.read_text(encoding="utf-8").strip()
                if result_path.exists()
                else ""
            )
        if not transcript:
            raise RuntimeError(
                "Nova Speech Input closed without returning a transcript."
            )
        return transcript

    def _run(
        self,
        arguments: list[str],
        *,
        timeout: int,
    ) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                [str(self.executable), *arguments],
                check=True,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.CalledProcessError as exc:
            message = self._last_error(exc.stderr or exc.stdout or "")
            raise RuntimeError(message or "Native speech recognition failed.") from exc
        except (OSError, subprocess.SubprocessError) as exc:
            raise RuntimeError(f"Native speech recognition failed: {exc}") from exc

    def _write_info_plist(self, destination: Path) -> None:
        payload = {
            "CFBundleDevelopmentRegion": "en",
            "CFBundleExecutable": "NovaSpeechInput",
            "CFBundleIdentifier": "com.bobinom.nova.speechinput",
            "CFBundleInfoDictionaryVersion": "6.0",
            "CFBundleName": "Nova Speech Input",
            "CFBundlePackageType": "APPL",
            "CFBundleShortVersionString": self.HELPER_VERSION,
            "CFBundleVersion": self.HELPER_VERSION,
            "LSUIElement": True,
            "NSMicrophoneUsageDescription": (
                "Nova uses the microphone only while you ask it to listen."
            ),
            "NSSpeechRecognitionUsageDescription": (
                "Nova converts your spoken request into text on this Mac."
            ),
        }
        with destination.open("wb") as handle:
            plistlib.dump(payload, handle, sort_keys=True)

    @staticmethod
    def _last_error(output: str) -> str:
        lines = [line.strip() for line in output.splitlines() if line.strip()]
        useful = [
            line
            for line in lines
            if not line.startswith("nwi_state:")
            and "NovaSpeechInput[" not in line
        ]
        return useful[-1] if useful else (lines[-1] if lines else "")
