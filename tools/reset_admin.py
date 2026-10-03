import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
"""Offline reset for an existing admin account. Stop the server before running."""
import getpass
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from auth import event, hash_password

ROOT = Path(__file__).resolve().parent.parent

def reset_admin(db_path, password, *, allow_short=False):
    source = Path(db_path).resolve()
    if not source.is_file():
        raise ValueError(f'Database tidak ditemukan: {source}')
    password_hash = hash_password(password, allow_short=allow_short)
    backup_dir = source.parent / 'backups'
    backup_dir.mkdir(mode=0o700, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f')
    backup_path = backup_dir / f'pre-admin-reset-{stamp}.db'
    with sqlite3.connect(f'{source.as_uri()}?mode=rw', uri=True) as db:
        db.row_factory = sqlite3.Row
        row = db.execute("SELECT id FROM users WHERE username='admin' AND role='admin'").fetchone()
        if not row:
            raise ValueError('Akun admin yang ada tidak ditemukan. Database tidak diubah.')
        with sqlite3.connect(backup_path) as backup:
            db.backup(backup)
            if backup.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValueError('Backup gagal diverifikasi. Database tidak diubah.')
        os.chmod(backup_path, 0o600)
        db.execute('BEGIN IMMEDIATE')
        db.execute('UPDATE users SET password_hash=?,active=1 WHERE id=?', (password_hash, row['id']))
        db.execute('DELETE FROM sessions WHERE user_id=?', (row['id'],))
        event(db, 'admin', 'PASSWORD_RESET_OFFLINE')
    return backup_path

def main():
    path = Path(os.environ.get('DRILLING_DB') or ROOT / 'drilling.db')
    print(f'Database: {path.resolve()}')
    print('Hentikan server aplikasi dengan Ctrl+C sebelum melanjutkan.')
    one = getpass.getpass('Password baru admin (minimal 12 karakter): ')
    two = getpass.getpass('Ulangi password baru: ')
    if one != two:
        raise SystemExit('Password tidak cocok. Database tidak diubah.')
    try:
        backup = reset_admin(path, one)
    except (ValueError, sqlite3.Error, OSError) as exc:
        raise SystemExit(str(exc))
    print(f'Password admin berhasil direset. Backup sebelum reset: {backup}')
    print('Semua sesi admin lama dicabut. Jalankan kembali python app.py lalu login sebagai admin.')

if __name__ == '__main__':
    main()
