"""Render typed Quality Graph check reports."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from monori.ci.lib.status import QualityStatus
from monori.ci.quality_graph.job_results import JobControl
from monori.ci.quality_graph.registry import workflow_job_for_gate, workflow_job_for_report

if TYPE_CHECKING:
    from collections.abc import Collection, Mapping

    from monori.ci.quality_graph.models import Metric

ReportStatus = QualityStatus


@dataclass(frozen=True)
class ReportLocation:
    """Clickable source location rendered consistently in report findings."""

    path: str
    line: int
    url: str

    @property
    def label(self) -> str:
        """Return the compact file-and-line label shown to the reader."""
        return f"{self.path}:{self.line}"


@dataclass(frozen=True)
class ReportFinding:
    """One rendered finding with its current approval state."""

    text: str
    approved: bool = False
    location: ReportLocation | None = None


@dataclass(frozen=True)
class AdminCommands:
    """Reversible administrator controls and explanatory notes."""

    controls: tuple[JobControl, ...]
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class RenderedCheckReport:
    """Carry rendered Markdown together with its original typed controls."""

    summary: str
    controls: tuple[JobControl, ...] = ()
    control_notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReportModel:
    """Typed data consumed by the shared Jinja report template."""

    marker: str
    status: QualityStatus
    message: str = ""
    metrics: tuple[Metric, ...] = ()
    content: str = ""
    findings_title: str = "Findings"
    findings: tuple[ReportFinding, ...] = ()
    admin: AdminCommands | None = None

    @property
    def title(self) -> str:
        """Return the registered title for this report type."""
        return workflow_job_for_report(self.marker).title


TEMPLATE_DIRECTORY = Path(__file__).with_name("templates")
TEMPLATE_ENVIRONMENT = Environment(
    loader=FileSystemLoader(TEMPLATE_DIRECTORY),
    undefined=StrictUndefined,
    autoescape=select_autoescape(default=False),
    keep_trailing_newline=True,
    trim_blocks=False,
    lstrip_blocks=False,
)
REPORT_TEMPLATE = TEMPLATE_ENVIRONMENT.get_template("report.md.j2")


def finding_location(pr_url: str, path: str, line: int) -> ReportLocation:
    """Build a clickable pull-request diff location for a report finding."""
    diff_hash = hashlib.sha256(path.encode()).hexdigest()
    url = f"{pr_url.rstrip('/')}/files#diff-{diff_hash}R{line}"
    return ReportLocation(path, line, url)


def admin_commands(
    gate: str,
    active_ids: Collection[str],
    approved_ids: Collection[str],
    file_findings: Mapping[str, Collection[str]] | None = None,
    notes: Collection[str] = (),
) -> AdminCommands:
    """Build canonical administrator commands from one gate's current data."""
    active = sorted(set(active_ids))
    approved = sorted(set(approved_ids))
    command_target = workflow_job_for_gate(gate).job_id
    controls: list[JobControl] = []
    if active:
        remove_active = f"/qg remove-ignore {','.join(active)}"
        controls.extend(
            (
                JobControl(f"/qg ignore {','.join(active)}", remove_active),
                JobControl(f"/qg ignore {command_target}", remove_active),
            )
        )
        for path, finding_ids in sorted((file_findings or {}).items()):
            selected = sorted(set(finding_ids))
            if selected:
                controls.append(
                    JobControl(
                        f"/qg ignore-file {path}",
                        f"/qg remove-ignore {','.join(selected)}",
                    )
                )
    if approved:
        approved_command = f"/qg ignore {','.join(approved)}"
        controls.append(
            JobControl(
                approved_command,
                f"/qg remove-ignore {','.join(approved)}",
                checked=True,
            )
        )
    return AdminCommands(tuple(controls), tuple(notes))


def render_report(model: ReportModel) -> RenderedCheckReport:
    """Render Markdown while preserving administrator controls as typed data."""
    rendered = re.sub(r"\n{3,}", "\n\n", REPORT_TEMPLATE.render(model=model).strip())
    admin = model.admin or AdminCommands(())
    return RenderedCheckReport(rendered + "\n", admin.controls, admin.notes)
