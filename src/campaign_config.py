"""캠페인 설정 파일 (campaign.toml) 로더.

범용 Reddit 마케팅 자동화 — config 하나로 어떤 제품이든 캠페인 실행.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

CAMPAIGN_FILE = "campaign.toml"


@dataclass
class SubTarget:
    sub: str
    keywords: list[str] = field(default_factory=list)


@dataclass
class PostTarget:
    sub: str
    title_hint: str = ""


@dataclass
class Limits:
    karma_comments_per_day: int = 4
    seed_comments_per_day: int = 2
    posts_per_day: int = 1
    min_delay_seconds: int = 8
    max_delay_seconds: int = 25


@dataclass
class CampaignConfig:
    # Product
    product_name: str = ""
    product_url: str = ""
    tagline: str = ""
    category: str = "developer_tool"

    # Reddit account
    reddit_username: str = ""

    # Targets
    karma_subs: list[SubTarget] = field(default_factory=list)
    seed_subs: list[SubTarget] = field(default_factory=list)
    post_subs: list[PostTarget] = field(default_factory=list)

    # Content style
    karma_tone: str = "helpful_expert"
    seed_tone: str = "casual_mention"

    # Limits
    limits: Limits = field(default_factory=Limits)

    # Post content templates
    post_templates: list[dict] = field(default_factory=list)


def load_campaign(path: str | None = None) -> CampaignConfig:
    """campaign.toml 로드."""
    p = Path(path or CAMPAIGN_FILE)
    if not p.exists():
        raise FileNotFoundError(f"캠페인 설정 파일 없음: {p}")

    with open(p, "rb") as f:
        data = tomllib.load(f)

    cfg = CampaignConfig()

    # [product]
    if prod := data.get("product"):
        cfg.product_name = prod.get("name", "")
        cfg.product_url = prod.get("url", "")
        cfg.tagline = prod.get("tagline", "")
        cfg.category = prod.get("category", "developer_tool")

    # [reddit]
    if reddit := data.get("reddit"):
        cfg.reddit_username = reddit.get("username", "")

    # [targets]
    if targets := data.get("targets"):
        for item in targets.get("karma_subs", []):
            if isinstance(item, dict):
                cfg.karma_subs.append(SubTarget(
                    sub=item["sub"],
                    keywords=item.get("keywords", []),
                ))
        for item in targets.get("seed_subs", []):
            if isinstance(item, dict):
                cfg.seed_subs.append(SubTarget(
                    sub=item["sub"],
                    keywords=item.get("keywords", []),
                ))
        for item in targets.get("post_subs", []):
            if isinstance(item, str):
                cfg.post_subs.append(PostTarget(sub=item))
            elif isinstance(item, dict):
                cfg.post_subs.append(PostTarget(
                    sub=item["sub"],
                    title_hint=item.get("title_hint", ""),
                ))

    # [content]
    if content := data.get("content"):
        cfg.karma_tone = content.get("karma_tone", "helpful_expert")
        cfg.seed_tone = content.get("seed_tone", "casual_mention")

    # [limits]
    if limits := data.get("limits"):
        cfg.limits = Limits(
            karma_comments_per_day=limits.get("karma_comments_per_day", 4),
            seed_comments_per_day=limits.get("seed_comments_per_day", 2),
            posts_per_day=limits.get("posts_per_day", 1),
            min_delay_seconds=limits.get("min_delay_seconds", 8),
            max_delay_seconds=limits.get("max_delay_seconds", 25),
        )

    # [posts] — optional post content templates
    if posts := data.get("posts"):
        for item in posts:
            if isinstance(item, dict):
                cfg.post_templates.append(item)

    return cfg


def save_campaign(cfg: CampaignConfig, path: str | None = None):
    """CampaignConfig를 TOML 형식으로 저장."""
    p = Path(path or CAMPAIGN_FILE)

    lines = [
        '[product]',
        f'name = "{cfg.product_name}"',
        f'url = "{cfg.product_url}"',
        f'tagline = "{cfg.tagline}"',
        f'category = "{cfg.category}"',
        '',
        '[reddit]',
        f'username = "{cfg.reddit_username}"',
        '',
        '[targets]',
    ]

    # karma_subs
    lines.append('karma_subs = [')
    for st in cfg.karma_subs:
        kw_str = ", ".join(f'"{k}"' for k in st.keywords)
        lines.append(f'    {{sub = "{st.sub}", keywords = [{kw_str}]}},')
    lines.append(']')

    # seed_subs
    lines.append('seed_subs = [')
    for st in cfg.seed_subs:
        kw_str = ", ".join(f'"{k}"' for k in st.keywords)
        lines.append(f'    {{sub = "{st.sub}", keywords = [{kw_str}]}},')
    lines.append(']')

    # post_subs
    lines.append('post_subs = [')
    for pt in cfg.post_subs:
        if pt.title_hint:
            lines.append(f'    {{sub = "{pt.sub}", title_hint = "{pt.title_hint}"}},')
        else:
            lines.append(f'    "{pt.sub}",')
    lines.append(']')

    lines.extend([
        '',
        '[content]',
        f'karma_tone = "{cfg.karma_tone}"',
        f'seed_tone = "{cfg.seed_tone}"',
        '',
        '[limits]',
        f'karma_comments_per_day = {cfg.limits.karma_comments_per_day}',
        f'seed_comments_per_day = {cfg.limits.seed_comments_per_day}',
        f'posts_per_day = {cfg.limits.posts_per_day}',
        f'min_delay_seconds = {cfg.limits.min_delay_seconds}',
        f'max_delay_seconds = {cfg.limits.max_delay_seconds}',
    ])

    p.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def campaign_exists(path: str | None = None) -> bool:
    """캠페인 설정 파일 존재 여부."""
    return Path(path or CAMPAIGN_FILE).exists()


def to_dict(cfg: CampaignConfig) -> dict:
    """CampaignConfig를 JSON-safe dict로 변환."""
    return {
        "product": {
            "name": cfg.product_name,
            "url": cfg.product_url,
            "tagline": cfg.tagline,
            "category": cfg.category,
        },
        "reddit": {
            "username": cfg.reddit_username,
        },
        "targets": {
            "karma_subs": [{"sub": s.sub, "keywords": s.keywords} for s in cfg.karma_subs],
            "seed_subs": [{"sub": s.sub, "keywords": s.keywords} for s in cfg.seed_subs],
            "post_subs": [{"sub": p.sub, "title_hint": p.title_hint} for p in cfg.post_subs],
        },
        "content": {
            "karma_tone": cfg.karma_tone,
            "seed_tone": cfg.seed_tone,
        },
        "limits": {
            "karma_comments_per_day": cfg.limits.karma_comments_per_day,
            "seed_comments_per_day": cfg.limits.seed_comments_per_day,
            "posts_per_day": cfg.limits.posts_per_day,
            "min_delay_seconds": cfg.limits.min_delay_seconds,
            "max_delay_seconds": cfg.limits.max_delay_seconds,
        },
    }
