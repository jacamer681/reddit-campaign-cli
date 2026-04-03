// 레딧브라우저 Extension - Background Service Worker
let ws = null;
let connectedTabId = null;
let isDebugging = false;
let debugTabId = null;
let consoleBuffer = [];
let consoleMaxEntries = 500;

// Recording state
let isRecording = false;
let recordingActions = [];
let recordingStartTime = 0;
let recordingTabId = null;
let recordingStartUrl = "";

function pushConsoleEntry(entry) {
  consoleBuffer.push(entry);
  const over = consoleBuffer.length - consoleMaxEntries;
  if (over > 0) {
    consoleBuffer.splice(0, over);
  }
}

function sendDebuggerCommand(tabId, method, params = {}) {
  return new Promise((resolve, reject) => {
    chrome.debugger.sendCommand({ tabId }, method, params, (result) => {
      const err = chrome.runtime.lastError;
      if (err) return reject(new Error(err.message));
      resolve(result);
    });
  });
}

// Capture console logs / exceptions while debugger is attached.
chrome.debugger.onEvent.addListener((source, method, params) => {
  if (!isDebugging || !debugTabId) return;
  if (!source || source.tabId !== debugTabId) return;

  try {
    if (method === "Runtime.consoleAPICalled") {
      const level = params?.type || "log";
      const args = Array.isArray(params?.args) ? params.args : [];
      const text = args
        .map((a) => {
          if (a && typeof a.value !== "undefined") return String(a.value);
          if (a && typeof a.description === "string") return a.description;
          if (a && typeof a.type === "string") return `[${a.type}]`;
          return "";
        })
        .filter(Boolean)
        .join(" ");
      pushConsoleEntry({ ts: Date.now(), level, text });
    } else if (method === "Runtime.exceptionThrown") {
      const details = params?.exceptionDetails || {};
      const text =
        details?.exception?.description ||
        details?.text ||
        "Uncaught exception";
      pushConsoleEntry({ ts: Date.now(), level: "exception", text: String(text) });
    } else if (method === "Log.entryAdded") {
      const entry = params?.entry || {};
      const level = entry?.level || "log";
      const text = entry?.text || entry?.url || "";
      if (text) pushConsoleEntry({ ts: Date.now(), level, text: String(text) });
    }
  } catch (e) {
    // Ignore console capture errors.
  }
});

chrome.debugger.onDetach.addListener((source, reason) => {
  if (!debugTabId) return;
  if (!source || source.tabId !== debugTabId) return;
  console.log("[레딧] Debugger detached:", reason);
  isDebugging = false;
  debugTabId = null;
});

// 서비스 워커 활성 유지를 위한 알람
chrome.alarms.create("keepAlive", { periodInMinutes: 0.5 });
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === "keepAlive") {
    console.log("[레딧] Keep alive ping");
    // WebSocket 연결 확인
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      connect();
    }
  }
});

// WebSocket 서버에 연결
function connect() {
  if (ws && ws.readyState === WebSocket.OPEN) return;

  console.log("[레딧] WebSocket 연결 시도...");
  // Pin to IPv4 to avoid localhost IPv6 resolution issues.
  ws = new WebSocket("ws://127.0.0.1:9877");

  ws.onopen = () => {
    console.log("[레딧] WebSocket 연결됨");
    chrome.action.setBadgeText({ text: "ON" });
    chrome.action.setBadgeBackgroundColor({ color: "#4CAF50" });
  };

  ws.onclose = () => {
    console.log("[레딧] WebSocket 연결 끊김");
    chrome.action.setBadgeText({ text: "" });
    ws = null;
    // 5초 후 재연결 시도
    setTimeout(connect, 5000);
  };

  ws.onerror = (error) => {
    console.log("[레딧] WebSocket 에러:", error);
  };

  ws.onmessage = async (event) => {
    let msgId = null;
    try {
      const message = JSON.parse(event.data);
      msgId = message.id;
      console.log("[레딧] 명령 수신:", message.command, message.params);
      const result = await handleCommand(message);
      console.log("[레딧] 명령 완료:", message.command);
      ws.send(JSON.stringify({ id: msgId, result }));
    } catch (error) {
      console.error("[레딧] 명령 처리 에러:", error.message);
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ id: msgId, error: error.message }));
      }
    }
  };
}

// 명령 처리
async function handleCommand(message) {
  const { command, params } = message;

  switch (command) {
    case "consoleStart":
      return await consoleStart(params?.maxEntries);

    case "consoleGet":
      return await consoleGet(params?.limit);

    case "consoleClear":
      return await consoleClear();

    case "consoleStop":
      return await consoleStop();

    case "getTabs":
      return await getTabs();

    case "selectTab":
      return await selectTab(params.tabId);

    case "navigate":
      return await navigate(params.url);

    case "screenshot":
      return await takeScreenshot();

    case "snapshot":
      return await getSnapshot();

    case "click":
      return await clickElement(params.selector);

    case "fill":
      return await fillElement(params.selector, params.value);

    case "press":
      return await pressKey(params.key);

    case "scroll":
      return await scroll(params.direction, params.amount);

    case "getText":
      return await getPageText();

    case "getHtml":
      return await getPageHtml(params?.maxChars);

    case "evaluate":
      return await evaluateScript(params.script);

    case "getLinks":
      return await getLinks(params?.pattern, params?.limit);

    case "getPageInfo":
      return await getPageInfo();

    case "redditComment":
      return await redditComment(params?.body);

    case "redditGetPosts":
      return await redditGetPosts(params?.limit);

    case "redditGetComments":
      return await redditGetComments(params?.limit);

    case "redditGetPostDetail":
      return await redditGetPostDetail();

    case "redditCheckLogin":
      return await redditCheckLogin();

    case "redditUpvote":
      return await redditUpvote(params?.selector);

    case "redditSearch":
      return await redditSearch(params?.query, params?.subreddit, params?.sort, params?.limit);

    case "redditReplyToComment":
      return await redditReplyToComment(params?.thingId, params?.body);

    case "redditGetUserInfo":
      return await redditGetUserInfo();

    case "redditNavigateSub":
      return await redditNavigateSub(params?.subreddit, params?.sort);

    case "getDomTree":
      return await getDomTree(params?.maxDepth, params?.maxNodes);

    case "clickByIndex":
      return await clickByIndex(params?.index);

    case "fillByIndex":
      return await fillByIndex(params?.index, params?.value);

    case "recordingStart":
      return await recordingStart();

    case "recordingStop":
      return await recordingStop();

    case "recordingStatus":
      return {
        isRecording,
        actionCount: recordingActions.length,
        duration: isRecording ? Date.now() - recordingStartTime : 0,
        tabId: recordingTabId,
      };

    case "clickCoords":
      return await clickCoords(params?.x, params?.y);

    case "typeText":
      return await typeText(params?.text);

    case "redditSubmitPost":
      return await redditSubmitPost(params?.subreddit, params?.title, params?.body, params?.autoSubmit);

    default:
      throw new Error(`Unknown command: ${command}`);
  }
}

// 탭 목록 가져오기
async function getTabs() {
  const tabs = await chrome.tabs.query({});
  return tabs.map((tab) => ({
    id: tab.id,
    title: tab.title,
    url: tab.url,
    active: tab.active,
  }));
}

// 탭 선택
async function selectTab(tabId) {
  connectedTabId = tabId;
  await chrome.tabs.update(tabId, { active: true });
  return { success: true, tabId };
}

// 페이지 이동
async function navigate(url) {
  if (!connectedTabId) {
    // 새 탭 생성
    const tab = await chrome.tabs.create({ url });
    connectedTabId = tab.id;
  } else {
    await chrome.tabs.update(connectedTabId, { url });
  }

  // 페이지 로드 대기
  await waitForPageLoad();

  const tab = await chrome.tabs.get(connectedTabId);
  return { success: true, url: tab.url, title: tab.title };
}

// 페이지 로드 대기
function waitForPageLoad() {
  return new Promise((resolve) => {
    const listener = (tabId, info) => {
      if (tabId === connectedTabId && info.status === "complete") {
        chrome.tabs.onUpdated.removeListener(listener);
        setTimeout(resolve, 500); // 추가 대기
      }
    };
    chrome.tabs.onUpdated.addListener(listener);
    // 타임아웃
    setTimeout(() => {
      chrome.tabs.onUpdated.removeListener(listener);
      resolve();
    }, 30000);
  });
}

// 스크린샷
async function takeScreenshot() {
  await getActiveTabId();

  const dataUrl = await chrome.tabs.captureVisibleTab(null, {
    format: "png",
  });

  return { image: dataUrl };
}

