"""Main CustomTkinter Desktop Application for Algo Platform."""

from __future__ import annotations

import datetime
import logging
import os
import queue
import sys
import threading
import time
import webbrowser
from typing import Optional

try:
    import customtkinter as ctk
    _CTK_AVAILABLE = True
except Exception:
    _CTK_AVAILABLE = False
    ctk = None

from launcher.config import get_asset_path, load_env_dict
from launcher.ip_guard import IPGuardStatus
from launcher.settings_dialog import SettingsDialog
from launcher.supervisor import ProcessSupervisor
from launcher.terminal_widget import TerminalWidget
from launcher.tray import SystemTrayController

# Set Windows Application User Model ID for crisp taskbar pinning
if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("bhavinamesara.algoplatform.launcher.1_0")
    except Exception:
        pass

logger = logging.getLogger("DesktopApp")


class DesktopApp(ctk.CTk if ctk else object):
    """Native CustomTkinter Desktop Application managing the Algo Platform stack."""

    def __init__(self):
        if not _CTK_AVAILABLE:
            raise RuntimeError("CustomTkinter is not available in the current Python environment.")

        super().__init__()

        self.title("Algo Platform - Desktop Launcher & Engine Supervisor")
        self.geometry("980x680")
        self.minsize(860, 560)
        self.configure(fg_color="#050608")

        # Set titlebar and taskbar icons
        self._set_app_icon()

        # Core State
        self.log_queue: queue.Queue = queue.Queue()
        self.ip_status = IPGuardStatus()
        self.supervisor = ProcessSupervisor(self.log_queue, on_status_change=self._update_status_cards)
        self.tray = SystemTrayController(
            on_show=self._restore_window,
            on_open_browser=self._open_in_browser,
            on_settings=self._open_settings,
            on_restart=self.supervisor.restart_all,
            on_exit=self._on_full_exit,
        )

        # Build UI layout
        self._build_header()
        self._build_status_cards()
        self._build_toolbar()
        self._build_terminal()
        self._build_footer()
        self._bind_global_shortcuts()

        # Intercept window close (X) to minimize to system tray
        self.protocol("WM_DELETE_WINDOW", self._minimize_to_tray)

        # Start background services, queue polling, and clock tick
        self.after(100, self._initial_startup)
        self.after(50, self._poll_log_queue)
        self.after(1000, self._update_clock)

    def _set_app_icon(self):
        """Configure Windows icon using resolved asset path."""
        ico_path = get_asset_path("app_icon.ico")
        png_path = get_asset_path("app_icon.png")

        if sys.platform == "win32" and ico_path.exists():
            try:
                self.iconbitmap(default=str(ico_path))
            except Exception:
                pass
        elif png_path.exists():
            try:
                from PIL import ImageTk
                self._icon_photo = ImageTk.PhotoImage(file=str(png_path))
                self.wm_iconphoto(True, self._icon_photo)
            except Exception:
                pass

    def _build_header(self):
        """Top brand bar and quick exit action."""
        hdr = ctk.CTkFrame(self, fg_color="#0A0B0E", height=44, corner_radius=0)
        hdr.pack(fill="x", side="top")
        hdr.pack_propagate(False)

        # Left brand title and logo
        brand_box = ctk.CTkFrame(hdr, fg_color="transparent")
        brand_box.pack(side="left", padx=14)

        # Brand logo asset from Algo Platform
        logo_path = get_asset_path("algo_symbol.png")
        if logo_path.exists():
            try:
                from PIL import Image
                logo_raw = Image.open(logo_path).convert("RGBA")
                self.logo_ctk = ctk.CTkImage(light_image=logo_raw, dark_image=logo_raw, size=(22, 22))
                lbl_logo = ctk.CTkLabel(brand_box, image=self.logo_ctk, text="")
                lbl_logo.pack(side="left", padx=(0, 8))
            except Exception:
                pass

        title = ctk.CTkLabel(
            brand_box,
            text="ALGO PLATFORM",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#FFFFFF",
        )
        title.pack(side="left")

        sep = ctk.CTkLabel(
            brand_box,
            text="|",
            font=ctk.CTkFont(size=12),
            text_color="#2E323D",
        )
        sep.pack(side="left", padx=8)

        subtitle = ctk.CTkLabel(
            brand_box,
            text="ENGINE SUPERVISOR",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#64748B",
        )
        subtitle.pack(side="left")

        # Global status pill badge
        self.header_pill = ctk.CTkFrame(hdr, fg_color="#181A20", corner_radius=12, height=24)
        self.header_pill.pack(side="left", padx=10)

        self.lbl_header_dot = ctk.CTkLabel(self.header_pill, text="•", font=ctk.CTkFont(size=14, weight="bold"), text_color="#F59E0B")
        self.lbl_header_dot.pack(side="left", padx=(8, 2))

        self.lbl_header_status = ctk.CTkLabel(self.header_pill, text="STARTING...", font=ctk.CTkFont(size=10, weight="bold"), text_color="#E2E8F0")
        self.lbl_header_status.pack(side="left", padx=(0, 8))

        # Right-side button to close directly or minimize
        exit_btn = ctk.CTkButton(
            hdr,
            text="Exit App",
            command=self._on_full_exit,
            width=70,
            height=26,
            font=ctk.CTkFont(size=11),
            fg_color="#181A20",
            hover_color="#DC2626",
            text_color="#A1A1AA",
        )
        exit_btn.pack(side="right", padx=(4, 12), pady=9)

        min_btn = ctk.CTkButton(
            hdr,
            text="Minimize to Tray",
            command=self._minimize_to_tray,
            width=105,
            height=26,
            font=ctk.CTkFont(size=11),
            fg_color="#181A20",
            hover_color="#2E323D",
            text_color="#A1A1AA",
        )
        min_btn.pack(side="right", padx=4, pady=9)

    def _build_status_cards(self):
        """Build status strip showing Backend API, Celery Worker, Celery Beat, and IP Guard."""
        strip = ctk.CTkFrame(self, fg_color="transparent")
        strip.pack(fill="x", padx=14, pady=(10, 4))
        strip.grid_columnconfigure((0, 1, 2, 3), weight=1)
        strip.grid_rowconfigure(0, weight=1)

        # Card 1: Backend API
        self.card_backend = self._create_status_card(strip, 0, "BACKEND API", "INITIALIZING...", "#94A3B8", "Port: --")

        # Card 2: Celery Worker
        self.card_worker = self._create_status_card(strip, 1, "STRATEGY WORKER", "INITIALIZING...", "#94A3B8", "Solo Engine")

        # Card 3: Celery Beat
        self.card_beat = self._create_status_card(strip, 2, "BEAT SCHEDULER", "INITIALIZING...", "#94A3B8", "Watchdogs & Tokens")

        # Card 4: SEBI IP Guard
        self.card_ip = self._create_status_card(strip, 3, "SEBI IP GUARD", "CHECKING...", "#94A3B8", "Resolving IP...")

    def _create_status_card(self, parent, col: int, title: str, status: str, color: str, subtext: str) -> dict:
        frame = ctk.CTkFrame(parent, fg_color="#0E1015", border_color="#1E2026", border_width=1, corner_radius=6)
        frame.grid(row=0, column=col, padx=4, sticky="nsew")

        top_row = ctk.CTkFrame(frame, fg_color="transparent")
        top_row.pack(fill="x", padx=10, pady=(8, 2))

        dot = ctk.CTkLabel(top_row, text="•", font=ctk.CTkFont(size=12, weight="bold"), text_color=color)
        dot.pack(side="left", padx=(0, 4))

        lbl_title = ctk.CTkLabel(top_row, text=title, font=ctk.CTkFont(size=10, weight="bold"), text_color="#94A3B8")
        lbl_title.pack(side="left")

        lbl_status = ctk.CTkLabel(frame, text=status, font=ctk.CTkFont(size=12, weight="bold"), text_color=color)
        lbl_status.pack(anchor="w", padx=10, pady=(1, 2))

        lbl_sub = ctk.CTkLabel(frame, text=subtext, font=ctk.CTkFont(size=10), text_color="#64748B")
        lbl_sub.pack(anchor="w", padx=10, pady=(0, 8))

        return {"frame": frame, "dot": dot, "title": lbl_title, "status": lbl_status, "sub": lbl_sub}

    def _build_toolbar(self):
        """Action toolbar with Open Browser, Restart, Settings, and LAN URLs."""
        tb = ctk.CTkFrame(self, fg_color="#0E1015", height=44, corner_radius=6, border_color="#1E2026", border_width=1)
        tb.pack(fill="x", padx=14, pady=6)
        tb.pack_propagate(False)

        # Left actions
        self.btn_browser = ctk.CTkButton(
            tb,
            text="Open Platform",
            command=self._open_in_browser,
            width=115,
            height=30,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#08B6DE",
            hover_color="#0693B3",
            text_color="#FFFFFF",
        )
        self.btn_browser.pack(side="left", padx=8, pady=7)

        self.btn_restart = ctk.CTkButton(
            tb,
            text="Restart Services",
            command=self.supervisor.restart_all,
            width=110,
            height=30,
            font=ctk.CTkFont(size=11),
            fg_color="#181A20",
            hover_color="#2E323D",
            border_color="#27272A",
            border_width=1,
            text_color="#CBD5E1",
        )
        self.btn_restart.pack(side="left", padx=4, pady=7)

        self.btn_settings = ctk.CTkButton(
            tb,
            text="Settings (.env)",
            command=self._open_settings,
            width=105,
            height=30,
            font=ctk.CTkFont(size=11),
            fg_color="#181A20",
            hover_color="#2E323D",
            border_color="#27272A",
            border_width=1,
            text_color="#CBD5E1",
        )
        self.btn_settings.pack(side="left", padx=4, pady=7)

        # Right: URL Badge and Copy Button
        btn_copy_url = ctk.CTkButton(
            tb,
            text="Copy URL",
            command=self._copy_lan_url,
            width=70,
            height=28,
            font=ctk.CTkFont(size=10),
            fg_color="#181A20",
            hover_color="#2E323D",
            border_color="#27272A",
            border_width=1,
            text_color="#A1A1AA",
        )
        btn_copy_url.pack(side="right", padx=(4, 8), pady=7)

        self.url_badge = ctk.CTkFrame(tb, fg_color="#13151B", border_color="#1E2026", border_width=1, corner_radius=4)
        self.url_badge.pack(side="right", padx=4, pady=7)

        self.lbl_lan_url = ctk.CTkLabel(
            self.url_badge,
            text="LAN URL: Resolving...",
            font=ctk.CTkFont(size=11),
            text_color="#38BDF8",
        )
        self.lbl_lan_url.pack(side="left", padx=8, pady=2)

    def _build_terminal(self):
        """Center embedded terminal widget."""
        self.terminal = TerminalWidget(self)
        self.terminal.pack(fill="both", expand=True, padx=14, pady=(2, 6))

    def _build_footer(self):
        """Bottom status bar with quick system metrics and live clock."""
        footer = ctk.CTkFrame(self, fg_color="#0A0B0E", height=26, corner_radius=0)
        footer.pack(fill="x", side="bottom")
        footer.pack_propagate(False)

        self.lbl_footer = ctk.CTkLabel(
            footer,
            text="System initializing | Closing window minimizes to tray",
            font=ctk.CTkFont(size=10),
            text_color="#64748B",
        )
        self.lbl_footer.pack(side="left", padx=14)

        self.lbl_clock = ctk.CTkLabel(
            footer,
            text="",
            font=ctk.CTkFont(size=10),
            text_color="#94A3B8",
        )
        self.lbl_clock.pack(side="right", padx=14)

    def _bind_global_shortcuts(self):
        """Bind global shortcuts for keyboard navigation."""
        # Ctrl-, or Command-, to open Settings
        modifier = "Command" if sys.platform == "darwin" else "Control"
        self.bind(f"<{modifier}-comma>", lambda e: self._open_settings())

    def _update_clock(self):
        """Update live IST clock in footer."""
        now = datetime.datetime.now().strftime("%H:%M:%S")
        self.lbl_clock.configure(text=f"{now} IST")
        self.after(1000, self._update_clock)

    def _initial_startup(self):
        """Execute initial background checks, start supervisor, and initialize tray."""
        self.tray.start()

        # Initial IP check
        threading.Thread(target=self._run_ip_check, daemon=True).start()

        # Start supervisor
        threading.Thread(target=self.supervisor.start_all, daemon=True).start()

    def _run_ip_check(self):
        """Refresh IP guard and update UI cards."""
        self.ip_status.refresh()
        self.log_queue.put(("IP-GUARD", self.ip_status.color, f"Public IPv4: {self.ip_status.public_ipv4} ({self.ip_status.status_label})"))
        if self.ip_status.public_ipv6:
            self.log_queue.put(("IP-GUARD", "#A1A1AA", f"Public IPv6: {self.ip_status.public_ipv6}"))

        self.after(0, self._update_ip_card)

    def _update_ip_card(self):
        """Update SEBI IP guard status card in UI."""
        self.card_ip["dot"].configure(text_color=self.ip_status.color)
        self.card_ip["status"].configure(text=self.ip_status.status_label, text_color=self.ip_status.color)
        self.card_ip["sub"].configure(text=f"IP: {self.ip_status.public_ipv4 or 'Not Detected'}")
        self.tray.set_status(is_running=self.supervisor.is_running, is_ip_matched=self.ip_status.is_matched)

    def _update_status_cards(self):
        """Callback from supervisor on service state transitions."""
        port = self.supervisor.port

        # Update Backend Card
        if self.supervisor.backend_ready:
            port_label = f"(PORT {port})"
            self.card_backend["dot"].configure(text_color="#10B981")
            self.card_backend["status"].configure(text=f"ACTIVE {port_label}", text_color="#10B981")
            self.card_backend["sub"].configure(text=f"http://0.0.0.0:{port}")
        else:
            self.card_backend["dot"].configure(text_color="#EF4444")
            self.card_backend["status"].configure(text="STOPPED", text_color="#EF4444")
            self.card_backend["sub"].configure(text="Service Inactive")

        # Update Worker Card
        if self.supervisor.worker_ready:
            self.card_worker["dot"].configure(text_color="#10B981")
            self.card_worker["status"].configure(text="RUNNING (SOLO)", text_color="#10B981")
            self.card_worker["sub"].configure(text="Celery Algo Engine")
        else:
            self.card_worker["dot"].configure(text_color="#EF4444")
            self.card_worker["status"].configure(text="STOPPED", text_color="#EF4444")
            self.card_worker["sub"].configure(text="Worker Inactive")

        # Update Beat Card
        if self.supervisor.beat_ready:
            self.card_beat["dot"].configure(text_color="#10B981")
            self.card_beat["status"].configure(text="ACTIVE", text_color="#10B981")
            self.card_beat["sub"].configure(text="Periodic Tasks")
        else:
            self.card_beat["dot"].configure(text_color="#EF4444")
            self.card_beat["status"].configure(text="STOPPED", text_color="#EF4444")
            self.card_beat["sub"].configure(text="Scheduler Inactive")

        # Update Overall Header Pill
        all_active = self.supervisor.backend_ready and self.supervisor.worker_ready and self.supervisor.beat_ready
        if all_active:
            self.lbl_header_dot.configure(text_color="#10B981")
            port_label = f"PORT {port}" if port != 80 else "ZERO-PORT 80"
            self.lbl_header_status.configure(text=f"ALL SYSTEMS ACTIVE ({port_label})")
        else:
            self.lbl_header_dot.configure(text_color="#F59E0B")
            self.lbl_header_status.configure(text="STARTING / DEGRADED")

        # Update LAN URL Display
        lan_url = self._get_lan_url()
        self.lbl_lan_url.configure(text=f"LAN URL: {lan_url}")
        self.lbl_footer.configure(text=f"Platform Active on {lan_url} | Closing (X) minimizes to tray")

        self.tray.set_status(is_running=self.supervisor.is_running, is_ip_matched=self.ip_status.is_matched)

    def _get_lan_url(self) -> str:
        """Construct full network URL for local and LAN access."""
        port = self.supervisor.port
        lan_ip = self.ip_status.lan_ip
        if port == 80:
            return f"http://{lan_ip}"
        return f"http://{lan_ip}:{port}"

    def _copy_lan_url(self):
        url = self._get_lan_url()
        self.clipboard_clear()
        self.clipboard_append(url)
        self.log_queue.put(("PLATFORM", "#38BDF8", f"Copied URL to clipboard: {url}"))

    def _open_in_browser(self):
        """Launch web browser pointing to local instance."""
        port = self.supervisor.port
        url = f"http://localhost:{port}" if port != 80 else "http://localhost"
        webbrowser.open(url)

    def _open_settings(self):
        """Open modal settings dialog."""
        SettingsDialog(self, self.ip_status, on_save_callback=self._on_settings_saved)

    def _on_settings_saved(self):
        """Callback after settings dialog saves changes."""
        self.log_queue.put(("PLATFORM", "#10B981", "Settings updated from dialog. Refreshing IP guard and reloading configuration..."))
        threading.Thread(target=self._run_ip_check, daemon=True).start()

    def _poll_log_queue(self):
        """Drain up to 50 log items from queue on each UI tick to maintain 60 FPS."""
        count = 0
        while not self.log_queue.empty() and count < 50:
            try:
                tag, color, text = self.log_queue.get_nowait()
                self.terminal.append_log(tag, color, text)
                count += 1
            except queue.Empty:
                break

        self.after(50, self._poll_log_queue)

    def _minimize_to_tray(self):
        """Hide window to notification icon / system tray."""
        self.withdraw()
        self.tray.notify("Algo Platform", "Application minimized to system notification tray. Services are running actively in the background.")

    def _restore_window(self):
        """Restore and focus window from system tray."""
        self.deiconify()
        self.lift()
        self.focus_force()

    def _on_full_exit(self):
        """Gracefully stop all services and terminate the application."""
        self.tray.stop()
        threading.Thread(target=self.supervisor.stop_all, daemon=True).start()
        time.sleep(0.5)
        self.destroy()
        sys.exit(0)


def main():
    """Application entry point handling both GUI mode and service worker sub-commands."""
    # Check if executed as a background service worker (for PyInstaller single-file mode)
    if len(sys.argv) > 1 and sys.argv[1] == "--service":
        service_name = sys.argv[2] if len(sys.argv) > 2 else ""
        if service_name == "backend":
            import uvicorn
            port = 80
            if "--port" in sys.argv:
                try:
                    port = int(sys.argv[sys.argv.index("--port") + 1])
                except Exception:
                    port = 80
            uvicorn.run("app.main:app", host="0.0.0.0", port=port, log_level="info")
            return
        elif service_name == "worker":
            from app.worker.celery_app import celery_app
            pool_type = "solo" if (sys.platform in ("darwin", "win32")) else "prefork"
            celery_app.worker_main(argv=["worker", "--loglevel=info", "-P", pool_type])
            return
        elif service_name == "beat":
            from app.worker.celery_app import celery_app
            beat = celery_app.Beat(loglevel="info")
            beat.run()
            return

    # Normal GUI Mode
    app = DesktopApp()
    app.mainloop()


if __name__ == "__main__":
    main()
