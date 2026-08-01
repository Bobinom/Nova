from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from nova import __version__
from nova.conversation.manager import ConversationManager
from nova.conversation.repository import ConversationRepository
from nova.core.events import EventBus
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
    def __init__(self) -> None:
        self.paths = NovaPaths.create()
        self.logger = configure_logging(self.paths.logs_dir)
        self.settings = SettingsManager(self.paths.settings_file)
        self.state = StateStore(self.paths.database_file)

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
