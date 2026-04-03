"""레딧브라우저 Reddit 자동화 클라이언트.

Chrome Extension WebSocket 통신으로 Reddit에 직접 포스팅/댓글 작성.
API 키 불필요 — 사용자의 Chrome 로그인 세션 활용.

page-agent 방식: shreddit DOM 직접 파싱 + native event 시뮬레이션.
구조화된 데이터(포스트 목록, 댓글 등)는 redd 라이브러리 fallback.
"""

from __future__ import annotations

import base64
import re
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus

from .pi_browser_client import PiBrowserClient, init_browser

SCREENSHOT_DIR = Path("data/screenshots")


def _try_import_redd():
    """redd 라이브러리 임포트 시도."""
    try:
        from redd import Redd
        return Redd()
    except ImportError:
        return None


class RedditBrowser:
    """Pi Browser + redd 하이브리드 Reddit 자동화.

    읽기: redd 라이브러리 (구조화된 데이터) + getText (텍스트)
    쓰기: navigate + fill + click (브라우저 자동화)
    """

    def __init__(self):
        self.browser: PiBrowserClient | None = None
        self.redd = _try_import_redd()

    def connect(self) -> bool:
        """레딧브라우저 연결."""
        try:
            self.browser = init_browser()
            if self.browser.is_alive():
                print("[Reddit] 레딧브라우저 연결 성공", flush=True)
                return True
            print("[Reddit] 레딧브라우저 연결 대기... Chrome에서 레딧브라우저 확장 확인", flush=True)
            return False
        except Exception as e:
            print(f"[Reddit] 연결 실패: {e}", flush=True)
            return False

    def _wait_load(self, seconds: int = 3):
        """페이지 로드 대기."""
        time.sleep(seconds)
        self.browser._wait_for_connection()

    # ── 로그인 확인 ──

    def check_login(self) -> dict:
        """Reddit 로그인 상태 확인."""
        self.browser.ext_navigate("https://www.reddit.com")
        self._wait_load(6)

        # 디버깅: 현재 페이지 URL과 제목 확인
        page_info = self.browser.ext_evaluate("({url: location.href, title: document.title})")
        print(f"[Reddit] 현재 페이지: {page_info}", flush=True)

        # 디버깅: 로그인 관련 요소 확인
        debug = self.browser.ext_evaluate("""
            (() => {
                const expandBtn = document.querySelector('#expand-user-drawer-button');
                const loginBtn = document.querySelector('a[href*="login"]');
                const loginBtn2 = document.querySelector('button[data-testid="login-button"]');
                const userMenu = document.querySelector('faceplate-dropdown-menu-button');
                const allBtns = [...document.querySelectorAll('button')].slice(0, 10).map(b => b.textContent.trim().substring(0, 30));
                return {
                    expandBtn: !!expandBtn,
                    loginBtn: !!loginBtn,
                    loginBtn2: !!loginBtn2,
                    userMenu: !!userMenu,
                    sampleButtons: allBtns,
                    bodyLen: document.body?.innerHTML?.length || 0,
                };
            })()
        """)
        print(f"[Reddit] DOM 디버그: {debug}", flush=True)

        result = self.browser.reddit_check_login()
        print(f"[Reddit] 로그인 결과: {result}", flush=True)
        return {"logged_in": result.get("loggedIn", False), "username": result.get("username")}

    # ── 읽기 (redd 라이브러리) ──

    def get_subreddit_posts(self, subreddit: str, sort: str = "hot", limit: int = 10) -> list[dict]:
        """서브레딧의 포스트 목록 (Extension 네이티브 파싱)."""
        sub = subreddit.replace("r/", "")

        self.browser.ext_navigate(f"https://www.reddit.com/r/{sub}/{sort}/")
        self._wait_load(4)

        # Extension의 reddit_get_posts 사용 (shreddit-post 직접 파싱)
        posts = self.browser.reddit_get_posts(limit)
        if posts:
            return posts

        # fallback: redd 라이브러리
        if self.redd:
            try:
                redd_posts = self.redd.get_subreddit_posts(sub, sort=sort, limit=limit)
                return [
                    {
                        "title": p.title,
                        "url": f"https://www.reddit.com{p.permalink}" if hasattr(p, 'permalink') else p.url,
                        "permalink": getattr(p, 'permalink', ''),
                        "score": getattr(p, 'score', 0),
                        "num_comments": getattr(p, 'num_comments', 0),
                        "author": getattr(p, 'author', 'unknown'),
                    }
                    for p in redd_posts
                ]
            except Exception as e:
                print(f"[redd] r/{sub} fallback 실패: {e}", flush=True)

        # 최종 fallback: 텍스트 기반
        return self._get_posts_via_text(sub, sort)

    def _get_posts_via_text(self, sub: str, sort: str = "hot") -> list[dict]:
        """getText 기반 포스트 파싱 (redd 실패 시 대체)."""
        self.browser.ext_navigate(f"https://www.reddit.com/r/{sub}/{sort}/")
        self._wait_load(4)

        text = self.browser.ext_get_text()
        if not text:
            return []

        # 텍스트에서 포스트 제목 패턴 추출
        posts = []
        lines = text.split("\n")
        for line in lines:
            line = line.strip()
            if len(line) > 15 and not line.startswith(("Skip", "r/", "Create", "Expand", "Advertise")):
                # 사용자명 패턴 (u/xxx • N hours ago) 다음 줄이 제목
                if line.startswith("u/"):
                    continue
                # 충분히 긴 텍스트를 포스트 제목 후보로
                if not any(skip in line.lower() for skip in ["upvote", "downvote", "share", "comment", "promoted"]):
                    posts.append({"title": line[:200], "url": "", "score": 0, "num_comments": 0})
                    if len(posts) >= 10:
                        break

        return posts

    def get_post_detail(self, permalink: str) -> dict:
        """포스트 상세 정보 (redd 라이브러리)."""
        if self.redd:
            try:
                detail = self.redd.get_post_detail(permalink)
                return {
                    "title": detail.title,
                    "body": getattr(detail, 'selftext', '') or getattr(detail, 'body', ''),
                    "score": getattr(detail, 'score', 0),
                    "num_comments": getattr(detail, 'num_comments', 0),
                    "author": getattr(detail, 'author', 'unknown'),
                    "url": getattr(detail, 'url', ''),
                    "comments": [
                        {
                            "author": getattr(c, 'author', 'unknown'),
                            "body": getattr(c, 'body', '')[:500],
                            "score": getattr(c, 'score', 0),
                        }
                        for c in (getattr(detail, 'comments', []) or [])[:20]
                    ],
                }
            except Exception as e:
                print(f"[redd] 포스트 상세 실패: {e}", flush=True)

        # 텍스트 기반 대체
        url = f"https://www.reddit.com{permalink}" if permalink.startswith("/") else permalink
        return self._get_post_via_text(url)

    def _get_post_via_text(self, url: str) -> dict:
        """getText 기반 포스트 상세."""
        self.browser.ext_navigate(url)
        self._wait_load(4)

        text = self.browser.ext_get_text()
        return {
            "title": "",
            "body": text[:2000] if text else "",
            "score": 0,
            "num_comments": 0,
            "author": "",
            "url": url,
            "comments": [],
            "raw_text": text or "",
        }

    def search_subreddit(self, subreddit: str, query: str, limit: int = 5) -> list[dict]:
        """서브레딧 내 검색 (redd 라이브러리)."""
        sub = subreddit.replace("r/", "")

        if self.redd:
            try:
                results = self.redd.search(query, subreddit=sub, sort="new", time_filter="week", limit=limit)
                return [
                    {
                        "title": getattr(r, 'title', ''),
                        "url": f"https://www.reddit.com{r.permalink}" if hasattr(r, 'permalink') else getattr(r, 'url', ''),
                        "permalink": getattr(r, 'permalink', ''),
                        "score": getattr(r, 'score', 0),
                        "num_comments": getattr(r, 'num_comments', 0),
                        "author": getattr(r, 'author', 'unknown'),
                    }
                    for r in results
                ]
            except Exception as e:
                print(f"[redd] 검색 실패: {e}", flush=True)

        # 텍스트 기반 대체
        return self._search_via_text(sub, query)

    def _search_via_text(self, sub: str, query: str) -> list[dict]:
        """getText 기반 검색 (redd 실패 시)."""
        encoded = quote_plus(query)
        self.browser.ext_navigate(
            f"https://www.reddit.com/r/{sub}/search/?q={encoded}&restrict_sr=1&sort=new&t=week"
        )
        self._wait_load(4)

        text = self.browser.ext_get_text()
        if not text:
            return []

        # 텍스트에서 포스트 제목 추출 (간단한 파싱)
        posts = []
        for line in text.split("\n"):
            line = line.strip()
            if len(line) > 20 and not line.startswith(("Skip", "r/", "u/", "Search")):
                if not any(skip in line.lower() for skip in ["upvote", "sort by", "promoted"]):
                    posts.append({"title": line[:200], "url": "", "score": 0})
                    if len(posts) >= 5:
                        break
        return posts

    # ── 쓰기 (브라우저 자동화) ──

    def submit_post(self, subreddit: str, title: str, body: str, auto_submit: bool = False) -> dict:
        """서브레딧에 텍스트 포스트 작성 — CDP 기반 업그레이드.

        1차: Extension의 redditSubmitPost 명령 사용 (CDP typeText)
        2차 fallback: fill 커맨드
        """
        sub = subreddit.replace("r/", "")
        print(f"[레딧브라우저] 포스트 작성: r/{sub} — '{title[:50]}'", flush=True)

        # 방법 1: Extension의 redditSubmitPost (CDP 기반)
        try:
            result = self.browser._send_ext_command("redditSubmitPost", {
                "subreddit": sub,
                "title": title,
                "body": body,
                "autoSubmit": auto_submit,
            })
            log = result.get("log", [])
            for l in log:
                print(f"  [submitPost] {l}", flush=True)

            if result.get("success"):
                return {"status": "posted", "url": result.get("url", ""), "message": "CDP 기반 발행 성공"}
            if result.get("ready"):
                return {"status": "ready", "message": f"r/{sub}에 포스트 준비 완료 — 발행 확인 필요"}
        except Exception as e:
            print(f"[레딧브라우저] redditSubmitPost 실패: {e}", flush=True)

        # 방법 2: fill 커맨드 fallback
        print("[레딧브라우저] fill fallback 사용", flush=True)
        self.browser.ext_navigate(f"https://www.reddit.com/r/{sub}/submit?type=TEXT")
        self._wait_load(5)

        self.browser.ext_fill('textarea[name="title"]', title)
        time.sleep(1)
        self.browser.ext_fill('div[contenteditable="true"]', body)
        time.sleep(1)

        return {"status": "ready", "message": f"r/{sub}에 포스트 준비 완료 — 발행 확인 필요"}

    def confirm_submit(self) -> dict:
        """포스트 발행 버튼 클릭."""
        # JS 방식 시도
        result = self.browser.ext_evaluate("""
            (() => {
                const postBtn = Array.from(document.querySelectorAll('button')).find(
                    b => b.textContent?.trim().toLowerCase() === 'post'
                );
                if (postBtn && !postBtn.disabled) {
                    postBtn.click();
                    return {clicked: true};
                }
                return {clicked: false};
            })()
        """)

        if not (isinstance(result, dict) and result.get("clicked")):
            # fallback: click 명령
            self.browser.ext_click('button[type="submit"]')

        self._wait_load(5)

        # URL 확인
        page_info = self.browser.ext_evaluate("({url: location.href})")
        url = page_info.get("url", "") if isinstance(page_info, dict) else ""

        if "/comments/" in url:
            return {"status": "posted", "url": url}

        text = self.browser.ext_get_text()
        return {"status": "submitted", "url": url, "page_text": (text or "")[:500]}

    def scroll_down(self, amount: int = 500) -> dict:
        """페이지 스크롤 다운."""
        return self.browser.ext_scroll("down", amount)

    def scroll_up(self, amount: int = 500) -> dict:
        """페이지 스크롤 업."""
        return self.browser.ext_scroll("up", amount)

    def _save_comment_to_db(self, post_url: str, comment_body: str, comment_type: str = "seeding"):
        """댓글을 대시보드 DB에 기록."""
        try:
            from .state import StateDB
            # URL에서 subreddit 추출
            m = re.search(r'/r/([^/]+)', post_url)
            subreddit = m.group(1) if m else "unknown"
            # URL에서 submission id 추출
            m2 = re.search(r'/comments/([^/]+)', post_url)
            submission_id = m2.group(1) if m2 else None

            db = StateDB("data/campaign.db")
            db.save_comment(
                reddit_id=f"browser_{int(time.time())}",
                submission_id=submission_id,
                subreddit=subreddit,
                body=comment_body,
                comment_type=comment_type,
            )
            db.close()
            print(f"[레딧브라우저] DB 기록 완료 (r/{subreddit}, type={comment_type})", flush=True)
        except Exception as e:
            print(f"[레딧브라우저] DB 기록 실패: {e}", flush=True)

    def post_comment(self, post_url: str, comment_body: str, save_screenshot: bool = True, comment_type: str = "seeding") -> dict:
        """포스트에 댓글 작성 — 3단계: JS inject → 버튼 찾기 → CDP full fallback.

        핵심: 텍스트 입력 후 페이지를 절대 리로드하지 않음 (입력 텍스트 보존).
        """
        print(f"[레딧브라우저] 댓글 작성 시작: {post_url[:80]}...", flush=True)
        self.browser.ext_navigate(post_url)
        self._wait_load(5)

        if save_screenshot:
            self.save_screenshot("before_comment")

        # ══════════════════════════════════════
        # 방법 1: JS inject로 텍스트 입력 시도
        # ══════════════════════════════════════
        print("[레딧브라우저] Step 1: JS inject 텍스트 입력...", flush=True)
        result = self.browser.reddit_comment(comment_body)
        log = result.get("log", [])
        for l in log:
            print(f"  [JS] {l}", flush=True)

        if result.get("success") and result.get("verified"):
            print("[레딧브라우저] JS 완전 성공 + 검증됨!", flush=True)
            self._save_comment_to_db(post_url, comment_body, comment_type)
            if save_screenshot:
                self.save_screenshot("verified_comment")
            return {"status": "commented", "verified": True}

        # JS가 텍스트를 입력했지만 버튼 클릭이 실패한 경우
        # → 페이지를 리로드하지 않고 바로 버튼 찾기 시도
        if result.get("success") or "CDP typeText done" in str(log):
            print("[레딧브라우저] 텍스트 입력됨 — 버튼 클릭 재시도 (리로드 없이)...", flush=True)
            btn_clicked = self._try_click_comment_button()
            if btn_clicked:
                time.sleep(3)
                if save_screenshot:
                    self.save_screenshot("after_submit_retry")
                # 검증
                verified = self._verify_comment(post_url, comment_body)
                if verified:
                    self._save_comment_to_db(post_url, comment_body, comment_type)
                    if save_screenshot:
                        self.save_screenshot("verified_comment")
                    return {"status": "commented", "verified": True}

        # ══════════════════════════════════════
        # 방법 2: CDP full — 처음부터 다시 (트리거 클릭 → 타이핑 → 버튼)
        # ══════════════════════════════════════
        print("[레딧브라우저] Step 2: CDP full fallback...", flush=True)
        # beforeunload 팝업 방지 후 페이지 리로드
        self.browser.ext_evaluate("window.onbeforeunload = null")
        time.sleep(0.3)
        self.browser.ext_navigate(post_url)
        self._wait_load(5)

        # 스크롤 내려서 댓글 영역 보이게
        self.browser.ext_scroll("down", 400)
        time.sleep(1.5)

        # 2a: 댓글 트리거 클릭 (join the conversation / add a comment)
        trigger_clicked = self._click_comment_trigger()
        if not trigger_clicked:
            print("[레딧브라우저] 트리거 못 찾음 — faceplate-textarea 직접 클릭", flush=True)
            self.browser.ext_click("faceplate-textarea-input")
        time.sleep(2)

        # 2b: 에디터 찾기 + 포커스
        editor_found = self._focus_editor()
        time.sleep(0.5)

        # 2c: CDP 타이핑
        print(f"[레딧브라우저] CDP 타이핑 ({len(comment_body)}자)...", flush=True)
        type_result = self.browser.ext_type_text(comment_body)
        if type_result.get("error"):
            print("[레딧브라우저] CDP 타이핑 실패 — fill 시도", flush=True)
            self.browser.ext_fill('div[contenteditable="true"]', comment_body)
            time.sleep(0.5)
            # textarea도 시도
            self.browser.ext_fill('textarea', comment_body)
        time.sleep(1)

        if save_screenshot:
            self.save_screenshot("after_text_input")

        # 2d: 에디터에 텍스트가 있는지 확인
        editor_text = self.browser.ext_evaluate("""
            (() => {
                const ed = document.querySelector('div[contenteditable="true"]');
                if (ed && ed.textContent.trim()) return ed.textContent.trim().substring(0, 100);
                const ta = document.querySelector('textarea');
                if (ta && ta.value.trim()) return ta.value.trim().substring(0, 100);
                return '';
            })()
        """)
        if editor_text:
            print(f"[레딧브라우저] 에디터 텍스트 확인: {str(editor_text)[:60]}", flush=True)
        else:
            print("[레딧브라우저] 에디터 텍스트 없음 — 그래도 계속 진행", flush=True)

        # 2e: Comment 버튼 클릭
        btn_clicked = self._try_click_comment_button()
        if not btn_clicked:
            # JS로 직접 클릭 시도
            print("[레딧브라우저] snapshot 버튼 실패 — JS 직접 클릭 시도", flush=True)
            self.browser.ext_evaluate("""
                (() => {
                    const btns = document.querySelectorAll('button');
                    for (const b of btns) {
                        const t = b.textContent.trim().toLowerCase();
                        if (t === 'comment' && b.offsetWidth > 30) {
                            b.click();
                            return 'clicked';
                        }
                    }
                    // submit 타입 버튼
                    for (const b of btns) {
                        if (b.type === 'submit' && b.offsetWidth > 30) {
                            const t = b.textContent.trim().toLowerCase();
                            if (!['reply','cancel','search','chat'].includes(t)) {
                                b.click();
                                return 'clicked-submit';
                            }
                        }
                    }
                    return 'not-found';
                })()
            """)

        time.sleep(3)
        if save_screenshot:
            self.save_screenshot("after_submit")

        # ══════════════════════════════════════
        # 검증 (리로드 후)
        # ══════════════════════════════════════
        verified = self._verify_comment(post_url, comment_body)
        if verified:
            self._save_comment_to_db(post_url, comment_body, comment_type)
            if save_screenshot:
                self.save_screenshot("verified_comment")
            return {"status": "commented", "verified": True}

        if save_screenshot:
            self.save_screenshot("unverified_comment")
        print("[레딧브라우저] 댓글 미확인", flush=True)
        return {"status": "unverified", "message": "제출됐지만 페이지에서 미확인"}

    def _click_comment_trigger(self) -> bool:
        """댓글 트리거 (join the conversation / add a comment) 클릭."""
        snap = self.browser._send_ext_command("snapshot")
        for el in snap.get("elements", []):
            sel = el.get("selector", "")
            text = (el.get("text") or "").lower()
            rect = el.get("rect", {})
            if ("faceplate-textarea" in sel or "join" in text or
                "conversation" in text or "add a comment" in text):
                if rect.get("width", 0) > 0 and rect.get("height", 0) > 0:
                    x = rect["x"] + rect["width"] // 2
                    y = rect["y"] + rect["height"] // 2
                    print(f"  트리거 클릭: ({x}, {y}) - {text[:40]}", flush=True)
                    self.browser.ext_click_coords(x, y)
                    return True
        return False

    def _focus_editor(self) -> bool:
        """에디터 (textbox/textarea) 찾아서 포커스."""
        snap = self.browser._send_ext_command("snapshot")
        for el in snap.get("elements", []):
            role = el.get("role", "")
            tag = el.get("tag", "")
            rect = el.get("rect", {})
            if (role == "textbox" or tag == "textarea" or
                "contenteditable" in str(el.get("attributes", ""))):
                if rect.get("width", 0) > 100 and rect.get("height", 0) > 20:
                    ex = rect["x"] + rect["width"] // 2
                    ey = rect["y"] + rect["height"] // 2
                    print(f"  에디터 포커스: ({ex}, {ey}) tag={tag} role={role}", flush=True)
                    self.browser.ext_click_coords(ex, ey)
                    return True
        return False

    def _try_click_comment_button(self) -> bool:
        """snapshot에서 Comment 버튼 찾아 클릭."""
        snap = self.browser._send_ext_command("snapshot")
        # 1차: text가 정확히 "comment"인 버튼
        for el in snap.get("elements", []):
            if el.get("tag") == "button":
                text = (el.get("text") or "").strip().lower()
                rect = el.get("rect", {})
                if text == "comment" and rect.get("width", 0) > 30:
                    sx = rect["x"] + rect["width"] // 2
                    sy = rect["y"] + rect["height"] // 2
                    print(f"  Comment 버튼: ({sx}, {sy})", flush=True)
                    self.browser.ext_click_coords(sx, sy)
                    return True
        # 2차: submit 타입 버튼 (reply, cancel 등 제외)
        exclude = {"open chat", "search", "collapse", "expand", "chat", "reply", "cancel", "save draft", "post"}
        for el in snap.get("elements", []):
            if el.get("tag") == "button":
                text = (el.get("text") or "").strip().lower()
                btn_type = el.get("type", "")
                rect = el.get("rect", {})
                if btn_type == "submit" and rect.get("width", 0) > 30:
                    if not any(ex in text for ex in exclude):
                        sx = rect["x"] + rect["width"] // 2
                        sy = rect["y"] + rect["height"] // 2
                        print(f"  Submit 버튼: ({sx}, {sy}) text={text}", flush=True)
                        self.browser.ext_click_coords(sx, sy)
                        return True
        return False

    def _verify_comment(self, post_url: str, comment_body: str) -> bool:
        """댓글 게시 검증 — 현재 페이지 + 리로드 후 확인."""
        snippet = comment_body[:40]

        # 현재 페이지에서 확인
        print("[레딧브라우저] 검증: 현재 페이지...", flush=True)
        text = self.browser.ext_get_text() or ""
        if snippet in text:
            print("[레딧브라우저] 댓글 확인됨!", flush=True)
            return True

        # 리로드 후 확인
        print("[레딧브라우저] 검증: 리로드 후...", flush=True)
        self.browser.ext_evaluate("window.onbeforeunload = null")
        time.sleep(1)
        self.browser.ext_navigate(post_url)
        self._wait_load(5)
        text = self.browser.ext_get_text() or ""
        if snippet in text:
            print("[레딧브라우저] 리로드 후 댓글 확인됨!", flush=True)
            return True

        print("[레딧브라우저] 댓글 미확인", flush=True)
        return False

    def save_screenshot(self, label: str = "screenshot") -> str | None:
        """현재 페이지 스크린샷을 파일로 저장."""
        try:
            result = self.browser.ext_screenshot()
            if not result or not result.get("image"):
                return None

            SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{ts}_{label}.png"
            filepath = SCREENSHOT_DIR / filename

            # data:image/png;base64,... 형식에서 base64 추출
            img_data = result["image"]
            if "," in img_data:
                img_data = img_data.split(",", 1)[1]
            filepath.write_bytes(base64.b64decode(img_data))

            print(f"[레딧브라우저] 스크린샷 저장: {filepath}", flush=True)
            return str(filepath)
        except Exception as e:
            print(f"[레딧브라우저] 스크린샷 실패: {e}", flush=True)
            return None

    def search_and_comment(self, subreddit: str, query: str, comment_body: str, max_posts: int = 1) -> list[dict]:
        """서브레딧 검색 → 관련 포스트에 댓글.

        redd로 포스트 검색 → 브라우저로 댓글 작성.
        """
        results = []
        posts = self.search_subreddit(subreddit, query, limit=max_posts + 2)

        if not posts:
            return [{"status": "no_posts_found", "subreddit": subreddit, "query": query}]

        for post in posts[:max_posts]:
            url = post.get("url", "")
            if not url:
                continue

            result = self.post_comment(url, comment_body)
            result["url"] = url
            result["subreddit"] = subreddit
            result["title"] = post.get("title", "")
            results.append(result)

            if len(results) < max_posts:
                time.sleep(5)

        return results

    # ── 모니터링 ──

    def get_post_comments(self, post_url: str) -> list[dict]:
        """포스트의 댓글 목록 (Extension 네이티브)."""
        self.browser.ext_navigate(post_url)
        self._wait_load(4)

        comments = self.browser.reddit_get_comments(limit=30)
        if comments:
            return comments

        # fallback: redd
        permalink = _url_to_permalink(post_url)
        if self.redd and permalink:
            try:
                detail = self.redd.get_post_detail(permalink)
                return [
                    {"author": getattr(c, 'author', 'unknown'), "body": getattr(c, 'body', '')[:500], "score": getattr(c, 'score', 0)}
                    for c in (getattr(detail, 'comments', []) or [])[:50]
                ]
            except Exception:
                pass

        return self._get_comments_via_text(post_url)

    def _get_comments_via_text(self, url: str) -> list[dict]:
        """getText 기반 댓글 파싱."""
        self.browser.ext_navigate(url)
        self._wait_load(4)

        text = self.browser.ext_get_text()
        if not text:
            return []

        # 간단한 댓글 파싱 (텍스트 블록)
        return [{"body": text[:2000], "raw": True}]

    def get_post_stats(self, post_url: str) -> dict:
        """포스트 통계 (Extension 네이티브)."""
        self.browser.ext_navigate(post_url)
        self._wait_load(3)

        detail = self.browser.reddit_get_post_detail()
        if detail and detail.get("title"):
            return {
                "score": detail.get("score", 0),
                "comment_count": detail.get("commentCount", 0),
                "title": detail.get("title", ""),
                "author": detail.get("author", ""),
                "url": post_url,
            }

        return {"title": "", "score": 0, "comment_count": 0, "url": post_url}

    # ── 업보트 ──

    def upvote_post(self, post_url: str = None) -> dict:
        """현재 페이지 또는 지정 URL의 포스트 업보트."""
        if post_url:
            self.browser.ext_navigate(post_url)
            self._wait_load(3)
        return self.browser.reddit_upvote()

    # ── 서브레딧 이동 ──

    def navigate_subreddit(self, subreddit: str, sort: str = "hot") -> dict:
        """서브레딧으로 이동 + 서브레딧 정보 수집."""
        sub = subreddit.replace("r/", "")
        return self.browser.reddit_navigate_sub(sub, sort)

    # ── 사용자 정보 ──

    def get_user_info(self) -> dict:
        """현재 로그인한 사용자 정보."""
        return self.browser.reddit_get_user_info()

    # ── 댓글 답글 ──

    def reply_to_comment(self, thing_id: str, body: str) -> dict:
        """특정 댓글에 답글."""
        return self.browser.reddit_reply_to_comment(thing_id, body)

    # ── DOM 트리 (page-agent 방식) ──

    def get_dom_tree(self, max_depth: int = 5, max_nodes: int = 200) -> dict:
        """page-agent 방식 DOM 트리 추출."""
        return self.browser.get_dom_tree(max_depth, max_nodes)

    def click_by_index(self, index: int) -> dict:
        """DOM 인덱스 기반 클릭."""
        return self.browser.click_by_index(index)

    def fill_by_index(self, index: int, value: str) -> dict:
        """DOM 인덱스 기반 입력."""
        return self.browser.fill_by_index(index, value)

    # ── 페이지 텍스트 읽기 ──

    def read_page(self, url: str) -> str:
        """URL의 텍스트 내용 읽기."""
        self.browser.ext_navigate(url)
        self._wait_load(4)
        return self.browser.ext_get_text() or ""

    def stop(self):
        """브라우저 연결 종료."""
        if self.browser:
            self.browser.stop()


def _url_to_permalink(url: str) -> str:
    """Reddit URL을 permalink로 변환."""
    if not url:
        return ""
    # https://www.reddit.com/r/sub/comments/xxx/title/ → /r/sub/comments/xxx/title/
    m = re.search(r"(\/r\/\w+\/comments\/\w+\/[^?#]*)", url)
    return m.group(1) if m else ""
