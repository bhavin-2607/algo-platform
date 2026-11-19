"""High-performance dark embedded terminal widget with real-time streaming and filtering."""

from __future__ import annotations

import datetime
import sys
import tkinter as tk
from collections import deque
from typing import List, Optional, Tuple

import customtkinter as ctk


class TerminalWidget(ctk.CTkFrame):
    """Integrated monospace dark terminal widget displaying real-time platform logs."""

    MAX_BUFFER_LINES = 5000

    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color="#080A0F", corner_radius=6, border_color="#1E2026", border_width=1, **kwargs)

        self._auto_scroll = True
        self._is_paused = False
        self._filter = "ALL"
        self._search_query = ""

        # Ring buffer storing (timestamp, tag, color, text)
        self._log_history: deque[Tuple[str, str, str, str]] = deque(maxlen=self.MAX_BUFFER_LINES)

        self._build_toolbar()
        self._build_console()

    def _build_toolbar(self):
        """Build terminal control toolbar (filter, search, auto-scroll, clear, copy)."""
        bar = ctk.CTkFrame(self, fg_color="#101114", height=38, corner_radius=0)
        bar.pack(side="top", fill="x")
        bar.pack_propagate(False)

        # Left: Filter
        filter_label = ctk.CTkLabel(bar, text="Filter:", text_color="#A1A1AA", font=ctk.CTkFont(size=11))
        filter_label.pack(side="left", padx=(10, 4), pady=4)

        self.filter_menu = ctk.CTkOptionMenu(
            bar,
            values=["ALL", "BACKEND", "WORKER", "BEAT", "PLATFORM", "ERRORS"],
            command=self._on_filter_changed,
            width=95,
            height=26,
            font=ctk.CTkFont(size=10),
            fg_color="#1E2026",
            button_color="#27272A",
            button_hover_color="#3F3F46",
            text_color="#FFFFFF",
        )
        self.filter_menu.set("ALL")
        self.filter_menu.pack(side="left", padx=4, pady=4)

        # Search box
        self.search_entry = ctk.CTkEntry(
            bar,
            placeholder_text="Search logs...",
            width=140,
            height=26,
            font=ctk.CTkFont(size=10),
            fg_color="#080A0F",
            border_color="#27272A",
            text_color="#FFFFFF",
        )
        self.search_entry.pack(side="left", padx=8, pady=4)
        self.search_entry.bind("<KeyRelease>", self._on_search_changed)

        # Right-side buttons: Copy, Clear, Pause, Auto-scroll
        copy_btn = ctk.CTkButton(
            bar,
            text="Copy",
            command=self._copy_all,
            width=50,
            height=24,
            font=ctk.CTkFont(size=10),
            fg_color="#1E2026",
            hover_color="#2E323D",
            text_color="#CBD5E1",
        )
        copy_btn.pack(side="right", padx=(4, 10), pady=4)

        clear_btn = ctk.CTkButton(
            bar,
            text="Clear",
            command=self.clear,
            width=50,
            height=24,
            font=ctk.CTkFont(size=10),
            fg_color="#1E2026",
            hover_color="#2E323D",
            text_color="#CBD5E1",
        )
        clear_btn.pack(side="right", padx=4, pady=4)

        self.pause_btn = ctk.CTkButton(
            bar,
            text="Pause",
            command=self._toggle_pause,
            width=55,
            height=24,
            font=ctk.CTkFont(size=10),
            fg_color="#1E2026",
            hover_color="#2E323D",
            text_color="#CBD5E1",
        )
        self.pause_btn.pack(side="right", padx=4, pady=4)

        self.scroll_check = ctk.CTkCheckBox(
            bar,
            text="Auto-Scroll",
            command=self._on_scroll_toggle,
            font=ctk.CTkFont(size=10),
            checkbox_width=16,
            checkbox_height=16,
            fg_color="#08B6DE",
            hover_color="#0693B3",
            text_color="#A1A1AA",
        )
        self.scroll_check.select()
        self.scroll_check.pack(side="right", padx=8, pady=4)

    def _build_console(self):
        """Build scrolled text box with monospace font and color tags."""
        font_family = "Consolas" if sys.platform.startswith("win") else "Menlo"
        self.textbox = ctk.CTkTextbox(
            self,
            fg_color="#050608",
            text_color="#E2E8F0",
            font=ctk.CTkFont(family=font_family, size=11),
            corner_radius=0,
            activate_scrollbars=True,
            wrap="none",
        )
        self.textbox.pack(side="bottom", fill="both", expand=True, padx=1, pady=1)

        # Setup standard color tags
        text_widget = self.textbox._textbox
        text_widget.tag_configure("time", foreground="#64748B")
        text_widget.tag_configure("PLATFORM", foreground="#38BDF8")
        text_widget.tag_configure("BACKEND", foreground="#06B6D4")
        text_widget.tag_configure("WORKER", foreground="#10B981")
        text_widget.tag_configure("BEAT", foreground="#D946EF")
        text_widget.tag_configure("IP-GUARD", foreground="#F5A623")
        text_widget.tag_configure("ERROR", foreground="#EF4444")
        text_widget.tag_configure("text", foreground="#CBD5E1")

    def append_log(self, tag: str, color: str, text: str):
        """Append a single log event and apply formatting tags."""
        now = datetime.datetime.now().strftime("%H:%M:%S")
        clean_tag = tag.strip().upper()
        self._log_history.append((now, clean_tag, color, text))

        if self._is_paused:
            return

        if not self._matches_filter(clean_tag, text):
            return

        self._render_line(now, clean_tag, color, text)

    def _render_line(self, now: str, tag: str, color: str, text: str):
        """Write formatted line to text widget with custom tag coloring."""
        text_widget = self.textbox._textbox
        tag_key = f"tag_{color.replace('#', '')}"
        try:
            text_widget.tag_configure(tag_key, foreground=color)
        except Exception:
            tag_key = tag

        line_header = f"{now} [{tag.ljust(8)}] "
        line_content = f"{text}\n"

        # Check line threshold to prevent GUI lag
        line_count = int(float(text_widget.index("end-1c")))
        if line_count > self.MAX_BUFFER_LINES:
            text_widget.delete("1.0", "500.0")

        text_widget.insert("end", line_header, tag_key)
        text_widget.insert("end", line_content, "text")

        if self._auto_scroll:
            text_widget.see("end")

    def _matches_filter(self, tag: str, text: str) -> bool:
        """Check if row satisfies active filter and search text."""
        f = self._filter
        if f != "ALL":
            if f == "ERRORS" and "ERROR" not in tag and "ERROR" not in text.upper():
                return False
            elif f != "ERRORS" and f not in tag:
                return False

        if self._search_query:
            if self._search_query.lower() not in text.lower():
                return False

        return True

    def _rebuild_display(self):
        """Re-render entire buffer based on new filter or search query."""
        text_widget = self.textbox._textbox
        text_widget.delete("1.0", "end")

        for now, tag, color, text in self._log_history:
            if self._matches_filter(tag, text):
                self._render_line(now, tag, color, text)

        if self._auto_scroll:
            text_widget.see("end")

    def _on_filter_changed(self, choice: str):
        self._filter = choice
        self._rebuild_display()

    def _on_search_changed(self, event=None):
        self._search_query = self.search_entry.get().strip()
        self._rebuild_display()

    def _on_scroll_toggle(self):
        self._auto_scroll = bool(self.scroll_check.get())

    def _toggle_pause(self):
        self._is_paused = not self._is_paused
        if self._is_paused:
            self.pause_btn.configure(text="Resume", fg_color="#F5A623", text_color="#000000")
        else:
            self.pause_btn.configure(text="Pause", fg_color="#1E2026", text_color="#CBD5E1")
            self._rebuild_display()

    def clear(self):
        """Clear active display buffer."""
        self._log_history.clear()
        self.textbox._textbox.delete("1.0", "end")

    def _copy_all(self):
        """Copy all log contents to system clipboard."""
        content = self.textbox._textbox.get("1.0", "end-1c")
        self.clipboard_clear()
        self.clipboard_append(content)
