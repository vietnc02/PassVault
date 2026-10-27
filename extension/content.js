// Watches the page for a login form, asks the background worker for
// credentials once per URL, and keeps filling as fields appear (the password
// box often shows up after the username box). Runs in the top frame only.
(() => {
  const WATCH_MS = 60000;
  let creds = null;
  let credsFor = null;
  let timer = null;

  async function check() {
    if (!passvaultHasLoginForm()) return;
    if (credsFor !== location.href) {
      credsFor = location.href;
      creds = null;
      try {
        creds = await chrome.runtime.sendMessage({ type: "loginFormFound" });
      } catch {
        return; // extension reloaded or worker unavailable
      }
    }
    // Auto mode never overwrites a field that already has a value.
    if (creds && creds.password !== undefined) {
      passvaultFill(creds.username, creds.password, location.hostname, true);
    }
  }

  // Login forms on single-page apps often appear, or become visible, after load.
  const observer = new MutationObserver(() => {
    clearTimeout(timer);
    timer = setTimeout(check, 300);
  });
  observer.observe(document.documentElement, {
    childList: true, subtree: true,
    attributes: true, attributeFilter: ["class", "style", "hidden", "type", "readonly", "disabled"],
  });
  setTimeout(() => {
    observer.disconnect();
    creds = null; // don't keep the password around longer than needed
  }, WATCH_MS);
  check();
})();
