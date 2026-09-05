"""Deterministic flat-YAML Markdown rendering for formal event versions."""

import json

from ai_intel.domain.models import ArchiveCandidate


def _yaml_scalar(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def render_archive(candidate: ArchiveCandidate) -> str:
    published_at = min(item.published_at for item in candidate.evidence).isoformat()
    properties: tuple[tuple[str, object], ...] = (
        ("event_id", candidate.event_id),
        ("version_no", candidate.version_no),
        ("primary_topic", candidate.primary_topic),
        ("source_ids", list(candidate.source_ids)),
        ("published_at", published_at),
        ("quality_score", candidate.score.total),
        ("score_version", candidate.score.config_version),
        ("content_hash", candidate.content_hash),
        ("generated", True),
        ("do_not_edit", True),
    )
    frontmatter = "\n".join(f"{key}: {_yaml_scalar(value)}" for key, value in properties)
    sources = "\n".join(
        f"- [{item.source_id}]({item.url}) — {item.viewpoint}" for item in candidate.evidence
    )
    return (
        f"---\n{frontmatter}\n---\n\n"
        f"# {candidate.canonical_title}\n\n"
        f"## 中文摘要\n\n{candidate.summary}\n\n"
        f"## 正文\n\n{candidate.content}\n\n"
        f"## 来源与观点\n\n{sources}\n"
    )