// 현재 활성 탭 ID 가져오기 (Reddit 탭 우선)
async function getActiveTabId() {
  if (connectedTabId) {
    try {
      const tab = await chrome.tabs.get(connectedTabId);
      if (tab && tab.url && !tab.url.startsWith("chrome://") && !tab.url.startsWith("chrome-extension://")) {
        return connectedTabId;
      }
    } catch {}
  }

  // Reddit 탭 우선 검색
  const allTabs = await chrome.tabs.query({});
  const redditTab = allTabs.find(t => t.url && t.url.includes("reddit.com") && t.active);
  if (redditTab) {
    connectedTabId = redditTab.id;
    return redditTab.id;
  }

  // 활성 탭
  const activeTabs = await chrome.tabs.query({ active: true, currentWindow: true });
  for (const tab of activeTabs) {
    if (tab.url && !tab.url.startsWith("chrome://") && !tab.url.startsWith("chrome-extension://")) {
      connectedTabId = tab.id;
      return tab.id;
    }
  }

  // Reddit 탭 (비활성이라도)
  const anyReddit = allTabs.find(t => t.url && t.url.includes("reddit.com"));
  if (anyReddit) {
    connectedTabId = anyReddit.id;
    return anyReddit.id;
  }

  // 아무 접근 가능한 탭
  for (const tab of allTabs) {
    if (tab.url && !tab.url.startsWith("chrome://") && !tab.url.startsWith("chrome-extension://")) {
      connectedTabId = tab.id;
      return tab.id;
    }
  }

  throw new Error("No accessible tab found");
}

// 페이지 스냅샷 (요소 정보)
async function getSnapshot() {
  const tabId = await getActiveTabId();

  const results = await chrome.scripting.executeScript({
    target: { tabId },
    func: () => {
      const elements = [];
      const interactiveSelectors = [
        "a",
        "button",
        "input",
        "select",
        "textarea",
        '[role="button"]',
        '[role="link"]',
        '[role="textbox"]',
        '[role="checkbox"]',
        '[role="radio"]',
        '[onclick]',
        '[tabindex]',
      ];

      // Shadow DOM 관통 수집
      function collectAll(selectors, root = document) {
        const results = [...root.querySelectorAll(selectors)];
        function traverse(node) {
          if (node.shadowRoot) {
            results.push(...node.shadowRoot.querySelectorAll(selectors));
            for (const c of node.shadowRoot.children) traverse(c);
          }
          if (node.children) for (const c of node.children) traverse(c);
        }
        // 주요 web component만 순회 (성능)
        root.querySelectorAll("shreddit-post, shreddit-comment, shreddit-composer, faceplate-form, faceplate-textarea-input, shreddit-comment-tree").forEach(traverse);
        return results;
      }

      collectAll(interactiveSelectors.join(",")).forEach((el, index) => {
        const rect = el.getBoundingClientRect();
        if (rect.width === 0 || rect.height === 0) return;
        if (rect.top > window.innerHeight || rect.bottom < 0) return;

        const text =
          el.innerText?.trim().slice(0, 100) ||
          el.value ||
          el.placeholder ||
          el.getAttribute("aria-label") ||
          el.title ||
          "";

        elements.push({
          ref: `ref_${index}`,
          tag: el.tagName.toLowerCase(),
          type: el.type || null,
          text: text,
          role: el.getAttribute("role"),
          selector: generateSelector(el),
          rect: {
            x: Math.round(rect.x),
            y: Math.round(rect.y),
            width: Math.round(rect.width),
            height: Math.round(rect.height),
          },
        });
      });

      function generateSelector(el) {
        if (el.id) return `#${el.id}`;
        if (el.name) return `[name="${el.name}"]`;

        let path = el.tagName.toLowerCase();
        if (el.className && typeof el.className === "string") {
          const classes = el.className.trim().split(/\s+/).slice(0, 2).join(".");
          if (classes) path += `.${classes}`;
        }
        return path;
      }

      return elements;
    },
  });

  return { elements: results[0]?.result || [] };
}

// 요소 클릭 (page-agent 방식 — Shadow DOM 관통 + 완전한 이벤트 시퀀스)
async function clickElement(selector) {
  const tabId = await getActiveTabId();

  const results = await chrome.scripting.executeScript({
    target: { tabId },
    func: (sel) => {
      // Shadow DOM 관통 querySelector
      function findDeep(s) {
        let r = document.querySelector(s);
        if (r) return r;
        function traverse(node) {
          if (r) return;
          if (node.shadowRoot) {
            r = node.shadowRoot.querySelector(s);
            if (r) return;
            for (const c of node.shadowRoot.children) traverse(c);
          }
          if (node.children) for (const c of node.children) traverse(c);
        }
        traverse(document.documentElement);
        return r;
      }

      const el = findDeep(sel);
      if (!el) throw new Error(`Element not found: ${sel}`);

      // 뷰포트에 보이게 스크롤
      el.scrollIntoView({ behavior: "instant", block: "center" });

      const rect = el.getBoundingClientRect();
      const x = rect.left + rect.width / 2;
      const y = rect.top + rect.height / 2;
      const evtInit = { bubbles: true, cancelable: true, view: window, clientX: x, clientY: y };

      // page-agent 이벤트 시퀀스 (mouseenter→mouseover→mousedown→focus→mouseup→click)
      el.dispatchEvent(new MouseEvent("mouseenter", evtInit));
      el.dispatchEvent(new MouseEvent("mouseover", evtInit));
      el.dispatchEvent(new MouseEvent("mousedown", { ...evtInit, button: 0 }));
      el.focus();
      el.dispatchEvent(new MouseEvent("mouseup", { ...evtInit, button: 0 }));
      el.dispatchEvent(new MouseEvent("click", { ...evtInit, button: 0 }));

      return { success: true, tag: el.tagName, shadow: !!el.getRootNode()?.host };
    },
    args: [selector],
  });

  return results[0]?.result;
}

// 요소에 입력 (page-agent 방식 — React/contenteditable/native input 호환)
async function fillElement(selector, value) {
  const tabId = await getActiveTabId();

  const results = await chrome.scripting.executeScript({
    target: { tabId },
    func: (sel, val) => {
      // Shadow DOM 관통 검색
      function findDeep(s) {
        let r = document.querySelector(s);
        if (r) return r;
        function traverse(node) {
          if (r) return;
          if (node.shadowRoot) {
            r = node.shadowRoot.querySelector(s);
            if (r) return;
            for (const c of node.shadowRoot.children) traverse(c);
          }
          if (node.children) for (const c of node.children) traverse(c);
        }
        traverse(document.documentElement);
        return r;
      }

      let el = findDeep(sel);
      if (!el) el = findDeep('[contenteditable="true"]');
      if (!el) el = findDeep('[role="textbox"]');
      if (!el) throw new Error(`Element not found: ${sel}`);

      el.focus();

      const tag = el.tagName.toLowerCase();
      const isContentEditable = el.getAttribute("contenteditable") === "true" || el.isContentEditable;

      if (isContentEditable) {
        // page-agent contentEditable 입력: beforeinput(delete)→clear→input→beforeinput(insert)→set→input→change
        if (el.dispatchEvent(new InputEvent("beforeinput", {
          bubbles: true, cancelable: true, inputType: "deleteContent"
        }))) {
          el.innerText = "";
          el.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "deleteContent" }));
        }
        if (el.dispatchEvent(new InputEvent("beforeinput", {
          bubbles: true, cancelable: true, inputType: "insertText", data: val
        }))) {
          el.innerText = val;
          el.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertText", data: val }));
        }
        el.dispatchEvent(new Event("change", { bubbles: true }));
      } else if (tag === "input" || tag === "textarea") {
        // React native value setter
        const proto = tag === "textarea" ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
        const nativeSetter = Object.getOwnPropertyDescriptor(proto, "value")?.set;
        if (nativeSetter) nativeSetter.call(el, val);
        else el.value = val;
        el.dispatchEvent(new Event("input", { bubbles: true }));
        el.dispatchEvent(new Event("change", { bubbles: true }));
      } else {
        document.execCommand("selectAll", false, null);
        document.execCommand("delete", false, null);
        document.execCommand("insertText", false, val);
      }

      return { success: true, tag };
    },
    args: [selector, value],
  });

  return results[0]?.result;
}

