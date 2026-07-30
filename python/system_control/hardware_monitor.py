"""
BARQ Hardware Monitor — CPU, RAM, GPU, disk, network telemetry with threshold alerts.

Provides:
- Real-time telemetry snapshot (CPU, RAM, disk, GPU, network, uptime, top processes)
- Configurable threshold monitoring with desktop + voice alerts
- Historical recording of telemetry snapshots
- Background monitoring loop (optional, started via start_monitoring / stop_monitoring)
"""

import asyncio
import json
import logging
import os
import platform
import subprocess
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("barq.hardware_monitor")

# ─── Threshold Configuration ─────────────────────────────────────────────

DEFAULT_THRESHOLDS: dict[str, float] = {
    "cpu_percent": 90.0,       # Alert when CPU > 90%
    "ram_percent": 90.0,       # Alert when RAM > 90%
    "disk_percent": 95.0,      # Alert when disk > 95%
    "gpu_temp": 85.0,          # Alert when GPU temp > 85°C
    "gpu_percent": 90.0,       # Alert when GPU util > 90%
    "gpu_mem_percent": 90.0,   # Alert when GPU mem > 90%
}

# ─── Telemetry Data Models ──────────────────────────────────────────────


@dataclass
class TelemetrySnapshot:
    timestamp: float
    cpu_percent: float
    cpu_count: int
    cpu_freq: Optional[float] = None
    ram_percent: float = 0.0
    ram_used_gb: float = 0.0
    ram_total_gb: float = 0.0
    disk_percent: float = 0.0
    disk_free_gb: float = 0.0
    disk_total_gb: float = 0.0
    net_sent_mbps: float = 0.0
    net_recv_mbps: float = 0.0
    gpu_name: Optional[str] = None
    gpu_percent: Optional[float] = None
    gpu_temp: Optional[float] = None
    gpu_mem_percent: Optional[float] = None
    gpu_mem_used_gb: Optional[float] = None
    gpu_mem_total_gb: Optional[float] = None
    uptime_seconds: float = 0.0
    top_processes: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_brief(self) -> dict[str, Any]:
        """Return a lightweight dict for frequent polling."""
        return {
            "cpu_percent": self.cpu_percent,
            "ram_percent": self.ram_percent,
            "ram_used_gb": self.ram_used_gb,
            "ram_total_gb": self.ram_total_gb,
            "disk_percent": self.disk_percent,
            "gpu_percent": self.gpu_percent,
            "gpu_temp": self.gpu_temp,
            "gpu_mem_percent": self.gpu_mem_percent,
            "uptime_seconds": self.uptime_seconds,
        }


# ─── Alert Model ────────────────────────────────────────────────────────


@dataclass
class HardwareAlert:
    metric: str           # e.g. "cpu_percent", "gpu_temp"
    label: str            # e.g. "CPU", "GPU Temperature"
    current_value: float
    threshold: float
    severity: str         # "warning" | "critical"
    message: str          # Human-readable alert text
    timestamp: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ─── Hardware Monitor ───────────────────────────────────────────────────


