"""마크다운 → DayPlan 데이터 파싱."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class DayType(Enum):
    PREP = "prep"
    POST = "post"
    COMMENT_MGMT = "comment_mgmt"
    REST = "rest"
    REVIEW = "review"


@dataclass
class PostContent:
    title: str
    body: str
    placeholders: list[str] = field(default_factory=list)


@dataclass
class QAPair:
    question: str
    answer: str


@dataclass
class SeedingComment:
    subreddit: str
    context: str  # 예시 상황
    body: str


@dataclass
class DayPlan:
    day_id: str
    day_type: DayType
    subreddit: str | None = None
    post: PostContent | None = None
    qa_pairs: list[QAPair] = field(default_factory=list)
    seeding_comments: list[SeedingComment] = field(default_factory=list)
    previous_days_to_monitor: list[str] = field(default_factory=list)
    raw_content: str = ""


# day_id -> day_type 매핑
POST_DAYS = {1, 3, 5, 8, 10, 12, 15, 17, 19, 22, 24, 26, 29}
COMMENT_MGMT_DAYS = {2, 4, 9, 11, 16, 18, 23, 25}
REST_DAYS = {6, 13, 20, 27}
REVIEW_DAYS = {7, 14, 21, 28, 30}


def _classify_day(day_id: str) -> DayType:
    if day_id.startswith("prep"):
        return DayType.PREP

    m = re.match(r"day-(\d+)", day_id)
    if not m:
        return DayType.REST

    num = int(m.group(1))
    if num in POST_DAYS:
        return DayType.POST
    if num in COMMENT_MGMT_DAYS:
        return DayType.COMMENT_MGMT
    if num in REVIEW_DAYS:
        return DayType.REVIEW
    return DayType.REST


def _extract_subreddit(content: str) -> str | None:
    # 기본 정보 테이블에서 서브레딧 추출
    m = re.search(r"\|\s*서브레딧\s*\|\s*(r/\w+)", content)
    return m.group(1) if m else None


def _extract_post(content: str) -> PostContent | None:
    # "## 포스트" 섹션에서 제목 + 본문 추출
    post_section = re.search(r"## 포스트\s*\n(.*?)(?=\n## |\Z)", content, re.DOTALL)
    if not post_section:
        return None

    section = post_section.group(1)

    # 제목 추출
    title_match = re.search(r'\*\*제목:\*\*\s*"([^"]+)"', section)
    if not title_match:
        title_match = re.search(r'\*\*제목:\*\*\s*(.+)', section)
    if not title_match:
        return None
    title = title_match.group(1).strip().strip('"')

    # 본문 추출 (```로 감싸진 블록)
    body_match = re.search(r'\*\*본문:\*\*\s*\n```\n(.*?)```', section, re.DOTALL)
    if not body_match:
        return None

    body = body_match.group(1).strip()

    # 플레이스홀더 검출
    placeholders = re.findall(r'\[([^\]]*?(?:기능|수정|기반|현재|숫자|이유|인용)[^\]]*?)\]', body)
    post = PostContent(title=title, body=body)
    if placeholders:
        post.placeholders = placeholders
    return post


def _extract_qa_pairs(content: str) -> list[QAPair]:
    pairs = []
    # "## 예상 질문 + 준비된 답변" 섹션 찾기
    qa_section = re.search(
        r"## 예상 질문.*?\n(.*?)(?=\n## (?!#)|\Z)", content, re.DOTALL
    )
    if not qa_section:
        return pairs

    section = qa_section.group(1)

    # ### "질문" 패턴으로 각 Q&A 추출
    questions = re.finditer(
        r'### "([^"]+)"\s*\n```\n(.*?)```', section, re.DOTALL
    )
    for m in questions:
        pairs.append(QAPair(question=m.group(1).strip(), answer=m.group(2).strip()))

    return pairs


def _extract_seeding_comments(content: str, day_type: DayType) -> list[SeedingComment]:
    comments = []

    if day_type == DayType.PREP:
        # PREP 파일: ### N. r/subreddit 댓글 N개 패턴
        sections = re.finditer(
            r"### \d+\.\s+(r/\w+)\s+댓글.*?\n(.*?)(?=### \d+\.|## |\Z)",
            content,
            re.DOTALL,
        )
        for section in sections:
            subreddit = section.group(1)
            section_text = section.group(2)
            # ```로 감싸진 댓글 추출
            comment_blocks = re.finditer(
                r"\*\*예시 상황:\*\*\s*(.*?)\n```\n(.*?)```",
                section_text,
                re.DOTALL,
            )
            for cb in comment_blocks:
                comments.append(
                    SeedingComment(
                        subreddit=subreddit,
                        context=cb.group(1).strip(),
                        body=cb.group(2).strip(),
                    )
                )
    else:
        # POST/COMMENT_MGMT: "## 댓글 활동" 섹션에서 추출
        comment_section = re.search(
            r"## (?:댓글 활동|다른 서브 댓글 활동).*?\n(.*?)(?=\n## (?!#)|\Z)",
            content,
            re.DOTALL,
        )
        if not comment_section:
            # "### 2. 다른 서브 댓글 활동" 패턴도 시도
            comment_section = re.search(
                r"### \d+\.\s*다른 서브 댓글 활동.*?\n(.*?)(?=### \d+\.|## |\Z)",
                content,
                re.DOTALL,
            )
        if comment_section:
            section_text = comment_section.group(1)
            # r/subreddit 패턴으로 댓글 타겟 추출
            targets = re.finditer(
                r"(r/\w+).*?(?:댓글|에서)",
                section_text,
            )
            for t in targets:
                subreddit = t.group(1)
                comments.append(
                    SeedingComment(subreddit=subreddit, context="", body="")
                )

            # ```로 감싸진 댓글 템플릿 추출
            comment_blocks = re.finditer(
                r"(r/\w+)\s*[—\-–]\s*(.*?)\n```\n(.*?)```",
                section_text,
                re.DOTALL,
            )
            for cb in comment_blocks:
                # 이미 추가된 빈 댓글 교체
                subreddit = cb.group(1)
                for i, c in enumerate(comments):
                    if c.subreddit == subreddit and not c.body:
                        comments[i] = SeedingComment(
                            subreddit=subreddit,
                            context=cb.group(2).strip(),
                            body=cb.group(3).strip(),
                        )
                        break
                else:
                    comments.append(
                        SeedingComment(
                            subreddit=subreddit,
                            context=cb.group(2).strip(),
                            body=cb.group(3).strip(),
                        )
                    )

    return comments


def _extract_monitor_targets(content: str) -> list[str]:
    """모니터링할 이전 포스트 day_id 추출."""
    targets = []
    # "Day N 포스트" 패턴 찾기
    for m in re.finditer(r"Day\s+(\d+)\s+(?:포스트|댓글)", content):
        day_num = int(m.group(1))
        targets.append(f"day-{day_num:02d}")
    return list(set(targets))


def parse_day_file(filepath: Path) -> DayPlan:
    """마크다운 파일 하나를 DayPlan으로 파싱."""
    content = filepath.read_text(encoding="utf-8")
    stem = filepath.stem  # "day-01", "prep-d3"

    # day_id 정규화
    day_id = stem

    day_type = _classify_day(day_id)

    plan = DayPlan(
        day_id=day_id,
        day_type=day_type,
        raw_content=content,
    )

    plan.subreddit = _extract_subreddit(content)
    plan.post = _extract_post(content)
    plan.qa_pairs = _extract_qa_pairs(content)
    plan.seeding_comments = _extract_seeding_comments(content, day_type)
    plan.previous_days_to_monitor = _extract_monitor_targets(content)

    return plan


def parse_all_days(docs_dir: str = "docs/reddit-30day") -> dict[str, DayPlan]:
    """모든 마크다운 파일을 파싱하여 day_id → DayPlan 매핑 반환."""
    plans = {}
    docs_path = Path(docs_dir)
    if not docs_path.exists():
        return plans

    for f in sorted(docs_path.glob("*.md")):
        if f.name == "README.md":
            continue
        plan = parse_day_file(f)
        plans[plan.day_id] = plan

    return plans


def resolve_day_id(day_input: str) -> str:
    """사용자 입력을 day_id로 변환. '1' -> 'day-01', 'prep-d3' -> 'prep-d3'."""
    day_input = day_input.strip().lower()
    if day_input.startswith("prep"):
        return day_input
    # 숫자만 입력한 경우
    try:
        num = int(day_input)
        return f"day-{num:02d}"
    except ValueError:
        return day_input