// 키 입력
async function pressKey(key) {
  const tabId = await getActiveTabId();

  const results = await chrome.scripting.executeScript({
    target: { tabId },
    func: (k) => {
      const keyMap = {
        Enter: { key: "Enter", code: "Enter", keyCode: 13 },
        Tab: { key: "Tab", code: "Tab", keyCode: 9 },
        Escape: { key: "Escape", code: "Escape", keyCode: 27 },
        ArrowUp: { key: "ArrowUp", code: "ArrowUp", keyCode: 38 },
        ArrowDown: { key: "ArrowDown", code: "ArrowDown", keyCode: 40 },
        Backspace: { key: "Backspace", code: "Backspace", keyCode: 8 },
      };

      const keyInfo = keyMap[k] || { key: k, code: k, keyCode: k.charCodeAt(0) };
      const event = new KeyboardEvent("keydown", {
        key: keyInfo.key,
        code: keyInfo.code,
        keyCode: keyInfo.keyCode,
        bubbles: true,
      });

      document.activeElement?.dispatchEvent(event);
      return { success: true };
    },
    args: [key],
  });

  return results[0]?.result;
}

// 스크롤
async function scroll(direction, amount = 500) {
  const tabId = await getActiveTabId();

  const results = await chrome.scripting.executeScript({
    target: { tabId },
    func: (dir, amt) => {
      const scrollMap = {
        up: [0, -amt],
        down: [0, amt],
        left: [-amt, 0],
        right: [amt, 0],
      };
      const [x, y] = scrollMap[dir] || [0, amt];
      window.scrollBy(x, y);
      return { success: true, scrollY: window.scrollY };
    },
    args: [direction, amount],
  });

  return results[0]?.result;
}

// 페이지 텍스트 가져오기
async function getPageText() {
  const tabId = await getActiveTabId();

  const results = await chrome.scripting.executeScript({
    target: { tabId },
    func: () => {
      return document.body.innerText;
    },
  });

  return { text: results[0]?.result || "" };
}

// 페이지 HTML 가져오기
async function getPageHtml(maxChars = 200000) {
  const tabId = await getActiveTabId();
  const limit = Math.max(1000, Math.min(Number(maxChars) || 200000, 2000000));

  const results = await chrome.scripting.executeScript({
    target: { tabId },
    func: (maxLen) => {
      const html = document.documentElement?.outerHTML || "";
      return html.length > maxLen ? html.slice(0, maxLen) : html;
    },
    args: [limit],
  });

  return { html: results[0]?.result || "" };
}

// 페이지 링크 수집 (eval 불필요)
async function getLinks(pattern, limit = 20) {
  const tabId = await getActiveTabId();
  const results = await chrome.scripting.executeScript({
    target: { tabId },
    func: (pat, lim) => {
      const links = [];
      const seen = new Set();
      document.querySelectorAll("a[href]").forEach((a) => {
        const href = a.href;
        if (!href || seen.has(href)) return;
        if (pat && !href.includes(pat)) return;
        seen.add(href);
        links.push({
          url: href,
          text: (a.textContent || "").trim().substring(0, 120),
        });
      });
      return links.slice(0, lim);
    },
    args: [pattern || null, limit || 20],
  });
  return { links: results[0]?.result || [] };
}

// 페이지 기본 정보 (eval 불필요)
async function getPageInfo() {
  const tabId = await getActiveTabId();
  const results = await chrome.scripting.executeScript({
    target: { tabId },
    func: () => {
      return {
        title: document.title,
        url: window.location.href,
        domain: window.location.hostname,
      };
    },
  });
  return results[0]?.result || {};
}

// ═══ Reddit 전용 커맨드 (page-agent 방식 — Shadow DOM 관통) ═══

