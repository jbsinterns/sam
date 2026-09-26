"""
SAM Rover - Prometheus Metrics Endpoint
Exposes open-standard Prometheus text metrics for Grafana and time-series monitoring.
"""

from fastapi import APIRouter, Response
from core.hardware_manager import hw_manager

router = APIRouter(tags=["Metrics & Monitoring"])

# Counters maintained in memory
metrics_counters = {
    "watchdog_cuts": 0,
    "obstacle_stops": 0,
    "drive_commands": 0,
}


def increment_counter(key: str, count: int = 1) -> None:
    """Safely increments an in-memory telemetry counter."""
    if key in metrics_counters:
        metrics_counters[key] += count


@router.get("/metrics")
def prometheus_metrics() -> Response:
    """
    Returns application and hardware metrics in standard Prometheus text format.
    Suitable for Prometheus scrapers, Grafana Agent, or Datadog OpenMetrics.
    """
    telemetry = hw_manager.get_telemetry()
    vitals = telemetry.get("vitals", {})
    motors = telemetry.get("motors", {})
    ultrasonic = telemetry.get("ultrasonic", {}).get("distances", {})

    lines = [
        "# HELP sam_hardware_leased Hardware lease state (1 = claimed, 0 = released)",
        "# TYPE sam_hardware_leased gauge",
        f"sam_hardware_leased {1 if telemetry.get('hardware_leased') else 0}",
        "",
        "# HELP sam_motors_enabled Motor power toggle switch state",
        "# TYPE sam_motors_enabled gauge",
        f"sam_motors_enabled {1 if telemetry.get('motors_enabled') else 0}",
        "",
        "# HELP sam_sensors_enabled Ultrasonic polling toggle switch state",
        "# TYPE sam_sensors_enabled gauge",
        f"sam_sensors_enabled {1 if telemetry.get('sensors_enabled') else 0}",
        "",
        "# HELP sam_motor_speed_percent Motor velocity output (-100 to 100)",
        "# TYPE sam_motor_speed_percent gauge",
        f'sam_motor_speed_percent{{side="left"}} {float(motors.get("left", 0.0)):.1f}',
        f'sam_motor_speed_percent{{side="right"}} {float(motors.get("right", 0.0)):.1f}',
        "",
        "# HELP sam_drive_commands_total Total teleoperation drive packets processed",
        "# TYPE sam_drive_commands_total counter",
        f"sam_drive_commands_total {metrics_counters['drive_commands']}",
        "",
        "# HELP sam_watchdog_cuts_total Total failsafe motor cuts triggered by watchdog",
        "# TYPE sam_watchdog_cuts_total counter",
        f"sam_watchdog_cuts_total {metrics_counters['watchdog_cuts']}",
        "",
        "# HELP sam_obstacle_stops_total Total safety stops triggered by proximity sensors",
        "# TYPE sam_obstacle_stops_total counter",
        f"sam_obstacle_stops_total {metrics_counters['obstacle_stops']}",
        "",
        "# HELP sam_ultrasonic_distance_cm Proximity distance in cm",
        "# TYPE sam_ultrasonic_distance_cm gauge",
    ]

    for direction, dist in ultrasonic.items():
        if dist is not None:
            lines.append(f'sam_ultrasonic_distance_cm{{direction="{direction}"}} {float(dist):.1f}')
        else:
            lines.append(f'sam_ultrasonic_distance_cm{{direction="{direction}"}} -1.0')

    # Pi Vitals
    cpu_temp = vitals.get("cpu_temp")
    if cpu_temp is not None:
        lines.extend([
            "",
            "# HELP sam_cpu_temperature_celsius Raspberry Pi SoC CPU temperature",
            "# TYPE sam_cpu_temperature_celsius gauge",
            f"sam_cpu_temperature_celsius {float(cpu_temp):.1f}",
        ])

    lines.extend([
        "",
        "# HELP sam_cpu_load_percent CPU load utilization percentage",
        "# TYPE sam_cpu_load_percent gauge",
        f"sam_cpu_load_percent {float(vitals.get('cpu_load', 0.0)):.1f}",
        "",
        "# HELP sam_ram_usage_percent RAM memory consumption percentage",
        "# TYPE sam_ram_usage_percent gauge",
        f"sam_ram_usage_percent {float(vitals.get('ram_usage', 0.0)):.1f}",
        "",
        "# HELP sam_power_undervoltage Raspberry Pi under-voltage power throttle (1 = under-voltage detected)",
        "# TYPE sam_power_undervoltage gauge",
        f"sam_power_undervoltage {1 if vitals.get('undervoltage') else 0}",
    ])

    return Response(
        content="\n".join(lines) + "\n",
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )
