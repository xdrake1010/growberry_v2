#!/bin/bash
# Growberry WiFi Watchdog
# Detects internet loss and attempts to reconnect nmcli/interface
LOG=/var/log/growberry_wifi.log
IFACE=wlan0

# Check connectivity to Google DNS
ping -c 3 -W 5 8.8.8.8 > /dev/null 2>&1

if [ $? -ne 0 ]; then
    echo "[$(date)] No internet connectivity detected. Attempting to repair..." >> $LOG
    
    # Attempt 1: Get active connection name and try to bring it up
    CONN_NAME=$(nmcli -t -f NAME,DEVICE connection show --active | grep $IFACE | cut -d: -f1)
    
    if [ -n "$CONN_NAME" ]; then
        echo "[$(date)] Found active connection: $CONN_NAME. Reconnecting..." >> $LOG
        nmcli connection up "$CONN_NAME" >> $LOG 2>&1
    else
        echo "[$(date)] No active connection found on $IFACE. Searching for saved connections..." >> $LOG
        # Try to bring up the first available wifi connection
        SAVED_CONN=$(nmcli -t -f NAME,TYPE connection show | grep 802-11-wireless | head -n 1 | cut -d: -f1)
        if [ -n "$SAVED_CONN" ]; then
             nmcli connection up "$SAVED_CONN" >> $LOG 2>&1
        fi
    fi

    # Wait and check again
    sleep 15
    ping -c 3 -W 5 8.8.8.8 > /dev/null 2>&1
    
    if [ $? -ne 0 ]; then
        echo "[$(date)] nmcli reconnect failed. Power cycling interface $IFACE..." >> $LOG
        ip link set $IFACE down
        sleep 5
        ip link set $IFACE up
        sleep 20
    fi

    # Final check
    ping -c 3 -W 5 8.8.8.8 > /dev/null 2>&1
    if [ $? -eq 0 ]; then
        echo "[$(date)] Connectivity restored successfully." >> $LOG
    else
        echo "[$(date)] Connectivity repair failed. Still offline." >> $LOG
    fi
fi
