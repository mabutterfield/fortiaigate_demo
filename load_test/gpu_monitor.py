"""Persistent remote NVIDIA telemetry sampling for local workload runs."""

from __future__ import annotations

import csv
import datetime as dt
import json
import subprocess
import threading
import time
from pathlib import Path
from typing import Any


QUERY_FIELDS = [
    "timestamp",
    "index",
    "uuid",
    "name",
    "utilization.gpu",
    "utilization.memory",
    "memory.used",
    "memory.total",
    "power.draw",
    "temperature.gpu",
]


def _number(value: str) -> float | None:
    value = value.strip()
    if not value or value.upper() in {"N/A", "[N/A]"}:
        return None
    try:
        return float(value)
    except ValueError:
        return None


class NvidiaSmiMonitor:
    def __init__(
        self,
        ssh_command: list[str],
        output_path: Path,
        interval_seconds: int,
    ) -> None:
        self.ssh_command = ssh_command
        self.output_path = output_path
        self.interval_seconds = interval_seconds
        self.process: subprocess.Popen[str] | None = None
        self.thread: threading.Thread | None = None
        self._samples: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self.error = ""

    def start(self) -> None:
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        query = ",".join(QUERY_FIELDS)
        remote = (
            f"nvidia-smi --query-gpu={query} --format=csv,noheader,nounits "
            f"--loop={self.interval_seconds}"
        )
        self.process = subprocess.Popen(
            [*self.ssh_command, remote],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=1,
        )
        self.thread = threading.Thread(target=self._read, daemon=True)
        self.thread.start()

    def _read(self) -> None:
        assert self.process is not None and self.process.stdout is not None
        try:
            with self.output_path.open("a", encoding="utf-8") as handle:
                for line in self.process.stdout:
                    values = next(csv.reader([line]))
                    if len(values) != len(QUERY_FIELDS):
                        continue
                    received_at = dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z")
                    sample = {
                        "received_at": received_at,
                        "received_epoch": time.time(),
                        "gpu_timestamp": values[0].strip(),
                        "index": int(float(values[1].strip())),
                        "uuid": values[2].strip(),
                        "name": values[3].strip(),
                        "utilization_gpu_percent": _number(values[4]),
                        "utilization_memory_percent": _number(values[5]),
                        "memory_used_mib": _number(values[6]),
                        "memory_total_mib": _number(values[7]),
                        "power_draw_watts": _number(values[8]),
                        "temperature_c": _number(values[9]),
                    }
                    with self._lock:
                        self._samples.append(sample)
                    json.dump(sample, handle, sort_keys=True)
                    handle.write("\n")
                    handle.flush()
        except Exception as exc:  # telemetry must not terminate workload traffic
            self.error = str(exc)

    def snapshot(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._samples)

    def stop(self) -> None:
        if self.process is None:
            return
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        if self.thread is not None:
            self.thread.join(timeout=5)
        if self.process.stderr is not None:
            stderr = self.process.stderr.read().strip()
            if stderr and not self.error:
                self.error = stderr[:1000]
