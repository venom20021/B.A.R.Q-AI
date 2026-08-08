"""
FastAPI routes for hardware monitoring — CPU, RAM, GPU, disk telemetry,
threshold configuration, and background monitoring control.
"""

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .hardware_monitor import (
    get_hardware_monitor,
    format_hardware_summary,
    format_uptime,
)

router = APIRouter()


class ThresholdsRequest(BaseModel):
    cpu_percent: Optional[float] = None
    ram_percent: Optional[float] = None
    disk_percent: Optional[float] = None
    gpu_temp: Optional[float] = None
    gpu_percent: Optional[float] = None
    gpu_mem_percent: Optional[float] = None


class MonitoringConfigRequest(BaseModel):
    interval: float = 5.0
    enabled: bool = True


# ─── Endpoints ─────────────────────────────────────────────────────────


@router.get("/hardware", summary="Get full hardware telemetry snapshot")
async def get_hardware_telemetry():
    """Returns current CPU, RAM, disk, GPU, network, and uptime telemetry."""
    try:
        monitor = get_hardware_monitor()
        snap = monitor.snapshot(collect_processes=True)
        return {
            "status": "ok",
            "telemetry": snap.to_dict(),
            "summary": format_hardware_summary(snap),
            "uptime_human": format_uptime(snap.uptime_seconds),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/hardware/brief", summary="Get lightweight telemetry snapshot")
async def get_hardware_brief():
    """Returns a minimal telemetry snapshot for frequent polling (no GPU init)."""
    try:
        monitor = get_hardware_monitor()
        snap = monitor.snapshot(collect_processes=False)
        return {
            "status": "ok",
            "telemetry": snap.to_brief(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/hardware/thresholds", summary="Get alert thresholds")
async def get_thresholds():
    """Return the current alert threshold configuration."""
    monitor = get_hardware_monitor()
    return {
        "thresholds": monitor.get_thresholds(),
        "defaults": {
            "cpu_percent": 90,
            "ram_percent": 90,
            "disk_percent": 95,
            "gpu_temp": 85,
            "gpu_percent": 90,
            "gpu_mem_percent": 90,
        },
    }


@router.post("/hardware/thresholds", summary="Set alert thresholds")
async def set_thresholds(request: ThresholdsRequest):
    """Update alert thresholds. Only provided fields are changed."""
    try:
        monitor = get_hardware_monitor()
        overrides = request.model_dump(exclude_none=True)
        monitor.set_thresholds(overrides)
        return {
            "status": "updated",
            "thresholds": monitor.get_thresholds(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/hardware/thresholds/reset", summary="Reset thresholds to defaults")
async def reset_thresholds():
    """Reset all alert thresholds back to factory defaults."""
    monitor = get_hardware_monitor()
    monitor.reset_thresholds()
    return {
        "status": "reset",
        "thresholds": monitor.get_thresholds(),
    }


@router.post("/hardware/monitoring", summary="Start/stop background monitoring")
async def set_monitoring(request: MonitoringConfigRequest):
    """Start or stop the background hardware monitoring loop.

    When enabled, takes telemetry snapshots at the given interval
    and fires alerts when thresholds are exceeded.
    """
    try:
        monitor = get_hardware_monitor()
        if request.enabled:
            await monitor.start_monitoring(interval=request.interval)
        else:
            await monitor.stop_monitoring()
        return {
            "status": "started" if request.enabled else "stopped",
            "monitoring": request.enabled,
            "interval": request.interval,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/hardware/monitoring", summary="Get monitoring status")
async def get_monitoring_status():
    """Return whether background monitoring is running and its stats."""
    monitor = get_hardware_monitor()
    status = monitor.get_status()
    return {
        "status": "ok",
        "monitoring": status,
    }


@router.get("/hardware/alerts", summary="Get recent alerts")
async def get_alerts(since: Optional[float] = None):
    """Return recent hardware alerts, optionally filtered by timestamp."""
    monitor = get_hardware_monitor()
    alerts = monitor.get_alerts(since=since)
    return {
        "alerts": alerts,
        "count": len(alerts),
    }


@router.post("/hardware/alerts/clear", summary="Clear all alerts")
async def clear_alerts():
    """Dismiss all active hardware alerts."""
    monitor = get_hardware_monitor()
    monitor.clear_alerts()
    return {"status": "cleared"}


@router.get("/hardware/history", summary="Get telemetry history")
async def get_history(count: int = 10):
    """Return the most recent N telemetry snapshots."""
    monitor = get_hardware_monitor()
    history = monitor.get_history(count=count)
    return {
        "history": history,
        "count": len(history),
    }
