from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class NovaPaths:
    data_dir: Path
    logs_dir: Path
    plugins_dir: Path
    settings_file: Path
    database_file: Path

    @classmethod
    def create(cls, base_dir=None):
        data_dir = (base_dir or Path.home() / ".nova4").expanduser().resolve()
        logs_dir = data_dir / "logs"
        plugins_dir = data_dir / "plugins"
        for directory in (data_dir, logs_dir, plugins_dir):
            directory.mkdir(parents=True, exist_ok=True)
        return cls(data_dir, logs_dir, plugins_dir,
                   data_dir / "settings.json", data_dir / "nova.db")
