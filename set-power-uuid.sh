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

if [ -z "$*" ]; then
    main "63BE270F-1C11-48FD-A6F7-3AF253FF3E2D"
else
    main "$@"
fi

# 
# /	
# Date	Wed, 10 Oct 2018 01:30:06 -0700
# Subject	[PATCH 1/2] thermal/int340x_thermal: Add additional UUIDs
# From	Matthew Garrett <>
# 	
# 
#     share
# 
# Platforms support more DPTF policies than the driver currently exposes.
# Add them. This effectively reverts
# 31908f45a583e8f21db37f402b6e8d5739945afd which removed several UUIDs
# without explaining why.
# 
# Signed-off-by: Matthew Garrett <mjg59@google.com>
# Cc: Zhang Rui <rui.zhang@intel.com>
# Cc: Nisha Aram <nisha.aram@intel.com>
# ---
#  drivers/thermal/int340x_thermal/int3400_thermal.c | 14 ++++++++++++++
#  1 file changed, 14 insertions(+)
# 
# diff --git a/drivers/thermal/int340x_thermal/int3400_thermal.c b/drivers/thermal/int340x_thermal/int3400_thermal.c
# index e26b01c05e82..51c9097eaf7a 100644
# --- a/drivers/thermal/int340x_thermal/int3400_thermal.c
# +++ b/drivers/thermal/int340x_thermal/int3400_thermal.c
# @@ -22,6 +22,13 @@ enum int3400_thermal_uuid {
#  	INT3400_THERMAL_PASSIVE_1,
#  	INT3400_THERMAL_ACTIVE,
#  	INT3400_THERMAL_CRITICAL,
# +	INT3400_THERMAL_ADAPTIVE_PERFORMANCE,
# +	INT3400_THERMAL_EMERGENCY_CALL_MODE,
# +	INT3400_THERMAL_PASSIVE_2,
# +	INT3400_THERMAL_POWER_BOSS,
# +	INT3400_THERMAL_VIRTUAL_SENSOR,
# +	INT3400_THERMAL_COOLING_MODE,
# +	INT3400_THERMAL_HARDWARE_DUTY_CYCLING,
#  	INT3400_THERMAL_MAXIMUM_UUID,
#  };
#  
# @@ -29,6 +36,13 @@ static char *int3400_thermal_uuids[INT3400_THERMAL_MAXIMUM_UUID] = {
#  	"42A441D6-AE6A-462b-A84B-4A8CE79027D3",
#  	"3A95C389-E4B8-4629-A526-C52C88626BAE",
#  	"97C68AE7-15FA-499c-B8C9-5DA81D606E0A",
# +	"63BE270F-1C11-48FD-A6F7-3AF253FF3E2D",
# +	"5349962F-71E6-431D-9AE8-0A635B710AEE",
# +	"9E04115A-AE87-4D1C-9500-0F3E340BFE75",
# +	"F5A35014-C209-46A4-993A-EB56DE7530A1",
# +	"6ED722A7-9240-48A5-B479-31EEF723D7CF",
# +	"16CAF1B7-DD38-40ED-B1C1-1B8A1913D531",
# +	"BE84BABF-C4D4-403D-B495-3128FD44dAC1",
#  };
#  
#  struct int3400_thermal_priv {
