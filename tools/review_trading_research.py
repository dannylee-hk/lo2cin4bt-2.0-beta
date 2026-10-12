from __future__ import annotations

import argparse
import html
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DOC_NAMES = (
    "README.md",
    "RESEARCH_SPEC.md",
    "HANDOFF.md",
    "STATUS.md",
)
RUNNER_RE = re.compile(
    r"(?:^|[_-])(run|runner|backtest|monitor|pipeline|screener|refresh|build)(?:[_-]|\.|$)",
    re.IGNORECASE,
)
ARTIFACT_RE = re.compile(
    r"(backtest|result|summary|metrics|trades|equity|drawdown|wfa|walk.forward|"
    r"event.study|monitor|verdict|gate|status|readiness)",
    re.IGNORECASE,
)
TEXT_SUFFIXES = {".md", ".txt", ".json", ".yaml", ".yml", ".toml"}
SKIP_DIRS = {
    ".git",
    ".pytest_cache",
    "__pycache__",
    ".venv",
    "node_modules",
    "archive",
}

EVIDENCE_CHECKS = {
    "hypothesis": (
        "hypothesis",
        "thesis",
        "economic logic",
        "研究假設",
        "假設",
    ),
    "costs_slippage": (
        "slippage",
        "transaction cost",
        "commission",
        "spread",
        "滑價",
        "交易成本",
    ),
    "lookahead_timing": (
        "look-ahead",
        "lookahead",
        "point-in-time",
        "usable_from",
        "observed_at",
        "前視",
        "時間可用",
    ),
    "survivorship_universe": (
        "survivorship",
        "historical constituents",
        "point-in-time universe",
        "delisted",
        "存活者",
        "歷史成分",
    ),
    "out_of_sample": (
        "out-of-sample",
        "out of sample",
        "walk-forward",
        "walk forward",
        "rolling validation",
        "oos",
        "樣本外",
        "滾動驗證",
    ),
    "parameter_robustness": (
        "parameter sensitivity",
        "robustness",
        "stress test",
        "plateau",
        "sensitivity",
        "參數敏感",
        "穩健",
        "壓力測試",
    ),
    "sample_size": (
        "trade count",
        "total trades",
        "sample size",
        "observations",
        "樣本量",
        "交易次數",
    ),
    "benchmark": (
        "benchmark",
        "buy and hold",
        "基準",
    ),
    "provenance": (
        "provider",
        "source",
        "provenance",
        "retrieved",
        "as of",
        "資料來源",
        "數據來源",
    ),
}


def _read_text(path: Path, limit: int = 1_000_000) -> str:
    try:
        if path.stat().st_size > limit:
            return ""
        return path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return ""


def _iter_files(root: Path, max_depth: int = 4):
    root_depth = len(root.parts)
    for path in root.rglob("*"):
        try:
            relative_depth = len(path.parts) - root_depth
        except OSError:
            continue
        if relative_depth > max_depth:
            continue
        if any(part in SKIP_DIRS for part in path.parts[root_depth:]):
            continue
        if path.is_file():
            yield path


def _load_status(project_dir: Path) -> tuple[dict[str, Any] | None, str | None]:
    path = project_dir / "status.json"
    if not path.exists():
        return None, None
    try:
        payload = json.loads(_read_text(path))
        if not isinstance(payload, dict):
            return None, "status.json is not an object"
        return payload, None
    except json.JSONDecodeError as exc:
        return None, f"invalid status.json: {exc}"


def _find_docs(project_dir: Path) -> list[Path]:
    docs: list[Path] = []
    for name in DOC_NAMES:
        path = project_dir / name
        if path.exists():
            docs.append(path)
    for path in project_dir.glob("*HANDOFF*.md"):
        if path not in docs:
            docs.append(path)
    return sorted(docs)


def _find_runners(project_dir: Path) -> list[Path]:
    candidates: list[Path] = []
    for path in _iter_files(project_dir, max_depth=2):
        if path.suffix.lower() not in {".py", ".ps1", ".bat", ".cmd", ".sh"}:
            continue
        if RUNNER_RE.search(path.name):
            candidates.append(path)
    return sorted(candidates, key=lambda p: (len(p.relative_to(project_dir).parts), p.name))[:12]


