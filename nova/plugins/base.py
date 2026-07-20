from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass(frozen=True)
class PluginContext:
    events: object
    logger: object

class NovaPlugin(ABC):
    plugin_id = "unnamed"
    display_name = "Unnamed Plugin"
    version = "0.0.0"

    def __init__(self, context):
        self.context = context

    @abstractmethod
    def start(self): ...

    @abstractmethod
    def stop(self): ...
