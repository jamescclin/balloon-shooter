from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = ROOT / "config.yaml"


def load_config(path=DEFAULT_CONFIG):
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    model_path = Path(cfg["model"]["path"])
    if not model_path.is_absolute():
        cfg["model"]["path"] = str((ROOT / model_path).resolve())
    return cfg
