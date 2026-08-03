# Nova 7.7

Nova is a local, conversational AI assistant for macOS. It uses Ollama for
language-model responses and SQLite for persistent conversation, semantic, and
episodic memory.

## Highlights

- Structured Ollama chat with recent conversation history
- Deterministic exact-key recall for known facts
- Natural-language semantic memory search
- Explainable relevance scores with stronger weak-match filtering
- Reversible low-confidence memory archiving and duplicate consolidation
- Explicit fact learning for identity, relationships, pets, work, projects,
  goals, and preferences
- Natural-language memory updates and forgetting
- Timestamped episodic memory for past discussions
- Relevant-only memory injection into Ollama prompts
- Episode filtering for failures, sensitive requests, and duplicate discussions
- Persistent episode auto-save, confirmation, and retention controls
- Privacy audit, JSON memory export, and verified backup/restore
- Persistent multi-topic conversation sessions with compact summaries
- Versioned database migrations, startup integrity checks, and corruption quarantine
- Native macOS speech output with optional automatic spoken responses
- Built-in on-device macOS microphone transcription with native permissions
- Configurable recognition language and listening duration
- Hands-free listen, respond, and continue mode with spoken stop control
- Configurable wake phrase that ignores background speech until activated
- Opt-in live weather and sourced factual lookup with offline-safe failures
- Optional pluggable local transcription command fallback
- Confirm-before-execution apps, files, notes, reminders, calendar events, and web actions
- Native SwiftUI chat window and macOS menu-bar app connected to the same Nova core
- Global Option-Space quick access and optional launch at login
- Guided first-launch setup for Nova Core, voice permissions, Google Calendar,
  privacy, computer actions, and launch at login
- Standalone Apple-silicon macOS app with Nova Core and Python dependencies
  embedded inside the bundle
- Drag-to-Applications DMG installer and native Nova orb app icon
- Optional ElevenLabs custom voice with macOS Keychain credential storage,
  in-app testing, provider switching, and offline macOS fallback
- Hands-free wake-phrase mode in the standalone app with menu-bar controls,
  visible microphone state, spoken sleep control, and self-listening prevention
- Floating Glass native interface with an animated, transparent Nova orb
- Functional Voice, Chat/History, and Settings navigation
- Native controls for voice, spoken replies, memory privacy, live information,
  and confirmed computer actions
- Distinct real-time orb animations for listening, thinking, and speaking
- Privacy-safe local weather refresh using a saved location and Open-Meteo
- Google Calendar events through calendars connected to macOS Internet Accounts
- Live local CPU, memory, database, service, and macOS thermal-state dashboard
- Clickable Confirm and Cancel controls for pending computer actions
- Persistent local SQLite storage

## Requirements