// Reddit 댓글 작성 — page-agent 방식 Shadow DOM 완전 관통
async function redditComment(body) {
  const tabId = await getActiveTabId();
  const log = [];

  try {
    await ensureDebugger(tabId);
  } catch (e) {
    log.push('debugger attach failed: ' + e.message);
  }

  // Step 1: 트리거 좌표 찾기 (executeScript)
  const step1 = await chrome.scripting.executeScript({
    target: { tabId },
    func: () => {
      const ct = document.querySelector('shreddit-comment-tree') || document.querySelector('#comment-tree');
      if (ct) ct.scrollIntoView({ behavior: 'instant', block: 'center' });
      else window.scrollBy(0, 500);

      const trigger = document.querySelector('faceplate-textarea-input');
      if (trigger) {
        trigger.scrollIntoView({ behavior: 'instant', block: 'center' });
        let rect = trigger.getBoundingClientRect();
        // display:contents인 경우 shadow root 자식에서 좌표 가져오기
        if (rect.width === 0 && trigger.shadowRoot) {
          const inner = trigger.shadowRoot.querySelector('div, span, textarea, input');
          if (inner) rect = inner.getBoundingClientRect();
        }
        // 그래도 0이면 Range로 시도
        if (rect.width === 0) {
          const range = document.createRange();
          range.selectNodeContents(trigger);
          rect = range.getBoundingClientRect();
        }
        return { found: true, x: Math.round(rect.x + rect.width / 2), y: Math.round(rect.y + rect.height / 2), w: Math.round(rect.width), h: Math.round(rect.height) };
      }
      return { found: false };
    },
  });

  const triggerInfo = step1[0]?.result || {};
  log.push('trigger: ' + JSON.stringify(triggerInfo));

  if (!triggerInfo.found) {
    return { success: false, error: '트리거 미발견', log };
  }

  // Step 2: CDP 클릭으로 에디터 열기
  try {
    await sendDebuggerCommand(tabId, 'Input.dispatchMouseEvent', {
      type: 'mousePressed', x: triggerInfo.x, y: triggerInfo.y, button: 'left', clickCount: 1,
    });
    await sendDebuggerCommand(tabId, 'Input.dispatchMouseEvent', {
      type: 'mouseReleased', x: triggerInfo.x, y: triggerInfo.y, button: 'left', clickCount: 1,
    });
    log.push('CDP click trigger OK');
  } catch (e) {
    log.push('CDP click failed: ' + e.message);
    await chrome.scripting.executeScript({
      target: { tabId },
      func: () => { const t = document.querySelector('faceplate-textarea-input'); if (t) { t.click(); t.focus(); } },
    });
  }

  await new Promise(r => setTimeout(r, 2500));

  // Step 3: 에디터에 텍스트 입력 (executeScript + execCommand)
  const step3 = await chrome.scripting.executeScript({
    target: { tabId },
    func: (commentBody) => {
      const log = [];
      let editor = null;
      const composers = document.querySelectorAll('shreddit-composer');
      for (const comp of composers) {
        editor = comp.querySelector('div[data-lexical-editor="true"]')
          || comp.querySelector('div[contenteditable="true"][role="textbox"]')
          || comp.querySelector('div[contenteditable="true"]');
        if (editor) { log.push('editor in composer'); break; }
      }
      if (!editor) {
        const forms = document.querySelectorAll('faceplate-form');
        for (const form of forms) {
          if ((form.getAttribute('action') || '').includes('comment')) {
            editor = form.querySelector('div[data-lexical-editor="true"]') || form.querySelector('div[contenteditable="true"]');
            if (editor) { log.push('editor in faceplate-form'); break; }
          }
        }
      }
      if (!editor) {
        const allCE = document.querySelectorAll('[contenteditable="true"]');
        for (const ce of allCE) {
          const r = ce.getBoundingClientRect();
          if (r.width > 50 && r.height > 10) { editor = ce; log.push('editor via scan ' + r.width + 'x' + r.height); break; }
        }
      }
      if (!editor) { log.push('NO EDITOR'); return { ok: false, log }; }

      let rect = editor.getBoundingClientRect();
      // display:contents 보정 — 부모 composer에서 실제 렌더링된 좌표
      if (rect.width === 0) {
        const comp = editor.closest('shreddit-composer');
        if (comp && comp.shadowRoot) {
          const slot = comp.shadowRoot.querySelector('slot[name="rte"]');
          if (slot) {
            const assigned = slot.assignedElements();
            if (assigned.length > 0) rect = assigned[0].getBoundingClientRect();
          }
          if (rect.width === 0) {
            const inner = comp.shadowRoot.querySelector('div, reddit-rte');
            if (inner) rect = inner.getBoundingClientRect();
          }
        }
      }
      log.push('editor: ' + Math.round(rect.width) + 'x' + Math.round(rect.height));

      // 에디터가 보이지 않으면 CDP 클릭이 필요 — 좌표 반환
      if (rect.width === 0) {
        log.push('editor still 0x0 — returning for CDP click');
        return { ok: false, needCdpClick: true, log };
      }

      // 포커스 + execCommand (Lexical 호환)
      editor.focus();
      const sel = window.getSelection();
      const range = document.createRange();
      range.selectNodeContents(editor);
      sel.removeAllRanges();
      sel.addRange(range);
      document.execCommand('delete', false, null);
      const ok = document.execCommand('insertText', false, commentBody);
      log.push('insertText: ' + ok);
      const editorText = (editor.innerText || '').trim();
      log.push('text: ' + editorText.slice(0, 50));

      // Submit 버튼 좌표 찾기
      let btnRect = null;
      let btnText = '';
      const form = editor.closest('faceplate-form') || editor.closest('shreddit-composer');
      if (form) {
        const btn = form.querySelector('button[type="submit"]');
        if (btn && !btn.disabled) {
          const r = btn.getBoundingClientRect();
          btnRect = { x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2) };
          btnText = btn.textContent.trim();
        }
      }
      if (!btnRect) {
        const allBtns = document.querySelectorAll('button');
        for (const b of allBtns) {
          const t = (b.textContent || '').trim().toLowerCase();
          if (t === 'comment' && !b.disabled) {
            const r = b.getBoundingClientRect();
            if (r.width > 20) {
              btnRect = { x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2) };
              btnText = b.textContent.trim();
              break;
            }
          }
        }
      }
      log.push('btn: ' + btnText + ' ' + JSON.stringify(btnRect));
      return { ok: true, editorText: editorText.slice(0, 60), btnRect, btnText, log };
    },
    args: [body],
  });

  let inputInfo = step3[0]?.result || {};
  log.push(...(inputInfo.log || []));

  // 에디터가 0x0 — 실제 클릭 가능한 영역 찾고 CDP 타이핑
  if (!inputInfo.ok && inputInfo.needCdpClick) {
    log.push('fallback: find clickable editor area');

    // Step 3.5: 에디터 영역의 실제 좌표 찾기 (부모/형제/slot에서)
    const step3a = await chrome.scripting.executeScript({
      target: { tabId },
      func: () => {
        // 방법1: shreddit-composer 안의 보이는 요소 찾기
        const composers = document.querySelectorAll('shreddit-composer');
        for (const comp of composers) {
          // Shadow DOM 안의 에디터 컨테이너
          if (comp.shadowRoot) {
            const rte = comp.shadowRoot.querySelector('reddit-rte, .editor-container, [slot], div');
            if (rte) {
              const r = rte.getBoundingClientRect();
              if (r.width > 50 && r.height > 20) return { x: Math.round(r.x + 20), y: Math.round(r.y + 20), src: 'shadow-rte' };
            }
          }
          // 직접 자식 중 보이는 것
          const children = comp.querySelectorAll('*');
          for (const child of children) {
            const r = child.getBoundingClientRect();
            if (r.width > 50 && r.height > 20 && r.y > 0) {
              return { x: Math.round(r.x + 20), y: Math.round(r.y + 20), src: 'composer-child:' + child.tagName };
            }
          }
          // composer 자체
          const cr = comp.getBoundingClientRect();
          if (cr.width > 50) return { x: Math.round(cr.x + 20), y: Math.round(cr.y + 50), src: 'composer-self' };
        }
        // 방법2: p[data-lexical-text] 근처
        const lp = document.querySelector('p[data-lexical-text]');
        if (lp) {
          const r = lp.getBoundingClientRect();
          if (r.width > 0) return { x: Math.round(r.x + 10), y: Math.round(r.y + 5), src: 'lexical-p' };
        }
        // 방법3: 제출 버튼 위쪽 (에디터는 보통 버튼 바로 위)
        const btns = document.querySelectorAll('button');
        for (const b of btns) {
          if ((b.textContent || '').trim().toLowerCase() === 'comment') {
            const r = b.getBoundingClientRect();
            if (r.y > 100) return { x: Math.round(r.x), y: Math.round(r.y - 80), src: 'above-btn' };
          }
        }
        return null;
      },
    });
    const editorCoords = step3a[0]?.result;
    log.push('editor coords: ' + JSON.stringify(editorCoords));

    try {
      // 에디터 영역 CDP 클릭으로 포커스
      if (editorCoords) {
        await sendDebuggerCommand(tabId, 'Input.dispatchMouseEvent', {
          type: 'mousePressed', x: editorCoords.x, y: editorCoords.y, button: 'left', clickCount: 1,
        });
        await sendDebuggerCommand(tabId, 'Input.dispatchMouseEvent', {
          type: 'mouseReleased', x: editorCoords.x, y: editorCoords.y, button: 'left', clickCount: 1,
        });
        await new Promise(r => setTimeout(r, 500));
        log.push('CDP click editor at ' + editorCoords.src);
      }

      // Ctrl+A로 기존 내용 선택 후 삭제
      await sendDebuggerCommand(tabId, 'Input.dispatchKeyEvent', { type: 'keyDown', key: 'a', code: 'KeyA', modifiers: 2 });
      await sendDebuggerCommand(tabId, 'Input.dispatchKeyEvent', { type: 'keyUp', key: 'a', code: 'KeyA' });
      await sendDebuggerCommand(tabId, 'Input.dispatchKeyEvent', { type: 'keyDown', key: 'Backspace', code: 'Backspace' });
      await sendDebuggerCommand(tabId, 'Input.dispatchKeyEvent', { type: 'keyUp', key: 'Backspace', code: 'Backspace' });
      await new Promise(r => setTimeout(r, 300));

      // 텍스트 입력 (랜덤 딜레이로 사람처럼)
      for (const char of body) {
        await sendDebuggerCommand(tabId, 'Input.dispatchKeyEvent', { type: 'keyDown', text: char, key: char, code: '' });
        await sendDebuggerCommand(tabId, 'Input.dispatchKeyEvent', { type: 'keyUp', key: char, code: '' });
        await new Promise(r => setTimeout(r, 20 + Math.random() * 50));
      }
      log.push('CDP typeText done (' + body.length + ' chars)');
    } catch (e) {
      log.push('CDP typeText failed: ' + e.message);
      // fill fallback — input 이벤트도 발생시킴
      await chrome.scripting.executeScript({
        target: { tabId },
        func: (text) => {
          const editors = document.querySelectorAll('shreddit-composer');
          for (const comp of editors) {
            const ed = comp.querySelector('div[contenteditable="true"]');
            if (ed) {
              ed.focus();
              ed.innerText = text;
              ed.dispatchEvent(new Event('input', {bubbles: true}));
              ed.dispatchEvent(new Event('change', {bubbles: true}));
              return;
            }
          }
        },
        args: [body],
      });
      log.push('fill fallback done');
    }

    await new Promise(r => setTimeout(r, 1000));

    // 버튼 좌표 다시 찾기
    const step3b = await chrome.scripting.executeScript({
      target: { tabId },
      func: () => {
        // 에디터 텍스트 확인
        const composers = document.querySelectorAll('shreddit-composer');
        let editorText = '';
        for (const comp of composers) {
          const ed = comp.querySelector('div[contenteditable="true"]');
          if (ed) { editorText = (ed.innerText || '').trim(); break; }
        }
        // 버튼 찾기
        let btnRect = null, btnText = '';
        const allBtns = document.querySelectorAll('button');
        for (const b of allBtns) {
          const t = (b.textContent || '').trim().toLowerCase();
          if (t === 'comment' && !b.disabled) {
            const r = b.getBoundingClientRect();
            if (r.width > 20) {
              btnRect = { x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2), w: r.width };
              btnText = b.textContent.trim();
              break;
            }
          }
        }
        // 버튼도 0x0이면 JS click 시도
        if (!btnRect) {
          for (const b of allBtns) {
            const t = (b.textContent || '').trim().toLowerCase();
            if (t === 'comment' && !b.disabled) { b.click(); btnText = 'JS-clicked'; break; }
          }
        }
        return { editorText: editorText.slice(0, 60), btnRect, btnText };
      },
    });
    inputInfo = step3b[0]?.result || {};
    inputInfo.ok = true;
    log.push('editorText: ' + (inputInfo.editorText || ''));
    log.push('btn: ' + inputInfo.btnText + ' ' + JSON.stringify(inputInfo.btnRect));

    if (inputInfo.btnText === 'JS-clicked') {
      // 이미 JS로 클릭됨
      log.push('submit via JS click');
      await new Promise(r => setTimeout(r, 3000));
      const step5 = await chrome.scripting.executeScript({
        target: { tabId },
        func: (snippet) => (document.body.innerText || '').includes(snippet),
        args: [body.slice(0, 40)],
      });
      const verified = step5[0]?.result || false;
      log.push('verified=' + verified);
      return { success: true, verified, log, message: verified ? '댓글 확인됨' : '미확인' };
    }
  }

  if (!inputInfo.ok) return { success: false, error: '에디터 없음', log };
  if (!inputInfo.editorText || inputInfo.editorText.length < 5) log.push('WARNING: editor text empty');
  if (!inputInfo.btnRect) return { success: false, error: '제출 버튼 없음', bodyEntered: true, log };

  // Step 4: CDP 클릭으로 제출
  await new Promise(r => setTimeout(r, 500));
  try {
    await sendDebuggerCommand(tabId, 'Input.dispatchMouseEvent', {
      type: 'mousePressed', x: inputInfo.btnRect.x, y: inputInfo.btnRect.y, button: 'left', clickCount: 1,
    });
    await sendDebuggerCommand(tabId, 'Input.dispatchMouseEvent', {
      type: 'mouseReleased', x: inputInfo.btnRect.x, y: inputInfo.btnRect.y, button: 'left', clickCount: 1,
    });
    log.push('CDP click submit OK: ' + inputInfo.btnText);
  } catch (e) {
    log.push('CDP submit failed: ' + e.message);
    await chrome.scripting.executeScript({
      target: { tabId },
      func: () => {
        const allBtns = document.querySelectorAll('button');
        for (const b of allBtns) {
          if ((b.textContent || '').trim().toLowerCase() === 'comment' && !b.disabled) { b.click(); break; }
        }
      },
    });
  }

  // Step 5: 검증
  await new Promise(r => setTimeout(r, 3000));
  const step5 = await chrome.scripting.executeScript({
    target: { tabId },
    func: (snippet) => (document.body.innerText || '').includes(snippet),
    args: [body.slice(0, 40)],
  });

  const verified = step5[0]?.result || false;
  log.push('verified=' + verified);
  return { success: true, verified, log, message: verified ? '댓글 확인됨' : '미확인' };
}


