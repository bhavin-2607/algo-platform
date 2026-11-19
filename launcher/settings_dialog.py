"""Modal Settings Dialog for inspecting and editing .env configurations."""

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
        self.geometry("640x700")
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
        self.grab_set()

        self._entries: Dict[str, ctk.CTkEntry] = {}
        self._token_visible = False

        self._build_ui()
        self._load_values()

    def _build_ui(self):
        # 1. FIXED BOTTOM ACTION BAR
        footer = ctk.CTkFrame(self, fg_color="#101114", border_color="#1E2026", border_width=1, corner_radius=0, height=60)
        footer.pack(side="bottom", fill="x")
        footer.pack_propagate(False)

        btn_row = ctk.CTkFrame(footer, fg_color="transparent")
        btn_row.pack(fill="x", padx=16, pady=12)

        cancel_btn = ctk.CTkButton(
            btn_row,
            text="Cancel",
            command=self.destroy,
            width=90,
            height=34,
            fg_color="#1E2026",
            hover_color="#2E323D",
            border_color="#27272A",
            border_width=1,
            text_color="#A1A1AA",
            font=ctk.CTkFont(size=12),
        )
        cancel_btn.pack(side="left")

        save_btn = ctk.CTkButton(
            btn_row,
            text="Save Changes",
            command=self._save_settings,
            width=130,
            height=34,
            fg_color="#08B6DE",
            hover_color="#0693B3",
            text_color="#FFFFFF",
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        save_btn.pack(side="right")

        # 2. SCROLLABLE SETTINGS CONTAINER
        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=16, pady=(12, 0))

        title = ctk.CTkLabel(
            scroll,
            text="Configuration & Environment Settings",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color="#FFFFFF",
        )
        title.pack(anchor="w", pady=(0, 10))

        # -- Card 1: DhanHQ Broker Credentials ----------------------------------
        card1 = self._create_card(scroll, "DHANHQ BROKER CREDENTIALS")

        self._create_field(card1, "DHAN_CLIENT_ID", "Dhan Client ID", "e.g. 1105204777")

        # Access token row with show/hide toggle
        lbl_token = ctk.CTkLabel(card1, text="Dhan Access Token (JWT)", font=ctk.CTkFont(size=11), text_color="#A1A1AA")
        lbl_token.pack(anchor="w", padx=12, pady=(6, 2))

        token_row = ctk.CTkFrame(card1, fg_color="transparent")
        token_row.pack(fill="x", padx=12, pady=(0, 6))

        self.token_entry = ctk.CTkEntry(
            token_row,
            show="*",
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
            width=50,
            height=28,
            font=ctk.CTkFont(size=10),
            fg_color="#1E2026",
            hover_color="#2E323D",
            text_color="#CBD5E1",
        )
        self.eye_btn.pack(side="left", padx=(6, 0))

        self.force_ipv4_var = ctk.BooleanVar(value=True)
        chk_ipv4 = ctk.CTkCheckBox(
            card1,
            text="Force Outgoing IPv4 (Recommended for SEBI Static IP Compliance)",
            variable=self.force_ipv4_var,
            font=ctk.CTkFont(size=11),
            fg_color="#08B6DE",
            hover_color="#0693B3",
            text_color="#CBD5E1",
        )
        chk_ipv4.pack(anchor="w", padx=12, pady=(4, 10))

        # -- Card 2: Network & Zero-Port Setup ----------------------------------
        card2 = self._create_card(scroll, "NETWORK, SEBI STATIC IP & WEB PORT")

        self._create_field(card2, "PLATFORM_PORT", "Web Server Port (80 for Zero-Port, or 8000)", "80")

        lbl_static_ip = ctk.CTkLabel(card2, text="Registered SEBI Static IP (Dhan Portal)", font=ctk.CTkFont(size=11), text_color="#A1A1AA")
        lbl_static_ip.pack(anchor="w", padx=12, pady=(6, 2))

        ip_row = ctk.CTkFrame(card2, fg_color="transparent")
        ip_row.pack(fill="x", padx=12, pady=(0, 6))

        self.static_ip_entry = ctk.CTkEntry(
            ip_row,
            fg_color="#080A0F",
            border_color="#27272A",
            text_color="#FFFFFF",
            font=ctk.CTkFont(size=11),
        )
        self.static_ip_entry.pack(side="left", fill="x", expand=True)
        self._entries["DHAN_STATIC_IP"] = self.static_ip_entry

        use_ip_btn = ctk.CTkButton(
            ip_row,
            text="Use Current IP",
            command=self._copy_detected_ip,
            width=100,
            height=28,
            font=ctk.CTkFont(size=10),
            fg_color="#1E2026",
            hover_color="#2E323D",
            text_color="#10B981",
        )
        use_ip_btn.pack(side="left", padx=(6, 0))

        detected_label = ctk.CTkLabel(
            card2,
            text=f"Detected Public IPv4: {self.ip_status.public_ipv4}  |  LAN IP: {self.ip_status.lan_ip}",
            font=ctk.CTkFont(size=10),
            text_color="#64748B",
        )
        detected_label.pack(anchor="w", padx=12, pady=(0, 10))

        # -- Card 3: Database & Redis Connections ------------------------------
        card3 = self._create_card(scroll, "DATABASE & MESSAGE BROKER")
        self._create_field(card3, "DATABASE_URL", "PostgreSQL Async URL", "postgresql+asyncpg://...")
        self._create_field(card3, "REDIS_URL", "Redis URL", "redis://localhost:6379/0")

        # -- Card 4: Trading Safety ---------------------------------------------
        card4 = self._create_card(scroll, "TRADING SAFETY & EXECUTION")

        self.live_trading_var = ctk.BooleanVar(value=False)
        self.live_switch = ctk.CTkSwitch(
            card4,
            text="Enable Live Trading (When OFF, Paper Trading Simulation is used)",
            variable=self.live_trading_var,
            font=ctk.CTkFont(size=11),
            fg_color="#27272A",
            progress_color="#10B981",
            text_color="#FFFFFF",
        )
        self.live_switch.pack(anchor="w", padx=12, pady=(8, 8))

        self._create_field(card4, "ORDER_FILL_TIMEOUT_SEC", "Order Fill Timeout (Seconds)", "30")

    def _create_card(self, parent, title: str) -> ctk.CTkFrame:
        """Create styled container frame with section title."""
        card = ctk.CTkFrame(parent, fg_color="#101114", border_color="#1E2026", border_width=1, corner_radius=6)
        card.pack(fill="x", pady=6)

        hdr = ctk.CTkLabel(card, text=title, font=ctk.CTkFont(size=11, weight="bold"), text_color="#38BDF8")
        hdr.pack(anchor="w", padx=12, pady=(10, 4))
        return card

    def _create_field(self, parent, key: str, label: str, placeholder: str):
        lbl = ctk.CTkLabel(parent, text=label, font=ctk.CTkFont(size=11), text_color="#A1A1AA")
        lbl.pack(anchor="w", padx=12, pady=(6, 2))

        entry = ctk.CTkEntry(
            parent,
            placeholder_text=placeholder,
            fg_color="#080A0F",
            border_color="#27272A",
            text_color="#FFFFFF",
            font=ctk.CTkFont(size=11),
        )
        entry.pack(fill="x", padx=12, pady=(0, 6))
        self._entries[key] = entry

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

    def _load_values(self):
        """Populate inputs with existing values from .env."""
        env = load_env_dict()

        for key, entry in self._entries.items():
            val = env.get(key, "")
            entry.delete(0, "end")
            entry.insert(0, val)

        # Boolean toggles
        self.force_ipv4_var.set(env.get("DHAN_FORCE_IPV4", "true").lower() in ("true", "1", "yes"))
        self.live_trading_var.set(env.get("LIVE_TRADING_ENABLED", "false").lower() in ("true", "1", "yes"))

    def _save_settings(self):
        """Persist all modified settings to .env and trigger reload."""
        for key, entry in self._entries.items():
            val = entry.get().strip()
            update_env_variable(key, val)

        update_env_variable("DHAN_FORCE_IPV4", "true" if self.force_ipv4_var.get() else "false")
        update_env_variable("LIVE_TRADING_ENABLED", "true" if self.live_trading_var.get() else "false")

        # Also mirror DHAN_STATIC_IP to DHAN_PRIMARY_IP
        static_ip = self._entries.get("DHAN_STATIC_IP", ctk.CTkEntry(self)).get().strip()
        if static_ip:
            update_env_variable("DHAN_PRIMARY_IP", static_ip)

        if self.on_save_callback:
            self.on_save_callback()

        self.destroy()
