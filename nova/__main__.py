import shlex
from pathlib import Path

from nova import __version__
from nova.app import NovaApplication
from nova.voice.conversation import HandsFreeConversation
from nova.voice.wake import WakePhraseSession


def _print_memories(app: NovaApplication, category: str | None = None) -> None:
    category_aliases = {
        "identity": "identity",
        "identities": "identity",
        "preference": "preference",
        "preferences": "preference",
    }
    normalized_category = category_aliases.get(category.lower(), category) if category else None
    memories = app.memory.list_memories(normalized_category)

    if not memories:
        print("No memories stored.")
        return

    groups: dict[str, list] = {}
    for memory in memories:
        groups.setdefault(memory.category, []).append(memory)

    labels = {
        "identity": "Identity",
        "preference": "Preferences",
        "general": "General",
    }

    for group_name, items in groups.items():
        print(labels.get(group_name, group_name.title()))
        print("-" * len(labels.get(group_name, group_name.title())))

        for memory in items:
            display_names = {
                "user.name": "Name",
                "user.favorite_color": "Favorite color",
                "user.liked_colors": "Also likes",
                "user.location": "Location",
                "user.birthday": "Birthday",
            }
            label = display_names.get(memory.key, memory.key)
            value = memory.value
            if isinstance(value, list):
                value = ", ".join(str(item) for item in value)
            print(f"{label}: {value}")
        print()


def _print_episodes(app: NovaApplication) -> None:
    episodes = app.conversation.episodes()
    if not episodes:
        print("No conversation episodes stored.")
        return
    for episode in episodes:
        print(
            f"[{episode['id']}] {episode['created_at']} "
            f"({episode['topic']}): {episode['summary']}"
        )


def _print_sessions(app: NovaApplication) -> None:
    sessions = app.conversation.sessions()
    if not sessions:
        print("No conversation sessions stored.")
        return
    for session in sessions:
        status = "active" if session["ended_at"] is None else "ended"
        print(
            f"[{session['id']}] {status}, {session['episode_count']} episode(s), "
            f"{session['topic']}: {session['summary']}"
        )


def _run_hands_free_conversation(app: NovaApplication) -> None:
    session = HandsFreeConversation(app.voice, app.handle_message)
    print(
        "Hands-free conversation started. Say 'Nova, stop' or press "
        "Ctrl+C to finish."
    )
    reason = session.run(
        on_listening=lambda: print("Listening..."),
        on_transcript=lambda text: print(f"You: {text}"),
        on_response=lambda text: print(f"Nova: {text}"),
        on_error=lambda text: print(f"Hands-free error: {text}"),
    )
    if reason == "interrupted":
        print("Hands-free conversation interrupted.")
    else:
        print("Hands-free conversation stopped.")


def _run_wake_phrase_mode(app: NovaApplication) -> None:
    phrase = str(app.voice.status()["wake_phrase"])
    session = WakePhraseSession(app.voice, app.handle_message, phrase)
    print(
        f"Wake phrase mode started. Say '{phrase}' followed by a request. "
        f"Say '{phrase}, go to sleep' or press Ctrl+C to finish."
    )
    reason = session.run(
        on_activation=lambda text: print(f"Wake phrase detected: {text}"),
        on_transcript=lambda text: print(f"You: {text}"),
        on_response=lambda text: print(f"Nova: {text}"),
        on_error=lambda text: print(f"Wake phrase error: {text}"),
    )
    if reason == "interrupted":
        print("Wake phrase mode interrupted.")
    else:
        print("Wake phrase mode stopped.")


