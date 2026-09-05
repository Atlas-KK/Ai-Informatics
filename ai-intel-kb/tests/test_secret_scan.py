import subprocess
from pathlib import Path


def test_secret_scan_rejects_a_fake_secret_without_echoing_it(tmp_path: Path) -> None:
    fake_secret = "sk-" + ("x" * 24)
    (tmp_path / "fixture.py").write_text(f'API_KEY="{fake_secret}"\n', encoding="utf-8")
    script = Path(__file__).parents[1] / "scripts" / "secret-scan.ps1"

    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-ScanRoot",
            str(tmp_path),
        ],
        capture_output=True,
        check=False,
    )

    output = (result.stdout or b"") + (result.stderr or b"")
    assert result.returncode != 0
    assert b"Potential secret material detected" in output
    assert fake_secret.encode("ascii") not in output
