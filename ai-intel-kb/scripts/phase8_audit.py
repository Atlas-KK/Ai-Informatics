"""Run the local Phase 8 gates and produce redacted, evidence-linked reports."""

from __future__ import annotations

import argparse
import hashlib
import json
import locale
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ai_intel.application.phase8_acceptance import (  # noqa: E402
    AcceptanceAssessment,
    AcceptanceStatus,
    QualityReview,
    SoakObservation,
    assess_quality_sample,
    assess_rolling_thirty_days,
    assess_seven_day_soak,
)
from ai_intel.infrastructure.telemetry.redaction import redact_text  # noqa: E402

EXECUTION_DOC = PROJECT_ROOT.parent / "AI情报知识库_Codex开发执行文档_v1.1.md"
EVIDENCE_DIR = PROJECT_ROOT / "docs" / "phase8" / "evidence"
REPORT_DIR = PROJECT_ROOT / "docs" / "phase8"
_FINGERPRINT_ROOTS = ("src", "tests", "migrations", "scripts", "web/src", "web/e2e")
_FINGERPRINT_FILES = (
    "pyproject.toml",
    "requirements.lock",
    "alembic.ini",
    "web/package.json",
    "web/pnpm-lock.yaml",
    "web/pnpm-workspace.yaml",
    "web/eslint.config.js",
    "web/index.html",
    "web/tsconfig.json",
    "web/tsconfig.app.json",
    "web/tsconfig.node.json",
    "web/vite.config.ts",
)


@dataclass(frozen=True, slots=True)
class CommandResult:
    case_id: str
    label: str
    command: str
    started_at: str
    finished_at: str
    duration_seconds: float
    exit_code: int
    status: str
    evidence_path: str
    output_tail: str


def _redact(value: str) -> str:
    value = redact_text(value)
    return re.sub(r"(?i)sk-[a-z0-9_-]{20,}", "[REDACTED]", value)


def _relative(path: Path) -> str:
    return path.relative_to(PROJECT_ROOT).as_posix()


def _source_fingerprint() -> str:
    """Hash executable sources, tests, migrations and locked configuration."""

    paths: set[Path] = set()
    for relative_root in _FINGERPRINT_ROOTS:
        root = PROJECT_ROOT / relative_root
        if root.exists():
            paths.update(
                path
                for path in root.rglob("*")
                if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
            )
    paths.update(
        path for relative in _FINGERPRINT_FILES if (path := PROJECT_ROOT / relative).is_file()
    )
    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda item: _relative(item)):
        relative = _relative(path).encode("utf-8")
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        content = path.read_bytes()
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def _strict_bool(value: object, field: str) -> bool:
    if type(value) is not bool:
        raise ValueError(f"{field} must be a JSON boolean")
    return value


def _strict_optional_bool(value: object, field: str) -> bool | None:
    return None if value is None else _strict_bool(value, field)


def _run(case_id: str, label: str, command: list[str], evidence_name: str) -> CommandResult:
    started = datetime.now(UTC)
    environment = os.environ.copy()
    environment["PYTHONUTF8"] = "1"
    environment["PYTHONIOENCODING"] = "utf-8"
    completed = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        env=environment,
    )
    finished = datetime.now(UTC)
    output = _redact((completed.stdout or "") + (completed.stderr or ""))
    evidence_path = EVIDENCE_DIR / evidence_name
    payload = {
        "case_id": case_id,
        "label": label,
        "command": subprocess.list2cmdline(command),
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "duration_seconds": round((finished - started).total_seconds(), 3),
        "exit_code": completed.returncode,
        "status": "PASS" if completed.returncode == 0 else "FAIL",
        "source_fingerprint": _source_fingerprint(),
        "output": output,
    }
    evidence_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return CommandResult(
        case_id=case_id,
        label=label,
        command=payload["command"],
        started_at=payload["started_at"],
        finished_at=payload["finished_at"],
        duration_seconds=payload["duration_seconds"],
        exit_code=completed.returncode,
        status=payload["status"],
        evidence_path=_relative(evidence_path),
        output_tail=output[-4000:],
    )


def _tool_version(command: list[str]) -> str:
    result = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding=locale.getpreferredencoding(False),
        errors="replace",
        check=False,
    )
    return _redact(((result.stdout or "") + (result.stderr or "")).strip()) or "unavailable"


