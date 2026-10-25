// Watches the page for a login form and asks the background worker for
// credentials once per URL. Runs in the top frame only.
(() => {
  const WATCH_MS = 30000;
  let requestedFor = null;
  let timer = null;

  async function check() {
    if (requestedFor === location.href || !passvaultHasLoginForm()) return;
    requestedFor = location.href;
    let creds;
    try {
      creds = await chrome.runtime.sendMessage({ type: "loginFormFound" });
    } catch {
      return; // extension reloaded or worker unavailable
    }
    if (creds && creds.password !== undefined) {
      passvaultFill(creds.username, creds.password, location.hostname, true);
    }
  }

  // Login forms on single-page apps often appear after load.
  const observer = new MutationObserver(() => {
    clearTimeout(timer);
    timer = setTimeout(check, 300);
  });
  observer.observe(document.documentElement, { childList: true, subtree: true });
  setTimeout(() => observer.disconnect(), WATCH_MS);
  check();
})();
