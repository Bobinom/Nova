# Nova 5.0

Nova is a local, conversational AI assistant for macOS. It uses Ollama for
language-model responses and SQLite for persistent conversation, semantic, and
episodic memory.

## Highlights

- Structured Ollama chat with recent conversation history
- Deterministic exact-key recall for known facts
- Natural-language semantic memory search
- Explicit fact learning for identity, relationships, pets, work, projects,
  goals, and preferences
- Natural-language memory updates and forgetting
- Timestamped episodic memory for past discussions
- Relevant-only memory injection into Ollama prompts
- Episode filtering for failures, sensitive requests, and duplicate discussions
- Persistent local SQLite storage

## Requirements

- macOS
- Python 3.12
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
| `forget <memory-key>` | Delete one exact semantic-memory key |
| `history` | Show recent conversation turns |
| `clear-history` | Delete conversation turns |
| `episodes` | Inspect saved conversation episodes |
| `delete-episode <id>` | Delete one episode |
| `clear-episodes` | Delete all episodes |
| `quit` | Stop Nova safely |

## Privacy

- Nova stores its data locally in `~/.nova4/nova.db`.
- Semantic facts are saved only from supported explicit first-person statements.
- Questions, uncertain claims, and third-person claims are not learned as facts.
- Episodic memory skips trivial greetings, failed Ollama responses, and requests
  containing common secret-related terms such as passwords or API keys.
- Only relevant memories and past discussions are added to an Ollama prompt.
- Use the memory and episode commands to inspect or delete stored information.

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

Nova 5.0 keeps the existing SQLite tables and adds its memory structures without
requiring users to delete earlier Nova data.
