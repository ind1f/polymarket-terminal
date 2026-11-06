import os
from pathlib import Path

ENV_PATH = Path(__file__).parents[1] / ".env"


def load_env(path: Path = ENV_PATH) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def set_env_value(key: str, value: str, path: Path = ENV_PATH) -> None:
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    kept = [line for line in lines if not line.strip().startswith(f"{key}=")]
    kept.append(f"{key}={value}")
    path.write_text("\n".join(kept) + "\n", encoding="utf-8")
