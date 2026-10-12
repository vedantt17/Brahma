"""Check the serverless entrypoint and writable storage selection in a fresh process."""

import json
import os
from pathlib import Path
import subprocess
import sys


def test_vercel_entrypoint_uses_ephemeral_storage_and_demo_mode(tmp_path):
    root = Path(__file__).resolve().parents[1]
    env = {k: v for k, v in os.environ.items()
           if k not in {"DATABASE_URL", "PUBLIC_DEMO", "TMPDIR", "VERCEL"}}
    env.update(VERCEL="1", TMPDIR=str(tmp_path))
    script = (
        "import json; from main import app; from app.config import DATA_DIR, settings; "
        "print(json.dumps({'title':app.title,'data_dir':str(DATA_DIR),"
        "'database_url':settings.database_url,'public_demo':settings.public_demo}))"
    )
    result = subprocess.run([sys.executable, "-c", script], cwd=root, env=env,
                            check=True, capture_output=True, text=True, timeout=20)
    data = json.loads(result.stdout)
    assert data["title"] == "Brahma API"
    assert data["public_demo"] is True
    assert data["data_dir"].startswith(str(tmp_path))
    assert data["database_url"].startswith("sqlite+aiosqlite:////")
    assert str(root / "data") not in data["database_url"]
