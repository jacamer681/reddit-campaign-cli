"""TOML + env 설정 로딩."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

@dataclass
class CampaignConfig:
    docs_dir: str = "docs/reddit-30day"
    db_path: str = "data/campaign.db"


@dataclass
class Settings:
    post_delay: int = 5
    comment_delay: int = 10
    seeding_search_limit: int = 10
    seeding_max_comments: int = 3


@dataclass
class Config:
    campaign: CampaignConfig = field(default_factory=CampaignConfig)
    settings: Settings = field(default_factory=Settings)


def load_config(config_path: str | None = None) -> Config:
    """Load config from TOML file."""
    path = Path(config_path or "campaign.toml")
    cfg = Config()

    if path.exists():
        with open(path, "rb") as f:
            data = tomllib.load(f)

        if "campaign" in data:
            cfg.campaign = CampaignConfig(**data["campaign"])
        if "settings" in data:
            cfg.settings = Settings(**data["settings"])

    return cfg
