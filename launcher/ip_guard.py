"""SEBI IP Whitelisting Guard and Network Detector."""

from __future__ import annotations

import json
import logging
import socket
import urllib.request
from typing import Dict, List, Optional, Tuple

from launcher.config import load_env_dict, update_env_variable

logger = logging.getLogger("IPGuard")


def get_local_lan_ip() -> str:
    """Return local IPv4 address of this machine on the local network / Wi-Fi."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(0.5)
            # Connecting to a public IP doesn't actually send packets but selects the active interface
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return "127.0.0.1"


def get_local_hostname() -> str:
    """Return friendly local machine hostname e.g. algo.local."""
    try:
        raw_name = socket.gethostname().split(".")[0].strip()
        return f"{raw_name.lower()}.local"
    except Exception:
        return "algo.local"


def fetch_public_ipv4() -> Optional[str]:
    """Fetch public outgoing IPv4 address with fallback endpoints."""
    resolvers = [
        "https://api.ipify.org?format=json",
        "https://api4.my-ip.io/v2/ip.json",
        "https://ipv4.icanhazip.com",
    ]
    for url in resolvers:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "AlgoPlatform-IPGuard/1.0"})
            with urllib.request.urlopen(req, timeout=3.5) as resp:
                raw = resp.read().decode("utf-8").strip()
                if "{" in raw:
                    data = json.loads(raw)
                    ip = data.get("ip") or data.get("IPv4")
                else:
                    ip = raw
                if ip and "." in ip:
                    return ip.strip()
        except Exception:
            continue
    return None


def fetch_public_ipv6() -> Optional[str]:
    """Fetch public outgoing IPv6 address if network has IPv6 enabled."""
    resolvers = [
        "https://api64.ipify.org?format=json",
        "https://api6.my-ip.io/v2/ip.json",
    ]
    for url in resolvers:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "AlgoPlatform-IPGuard/1.0"})
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                data = json.loads(resp.read().decode("utf-8").strip())
                ip = data.get("ip")
                if ip and ":" in ip:
                    return ip.strip()
        except Exception:
            continue
    return None


class IPGuardStatus:
    """Encapsulates full network and Dhan IP registration telemetry."""

    def __init__(self):
        self.public_ipv4: str = "Checking..."
        self.public_ipv6: Optional[str] = None
        self.lan_ip: str = get_local_lan_ip()
        self.hostname: str = get_local_hostname()
        self.registered_ips: List[str] = []
        self.is_matched: bool = False
        self.status_label: str = "CHECKING..."
        self.color: str = "#94A3B8"  # Slate

    def refresh(self) -> IPGuardStatus:
        """Run network resolution and compare against configured static IPs in .env."""
        env = load_env_dict()
        reg_candidates = [
            env.get("DHAN_STATIC_IP"),
            env.get("DHAN_PRIMARY_IP"),
            env.get("DHAN_SECONDARY_IP"),
            env.get("STATIC_IP"),
        ]
        self.registered_ips = [ip.strip() for ip in reg_candidates if ip and ip.strip()]
        self.lan_ip = get_local_lan_ip()
        self.hostname = get_local_hostname()

        ipv4 = fetch_public_ipv4()
        if ipv4:
            self.public_ipv4 = ipv4
        else:
            self.public_ipv4 = "Unavailable (Offline)"

        self.public_ipv6 = fetch_public_ipv6()

        if self.public_ipv4.startswith("Unavailable"):
            self.is_matched = False
            self.status_label = "OFFLINE"
            self.color = "#EF4444"  # Red
        elif not self.registered_ips:
            self.is_matched = False
            self.status_label = "NOT CONFIGURED"
            self.color = "#F5A623"  # Amber
        elif self.public_ipv4 in self.registered_ips:
            self.is_matched = True
            self.status_label = "WHITELISTED"
            self.color = "#10B981"  # Emerald Green
        else:
            self.is_matched = False
            self.status_label = "IP MISMATCH"
            self.color = "#EF4444"  # Red

        return self

    def sync_to_env(self) -> bool:
        """One-click synchronization of current detected public IPv4 into .env."""
        if not self.public_ipv4 or "." not in self.public_ipv4:
            return False
        update_env_variable("DHAN_STATIC_IP", self.public_ipv4)
        update_env_variable("DHAN_PRIMARY_IP", self.public_ipv4)
        self.refresh()
        return True
