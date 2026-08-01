from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from nova import __version__
from nova.conversation.manager import ConversationManager
from nova.conversation.repository import ConversationRepository
from nova.core.events import EventBus
from nova.core.data import DataManager
from nova.core.logging import configure_logging
from nova.core.paths import NovaPaths
from nova.core.settings import SettingsManager
from nova.core.state import StateStore
from nova.llm.ollama import OllamaService
from nova.memory.engine import MemoryEngine
from nova.memory.repository import MemoryRepository
from nova.plugins.manager import PluginManager


@dataclass
class NovaStatus:
    version: str
    running: bool
    loaded_plugins: int
    memories: int
    conversation_turns: int
    conversation_episodes: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "running": self.running,
            "loaded_plugins": self.loaded_plugins,
            "memories": self.memories,
            "conversation_turns": self.conversation_turns,
            "conversation_episodes": self.conversation_episodes,
        }


class NovaApplication:
    def __init__(self, base_dir: Path | None = None) -> None:
        self.paths = NovaPaths.create(base_dir)
        self.logger = configure_logging(self.paths.logs_dir)
        self.settings = SettingsManager(self.paths.settings_file)
        self.state = StateStore(self.paths.database_file)
        self.data = DataManager(self.paths.database_file, self.paths.data_dir)

        self.events = EventBus(
            logger=self.logger,
        )

        self.plugins = PluginManager(
            plugins_dir=self.paths.plugins_dir,
            event_bus=self.events,
            logger=self.logger,
        )

        self.memory = MemoryEngine(
            repository=MemoryRepository(self.paths.database_file),
            events=self.events,
            logger=self.logger.getChild("memory"),
        )

        self.llm = OllamaService(
            model="llama3.2",
        )

        self.conversation = ConversationManager(
            repository=ConversationRepository(self.paths.database_file),
            memory=self.memory,
            events=self.events,
            logger=self.logger.getChild("conversation"),
            llm=self.llm,
            settings=self.settings,
        )

        self._running = False

    def start(self) -> None:
        if self._running:
            return

        self.logger.info("Starting Nova Core")

        self.settings.load()
        self.state.initialize()
        self.memory.initialize()
        self.conversation.initialize()
        self.plugins.discover()
        self.plugins.start_all()

        self._running = True

        self.events.emit(
            "nova.started",
            {
                "version": __version__,
            },
        )

        self.logger.info("Nova Core started")

    def stop(self) -> None:
        if not self._running:
            return

        self.logger.info("Stopping Nova Core")

        self.events.emit(
            "nova.stopping",
            {},
        )

        self.plugins.stop_all()
        self.conversation.close()
        self.memory.close()
        self.state.close()

        self._running = False

        self.logger.info("Nova Core stopped")

    def status(self) -> dict[str, Any]:
        return NovaStatus(
            version=__version__,
            running=self._running,
            loaded_plugins=self.plugins.loaded_count,
            memories=len(self.memory.list_memories()),
            conversation_turns=len(self.conversation.history(1000)),
            conversation_episodes=len(self.conversation.episodes(1000)),
        ).as_dict()

    def handle_message(self, text: str) -> dict[str, Any]:
        return self.conversation.handle(text)

    def privacy_audit(self) -> dict[str, Any]:
        memories = self.memory.list_memories()
        categories: dict[str, int] = {}
        for memory in memories:
            categories[memory.category] = categories.get(memory.category, 0) + 1
        return {
            "database": str(self.paths.database_file),
            "database_bytes": self.paths.database_file.stat().st_size,
            "semantic_memories": len(memories),
            "memory_categories": categories,
            "conversation_turns": len(self.conversation.history(1000)),
            "conversation_episodes": len(self.conversation.episodes(1000)),
            "conversation_sessions": len(self.conversation.sessions(1000)),
            "privacy": self.conversation.privacy_status(),
        }

    def export_memory(self, destination: Path | None = None) -> Path:
        payload = {
            "format": "nova-memory-export",
            "format_version": 1,
            "nova_version": __version__,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "audit": self.privacy_audit(),
            "semantic_memories": [
                memory.as_dict()
                for memory in self.memory.list_memories()
            ],
            "conversation_episodes": self.conversation.episodes(1000),
            "conversation_sessions": self.conversation.sessions(1000),
        }
        return self.data.export_json(payload, destination)

    def backup_data(self, destination: Path | None = None) -> Path:
        return self.data.backup(destination)

    def restore_data(self, backup_path: Path) -> Path:
        was_running = self._running
        if was_running:
            self.stop()
        try:
            return self.data.restore(backup_path)
        finally:
            if was_running:
                self.start()
