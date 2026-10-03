"""
Startup script untuk cloud deployment (Railway / Render / Fly.io).
- Jika DRILLING_DB env var diset ke path lain (misal /data/drilling.db),
  script akan menyalin seed DB ke sana jika belum ada.
- Jika tidak diset, app langsung pakai drilling.db di folder project.
"""
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SEED_DB = ROOT / 'drilling.db'

DB_ENV = os.environ.get('DRILLING_DB', '')
DB_PATH = Path(DB_ENV) if DB_ENV else None

def main():
    if DB_PATH and DB_PATH != SEED_DB:
        print(f"[start.py] Mode persistent volume: {DB_PATH}")
        if not DB_PATH.exists():
            DB_PATH.parent.mkdir(parents=True, exist_ok=True)
            if SEED_DB.exists():
                print(f"[start.py] Volume kosong, menyalin seed database...")
                try:
                    with sqlite3.connect(f'{SEED_DB.resolve().as_uri()}?mode=ro',uri=True) as source,sqlite3.connect(DB_PATH) as destination:
                        source.backup(destination)
                        if destination.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
                            raise RuntimeError('Integritas seed database gagal')
                        if destination.execute('PRAGMA foreign_key_check').fetchone():
                            raise RuntimeError('Relasi seed database gagal')
                except Exception:
                    DB_PATH.unlink(missing_ok=True)
                    raise
                print(f"[start.py] Seed database berhasil disalin ({DB_PATH.stat().st_size / 1024:.0f} KB)")
            else:
                print(f"[start.py] Tidak ada seed DB, database baru akan dibuat.")
        else:
            size_mb = DB_PATH.stat().st_size / 1024 / 1024
            print(f"[start.py] Database ditemukan ({size_mb:.2f} MB), menggunakan data existing.")
    else:
        print(f"[start.py] Mode lokal/ephemeral: menggunakan {SEED_DB}")

    print("[start.py] Memulai aplikasi...")
    result = subprocess.run([sys.executable, str(ROOT / 'app.py')], env=os.environ)
    sys.exit(result.returncode)

if __name__ == '__main__':
    main()