- macOS
- Python 3.12
- Xcode for building the native Nova app
- Apple Command Line Tools (`xcode-select --install`) for terminal-only microphone setup
- [Ollama](https://ollama.com/) with the `llama3.2` model

Install the Ollama model once:

```bash
ollama pull llama3.2
```

## Setup

From the Nova project directory:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install --requirement requirements.txt
chmod +x start_nova.command
```

For development and tests:

```bash
.venv/bin/python -m pip install --requirement requirements-dev.txt
```

## Start Nova

Start Ollama if it is not already running:

```bash
ollama serve
```

Then start Nova in another terminal:

```bash
./start_nova.command
```

The launcher automatically uses `.venv/bin/python` when the virtual
environment exists. Set `PYTHON_BIN` to override it.

## Build the standalone macOS app

Install the development dependencies and build the locally signed app after
installing and opening Xcode once:

```bash
.venv/bin/python -m pip install --requirement requirements-dev.txt
./scripts/build_macos_app.sh
open dist/Nova.app
```

The resulting `dist/Nova.app` contains Nova Core, its Python runtime, Requests,
SQLite support, and the speech-helper source. It does not depend on the project
folder or `.venv` at runtime. This build currently targets Apple-silicon Macs.
Ollama remains a separate local service and must be installed with the
`llama3.2` model.

To create the drag-to-Applications installer:

```bash
./scripts/build_macos_dmg.sh
```

Open the versioned DMG under `dist/`, then drag Nova into Applications. These local builds
are ad-hoc signed for development; public distribution will require an Apple
Developer ID signature and notarization.

Nova appears as a sparkles icon in the menu bar and opens a native chat window.
The first launch opens a guided setup that checks Nova Core and lets you choose
voice, calendar, privacy, action, and login preferences. Optional permissions
can be skipped, and the guide can be reopened from **Settings > Setup**.
Closing the window hides it without stopping Nova. Press `Option-Space` from any
app to bring the chat back immediately, or choose **Open Nova** from the menu.
Enable **Launch at Login** there to start Nova automatically when you sign in.
Choose **Quit Nova** to stop both the interface and its embedded Nova Core. The
app uses the existing Ollama connection and `~/.nova4` data, memories, settings,
permissions, and actions.
The terminal launcher remains available and unchanged.

Generated app bundles and installer images under `dist/` are not committed.

The command-center interface starts in Voice mode. Use the microphone button for
one local transcript or switch to Chat to see recent history and type. Pending
computer actions appear as a confirmation card with **Confirm** and **Cancel**
buttons. Dashboard CPU and memory values are sampled locally. Because macOS does
not provide a safe public Celsius sensor API, Nova reports Apple's honest thermal
state (`Nominal`, `Warm`, `High`, or `Critical`) instead of inventing a temperature.

The Google Calendar card reads only Google or Google Workspace calendars already
connected under **System Settings > Internet Accounts**. Click the card once to
grant Nova Calendar access. No Google password or OAuth secret is stored by Nova.

### Nova 7.7 interface

Nova 7.7 retains the Floating Glass design with an atmospheric indigo
background, narrow navigation rail, translucent live cards, floating composer,
and central animated orb. The orb breathes gently while ready, emits expanding
cyan rings while listening, and displays a moving purple/cyan waveform while
Nova is speaking. A matching five-step setup guide now helps new users configure
the local engine, microphone and speech recognition, Google Calendar, privacy,
confirmed actions, and launch at login.

The app is now self-contained: its SwiftUI interface starts a frozen Nova Core
from inside the application bundle. You can move Nova into Applications or run
it from the DMG without keeping the repository beside it.

### ElevenLabs custom voice

Open **Settings > Voice**, select **ElevenLabs custom voice**, and enter your
Voice ID and API key. Nova stores the API key in macOS Keychain; it is never
written to `settings.json`, SQLite, Git, or diagnostic responses. Use **Test
voice** to hear a preview. If ElevenLabs is unavailable, normal spoken responses
fall back automatically to the built-in macOS voice.

ElevenLabs speech requires an internet connection, sends the response text to
ElevenLabs for synthesis, and may consume paid account credits. Switch **Voice
output** back to **Built-in macOS** for fully local speech.

### Hands-free app mode

Open **Settings > Voice** and enable **Hands-free wake phrase**, or use the same
toggle in Nova's menu-bar menu. Nova listens in short recognition windows for
the configured phrase (for example, "Hey Nova") while leaving chat and Settings
responsive. Say the phrase followed by a request, or say only the phrase and
wait for Nova to answer "Yes?" before continuing.

Say **"Hey Nova, go to sleep"** to disable persistent listening. Nova pauses the
microphone while it thinks and speaks, so it cannot activate itself from its own
ElevenLabs or macOS voice. Raw microphone audio is not saved; recognition uses
the configured on-device or automatic Apple Speech mode.

Enable **Natural follow-up conversation** to keep talking after Nova answers
without repeating "Hey Nova." Nova opens one short follow-up window after each
answer, preserves the current conversation context, and returns to wake-phrase
standby after silence. Say **"stop," "cancel," "never mind,"** or **"that's
all"** to close the conversation while keeping wake mode ready. Say **"go to
sleep"** during a follow-up to turn wake listening off completely. Confirmed
computer actions still accept the next spoken `yes` or `no` safely.

The navigation rail opens Voice, Chat with persisted conversation history, and
Settings. Settings provides native switches for voice mode, automatic spoken
responses, episode saving, memory confirmation, live information, and computer
actions. Changes are persisted by Nova Core and remain available to the CLI.
The current Ollama model is displayed honestly as read-only because Nova Core
does not yet expose a safe runtime model-switching setting.

The app separates microphone capture from speech playback so these animations
follow Nova's actual voice state. This native bridge change does not alter the
terminal `listen`, hands-free conversation, or wake-phrase commands.

The glass **Suggested** card can request current local weather from Open-Meteo. Nova uses
the exact `user.location` fact you previously saved, and sends it only when you
click **Refresh local weather** or explicitly ask a weather question. Live web
access must already be enabled with `live-on`.

## Memory examples

Nova learns explicit first-person facts:

```text
My girlfriend's name is Dunja.
My dog is Max.
I work at Espresso House.
I'm working on Nova.
My goal is to build a Jarvis-style assistant.
I prefer concise answers.
```

Nova also understands corrections and explicit forgetting:

```text
Actually, I work at IKEA now.
Dunja is no longer my girlfriend.
Forget where I live.
Forget what you know about my pets.
```

Search semantic and episodic memory naturally:

```text
What do you remember about my projects?
What did we discuss about upgrading my PC?
What did we discuss yesterday?
Continue our PC upgrade discussion.
```

## Commands

| Command | Purpose |
| --- | --- |
| `status` | Show Nova status and stored-item counts |
| `memory` or `memories` | Inspect semantic memories |
| `memory <category>` | Filter semantic memories by category |
| `memory-explain <query>` | Show why semantic memories match a query |
| `memory-maintain [minimum-confidence]` | Consolidate lists and archive weaker memories |
| `archived-memories` | Inspect reversible archived memories |
| `restore-memory <memory-key>` | Restore one archived semantic memory |
| `forget <memory-key>` | Delete one exact semantic-memory key |
| `history` | Show recent conversation turns |
| `clear-history` | Delete conversation turns |
| `episodes` | Inspect saved conversation episodes |
| `delete-episode <id>` | Delete one episode |
| `clear-episodes` | Delete all episodes |
| `privacy-status` | Show persistent memory privacy settings |
| `memory-auto <on\|off>` | Enable or disable automatic episode saving |
| `memory-confirm <on\|off>` | Require confirmation before saving facts |
| `memory-retention <count>` | Limit stored episodes by count; `0` is unlimited |
| `memory-retention-days <days>` | Delete older episodes; `0` disables age expiry |
| `remember-conversation` | Manually save the previous conversation |
| `dont-save-conversation` | Remove the most recently saved conversation |
| `forget-last-conversation` | Forget the most recent episode |
| `privacy-audit` | Summarize locally stored memory and privacy settings |
| `live-status` | Show web-access permission and fixed information providers |
| `live-on` / `live-off` | Allow or block queries to approved providers |
| `web-search <query>` | Search for a sourced factual answer |
| `export-memory [path]` | Export readable semantic and episodic memory JSON |
| `backup [path]` | Create and verify a consistent SQLite backup |
| `restore <backup-path>` | Restore after typed confirmation and create a recovery backup |
| `sessions` | Inspect consolidated conversation sessions |
| `session-summary` | Summarize the current meaningful session |
| `delete-session <id>` | Delete one session summary |
| `clear-sessions` | Delete all session summaries |
| `health` | Show database integrity and schema health |
| `recoveries` | List quarantined corrupted database files |
| `voice-status` | Show speech input/output availability and settings |
| `voice-on` / `voice-off` | Enable or disable voice mode |
| `voice-auto <on\|off>` | Speak Nova's responses automatically |
| `say <text>` | Speak text immediately with macOS `say` |
| `listen` | Capture one local transcript and send it to Nova |
| `conversation-on` | Start hands-free voice conversation until spoken stop or Ctrl+C |
| `wake-on` | Wait for the configured wake phrase before handling speech |
| `wake-phrase <phrase>` | Set a one-to-three-word wake phrase; default is `Nova` |
| `voice-setup` | Build and verify Nova's signed native microphone helper |
| `voice-locale <locale>` | Set recognition language, such as `en-US` or `sv-SE` |
| `voice-duration <seconds>` | Set one-shot listening time from 2–20 seconds |
| `voice-recognition <on-device\|automatic>` | Choose private local or Apple-assisted recognition |
| `voice-input <local-command>` | Configure a local command that prints one transcript |
| `voice-input-clear` | Remove the configured transcription command |
| `actions-status` | Show action permissions and pending confirmation |
| `actions-on` / `actions-off` | Enable or disable computer actions |
| `action-websites <on\|off>` | Allow or block confirmed website actions |
| `quit` | Stop Nova safely |

## Voice and actions

Turn on native speech and optionally speak every answer:

```text
voice-on
voice-auto on
say Nova voice is ready
```

Nova uses the built-in macOS `say` command, so speech output needs no cloud
service or additional Python package. Nova 6.2 also builds a small signed helper
that uses Apple's Speech and AVFoundation frameworks for on-device transcription.
Set it up once, choose a language if needed, and listen:

```text
voice-setup
voice-locale en-US
voice-duration 7
voice-recognition on-device
listen
```

The first `listen` asks macOS for Microphone and Speech Recognition permission.
Audio is processed through Apple's on-device recognizer and is not sent to
Ollama. Nova records only the resulting transcript in its normal conversation
history. If the built-in provider is unavailable, `voice-input` can still select
a trusted local command. That command is stored as an argument list and executed
directly without a shell.

If on-device recognition cannot understand the microphone audio, use
`voice-recognition automatic` to match macOS Dictation behavior. In automatic
mode, Apple decides whether recognition runs locally or on its servers, so
speech audio may be sent to Apple for processing. Return to private local
recognition with `voice-recognition on-device`.

For a continuous spoken conversation, enable voice and start hands-free mode:

```text
voice-on
conversation-on
```

Nova repeatedly listens, answers aloud, and listens again. Say `Nova, stop` to
return to the normal prompt, or press `Ctrl+C` to interrupt hands-free mode.
Temporary recognition failures are reported and the session continues. Spoken
action requests still use Nova's existing confirmation requirement; answer
`yes` or `no` during the next listening turn.

For wake phrase mode, say the wake phrase and request together:

```text
voice-on
wake-on
```

Then say `Nova, open Safari` or say `Nova`, wait for `Yes?`, and speak the
request in the next listening window. Background speech without the wake phrase
is ignored. Say `Nova, go to sleep` or press `Ctrl+C` to return to the prompt.
Change the phrase with `wake-phrase Hey Nova`. After an action request, Nova
accepts the required spoken `yes` or `no` without making you repeat the wake
phrase.

## Live information

Live information is off by default. Enable it explicitly:

```text
live-on
```

Nova can then answer requests such as `What's the weather in Malmö?`, `Look up
Sweden`, or `How many people live in Sweden?`. Weather uses Open-Meteo. Factual
lookup uses DuckDuckGo with a Wikipedia fallback. Nova only contacts these fixed
provider endpoints and prints source links with successful results. Voice modes
speak the concise answer without reading URLs aloud.

Enabling this feature sends the relevant location or search query to those
providers. Use `live-off` to block all live requests again. If the providers or
internet connection are unavailable, Nova reports that clearly instead of
inventing a current answer.

If you previously configured `voice-input`, run `voice-input-clear` to return to
Nova's built-in on-device provider.

If Nova reports that no speech was detected, open **System Settings > Sound >
Input**, select the microphone you are actually using, and confirm that its
input-level meter moves while you speak. Connected AirPods or Bluetooth headsets
can become the default input even when you intend to use the Mac's microphone.

Computer actions are deliberately narrow. Nova can open an allowlisted macOS app,
open an existing file or folder, create a note, reminder, or calendar event, and
perform a browser search. Website opening and browser searches are off by default.
Actions themselves are also off until explicitly enabled, and every recognized
action requires a separate confirmation:

```text
nova> actions-on
Computer actions enabled.
nova> Open Safari
Nova: Confirm action: open Safari? Reply yes or no.
nova> yes
Nova: Done. I opened Safari.
```

Examples of expanded actions:

```text
Create a note called Shopping saying Buy milk
Remind me to check Nova tomorrow at 9 am
Create calendar event Nova demo tomorrow at 3 pm for 30 minutes
Open file ~/Projects/Nova/README.md
Search the web for Nova AI assistant
```

Dates use `today`, `tomorrow`, or `on YYYY-MM-DD`; times support 12-hour or
24-hour input. Reminders without a date are also supported. Browser searches
require `action-websites on`. macOS may ask for Automation access the first time
Nova creates a note, reminder, or calendar event.

## Privacy

- Nova stores its data locally in `~/.nova4/nova.db`.
- Semantic facts are saved only from supported explicit first-person statements.
- Questions, uncertain claims, and third-person claims are not learned as facts.
- Episodic memory skips trivial greetings, failed Ollama responses, and requests
  containing common secret-related terms such as passwords or API keys.
- Only relevant memories and past discussions are added to an Ollama prompt.
- At most three strongly matching semantic memories are added to each prompt.
- Maintenance archives low-confidence memories instead of deleting them.
- Use the memory and episode commands to inspect or delete stored information.
- Privacy settings persist in `~/.nova4/settings.json`.
- Protected mode (`memory-confirm on`) asks before saving supported semantic facts.
- JSON exports omit raw conversation history but include semantic memories and episodes.
- Restore validates SQLite integrity and required Nova tables before replacing data.
- Every restore first creates a timestamped recovery backup of the current database.
- Startup checks database integrity before opening long-lived connections.
- Corrupted databases are preserved under `~/.nova4/recoveries/` before Nova creates a healthy replacement.
- Voice output stays local through macOS. On-device recognition keeps microphone
  processing local; automatic recognition may send speech to Apple.
- Live information is disabled by default and uses only fixed provider endpoints.
- Actions are disabled by default, never invoke a shell, and never execute before explicit confirmation.
- Note and schedule text is passed to fixed AppleScript programs only as data arguments.
- File and folder actions require an existing path before execution.
- Website actions and browser searches are disabled by default; URLs accept only HTTP or HTTPS.
- The native app communicates with Nova through a local process pipe and does not add a network server.
- Google calendar events are read locally through macOS EventKit from accounts connected to this Mac.
- System health sampling stays local and reports macOS thermal state rather than a fabricated temperature.

Sensitive-term filtering is a safeguard, not a guarantee. Do not give Nova
passwords, private keys, payment-card details, or other secrets.

## Tests

Run the full suite:

```bash
.venv/bin/python -m pytest -q
```

GitHub Actions runs the same suite with Python 3.12 for pull requests and pushes
to `main`.

## Data compatibility

Nova 7.2 keeps the Nova 5.5 SQLite schema and memory archive without
requiring users to delete earlier Nova data.
