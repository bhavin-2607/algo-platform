"""Modern Modal Settings Dialog for inspecting and editing .env configurations."""

from __future__ import annotations

import sys
from typing import Callable, Dict, Optional

import customtkinter as ctk

from launcher.config import get_asset_path, load_env_dict, update_env_variable
from launcher.ip_guard import IPGuardStatus


class SettingsDialog(ctk.CTkToplevel):
    """Modern modal dialog for configuring credentials, network ports, and environment variables."""

    def __init__(self, parent, ip_status: IPGuardStatus, on_save_callback: Optional[Callable[[], None]] = None):
        super().__init__(parent)
        self.parent = parent
        self.ip_status = ip_status
        self.on_save_callback = on_save_callback

        self.title("Algo Platform - Settings & Environment Config")
        self.geometry("660x660")
        self.minsize(580, 520)
        self.configure(fg_color="#0A0B0E")

        # Set titlebar icon if on Windows
        ico_path = get_asset_path("app_icon.ico")
        if sys.platform == "win32" and ico_path.exists():
            try:
                self.iconbitmap(default=str(ico_path))
            except Exception:
                pass

        # Center on parent window and set modal grab
        self.transient(parent)
        self._center_window(parent)
        self.grab_set()

        self._entries: Dict[str, ctk.CTkEntry] = {}
        self._token_visible = False

        self._build_ui()
        self._load_values()
        self._bind_scroll_tree(self)
        self._bind_keyboard_shortcuts()

    def _center_window(self, parent):
        """Center the dialog over the parent application window."""
        try:
            self.update_idletasks()
            pw = parent.winfo_width()
            ph = parent.winfo_height()
            px = parent.winfo_x()
            py = parent.winfo_y()
            w = 660
            h = 660
            x = max(30, px + (pw - w) // 2)
            y = max(30, py + (ph - h) // 2)
            self.geometry(f"{w}x{h}+{x}+{y}")
        except Exception:
            pass

    def _build_ui(self):
        # 1. FIXED BOTTOM ACTION BAR
        footer = ctk.CTkFrame(self, fg_color="#0E1015", border_color="#1E2026", border_width=1, corner_radius=0, height=58)
        footer.pack(side="bottom", fill="x")
        footer.pack_propagate(False)

        btn_row = ctk.CTkFrame(footer, fg_color="transparent")
        btn_row.pack(fill="x", padx=16, pady=12)

        self.lbl_feedback = ctk.CTkLabel(
            btn_row,
            text="",
            font=ctk.CTkFont(size=11),
            text_color="#10B981",
        )
        self.lbl_feedback.pack(side="left", padx=4)

        cancel_btn = ctk.CTkButton(
            btn_row,
            text="Cancel",
            command=self.destroy,
            width=90,
            height=32,
            fg_color="#1E2026",
            hover_color="#2E323D",
            border_color="#27272A",
            border_width=1,
            text_color="#A1A1AA",
            font=ctk.CTkFont(size=11),
        )
        cancel_btn.pack(side="right", padx=(8, 0))

        save_btn = ctk.CTkButton(
            btn_row,
            text="Save Changes",
            command=self._save_settings,
            width=125,
            height=32,
            fg_color="#08B6DE",
            hover_color="#0693B3",
            text_color="#FFFFFF",
            font=ctk.CTkFont(size=11, weight="bold"),
        )
        save_btn.pack(side="right")

        # 2. SCROLLABLE SETTINGS CONTAINER
        self.scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.scroll.pack(fill="both", expand=True, padx=16, pady=(12, 0))

        # Header Title with Logo
        title_box = ctk.CTkFrame(self.scroll, fg_color="transparent")
        title_box.pack(fill="x", pady=(0, 10))

        title_row = ctk.CTkFrame(title_box, fg_color="transparent")
        title_row.pack(anchor="w")

        # Brand logo asset from Algo Platform
        logo_path = get_asset_path("algo_symbol.png")
        if logo_path.exists():
            try:
                from PIL import Image
                logo_raw = Image.open(logo_path).convert("RGBA")
                self.logo_ctk = ctk.CTkImage(light_image=logo_raw, dark_image=logo_raw, size=(22, 22))
                lbl_logo = ctk.CTkLabel(title_row, image=self.logo_ctk, text="")
                lbl_logo.pack(side="left", padx=(0, 8))
            except Exception:
                pass

        title = ctk.CTkLabel(
            title_row,
            text="Configuration & Environment Settings",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color="#FFFFFF",
        )
        title.pack(side="left")

        subtitle = ctk.CTkLabel(
            title_box,
            text="Changes update the project .env configuration and take effect upon restart.",
            font=ctk.CTkFont(size=11),
            text_color="#64748B",
        )
        subtitle.pack(anchor="w", pady=(2, 0))

        # -- Card 1: DhanHQ Broker Credentials ----------------------------------
        card1 = self._create_card(self.scroll, "BROKER API & AUTHENTICATION")

        self._create_field(card1, "DHAN_CLIENT_ID", "Dhan Client ID", "e.g. 1105204777")

        # Access token row with show/hide toggle
        lbl_token = ctk.CTkLabel(card1, text="Dhan Access Token (JWT)", font=ctk.CTkFont(size=11), text_color="#A1A1AA")
        lbl_token.pack(anchor="w", padx=14, pady=(6, 2))

        token_row = ctk.CTkFrame(card1, fg_color="transparent")
        token_row.pack(fill="x", padx=14, pady=(0, 6))

        self.token_entry = ctk.CTkEntry(
            token_row,
            show="*",
            height=32,
            placeholder_text="Paste JWT Access Token from Dhan portal",
            fg_color="#080A0F",
            border_color="#27272A",
            text_color="#FFFFFF",
            font=ctk.CTkFont(size=11),
        )
        self.token_entry.pack(side="left", fill="x", expand=True)
        self._entries["DHAN_ACCESS_TOKEN"] = self.token_entry

        self.eye_btn = ctk.CTkButton(
            token_row,
            text="Show",
            command=self._toggle_token_visibility,
            width=56,
            height=32,
            font=ctk.CTkFont(size=11),
            fg_color="#1E2026",
            hover_color="#2E323D",
            text_color="#CBD5E1",
        )
        self.eye_btn.pack(side="left", padx=(8, 0))

        self.force_ipv4_var = ctk.BooleanVar(value=True)
        chk_ipv4 = ctk.CTkCheckBox(
            card1,
            text="Force Outgoing IPv4 (SEBI Whitelist Compliance)",
            variable=self.force_ipv4_var,
            font=ctk.CTkFont(size=11),
            checkbox_width=18,
            checkbox_height=18,
            fg_color="#08B6DE",
            hover_color="#0693B3",
            text_color="#CBD5E1",
        )
        chk_ipv4.pack(anchor="w", padx=14, pady=(6, 2))

        lbl_ipv4_hint = ctk.CTkLabel(
            card1,
            text="Forces API order routing over IPv4 to prevent ISP dynamic IPv6 route switching.",
            font=ctk.CTkFont(size=10),
            text_color="#64748B",
        )
        lbl_ipv4_hint.pack(anchor="w", padx=14, pady=(0, 10))

        # -- Card 2: Network & Zero-Port Setup ----------------------------------
        card2 = self._create_card(self.scroll, "NETWORK ACCESS & SEBI IP GUARD")

        lbl_port = ctk.CTkLabel(card2, text="Web Server Port", font=ctk.CTkFont(size=11), text_color="#A1A1AA")
        lbl_port.pack(anchor="w", padx=14, pady=(6, 2))

        port_row = ctk.CTkFrame(card2, fg_color="transparent")
        port_row.pack(fill="x", padx=14, pady=(0, 4))

        self.port_entry = ctk.CTkEntry(
            port_row,
            height=32,
            width=100,
            placeholder_text="80",
            fg_color="#080A0F",
            border_color="#27272A",
            text_color="#FFFFFF",
            font=ctk.CTkFont(size=11),
        )
        self.port_entry.pack(side="left")
        self._entries["PLATFORM_PORT"] = self.port_entry

        btn_p80 = ctk.CTkButton(
            port_row,
            text="Port 80 (Zero-Port)",
            command=lambda: self._set_port("80"),
            width=125,
            height=32,
            font=ctk.CTkFont(size=10),
            fg_color="#1E2026",
            hover_color="#2E323D",
            text_color="#38BDF8",
        )
        btn_p80.pack(side="left", padx=(8, 0))

        btn_p8000 = ctk.CTkButton(
            port_row,
            text="Port 8000 (Standard)",
            command=lambda: self._set_port("8000"),
            width=130,
            height=32,
            font=ctk.CTkFont(size=10),
            fg_color="#1E2026",
            hover_color="#2E323D",
            text_color="#CBD5E1",
        )
        btn_p8000.pack(side="left", padx=(6, 0))

        lbl_port_desc = ctk.CTkLabel(
            card2,
            text="Port 80 enables clean access (http://<IP>) without typing :8000 in your browser.",
            font=ctk.CTkFont(size=10),
            text_color="#64748B",
        )
        lbl_port_desc.pack(anchor="w", padx=14, pady=(0, 8))

        lbl_static_ip = ctk.CTkLabel(card2, text="Registered SEBI Static IP (Dhan Portal)", font=ctk.CTkFont(size=11), text_color="#A1A1AA")
        lbl_static_ip.pack(anchor="w", padx=14, pady=(4, 2))

        ip_row = ctk.CTkFrame(card2, fg_color="transparent")
        ip_row.pack(fill="x", padx=14, pady=(0, 6))

        self.static_ip_entry = ctk.CTkEntry(
            ip_row,
            height=32,
            placeholder_text="Enter registered public IPv4 address",
            fg_color="#080A0F",
            border_color="#27272A",
            text_color="#FFFFFF",
            font=ctk.CTkFont(size=11),
        )
        self.static_ip_entry.pack(side="left", fill="x", expand=True)
        self._entries["DHAN_STATIC_IP"] = self.static_ip_entry

        use_ip_btn = ctk.CTkButton(
            ip_row,
            text="Sync Public IP",
            command=self._copy_detected_ip,
            width=105,
            height=32,
            font=ctk.CTkFont(size=10),
            fg_color="#1E2026",
            hover_color="#2E323D",
            text_color="#10B981",
        )
        use_ip_btn.pack(side="left", padx=(8, 0))

        # Live IP telemetry card
        telemetry = ctk.CTkFrame(card2, fg_color="#0A0B0E", border_color="#1E2026", border_width=1, corner_radius=4)
        telemetry.pack(fill="x", padx=14, pady=(2, 10))

        pub_ip = self.ip_status.public_ipv4 or "Not detected"
        status_label = self.ip_status.status_label
        badge_color = "#10B981" if status_label == "WHITELISTED" else ("#EF4444" if status_label == "IP MISMATCH" else "#F59E0B")

        telem_row1 = ctk.CTkFrame(telemetry, fg_color="transparent")
        telem_row1.pack(fill="x", padx=10, pady=(6, 2))

        lbl_pub = ctk.CTkLabel(telem_row1, text=f"Public IPv4: {pub_ip}", font=ctk.CTkFont(size=10), text_color="#E2E8F0")
        lbl_pub.pack(side="left")

        lbl_badge = ctk.CTkLabel(
            telem_row1,
            text=f"  {status_label}  ",
            font=ctk.CTkFont(size=9, weight="bold"),
            text_color=badge_color,
            fg_color="#1E2026",
            corner_radius=3,
        )
        lbl_badge.pack(side="right")

        telem_row2 = ctk.CTkFrame(telemetry, fg_color="transparent")
        telem_row2.pack(fill="x", padx=10, pady=(0, 6))

        port_val = self.port_entry.get().strip() or "80"
        port_suffix = f":{port_val}" if port_val != "80" else ""
        lbl_lan = ctk.CTkLabel(
            telem_row2,
            text=f"LAN Access: http://{self.ip_status.lan_ip}{port_suffix}  (or http://{self.ip_status.hostname})",
            font=ctk.CTkFont(size=10),
            text_color="#64748B",
        )
        lbl_lan.pack(side="left")

        # -- Card 3: Database & Redis Connections ------------------------------
        card3 = self._create_card(self.scroll, "DATABASE & MESSAGE BROKER")
        self._create_field(card3, "DATABASE_URL", "PostgreSQL Async URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/trading_platform")
        self._create_field(card3, "REDIS_URL", "Redis Broker URL", "redis://localhost:6379/0")

        # -- Card 4: Trading Safety ---------------------------------------------
        card4 = self._create_card(self.scroll, "TRADING SAFETY & EXECUTION MODE")

        self.live_trading_var = ctk.BooleanVar(value=False)
        self.live_switch = ctk.CTkSwitch(
            card4,
            text="Enable Live Trading (Direct Market Execution)",
            command=self._on_live_toggle,
            variable=self.live_trading_var,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#27272A",
            progress_color="#EF4444",
            text_color="#FFFFFF",
        )
        self.live_switch.pack(anchor="w", padx=14, pady=(10, 4))

        # Dynamic safety warning banner
        self.banner_frame = ctk.CTkFrame(card4, fg_color="#0F172A", border_color="#1E293B", border_width=1, corner_radius=4)
        self.banner_frame.pack(fill="x", padx=14, pady=(4, 8))

        self.banner_label = ctk.CTkLabel(
            self.banner_frame,
            text="SAFETY MODE: Paper Trading Active (Orders execute in simulation with zero financial risk).",
            font=ctk.CTkFont(size=10),
            text_color="#38BDF8",
        )
        self.banner_label.pack(anchor="w", padx=10, pady=6)

        self._create_field(card4, "ORDER_FILL_TIMEOUT_SEC", "Order Fill Timeout (Seconds)", "30")

    def _create_card(self, parent, title: str) -> ctk.CTkFrame:
        """Create styled container frame with section title."""
        card = ctk.CTkFrame(parent, fg_color="#101114", border_color="#1E2026", border_width=1, corner_radius=6)
        card.pack(fill="x", pady=6)

        hdr_row = ctk.CTkFrame(card, fg_color="transparent")
        hdr_row.pack(fill="x", padx=14, pady=(10, 4))

        # Subtle cyan indicator dot
        dot = ctk.CTkLabel(hdr_row, text="•", font=ctk.CTkFont(size=14, weight="bold"), text_color="#08B6DE")
        dot.pack(side="left", padx=(0, 4))

        hdr = ctk.CTkLabel(hdr_row, text=title, font=ctk.CTkFont(size=11, weight="bold"), text_color="#E2E8F0")
        hdr.pack(side="left")
        return card

    def _create_field(self, parent, key: str, label: str, placeholder: str):
        lbl = ctk.CTkLabel(parent, text=label, font=ctk.CTkFont(size=11), text_color="#A1A1AA")
        lbl.pack(anchor="w", padx=14, pady=(6, 2))

        entry = ctk.CTkEntry(
            parent,
            height=32,
            placeholder_text=placeholder,
            fg_color="#080A0F",
            border_color="#27272A",
            text_color="#FFFFFF",
            font=ctk.CTkFont(size=11),
        )
        entry.pack(fill="x", padx=14, pady=(0, 6))
        self._entries[key] = entry

    def _set_port(self, port_str: str):
        self.port_entry.delete(0, "end")
        self.port_entry.insert(0, port_str)

    def _on_live_toggle(self):
        """Update visual warning banner when live trading switch changes."""
        is_live = self.live_trading_var.get()
        if is_live:
            self.banner_frame.configure(fg_color="#2A1215", border_color="#7F1D1D")
            self.banner_label.configure(
                text="CAUTION: Live Trading is ENABLED - Real market orders will execute via DhanHQ API.",
                text_color="#F87171",
            )
        else:
            self.banner_frame.configure(fg_color="#0F172A", border_color="#1E293B")
            self.banner_label.configure(
                text="SAFETY MODE: Paper Trading Active (Orders execute in simulation with zero financial risk).",
                text_color="#38BDF8",
            )

    def _bind_scroll_tree(self, widget):
        """Recursively attach mousewheel and touchpad scroll handlers to all child widgets."""
        widget.bind("<MouseWheel>", self._on_mouse_wheel, add=True)
        widget.bind("<Button-4>", self._on_mouse_wheel, add=True)
        widget.bind("<Button-5>", self._on_mouse_wheel, add=True)

        if hasattr(widget, "winfo_children"):
            for child in widget.winfo_children():
                self._bind_scroll_tree(child)

    def _on_mouse_wheel(self, event):
        """Smooth normalized scrolling handler for mouse wheel and touchpad."""
        if not hasattr(self, "scroll") or not hasattr(self.scroll, "_parent_canvas"):
            return

        if sys.platform == "darwin":
            # macOS trackpad fine gestures emit small delta (1, -1); physical mice emit larger
            if abs(event.delta) < 6:
                delta = -int(event.delta * 4)
            else:
                delta = -int(event.delta / 4)
        elif sys.platform.startswith("win"):
            delta = -int(event.delta / 30)
        else:
            delta = -3 if getattr(event, "num", None) == 4 else 3

        if delta != 0:
            self.scroll._parent_canvas.yview("scroll", delta, "units")
        return "break"

    def _bind_keyboard_shortcuts(self):
        """Bind Escape to close and Return to save."""
        self.bind("<Escape>", lambda e: self.destroy())

    def _toggle_token_visibility(self):
        self._token_visible = not self._token_visible
        if self._token_visible:
            self.token_entry.configure(show="")
            self.eye_btn.configure(text="Hide")
        else:
            self.token_entry.configure(show="*")
            self.eye_btn.configure(text="Show")

    def _copy_detected_ip(self):
        if self.ip_status.public_ipv4 and "." in self.ip_status.public_ipv4:
            self.static_ip_entry.delete(0, "end")
            self.static_ip_entry.insert(0, self.ip_status.public_ipv4)
            self.lbl_feedback.configure(text="Public IP copied to input.", text_color="#38BDF8")

    def _load_values(self):
        """Populate inputs with existing values from .env."""
        env = load_env_dict()

        for key, entry in self._entries.items():
            val = env.get(key, "")
            entry.delete(0, "end")
            entry.insert(0, val)

        # Fallback port from PORT if PLATFORM_PORT is empty
        if not self.port_entry.get().strip():
            self.port_entry.insert(0, env.get("PORT", "80"))

        # Fallback static IP from DHAN_PRIMARY_IP
        if not self.static_ip_entry.get().strip():
            self.static_ip_entry.insert(0, env.get("DHAN_PRIMARY_IP", ""))

        # Fallback timeout
        timeout_entry = self._entries.get("ORDER_FILL_TIMEOUT_SEC")
        if timeout_entry and not timeout_entry.get().strip():
            timeout_entry.insert(0, "30")

        # Boolean toggles
        self.force_ipv4_var.set(env.get("DHAN_FORCE_IPV4", "true").lower() in ("true", "1", "yes"))
        is_live = env.get("LIVE_TRADING_ENABLED", "false").lower() in ("true", "1", "yes")
        self.live_trading_var.set(is_live)
        self._on_live_toggle()

    def _save_settings(self):
        """Persist all modified settings to .env and trigger reload."""
        timeout_entry = self._entries.get("ORDER_FILL_TIMEOUT_SEC")
        if timeout_entry and (not timeout_entry.get().strip() or not timeout_entry.get().strip().isdigit()):
            timeout_entry.delete(0, "end")
            timeout_entry.insert(0, "30")

        for key, entry in self._entries.items():
            val = entry.get().strip()
            update_env_variable(key, val)

        update_env_variable("DHAN_FORCE_IPV4", "true" if self.force_ipv4_var.get() else "false")
        update_env_variable("LIVE_TRADING_ENABLED", "true" if self.live_trading_var.get() else "false")

        # Mirror DHAN_STATIC_IP to DHAN_PRIMARY_IP and registered IP
        static_ip = self.static_ip_entry.get().strip()
        if static_ip:
            update_env_variable("DHAN_PRIMARY_IP", static_ip)
            update_env_variable("DHAN_REGISTERED_IP", static_ip)

        port_val = self.port_entry.get().strip()
        if port_val:
            update_env_variable("PORT", port_val)

        self.lbl_feedback.configure(text="Settings saved to .env", text_color="#10B981")

        if self.on_save_callback:
            self.on_save_callback()

        self.after(400, self.destroy)
