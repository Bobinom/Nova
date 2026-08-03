# Changelog

All notable Nova releases are documented here.

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
