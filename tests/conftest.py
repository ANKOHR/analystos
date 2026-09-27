from __future__ import annotations

import tempfile
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEMP_ROOT = PROJECT_ROOT / ".test-tmp"


@pytest.fixture
def project_temp_dir():
    TEMP_ROOT.mkdir(exist_ok=True)
    temporary = tempfile.TemporaryDirectory(dir=TEMP_ROOT)
    try:
        yield Path(temporary.name)
    finally:
        temporary.cleanup()
