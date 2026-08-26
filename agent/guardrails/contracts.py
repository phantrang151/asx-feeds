from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class GuardrailDecision:
    """Standard result for a guardrail decision."""

    allowed: bool
    reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolResult:
    """Application-level tool result before a framework adapter serializes it."""

    content: str
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    outcome: str = "succeeded"
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_content_and_artifact(self) -> tuple[str, list[dict[str, Any]]]:
        artifacts = [dict(self.metadata, **artifact) for artifact in self.artifacts]
        return self.content, artifacts
