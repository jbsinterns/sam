"""
SAM Rover - Network Inspector & Wi-Fi Management
Interfaces with NetworkManager (nmcli) on Linux / Ubuntu.
Provides real-time interface discovery, Wi-Fi scanning, connection, and Hotspot AP control.
"""

import subprocess
import shutil
import socket
import platform
from typing import Dict, Any, List, Optional


class NetworkManager:
    """
    Inspects networking interfaces (internal wlan0 vs external wlan1)
    and manages real Wi-Fi scanning, connection, and AP Hotspot.
    """

    HOTSPOT_NAME = "SAM-Rover-Setup"
    HOTSPOT_SSID = "SAM-Rover-Setup"
    HOTSPOT_IP = "192.168.4.1/24"

    def __init__(self):
        self.is_linux = platform.system() == "Linux"
        self.has_nmcli = shutil.which("nmcli") is not None

    def get_interfaces(self) -> List[Dict[str, Any]]:
        """
        Enumerates wireless and ethernet interfaces using nmcli.
        Filters out loopback and virtual p2p interfaces.
        """
        interfaces = []
        if not self.has_nmcli:
            return []

        try:
            res = subprocess.run(
                ["nmcli", "-t", "-f", "DEVICE,TYPE,STATE,CONNECTION", "dev"],
                capture_output=True,
                text=True,
                timeout=4,
            )
            for line in res.stdout.strip().split("\n"):
                if not line or ":" not in line:
                    continue
                parts = line.split(":")
                if len(parts) >= 4:
                    dev, dev_type, state, conn = parts[0], parts[1], parts[2], parts[3]
                    # Filter out loopback and virtual internal devices
                    if dev in ("lo",) or dev.startswith("p2p-dev"):
                        continue

                    is_ext = dev.startswith("wlan") and dev != "wlan0"
                    if is_ext:
                        label = f"External USB Wi-Fi ({dev})"
                    elif dev == "wlan0":
                        label = f"Onboard Wi-Fi ({dev})"
                    elif dev_type == "ethernet":
                        label = f"Ethernet ({dev})"
                    else:
                        label = f"{dev_type.capitalize()} ({dev})"

                    interfaces.append({
                        "name": dev,
                        "label": label,
                        "type": dev_type,
                        "state": state,
                        "connection": conn if conn and conn != "--" else "Disconnected",
                        "ip": self.get_interface_ip(dev),
                        "is_external": is_ext,
                    })
        except Exception as e:
            print(f"[Network] Failed to query nmcli dev: {e}")

        return interfaces

    def get_interface_ip(self, ifname: str) -> str:
        """Retrieves actual IP address of a specific interface."""
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
        Scans and returns actual available Wi-Fi access points in range.
        """
        if not self.has_nmcli:
            return []

        try:
            subprocess.run(["nmcli", "dev", "wifi", "rescan"], capture_output=True, timeout=8)
            res = subprocess.run(
                ["nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY,IN-USE", "dev", "wifi", "list"],
                capture_output=True,
                text=True,
                timeout=8,
            )
            networks = []
            seen = set()
            for line in res.stdout.strip().split("\n"):
                if not line or ":" not in line:
                    continue
                parts = line.split(":")
                ssid = parts[0]
                # Filter out hidden or empty SSIDs and duplicates
                if ssid and ssid not in seen and ssid != "--":
                    seen.add(ssid)
                    signal = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
                    sec = parts[2] if len(parts) > 2 and parts[2] else "Open"
                    in_use = (len(parts) > 3 and parts[3].strip() == "*")
                    networks.append({
                        "ssid": ssid,
                        "signal": signal,
                        "security": sec,
                        "connected": in_use,
                    })
            return networks
        except Exception as e:
            print(f"[Network] Scan failed: {e}")
            return []

    def get_active_wifi_connection(self) -> Optional[str]:
        """Returns the name of the currently active Wi-Fi connection profile."""
        if not self.has_nmcli:
            return None
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
                    if ctype in ("802-11-wireless", "wifi") and not name.startswith(self.HOTSPOT_NAME):
                        return name
        except Exception:
            pass
        return None

    def connect_wifi(self, ssid: str, password: str = "") -> Dict[str, Any]:
        """
        Connects to a real Wi-Fi network with automatic rollback if failed.
        """
        if not self.has_nmcli:
            return {"success": False, "message": "NetworkManager (nmcli) is not available on this platform."}

        previous_conn = self.get_active_wifi_connection()

        try:
            cmd = ["nmcli", "dev", "wifi", "connect", ssid]
            if password:
                cmd.extend(["password", password])

            print(f"[Network] Connecting to Wi-Fi '{ssid}'...")
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=25)

            if res.returncode == 0:
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
                            "message": f"Connection to '{ssid}' failed ({err_msg}). Re-connected to '{previous_conn}'.",
                        }

                return {
                    "success": False,
                    "rolled_back": False,
                    "message": f"Connection to '{ssid}' failed: {err_msg}",
                }
        except Exception as e:
            if previous_conn:
                try:
                    subprocess.run(["nmcli", "con", "up", previous_conn], capture_output=True, timeout=10)
                except Exception:
                    pass
            return {"success": False, "message": str(e)}

    def is_hotspot_active(self) -> bool:
        """Checks if the SAM AP Hotspot is currently active."""
        if not self.has_nmcli:
            return False
        try:
            res = subprocess.run(
                ["nmcli", "-t", "-f", "NAME,TYPE", "con", "show", "--active"],
                capture_output=True,
                text=True,
                timeout=3,
            )
            return self.HOTSPOT_NAME in res.stdout
        except Exception:
            return False

    def get_hotspot_status(self) -> Dict[str, Any]:
        """Returns current status of the AP Hotspot."""
        active = self.is_hotspot_active()
        return {
            "active": active,
            "name": self.HOTSPOT_NAME,
            "ssid": self.HOTSPOT_SSID,
            "ip": "192.168.4.1" if active else None,
        }

    def start_hotspot(self) -> Dict[str, Any]:
        """Activates the rescue AP Hotspot (SAM-Rover-Setup)."""
        if not self.has_nmcli:
            return {"success": False, "message": "nmcli not available"}

        # Detect interface
        interfaces = self.get_interfaces()
        wifi_devs = [i["name"] for i in interfaces if i["type"] == "wifi"]
        ap_iface = "wlan1" if "wlan1" in wifi_devs else "wlan0"

        try:
            # Check if profile exists, create if not
            check = subprocess.run(["nmcli", "con", "show", self.HOTSPOT_NAME], capture_output=True, text=True)
            if check.returncode != 0:
                subprocess.run([
                    "nmcli", "con", "add", "type", "wifi",
                    "ifname", ap_iface,
                    "con-name", self.HOTSPOT_NAME,
                    "autoconnect", "no",
                    "ssid", self.HOTSPOT_SSID
                ], capture_output=True, timeout=5)
                subprocess.run([
                    "nmcli", "con", "modify", self.HOTSPOT_NAME,
                    "802-11-wireless.mode", "ap",
                    "802-11-wireless.band", "bg",
                    "wifi-sec.key-mgmt", "wpa-psk",
                    "wifi-sec.psk", "raspberry",
                    "ipv4.method", "shared",
                    "ipv4.addresses", self.HOTSPOT_IP
                ], capture_output=True, timeout=5)

            res = subprocess.run(["nmcli", "con", "up", self.HOTSPOT_NAME], capture_output=True, text=True, timeout=12)
            if res.returncode == 0:
                return {"success": True, "message": f"Hotspot '{self.HOTSPOT_SSID}' started on {ap_iface}."}
            else:
                return {"success": False, "message": res.stderr.strip() or res.stdout.strip()}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def stop_hotspot(self) -> Dict[str, Any]:
        """Deactivates the AP Hotspot."""
        if not self.has_nmcli:
            return {"success": False, "message": "nmcli not available"}

        try:
            res = subprocess.run(["nmcli", "con", "down", self.HOTSPOT_NAME], capture_output=True, text=True, timeout=8)
            if res.returncode == 0:
                return {"success": True, "message": f"Hotspot '{self.HOTSPOT_SSID}' stopped."}
            else:
                return {"success": False, "message": res.stderr.strip() or res.stdout.strip()}
        except Exception as e:
            return {"success": False, "message": str(e)}
