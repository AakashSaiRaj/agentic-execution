"""Lightweight, DB-derived metrics (Phase 4).

Rather than maintaining cross-process counters, metrics are aggregated from the
database on demand (accurate across API + all workers) plus live queue depths
from Redis. Exposed as JSON (/api/metrics) and Prometheus text (/metrics).
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import func, select

from ..config import get_settings
from ..enums import ExecutionStatus, TaskStatus
from ..models import Execution, Task


def _round(value) -> Optional[float]:
    return round(float(value), 1) if value is not None else None


def collect_metrics(db) -> dict:
    settings = get_settings()

    exec_counts = dict(
        db.execute(select(Execution.status, func.count()).group_by(Execution.status)).all()
    )
    task_counts = dict(
        db.execute(select(Task.status, func.count()).group_by(Task.status)).all()
    )

    total_tokens = int(db.scalar(select(func.coalesce(func.sum(Task.total_tokens), 0))) or 0)
    total_cost = float(db.scalar(select(func.coalesce(func.sum(Task.cost_usd), 0.0))) or 0.0)
    total_tool_calls = int(db.scalar(select(func.coalesce(func.sum(Task.tool_calls), 0))) or 0)

    avg_task_ms = db.scalar(select(func.avg(Task.duration_ms)).where(Task.duration_ms.isnot(None)))
    max_task_ms = db.scalar(select(func.max(Task.duration_ms)))
    avg_exec_ms = db.scalar(
        select(func.avg(Execution.duration_ms)).where(Execution.duration_ms.isnot(None))
    )
    max_exec_ms = db.scalar(select(func.max(Execution.duration_ms)))

    metrics = {
        "executions": {
            "total": sum(exec_counts.values()),
            "by_status": {s.value: int(exec_counts.get(s.value, 0)) for s in ExecutionStatus},
        },
        "tasks": {
            "total": sum(task_counts.values()),
            "by_status": {s.value: int(task_counts.get(s.value, 0)) for s in TaskStatus},
        },
        "durations_ms": {
            "execution_avg": _round(avg_exec_ms),
            "execution_max": int(max_exec_ms) if max_exec_ms is not None else None,
            "task_avg": _round(avg_task_ms),
            "task_max": int(max_task_ms) if max_task_ms is not None else None,
        },
        "llm": {"total_tokens": total_tokens, "total_cost_usd": round(total_cost, 6)},
        "tools": {"total_calls": total_tool_calls},
    }

    if settings.execution_mode.lower() == "queue":
        try:
            from ..jobqueue import dead_letter_depth, delayed_depth, queue_depth

            metrics["queue"] = {
                "main_depth": queue_depth(),
                "delayed_depth": delayed_depth(),
                "dead_letter_depth": dead_letter_depth(),
            }
        except Exception as exc:  # noqa: BLE001
            metrics["queue"] = {"error": str(exc)}

    return metrics


def render_prometheus(metrics: dict) -> str:
    """Render a metrics dict as Prometheus text exposition format."""
    lines = []

    def add(name: str, value, labels: str = "", help_text: str = "", metric_type: str = "gauge"):
        if value is None:
            return
        if help_text:
            lines.append(f"# HELP {name} {help_text}")
            lines.append(f"# TYPE {name} {metric_type}")
        suffix = f"{{{labels}}}" if labels else ""
        lines.append(f"{name}{suffix} {value}")

    for status, count in metrics["executions"]["by_status"].items():
        add("aep_executions_total", count, f'status="{status}"',
            "Executions by status" if status == "PENDING" else "")
    for status, count in metrics["tasks"]["by_status"].items():
        add("aep_tasks_total", count, f'status="{status}"',
            "Tasks by status" if status == "PENDING" else "")

    d = metrics["durations_ms"]
    add("aep_execution_duration_ms_avg", d["execution_avg"], help_text="Avg execution duration (ms)")
    add("aep_execution_duration_ms_max", d["execution_max"], help_text="Max execution duration (ms)")
    add("aep_task_duration_ms_avg", d["task_avg"], help_text="Avg task duration (ms)")
    add("aep_task_duration_ms_max", d["task_max"], help_text="Max task duration (ms)")

    add("aep_llm_tokens_total", metrics["llm"]["total_tokens"],
        help_text="Total LLM tokens", metric_type="counter")
    add("aep_llm_cost_usd_total", metrics["llm"]["total_cost_usd"],
        help_text="Estimated LLM cost (USD)", metric_type="counter")
    add("aep_tool_calls_total", metrics["tools"]["total_calls"],
        help_text="Total tool invocations", metric_type="counter")

    queue = metrics.get("queue", {})
    for name, key in (("main", "main_depth"), ("delayed", "delayed_depth"), ("dead_letter", "dead_letter_depth")):
        if key in queue:
            add("aep_queue_depth", queue[key], f'queue="{name}"',
                "Queue depth" if name == "main" else "")

    return "\n".join(lines) + "\n"