// Reddit 포스트 목록 수집 (서브레딧 페이지에서)
async function redditGetPosts(limit = 10) {
  const tabId = await getActiveTabId();

  const results = await chrome.scripting.executeScript({
    target: { tabId },
    func: (lim) => {
      const posts = [];
      // shreddit-post 요소
      const postEls = document.querySelectorAll("shreddit-post");
      for (const el of postEls) {
        const title = el.getAttribute("post-title") || "";
        const permalink = el.getAttribute("permalink") || "";
        const author = el.getAttribute("author") || "";
        const score = parseInt(el.getAttribute("score")) || 0;
        const commentCount = parseInt(el.getAttribute("comment-count")) || 0;
        const createdAt = el.getAttribute("created-timestamp") || "";

        if (title) {
          posts.push({
            title,
            permalink,
            url: permalink ? "https://www.reddit.com" + permalink : "",
            author,
            score,
            commentCount,
            createdAt,
          });
        }
        if (posts.length >= lim) break;
      }

      // shreddit-post가 없으면 링크 기반 fallback
      if (posts.length === 0) {
        const links = document.querySelectorAll('a[href*="/comments/"]');
        const seen = new Set();
        for (const a of links) {
          const href = a.href;
          if (href && href.includes("/comments/") && !seen.has(href)) {
            seen.add(href);
            posts.push({
              title: (a.textContent || "").trim().substring(0, 120),
              url: href,
              permalink: new URL(href).pathname,
              author: "",
              score: 0,
              commentCount: 0,
            });
            if (posts.length >= lim) break;
          }
        }
      }
      return posts;
    },
    args: [limit || 10],
  });

  return { posts: results[0]?.result || [] };
}

// Reddit 포스트 상세 정보 (포스트 페이지에서)
async function redditGetPostDetail() {
  const tabId = await getActiveTabId();

  const results = await chrome.scripting.executeScript({
    target: { tabId },
    func: () => {
      const post = document.querySelector("shreddit-post");
      const title = post?.getAttribute("post-title") || document.title;
      const author = post?.getAttribute("author") || "";
      const score = parseInt(post?.getAttribute("score")) || 0;
      const commentCount = parseInt(post?.getAttribute("comment-count")) || 0;
      const subreddit = post?.getAttribute("subreddit-prefixed-name") || "";
      const createdAt = post?.getAttribute("created-timestamp") || "";

      // 본문 추출
      const bodyEl = document.querySelector('[slot="text-body"]')
        || document.querySelector(".text-neutral-content");
      const body = bodyEl ? bodyEl.textContent.trim() : "";

      return {
        title, author, score, commentCount, subreddit, createdAt, body,
        url: window.location.href,
      };
    },
  });

  return results[0]?.result || {};
}

// Reddit 댓글 목록 수집 (포스트 페이지에서)
async function redditGetComments(limit = 30) {
  const tabId = await getActiveTabId();

  const results = await chrome.scripting.executeScript({
    target: { tabId },
    func: (lim) => {
      const comments = [];
      const commentEls = document.querySelectorAll("shreddit-comment");
      for (const el of commentEls) {
        const author = el.getAttribute("author") || "unknown";
        const score = parseInt(el.getAttribute("score")) || 0;
        const depth = parseInt(el.getAttribute("depth")) || 0;
        const thingId = el.getAttribute("thingid") || "";

        // 댓글 본문
        const bodyEl = el.querySelector('[slot="comment"]')
          || el.querySelector(".md");
        const body = bodyEl ? bodyEl.textContent.trim().substring(0, 500) : "";

        if (body) {
          comments.push({ author, body, score, depth, thingId });
        }
        if (comments.length >= lim) break;
      }
      return comments;
    },
    args: [limit || 30],
  });

  return { comments: results[0]?.result || [] };
}

// Reddit 로그인 상태 확인
async function redditCheckLogin() {
  const tabId = await getActiveTabId();

  const results = await chrome.scripting.executeScript({
    target: { tabId },
    func: () => {
      // 여러 셀렉터로 로그인 감지 (Reddit UI 변경 대응)
      const expandBtn = document.querySelector("#expand-user-drawer-button");
      const userMenu = document.querySelector('[id*="user-drawer"]')
        || document.querySelector('button[aria-label*="profile"]')
        || document.querySelector('button[aria-label*="User"]')
        || document.querySelector('faceplate-dropdown-menu-button')
        || document.querySelector('[data-testid="user-menu-toggle"]');
      const loginBtn = document.querySelector('a[href*="login"]');
      const loginBtnAlt = document.querySelector('button[data-testid="login-button"]')
        || document.querySelector('a[data-testid="login-button"]');

      // 로그인 버튼이 없고, 유저 메뉴가 있으면 로그인된 것
      const hasUserElement = !!(expandBtn || userMenu);
      const hasLoginBtn = !!(loginBtn || loginBtnAlt);
      const loggedIn = hasUserElement || !hasLoginBtn;

      // 유저네임 추출 시도
      let username = expandBtn?.textContent?.trim() || "";
      if (!username && userMenu) {
        username = userMenu.textContent?.trim() || "";
      }

      return {
        loggedIn,
        username: username || null,
      };
    },
  });

  return results[0]?.result || { loggedIn: false };
}

// ═══ page-agent 스타일 DOM 트리 추출 ═══
async function getDomTree(maxDepth = 5, maxNodes = 200) {
  const tabId = await getActiveTabId();

  const results = await chrome.scripting.executeScript({
    target: { tabId },
    func: (mDepth, mNodes) => {
      let nodeCount = 0;
      const interactiveTags = new Set([
        "A", "BUTTON", "INPUT", "SELECT", "TEXTAREA",
        "SHREDDIT-POST", "SHREDDIT-COMMENT", "FACEPLATE-TEXTAREA-INPUT",
      ]);
      const interactiveRoles = new Set([
        "button", "link", "textbox", "checkbox", "radio", "menuitem", "tab",
      ]);

      // 전역 인덱스 매핑 저장 (clickByIndex/fillByIndex에서 사용)
      window.__redditDomMap = [];

      function traverse(el, depth) {
        if (nodeCount >= mNodes || depth > mDepth) return null;
        if (!el || el.nodeType !== 1) return null;

        const tag = el.tagName;
        const style = getComputedStyle(el);
        if (style.display === "none" || style.visibility === "hidden") return null;

        const isInteractive = interactiveTags.has(tag)
          || interactiveRoles.has(el.getAttribute("role"))
          || el.getAttribute("contenteditable") === "true"
          || el.hasAttribute("onclick")
          || el.hasAttribute("tabindex");

        const rect = el.getBoundingClientRect();
        const visible = rect.width > 0 && rect.height > 0;

        let node = null;

        if (isInteractive && visible) {
          const idx = window.__redditDomMap.length;
          window.__redditDomMap.push(el);
          nodeCount++;

          const text = (el.innerText || el.value || el.placeholder ||
            el.getAttribute("aria-label") || el.getAttribute("post-title") || "").trim().slice(0, 80);

          node = {
            idx, tag: tag.toLowerCase(),
            role: el.getAttribute("role"),
            type: el.type || null,
            text,
            href: el.href || null,
            rect: { x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height) },
          };

          // shreddit-post 추가 속성
          if (tag === "SHREDDIT-POST") {
            node.postTitle = el.getAttribute("post-title");
            node.author = el.getAttribute("author");
            node.score = el.getAttribute("score");
            node.permalink = el.getAttribute("permalink");
          }
          // shreddit-comment 추가 속성
          if (tag === "SHREDDIT-COMMENT") {
            node.author = el.getAttribute("author");
            node.score = el.getAttribute("score");
            node.depth = el.getAttribute("depth");
            node.thingId = el.getAttribute("thingid");
          }
        }

        // 자식 순회
        const children = [];
        for (const child of el.children) {
          const c = traverse(child, depth + 1);
          if (c) children.push(c);
        }

        if (node) {
          if (children.length) node.children = children;
          return node;
        }
        if (children.length === 1) return children[0];
        if (children.length > 1) return { tag: tag.toLowerCase(), children };
        return null;
      }

      const tree = traverse(document.body, 0);
      return { tree, totalNodes: nodeCount, url: location.href };
    },
    args: [maxDepth || 5, maxNodes || 200],
  });

  return results[0]?.result || {};
}