def main() -> None:
    app = NovaApplication()
    app.start()

    print(f"Nova {__version__} is running.")
    print(f"Data directory: {app.paths.data_dir}")
    print("Commands:")
    print("  status")
    print("  memory")
    print("  memory <category>")
    print("  memory-explain <query>")
    print("  memory-maintain [minimum-confidence]")
    print("  archived-memories")
    print("  restore-memory <memory-key>")
    print("  memories")
    print("  history")
    print("  clear-history")
    print("  episodes")
    print("  delete-episode <id>")
    print("  clear-episodes")
    print("  privacy-status")
    print("  memory-auto <on|off>")
    print("  memory-confirm <on|off>")
    print("  memory-retention <count>")
    print("  memory-retention-days <days>")
    print("  remember-conversation")
    print("  dont-save-conversation")
    print("  forget-last-conversation")
    print("  privacy-audit")
    print("  live-status")
    print("  live-on | live-off")
    print("  web-search <query>")
    print("  export-memory [path]")
    print("  backup [path]")
    print("  restore <backup-path>")
    print("  sessions")
    print("  session-summary")
    print("  delete-session <id>")
    print("  clear-sessions")
    print("  health")
    print("  recoveries")
    print("  voice-status")
    print("  voice-on | voice-off")
    print("  voice-auto <on|off>")
    print("  say <text>")
    print("  listen")
    print("  conversation-on")
    print("  wake-on")
    print("  wake-phrase <phrase>")
    print("  voice-setup")
    print("  voice-locale <locale>")
    print("  voice-duration <seconds>")
    print("  voice-recognition <on-device|automatic>")
    print("  voice-input <local-command>")
    print("  voice-input-clear")
    print("  actions-status")
    print("  actions-on | actions-off")
    print("  action-websites <on|off>")
    print("  forget <memory-key>")
    print("  quit")

    try:
        while True:
            raw = input("nova> ").strip()

            if not raw:
                continue

            if raw in {"quit", "exit"}:
                break

            if raw == "status":
                print(app.status())
                continue

            if raw == "health":
                print(app.database_health())
                continue

            if raw == "recoveries":
                recoveries = app.database_recoveries()
                if recoveries:
                    for recovery in recoveries:
                        print(recovery)
                else:
                    print("No quarantined databases.")
                continue

            if raw == "voice-status":
                print(app.voice.status())
                continue

            if raw in {"voice-on", "voice-off"}:
                enabled = raw == "voice-on"
                app.voice.set_enabled(enabled)
                print(f"Voice mode {'enabled' if enabled else 'disabled'}.")
                continue

            if raw.startswith("voice-auto "):
                value = raw[len("voice-auto "):].strip().lower()
                if value not in {"on", "off"}:
                    print("Use: voice-auto <on|off>")
                else:
                    app.voice.set_auto_speak(value == "on")
                    print(f"Automatic speech {value}.")
                continue

            if raw.startswith("say "):
                try:
                    app.voice.speak(raw[len("say "):].strip(), force=True)
                except (OSError, RuntimeError, ValueError) as exc:
                    print(f"Speech failed: {exc}")
                continue

            if raw == "listen":
                print("Listening...")
                try:
                    result = app.listen_and_respond()
                except (OSError, RuntimeError, ValueError) as exc:
                    print(f"Listening failed: {exc}")
                else:
                    print(f"You: {result['transcript']}")
                    print(f"Nova: {result['response']}")
                continue

            if raw == "conversation-on":
                if not app.voice.status()["enabled"]:
                    print("Voice mode is disabled. Use voice-on first.")
                else:
                    _run_hands_free_conversation(app)
                continue

            if raw == "wake-on":
                if not app.voice.status()["enabled"]:
                    print("Voice mode is disabled. Use voice-on first.")
                else:
                    _run_wake_phrase_mode(app)
                continue

            if raw.startswith("wake-phrase "):
                phrase = raw[len("wake-phrase "):].strip()
                try:
                    app.voice.set_wake_phrase(phrase)
                except ValueError as exc:
                    print(f"Invalid wake phrase: {exc}")
                else:
                    configured = app.voice.status()["wake_phrase"]
                    print(f"Wake phrase set to {configured}.")
                continue

            if raw == "voice-setup":
                try:
                    setup = app.voice.setup_input()
                except (OSError, RuntimeError, ValueError) as exc:
                    print(f"Voice setup failed: {exc}")
                else:
                    print(
                        "Built-in microphone input is ready for "
                        f"{setup['locale']}."
                    )
                    print(
                        "The first listen will request Microphone and "
                        "Speech Recognition permission."
                    )
                continue

            if raw.startswith("voice-locale "):
                locale = raw[len("voice-locale "):].strip()
                try:
                    app.voice.set_locale(locale)
                except ValueError as exc:
                    print(f"Invalid locale: {exc}")
                else:
                    print(f"Voice recognition locale set to {locale}.")
                continue

            if raw.startswith("voice-duration "):
                value = raw[len("voice-duration "):].strip()
                if not value.isdigit():
                    print("Use: voice-duration <seconds>")
                else:
                    app.voice.set_duration(int(value))
                    print(
                        "Listening duration set to "
                        f"{app.voice.status()['listen_seconds']} seconds."
                    )
                continue

            if raw.startswith("voice-recognition "):
                mode = raw[len("voice-recognition "):].strip().lower()
                try:
                    app.voice.set_recognition_mode(mode)
                except ValueError as exc:
                    print(f"Invalid recognition mode: {exc}")
                else:
                    if mode == "automatic":
                        print(
                            "Apple-assisted recognition enabled. Speech may "
                            "be sent to Apple for processing."
                        )
                    else:
                        print("Private on-device recognition enabled.")
                continue

            if raw.startswith("voice-input "):
                try:
                    command = shlex.split(raw[len("voice-input "):].strip())
                except ValueError as exc:
                    print(f"Invalid command: {exc}")
                else:
                    app.voice.set_input_command(command)
                    print("Local microphone transcription command saved.")
                continue

            if raw == "voice-input-clear":
                app.voice.set_input_command([])
                print("Local microphone transcription command cleared.")
                continue

            if raw == "actions-status":
                print(app.actions.status())
                continue

            if raw in {"actions-on", "actions-off"}:
                enabled = raw == "actions-on"
                app.actions.set_enabled(enabled)
                print(f"Computer actions {'enabled' if enabled else 'disabled'}.")
                continue

            if raw.startswith("action-websites "):
                value = raw[len("action-websites "):].strip().lower()
                if value not in {"on", "off"}:
                    print("Use: action-websites <on|off>")
                else:
                    app.actions.set_websites_enabled(value == "on")
                    print(f"Website actions {value}.")
                continue

            if raw in {"memory", "memories"}:
                _print_memories(app)
                continue

            if raw.startswith("memory "):
                _print_memories(app, raw[7:].strip())
                continue

            if raw.startswith("memory-explain "):
                query = raw[len("memory-explain "):].strip()
                explanation = app.memory.explain_search(query)
                if not explanation["matches"]:
                    print("No relevant memories found.")
                else:
                    for match in explanation["matches"]:
                        memory = match["memory"]
                        reasons = "; ".join(match["reasons"])
                        print(
                            f"{memory['key']} (score {match['score']}): {reasons}"
                        )
                continue

            if raw == "memory-maintain" or raw.startswith("memory-maintain "):
                value = raw[len("memory-maintain"):].strip()
                try:
                    threshold = float(value) if value else 0.5
                except ValueError:
                    print("Use: memory-maintain [minimum-confidence]")
                else:
                    print(app.memory.maintain(threshold))
                continue

            if raw == "archived-memories":
                archived = app.memory.archived_memories()
                if not archived:
                    print("No archived memories.")
                else:
                    for memory in archived:
                        print(
                            f"{memory['key']}: {memory['value']} "
                            f"({memory['reason']})"
                        )
                continue

            if raw.startswith("restore-memory "):
                key = raw[len("restore-memory "):].strip()
                restored = app.memory.restore_archived(key)
                print("Memory restored." if restored else "Archived memory not found.")
                continue

            if raw == "history":
                history = app.conversation.history()
                if not history:
                    print("No conversation history.")
                else:
                    for turn in history:
                        print(f"{turn['role']}: {turn['text']}")
                continue

            if raw == "clear-history":
                app.conversation.clear_history()
                print("Conversation history cleared.")
                continue

            if raw == "episodes":
                _print_episodes(app)
                continue

            if raw == "sessions":
                _print_sessions(app)
                continue

            if raw == "session-summary":
                result = app.handle_message("Summarize this session")
                print(f"Nova: {result['response']}")
                continue

            if raw.startswith("delete-session "):
                session_id = raw[len("delete-session "):].strip()
                if not session_id.isdigit():
                    print("Session ID must be a number.")
                else:
                    deleted = app.conversation.delete_session(int(session_id))
                    print("Session deleted." if deleted else "Session not found.")
                continue

            if raw == "clear-sessions":
                app.conversation.clear_sessions()
                print("Conversation sessions cleared.")
                continue

            if raw.startswith("delete-episode "):
                episode_id = raw[15:].strip()
                if not episode_id.isdigit():
                    print("Episode ID must be a number.")
                else:
                    deleted = app.conversation.delete_episode(int(episode_id))
                    print("Episode deleted." if deleted else "Episode not found.")
                continue

            if raw == "clear-episodes":
                app.conversation.clear_episodes()
                print("Conversation episodes cleared.")
                continue

            if raw == "privacy-status":
                print(app.conversation.privacy_status())
                continue

            if raw == "privacy-audit":
                print(app.privacy_audit())
                continue

            if raw == "live-status":
                print(app.live.status())
                continue

            if raw in {"live-on", "live-off"}:
                enabled = raw == "live-on"
                app.live.set_enabled(enabled)
                if enabled:
                    print(
                        "Live information enabled. Weather and search queries "
                        "may be sent to Open-Meteo, DuckDuckGo, or Wikipedia."
                    )
                else:
                    print("Live information disabled.")
                continue

            if raw.startswith("web-search "):
                query = raw[len("web-search "):].strip()
                result = app.handle_message(f"Search the web for {query}")
                print(f"Nova: {result['response']}")
                continue

            if raw == "export-memory" or raw.startswith("export-memory "):
                value = raw[len("export-memory"):].strip()
                destination = Path(value) if value else None
                try:
                    exported = app.export_memory(destination)
                except (OSError, ValueError) as exc:
                    print(f"Export failed: {exc}")
                else:
                    print(f"Memory export created: {exported}")
                continue

            if raw == "backup" or raw.startswith("backup "):
                value = raw[len("backup"):].strip()
                destination = Path(value) if value else None
                try:
                    backup = app.backup_data(destination)
                except (OSError, ValueError) as exc:
                    print(f"Backup failed: {exc}")
                else:
                    print(f"Verified backup created: {backup}")
                continue

            if raw.startswith("restore "):
                backup_path = Path(raw[len("restore "):].strip())
                confirmation = input(
                    "Restore this backup and replace current Nova data? "
                    "Type RESTORE to continue: "
                )
                if confirmation != "RESTORE":
                    print("Restore cancelled.")
                    continue
                try:
                    recovery = app.restore_data(backup_path)
                except (OSError, ValueError) as exc:
                    print(f"Restore failed: {exc}")
                else:
                    print(
                        "Restore completed. Pre-restore recovery backup: "
                        f"{recovery}"
                    )
                continue

            if raw.startswith("memory-auto "):
                value = raw[12:].strip().lower()
                if value not in {"on", "off"}:
                    print("Use: memory-auto <on|off>")
                else:
                    app.conversation.set_episode_auto_save(value == "on")
                    print(f"Episode auto-save {value}.")
                continue

            if raw.startswith("memory-confirm "):
                value = raw[15:].strip().lower()
                if value not in {"on", "off"}:
                    print("Use: memory-confirm <on|off>")
                else:
                    app.conversation.set_semantic_confirmation(value == "on")
                    print(f"Semantic memory confirmation {value}.")
                continue

            if raw.startswith("memory-retention-days "):
                value = raw[22:].strip()
                if not value.isdigit():
                    print("Use: memory-retention-days <days>")
                else:
                    deleted = app.conversation.set_episode_retention(
                        retention_days=int(value),
                    )
                    print(f"Retention updated; {deleted} episode(s) removed.")
                continue

            if raw.startswith("memory-retention "):
                value = raw[17:].strip()
                if not value.isdigit():
                    print("Use: memory-retention <count>")
                else:
                    deleted = app.conversation.set_episode_retention(
                        max_episodes=int(value),
                    )
                    print(f"Retention updated; {deleted} episode(s) removed.")
                continue

            if raw in {
                "remember-conversation",
                "dont-save-conversation",
                "forget-last-conversation",
            }:
                phrases = {
                    "remember-conversation": "Remember this conversation",
                    "dont-save-conversation": "Don't save this conversation",
                    "forget-last-conversation": "Forget our last conversation",
                }
                result = app.handle_message(phrases[raw])
                print(f"Nova: {result['response']}")
                continue

            if raw.startswith("forget "):
                key = raw[7:].strip()
                print("Forgotten." if app.memory.forget(key) else "Memory not found.")
                continue

            result = app.handle_message(raw)
            print(f"Nova: {result['response']}")
    except (KeyboardInterrupt, EOFError):
        pass
    finally:
        app.stop()
        print("\nNova stopped safely.")


if __name__ == "__main__":
    main()