class HardwareMonitor:
    """Collects hardware telemetry and fires alerts when thresholds are exceeded."""

    def __init__(self):
        self._thresholds: dict[str, float] = dict(DEFAULT_THRESHOLDS)
        self._history: deque[TelemetrySnapshot] = deque(maxlen=360)  # 360 snapshots max
        self._alerts: deque[HardwareAlert] = deque(maxlen=100)

        # Alert debounce: prevent spamming the same alert within the cooldown window
        self._last_alert_time: dict[str, float] = {}
        self._alert_cooldown: float = 60.0  # seconds

        # Previous network counters for delta calculation
        self._prev_net_sent: int = 0
        self._prev_net_recv: int = 0
        self._prev_net_time: float = 0.0

        # Monitoring loop state
        self._monitor_task: Optional[asyncio.Task] = None
        self._monitor_interval: float = 5.0  # seconds between snapshots
        self._running: bool = False

        # Callbacks
        self.on_alert: Optional[callable] = None  # async callable(alert: HardwareAlert)

        self._ready = False

    # ─── Threshold Management ──────────────────────────────────────────

    def get_thresholds(self) -> dict[str, float]:
        return dict(self._thresholds)

    def set_thresholds(self, overrides: dict[str, float]) -> None:
        valid_keys = set(DEFAULT_THRESHOLDS.keys())
        for key, value in overrides.items():
            if key in valid_keys and isinstance(value, (int, float)) and value > 0:
                self._thresholds[key] = float(value)

    def reset_thresholds(self) -> None:
        self._thresholds = dict(DEFAULT_THRESHOLDS)

    # ─── Telemetry Collection ──────────────────────────────────────────

    def snapshot(self, collect_processes: bool = False) -> TelemetrySnapshot:
        """Take a full hardware telemetry snapshot. Non-blocking.

        Args:
            collect_processes: If True, also collect top 5 processes by CPU.
                               Default False for faster polling.
        """
        import psutil

        now = time.time()

        # CPU
        cpu_percent = psutil.cpu_percent(interval=0.0)  # non-blocking (uses last interval)
        cpu_count = psutil.cpu_count()
        try:
            cpu_freq = psutil.cpu_freq().current if psutil.cpu_freq() else None
        except Exception:
            cpu_freq = None

        # RAM
        mem = psutil.virtual_memory()
        ram_percent = mem.percent
        ram_used_gb = round(mem.used / (1024**3), 2)
        ram_total_gb = round(mem.total / (1024**3), 2)

        # Disk
        try:
            if platform.system() == "Windows":
                disk_path = os.path.splitdrive(os.path.abspath(__file__))[0] + "\\"
            else:
                disk_path = "/"
            disk = psutil.disk_usage(disk_path)
            disk_percent = disk.percent
            disk_free_gb = round(disk.free / (1024**3), 2)
            disk_total_gb = round(disk.total / (1024**3), 2)
        except Exception:
            disk_percent = 0.0
            disk_free_gb = 0.0
            disk_total_gb = 0.0

        # Network (delta from previous measurement)
        net = psutil.net_io_counters()
        net_sent_mbps = 0.0
        net_recv_mbps = 0.0
        if self._prev_net_time > 0:
            dt = now - self._prev_net_time
            if dt > 0:
                net_sent_mbps = round((net.bytes_sent - self._prev_net_sent) * 8 / dt / 1_000_000, 2)
                net_recv_mbps = round((net.bytes_recv - self._prev_net_recv) * 8 / dt / 1_000_000, 2)
        self._prev_net_sent = net.bytes_sent
        self._prev_net_recv = net.bytes_recv
        self._prev_net_time = now

        # Uptime
        try:
            uptime_seconds = time.time() - psutil.boot_time()
        except Exception:
            uptime_seconds = 0.0

        # GPU (via GPUtil)
        gpu_name: Optional[str] = None
        gpu_percent: Optional[float] = None
        gpu_temp: Optional[float] = None
        gpu_mem_percent: Optional[float] = None
        gpu_mem_used_gb: Optional[float] = None
        gpu_mem_total_gb: Optional[float] = None
        try:
            import GPUtil

            gpus = GPUtil.getGPUs()
            if gpus:
                gpu = gpus[0]
                gpu_name = gpu.name
                gpu_percent = round(gpu.load * 100, 1)
                gpu_temp = gpu.temperature
                if gpu.memoryTotal > 0:
                    gpu_mem_percent = round((gpu.memoryUsed / gpu.memoryTotal) * 100, 1)
                    gpu_mem_used_gb = round(gpu.memoryUsed / 1024, 2)
                    gpu_mem_total_gb = round(gpu.memoryTotal / 1024, 2)
        except ImportError:
            logger.debug("GPUtil not installed — skipping GPU telemetry")
        except Exception as e:
            logger.debug(f"GPU telemetry error: {e}")

        # Top processes
        top_processes: list[dict[str, Any]] = []
        if collect_processes:
            try:
                for proc in sorted(psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]),
                                   key=lambda p: p.info.get("cpu_percent", 0) or 0, reverse=True)[:5]:
                    top_processes.append({
                        "pid": proc.info["pid"],
                        "name": proc.info["name"],
                        "cpu_percent": round(proc.info.get("cpu_percent", 0) or 0, 1),
                        "mem_percent": round(proc.info.get("memory_percent", 0) or 0, 1),
                    })
            except Exception:
                pass

        snapshot = TelemetrySnapshot(
            timestamp=now,
            cpu_percent=round(cpu_percent, 1),
            cpu_count=cpu_count,
            cpu_freq=cpu_freq,
            ram_percent=round(ram_percent, 1),
            ram_used_gb=ram_used_gb,
            ram_total_gb=ram_total_gb,
            disk_percent=round(disk_percent, 1),
            disk_free_gb=disk_free_gb,
            disk_total_gb=disk_total_gb,
            net_sent_mbps=net_sent_mbps,
            net_recv_mbps=net_recv_mbps,
            gpu_name=gpu_name,
            gpu_percent=gpu_percent,
            gpu_temp=gpu_temp,
            gpu_mem_percent=gpu_mem_percent,
            gpu_mem_used_gb=gpu_mem_used_gb,
            gpu_mem_total_gb=gpu_mem_total_gb,
            uptime_seconds=uptime_seconds,
            top_processes=top_processes,
        )
        self._history.append(snapshot)
        self._ready = True
        return snapshot

    # ─── Threshold Checking & Alert Generation ────────────────────────

    def check_thresholds(self, snap: TelemetrySnapshot) -> list[HardwareAlert]:
        """Compare a snapshot against thresholds and return any new alerts.

        Applies debounce to prevent alert spam within the cooldown window.
        Alerts are also stored in self._alerts for retrieval.
        """
        alerts: list[HardwareAlert] = []
        now = snap.timestamp

        checks: list[tuple[str, str, float, float, str]] = [
            ("cpu_percent", "CPU", snap.cpu_percent, self._thresholds.get("cpu_percent", 90), "cpu"),
            ("ram_percent", "RAM", snap.ram_percent, self._thresholds.get("ram_percent", 90), "memory"),
        ]

        # Disk check (only if disk_percent is meaningful)
        if snap.disk_percent > 0:
            checks.append(("disk_percent", "Disk", snap.disk_percent, self._thresholds.get("disk_percent", 95), "disk"))

        # GPU checks
        if snap.gpu_temp is not None:
            checks.append(("gpu_temp", "GPU Temperature", snap.gpu_temp, self._thresholds.get("gpu_temp", 85), "gpu"))
        if snap.gpu_percent is not None:
            checks.append(("gpu_percent", "GPU", snap.gpu_percent, self._thresholds.get("gpu_percent", 90), "gpu"))
        if snap.gpu_mem_percent is not None:
            checks.append(("gpu_mem_percent", "GPU Memory", snap.gpu_mem_percent, self._thresholds.get("gpu_mem_percent", 90), "gpu"))

        for metric, label, current, threshold, category in checks:
            if current >= threshold:
                # Debounce: skip if this metric alerted recently
                last_alert = self._last_alert_time.get(metric, 0.0)
                if now - last_alert < self._alert_cooldown:
                    continue

                # Determine severity
                severity = "critical" if current >= threshold * 1.15 else "warning"

                # Human-readable message
                if metric == "cpu_percent":
                    msg = f"CPU at {current:.0f}% — above {threshold:.0f}% threshold"
                elif metric == "ram_percent":
                    msg = f"RAM at {current:.0f}% — above {threshold:.0f}% threshold ({snap.ram_used_gb:.1f}GB / {snap.ram_total_gb:.1f}GB)"
                elif metric == "disk_percent":
                    msg = f"Disk at {current:.0f}% — above {threshold:.0f}% threshold ({snap.disk_free_gb:.1f}GB free)"
                elif metric == "gpu_temp":
                    msg = f"GPU at {current:.0f}°C — above {threshold:.0f}°C threshold"
                elif metric == "gpu_percent":
                    msg = f"GPU at {current:.0f}% — above {threshold:.0f}% threshold"
                elif metric == "gpu_mem_percent":
                    msg = f"GPU memory at {current:.0f}% — above {threshold:.0f}% threshold"
                else:
                    msg = f"{label} at {current:.1f} — above {threshold:.1f} threshold"

                alert = HardwareAlert(
                    metric=metric,
                    label=label,
                    current_value=current,
                    threshold=threshold,
                    severity=severity,
                    message=msg,
                    timestamp=now,
                )
                alerts.append(alert)
                self._last_alert_time[metric] = now

        # Store alerts
        self._alerts.extend(alerts)

        return alerts

    # ─── Alert History ────────────────────────────────────────────────

    def get_alerts(self, since: Optional[float] = None) -> list[dict[str, Any]]:
        """Get recent alerts, optionally filtered by timestamp."""
        if since is None:
            return [a.to_dict() for a in self._alerts]
        return [a.to_dict() for a in self._alerts if a.timestamp >= since]

    def clear_alerts(self) -> None:
        self._alerts.clear()
        self._last_alert_time.clear()

    # ─── History ──────────────────────────────────────────────────────

    def get_history(self, count: int = 10) -> list[dict[str, Any]]:
        """Get the most recent `count` telemetry snapshots (brief format)."""
        items = list(self._history)
        return [s.to_brief() for s in items[-count:]]

    # ─── Status ───────────────────────────────────────────────────────

    def get_status(self) -> dict[str, Any]:
        """Get a full status report including latest telemetry + alerts."""
        latest = self._history[-1] if self._history else None
        return {
            "monitoring": self._running,
            "ready": self._ready,
            "snapshots_collected": len(self._history),
            "active_alerts": len(self._alerts),
            "latest": latest.to_dict() if latest else None,
            "thresholds": self._thresholds,
        }

    # ─── Background Monitoring Loop ───────────────────────────────────

    async def start_monitoring(self, interval: float = 5.0) -> None:
        """Start a background loop that takes snapshots and checks thresholds."""
        if self._running:
            logger.info("[HardwareMonitor] Already monitoring")
            return
        self._running = True
        self._monitor_interval = interval
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info(f"[HardwareMonitor] Monitoring started (interval={interval}s)")

    async def stop_monitoring(self) -> None:
        """Stop the background monitoring loop."""
        self._running = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
            self._monitor_task = None
        logger.info("[HardwareMonitor] Monitoring stopped")

    async def _monitor_loop(self) -> None:
        """Background loop: snapshot → check thresholds → fire alerts."""
        # Take an initial sample to seed CPU percent measurement
        import psutil

        psutil.cpu_percent(interval=0.1)

        while self._running:
            try:
                snap = self.snapshot(collect_processes=False)
                alerts = self.check_thresholds(snap)

                # Fire alert callbacks
                for alert in alerts:
                    logger.warning(f"[HardwareMonitor] ALERT: {alert.message}")
                    if self.on_alert:
                        try:
                            if asyncio.iscoroutinefunction(self.on_alert):
                                await self.on_alert(alert)
                            else:
                                self.on_alert(alert)
                        except Exception as cb_err:
                            logger.error(f"[HardwareMonitor] Alert callback error: {cb_err}")

                await asyncio.sleep(self._monitor_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[HardwareMonitor] Loop error: {e}")
                await asyncio.sleep(5.0)


# ─── Formatter Helpers ─────────────────────────────────────────────────


def format_uptime(seconds: float) -> str:
    """Convert seconds to a human-readable uptime string."""
    days, remainder = divmod(int(seconds), 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, secs = divmod(remainder, 60)
    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    parts.append(f"{secs}s")
    return " ".join(parts)


def format_hardware_summary(snap: TelemetrySnapshot) -> str:
    """Format a telemetry snapshot into a concise spoken summary."""
    lines = [
        f"CPU: {snap.cpu_percent}%, RAM: {snap.ram_percent}% ({snap.ram_used_gb}/{snap.ram_total_gb} GB)",
    ]
    if snap.gpu_name:
        gpu_line = f"GPU {snap.gpu_name}: {snap.gpu_percent}%"
        if snap.gpu_temp is not None:
            gpu_line += f", {snap.gpu_temp}°C"
        lines.append(gpu_line)
    if snap.disk_percent > 0:
        lines.append(f"Disk: {snap.disk_percent}% full ({snap.disk_free_gb} GB free)")
    lines.append(f"Uptime: {format_uptime(snap.uptime_seconds)}")
    return ". ".join(lines)


# ─── Singleton ─────────────────────────────────────────────────────────


_hardware_monitor: Optional[HardwareMonitor] = None


def get_hardware_monitor() -> HardwareMonitor:
    global _hardware_monitor
    if _hardware_monitor is None:
        _hardware_monitor = HardwareMonitor()
    return _hardware_monitor
