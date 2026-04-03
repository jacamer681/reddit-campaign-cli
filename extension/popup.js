// 자동 업데이트 확인 - manifest 버전과 비교
async function checkAndReload() {
  try {
    const manifest = chrome.runtime.getManifest();
    // Fetch the latest manifest from disk (for unpacked extensions)
    const resp = await fetch(chrome.runtime.getURL("manifest.json") + "?t=" + Date.now());
    const diskManifest = await resp.json();
    if (diskManifest.version !== manifest.version) {
      console.log("[레딧] 새 버전 감지:", manifest.version, "→", diskManifest.version);
      chrome.runtime.reload();
      return;
    }
  } catch (e) {
    console.log("[레딧] 버전 확인 실패:", e);
  }
}

// 연결 상태 확인
async function checkStatus() {
  const statusEl = document.getElementById("status");

  try {
    // background에서 상태 확인
    const response = await chrome.runtime.sendMessage({ type: "getStatus" });
    if (response?.connected) {
      statusEl.className = "status connected";
      statusEl.textContent = "✓ 연결됨";
    } else {
      statusEl.className = "status disconnected";
      statusEl.textContent = "연결 대기 중...";
    }
  } catch (e) {
    statusEl.className = "status disconnected";
    statusEl.textContent = "연결 대기 중...";
  }
}

// 먼저 업데이트 확인, 그 다음 상태 확인
checkAndReload().then(() => {
  checkStatus();
  setInterval(checkStatus, 2000);
});
