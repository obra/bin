#!/bin/bash

set -eu


die() {
    echo "$1" >&2
    exit 1
}


main() {
    local uuid="$1"; shift

    # Ensure we have the device node
    if [[ ! -d /sys/devices/platform/INT3400:00/ ]]; then
        die "INT3400 device not found"
    fi

    # Ensure we have the thermal zone...
    local zone
    for zone in /sys/class/thermal/thermal_zone?; do
        if [[ -f "$zone/type" ]] && [[ "$(cat $zone/type)" = "INT3400 Thermal" ]]; then
            break
        fi
    done
    if [[ -z "${zone:-}" ]]; then
        die "Could not find 'INT3400 Thermal' thermal zone"
    fi

    # ... and that we can enable/disable it (which is only true when the right
    # kernel patches are present).
    if [[ ! -f "$zone/mode" ]]; then
        die "Thermal zone 'mode' not found; are the kernel patches applied?"
    fi

    # Ensure the given UUID exists in the `available_uuids` set.
    if ! grep -q "^$uuid$" "/sys/devices/platform/INT3400:00/uuids/available_uuids" 2>&1 >/dev/null; then
        die "UUID '$uuid' is not supported by the device"
    fi

    # Okay, all set!  Disable zone, set UUID, then enable.
    echo disabled > "$zone/mode"
    echo "$uuid" > "/sys/devices/platform/INT3400:00/uuids/current_uuid"
    echo enabled > "$zone/mode"
    echo "Set UUID to: $uuid" >&2

    # Ensure that the UUID set properly by reading it back.
    if [[ "$(cat /sys/devices/platform/INT3400:00/uuids/current_uuid)" != "$uuid" ]]; then
        die "UUID did not set correctly"
    fi

    echo "Success" >&2
}


main "$@"