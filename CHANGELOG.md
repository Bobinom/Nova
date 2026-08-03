# Changelog

All notable Nova releases are documented here.

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
