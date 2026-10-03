"""Consistent SQLite backup, optionally selected by DRILLING_DB."""
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

source=Path(os.environ.get('DRILLING_DB',Path(__file__).resolve().parent.parent/'drilling.db'))
if not source.exists(): raise SystemExit('Database belum ditemukan')
destination=Path(sys.argv[1]) if len(sys.argv)>1 else source.parent/'backups'/f'drilling-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}.db'
destination.parent.mkdir(parents=True,exist_ok=True)
if source.resolve()==destination.resolve(): raise SystemExit('Tujuan backup harus berbeda')
with sqlite3.connect(source) as original,sqlite3.connect(destination) as backup:
    original.backup(backup)
    integrity=backup.execute('PRAGMA integrity_check').fetchone()[0]
    if integrity!='ok':raise SystemExit('Backup gagal verifikasi integritas')
print(destination)