// page-agent 스타일 인덱스 기반 클릭
async function clickByIndex(index) {
  const tabId = await getActiveTabId();

  const results = await chrome.scripting.executeScript({
    target: { tabId },
    func: (idx) => {
      if (!window.__redditDomMap || !window.__redditDomMap[idx]) {
        throw new Error(`Index ${idx} not found — call getDomTree first`);
      }
      const el = window.__redditDomMap[idx];
      el.scrollIntoView({ behavior: "instant", block: "center" });
      const rect = el.getBoundingClientRect();
      const x = rect.left + rect.width / 2;
      const y = rect.top + rect.height / 2;
      const evtInit = { bubbles: true, cancelable: true, view: window, clientX: x, clientY: y };
      el.dispatchEvent(new PointerEvent("pointerenter", evtInit));
      el.dispatchEvent(new MouseEvent("mouseenter", evtInit));
      el.dispatchEvent(new PointerEvent("pointerover", evtInit));
      el.dispatchEvent(new MouseEvent("mouseover", evtInit));
      el.dispatchEvent(new PointerEvent("pointerdown", { ...evtInit, button: 0 }));
      el.dispatchEvent(new MouseEvent("mousedown", { ...evtInit, button: 0 }));
      el.focus();
      el.dispatchEvent(new PointerEvent("pointerup", { ...evtInit, button: 0 }));
      el.dispatchEvent(new MouseEvent("mouseup", { ...evtInit, button: 0 }));
      el.dispatchEvent(new MouseEvent("click", { ...evtInit, button: 0 }));
      return { success: true, tag: el.tagName.toLowerCase(), text: (el.innerText || "").slice(0, 50) };
    },
    args: [index],
  });

  return results[0]?.result;
}

// page-agent 스타일 인덱스 기반 입력
async function fillByIndex(index, value) {
  const tabId = await getActiveTabId();

  const results = await chrome.scripting.executeScript({
    target: { tabId },
    func: (idx, val) => {
      if (!window.__redditDomMap || !window.__redditDomMap[idx]) {
        throw new Error(`Index ${idx} not found — call getDomTree first`);
      }
      const el = window.__redditDomMap[idx];
      el.focus();
      const tag = el.tagName.toLowerCase();
      const isContentEditable = el.getAttribute("contenteditable") === "true" || el.isContentEditable;

      if (isContentEditable) {
        el.dispatchEvent(new InputEvent("beforeinput", { bubbles: true, cancelable: true, inputType: "insertText", data: val }));
        el.innerText = val;
        el.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertText", data: val }));
        el.dispatchEvent(new Event("change", { bubbles: true }));
      } else if (tag === "input" || tag === "textarea") {
        const proto = tag === "textarea" ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
        const nativeSetter = Object.getOwnPropertyDescriptor(proto, "value")?.set;
        if (nativeSetter) nativeSetter.call(el, val);
        else el.value = val;
        el.dispatchEvent(new Event("input", { bubbles: true }));
        el.dispatchEvent(new Event("change", { bubbles: true }));
      } else {
        document.execCommand("selectAll", false, null);
        document.execCommand("delete", false, null);
        document.execCommand("insertText", false, val);
      }
      return { success: true, tag, text: val.slice(0, 50) };
    },
    args: [index, value],
  });

  return results[0]?.result;
}

// ═══ Reddit 추가 전용 커맨드 ═══

// Reddit 업보트 (포스트 또는 댓글)
async function redditUpvote(selector) {
  const tabId = await getActiveTabId();

  const results = await chrome.scripting.executeScript({
    target: { tabId },
    func: (sel) => {
      // 셀렉터 지정 시 해당 요소 내에서, 아니면 페이지 첫 포스트
      const container = sel ? document.querySelector(sel) : document.querySelector("shreddit-post");
      if (!container) return { success: false, error: "대상 없음" };

      const upBtn = container.querySelector('button[upvote]')
        || container.querySelector('button[aria-label*="upvote"]')
        || container.querySelector('button[aria-label*="Upvote"]');

      if (!upBtn) return { success: false, error: "업보트 버튼 없음" };

      // 이미 눌려있는지 확인
      const pressed = upBtn.getAttribute("aria-pressed") === "true";
      if (pressed) return { success: true, alreadyUpvoted: true };

      const rect = upBtn.getBoundingClientRect();
      const x = rect.left + rect.width / 2;
      const y = rect.top + rect.height / 2;
      const evtInit = { bubbles: true, cancelable: true, view: window, clientX: x, clientY: y };
      upBtn.dispatchEvent(new PointerEvent("pointerdown", { ...evtInit, button: 0 }));
      upBtn.dispatchEvent(new MouseEvent("mousedown", { ...evtInit, button: 0 }));
      upBtn.dispatchEvent(new PointerEvent("pointerup", { ...evtInit, button: 0 }));
      upBtn.dispatchEvent(new MouseEvent("mouseup", { ...evtInit, button: 0 }));
      upBtn.dispatchEvent(new MouseEvent("click", { ...evtInit, button: 0 }));

      return { success: true };
    },
    args: [selector || null],
  });

  return results[0]?.result || { success: false };
}

// Reddit 검색 (서브레딧 내 or 전체)
async function redditSearch(query, subreddit, sort = "relevance", limit = 10) {
  const tabId = await getActiveTabId();

  const searchUrl = subreddit
    ? `https://www.reddit.com/r/${subreddit}/search/?q=${encodeURIComponent(query)}&restrict_sr=1&sort=${sort}`
    : `https://www.reddit.com/search/?q=${encodeURIComponent(query)}&sort=${sort}`;

  await chrome.tabs.update(tabId, { url: searchUrl });
  await waitForPageLoad();
  await new Promise(r => setTimeout(r, 2000));

  return await redditGetPosts(limit);
}

