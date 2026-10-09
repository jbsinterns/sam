#!/bin/bash
# ==============================================================================
# SAM Rover - Smart Premise-Aware Wi-Fi Failover Script
# Uses NetworkManager (nmcli) standard on Ubuntu 24.04/26.04
#
# Logic:
# 1. Prioritizes known premise Wi-Fi networks (never falls back to AP unnecessarily).
# 2. If disconnected, automatically scans and retries reconnecting to any saved known network.
# 3. Only starts AP Hotspot after multiple consecutive failures (3+ minutes without known Wi-Fi).
# 4. If AP Hotspot is active and a known premise Wi-Fi reappears, auto-shuts down Hotspot
#    and re-connects to premise Wi-Fi.
# ==============================================================================

HOTSPOT_NAME="SAM-Rover-Setup"
HOTSPOT_SSID="SAM-Rover-Setup"
HOTSPOT_IP="192.168.4.1/24"
FAIL_COUNTER_FILE="/tmp/sam_wifi_fail_count"
MAX_DISCONNECT_RETRIES=3  # 3 checks (~3 minutes) before falling back to AP

# Check if an external Wi-Fi dongle (wlan1) is present
if nmcli dev | grep -q "wlan1"; then
    # Dedicated interface mode: wlan1 is permanent Hotspot, wlan0 stays on premise Wi-Fi
    AP_INTERFACE="wlan1"
    STA_INTERFACE="wlan0"
else
    AP_INTERFACE="wlan0"
    STA_INTERFACE="wlan0"
fi

# Function to get connection state
get_connection_state() {
    nmcli -t -f DEVICE,STATE dev | grep "^${STA_INTERFACE}:" | cut -d: -f2
}

# Function to check if Hotspot is currently active
is_hotspot_active() {
    nmcli -t -f NAME,TYPE con show --active | grep -q "^${HOTSPOT_NAME}:"
}

# Function to scan and attempt reconnecting to any known premise Wi-Fi
try_reconnect_known_networks() {
    echo "[SAM Network] Scanning for known premise Wi-Fi networks..."
    nmcli dev wifi rescan >/dev/null 2>&1 || true
    
    # List visible SSIDs
    VISIBLE_SSIDS=$(nmcli -t -f SSID dev wifi list | grep -v '^--$' | sort -u)
    
    # Check against saved connection profiles
    SAVED_PROFILES=$(nmcli -t -f NAME,TYPE con show | grep '802-11-wireless' | cut -d: -f1 | grep -v "${HOTSPOT_NAME}")
    
    for PROFILE in $SAVED_PROFILES; do
        if echo "$VISIBLE_SSIDS" | grep -qx "$PROFILE"; then
            echo "[SAM Network] Found visible known premise network: '$PROFILE'. Connecting..."
            if nmcli con up "$PROFILE" >/dev/null 2>&1; then
                echo "[SAM Network] Successfully reconnected to premise network '$PROFILE'!"
                rm -f "$FAIL_COUNTER_FILE"
                # If Hotspot was active on single interface, deactivate it
                if [ "$AP_INTERFACE" = "$STA_INTERFACE" ] && is_hotspot_active; then
                    nmcli con down "${HOTSPOT_NAME}" >/dev/null 2>&1 || true
                fi
                return 0
            fi
        fi
    done
    return 1
}

# Function to start AP Hotspot
start_hotspot() {
    echo "[SAM Network] Activating Rescue AP Hotspot on ${AP_INTERFACE}..."
    if ! nmcli con show "${HOTSPOT_NAME}" >/dev/null 2>&1; then
        nmcli con add type wifi ifname "${AP_INTERFACE}" con-name "${HOTSPOT_NAME}" autoconnect no ssid "${HOTSPOT_SSID}"
        nmcli con modify "${HOTSPOT_NAME}" 802-11-wireless.mode ap 802-11-wireless.band bg
        nmcli con modify "${HOTSPOT_NAME}" wifi-sec.key-mgmt wpa-psk wifi-sec.psk "raspberry"
        nmcli con modify "${HOTSPOT_NAME}" ipv4.method shared ipv4.addresses "${HOTSPOT_IP}"
    fi
    nmcli con up "${HOTSPOT_NAME}"
}

CURRENT_STATE=$(get_connection_state)

if [ "$CURRENT_STATE" = "connected" ]; then
    # Currently connected to Wi-Fi: reset failure counter
    rm -f "$FAIL_COUNTER_FILE"
    echo "[SAM Network] Wi-Fi is actively connected on ${STA_INTERFACE}."
    exit 0
fi

echo "[SAM Network] Interface ${STA_INTERFACE} is disconnected (State: ${CURRENT_STATE})."

# First, attempt to reconnect to any known premise Wi-Fi
if try_reconnect_known_networks; then
    exit 0
fi

# If known Wi-Fi is not reachable, increment failure counter
FAIL_COUNT=0
if [ -f "$FAIL_COUNTER_FILE" ]; then
    FAIL_COUNT=$(cat "$FAIL_COUNTER_FILE")
fi
FAIL_COUNT=$((FAIL_COUNT + 1))
echo "$FAIL_COUNT" > "$FAIL_COUNTER_FILE"

echo "[SAM Network] Disconnect streak: ${FAIL_COUNT} / ${MAX_DISCONNECT_RETRIES}"

if [ "$FAIL_COUNT" -ge "$MAX_DISCONNECT_RETRIES" ]; then
    if ! is_hotspot_active; then
        echo "[SAM Network] Premise Wi-Fi unreachable after multiple attempts. Starting Rescue AP Hotspot..."
        start_hotspot
    else
        echo "[SAM Network] Rescue AP Hotspot is already active."
    fi
else
    echo "[SAM Network] Retrying premise Wi-Fi on next cycle before falling back to AP mode."
fi
