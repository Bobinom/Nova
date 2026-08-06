# Changelog

All notable Nova releases are documented here.

## 7.8.0 - 2026-08-04

### Added

- Natural follow-up conversations in the standalone app after a wake request.
- A persistent Voice Settings toggle for follow-up listening.
- Wake-free follow-up questions, action confirmations, and contextual replies.
- Spoken `stop`, `cancel`, `never mind`, and `that's all` conversation exits.
- Plain `go to sleep` support while a follow-up conversation is active.
- Tests for follow-up persistence, requests, stop phrases, and sleep behavior.

### Changed

- Nova opens one short listening window after each spoken answer and returns to
  wake-phrase standby after silence.
- The app clearly distinguishes wake requests from active follow-up speech.

### Privacy

- Follow-up listening uses the existing visible microphone state and configured
  Apple Speech recognition mode. Raw microphone audio is not stored.

### Preserved

- Wake-only mode can be restored from Settings. Manual voice, text chat,
  ElevenLabs, Ollama, SQLite memory, and confirmed actions remain compatible.

## 7.7.0 - 2026-08-03

### Added

- Opt-in hands-free wake-phrase mode in the standalone SwiftUI app.
- Persistent wake control in Voice Settings and the Nova menu-bar menu.
- Asynchronous wake-listening events that keep chat, Settings, and Nova Core
  responsive while the microphone waits for the configured phrase.
- Native listening, activation, thinking, speaking, error, and sleeping feedback.
- Spoken sleep command support and wake-free follow-up action confirmation.
- Automatic restart after silence and recoverable recognition errors.
- Tests for opt-in persistence, non-blocking wake events, requests, spoken
  responses, sleep commands, and bridge ordering.

### Changed

- Nova pauses wake listening while processing and speaking, then resumes after a
  short delay to prevent its own ElevenLabs or macOS output from reactivating it.
- Enabling hands-free mode also enables the required voice mode.

### Privacy

- Hands-free listening is always visibly indicated and disabled by default.
- Nova stores transcripts only through the existing conversation behavior; raw
  microphone audio is not saved.

### Preserved

- Manual click-to-speak, terminal wake mode, ElevenLabs, macOS fallback, Ollama,
  SQLite memory, standalone packaging, and confirmed actions remain compatible.

## 7.6.0 - 2026-08-03

### Added

- Optional ElevenLabs text-to-speech output using the configured custom Voice ID
  and the low-latency multilingual model.
- Secure API-key storage in macOS Keychain with no credential values returned by
  the GUI bridge or written to Nova settings and SQLite.
- Native Settings controls for provider selection, Voice ID configuration,
  secure account connection, connection status, and voice preview playback.
- Automatic built-in macOS speech fallback for normal responses when ElevenLabs
  is offline, times out, reaches a quota limit, or returns invalid audio.
- Tests for credential isolation, request construction, temporary-file cleanup,
  validation, fallback, and GUI bridge behavior.

### Changed

- Voice status now reports its output provider and whether ElevenLabs has been
  configured without exposing the API key.
- The DMG builder derives its filename and volume name from the app version.

### Privacy

- ElevenLabs output is opt-in. When selected, response text is sent to the
  ElevenLabs API for speech synthesis and may consume account credits.
- Generated MP3 data is played from a temporary file that is deleted immediately
  after playback.

### Preserved

- Built-in macOS speech remains the default and works without ElevenLabs.
- Standalone packaging, Ollama, SQLite memory, CLI voice input, calendar access,
  onboarding, and confirmed actions remain compatible.

## 7.5.0 - 2026-08-03

### Added

- Embedded Nova Core executable containing Python 3.12 and Nova's runtime
  dependencies, built reproducibly with PyInstaller.
- Orb-based native macOS application icon generated during the build.
- Drag-to-Applications `Nova-7.5.0.dmg` build script.
- Bundled native speech-helper source so voice setup continues to work after the
  app is moved away from the repository.

### Changed

- The SwiftUI app now launches Nova Core from its own Resources directory rather
  than using the repository's `.venv` and `repo-path.txt`.
- The app builder creates a clean, ad-hoc-signed standalone bundle and checks for
  the required packaging tools.

### Verified

- The embedded core starts from a copied app outside the repository, accesses
  the existing `~/.nova4` data, reports healthy status, and shuts down cleanly.
- The standalone bundle passes strict deep code-signature verification and has
  no repository-path resource.

### Preserved

- Terminal development workflows, Ollama integration, SQLite memory, first-run
  setup, voice, calendar access, and confirmed actions remain compatible.

## 7.4.0 - 2026-08-03

### Added

- Five-step first-launch guide for Nova Core, microphone and speech recognition,
  Google Calendar, privacy and memory, confirmed actions, and launch at login.
- Real native microphone diagnostics from the setup guide, including macOS
  permission prompts and clear success or failure feedback.
- A Settings shortcut for reopening setup whenever preferences or permissions
  need to be reviewed.
- Native microphone and speech-recognition permission descriptions in the app
  bundle.

### Changed

- Voice status now exposes the configured recognition language, listening
  duration, and recognition mode to the native interface.
- Setup choices immediately update Nova's existing persisted local settings.

### Preserved

- Floating Glass interface, SQLite memory, Ollama chat, CLI behavior, Google
  Calendar integration, voice modes, and action confirmation remain compatible.

## 7.3.0 - 2026-08-03

### Added

- Floating Glass native macOS interface with a transparent title area,
  atmospheric background, translucent live cards, and smoother transitions.
- Functional Voice, Chat/History, and Settings navigation with persisted native
  controls for voice, spoken replies, memory privacy, live information, and
  confirmed actions.
- Transparent purple/cyan Nova orb asset integrated directly into the interface.
- Separate listening and speaking states in the native bridge, with expanding
  listening pulses and a live speaking waveform.
- Privacy-safe on-demand weather refresh in the Today card using the saved
  `user.location` memory and Open-Meteo.
- Natural weather phrases such as "What's the weather like here?" and
  "What's the temperature where I live?".

### Changed

- Voice replies in the native app now separate transcription, response
  generation, and speech playback so the interface reflects the real state.
- Glass cards, orb motion, status feedback, and Voice/Chat transitions have been
  visually refined while retaining conservative idle refresh rates.
- The macOS window now uses full-size content with transparent title chrome.

### Preserved

- Existing SQLite storage, Ollama chat behavior, semantic and episodic memory,
  deterministic exact-key recall, CLI commands, action confirmation, and voice
  terminal workflows remain compatible.