// Reddit 포스트 작성 (CDP + JS 하이브리드)
async function redditSubmitPost(subreddit, title, body, autoSubmit = false) {
  const tabId = await getActiveTabId();
  const log = [];

  // Step 1: 포스트 작성 페이지로 이동
  const submitUrl = `https://www.reddit.com/r/${subreddit}/submit?type=TEXT`;
  log.push(`Navigating to ${submitUrl}`);
  await chrome.tabs.update(tabId, { url: submitUrl });
  await waitForPageLoad();
  await new Promise(r => setTimeout(r, 3000));

  // Step 2: 제목 입력 (CDP typeText 사용)
  log.push("Entering title...");
  try {
    await ensureDebugger(tabId);

    // 제목 필드 찾기 + 클릭
    const titleResult = await chrome.scripting.executeScript({
      target: { tabId },
      func: () => {
        const titleInput = document.querySelector('textarea[name="title"]')
          || document.querySelector('div[data-testid="post-title"] textarea')
          || document.querySelector('input[name="title"]');
        if (titleInput) {
          titleInput.focus();
          titleInput.click();
          const rect = titleInput.getBoundingClientRect();
          return { found: true, x: rect.x + rect.width / 2, y: rect.y + rect.height / 2 };
        }
        return { found: false };
      },
    });

    const titleInfo = titleResult[0]?.result;
    if (titleInfo?.found) {
      await sendDebuggerCommand(tabId, "Input.dispatchMouseEvent", {
        type: "mousePressed", x: titleInfo.x, y: titleInfo.y, button: "left", clickCount: 1,
      });
      await sendDebuggerCommand(tabId, "Input.dispatchMouseEvent", {
        type: "mouseReleased", x: titleInfo.x, y: titleInfo.y, button: "left",
      });
      await new Promise(r => setTimeout(r, 300));

      // CDP로 텍스트 입력
      for (const ch of title) {
        await sendDebuggerCommand(tabId, "Input.dispatchKeyEvent", {
          type: "keyDown", text: ch, key: ch,
        });
        await sendDebuggerCommand(tabId, "Input.dispatchKeyEvent", {
          type: "keyUp", key: ch,
        });
        await new Promise(r => setTimeout(r, 20 + Math.random() * 30));
      }
      log.push("Title entered via CDP");
    } else {
      // Fallback: JS inject
      await chrome.scripting.executeScript({
        target: { tabId },
        func: (t) => {
          const input = document.querySelector('textarea[name="title"]')
            || document.querySelector('input[name="title"]');
          if (input) {
            const nativeSetter = Object.getOwnPropertyDescriptor(
              window.HTMLTextAreaElement?.prototype || window.HTMLInputElement?.prototype,
              "value"
            )?.set;
            if (nativeSetter) nativeSetter.call(input, t);
            else input.value = t;
            input.dispatchEvent(new Event("input", { bubbles: true }));
            input.dispatchEvent(new Event("change", { bubbles: true }));
          }
        },
        args: [title],
      });
      log.push("Title entered via JS fallback");
    }
  } catch (e) {
    log.push(`Title error: ${e.message}`);
  }

  await new Promise(r => setTimeout(r, 1000));

  // Step 3: 본문 입력
  log.push("Entering body...");
  try {
    const bodyResult = await chrome.scripting.executeScript({
      target: { tabId },
      func: () => {
        const editor = document.querySelector('div[contenteditable="true"]')
          || document.querySelector('.public-DraftEditor-content')
          || document.querySelector('div[role="textbox"]');
        if (editor) {
          editor.focus();
          editor.click();
          const rect = editor.getBoundingClientRect();
          return { found: true, x: rect.x + rect.width / 2, y: rect.y + rect.height / 2 };
        }
        return { found: false };
      },
    });

    const bodyInfo = bodyResult[0]?.result;
    if (bodyInfo?.found) {
      await sendDebuggerCommand(tabId, "Input.dispatchMouseEvent", {
        type: "mousePressed", x: bodyInfo.x, y: bodyInfo.y, button: "left", clickCount: 1,
      });
      await sendDebuggerCommand(tabId, "Input.dispatchMouseEvent", {
        type: "mouseReleased", x: bodyInfo.x, y: bodyInfo.y, button: "left",
      });
      await new Promise(r => setTimeout(r, 300));

      for (const ch of body) {
        if (ch === "\n") {
          await sendDebuggerCommand(tabId, "Input.dispatchKeyEvent", {
            type: "keyDown", key: "Enter", code: "Enter", windowsVirtualKeyCode: 13,
          });
          await sendDebuggerCommand(tabId, "Input.dispatchKeyEvent", {
            type: "keyUp", key: "Enter", code: "Enter",
          });
        } else {
          await sendDebuggerCommand(tabId, "Input.dispatchKeyEvent", {
            type: "keyDown", text: ch, key: ch,
          });
          await sendDebuggerCommand(tabId, "Input.dispatchKeyEvent", {
            type: "keyUp", key: ch,
          });
        }
        await new Promise(r => setTimeout(r, 15 + Math.random() * 25));
      }
      log.push("Body entered via CDP");
    } else {
      log.push("Body editor not found");
    }
  } catch (e) {
    log.push(`Body error: ${e.message}`);
  }

  await new Promise(r => setTimeout(r, 1000));

  // Step 4: 자동 제출 (autoSubmit == true일 때만)
  if (autoSubmit) {
    log.push("Auto-submitting...");
    const submitResult = await chrome.scripting.executeScript({
      target: { tabId },
      func: () => {
        const postBtn = Array.from(document.querySelectorAll("button")).find(
          (b) => b.textContent?.trim().toLowerCase() === "post"
        );
        if (postBtn && !postBtn.disabled) {
          postBtn.click();
          return { clicked: true };
        }
        return { clicked: false, error: "Post button not found or disabled" };
      },
    });
    const sr = submitResult[0]?.result;
    log.push(sr?.clicked ? "Submit clicked" : `Submit failed: ${sr?.error}`);

    if (sr?.clicked) {
      await new Promise(r => setTimeout(r, 5000));
      const tab = await chrome.tabs.get(tabId);
      const url = tab?.url || "";
      if (url.includes("/comments/")) {
        log.push(`Post successful! URL: ${url}`);
        return { success: true, url, log };
      }
      log.push(`Post URL check: ${url}`);
    }
  } else {
    log.push("Ready for manual submit (autoSubmit=false)");
  }

  return { success: autoSubmit, ready: !autoSubmit, log };
}

// Reddit 댓글에 답글 달기 (thingId 기반)
async function redditReplyToComment(thingId, body) {
  const tabId = await getActiveTabId();

  const results = await chrome.scripting.executeScript({
    target: { tabId },
    func: (tid, replyBody) => {
      // thingId로 댓글 찾기
      const comment = document.querySelector(`shreddit-comment[thingid="${tid}"]`);
      if (!comment) return { success: false, error: `댓글 ${tid} 없음` };

      // Reply 버튼 찾기
      const replyBtn = comment.querySelector('button[aria-label*="Reply"]')
        || comment.querySelector('button[aria-label*="reply"]');

      if (!replyBtn) return { success: false, error: "Reply 버튼 없음" };

      replyBtn.click();

      return new Promise((resolve) => {
        setTimeout(() => {
          // 답글 입력 영역 찾기 (댓글 내부)
          const editor = comment.querySelector('div[contenteditable="true"]')
            || comment.querySelector('faceplate-form div[contenteditable="true"]');

          if (!editor) {
            resolve({ success: false, error: "답글 입력 영역 없음" });
            return;
          }

          editor.focus();
          document.execCommand("selectAll", false, null);
          document.execCommand("delete", false, null);
          document.execCommand("insertText", false, replyBody);
          editor.dispatchEvent(new Event("input", { bubbles: true }));

          setTimeout(() => {
            const submitBtn = comment.querySelector('button[type="submit"]')
              || comment.querySelector('button[slot="submit-button"]');

            let btn = submitBtn;
            if (!btn) {
              const btns = comment.querySelectorAll("button");
              for (const b of btns) {
                const txt = b.textContent.trim().toLowerCase();
                if (txt === "reply" || txt === "comment") { btn = b; break; }
              }
            }

            if (btn && !btn.disabled) {
              btn.click();
              resolve({ success: true, message: "답글 제출됨" });
            } else {
              resolve({ success: false, error: "제출 버튼 없음", bodyEntered: true });
            }
          }, 1000);
        }, 1500);
      });
    },
    args: [thingId, body],
  });

  return results[0]?.result || { success: false };
}

// Reddit 현재 로그인 사용자 정보
async function redditGetUserInfo() {
  const tabId = await getActiveTabId();

  const results = await chrome.scripting.executeScript({
    target: { tabId },
    func: () => {
      const userBtn = document.querySelector("#expand-user-drawer-button");
      const username = userBtn?.textContent?.trim() || "";

      // 카르마 정보 (프로필 드로어에서)
      const karmaEls = document.querySelectorAll('[id*="karma"], [data-testid*="karma"]');
      let karma = null;
      for (const el of karmaEls) {
        const text = el.textContent.trim();
        if (text && /^\d/.test(text)) { karma = text; break; }
      }

      return {
        loggedIn: !!userBtn,
        username: username || null,
        karma,
        url: window.location.href,
      };
    },
  });

  return results[0]?.result || { loggedIn: false };
}

// Reddit 서브레딧으로 이동
async function redditNavigateSub(subreddit, sort = "hot") {
  const tabId = await getActiveTabId();
  const url = `https://www.reddit.com/r/${subreddit}/${sort}/`;
  await chrome.tabs.update(tabId, { url });
  await waitForPageLoad();
  await new Promise(r => setTimeout(r, 2000));

  // 서브레딧 정보 수집
  const results = await chrome.scripting.executeScript({
    target: { tabId },
    func: () => {
      const header = document.querySelector('shreddit-subreddit-header');
      const members = header?.getAttribute("subscribers") || "";
      const name = header?.getAttribute("display-name") || "";
      const desc = header?.getAttribute("public-description") || "";
      return {
        success: true,
        name, members, description: desc.slice(0, 200),
        url: location.href,
      };
    },
  });

  return results[0]?.result || { success: true, url: `https://www.reddit.com/r/${subreddit}/` };
}