def _load_soak(path: Path) -> tuple[SoakObservation, ...]:
    if not path.exists():
        return ()
    payload = json.loads(path.read_text(encoding="utf-8"))
    return tuple(
        SoakObservation(
            report_date=date.fromisoformat(item["report_date"]),
            run_id=str(item["run_id"]),
            trigger_type=str(item["trigger_type"]),
            status=str(item["status"]),
            started_at=datetime.fromisoformat(item["started_at"]),
            finished_at=(
                None
                if item.get("finished_at") is None
                else datetime.fromisoformat(item["finished_at"])
            ),
            enabled_source_ids=tuple(str(value) for value in item["enabled_source_ids"]),
            attempted_source_ids=tuple(str(value) for value in item["attempted_source_ids"]),
            digest_id=None if item.get("digest_id") is None else str(item["digest_id"]),
            failure_trace_complete=_strict_bool(
                item.get("failure_trace_complete", False), "failure_trace_complete"
            ),
        )
        for item in payload.get("observations", [])
    )


def _load_quality(path: Path) -> tuple[tuple[QualityReview, ...], int, frozenset[str], int] | None:
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    reviews = tuple(
        QualityReview(
            event_id=str(item["event_id"]),
            tier=str(item["tier"]),
            relevant=_strict_bool(item["relevant"], "relevant"),
            worth_priority=_strict_optional_bool(item.get("worth_priority"), "worth_priority"),
            conclusion_count=int(item["conclusion_count"]),
            traceable_conclusion_count=int(item["traceable_conclusion_count"]),
            major_hallucination=_strict_bool(item["major_hallucination"], "major_hallucination"),
            excluded_content=_strict_bool(item["excluded_content"], "excluded_content"),
            valid_source_count=int(item["valid_source_count"]),
        )
        for item in payload.get("reviews", [])
    )
    return (
        reviews,
        int(payload["formal_count"]),
        frozenset(str(value) for value in payload.get("expected_must_read_ids", [])),
        int(payload["formal_records_without_valid_source"]),
    )


def _external_adapter_status(path: Path) -> tuple[AcceptanceStatus, tuple[str, ...]]:
    if not path.exists():
        return AcceptanceStatus.BLOCKED, ("未提供用户授权引用及真实适配器小流量证据",)
    payload = json.loads(path.read_text(encoding="utf-8"))
    authorization = str(payload.get("authorization_reference") or "").strip()
    checks = payload.get("checks", [])
    if not authorization:
        return AcceptanceStatus.BLOCKED, ("真实适配器证据缺少用户授权引用",)
    if not isinstance(checks, list) or not checks:
        return AcceptanceStatus.NOT_RUN, ("已有授权引用，但尚无真实适配器执行记录",)
    failed: list[str] = []
    for item in checks:
        if not isinstance(item, dict):
            failed.append("malformed-check")
            continue
        adapter = str(item.get("adapter") or "unknown").strip()
        evidence = str(item.get("evidence") or "").strip()
        evidence_path = (PROJECT_ROOT / evidence).resolve() if evidence else None
        evidence_is_local = evidence_path is not None and (
            evidence_path == PROJECT_ROOT or PROJECT_ROOT in evidence_path.parents
        )
        if (
            item.get("status") != "PASS"
            or not evidence_is_local
            or evidence_path is None
            or not evidence_path.is_file()
        ):
            failed.append(adapter)
    if failed:
        return AcceptanceStatus.FAIL, ("真实适配器未通过：" + "、".join(failed),)
    return AcceptanceStatus.PASS, ()


def _load_existing_result(case_id: str, label: str, path: Path) -> CommandResult:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("case_id") != case_id:
        raise SystemExit(f"Evidence case mismatch: {path}")
    exit_code = int(payload["exit_code"])
    status = str(payload["status"])
    if status not in {"PASS", "FAIL"} or (status == "PASS") != (exit_code == 0):
        raise SystemExit(f"Evidence result is inconsistent: {path}")
    if payload.get("source_fingerprint") != _source_fingerprint():
        raise SystemExit(f"Evidence is stale for the current source tree: {path}")
    return CommandResult(
        case_id=case_id,
        label=label,
        command=str(payload["command"]),
        started_at=str(payload["started_at"]),
        finished_at=str(payload["finished_at"]),
        duration_seconds=float(payload["duration_seconds"]),
        exit_code=exit_code,
        status=status,
        evidence_path=_relative(path),
        output_tail=str(payload.get("output", ""))[-4000:],
    )


