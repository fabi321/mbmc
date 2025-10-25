#!/usr/bin/env python3
import tkinter as tk
from tkinter import simpledialog
from typing import List, Optional, Tuple
import webbrowser

from PIL import ImageTk

from musicbrainz_submit.prefetch import load_thumbnail
from musicbrainz_submit.providers.provider import Provider, Album


# ---------- GUI ----------
class CollectorApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("mbmc")
        self.geometry("820x600")

        # active provider panel state (single active)
        self.active_provider: Optional[Provider] = None
        self.active_panel = None  # reference to panel Frame
        self.candidates: List[Album] = []

        # internal waiting variable for ask_question
        self._answer_var: Optional[tk.StringVar] = None
        self._last_answer: Optional[Tuple[str, Optional[Album]]] = None

        self.query_label = None
        self.list_frame = None
        self.closed: bool = False

        # container / idle label
        self.container = tk.Frame(self)
        self.container.pack(fill=tk.BOTH, expand=True)

        # global key bindings
        self.bind_all("<Key>", self._on_key)
        self.protocol("WM_DELETE_WINDOW", self.close)

        self._clear_ui()

    def close(self):
        self._ignore_active()
        self.destroy()
        self.closed = True

    # ----- UI build / teardown -----
    def _clear_ui(self):
        for w in self.container.winfo_children():
            w.destroy()
        self.active_panel = None
        self.active_provider = None
        self.candidates = []

    # ----- show / replace provider -----
    def add_provider(self, provider: Provider, replace: bool = True):
        """
        Show provider immediately. Replaces any active provider.
        If a caller is currently waiting in ask_question(), a 'replaced' result
        will be produced and the waiting call will return.
        """

        # If someone is waiting, signal replacement before destroying UI
        if (
            self._answer_var is not None
            and self.active_provider is not None
            and replace
        ):
            # set last answer and trigger waiting call
            self._last_answer = ("replaced", None)
            self._answer_var.set("replaced")

        # remove previous UI
        self._clear_ui()

        # build UI for this provider
        self.active_provider = provider
        header = tk.Frame(self.container)
        header.pack(fill=tk.X, pady=6)
        tk.Label(header, text=provider.name, font=("Arial", 14, "bold")).pack(
            side=tk.LEFT
        )
        self.query_label = tk.Label(header, text=f"query: {provider.query}", fg="#555")
        self.query_label.pack(side=tk.LEFT, padx=(8, 0))
        tk.Button(header, text="Edit (e)", command=lambda: self._edit_query()).pack(
            side=tk.RIGHT
        )
        tk.Button(
            header, text="Ignore (q)", command=lambda: self._ignore_active()
        ).pack(side=tk.RIGHT, padx=(6, 0))
        tk.Button(
            header, text="Ban (b)", command=lambda: self._ban_active()
        ).pack(side=tk.RIGHT, padx=(6, 0))

        self.candidates = provider.filter()

        # list frame (only actual candidates)
        self.list_frame = tk.Frame(self.container)
        self.list_frame.pack(fill=tk.BOTH, expand=True, pady=6)
        for i, c in enumerate(self.candidates):
            row = tk.Frame(self.list_frame)
            row.pack(fill=tk.X, pady=2)
            tk.Label(row, text=str(i + 1), width=2, bg="#eef", relief=tk.RIDGE).pack(
                side=tk.LEFT, padx=(0, 6)
            )

            # thumbnail only if available (collapses otherwise)
            if c.thumbnail:
                img = load_thumbnail(c.thumbnail)
                if img:
                    img = ImageTk.PhotoImage(img)
                    lbl = tk.Label(row, image=img)
                    lbl.image = img
                    lbl.pack(side=tk.LEFT, padx=(0, 6))

            textframe = tk.Frame(row)
            textframe.pack(side=tk.LEFT, fill=tk.X, expand=True)
            tk.Label(
                textframe,
                text=c.title,
                font=("Arial", 10, "bold"),
                anchor="w",
                wraplength=480,
            ).pack(anchor="w")
            tk.Label(
                textframe, text=c.snippet, anchor="w", wraplength=480, fg="#444"
            ).pack(anchor="w")

            tk.Button(
                row, text="Open", command=lambda u=c.url: webbrowser.open(u)
            ).pack(side=tk.RIGHT)

        # store a simple marker as active_panel (to know we have UI)
        self.active_panel = header

    # ----- editing / ignore actions -----
    def _edit_query(self):
        new_q = simpledialog.askstring(
            "Edit query",
            f"New query for {self.active_provider.name}:",
            initialvalue=self.active_provider.query,
            parent=self,
        )
        if new_q is not None:
            self.active_provider.query = new_q
            # refresh UI synchronously
            self.add_provider(self.active_provider, replace=False)

    def _ignore_active(self):
        if not self.active_provider:
            return
        if self._answer_var is not None:
            self._last_answer = ("ignored", None)
            self._answer_var.set("ignored")
        self._clear_ui()

    def _ban_active(self):
        if not self.active_provider:
            return
        if self._answer_var is not None:
            self._last_answer = ("banned", self.candidates[0] if self.candidates else None)
            self._answer_var.set("banned")
        self._clear_ui()

    # ----- selection / keyboard handling -----
    def _accept_candidate_index(self, idx: int):
        if not self.active_provider:
            return
        if idx < 0 or idx >= len(self.candidates):
            return
        cand = self.candidates[idx]

        # if someone is waiting, set answer
        if self._answer_var is not None:
            self._last_answer = ("selected", cand)
            self._answer_var.set("selected")

        # tear down UI & call external on_provider_done asynchronously
        self._clear_ui()

    def _on_key(self, event):
        # ignore key events while typing in a text entry/dialog
        fw = self.focus_get()
        if fw is not None:
            try:
                top = fw.winfo_toplevel()
                if top is not self:
                    return
            except Exception:
                pass
            if isinstance(fw, (tk.Entry, tk.Text, tk.Spinbox)):
                return
            cls = fw.winfo_class().lower()
            if cls in ("entry", "text", "spinbox"):
                return

        if not self.active_provider:
            return

        k = event.char
        if k and k in "123456789":
            idx = int(k) - 1
            self._accept_candidate_index(idx)
        elif k.lower() == "q":
            self._ignore_active()
        elif k.lower() == "e":
            self._edit_query()
        elif k.lower() == "b":
            self._ban_active()

    # ----- ask_question API (linear flow) -----
    def ask_question(self, provider: Provider) -> Tuple[str, Optional[Album]]:
        """
        Show the provider and block (while processing GUI events) until the user answers.
        Returns: (result_type, candidate)
        result_type in {"selected","ignored","replaced","timeout"}.
        """
        if self.closed:
            raise RuntimeError("Cannot add a closed provider.")

        # Setup the waiting variable
        self._answer_var = tk.StringVar(value="")
        self._last_answer = None

        # show provider (this also replaces any previous provider; if replacement occurs
        # while we are already waiting, add_provider will set 'replaced' into the var)

        self.add_provider(provider)

        # wait_variable will block but allows event processing (suitable for linear code)
        self.wait_variable(self._answer_var)

        # capture result
        result = self._last_answer
        # clear waiting state
        self._answer_var = None
        self._last_answer = None

        # Ensure UI is cleared if not already
        # If provider was replaced/selected/ignored, add_provider/_accept/_ignore already cleared UI.
        return result if result is not None else ("timeout", None)
