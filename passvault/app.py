"""Tkinter desktop UI for PassVault."""

import ctypes
import os
import queue
import sys
import threading
import time
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import messagebox, simpledialog, ttk

from . import autotype, ipc, settings
from .generator import generate_password
from .vault import Vault, VaultError, WrongPassword, default_vault_path

# In a PyInstaller build, bundled data lives under sys._MEIPASS.
ICON_PATH = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent)) / "assets" / "passvault.ico"
MIN_MASTER_LENGTH = 8
CLIPBOARD_CLEAR_SECONDS = 15
AUTO_LOCK_SECONDS = 5 * 60


class EntryDialog(tk.Toplevel):
    """Modal add/edit form. After wait_window(), `result` is a dict or None."""

    def __init__(self, parent, title: str, entry: dict | None = None):
        super().__init__(parent)
        self.title(title)
        self.transient(parent)
        self.resizable(False, False)
        self.result = None
        entry = entry or {}

        form = ttk.Frame(self, padding=12)
        form.pack(fill="both", expand=True)

        self.vars = {}
        defaults = {"autotype": autotype.DEFAULT_SEQUENCE}
        for row, (name, label) in enumerate([
            ("title", "Tên"), ("username", "Tài khoản"), ("password", "Mật khẩu"), ("url", "Website / App"),
            ("window", "Tiêu đề cửa sổ"), ("autotype", "Chuỗi tự gõ"),
        ]):
            ttk.Label(form, text=label).grid(row=row, column=0, sticky="w", pady=3)
            var = tk.StringVar(value=entry.get(name) or defaults.get(name, ""))
            widget = ttk.Entry(form, textvariable=var, width=40, show="•" if name == "password" else "")
            widget.grid(row=row, column=1, sticky="we", pady=3)
            self.vars[name] = var
            if name == "password":
                self.password_entry = widget

        tools = ttk.Frame(form)
        tools.grid(row=2, column=2, padx=(6, 0))
        self.show_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(tools, text="Hiện", variable=self.show_var, command=self._toggle_show).pack(side="left")
        ttk.Button(tools, text="Tạo", width=5, command=self._generate).pack(side="left", padx=(4, 0))

        ttk.Label(
            form, foreground="#777",
            text=f"Tự gõ ({parent.hotkey.label or 'phím tắt'}): "
                 "khớp khi tiêu đề cửa sổ chứa chữ ở trên.\n"
                 "Chuỗi dùng {USERNAME} {PASSWORD} {TAB} {ENTER}.",
        ).grid(row=6, column=1, sticky="w")

        ttk.Label(form, text="Ghi chú").grid(row=7, column=0, sticky="nw", pady=3)
        self.notes = tk.Text(form, width=40, height=4)
        self.notes.grid(row=7, column=1, sticky="we", pady=3)
        self.notes.insert("1.0", entry.get("notes", ""))

        buttons = ttk.Frame(form)
        buttons.grid(row=8, column=0, columnspan=3, sticky="e", pady=(10, 0))
        ttk.Button(buttons, text="Hủy", command=self.destroy).pack(side="right")
        ttk.Button(buttons, text="Lưu", command=self._save).pack(side="right", padx=(0, 6))

        self.bind("<Return>", lambda _e: self._save())
        self.bind("<Escape>", lambda _e: self.destroy())
        self.grab_set()
        self.focus_force()

    def _toggle_show(self):
        self.password_entry.configure(show="" if self.show_var.get() else "•")

    def _generate(self):
        self.vars["password"].set(generate_password())
        self.show_var.set(True)
        self._toggle_show()

    def _save(self):
        if not self.vars["title"].get().strip():
            messagebox.showwarning("Thiếu thông tin", "Hãy nhập Tên.", parent=self)
            return
        self.result = {name: var.get().strip() if name != "password" else var.get()
                       for name, var in self.vars.items()}
        self.result["notes"] = self.notes.get("1.0", "end-1c")
        self.destroy()


