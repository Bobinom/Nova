import importlib.util
from nova.plugins.base import NovaPlugin, PluginContext

class PluginManager:
    def __init__(self, plugins_dir, event_bus, logger):
        self.plugins_dir = plugins_dir
        self.event_bus = event_bus
        self.logger = logger
        self._plugins = {}

    @property
    def loaded_count(self):
        return len(self._plugins)

    def discover(self):
        self.plugins_dir.mkdir(parents=True, exist_ok=True)
        for file_path in sorted(self.plugins_dir.glob("*.py")):
            if file_path.name.startswith("_"):
                continue
            try:
                spec = importlib.util.spec_from_file_location(
                    f"nova_external_{file_path.stem}", file_path
                )
                if spec is None or spec.loader is None:
                    raise ImportError(str(file_path))
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                cls = getattr(module, "Plugin", None)
                if not isinstance(cls, type) or not issubclass(cls, NovaPlugin):
                    self.logger.warning("Skipping invalid plugin: %s", file_path)
                    continue
                plugin = cls(PluginContext(
                    self.event_bus,
                    self.logger.getChild(f"plugin.{file_path.stem}")
                ))
                if plugin.plugin_id in self._plugins:
                    self.logger.warning("Duplicate plugin id: %s", plugin.plugin_id)
                    continue
                self._plugins[plugin.plugin_id] = plugin
            except Exception:
                self.logger.exception("Failed to load plugin: %s", file_path)

    def start_all(self):
        for plugin_id, plugin in self._plugins.items():
            try:
                plugin.start()
                self.logger.info("Started plugin: %s", plugin_id)
            except Exception:
                self.logger.exception("Failed to start plugin: %s", plugin_id)

    def stop_all(self):
        for plugin_id, plugin in reversed(list(self._plugins.items())):
            try:
                plugin.stop()
            except Exception:
                self.logger.exception("Failed to stop plugin: %s", plugin_id)

    def describe(self):
        return [{"id": p.plugin_id, "name": p.display_name, "version": p.version}
                for p in self._plugins.values()]
