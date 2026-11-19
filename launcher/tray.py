"""System Tray Controller for background platform execution."""

from __future__ import annotations

import logging
import sys
import threading
from typing import Callable, Optional
from PIL import Image, ImageDraw

try:
    import pystray
    _PYSTRAY_AVAILABLE = True
except Exception:
    pystray = None
    _PYSTRAY_AVAILABLE = False

from launcher.config import get_asset_path

logger = logging.getLogger("SystemTray")


def create_tray_icon_image(color: str = "#10B981") -> Image.Image:
    """Generate system tray icon using brand icon with dynamic status dot."""
    ico_png = get_asset_path("app_icon.png")
    if ico_png.exists():
        try:
            base = Image.open(ico_png).convert("RGBA").resize((64, 64), Image.Resampling.LANCZOS)
            draw = ImageDraw.Draw(base)
            # Add dynamic status badge dot in bottom right corner
            draw.ellipse([44, 44, 62, 62], fill=color, outline="#080A0F", width=2)
            return base
        except Exception:
            pass

    size = (64, 64)
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse([4, 4, 60, 60], fill=color)
    draw.text((26, 18), "A", fill="white")
    return image


class SystemTrayController:
    """Manages the OS system tray icon, minimize-to-notification-icon, and background menu."""

    def __init__(
        self,
        on_show: Optional[Callable[[], None]] = None,
        on_open_browser: Optional[Callable[[], None]] = None,
        on_settings: Optional[Callable[[], None]] = None,
        on_restart: Optional[Callable[[], None]] = None,
        on_exit: Optional[Callable[[], None]] = None,
    ):
        self.on_show = on_show
        self.on_open_browser = on_open_browser
        self.on_settings = on_settings
        self.on_restart = on_restart
        self.on_exit = on_exit

        self._icon: Optional[pystray.Icon] = None
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """Start system tray in a background thread."""
        if not _PYSTRAY_AVAILABLE:
            logger.info("Pystray not available; tray icon disabled.")
            return

        if sys.platform != "win32":
            logger.info("System tray runs via dock on non-Windows.")
            return

        image = create_tray_icon_image(color="#10B981")

        menu = pystray.Menu(
            pystray.MenuItem("Show Terminal & Status", self._handle_show, default=True),
            pystray.MenuItem("Open Platform in Browser", self._handle_open_browser),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Settings & .env Config", self._handle_settings),
            pystray.MenuItem("Restart All Services", self._handle_restart),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Stop & Exit Application", self._handle_exit),
        )

        self._icon = pystray.Icon(
            name="AlgoPlatform",
            icon=image,
            title="Algo Platform — Automated Trading Engine",
            menu=menu,
        )

        self._thread = threading.Thread(target=self._icon.run, daemon=True, name="TrayThread")
        self._thread.start()
        logger.info("System tray initialized.")

    def set_status(self, is_running: bool, is_ip_matched: bool = True):
        """Update tray icon color according to platform state."""
        if not self._icon:
            return

        if is_running and is_ip_matched:
            color = "#10B981"  # Emerald Green
            tooltip = "Algo Platform: Running (IP Whitelisted)"
        elif is_running and not is_ip_matched:
            color = "#F5A623"  # Amber
            tooltip = "Algo Platform: Running (IP Mismatch Warning)"
        else:
            color = "#64748B"  # Slate / Grey
            tooltip = "Algo Platform: Stopped"

        try:
            self._icon.icon = create_tray_icon_image(color=color)
            self._icon.title = tooltip
        except Exception:
            pass

    def notify(self, title: str, message: str):
        """Show balloon notification from tray icon."""
        if self._icon and hasattr(self._icon, "notify"):
            try:
                self._icon.notify(message, title)
            except Exception:
                pass

    def stop(self):
        """Stop tray icon."""
        if self._icon:
            try:
                self._icon.stop()
            except Exception:
                pass

    def _handle_show(self, icon=None, item=None):
        if self.on_show:
            self.on_show()

    def _handle_open_browser(self, icon=None, item=None):
        if self.on_open_browser:
            self.on_open_browser()

    def _handle_settings(self, icon=None, item=None):
        if self.on_settings:
            self.on_settings()

    def _handle_restart(self, icon=None, item=None):
        if self.on_restart:
            self.on_restart()

    def _handle_exit(self, icon=None, item=None):
        if self.on_exit:
            self.on_exit()
