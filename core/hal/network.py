"""
SAM Rover - Network Inspector & Wi-Fi Management
Detects onboard wlan0 and external USB wlan1 adapters.
Interfaces with NetworkManager (nmcli) on Linux / Ubuntu.
"""

import subprocess
import shutil
import socket
import platform
from typing import Dict, Any, List


class NetworkManager:
    """
    Inspects networking interfaces (internal wlan0 vs external wlan1)
    and manages Wi-Fi scanning & connections.
    """

    def __init__(self):
        self.is_linux = platform.system() == "Linux"
        self.has_nmcli = shutil.which("nmcli") is not None

    def get_interfaces(self) -> List[Dict[str, Any]]:
        """
        Enumerates wireless and ethernet interfaces.
        Identifies wlan1 / external dongles.
        """
        interfaces = []
        if not self.is_linux or not self.has_nmcli:
            # Simulated environment / Windows dev
            return [
                {
                    "name": "wlan0",
                    "label": "Internal Wi-Fi (wlan0)",
                    "type": "wifi",
                    "state": "connected",
                    "connection": "Lab-WiFi-5G",
                    "ip": self.get_primary_ip(),
                    "is_external": False,
                },
                {
                    "name": "wlan1",
                    "label": "External Wi-Fi Adapter (wlan1)",
                    "type": "wifi",
                    "state": "available / hotspot",
                    "connection": "SAM-Hotspot",
                    "ip": "192.168.4.1",
                    "is_external": True,
                },
            ]

        try:
            # Query nmcli device status
            res = subprocess.run(
                ["nmcli", "-t", "-f", "DEVICE,TYPE,STATE,CONNECTION", "dev"],
                capture_output=True,
                text=True,
                timeout=3,
            )
            for line in res.stdout.strip().split("\n"):
                if not line or ":" not in line:
                    continue
                parts = line.split(":")
                if len(parts) >= 4:
                    dev, dev_type, state, conn = parts[0], parts[1], parts[2], parts[3]
                    is_ext = dev not in ("wlan0", "eth0", "lo")
                    label = f"External Wi-Fi ({dev})" if is_ext and dev_type == "wifi" else dev
                    interfaces.append({
                        "name": dev,
                        "label": label,
                        "type": dev_type,
                        "state": state,
                        "connection": conn if conn != "--" else "Disconnected",
                        "ip": self.get_interface_ip(dev),
                        "is_external": is_ext,
                    })
        except Exception as e:
            print(f"[Network] Failed to query nmcli: {e}")

        return interfaces

    def get_interface_ip(self, ifname: str) -> str:
        """Retrieves IP address of a specific interface."""
        if not self.is_linux:
            return self.get_primary_ip()
        try:
            res = subprocess.run(
                ["ip", "-4", "addr", "show", ifname],
                capture_output=True,
                text=True,
                timeout=2,
            )
            for line in res.stdout.split("\n"):
                line = line.strip()
                if line.startswith("inet "):
                    return line.split()[1].split("/")[0]
        except Exception:
            pass
        return "N/A"

    def get_primary_ip(self) -> str:
        """Gets primary local IP address."""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"

    def scan_wifi(self) -> List[Dict[str, Any]]:
        """
        Scans available Wi-Fi SSIDs.
        """
        if not self.is_linux or not self.has_nmcli:
            # Mock Wi-Fi list
            return [
                {"ssid": "Campus-Robotics-Lab", "signal": 92, "security": "WPA2"},
                {"ssid": "Student-Dorm-WiFi", "signal": 74, "security": "WPA2"},
                {"ssid": "Open-Lab-Guest", "signal": 60, "security": "Open"},
            ]

        try:
            subprocess.run(["nmcli", "dev", "wifi", "rescan"], capture_output=True, timeout=5)
            res = subprocess.run(
                ["nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY", "dev", "wifi", "list"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            networks = []
            seen = set()
            for line in res.stdout.strip().split("\n"):
                if not line or ":" not in line:
                    continue
                parts = line.split(":")
                ssid = parts[0]
                if ssid and ssid not in seen and ssid != "--":
                    seen.add(ssid)
                    signal = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
                    sec = parts[2] if len(parts) > 2 else "Open"
                    networks.append({"ssid": ssid, "signal": signal, "security": sec})
            return networks
        except Exception as e:
            print(f"[Network] Scan failed: {e}")
            return []

    def get_active_wifi_connection(self) -> Optional[str]:
        """Returns the name of the currently active Wi-Fi connection profile."""
        if not self.is_linux or not self.has_nmcli:
            return "Lab-WiFi-5G"
        try:
            res = subprocess.run(
                ["nmcli", "-t", "-f", "NAME,TYPE", "connection", "show", "--active"],
                capture_output=True,
                text=True,
                timeout=3,
            )
            for line in res.stdout.strip().split("\n"):
                if ":" in line:
                    name, ctype = line.split(":", 1)
                    if ctype in ("802-11-wireless", "wifi") and not name.startswith("SAM-Rover-Setup"):
                        return name
        except Exception:
            pass
        return None

    def connect_wifi(self, ssid: str, password: str = "") -> Dict[str, Any]:
        """
        Transactional Wi-Fi connect with automatic rollback.
        If connecting to the new Wi-Fi fails, it immediately reconnects to the previous
        working connection so the user is never stranded far away on the premises.
        """
        if not self.is_linux or not self.has_nmcli:
            return {"success": True, "message": f"Connected to {ssid} (Simulated)"}

        # 1. Snapshot current active connection before attempting switch
        previous_conn = self.get_active_wifi_connection()

        try:
            cmd = ["nmcli", "dev", "wifi", "connect", ssid]
            if password:
                cmd.extend(["password", password])

            print(f"[Network] Attempting connection to '{ssid}'...")
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=22)

            if res.returncode == 0:
                # Prioritize new connection and keep previous as fallback
                try:
                    subprocess.run(["nmcli", "con", "modify", ssid, "connection.autoconnect-priority", "10"], capture_output=True)
                    if previous_conn and previous_conn != ssid:
                        subprocess.run(["nmcli", "con", "modify", previous_conn, "connection.autoconnect-priority", "5"], capture_output=True)
                except Exception:
                    pass
                return {"success": True, "message": f"Connected to '{ssid}' successfully."}
            else:
                err_msg = res.stderr.strip() or res.stdout.strip()
                print(f"[Network] Failed to connect to '{ssid}': {err_msg}")

                # 2. TRANSACTIONAL ROLLBACK: Reconnect to previous working Wi-Fi
                if previous_conn:
                    print(f"[Network] Rolling back to previous connection '{previous_conn}'...")
                    rollback = subprocess.run(
                        ["nmcli", "con", "up", previous_conn],
                        capture_output=True,
                        text=True,
                        timeout=15,
                    )
                    if rollback.returncode == 0:
                        return {
                            "success": False,
                            "rolled_back": True,
                            "fallback_connection": previous_conn,
                            "message": f"Connection to '{ssid}' failed ({err_msg}). Safely re-connected to '{previous_conn}'.",
                        }

                return {
                    "success": False,
                    "rolled_back": False,
                    "message": f"Connection to '{ssid}' failed: {err_msg}",
                }
        except Exception as e:
            # Reconnect to previous on exception
            if previous_conn:
                try:
                    subprocess.run(["nmcli", "con", "up", previous_conn], capture_output=True, timeout=10)
                except Exception:
                    pass
            return {"success": False, "message": str(e)}
