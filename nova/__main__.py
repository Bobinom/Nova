from nova.app import NovaApplication


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


def main() -> None:
    app = NovaApplication()
    app.start()

    print("Nova 4.2.1 Conversation Polish is running.")
    print(f"Data directory: {app.paths.data_dir}")
    print("Commands:")
    print("  status")
    print("  memory")
    print("  memory <category>")
    print("  memories")
    print("  history")
    print("  clear-history")
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

            if raw in {"memory", "memories"}:
                _print_memories(app)
                continue

            if raw.startswith("memory "):
                _print_memories(app, raw[7:].strip())
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
