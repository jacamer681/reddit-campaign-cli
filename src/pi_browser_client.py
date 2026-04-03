"""
레딧브라우저 Python Client
Chrome Extension(레딧브라우저)과 직접 WebSocket 통신
Python이 WebSocket 서버(9876)를 열고, Extension이 연결하면 명령 전송
별도 브라우저를 띄우지 않음 - 사용자의 기존 Chrome 사용
"""
import json
import time
import threading
import asyncio
import socket
import subprocess
import os
from typing import Optional, Dict, Any


EXT_WS_PORT = 9877


class PiBrowserClient:
    """Chrome Extension 직접 통신 - Python WebSocket 서버"""

    def __init__(self, port: int = EXT_WS_PORT, **kwargs):
        self.port = port
        self._connected = False
        self._ext_ws = None
        self._server_thread = None
        self._loop = None
        self._msg_id = 0
        self._pending = {}
        self._results = {}
        self._running = False
        self.process = None

    def start_server(self):
        """WebSocket 서버 시작 - Extension 연결 대기"""
        if self._running:
            return

        # 포트 사용 중이면 정리
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            if sock.connect_ex(("localhost", self.port)) == 0:
                sock.close()
                result = subprocess.run(["lsof", f"-ti:{self.port}"], capture_output=True, text=True)
                for pid in result.stdout.strip().split("\n"):
                    if pid.strip():
                        try:
                            os.kill(int(pid.strip()), 9)
                        except Exception:
                            pass
                time.sleep(1)
            else:
                sock.close()
        except Exception:
            pass

        self._running = True
        self._server_thread = threading.Thread(target=self._run_server, daemon=True)
        self._server_thread.start()
        print(f"[레딧브라우저] WebSocket 서버 시작 (포트 {self.port}) - Extension 연결 대기...", flush=True)

    def _run_server(self):
        """비동기 WebSocket 서버 실행"""
        import websockets.server

        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        async def handler(websocket):
            self._ext_ws = websocket
            self._connected = True
            print(f"[레딧브라우저] Extension 연결됨!", flush=True)
            try:
                async for message in websocket:
                    try:
                        data = json.loads(message)
                        msg_id = data.get("id")
                        if msg_id and msg_id in self._pending:
                            if data.get("error"):
                                self._results[msg_id] = {"error": data["error"]}
                            else:
                                self._results[msg_id] = data.get("result", {})
                            self._pending[msg_id].set()
                    except Exception as e:
                        print(f"[레딧브라우저] 메시지 파싱 에러: {e}", flush=True)
            except Exception:
                pass
            finally:
                if self._ext_ws == websocket:
                    self._ext_ws = None
                    self._connected = False
                    print("[레딧브라우저] Extension 연결 끊김", flush=True)

        async def serve():
            async with websockets.server.serve(handler, "0.0.0.0", self.port):
                while self._running:
                    await asyncio.sleep(1)

        try:
            self._loop.run_until_complete(serve())
        except Exception:
            pass

    def connect(self, retries: int = 3):
        """Extension 연결 대기"""
        for _ in range(retries * 5):
            if self._connected:
                return
            time.sleep(1)
        if not self._connected:
            print("[레딧브라우저] Extension 연결 대기 시간 초과. Chrome에서 레딧브라우저 확장 확인.", flush=True)

    def is_alive(self) -> bool:
        return self._connected and self._ext_ws is not None

    def ensure_connected(self):
        if self.is_alive():
            return
        if not self._running:
            self.start_server()
            self.connect()

    # ============================================================
    # Extension 명령 전송
    # ============================================================

    def _send_ext_command(self, command: str, params: dict = None, timeout: int = 30, retries: int = 3) -> dict:
        """Extension에 명령 보내고 응답 대기 (재시도 포함)"""
        for attempt in range(retries):
            # 연결 대기
            if not self._wait_for_connection(timeout=10):
                continue

            self._msg_id += 1
            msg_id = self._msg_id
            event = threading.Event()
            self._pending[msg_id] = event

            msg = json.dumps({"id": msg_id, "command": command, "params": params or {}})

            try:
                future = asyncio.run_coroutine_threadsafe(self._ext_ws.send(msg), self._loop)
                future.result(timeout=5)
            except Exception as e:
                self._pending.pop(msg_id, None)
                if attempt < retries - 1:
                    time.sleep(2)
                    continue
                return {"error": f"전송 실패: {e}"}

            event.wait(timeout=timeout)

            result = self._results.pop(msg_id, None)
            self._pending.pop(msg_id, None)

            if result is not None:
                return result

            # 타임아웃 - 재시도
            if attempt < retries - 1:
                time.sleep(2)

        return {"error": "타임아웃"}

    def ext_navigate(self, url: str) -> dict:
        return self._send_ext_command("navigate", {"url": url})

    def ext_get_text(self) -> str:
        result = self._send_ext_command("getText")
        return result.get("text", "") if isinstance(result, dict) else ""

    def ext_get_tabs(self) -> list:
        result = self._send_ext_command("getTabs")
        return result if isinstance(result, list) else []

    def ext_click(self, selector: str) -> dict:
        return self._send_ext_command("click", {"selector": selector})

    def ext_fill(self, selector: str, value: str) -> dict:
        return self._send_ext_command("fill", {"selector": selector, "value": value})

    def ext_scroll(self, direction: str = "down", amount: int = 500) -> dict:
        return self._send_ext_command("scroll", {"direction": direction, "amount": amount})

    def ext_click_coords(self, x: int, y: int) -> dict:
        """CDP 기반 좌표 클릭 — Shadow DOM 관통."""
        return self._send_ext_command("clickCoords", {"x": x, "y": y}, timeout=10)

    def ext_type_text(self, text: str) -> dict:
        """CDP 기반 실제 타이핑 — Shadow DOM 관통."""
        return self._send_ext_command("typeText", {"text": text}, timeout=30)

    def ext_evaluate(self, script: str) -> Any:
        result = self._send_ext_command("evaluate", {"script": script})
        return result.get("result") if isinstance(result, dict) else None

    def ext_get_links(self, pattern: str = None, limit: int = 20) -> list:
        """페이지 링크 수집 (eval 불필요)."""
        params = {"limit": limit}
        if pattern:
            params["pattern"] = pattern
        result = self._send_ext_command("getLinks", params)
        return result.get("links", []) if isinstance(result, dict) else []

    def ext_get_page_info(self) -> dict:
        """페이지 기본 정보 (title, url, domain)."""
        result = self._send_ext_command("getPageInfo")
        return result if isinstance(result, dict) else {}

    # ============================================================
    # Reddit 전용 커맨드
    # ============================================================

    def reddit_comment(self, body: str) -> dict:
        """Reddit 댓글 작성 (트리거 클릭 → 입력 → 제출)."""
        result = self._send_ext_command("redditComment", {"body": body}, timeout=30)
        return result if isinstance(result, dict) else {"success": False}

    def reddit_get_posts(self, limit: int = 10) -> list:
        """서브레딧 포스트 목록 (shreddit-post 파싱)."""
        result = self._send_ext_command("redditGetPosts", {"limit": limit})
        return result.get("posts", []) if isinstance(result, dict) else []

    def reddit_get_post_detail(self) -> dict:
        """현재 포스트 상세 (제목, 본문, 점수, 작성자)."""
        result = self._send_ext_command("redditGetPostDetail")
        return result if isinstance(result, dict) else {}

    def reddit_get_comments(self, limit: int = 30) -> list:
        """현재 포스트 댓글 목록."""
        result = self._send_ext_command("redditGetComments", {"limit": limit})
        return result.get("comments", []) if isinstance(result, dict) else []

    def reddit_check_login(self) -> dict:
        """Reddit 로그인 상태."""
        result = self._send_ext_command("redditCheckLogin")
        return result if isinstance(result, dict) else {"loggedIn": False}

    def reddit_upvote(self, selector: str = None) -> dict:
        """Reddit 업보트."""
        params = {"selector": selector} if selector else {}
        result = self._send_ext_command("redditUpvote", params)
        return result if isinstance(result, dict) else {"success": False}

    def reddit_search(self, query: str, subreddit: str = None,
                      sort: str = "relevance", limit: int = 10) -> list:
        """Reddit 검색 → 포스트 목록."""
        params = {"query": query, "sort": sort, "limit": limit}
        if subreddit:
            params["subreddit"] = subreddit
        result = self._send_ext_command("redditSearch", params, timeout=20)
        return result.get("posts", []) if isinstance(result, dict) else []

    def reddit_submit_post(self, subreddit: str, title: str, body: str,
                           auto_submit: bool = False) -> dict:
        """Reddit 포스트 작성 (CDP 기반)."""
        result = self._send_ext_command("redditSubmitPost", {
            "subreddit": subreddit,
            "title": title,
            "body": body,
            "autoSubmit": auto_submit,
        }, timeout=30)
        return result if isinstance(result, dict) else {"success": False}

    def reddit_reply_to_comment(self, thing_id: str, body: str) -> dict:
        """Reddit 댓글에 답글."""
        result = self._send_ext_command("redditReplyToComment",
                                        {"thingId": thing_id, "body": body}, timeout=15)
        return result if isinstance(result, dict) else {"success": False}

    def reddit_get_user_info(self) -> dict:
        """현재 로그인 사용자 정보."""
        result = self._send_ext_command("redditGetUserInfo")
        return result if isinstance(result, dict) else {"loggedIn": False}

    def reddit_navigate_sub(self, subreddit: str, sort: str = "hot") -> dict:
        """서브레딧으로 이동 + 정보 수집."""
        result = self._send_ext_command("redditNavigateSub",
                                        {"subreddit": subreddit, "sort": sort}, timeout=20)
        return result if isinstance(result, dict) else {"success": False}

    # ============================================================
    # page-agent 스타일 DOM 트리 + 인덱스 기반 조작
    # ============================================================

    def get_dom_tree(self, max_depth: int = 5, max_nodes: int = 200) -> dict:
        """page-agent 방식 DOM 트리 추출 (인덱스 매핑)."""
        result = self._send_ext_command("getDomTree",
                                        {"maxDepth": max_depth, "maxNodes": max_nodes})
        return result if isinstance(result, dict) else {}

    def click_by_index(self, index: int) -> dict:
        """DOM 트리 인덱스로 클릭."""
        result = self._send_ext_command("clickByIndex", {"index": index})
        return result if isinstance(result, dict) else {"success": False}

    def fill_by_index(self, index: int, value: str) -> dict:
        """DOM 트리 인덱스로 입력."""
        result = self._send_ext_command("fillByIndex", {"index": index, "value": value})
        return result if isinstance(result, dict) else {"success": False}

    def ext_screenshot(self) -> dict:
        return self._send_ext_command("screenshot")

    # ============================================================
    # 고수준 크롤링 API
    # ============================================================

    def scrape_page(self, url: str) -> Dict:
        nav = self.ext_navigate(url)
        if isinstance(nav, dict) and nav.get("error"):
            return {"status": "error", "result": nav["error"]}
        time.sleep(3)
        self._wait_for_connection()
        text = self.ext_get_text()
        return {"status": "ok", "result": text[:5000]}

    def _wait_for_connection(self, timeout=10):
        """Extension 재연결 대기"""
        for _ in range(timeout * 2):
            if self.is_alive():
                return True
            time.sleep(0.5)
        return False

    def scrape_article(self, url: str) -> Dict:
        nav = self.ext_navigate(url)
        if isinstance(nav, dict) and nav.get("error"):
            return {"status": "error", "result": nav["error"]}
        time.sleep(3)
        self._wait_for_connection()
        text = self.ext_get_text()
        return {"status": "ok", "result": (text or "")[:3000]}

    def scrape_with_images(self, url: str) -> Dict:
        nav = self.ext_navigate(url)
        title = nav.get("title", "") if isinstance(nav, dict) else ""
        if isinstance(nav, dict) and nav.get("error"):
            return {"status": "error", "result": nav["error"]}
        time.sleep(3)
        self._wait_for_connection()
        text = self.ext_get_text()
        return {"status": "ok", "title": title, "content": (text or "")[:10000], "images": []}

    # 기존 호환
    def navigate(self, url: str) -> Dict:
        return self.ext_navigate(url)

    def screenshot(self) -> Dict:
        return self.ext_screenshot()

    def stop(self):
        self._running = False
        self._connected = False
        self._ext_ws = None
        print("[레딧브라우저] 종료됨", flush=True)


_client: Optional[PiBrowserClient] = None

def get_browser() -> PiBrowserClient:
    global _client
    if _client is None:
        _client = PiBrowserClient()
    return _client

def init_browser():
    client = get_browser()
    client.start_server()
    client.connect()
    return client
