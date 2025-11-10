"""Configuration package - exposes settings from parent module"""
import sys
from pathlib import Path

# Import settings from the parent config.py module
parent_dir = Path(__file__).parent.parent
config_module_path = parent_dir / "config.py"

# Import from the config.py file (not this package)
import importlib.util
spec = importlib.util.spec_from_file_location("app_config", config_module_path)
config_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(config_module)

settings = config_module.settings
Settings = config_module.Settings

__all__ = ['settings', 'Settings']