def _find_artifacts(project_dir: Path) -> list[Path]:
    candidates: list[Path] = []
    for path in _iter_files(project_dir, max_depth=4):
        if path.suffix.lower() not in {
            ".json",
            ".csv",
            ".parquet",
            ".html",
            ".md",
            ".xlsx",
        }:
            continue
        relative = path.relative_to(project_dir).as_posix()
        if relative in DOC_NAMES or relative == "status.json":
            continue
        if ARTIFACT_RE.search(relative):
            candidates.append(path)
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[:20]


def _collect_review_text(
    project_dir: Path,
    docs: list[Path],
    status: dict[str, Any] | None,
    artifacts: list[Path],
) -> str:
    parts = [_read_text(path) for path in docs]
    if status:
        parts.append(json.dumps(status, ensure_ascii=False))
    for path in artifacts:
        if path.suffix.lower() in TEXT_SUFFIXES:
            parts.append(_read_text(path, limit=250_000))
    return "\n".join(parts).lower()


def _infer_project_type(name: str, runners: list[Path], artifacts: list[Path]) -> str:
    lowered = name.lower()
    if lowered in {"cbbc-data", "longbridge_backfill"}:
        return "data_pipeline"
    if lowered == "workspace-audit":
        return "governance"
    if "guide" in lowered:
        return "research_guide"
    if "monitor" in lowered or "dashboard" in lowered:
        return "monitor"
    if any("backtest" in path.name.lower() for path in runners + artifacts):
        return "backtest_research"
    if runners:
        return "strategy_research"
    return "research_notes"


def _status_gate(status: dict[str, Any] | None) -> tuple[bool | None, str]:
    if not status:
        return None, "No root status.json"
    gate = status.get("gate")
    if isinstance(gate, dict):
        return bool(gate.get("passed")), str(gate.get("reason") or "")
    return None, "status.json has no gate object"


def _review_project(project_dir: Path, now: datetime) -> dict[str, Any]:
    status, status_error = _load_status(project_dir)
    docs = _find_docs(project_dir)
    runners = _find_runners(project_dir)
    artifacts = _find_artifacts(project_dir)
    review_text = _collect_review_text(project_dir, docs, status, artifacts)
    checks = {
        key: any(term in review_text for term in terms)
        for key, terms in EVIDENCE_CHECKS.items()
    }
    coverage_score = round(sum(checks.values()) / len(checks) * 100)
    gate_passed, gate_reason = _status_gate(status)
    project_type = _infer_project_type(project_dir.name, runners, artifacts)

    latest_paths = docs + runners + artifacts
    latest_mtime = max(
        (path.stat().st_mtime for path in latest_paths),
        default=project_dir.stat().st_mtime,
    )
    latest_update = datetime.fromtimestamp(latest_mtime, tz=timezone.utc)
    age_days = max(0, (now - latest_update).days)

    verdict = str(status.get("verdict") or "UNMANAGED") if status else "UNMANAGED"
    canonical_command = status.get("canonical_command") if status else None
    evidence_as_of = status.get("evidence_as_of") if status else None
    blockers = list(status.get("blockers") or []) if status else []
    source_boundaries = list(status.get("source_boundaries") or []) if status else []

    if status_error:
        action = "FIX_STATUS"
    elif project_type in {"data_pipeline", "governance"}:
        action = "SUPPORTING_ONLY"
    elif status:
        if verdict == "DATA_BLOCKED":
            action = "COLLECT_DATA" if not canonical_command else "RERUN_OR_COLLECT"
        elif verdict in {"WATCH", "PROXY_ONLY", "NO_TRADE"}:
            action = "RERUN_REVIEW" if canonical_command else "REVIEW"
        elif gate_passed and verdict in {"RESEARCH_READY", "PAPER_TEST"}:
            action = "STRESS_TEST"
        else:
            action = "REVIEW"
    elif runners and artifacts:
        action = "INITIALIZE_STATUS_AND_REVIEW"
    elif runners:
        action = "RUN_BASELINE"
    else:
        action = "DOCUMENT_OR_ARCHIVE_DECISION"

    risk_flags: list[str] = []
    if project_type not in {"data_pipeline", "governance", "research_guide"}:
        if not checks["costs_slippage"]:
            risk_flags.append("cost/slippage evidence not found")
        if not checks["lookahead_timing"]:
            risk_flags.append("look-ahead/time-availability control not found")
        if not checks["out_of_sample"]:
            risk_flags.append("out-of-sample/WFA evidence not found")
        if not checks["parameter_robustness"]:
            risk_flags.append("parameter robustness evidence not found")
        if not checks["sample_size"]:
            risk_flags.append("sample-size evidence not found")
    if not status:
        risk_flags.append("root status.json missing")
    if not docs:
        risk_flags.append("root README/research specification missing")
    if not runners and project_type not in {"research_notes", "research_guide", "governance"}:
        risk_flags.append("canonical runner not discovered")

    return {
        "project": project_dir.name,
        "path": str(project_dir),
        "project_type": project_type,
        "managed": status is not None,
        "status_error": status_error,
        "verdict": verdict,
        "gate_passed": gate_passed,
        "gate_reason": gate_reason,
        "evidence_as_of": evidence_as_of,
        "latest_file_update_utc": latest_update.isoformat(),
        "age_days": age_days,
        "canonical_command": canonical_command,
        "docs": [path.relative_to(project_dir).as_posix() for path in docs],
        "runner_candidates": [
            path.relative_to(project_dir).as_posix() for path in runners
        ],
        "artifact_candidates": [
            path.relative_to(project_dir).as_posix() for path in artifacts
        ],
        "evidence_checks": checks,
        "evidence_coverage_score": coverage_score,
        "risk_flags": risk_flags,
        "blockers": blockers,
        "source_boundaries": source_boundaries,
        "recommended_action": action,
    }


