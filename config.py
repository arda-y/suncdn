"""
Module for reading the config.yaml file.

Use the get function to get the value of a setting.

config.yaml file is read separately every time the get function is called to allow
hot swapping values without restarting the server on modification.
"""

import os
import logging
from typing import Any

import yaml

logger = logging.getLogger(__name__)

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(THIS_DIR, "config.yaml")


def get(setting_name: str, default_value: Any = None) -> Any:
    """
    Basically an `os.getenv()` function but for the config.yaml file.

    Returns the value of a setting from the config.yaml file with the given `setting_name`.

    If the `setting_name` is not found, or the config file is missing/invalid,
    the `default_value` is returned if provided, otherwise `None` is returned.
    """

    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as file:
            # safe_load is used to prevent code execution from the file
            cfg = yaml.safe_load(file)
    except FileNotFoundError:
        logger.error("Config file not found at %s", CONFIG_PATH)
        return default_value
    except yaml.YAMLError:
        logger.exception("Failed to parse config file at %s", CONFIG_PATH)
        return default_value

    if not isinstance(cfg, dict):
        # Empty file (yaml.safe_load returns None) or malformed top-level structure
        logger.error("Config file at %s did not contain a mapping", CONFIG_PATH)
        return default_value

    return cfg.get(setting_name, default_value)
