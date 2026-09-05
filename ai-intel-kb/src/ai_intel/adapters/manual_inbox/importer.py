"""Strict local Markdown ingestion into the same pre-processing queue as collectors."""

from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from urllib.parse import urlsplit

from ai_intel.domain.source import (
    CollectedItem,
    CollectionFailure,
    CollectionStage,
    CollectionStatus,
    SourceType,
    effective_publication,
    truncate_for_model,
)
from ai_intel.infrastructure.db.source_repository import SQLiteSourceRepository


@dataclass(frozen=True, slots=True)
class ManualImportResult:
    status: CollectionStatus
    snapshot_id: str | None
    file_hash: str
    failure: CollectionFailure | None = None


class ManualInboxImporter:
    def __init__(self, data_dir: Path, repository: SQLiteSourceRepository) -> None:
        self.data_dir = data_dir.resolve()
        self.inbox = self.data_dir / "manual-inbox"
        self.repository = repository

    def import_file(self, path: Path, *, imported_at: datetime) -> ManualImportResult:
        candidate = path.resolve()
        if candidate.parent != self.inbox:
            raise ValueError("manual import file must be directly inside data/manual-inbox")
        original = candidate.read_text(encoding="utf-8")
        file_hash = sha256(original.encode("utf-8")).hexdigest()
        existing = self.repository.get_manual_import(file_hash)
        if existing is not None and existing["status"] != "FAILED":
            return ManualImportResult(CollectionStatus.DUPLICATE, None, file_hash)
        try:
            metadata, body = self._parse(original)
            title = metadata["title"]
            url = metadata["source_url"]
            parsed_url = urlsplit(url)
            if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
                raise ValueError("source_url must be an absolute HTTP(S) URL")
            published_text = metadata.get("published_at")
            published_at = (
                None if published_text is None else datetime.fromisoformat(published_text)
            )
            published, unknown = effective_publication(published_at, imported_at)
            item = CollectedItem(
                external_id=file_hash,
                source_id="manual-inbox",
                source_type=SourceType.MANUAL_INBOX,
                title=title,
                url=url,
                author=metadata.get("author"),
                published_at=published,
                first_seen_at=imported_at.astimezone(UTC),
                published_at_unknown=unknown,
                raw_content=original,
                model_input=truncate_for_model(original, None),
                status=CollectionStatus.COLLECTED,
                metadata={"manual_file_hash": file_hash, "body": body},
            )
            snapshot_id = self.repository.save_item(None, item)
            if snapshot_id is None:
                return ManualImportResult(CollectionStatus.DUPLICATE, None, file_hash)
            self.repository.record_manual_import(
                file_hash=file_hash,
                file_path=candidate.relative_to(self.data_dir).as_posix(),
                status="IMPORTED",
                error=None,
                retry_count=0,
                snapshot_id=snapshot_id,
                imported_at=imported_at,
            )
            return ManualImportResult(CollectionStatus.COLLECTED, snapshot_id, file_hash)
        except (KeyError, ValueError) as exc:
            retry_count = 0 if existing is None else int(existing["retry_count"]) + 1
            if existing is None:
                self.repository.record_manual_import(
                    file_hash=file_hash,
                    file_path=candidate.relative_to(self.data_dir).as_posix(),
                    status="FAILED",
                    error=str(exc),
                    retry_count=retry_count,
                    snapshot_id=None,
                    imported_at=imported_at,
                )
            else:
                self.repository.update_manual_failure(
                    file_hash=file_hash,
                    error=str(exc),
                    retry_count=retry_count,
                    imported_at=imported_at,
                )
            failure = CollectionFailure(
                None, CollectionStage.IMPORT, str(exc), imported_at, retry_count
            )
            self.repository.save_failure(None, failure)
            return ManualImportResult(CollectionStatus.FAILED, None, file_hash, failure)

    @staticmethod
    def _parse(content: str) -> tuple[dict[str, str], str]:
        lines = content.splitlines()
        if len(lines) < 4 or lines[0].strip() != "---":
            raise ValueError("manual Markdown requires YAML-style front matter")
        try:
            end = lines.index("---", 1)
        except ValueError as exc:
            raise ValueError("manual Markdown front matter is not closed") from exc
        metadata: dict[str, str] = {}
        for line in lines[1:end]:
            key, separator, value = line.partition(":")
            if not separator or not key.strip() or not value.strip():
                raise ValueError("manual Markdown front matter contains an invalid field")
            metadata[key.strip()] = value.strip()
        for required in ("title", "source_url"):
            if not metadata.get(required):
                raise ValueError(f"manual Markdown requires {required}")
        body = "\n".join(lines[end + 1 :]).strip()
        if not body:
            raise ValueError("manual Markdown body is required")
        return metadata, body