def _render_html(payload: dict[str, Any]) -> str:
    projects = payload["projects"]
    action_counts = Counter(project["recommended_action"] for project in projects)
    verdict_counts = Counter(project["verdict"] for project in projects)
    managed = sum(1 for project in projects if project["managed"])
    rows = []
    for project in projects:
        risks = "<br>".join(html.escape(item) for item in project["risk_flags"][:4])
        runners = "<br>".join(
            f"<code>{html.escape(item)}</code>"
            for item in project["runner_candidates"][:3]
        )
        evidence = project["evidence_coverage_score"]
        css_class = "low" if evidence < 45 else "mid" if evidence < 75 else "high"
        rows.append(
            "<tr>"
            f"<td><strong>{html.escape(project['project'])}</strong>"
            f"<br><span class='muted'>{html.escape(project['project_type'])}</span></td>"
            f"<td>{html.escape(project['verdict'])}</td>"
            f"<td><span class='score {css_class}'>{evidence}</span></td>"
            f"<td>{html.escape(project['recommended_action'])}</td>"
            f"<td>{runners or '<span class=\"muted\">none found</span>'}</td>"
            f"<td>{risks or '<span class=\"ok\">no static gap found</span>'}</td>"
            "</tr>"
        )

    action_bars = []
    max_count = max(action_counts.values(), default=1)
    for action, count in action_counts.most_common():
        width = round(count / max_count * 100)
        action_bars.append(
            "<div class='bar-row'>"
            f"<span>{html.escape(action)}</span>"
            f"<div class='bar-track'><div class='bar-fill' style='width:{width}%'></div></div>"
            f"<strong>{count}</strong>"
            "</div>"
        )

    verdict_summary = ", ".join(
        f"{html.escape(key)}: {value}" for key, value in verdict_counts.most_common()
    )
    generated = html.escape(payload["generated_at"])
    return f"""<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Trading Research Review Inventory</title>
  <style>
    :root {{ --ink:#17202a; --muted:#667085; --paper:#fffdf7; --line:#ddd4c4;
      --green:#26734d; --amber:#b26a00; --red:#a33636; --blue:#175c72; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; color:var(--ink); background:
      radial-gradient(circle at 90% 0,#d9eee6 0,transparent 28%),
      linear-gradient(180deg,#f6f0e4,#eee5d5);
      font-family:"Segoe UI","Microsoft JhengHei UI",sans-serif; }}
    main {{ max-width:1500px; margin:auto; padding:28px 20px 48px; }}
    header,.card {{ background:rgba(255,253,247,.95); border:1px solid var(--line);
      border-radius:18px; box-shadow:0 14px 34px rgba(69,55,34,.08); }}
    header {{ padding:26px; margin-bottom:18px; }}
    h1,h2 {{ margin:0 0 10px; }}
    p {{ line-height:1.55; }}
    .muted {{ color:var(--muted); font-size:13px; }}
    .ok {{ color:var(--green); }}
    .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr));
      gap:14px; margin-top:18px; }}
    .kpi {{ padding:16px; border:1px solid var(--line); border-radius:14px; background:#fffaf0; }}
    .kpi strong {{ display:block; font-size:28px; }}
    .card {{ padding:22px; margin-bottom:18px; overflow:auto; }}
    .bar-row {{ display:grid; grid-template-columns:230px 1fr 36px; gap:12px;
      align-items:center; margin:9px 0; font-size:13px; }}
    .bar-track {{ height:13px; background:#e8dfd2; border-radius:9px; overflow:hidden; }}
    .bar-fill {{ height:100%; background:linear-gradient(90deg,var(--blue),#49a078); }}
    table {{ width:100%; border-collapse:collapse; min-width:1150px; font-size:13px; }}
    th,td {{ padding:10px 9px; border-bottom:1px solid #e8dfd2; text-align:left; vertical-align:top; }}
    th {{ position:sticky; top:0; background:#f6efe3; }}
    code {{ background:#efe6d8; padding:2px 5px; border-radius:5px; }}
    .score {{ display:inline-flex; width:42px; height:30px; border-radius:9px;
      align-items:center; justify-content:center; font-weight:700; color:white; }}
    .score.low {{ background:var(--red); }} .score.mid {{ background:var(--amber); }}
    .score.high {{ background:var(--green); }}
  </style>
</head>
<body><main>
  <header>
    <h1>全量策略與回測研究盤點</h1>
    <p>這是靜態證據盤點，不是部署或交易批准。缺少文件關鍵字表示「尚未找到證據」，
    不等同於策略必然錯誤。</p>
    <p class="muted">Generated: {generated} · Root: {html.escape(payload['research_root'])}</p>
    <div class="grid">
      <div class="kpi"><strong>{len(projects)}</strong>研究線</div>
      <div class="kpi"><strong>{managed}</strong>有 root status.json</div>
      <div class="kpi"><strong>{len(projects)-managed}</strong>未納入狀態契約</div>
      <div class="kpi"><strong>{sum(1 for p in projects if p['runner_candidates'])}</strong>找到 runner 候選</div>
    </div>
  </header>
  <section class="card">
    <h2>建議動作分布</h2>
    {''.join(action_bars)}
    <p class="muted">現有 verdict：{verdict_summary}</p>
  </section>
  <section class="card">
    <h2>逐專案審查</h2>
    <table>
      <thead><tr><th>專案</th><th>現有 verdict</th><th>證據覆蓋</th>
      <th>建議動作</th><th>Runner 候選</th><th>主要風險缺口</th></tr></thead>
      <tbody>{''.join(rows)}</tbody>
    </table>
  </section>
</main></body></html>"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--research-root",
        default=r"D:\trading\strategies\research",
    )
    parser.add_argument("--json-output", required=True)
    parser.add_argument("--html-output", required=True)
    args = parser.parse_args()

    root = Path(args.research_root).resolve()
    now = datetime.now(timezone.utc)
    projects = []
    for project_dir in sorted(root.iterdir(), key=lambda path: path.name.lower()):
        if not project_dir.is_dir() or project_dir.name in SKIP_DIRS:
            continue
        projects.append(_review_project(project_dir, now))

    projects.sort(
        key=lambda item: (
            item["recommended_action"] in {"SUPPORTING_ONLY", "DOCUMENT_OR_ARCHIVE_DECISION"},
            item["managed"],
            item["evidence_coverage_score"],
            item["project"].lower(),
        )
    )
    payload = {
        "schema_version": "1.0",
        "generated_at": now.isoformat(),
        "research_root": str(root),
        "methodology": {
            "minimum_trades": 30,
            "preferred_trades": 100,
            "minimum_years": 5,
            "preferred_years": 10,
            "required_review_dimensions": list(EVIDENCE_CHECKS),
            "note": "Static discovery only; project artifacts must be inspected before final verdict.",
        },
        "summary": {
            "total": len(projects),
            "managed": sum(1 for item in projects if item["managed"]),
            "with_runner_candidates": sum(
                1 for item in projects if item["runner_candidates"]
            ),
            "actions": dict(
                Counter(item["recommended_action"] for item in projects)
            ),
            "verdicts": dict(Counter(item["verdict"] for item in projects)),
        },
        "projects": projects,
    }

    json_output = Path(args.json_output)
    html_output = Path(args.html_output)
    json_output.parent.mkdir(parents=True, exist_ok=True)
    html_output.parent.mkdir(parents=True, exist_ok=True)
    json_output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    html_output.write_text(_render_html(payload), encoding="utf-8")
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
