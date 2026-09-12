"""Enumerations for execution / task states and agent types.

Stored in the database as their string values (plain VARCHARs) which keeps
migrations portable across SQLite and Postgres and avoids native ENUM types.
"""
from __future__ import annotations

from enum import Enum


class ExecutionStatus(str, Enum):
    PENDING = "PENDING"
    PLANNING = "PLANNING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class AgentType(str, Enum):
    RESEARCH = "research"
    ANALYSIS = "analysis"
    SUMMARIZATION = "summarization"

    @classmethod
    def from_value(cls, value: str) -> "AgentType":
        """Best-effort parse of a free-form agent type string."""
        if value is None:
            return cls.RESEARCH
        normalized = str(value).strip().lower()
        for member in cls:
            if member.value == normalized:
                return member
        # Accept a few common synonyms the LLM might emit.
        synonyms = {
            "researcher": cls.RESEARCH,
            "search": cls.RESEARCH,
            "analyze": cls.ANALYSIS,
            "analyst": cls.ANALYSIS,
            "analytics": cls.ANALYSIS,
            "summary": cls.SUMMARIZATION,
            "summarize": cls.SUMMARIZATION,
            "summarizer": cls.SUMMARIZATION,
        }
        return synonyms.get(normalized, cls.RESEARCH)