def _inventory(markdown: str) -> dict[str, dict[str, tuple[str, ...]]]:
    patterns = {
        "FR": re.compile(r"^F(?:[1-9]|1[0-2])$"),
        "AC": re.compile(r"^AC-[FDIEM]\d{2}$"),
        "NFR": re.compile(r"^NFR-S\d{2}(?:\s+.*)?$"),
        "CTD_ALIAS": re.compile(r"^TA-[A-Z]+-\d{2}(?:\s+.*)?$"),
    }
    found: dict[str, dict[str, tuple[str, ...]]] = {key: {} for key in patterns}
    for line in markdown.splitlines():
        if not line.startswith("|"):
            continue
        cells = tuple(cell.strip().replace("`", "") for cell in line.strip().strip("|").split("|"))
        if not cells:
            continue
        first = cells[0]
        for group, pattern in patterns.items():
            if pattern.fullmatch(first):
                key = first.split()[0]
                found[group].setdefault(key, cells)
    expected = {"FR": 12, "AC": 76, "NFR": 9, "CTD_ALIAS": 7}
    actual = {key: len(value) for key, value in found.items()}
    if actual != expected:
        raise RuntimeError(f"traceability inventory mismatch: expected={expected}, actual={actual}")
    return found


def _assessment_or_not_run(
    loaded: tuple[tuple[QualityReview, ...], int, frozenset[str], int] | None,
) -> AcceptanceAssessment:
    if loaded is None:
        return AcceptanceAssessment(
            AcceptanceStatus.NOT_RUN,
            {"state": "WAITING_FOR_HUMAN_REVIEW"},
            ("尚未提交基于 7 日正式档案的人工质量抽检结果",),
        )
    reviews, formal_count, must_read_ids, without_source = loaded
    return assess_quality_sample(
        reviews,
        formal_count=formal_count,
        expected_must_read_ids=must_read_ids,
        formal_records_without_valid_source=without_source,
    )


def _status_cell(status: AcceptanceStatus | str) -> str:
    value = status.value if isinstance(status, AcceptanceStatus) else status
    return value


def _write_traceability(
    inventory: dict[str, dict[str, tuple[str, ...]]],
    *,
    command_results: dict[str, CommandResult],
    soak: AcceptanceAssessment,
    quality: AcceptanceAssessment,
    rolling: AcceptanceAssessment,
) -> Path:
    full_status = command_results["P8-TC-01"].status
    security_status = command_results["P8-TC-02"].status
    performance_status = command_results["P8-TC-03"].status
    lines = [
        "# Phase 8 最终追踪报告",
        "",
        "本报告区分本地/Fake 自动化证据与真实时间、人工评审和外部适配证据。",
        "",
        "## 计数审计",
        "",
        "| 对象 | 数量 | 结果 |",
        "| --- | ---: | --- |",
        f"| FR | {len(inventory['FR'])}/12 | PASS |",
        f"| AC | {len(inventory['AC'])}/76 | PASS |",
        f"| NFR | {len(inventory['NFR'])}/9 | PASS |",
        f"| CTD 执行别名 | {len(inventory['CTD_ALIAS'])}/7（覆盖 CTD-01～08） | PASS |",
        "",
    ]
    mappings = (
        ("FR", "FR（本地/Fake 产品能力）"),
        ("AC", "AC"),
        ("NFR", "核心成功指标"),
        ("CTD_ALIAS", "CTD 执行别名"),
    )
    for group, title in mappings:
        lines.extend(
            (
                f"## {title}",
                "",
                "| ID | 状态 | 阶段/范围 | 证据或延期理由 |",
                "| --- | --- | --- | --- |",
            )
        )
        for item_id, cells in inventory[group].items():
            phase = cells[1] if len(cells) > 1 else "-"
            evidence = cells[2] if len(cells) > 2 else "执行文档追踪矩阵"
            status: str
            reason: str
            if group == "NFR":
                if item_id in {"NFR-S01", "NFR-S03"}:
                    status, reason = (
                        soak.status.value,
                        "P8-TC-04：" + "；".join(soak.reasons or ("7 日证据通过",)),
                    )
                elif item_id == "NFR-S02":
                    status, reason = (
                        rolling.status.value,
                        "P8-TC-08：" + "；".join(rolling.reasons or ("30 日指标通过",)),
                    )
                elif item_id in {"NFR-S04", "NFR-S05", "NFR-S06", "NFR-S07", "NFR-S08"}:
                    status, reason = (
                        quality.status.value,
                        "P8-TC-05：" + "；".join(quality.reasons or ("质量抽检通过",)),
                    )
                else:
                    status, reason = performance_status, command_results["P8-TC-03"].evidence_path
            elif group == "AC" and item_id == "AC-D13":
                status, reason = performance_status, command_results["P8-TC-03"].evidence_path
            elif group == "AC" and item_id in {"AC-E14", "AC-E15", "AC-E16", "AC-M04"}:
                status, reason = security_status, command_results["P8-TC-02"].evidence_path
            else:
                status, reason = full_status, command_results["P8-TC-01"].evidence_path
            safe_evidence = evidence.replace("|", "/")
            safe_reason = reason.replace("|", "/")
            lines.append(f"| {item_id} | {status} | {phase} | {safe_evidence}；{safe_reason} |")
        lines.append("")
    target = REPORT_DIR / "traceability-report.md"
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target