// CDP 기반 좌표 클릭 — Shadow DOM 내부까지 도달
async function clickCoords(x, y) {
  const tabId = await getActiveTabId();
  await ensureDebugger(tabId);

  // mousePressed + mouseReleased (실제 브라우저 클릭)
  await sendDebuggerCommand(tabId, "Input.dispatchMouseEvent", {
    type: "mousePressed",
    x: Math.round(x),
    y: Math.round(y),
    button: "left",
    clickCount: 1,
  });
  await sendDebuggerCommand(tabId, "Input.dispatchMouseEvent", {
    type: "mouseReleased",
    x: Math.round(x),
    y: Math.round(y),
    button: "left",
    clickCount: 1,
  });

  return { success: true, x: Math.round(x), y: Math.round(y) };
}

// CDP 기반 텍스트 입력 — 키보드 이벤트로 실제 타이핑
async function typeText(text) {
  const tabId = await getActiveTabId();
  await ensureDebugger(tabId);

  for (const char of text) {
    await sendDebuggerCommand(tabId, "Input.dispatchKeyEvent", {
      type: "keyDown",
      text: char,
      key: char,
      code: `Key${char.toUpperCase()}`,
      unmodifiedText: char,
    });
    await sendDebuggerCommand(tabId, "Input.dispatchKeyEvent", {
      type: "keyUp",
      key: char,
      code: `Key${char.toUpperCase()}`,
    });
    // 봇 감지 회피: 50-200ms 랜덤 타이핑 딜레이 (인간 타이핑 속도 시뮬레이션)
    await new Promise(r => setTimeout(r, 50 + Math.random() * 150));
  }

  return { success: true, length: text.length };
}

// 디버거 attach 헬퍼
async function ensureDebugger(tabId) {
  if (isDebugging && debugTabId === tabId) return;

  // 기존 디버거 detach (어떤 탭이든)
  if (isDebugging && debugTabId) {
    try {
      await new Promise((r) => chrome.debugger.detach({ tabId: debugTabId }, () => r()));
    } catch {}
    isDebugging = false;
    debugTabId = null;
  }

  // 대상 탭의 기존 디버거도 detach 시도
  try {
    await new Promise((r) => chrome.debugger.detach({ tabId }, () => r()));
  } catch {}

  try {
    await new Promise((resolve, reject) => {
      chrome.debugger.attach({ tabId }, "1.3", () => {
        const err = chrome.runtime.lastError;
        if (err) return reject(new Error(err.message));
        resolve();
      });
    });
  } catch (e) {
    if (!e.message?.includes("Already attached")) throw e;
  }

  isDebugging = true;
  debugTabId = tabId;
  try { await sendDebuggerCommand(tabId, "Runtime.enable", {}); } catch {}
  try { await sendDebuggerCommand(tabId, "Input.enable", {}); } catch {}
}

// 스크립트 실행 (Debugger Runtime.evaluate — CSP 완전 우회)
async function evaluateScript(script) {
  const tabId = await getActiveTabId();

  // 디버거가 아직 안 붙어있으면 붙이기
  if (!isDebugging || debugTabId !== tabId) {
    if (isDebugging && debugTabId && debugTabId !== tabId) {
      try {
        await new Promise((r) => chrome.debugger.detach({ tabId: debugTabId }, r));
      } catch {}
    }
    await new Promise((resolve, reject) => {
      chrome.debugger.attach({ tabId }, "1.3", () => {
        const err = chrome.runtime.lastError;
        if (err) return reject(new Error(err.message));
        resolve();
      });
    });
    isDebugging = true;
    debugTabId = tabId;
    try { await sendDebuggerCommand(tabId, "Runtime.enable", {}); } catch {}
  }

  // Runtime.evaluate로 실행 (CSP 무시)
  const evalResult = await sendDebuggerCommand(tabId, "Runtime.evaluate", {
    expression: script,
    returnByValue: true,
    awaitPromise: false,
  });

  if (evalResult?.exceptionDetails) {
    return { result: { __error: evalResult.exceptionDetails.text || "eval error" } };
  }

  return { result: evalResult?.result?.value };
}

async function consoleStart(maxEntries = 500) {
  const tabId = await getActiveTabId();
  const nextMax = Math.max(50, Math.min(Number(maxEntries) || 500, 5000));
  consoleMaxEntries = nextMax;
  consoleBuffer = [];

  if (isDebugging && debugTabId === tabId) {
    return { success: true, tabId, alreadyAttached: true };
  }

  if (isDebugging && debugTabId && debugTabId !== tabId) {
    try {
      await new Promise((resolve) => chrome.debugger.detach({ tabId: debugTabId }, () => resolve()));
    } catch {}
    isDebugging = false;
    debugTabId = null;
  }

  await new Promise((resolve, reject) => {
    chrome.debugger.attach({ tabId }, "1.3", () => {
      const err = chrome.runtime.lastError;
      if (err) return reject(new Error(err.message));
      resolve();
    });
  });

  isDebugging = true;
  debugTabId = tabId;

  // Enable domains needed for console + errors.
  try {
    await sendDebuggerCommand(tabId, "Runtime.enable", {});
  } catch {}
  try {
    await sendDebuggerCommand(tabId, "Log.enable", {});
  } catch {}

  return { success: true, tabId, maxEntries: consoleMaxEntries };
}

async function consoleStop() {
  if (!isDebugging || !debugTabId) {
    return { success: true, detached: false };
  }
  const tabId = debugTabId;
  await new Promise((resolve) => chrome.debugger.detach({ tabId }, () => resolve()));
  isDebugging = false;
  debugTabId = null;
  return { success: true, detached: true };
}

async function consoleClear() {
  consoleBuffer = [];
  return { success: true };
}

async function consoleGet(limit = 200) {
  const lim = Math.max(1, Math.min(Number(limit) || 200, 2000));
  const logs = consoleBuffer.slice(-lim);
  return {
    attached: isDebugging,
    tabId: debugTabId,
    total: consoleBuffer.length,
    logs,
  };
}

// 메시지 핸들러 (popup에서 상태 확인용 + 녹화 액션 수신)
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === "getStatus") {
    sendResponse({ connected: ws && ws.readyState === WebSocket.OPEN });
  } else if (message.type === "recordedAction" && isRecording) {
    const action = message.action;
    action.id = `act-${recordingActions.length}`;

    // Take screenshot and attach to action
    chrome.tabs.captureVisibleTab(null, { format: "jpeg", quality: 60 }, (dataUrl) => {
      if (dataUrl) {
        action.screenshotBefore = dataUrl;
      }
      recordingActions.push(action);
    });
  }
  return true;
});

// Recording: inject content script and start
async function recordingStart() {
  const tabId = await getActiveTabId();

  if (isRecording) {
    return { success: false, message: "이미 녹화 중입니다." };
  }

  isRecording = true;
  recordingActions = [];
  recordingStartTime = Date.now();
  recordingTabId = tabId;

  const tab = await chrome.tabs.get(tabId);
  recordingStartUrl = tab.url || "";

  // Inject content script
  await chrome.scripting.executeScript({
    target: { tabId },
    files: ["record-content.js"],
  });

  return { success: true, tabId, url: recordingStartUrl };
}

// Recording: stop and return collected actions
async function recordingStop() {
  if (!isRecording) {
    return { success: false, message: "녹화 중이 아닙니다." };
  }

  // Cleanup content script
  if (recordingTabId) {
    try {
      await chrome.scripting.executeScript({
        target: { tabId: recordingTabId },
        func: () => {
          if (window.__redditRecorderCleanup) window.__redditRecorderCleanup();
        },
      });
    } catch (e) {
      // Tab may have been closed
    }
  }

  const result = {
    success: true,
    actions: recordingActions,
    url: recordingStartUrl,
    duration: Date.now() - recordingStartTime,
    actionCount: recordingActions.length,
  };

  isRecording = false;
  recordingActions = [];
  recordingStartTime = 0;
  recordingTabId = null;
  recordingStartUrl = "";

  return result;
}

// Re-inject content script on page navigation during recording
chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (!isRecording || tabId !== recordingTabId) return;

  if (changeInfo.status === "complete") {
    // Record navigate action
    recordingActions.push({
      id: `act-${recordingActions.length}`,
      type: "navigate",
      timestamp: Date.now() - recordingStartTime,
      url: tab.url || "",
    });

    // Re-inject content script
    chrome.scripting
      .executeScript({
        target: { tabId },
        files: ["record-content.js"],
      })
      .catch(() => {
        // Ignore injection errors (e.g., chrome:// pages)
      });
  }
});

// Extension 설치/업데이트 시 연결
chrome.runtime.onInstalled.addListener(() => {
  console.log("[레딧] Extension 설치/업데이트됨");
  connect();
});

// 브라우저 시작 시 연결
chrome.runtime.onStartup.addListener(() => {
  console.log("[레딧] 브라우저 시작됨");
  connect();
});

// 시작 시 연결 시도
connect();
