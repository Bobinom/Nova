from nova.plugins.base import NovaPlugin

class Plugin(NovaPlugin):
    plugin_id = "hello"
    display_name = "Hello Plugin"
    version = "1.0.0"

    def start(self):
        self.context.events.subscribe("user.message", self.on_message)

    def stop(self):
        self.context.events.unsubscribe("user.message", self.on_message)

    def on_message(self, event):
        self.context.logger.info("Observed: %s", event.payload.get("text", ""))