class AutoTypePicker(tk.Toplevel):
    """Shown on the Auto-Type hotkey: the user confirms which entry to type."""

    def __init__(self, app, hwnd, window_title: str):
        super().__init__(app)
        self.app, self.hwnd = app, hwnd
        self.title("PassVault – Tự gõ")
        self.resizable(False, False)
        self.attributes("-topmost", True)
        self.matches = autotype.match_entries(app.vault.entries, window_title)
        self.shown = []

        box = ttk.Frame(self, padding=10)
        box.pack(fill="both", expand=True)
        ttk.Label(box, text=f"Gõ vào: {window_title or '(cửa sổ không có tiêu đề)'}", wraplength=400).pack(anchor="w")
        self.hint = tk.StringVar()
        ttk.Label(box, textvariable=self.hint, foreground="#777").pack(anchor="w")
        self.query = tk.StringVar()
        self.query.trace_add("write", lambda *_: self._refresh())
        search = ttk.Entry(box, textvariable=self.query, width=55)
        search.pack(fill="x", pady=(6, 4))
        self.listbox = tk.Listbox(box, height=8, activestyle="dotbox", exportselection=False)
        self.listbox.pack(fill="both", expand=True)
        ttk.Label(box, foreground="#777", text="Enter: gõ · ↑↓: chọn · Esc: hủy").pack(anchor="w", pady=(4, 0))

        search.bind("<Down>", lambda _e: self._move(1))
        search.bind("<Up>", lambda _e: self._move(-1))
        self.bind("<Return>", lambda _e: self._choose())
        self.bind("<Escape>", lambda _e: self.destroy())
        self.listbox.bind("<Double-1>", lambda _e: self._choose())
        self._refresh()

        self.update_idletasks()
        x = (self.winfo_screenwidth() - self.winfo_reqwidth()) // 2
        y = (self.winfo_screenheight() - self.winfo_reqheight()) // 3
        self.geometry(f"+{x}+{y}")
        self.lift()
        self.focus_force()
        search.focus_set()

    def _refresh(self):
        query = self.query.get()
        if query.strip():
            self.shown = sorted(self.app.vault.search(query), key=lambda e: e["title"].lower())
            self.hint.set("Kết quả tìm kiếm:")
        elif self.matches:
            self.shown = self.matches
            self.hint.set("Tài khoản khớp với cửa sổ này:")
        else:
            self.shown = sorted(self.app.vault.entries, key=lambda e: e["title"].lower())
            self.hint.set("Không có tài khoản khớp — chọn trong danh sách hoặc gõ để tìm:")
        self.listbox.delete(0, "end")
        for entry in self.shown:
            self.listbox.insert("end", f"{entry['title']}  —  {entry['username']}")
        if self.shown:
            self.listbox.selection_set(0)

    def _move(self, step: int):
        if not self.shown:
            return
        current = self.listbox.curselection()
        index = max(0, min(len(self.shown) - 1, (current[0] if current else -1) + step))
        self.listbox.selection_clear(0, "end")
        self.listbox.selection_set(index)
        self.listbox.see(index)

    def _choose(self):
        selection = self.listbox.curselection()
        if not selection:
            return
        entry = self.shown[selection[0]]
        self.destroy()
        self.app.start_autotype(self.hwnd, entry)