def _write_reports(
    results: dict[str, CommandResult],
    inventory: dict[str, dict[str, tuple[str, ...]]],
    soak: AcceptanceAssessment,
    quality: AcceptanceAssessment,
    external_status: AcceptanceStatus,
    external_reasons: tuple[str, ...],
    rolling: AcceptanceAssessment,
    versions: dict[str, str],
) -> None:
    trace_path = _write_traceability(
        inventory,
        command_results=results,
        soak=soak,
        quality=quality,
        rolling=rolling,
    )
    tc_statuses = {
        "P8-TC-01": (results["P8-TC-01"].status, results["P8-TC-01"].evidence_path),
        "P8-TC-02": (results["P8-TC-02"].status, results["P8-TC-02"].evidence_path),
        "P8-TC-03": (results["P8-TC-03"].status, results["P8-TC-03"].evidence_path),
        "P8-TC-04": (soak.status.value, "；".join(soak.reasons or ("7 日证据通过",))),
        "P8-TC-05": (quality.status.value, "；".join(quality.reasons or ("质量抽检通过",))),
        "P8-TC-06": (external_status.value, "；".join(external_reasons or ("真实适配器通过",))),
        "P8-TC-07": ("PASS", _relative(trace_path)),
        "P8-TC-08": (rolling.status.value, "；".join(rolling.reasons or ("30 日指标通过",))),
    }
    local_failures = [
        case_id
        for case_id in ("P8-TC-01", "P8-TC-02", "P8-TC-03")
        if tc_statuses[case_id][0] == "FAIL"
    ]
    overall = (
        "FAIL"
        if local_failures
        else ("PASS" if all(status == "PASS" for status, _ in tc_statuses.values()) else "PARTIAL")
    )
    now = datetime.now(UTC).isoformat()
    lines = [
        "# Phase 8 验收报告",
        "",
        f"- 生成时间：{now}",
        f"- 总体状态：**{overall}**",
        "- 验收边界：本地/Fake 自动化已执行；真实服务、自然日试运行和人工复核不以模拟结果冒充。",
        "",
        "## 环境与版本",
        "",
        "| 项目 | 版本 |",
        "| --- | --- |",
    ]
    lines.extend(f"| {key} | {value.replace('|', '/')} |" for key, value in versions.items())
    lines.extend(("", "## 用例结果", "", "| 用例 | 状态 | 证据/说明 |", "| --- | --- | --- |"))
    lines.extend(
        f"| {case_id} | {status} | {evidence.replace('|', '/')} |"
        for case_id, (status, evidence) in tc_statuses.items()
    )
    lines.extend(
        (
            "",
            "## 评估指标",
            "",
            "### 7 日试运行",
            "",
            "```json",
            json.dumps(asdict(soak), ensure_ascii=False, indent=2),
            "```",
            "",
            "### 人工质量抽检",
            "",
            "```json",
            json.dumps(asdict(quality), ensure_ascii=False, indent=2),
            "```",
            "",
            "### 滚动 30 日",
            "",
            "```json",
            json.dumps(asdict(rolling), ensure_ascii=False, indent=2),
            "```",
            "",
            "## 停止门禁",
            "",
            (
                "本报告生成后未部署公网、未安装 Windows 计划任务/系统服务、"
                "未发送真实消息，也未读取或写入真实凭证。"
            ),
            "",
        )
    )
    (REPORT_DIR / "phase8-acceptance-report.md").write_text("\n".join(lines), encoding="utf-8")

    risk_lines = [
        "# Phase 8 已知风险清单",
        "",
        "| 风险 | 当前状态 | 处置/退出条件 |",
        "| --- | --- | --- |",
        (
            "| 真实来源、LLM/Embedding、扩展搜索、飞书尚未小流量验收 | "
            f"{external_status.value} | 用户另行授权专用测试凭证和测试对象后执行 "
            "P8-TC-06；凭证不得进入证据文件 |"
        ),
        (
            f"| 连续 7 个自然日试运行未形成完整证据 | {soak.status.value} | "
            "使用只读采证脚本累计 7 个连续自然日；不得用 Fake Clock 演练替代 |"
        ),
        (
            f"| 质量阈值尚缺人工判定 | {quality.status.value} | "
            "对 7 日正式档案按 30 条/不足全检并覆盖全部必读 |"
        ),
        (
            f"| 30 日稳定性仍在观测 | {rolling.status.value} | "
            "满 30 个连续自然日后按滚动口径计算，当前不得宣称通过 |"
        ),
        "| Windows 计划任务未安装 | BLOCKED | 只有用户单独授权后才能创建；当前脚本不修改系统调度 |",
        (
            "| 项目文件尚未纳入可证明的 Git 基线 | BLOCKED | "
            "用户决定跟踪/提交策略后再建立版本化验收基线 |"
        ),
        "",
    ]
    (REPORT_DIR / "known-risks.md").write_text("\n".join(risk_lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execution-doc", type=Path, default=EXECUTION_DOC)
    parser.add_argument("--skip-commands", action="store_true")
    args = parser.parse_args()
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    python = str(PROJECT_ROOT / ".venv" / "Scripts" / "python.exe")
    if not Path(python).exists():
        raise SystemExit("Missing .venv; run scripts/bootstrap.ps1 first")

    command_specs = (
        (
            "P8-TC-01",
            "Phase 1-7 full gate and browser E2E",
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(PROJECT_ROOT / "scripts" / "quality.ps1"),
                "-Scope",
                "full",
            ],
            "p8-tc-01-full-gate.json",
        ),
        (
            "P8-TC-02",
            "Security boundary suite",
            [
                python,
                "-B",
                "-m",
                "pytest",
                "tests/test_config.py",
                "tests/test_secret_scan.py",
                "tests/phase5/test_phase5_acceptance.py",
                "tests/phase7/test_phase7_acceptance.py",
                "tests/phase8/test_phase8_acceptance.py",
                "-q",
                "-k",
                "security or secret or injection or xss or missing_expansion_configuration",
            ],
            "p8-tc-02-security.json",
        ),
        (
            "P8-TC-03",
            "10k repository and real-browser performance with SQLite reconciliation",
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(PROJECT_ROOT / "scripts" / "phase8-performance.ps1"),
            ],
            "p8-tc-03-performance.json",
        ),
        (
            "P8-RECOVERY",
            "Atomic commit, lock and recovery suite",
            [
                python,
                "-B",
                "-m",
                "pytest",
                "tests/phase2/test_recovery.py",
                "tests/phase2/test_lifecycle.py",
                "tests/phase6/test_phase6_acceptance.py",
                "-q",
                "-k",
                "recovery or stale or deadline or unique_lock or interrupted",
            ],
            "p8-recovery.json",
        ),
    )
    results: dict[str, CommandResult] = {}
    if args.skip_commands:
        for case_id, label, _command, evidence_name in command_specs:
            path = EVIDENCE_DIR / evidence_name
            if not path.exists():
                raise SystemExit(f"Missing existing evidence: {path}")
            results[case_id] = _load_existing_result(case_id, label, path)
    else:
        for case_id, label, command, evidence_name in command_specs:
            results[case_id] = _run(case_id, label, command, evidence_name)

    inventory = _inventory(args.execution_doc.read_text(encoding="utf-8"))
    soak_observations = _load_soak(EVIDENCE_DIR / "soak-observations.json")
    soak = (
        assess_seven_day_soak(soak_observations)
        if soak_observations
        else AcceptanceAssessment(
            AcceptanceStatus.NOT_RUN,
            {"observed_runs": 0, "natural_days": 0},
            ("尚未形成连续 7 个自然日的实际计划运行证据",),
        )
    )
    quality = _assessment_or_not_run(_load_quality(EVIDENCE_DIR / "quality-review.json"))
    external_status, external_reasons = _external_adapter_status(
        EVIDENCE_DIR / "real-adapters.json"
    )
    rolling = assess_rolling_thirty_days(soak_observations)
    versions = {
        "Python": _tool_version([python, "--version"]),
        "PowerShell": _tool_version(
            ["powershell", "-NoProfile", "-Command", "$PSVersionTable.PSVersion.ToString()"]
        ),
        "Git HEAD": _tool_version(["git", "rev-parse", "HEAD"]),
        "Source fingerprint": _source_fingerprint(),
        "执行文档": str(args.execution_doc),
    }
    _write_reports(
        results,
        inventory,
        soak,
        quality,
        external_status,
        external_reasons,
        rolling,
        versions,
    )
    local_failures = [result.case_id for result in results.values() if result.status == "FAIL"]
    if local_failures:
        print("Phase 8 local audit failed: " + ", ".join(local_failures))
        return 1
    print("Phase 8 local audit passed; deferred evidence remains explicitly non-PASS.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
