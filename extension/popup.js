const HOST = "com.passvault.host";

const siteEl = document.getElementById("site");
const listEl = document.getElementById("entries");
const messageEl = document.getElementById("message");
const actionEl = document.getElementById("action");

async function send(message) {
  try {
    return (await chrome.runtime.sendNativeMessage(HOST, message)) || {};
  } catch (err) {
    return { hostMissing: true, error: String(err && err.message || err) };
  }
}

function showMessage(text, { warn = false, button = null, onClick = null } = {}) {
  messageEl.textContent = text;
  messageEl.className = warn ? "warn" : "";
  messageEl.hidden = false;
  actionEl.hidden = !button;
  if (button) {
    actionEl.textContent = button;
    actionEl.onclick = onClick;
    actionEl.focus();
  }
}

// Shown when the app can't answer; offers to open/unlock it.
function handleUnavailable(res) {
  if (res.hostMissing) {
    showMessage("Chưa cài kết nối với app. Chạy install_autofill.bat trong thư mục PassVault rồi khởi động lại Chrome.", { warn: true });
  } else if (res.notRunning || res.locked) {
    showMessage(res.notRunning ? "PassVault chưa chạy." : "PassVault đang khóa.", {
      button: res.notRunning ? "Mở PassVault" : "Mở khóa",
      onClick: async () => {
        await send({ action: "show" });
        showMessage("Mở khóa PassVault rồi bấm lại biểu tượng này (Ctrl+Shift+L).");
      },
    });
  } else if (res.error) {
    showMessage(res.error, { warn: true });
  } else {
    return false;
  }
  return true;
}

async function fill(tab, entry) {
  const res = await send({ action: "get", id: entry.id, url: tab.url });
  if (handleUnavailable(res)) return;
  try {
    // Tabs opened before the extension was loaded don't have fill.js yet.
    await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ["fill.js"] });
    const [injection] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: (username, password, host) => passvaultFill(username, password, host, false),
      args: [res.username, res.password, new URL(tab.url).hostname],
    });
    if (injection && injection.result && injection.result.filled) {
      window.close();
    } else {
      showMessage("Không tìm thấy ô đăng nhập trên trang này.", { warn: true });
    }
  } catch (err) {
    showMessage("Không điền được vào trang này: " + (err.message || err), { warn: true });
  }
}

function render(tab, entries) {
  listEl.replaceChildren();
  for (const entry of entries) {
    const button = document.createElement("button");
    const title = document.createElement("div");
    title.className = "title";
    title.textContent = entry.title;
    const user = document.createElement("div");
    user.className = "user";
    user.textContent = entry.username || "(không có tài khoản)";
    button.append(title, user);
    button.addEventListener("click", () => fill(tab, entry));
    const li = document.createElement("li");
    li.append(button);
    listEl.append(li);
  }
  listEl.querySelector("button")?.focus();
}

async function initAutofillToggle() {
  const toggle = document.getElementById("autofill");
  const { autoFill = true } = await chrome.storage.local.get("autoFill");
  toggle.checked = autoFill;
  toggle.addEventListener("change", () => chrome.storage.local.set({ autoFill: toggle.checked }));
}

async function init() {
  initAutofillToggle();
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab || !tab.url || !/^https?:/.test(tab.url)) {
    showMessage("Trang này không hỗ trợ tự điền.");
    return;
  }
  const host = new URL(tab.url).hostname;
  siteEl.textContent = host;

  const res = await send({ action: "list", url: tab.url });
  if (handleUnavailable(res)) return;
  if (!res.entries || res.entries.length === 0) {
    showMessage(`Chưa có tài khoản cho trang này. Trong PassVault, thêm mục với Website là “${host.replace(/^www\./, "")}”.`);
    return;
  }
  render(tab, res.entries);
}

init();
