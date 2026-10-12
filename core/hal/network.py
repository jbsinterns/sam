"""
SAM Rover - Network Inspector & Wi-Fi Management
Interfaces with NetworkManager (nmcli) on Linux / Ubuntu.
Provides real-time interface discovery, Wi-Fi scanning, connection, and Hotspot AP control.
Optimized for Raspberry Pi 4 running Ubuntu.
"""

import subprocess
import shutil
import socket
import platform
import time
from typing import Dict, Any, List, Optional


class NetworkManager:
    """
    Inspects networking interfaces (internal wlan0 vs external wlan1)
    and manages real Wi-Fi scanning, connection, and AP Hotspot.
    """

    HOTSPOT_NAME = "SAM-Rover-Setup"
    HOTSPOT_SSID = "SAM-Rover-Setup"
    HOTSPOT_IP = "192.168.4.1/24"
    HOTSPOT_PSK = "raspberry"

    def __init__(self):
        self.is_linux = platform.system() == "Linux"
        self.has_nmcli = shutil.which("nmcli") is not None

    def get_primary_wifi_interface(self) -> str:
        """
        Determines the primary internal Wi-Fi interface (wlan0 on Raspberry Pi, wlo1 on PC).
        Excludes external USB adapters (wlan1, wlx*).
        """
        if not self.has_nmcli:
            return "wlan0"
        try:
            res = subprocess.run(
                ["nmcli", "-t", "-f", "DEVICE,TYPE", "dev"],
                capture_output=True,
                text=True,
                timeout=3,
            )
            candidates = []
            for line in res.stdout.strip().split("\n"):
                if not line or ":" not in line:
                    continue
                parts = line.split(":")
                dev, dev_type = parts[0], parts[1]
                if dev_type == "wifi":
                    if dev == "wlan0":
                        return "wlan0"
                    if not dev.startswith("wlx") and dev != "wlan1":
                        candidates.append(dev)
            if candidates:
                return candidates[0]
        except Exception as e:
            print(f"[Network] Error finding primary wifi interface: {e}")
        return "wlan0"

    def get_interfaces(self) -> List[Dict[str, Any]]:
        """
        Enumerates wireless interfaces using nmcli.
        Distinguishes internal Wi-Fi (wlan0) from external USB Wi-Fi dongles (wlan1, wlx*).
        Excludes non-wireless interfaces (loopback lo, VPN tunnels, etc.).
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
                    # Only show Wi-Fi interfaces (filter out lo, VPN tunnels like ztdhgltdot, ethernet, etc.)
                    if dev_type != "wifi":
                        continue

                    is_ext = dev.startswith("wlx") or (dev.startswith("wlan") and dev != "wlan0")
                    if is_ext:
                        label = f"External USB Wi-Fi ({dev})"
                    elif dev == "wlan0":
                        label = f"Onboard Wi-Fi ({dev})"
                    else:
                        label = f"Internal Wi-Fi ({dev})"

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
            subprocess.run(["nmcli", "dev", "wifi", "rescan"], capture_output=True, timeout=5)
            res = subprocess.run(
                ["nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY,IN-USE", "dev", "wifi", "list"],
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

    def get_active_wifi_connection(self, ifname: Optional[str] = None) -> Optional[str]:
        """
        Returns the name of the currently active Wi-Fi connection profile.
        If ifname is provided, filters specifically for that device.
        """
        if not self.has_nmcli:
            return None
        try:
            res = subprocess.run(
                ["nmcli", "-t", "-f", "NAME,DEVICE,TYPE", "connection", "show", "--active"],
                capture_output=True,
                text=True,
                timeout=3,
            )
            for line in res.stdout.strip().split("\n"):
                if ":" in line:
                    parts = line.split(":")
                    if len(parts) >= 3:
                        name, dev, ctype = parts[0], parts[1], parts[2]
                        if ctype in ("802-11-wireless", "wifi") and not name.startswith(self.HOTSPOT_NAME):
                            if ifname is None or dev == ifname:
                                return name
        except Exception:
            pass
        return None

    def _find_connection_uuids(self, ssid: str, ifname: Optional[str] = None) -> List[str]:
        """Finds all existing NetworkManager connection UUIDs matching SSID for the given interface."""
        matches = []
        try:
            res = subprocess.run(
                ["nmcli", "-t", "-f", "NAME,UUID,TYPE,DEVICE", "con", "show"],
                capture_output=True,
                text=True,
                timeout=3,
            )
            for line in res.stdout.strip().split("\n"):
                parts = line.split(":")
                if len(parts) >= 3 and parts[2] in ("802-11-wireless", "wifi"):
                    con_name, uuid = parts[0], parts[1]
                    dev = parts[3] if len(parts) > 3 else ""
                    if con_name == ssid or con_name.startswith(f"{ssid} "):
                        if ifname is None or not dev or dev == ifname:
                            matches.append(uuid)
        except Exception:
            pass
        return matches

    def _cleanup_duplicate_connections(self, ssid: str, keep_uuid: str, ifname: Optional[str] = None) -> None:
        """Removes redundant numbered connection profiles (e.g. SSID 1, SSID 2) on the same interface."""
        all_uuids = self._find_connection_uuids(ssid, ifname)
        for u in all_uuids:
            if u != keep_uuid:
                try:
                    subprocess.run(["nmcli", "con", "delete", u], capture_output=True, timeout=5)
                except Exception:
                    pass

    def _find_connection_uuid(self, ssid: str, ifname: Optional[str] = None) -> Optional[str]:
        """Finds primary NetworkManager connection UUID matching SSID."""
        uuids = self._find_connection_uuids(ssid, ifname)
        return uuids[0] if uuids else None

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

    def start_hotspot(self, ifname: Optional[str] = None) -> Dict[str, Any]:
        """Activates the rescue AP Hotspot (SAM-Rover-Setup)."""
        if not self.has_nmcli:
            return {"success": False, "message": "nmcli not available"}

        # Default to primary onboard Wi-Fi (wlan0 on Pi, wlo1 on PC)
        ap_iface = ifname or self.get_primary_wifi_interface()

        try:
            # Check if profile exists, create or update interface binding
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
                    "802-11-wireless-security.key-mgmt", "wpa-psk",
                    "802-11-wireless-security.psk", self.HOTSPOT_PSK,
                    "ipv4.method", "shared",
                    "ipv4.addresses", self.HOTSPOT_IP
                ], capture_output=True, timeout=5)
            else:
                subprocess.run(["nmcli", "con", "modify", self.HOTSPOT_NAME, "connection.interface-name", ap_iface], capture_output=True, timeout=5)

            res = subprocess.run(["nmcli", "con", "up", self.HOTSPOT_NAME, "ifname", ap_iface], capture_output=True, text=True, timeout=15)
            if res.returncode == 0:
                return {"success": True, "interface": ap_iface, "message": f"Hotspot '{self.HOTSPOT_SSID}' started on {ap_iface}.", "ip": "192.168.4.1"}
            else:
                err = res.stderr.strip() or res.stdout.strip()
                return {"success": False, "interface": ap_iface, "message": f"Failed to start Hotspot: {err}"}
        except Exception as e:
            return {"success": False, "interface": ap_iface, "message": str(e)}

    def stop_hotspot(self) -> Dict[str, Any]:
        """Deactivates the AP Hotspot."""
        if not self.has_nmcli:
            return {"success": False, "message": "nmcli not available"}

        try:
            res = subprocess.run(["nmcli", "con", "down", self.HOTSPOT_NAME], capture_output=True, text=True, timeout=10)
            if res.returncode == 0:
                return {"success": True, "message": f"Hotspot '{self.HOTSPOT_SSID}' stopped."}
            else:
                err = res.stderr.strip() or res.stdout.strip()
                return {"success": False, "message": f"Failed to stop Hotspot: {err}"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    # Aliases for AP methods
    start_ap = start_hotspot
    stop_ap = stop_hotspot
    get_ap_status = get_hotspot_status

    def _handle_connect_failure(
        self,
        ssid: str,
        target_iface: str,
        err_msg: str,
        previous_conn: Optional[str],
        was_hotspot_active: bool,
    ) -> Dict[str, Any]:
        """
        Handles transactional rollback when Wi-Fi connection fails.
        Tries previous Wi-Fi first; if that fails or previous state was AP,
        activates the Rescue AP Hotspot so the rover is NEVER left stranded.
        """
        if previous_conn and not was_hotspot_active:
            print(f"[Network] Rolling back {target_iface} to previous connection '{previous_conn}'...")
            rollback = subprocess.run(
                ["nmcli", "con", "up", previous_conn, "ifname", target_iface],
                capture_output=True,
                text=True,
                timeout=12,
            )
            if rollback.returncode == 0:
                return {
                    "success": False,
                    "interface": target_iface,
                    "rolled_back": True,
                    "fallback_mode": "wifi",
                    "fallback_connection": previous_conn,
                    "message": f"Connection to '{ssid}' failed ({err_msg}). Re-connected to '{previous_conn}'.",
                }
            print(f"[Network] Rollback to previous Wi-Fi '{previous_conn}' failed. Activating Rescue AP Hotspot...")

        # If previous Wi-Fi reconnection failed OR previous state was AP/unconnected:
        print(f"[Network] Activating Rescue AP Hotspot on {target_iface}...")
        hotspot_res = self.start_hotspot(ifname=target_iface)
        if hotspot_res.get("success"):
            return {
                "success": False,
                "interface": target_iface,
                "rolled_back": True,
                "fallback_mode": "hotspot",
                "fallback_connection": self.HOTSPOT_NAME,
                "message": f"Connection to '{ssid}' failed ({err_msg}). Safely activated Rescue AP Hotspot.",
            }

        return {
            "success": False,
            "interface": target_iface,
            "rolled_back": False,
            "message": f"Connection to '{ssid}' on {target_iface} failed: {err_msg}",
        }


    def connect_wifi(self, ssid: str, password: str = "", ifname: Optional[str] = None) -> Dict[str, Any]:
        """
        Transactional Wi-Fi connect targeting onboard wlan0 (never touching external wlan1 dongles).
        Includes automatic rollback to previous connection or Rescue AP Hotspot on failure.
        Prevents duplicate connection profiles (e.g. SSID 1, SSID 2).
        """
        if not self.has_nmcli:
            return {"success": False, "message": "NetworkManager (nmcli) is not available on this platform."}

        # 1. Target specifically the primary onboard interface (wlan0 on Pi, wlo1 on PC), never wlan1
        target_iface = ifname or self.get_primary_wifi_interface()
        previous_conn = self.get_active_wifi_connection(target_iface)
        was_hotspot_active = self.is_hotspot_active()

        # 2. If AP Hotspot is currently active on target interface, turn it down first
        if was_hotspot_active:
            self.stop_hotspot()
            time.sleep(1)

        try:
            # 3. Check if a profile already exists for this SSID on target interface
            uuids = self._find_connection_uuids(ssid, target_iface)
            if uuids:
                primary_uuid = uuids[0]
                print(f"[Network] Found existing connection profile for '{ssid}' (UUID: {primary_uuid}) on {target_iface}. Activating...")
                # Automatically purge any stale numbered duplicates (e.g. SSID 1, SSID 2) on this interface
                if len(uuids) > 1:
                    self._cleanup_duplicate_connections(ssid, keep_uuid=primary_uuid, ifname=target_iface)
                if password:
                    subprocess.run(["nmcli", "con", "modify", primary_uuid, "802-11-wireless-security.key-mgmt", "wpa-psk", "802-11-wireless-security.psk", password], capture_output=True)
                res = subprocess.run(["nmcli", "con", "up", primary_uuid, "ifname", target_iface], capture_output=True, text=True, timeout=12)
                if res.returncode == 0:
                    return {
                        "success": True,
                        "interface": target_iface,
                        "message": f"Connected to '{ssid}' on {target_iface} successfully.",
                    }
                else:
                    err_msg = res.stderr.strip() or res.stdout.strip()
                    print(f"[Network] Activation of existing profile for '{ssid}' failed on {target_iface}: {err_msg}")
                    # Do not fall through to nmcli dev wifi connect (avoids duplicate profile creation)
                    return self._handle_connect_failure(ssid, target_iface, err_msg, previous_conn, was_hotspot_active)

            # 4. Trigger quick rescan so target_iface populates visible SSIDs
            subprocess.run(["nmcli", "dev", "wifi", "rescan", "ifname", target_iface], capture_output=True, timeout=5)
            time.sleep(1)

            cmd = ["nmcli", "dev", "wifi", "connect", ssid, "ifname", target_iface]
            if password:
                cmd.extend(["password", password])

            print(f"[Network] Connecting to Wi-Fi '{ssid}' on interface '{target_iface}'...")
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=14)

            # 5. Fallback for WPA2/WPA3 key-mgmt missing bug on modern NetworkManager (Ubuntu 24.04/26.04)
            if res.returncode != 0 and ("key-mgmt" in res.stderr or "key-mgmt" in res.stdout):
                print(f"[Network] Applying explicit WPA security profile for '{ssid}' on {target_iface}...")
                uuid = self._find_connection_uuid(ssid, target_iface)
                if uuid:
                    subprocess.run(["nmcli", "con", "modify", uuid, "802-11-wireless-security.key-mgmt", "wpa-psk"], capture_output=True)
                    if password:
                        subprocess.run(["nmcli", "con", "modify", uuid, "802-11-wireless-security.psk", password], capture_output=True)
                    res = subprocess.run(["nmcli", "con", "up", uuid, "ifname", target_iface], capture_output=True, text=True, timeout=15)
                else:
                    subprocess.run(["nmcli", "con", "add", "type", "wifi", "ifname", target_iface, "con-name", ssid, "ssid", ssid], capture_output=True)
                    subprocess.run(["nmcli", "con", "modify", ssid, "802-11-wireless-security.key-mgmt", "wpa-psk"], capture_output=True)
                    if password:
                        subprocess.run(["nmcli", "con", "modify", ssid, "802-11-wireless-security.psk", password], capture_output=True)
                    res = subprocess.run(["nmcli", "con", "up", ssid, "ifname", target_iface], capture_output=True, text=True, timeout=15)

            if res.returncode == 0:
                try:
                    subprocess.run(["nmcli", "con", "modify", ssid, "connection.autoconnect-priority", "10"], capture_output=True)
                except Exception:
                    pass
                # Cleanup any duplicates if created by nmcli dev wifi connect
                created_uuids = self._find_connection_uuids(ssid, target_iface)
                if len(created_uuids) > 1:
                    self._cleanup_duplicate_connections(ssid, keep_uuid=created_uuids[0], ifname=target_iface)
                return {
                    "success": True,
                    "interface": target_iface,
                    "message": f"Connected to '{ssid}' on {target_iface} successfully.",
                }
            else:
                err_msg = res.stderr.strip() or res.stdout.strip()
                print(f"[Network] Failed to connect to '{ssid}' on {target_iface}: {err_msg}")

                # Clean up any newly created failed profile to prevent clutter
                if not uuids:
                    new_uuid = self._find_connection_uuid(ssid, target_iface)
                    if new_uuid:
                        subprocess.run(["nmcli", "con", "delete", new_uuid], capture_output=True, timeout=5)

                # 6. TRANSACTIONAL ROLLBACK
                return self._handle_connect_failure(ssid, target_iface, err_msg, previous_conn, was_hotspot_active)

        except subprocess.TimeoutExpired as te:
            print(f"[Network] Connection operation timed out: {te}")
            return self._handle_connect_failure(
                ssid, target_iface, "Operation timed out", previous_conn, was_hotspot_active
            )
        except Exception as e:
            print(f"[Network] Error during connect_wifi: {e}")
            return self._handle_connect_failure(
                ssid, target_iface, str(e), previous_conn, was_hotspot_active
            )

