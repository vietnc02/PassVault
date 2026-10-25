const HOST = "com.passvault.host";

async function send(message) {
  try {
    return (await chrome.runtime.sendNativeMessage(HOST, message)) || {};
  } catch {
    return { hostMissing: true };
  }
}

async function autoFillEnabled() {
  const { autoFill = true } = await chrome.storage.local.get("autoFill");
  return autoFill;
}

function badge(tabId, text, title) {
  chrome.action.setBadgeText({ tabId, text });
  chrome.action.setTitle({ tabId, title: `PassVault (Ctrl+Shift+L) – ${title}` });
}

// Returns credentials to fill, or null. The page URL comes from Chrome
// (sender.url), not from the page, so a page can't claim to be another site.
async function handleLoginForm(tab, url) {
  const list = await send({ action: "list", url });
  if (list.notRunning || list.locked) {
    badge(tab.id, "!", list.locked ? "đang khóa" : "chưa chạy");
    return null;
  }
  if (!list.entries) return null;

  const count = list.entries.length;
  badge(tab.id, count ? String(count) : "", count ? `${count} tài khoản cho trang này` : "không có tài khoản");
  // Only fill without asking when there's exactly one choice, over HTTPS.
  if (count !== 1 || !url.startsWith("https://") || !(await autoFillEnabled())) return null;

  const creds = await send({ action: "get", id: list.entries[0].id, url });
  return creds.password !== undefined ? { username: creds.username, password: creds.password } : null;
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message?.type !== "loginFormFound" || !sender.tab || sender.frameId !== 0) return;
  handleLoginForm(sender.tab, sender.url).then(sendResponse, () => sendResponse(null));
  return true; // keep the channel open for the async reply
});

chrome.runtime.onInstalled.addListener(() => {
  chrome.action.setBadgeBackgroundColor({ color: "#2f6fde" });
});
