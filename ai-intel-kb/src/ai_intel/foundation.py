"""Local runtime composition with migrations and startup recovery."""

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import Engine, text

from ai_intel.config import Settings
from ai_intel.infrastructure.archive.recovery import ArchiveRecovery
from ai_intel.infrastructure.db.engine import create_sqlite_engine
from ai_intel.infrastructure.db.event_repository import SQLiteEventRepository
from ai_intel.infrastructure.db.intelligence_repository import SQLiteIntelligenceRepository
from ai_intel.infrastructure.db.migrations import upgrade_database
from ai_intel.infrastructure.db.phase7_repository import Phase7Repository
from ai_intel.infrastructure.db.pipeline_repository import Phase6Repository
from ai_intel.infrastructure.db.repository import SQLiteArchiveRepository
from ai_intel.infrastructure.db.source_repository import SQLiteSourceRepository

RUNTIME_SUBDIRECTORIES = (
    "raw",
    "archive",
    "digests",
    "manual-inbox",
    "vault-view",
    "quarantine",
)


@dataclass(frozen=True, slots=True)
class RuntimeContext:
    """Resources owned by one application process."""

    data_dir: Path
    database_path: Path
    engine: Engine
    repository: SQLiteArchiveRepository
    source_repository: SQLiteSourceRepository
    event_repository: SQLiteEventRepository
    intelligence_repository: SQLiteIntelligenceRepository
    phase6_repository: Phase6Repository
    phase7_repository: Phase7Repository


def initialize_runtime(settings: Settings) -> RuntimeContext:
    """Create boundaries, migrate SQLite and recover interrupted local commits."""

    data_dir = settings.data_dir.resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    for name in RUNTIME_SUBDIRECTORIES:
        (data_dir / name).mkdir(exist_ok=True)

    database_path = data_dir / "app.db"
    upgrade_database(database_path)
    engine = create_sqlite_engine(database_path)
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))

    repository = SQLiteArchiveRepository(engine, data_dir)
    source_repository = SQLiteSourceRepository(engine, data_dir)
    event_repository = SQLiteEventRepository(engine, data_dir)
    intelligence_repository = SQLiteIntelligenceRepository(engine, data_dir)
    phase6_repository = Phase6Repository(engine, data_dir)
    phase7_repository = Phase7Repository(engine)
    ArchiveRecovery(
        data_dir,
        repository,
        source_repository.list_collected_paths,
    ).recover()
    return RuntimeContext(
        data_dir=data_dir,
        database_path=database_path,
        engine=engine,
        repository=repository,
        source_repository=source_repository,
        event_repository=event_repository,
        intelligence_repository=intelligence_repository,
        phase6_repository=phase6_repository,
        phase7_repository=phase7_repository,
    )


def close_runtime(runtime: RuntimeContext) -> None:
    """Release process-owned foundation resources."""

    runtime.engine.dispose()
