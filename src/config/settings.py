"""
Configuration settings for the application.
"""

from pathlib import Path

import yaml


class Config:
    """Load and manage configuration from YAML file (singleton)."""

    _instance = None
    _config = None

    def __new__(cls, config_file: str = None):
        """Return the cached instance if YAML is already loaded."""
        if cls._instance is not None:
            return cls._instance
        cls._instance = super().__new__(cls)
        base_path = Path(__file__).parent
        config_path = (
            base_path / "prompts.yaml"
            if config_file is None
            else Path(config_file)
        )
        with open(config_path, "r") as f:
            cls._config = yaml.safe_load(f)
        return cls._instance

    def prompt(self, key: str) -> str:
        """
        Retrieve a prompt from configuration.

        Args:
            key: The prompt key.

        Returns:
            The prompt template string.
        """
        return self._config["prompts"][key]
