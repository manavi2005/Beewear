"""Tiny network helpers for LAN testing (ADR-023).

The phone/Watch can't reach the laptop at 127.0.0.1 — they need its LAN address. These helpers
discover it so `attune doctor` / `attune serve --lan` can print the exact URL to paste into the
companion app's BackendConfig.
"""

from __future__ import annotations

import socket


def lan_ip() -> str | None:
    """Best-effort LAN IPv4 of this machine (no traffic is actually sent)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Connecting a UDP socket just selects the right source interface; nothing is sent.
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        return ip if not ip.startswith("127.") else None
    except OSError:
        return None
    finally:
        s.close()


def lan_url(port: int) -> str | None:
    ip = lan_ip()
    return f"http://{ip}:{port}" if ip else None
