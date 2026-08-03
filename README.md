# Nova 6.5

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
- Persistent local SQLite storage

## Requirements

- macOS
- Python 3.12
- Apple Command Line Tools (`xcode-select --install`) for built-in microphone setup
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

Nova 6.5 keeps the Nova 5.5 SQLite schema and memory archive without
requiring users to delete earlier Nova data.