class SettingsDialog(tk.Toplevel):
    """Lets the user pick the Auto-Type hotkey by pressing it."""

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title("Cài đặt")
        self.transient(app)
        self.resizable(False, False)
        self.capturing = False

        box = ttk.Frame(self, padding=16)
        box.pack(fill="both", expand=True)
        ttk.Label(box, text="Phím tắt Tự gõ", font=("Segoe UI", 10, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(box, foreground="#666", wraplength=360, text=(
            "Bấm vào ô tài khoản ở trang/app cần đăng nhập rồi nhấn phím này để PassVault gõ giúp."
        )).grid(row=1, column=0, columnspan=3, sticky="w", pady=(2, 10))

        self.current = tk.StringVar(value=app.hotkey.label or "(chưa có)")
        ttk.Label(box, textvariable=self.current, font=("Segoe UI", 16, "bold")).grid(row=2, column=0, sticky="w")
        self.change_button = ttk.Button(box, text="Đổi phím…", command=self._start_capture)
        self.change_button.grid(row=2, column=1, padx=(12, 4))
        ttk.Button(box, text="Mặc định", command=lambda: self._apply(*autotype.DEFAULT_HOTKEY)).grid(row=2, column=2)

        self.message = tk.StringVar()
        self.message_label = ttk.Label(box, textvariable=self.message, wraplength=360)
        self.message_label.grid(row=3, column=0, columnspan=3, sticky="w", pady=(10, 0))
        ttk.Button(box, text="Đóng", command=self.destroy).grid(row=4, column=2, sticky="e", pady=(14, 0))

        self.bind("<KeyPress>", self._on_key)
        self.grab_set()
        self.focus_force()

    def _say(self, text: str, error: bool = False):
        self.message.set(text)
        self.message_label.configure(foreground="#a33" if error else "#2a6b2a")

    def _start_capture(self):
        self.capturing = True
        self.change_button.state(["disabled"])
        self._say("Nhấn phím hoặc tổ hợp phím mới… (Esc để hủy)\n"
                  "Nếu nhấn mà không thấy gì, phím đó đang bị app khác dùng.")
        self.message_label.configure(foreground="#2f6fde")
        self.focus_force()

    def _stop_capture(self):
        self.capturing = False
        self.change_button.state(["!disabled"])

    def _on_key(self, event):
        if not self.capturing:
            return None
        vk = event.keycode  # on Windows, Tk reports the virtual-key code
        if vk == 0x1B:  # Esc
            self._stop_capture()
            self._say("Đã hủy.")
            return "break"
        if vk in autotype.MODIFIER_VKS:
            return "break"  # wait for the main key
        mods = autotype.held_modifiers()
        error = autotype.validate_hotkey(mods, vk)
        if error:
            self._say(error, error=True)
            return "break"
        self._stop_capture()
        self._apply(mods, vk)
        return "break"

    def _apply(self, mods: int, vk: int):
        name = autotype.format_hotkey(mods, vk)
        if self.app.hotkey.set_hotkey(mods, vk):
            settings.update(hotkey=[mods, vk])
            self.current.set(name)
            self._say(f"Đã đổi phím Tự gõ thành {name}.")
            self.app._hotkey_warning = None
            self.app.show_hints()
        else:
            self._say(f"{name} đang bị app khác dùng. Hãy chọn phím khác.", error=True)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("PassVault")
        if ICON_PATH.exists():
            # default= makes dialogs (add/edit, message boxes) use it too.
            self.iconbitmap(default=str(ICON_PATH))
        self.geometry("820x480")
        self.minsize(640, 360)
        self.vault_path = default_vault_path()
        self.vault: Vault | None = None
        self._copied_text = None
        self._clear_job = None
        self._last_activity = time.monotonic()

        for sequence in ("<Any-KeyPress>", "<Any-ButtonPress>", "<Motion>"):
            self.bind_all(sequence, self._touch, add="+")
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._idle_job = self.after(5000, self._check_idle)

        # Requests from the Chrome extension arrive on a background thread;
        # anything that touches Tk is queued and run on the main thread.
        self._ui_queue = queue.Queue()
        self._drain_job = self.after(200, self._drain_ui_queue)
        self.ipc = ipc.IpcServer(self._handle_ipc)
        self.ipc.start()

        self._pending_autotype = None  # (hwnd, title, time) from a hotkey pressed while locked
        self.hotkey = autotype.HotkeyListener(lambda: self._ui_queue.put(self._on_hotkey))
        preferred = tuple(settings.load().get("hotkey") or autotype.DEFAULT_HOTKEY)
        registered = self.hotkey.start(preferred)
        self._hotkey_warning = None
        if registered != preferred:
            self._hotkey_warning = f"Phím {autotype.format_hotkey(*preferred)} đang bị app khác dùng"

        self.container = ttk.Frame(self)
        self.container.pack(fill="both", expand=True)
        self.show_unlock()

    # ---- screens ---------------------------------------------------------

    def _clear_screen(self):
        for child in self.container.winfo_children():
            child.destroy()

    def show_unlock(self):
        self._clear_screen()
        creating = not self.vault_path.exists()

        box = ttk.Frame(self.container, padding=24)
        box.place(relx=0.5, rely=0.45, anchor="center")
        heading = "Tạo kho mật khẩu mới" if creating else "Mở khóa PassVault"
        ttk.Label(box, text=heading, font=("Segoe UI", 14, "bold")).grid(row=0, column=0, columnspan=2, pady=(0, 12))

        ttk.Label(box, text="Mật khẩu chính").grid(row=1, column=0, sticky="w", pady=3)
        password = ttk.Entry(box, show="•", width=30)
        password.grid(row=1, column=1, pady=3)
        confirm = None
        if creating:
            ttk.Label(box, text="Nhập lại").grid(row=2, column=0, sticky="w", pady=3)
            confirm = ttk.Entry(box, show="•", width=30)
            confirm.grid(row=2, column=1, pady=3)
            ttk.Label(
                box, foreground="#a33",
                text="Không có cách khôi phục nếu quên mật khẩu chính.",
            ).grid(row=3, column=0, columnspan=2, pady=(6, 0))

        def submit(_event=None):
            if creating:
                self._create_vault(password.get(), confirm.get())
            else:
                self._unlock(password.get())

        ttk.Button(box, text="Tạo" if creating else "Mở khóa", command=submit).grid(
            row=4, column=0, columnspan=2, pady=(12, 0)
        )
        ttk.Label(box, text=str(self.vault_path), foreground="#888").grid(row=5, column=0, columnspan=2, pady=(12, 0))
        password.bind("<Return>", submit)
        if confirm is not None:
            confirm.bind("<Return>", submit)
        password.focus_set()

    def show_main(self):
        self._clear_screen()

        toolbar = ttk.Frame(self.container, padding=(8, 8, 8, 4))
        toolbar.pack(fill="x")
        for text, command in [
            ("Thêm", self.add_entry),
            ("Sửa", self.edit_entry),
            ("Xóa", self.delete_entry),
            ("Copy tài khoản", lambda: self.copy_field("username")),
            ("Copy mật khẩu", lambda: self.copy_field("password")),
            ("Mở website", self.open_url),
        ]:
            ttk.Button(toolbar, text=text, command=command).pack(side="left", padx=(0, 4))
        ttk.Button(toolbar, text="Khóa", command=self.lock).pack(side="right")
        ttk.Button(toolbar, text="Đổi mật khẩu chính", command=self.change_master).pack(side="right", padx=(0, 4))
        ttk.Button(toolbar, text="Cài đặt", command=lambda: SettingsDialog(self)).pack(side="right", padx=(0, 4))

        search_row = ttk.Frame(self.container, padding=(8, 0, 8, 4))
        search_row.pack(fill="x")
        ttk.Label(search_row, text="Tìm:").pack(side="left")
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self.refresh())
        search = ttk.Entry(search_row, textvariable=self.search_var)
        search.pack(side="left", fill="x", expand=True, padx=(4, 0))

        table_frame = ttk.Frame(self.container, padding=(8, 0, 8, 0))
        table_frame.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(table_frame, columns=("title", "username", "url"), show="headings", selectmode="browse")
        for column, label, width in [("title", "Tên", 200), ("username", "Tài khoản", 220), ("url", "Website / App", 300)]:
            self.tree.heading(column, text=label)
            self.tree.column(column, width=width)
        scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.tree.bind("<Double-1>", lambda _e: self.edit_entry())
        self.tree.bind("<Control-c>", lambda _e: self.copy_field("password"))
        self.tree.bind("<Control-b>", lambda _e: self.copy_field("username"))

        self.status = tk.StringVar()
        ttk.Label(self.container, textvariable=self.status, padding=(8, 4), foreground="#555").pack(fill="x")
        self.show_hints()

        self.refresh()
        search.focus_set()

    # ---- vault actions ---------------------------------------------------

    def _create_vault(self, password: str, confirm: str):
        if len(password) < MIN_MASTER_LENGTH:
            messagebox.showwarning("Mật khẩu yếu", f"Mật khẩu chính cần ít nhất {MIN_MASTER_LENGTH} ký tự.")
            return
        if password != confirm:
            messagebox.showwarning("Không khớp", "Hai mật khẩu không giống nhau.")
            return
        try:
            self.vault = Vault.create(self.vault_path, password)
        except (VaultError, OSError) as exc:
            messagebox.showerror("Lỗi", str(exc))
            return
        self.show_main()

    def _unlock(self, password: str):
        self.config(cursor="watch")
        self.update_idletasks()
        try:
            self.vault = Vault.open(self.vault_path, password)
        except WrongPassword:
            messagebox.showerror("Sai mật khẩu", "Mật khẩu chính không đúng.")
            return
        except VaultError as exc:
            messagebox.showerror("Lỗi", str(exc))
            return
        finally:
            self.config(cursor="")
        self.show_main()
        # Hotkey was pressed while locked: carry on to the picker if it was recent.
        pending, self._pending_autotype = self._pending_autotype, None
        if pending and time.monotonic() - pending[2] < 60:
            AutoTypePicker(self, pending[0], pending[1])

    def lock(self):
        # Close any open add/edit dialog so it can't write to a locked vault.
        for child in self.winfo_children():
            if isinstance(child, tk.Toplevel):
                child.destroy()
        if self.vault is not None:
            self.vault.lock()
        self.vault = None
        self._clear_clipboard()
        self.show_unlock()

    def change_master(self):
        new = simpledialog.askstring("Đổi mật khẩu chính", "Mật khẩu chính mới:", show="•", parent=self)
        if new is None:
            return
        if len(new) < MIN_MASTER_LENGTH:
            messagebox.showwarning("Mật khẩu yếu", f"Cần ít nhất {MIN_MASTER_LENGTH} ký tự.")
            return
        again = simpledialog.askstring("Đổi mật khẩu chính", "Nhập lại:", show="•", parent=self)
        if again != new:
            messagebox.showwarning("Không khớp", "Hai mật khẩu không giống nhau.")
            return
        self.vault.change_password(new)
        self.set_status("Đã đổi mật khẩu chính.")

    # ---- entries ---------------------------------------------------------

    def refresh(self):
        selected = self._selected_id()
        self.tree.delete(*self.tree.get_children())
        entries = sorted(self.vault.search(self.search_var.get()), key=lambda e: e["title"].lower())
        for entry in entries:
            self.tree.insert("", "end", iid=entry["id"], values=(entry["title"], entry["username"], entry["url"]))
        if selected and self.tree.exists(selected):
            self.tree.selection_set(selected)
        elif entries:
            self.tree.selection_set(entries[0]["id"])

    def _selected_id(self):
        if not hasattr(self, "tree"):
            return None
        selection = self.tree.selection()
        return selection[0] if selection else None

    def _selected_entry(self):
        entry_id = self._selected_id()
        if entry_id is None:
            self.set_status("Chưa chọn mục nào.")
            return None
        return self.vault.get(entry_id)

    def add_entry(self):
        dialog = EntryDialog(self, "Thêm tài khoản")
        self.wait_window(dialog)
        if dialog.result:
            entry = self.vault.add(**dialog.result)
            self.refresh()
            self.tree.selection_set(entry["id"])
            self.tree.see(entry["id"])
            self.set_status(f"Đã thêm “{entry['title']}”.")

    def edit_entry(self):
        entry = self._selected_entry()
        if entry is None:
            return
        dialog = EntryDialog(self, "Sửa tài khoản", entry)
        self.wait_window(dialog)
        if dialog.result:
            self.vault.update(entry["id"], **dialog.result)
            self.refresh()
            self.set_status(f"Đã lưu “{dialog.result['title']}”.")

    def delete_entry(self):
        entry = self._selected_entry()
        if entry is None:
            return
        if messagebox.askyesno("Xóa", f"Xóa “{entry['title']}”? Không thể hoàn tác."):
            self.vault.delete(entry["id"])
            self.refresh()
            self.set_status("Đã xóa.")

    def open_url(self):
        entry = self._selected_entry()
        if entry is None:
            return
        url = entry["url"].strip()
        if not url:
            self.set_status("Mục này chưa có website.")
            return
        if "://" not in url:
            url = "https://" + url
        webbrowser.open(url)

    # ---- clipboard -------------------------------------------------------

    def copy_field(self, field: str):
        entry = self._selected_entry()
        if entry is None or not entry[field]:
            return
        self.clipboard_clear()
        self.clipboard_append(entry[field])
        self._copied_text = entry[field]
        if self._clear_job:
            self.after_cancel(self._clear_job)
        self._clear_job = self.after(CLIPBOARD_CLEAR_SECONDS * 1000, self._clear_clipboard)
        label = "mật khẩu" if field == "password" else "tài khoản"
        self.set_status(f"Đã copy {label} của “{entry['title']}”. Tự xóa sau {CLIPBOARD_CLEAR_SECONDS} giây.")

    def _clear_clipboard(self):
        self._clear_job = None
        if self._copied_text is None:
            return
        try:
            # Only wipe it if it still holds what we put there.
            if self.clipboard_get() == self._copied_text:
                self.clipboard_clear()
                self.clipboard_append("")
        except tk.TclError:
            pass
        self._copied_text = None
        if self.vault is not None:
            self.set_status("Đã xóa clipboard.")

    # ---- browser autofill ------------------------------------------------

    def _handle_ipc(self, message: dict) -> dict:
        action = message.get("action")
        if action == "show":
            self._ui_queue.put(self._bring_to_front)
            return {"ok": True}

        vault = self.vault
        if vault is None:
            return {"locked": True}
        page_url = str(message.get("url", ""))

        if action == "list":
            return {"entries": [
                {"id": e["id"], "title": e["title"], "username": e["username"]}
                for e in list(vault.entries) if ipc.url_matches(e["url"], page_url)
            ]}
        if action == "get":
            try:
                entry = vault.get(str(message.get("id", "")))
            except KeyError:
                return {"error": "Không tìm thấy mục này."}
            # Never hand a password to a page the entry doesn't belong to.
            if not ipc.url_matches(entry["url"], page_url):
                return {"error": "Mục này không thuộc trang hiện tại."}
            self._ui_queue.put(lambda: self.set_status(f"Đã tự điền “{entry['title']}” trên trình duyệt."))
            return {"username": entry["username"], "password": entry["password"]}
        return {"error": "Yêu cầu không hợp lệ."}

    # ---- auto-type -------------------------------------------------------

    def _on_hotkey(self):
        self._touch()
        hwnd, title, pid = autotype.foreground_window()
        if not hwnd or pid == os.getpid():
            return  # nothing to type into, or it's PassVault itself
        if self.vault is None:
            self._pending_autotype = (hwnd, title, time.monotonic())
            self._bring_to_front()
            return
        for child in self.winfo_children():
            if isinstance(child, AutoTypePicker):
                child.destroy()
        AutoTypePicker(self, hwnd, title)

    def start_autotype(self, hwnd, entry: dict):
        sequence = entry.get("autotype") or autotype.DEFAULT_SEQUENCE
        username, password, title = entry["username"], entry["password"], entry["title"]

        def run():
            try:
                autotype.perform(hwnd, sequence, username, password)
                message = f"Đã tự gõ “{title}”."
            except autotype.AutoTypeError as exc:
                message = f"Tự gõ không thành công: {exc}"
            self._ui_queue.put(lambda: self.set_status(message))

        threading.Thread(target=run, daemon=True).start()

    def _drain_ui_queue(self):
        while True:
            try:
                self._ui_queue.get_nowait()()
            except queue.Empty:
                break
        self._drain_job = self.after(200, self._drain_ui_queue)

    def _bring_to_front(self):
        self.deiconify()
        self.lift()
        self.attributes("-topmost", True)
        self.after(300, lambda: self.attributes("-topmost", False))
        self.focus_force()

    # ---- housekeeping ----------------------------------------------------

    def show_hints(self):
        if self.hotkey.label:
            hotkey = f"Tự gõ: {self.hotkey.label}"
            if self._hotkey_warning:
                hotkey += f" ({self._hotkey_warning}, đổi trong Cài đặt)"
        else:
            hotkey = "Tự gõ: chưa có phím tắt, chọn trong Cài đặt"
        self.set_status(f"Ctrl+B: copy tài khoản · Ctrl+C: copy mật khẩu · Nhấp đúp: sửa · {hotkey}")

    def set_status(self, text: str):
        if hasattr(self, "status"):
            try:
                self.status.set(text)
            except tk.TclError:
                pass

    def _touch(self, _event=None):
        self._last_activity = time.monotonic()

    def _check_idle(self):
        if self.vault is not None and time.monotonic() - self._last_activity > AUTO_LOCK_SECONDS:
            self.lock()
        self._idle_job = self.after(5000, self._check_idle)

    def _on_close(self):
        self._clear_clipboard()
        self.ipc.close()
        self.hotkey.stop()
        for job in (self._idle_job, self._drain_job, self._clear_job):
            if job:
                self.after_cancel(job)
        self.destroy()


def main():
    # If PassVault is already running, bring that window forward instead.
    try:
        ipc.request({"action": "show"})
        return
    except ipc.NotRunning:
        pass
    if sys.platform == "win32":
        # Own taskbar identity, so Windows shows PassVault's icon instead of Python's.
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("PassVault")
    App().mainloop()


if __name__ == "__main__":
    main()
