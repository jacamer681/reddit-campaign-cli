// record-content.js - Content Script for recording user browser actions
// Injected via chrome.scripting.executeScript() from background.js

(function () {
  if (window.__redditRecorderActive) return;
  window.__redditRecorderActive = true;

  const startTime = Date.now();

  function generateSelector(el) {
    if (el.id) return `#${el.id}`;
    if (el.name) return `[name="${el.name}"]`;

    let path = el.tagName.toLowerCase();
    if (el.className && typeof el.className === "string") {
      const classes = el.className
        .trim()
        .split(/\s+/)
        .filter((c) => !c.match(/^(hover|active|focus|visited|selected)/))
        .slice(0, 2)
        .join(".");
      if (classes) path += `.${classes}`;
    }

    // Add nth-child for disambiguation
    const parent = el.parentElement;
    if (parent) {
      const siblings = Array.from(parent.children).filter(
        (s) => s.tagName === el.tagName
      );
      if (siblings.length > 1) {
        const idx = siblings.indexOf(el) + 1;
        path += `:nth-child(${idx})`;
      }
    }

    return path;
  }

  function getElementText(el) {
    return (
      el.innerText?.trim().slice(0, 100) ||
      el.value ||
      el.placeholder ||
      el.getAttribute("aria-label") ||
      el.title ||
      ""
    );
  }

  function sendAction(action) {
    action.timestamp = Date.now() - startTime;
    action.url = location.href;
    try {
      chrome.runtime.sendMessage({ type: "recordedAction", action });
    } catch (e) {
      // Extension context invalidated - stop recording
      cleanup();
    }
  }

  // Click handler
  function onClick(e) {
    const el = e.target;
    if (!el || !el.tagName) return;

    sendAction({
      type: "click",
      selector: generateSelector(el),
      elementTag: el.tagName.toLowerCase(),
      elementText: getElementText(el),
      coordinates: { x: Math.round(e.clientX), y: Math.round(e.clientY) },
    });
  }

  // Input handler (debounced per element)
  const inputTimers = new WeakMap();
  function onInput(e) {
    const el = e.target;
    if (!el || !el.tagName) return;
    if (!["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName) && !el.isContentEditable) return;

    // Debounce: wait 500ms after last keystroke
    clearTimeout(inputTimers.get(el));
    inputTimers.set(
      el,
      setTimeout(() => {
        sendAction({
          type: "input",
          selector: generateSelector(el),
          elementTag: el.tagName.toLowerCase(),
          elementText: getElementText(el),
          value: el.isContentEditable ? el.innerText : el.value,
        });
      }, 500)
    );
  }

  // Keydown handler (special keys only)
  function onKeydown(e) {
    const specialKeys = ["Enter", "Tab", "Escape", "Backspace", "Delete", "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"];
    if (!specialKeys.includes(e.key)) return;

    sendAction({
      type: "keypress",
      key: e.key,
      selector: e.target ? generateSelector(e.target) : undefined,
      elementTag: e.target?.tagName?.toLowerCase(),
    });
  }

  // Scroll handler (debounced)
  let scrollTimer = null;
  let lastScrollY = window.scrollY;
  function onScroll() {
    clearTimeout(scrollTimer);
    scrollTimer = setTimeout(() => {
      const currentY = window.scrollY;
      const delta = currentY - lastScrollY;
      if (Math.abs(delta) < 50) return; // Ignore tiny scrolls

      sendAction({
        type: "scroll",
        scrollDirection: delta > 0 ? "down" : "up",
        scrollAmount: Math.abs(Math.round(delta)),
      });
      lastScrollY = currentY;
    }, 300);
  }

  // Attach listeners
  document.addEventListener("click", onClick, true);
  document.addEventListener("input", onInput, true);
  document.addEventListener("change", onInput, true);
  document.addEventListener("keydown", onKeydown, true);
  window.addEventListener("scroll", onScroll, { passive: true });

  // Cleanup function
  function cleanup() {
    document.removeEventListener("click", onClick, true);
    document.removeEventListener("input", onInput, true);
    document.removeEventListener("change", onInput, true);
    document.removeEventListener("keydown", onKeydown, true);
    window.removeEventListener("scroll", onScroll);
    window.__redditRecorderActive = false;
  }

  // Expose cleanup for external call
  window.__redditRecorderCleanup = cleanup;
})();
