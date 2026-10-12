#!/bin/bash
# ==============================================================================
# SAM Rover - Smart Premise-Aware Wi-Fi Failover Script (Production v2.4.0)
# Uses NetworkManager (nmcli) standard on Ubuntu 24.04/26.04
#
# Logic:
# 1. Prioritizes known premise Wi-Fi networks (never falls back to AP unnecessarily).
# 2. Differentiates client connection vs Hotspot state (avoids Hotspot loophole).
# 3. Fast-fails over to Rescue AP on fresh boot (< 180s) so students don't wait 3 min.
# 4. Periodically recovers and rejoins premise Wi-Fi if a known network reappears.
# ==============================================================================

export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

HOTSPOT_NAME="SAM-Rover-Setup"
HOTSPOT_SSID="SAM-Rover-Setup"
HOTSPOT_IP="192.168.4.1/24"
FAIL_COUNTER_FILE="/tmp/sam_wifi_fail_count"

# Check if an external Wi-Fi dongle (wlan1 or wlx*) is present
EXT_IFACE=$(nmcli -t -f DEVICE,TYPE dev 2>/dev/null | grep ':wifi$' | cut -d: -f1 | grep -v '^wlan0$' | head -n1)
if [ -n "$EXT_IFACE" ]; then
    AP_INTERFACE="$EXT_IFACE"
    STA_INTERFACE="wlan0"
else
    AP_INTERFACE="wlan0"
    STA_INTERFACE="wlan0"
fi

# Determine if the Rescue AP Hotspot is currently active
is_hotspot_active() {
    nmcli -t -f NAME,TYPE con show --active 2>/dev/null | grep -q "^${HOTSPOT_NAME}:"
}

# Determine if connected to actual premise Wi-Fi (NOT the Hotspot)
is_premise_wifi_connected() {
    local conn
    conn=$(nmcli -t -f NAME,DEVICE,TYPE con show --active 2>/dev/null | grep ":${STA_INTERFACE}:" | cut -d: -f1)
    if [ -n "$conn" ] && [ "$conn" != "${HOTSPOT_NAME}" ]; then
        return 0
    fi
    if [ -n "$EXT_IFACE" ]; then
        local ext_conn
        ext_conn=$(nmcli -t -f NAME,DEVICE,TYPE con show --active 2>/dev/null | grep ":${EXT_IFACE}:" | cut -d: -f1)
        if [ -n "$ext_conn" ] && [ "$ext_conn" != "${HOTSPOT_NAME}" ]; then
            return 0
        fi
    fi
    return 1
}

# Scan & reconnect to known premise networks
try_reconnect_known_networks() {
    echo "[SAM Network] Scanning for known premise Wi-Fi..."
    nmcli dev wifi rescan >/dev/null 2>&1 || true
    
    local visible_ssids saved_profiles
    visible_ssids=$(nmcli -t -f SSID dev wifi list 2>/dev/null | grep -v '^--$' | sort -u)
    saved_profiles=$(nmcli -t -f NAME,TYPE con show 2>/dev/null | grep '802-11-wireless' | cut -d: -f1 | grep -v "${HOTSPOT_NAME}")
    
    for profile in $saved_profiles; do
        if echo "$visible_ssids" | grep -qx "$profile"; then
            echo "[SAM Network] Found visible premise network '$profile'. Reconnecting..."
            # If hotspot was running on the same interface, take it down first
            if [ "$AP_INTERFACE" = "$STA_INTERFACE" ] && is_hotspot_active; then
                nmcli con down "${HOTSPOT_NAME}" >/dev/null 2>&1 || true
                sleep 1
            fi
            if nmcli con up "$profile" >/dev/null 2>&1; then
                echo "[SAM Network] Successfully reconnected to '$profile'!"
                rm -f "$FAIL_COUNTER_FILE"
                return 0
            fi
        fi
    done
    return 1
}

# Start AP Hotspot
start_hotspot() {
    echo "[SAM Network] Activating Rescue AP Hotspot on ${AP_INTERFACE}..."
    if ! nmcli con show "${HOTSPOT_NAME}" >/dev/null 2>&1; then
        nmcli con add type wifi ifname "${AP_INTERFACE}" con-name "${HOTSPOT_NAME}" autoconnect no ssid "${HOTSPOT_SSID}" >/dev/null 2>&1
        nmcli con modify "${HOTSPOT_NAME}" 802-11-wireless.mode ap 802-11-wireless.band bg >/dev/null 2>&1
        nmcli con modify "${HOTSPOT_NAME}" 802-11-wireless-security.key-mgmt wpa-psk 802-11-wireless-security.psk "raspberry" >/dev/null 2>&1
        nmcli con modify "${HOTSPOT_NAME}" ipv4.method shared ipv4.addresses "${HOTSPOT_IP}" >/dev/null 2>&1
    else
        nmcli con modify "${HOTSPOT_NAME}" connection.interface-name "${AP_INTERFACE}" >/dev/null 2>&1
    fi
    nmcli con up "${HOTSPOT_NAME}" ifname "${AP_INTERFACE}"
}

# 1. If actively connected to real premise Wi-Fi, everything is healthy
if is_premise_wifi_connected; then
    rm -f "$FAIL_COUNTER_FILE"
    echo "[SAM Network] Wi-Fi is actively connected on ${STA_INTERFACE}."
    exit 0
fi

# 2. If Hotspot is already running, attempt to find premise Wi-Fi periodically
if is_hotspot_active; then
    echo "[SAM Network] Rescue AP Hotspot is currently active. Checking for premise Wi-Fi..."
    try_reconnect_known_networks || true
    exit 0
fi

# 3. Not connected and Hotspot is off: attempt to reconnect to known Wi-Fi
if try_reconnect_known_networks; then
    exit 0
fi

# 4. If known Wi-Fi is unreachable, check fail counter
# On fresh boot (uptime < 180s), fail over to AP quickly (1 retry = ~45s)
UPTIME_SEC=$(awk '{print int($1)}' /proc/uptime 2>/dev/null || echo 999)
if [ "$UPTIME_SEC" -lt 180 ]; then
    MAX_RETRIES=1
else
    MAX_RETRIES=2
fi

FAIL_COUNT=0
[ -f "$FAIL_COUNTER_FILE" ] && FAIL_COUNT=$(cat "$FAIL_COUNTER_FILE" 2>/dev/null)
FAIL_COUNT=$((FAIL_COUNT + 1))
echo "$FAIL_COUNT" > "$FAIL_COUNTER_FILE"

echo "[SAM Network] Disconnect streak: ${FAIL_COUNT} / ${MAX_RETRIES}"

if [ "$FAIL_COUNT" -ge "$MAX_RETRIES" ]; then
    echo "[SAM Network] Starting Rescue AP Hotspot after ${FAIL_COUNT} failed checks..."
    start_hotspot
fi
