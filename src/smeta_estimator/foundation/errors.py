"""Domain errors for foundation calculations."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    """One invalid input with a stable field identifier."""

    field: str
    message: str


class FoundationValidationError(ValueError):
    """Raised when a foundation calculation cannot safely continue."""

    def __init__(self, issues: list[ValidationIssue] | tuple[ValidationIssue, ...]):
        self.issues = tuple(issues)
        details = "; ".join(f"{issue.field}: {issue.message}" for issue in self.issues)
        super().__init__(details or "Invalid foundation input")
