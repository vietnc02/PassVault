// Shared form-filling logic. Loaded as a content script on every page and
// injected by the popup; only uses `var`/function declarations so injecting
// it twice into the same page is harmless.

function passvaultVisible(el) {
  if (el.disabled || el.readOnly || el.getClientRects().length === 0) return false;
  var style = getComputedStyle(el);
  return style.visibility !== "hidden" && style.display !== "none";
}

function passvaultHasLoginForm() {
  return [...document.querySelectorAll('input[type="password"], input[autocomplete~="username"]')]
    .some(passvaultVisible);
}

// auto: called on page load. Then it never overwrites what the user typed and
// never moves focus (focus can pop up Chrome/Windows passkey prompts).
function passvaultFill(username, password, expectedHost, auto) {
  if (location.hostname !== expectedHost) return { filled: false, reason: "host" };

  var isUserField = (el) => ["text", "email", "tel"].includes(el.type);
  var setValue = (el, value) => {
    if (!value || (auto && el.value)) return;
    // Use the native setter so frameworks like React notice the change.
    var setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set;
    setter.call(el, value);
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
  };

  var inputs = [...document.querySelectorAll("input")].filter(passvaultVisible);
  var passwordField = inputs.find((el) => el.type === "password") || null;

  var userField = inputs.find((el) => isUserField(el) && /\busername\b/.test(el.autocomplete)) || null;
  if (!userField && passwordField) {
    var before = inputs.slice(0, inputs.indexOf(passwordField)).filter(isUserField);
    var sameForm = before.filter((el) => el.form === passwordField.form);
    userField = (sameForm.length ? sameForm : before).at(-1) || null;
  }
  if (!userField && !passwordField) {
    // Multi-step logins (username first, password on the next page).
    var hint = /user|email|login|account|name|tai.?khoan/i;
    userField = inputs.find((el) => isUserField(el) && hint.test(el.name + el.id + el.autocomplete + el.placeholder))
      || inputs.find(isUserField) || null;
  }

  if (userField) setValue(userField, username);
  if (passwordField) setValue(passwordField, password);
  if (passwordField && !auto) passwordField.focus();
  return { filled: Boolean(userField || passwordField) };
}
