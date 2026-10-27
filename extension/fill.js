// Shared form-filling logic. Loaded as a content script on every page and
// injected by the popup; only uses `var`/function declarations at top level so
// injecting it twice into the same page is harmless.

function passvaultVisible(el) {
  // Some sites make the password box read-only until it's focused, to block
  // browser autofill; still treat it as fillable.
  if (el.disabled || (el.readOnly && el.type !== "password") || el.getClientRects().length === 0) return false;
  var style = getComputedStyle(el);
  return style.visibility !== "hidden" && style.display !== "none";
}

// Some UI kits (e.g. DevExpress, used by ctt-sis.hust.edu.vn) hide the real
// password box and show a plain text "stand-in" holding the placeholder text;
// focusing the stand-in swaps the real box back in.
function passvaultStandIn(pw) {
  if (pw.disabled) return null;
  // Must sit right next to the real box and either be named after it
  // (DevExpress: "<id>_CLND") or show placeholder text, so a neighbouring
  // empty username box is never mistaken for one.
  return [pw.previousElementSibling, pw.nextElementSibling].find((el) =>
    el && el.tagName === "INPUT" && el.type === "text" && passvaultVisible(el) &&
    ((pw.id && el.id.startsWith(pw.id)) || el.value !== "")
  ) || null;
}

// Returns {field, anchor}: the password input to fill, and the visible element
// standing where it is on screen (the same input unless a stand-in is used).
function passvaultFindPassword(visibleInputs) {
  const shown = visibleInputs.find((el) => el.type === "password");
  if (shown) return { field: shown, anchor: shown };
  for (const pw of document.querySelectorAll('input[type="password"]')) {
    const standIn = passvaultStandIn(pw);
    if (standIn) return { field: pw, anchor: standIn };
  }
  return null;
}

function passvaultHasLoginForm() {
  const inputs = [...document.querySelectorAll("input")].filter(passvaultVisible);
  return Boolean(passvaultFindPassword(inputs)) || inputs.some((el) => /\busername\b/.test(el.autocomplete));
}

// auto: called on page load. Then it never overwrites what the user typed and
// only moves focus when a widget needs it (focus can pop up Chrome/Windows
// passkey prompts, so plain fields are filled without it).
function passvaultFill(username, password, expectedHost, auto) {
  if (location.hostname !== expectedHost) return { filled: false, reason: "host" };

  var isUserField = (el) => ["text", "email", "tel"].includes(el.type);
  // A value equal to the server-rendered one is placeholder text written into
  // the box ("Tài khoản") or a remembered value, not something the user typed.
  var untouched = (el) => el.value === "" || el.value === el.defaultValue;
  var setValue = (el, value, focusTarget) => {
    if (!value || (auto && !untouched(el))) return;
    // Placeholder-in-value widgets clear themselves (or swap boxes) on focus.
    var needsFocus = Boolean(focusTarget) || el.value !== "";
    if (needsFocus) (focusTarget || el).focus();
    // Use the native setter so frameworks like React notice the change.
    var setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set;
    setter.call(el, value);
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
    if (needsFocus && auto) el.blur();
  };

  var inputs = [...document.querySelectorAll("input")].filter(passvaultVisible);
  var pw = passvaultFindPassword(inputs);
  var anchor = pw ? pw.anchor : null;

  var userField = inputs.find((el) => el !== anchor && isUserField(el) && /\busername\b/.test(el.autocomplete)) || null;
  if (!userField && anchor) {
    var before = inputs.slice(0, inputs.indexOf(anchor)).filter(isUserField);
    var sameForm = before.filter((el) => el.form === anchor.form);
    userField = (sameForm.length ? sameForm : before).at(-1) || null;
  }
  if (!userField && !pw) {
    // Multi-step logins (username first, password on the next page).
    var hint = /user|email|login|account|name|tai.?khoan/i;
    userField = inputs.find((el) => isUserField(el) && hint.test(el.name + el.id + el.autocomplete + el.placeholder))
      || inputs.find(isUserField) || null;
  }

  if (userField) setValue(userField, username);
  if (pw) setValue(pw.field, password, pw.anchor !== pw.field ? pw.anchor : null);
  if (pw && !auto) pw.field.focus();
  return { filled: Boolean(userField || pw) };
}
