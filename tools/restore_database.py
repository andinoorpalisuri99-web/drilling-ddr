"""Install the verified recovery for the uploaded Drilling r.4 database.

This is deliberately limited to the supplied damaged database. Unknown or newer
files are left untouched. No passwords or dependencies are required.
"""
import argparse
import hashlib
import os
from pathlib import Path
import shutil
import socket
import sqlite3
import sys
import uuid
from datetime import datetime

DAMAGED_SHA256 = '68629572b5ddb7412585074b052df0bf281419bebbd1e0dc22a27c9966b9f8c1'
RECOVERED_SHA256 = 'e8ac91917d874716c33d7a173a53c7577695553e4c996c81221cd9bdd10d682b'
PACKAGE = Path(__file__).resolve().parent.parent


def digest(path):
    with path.open('rb') as stream:
        checksum = hashlib.sha256()
        for chunk in iter(lambda: stream.read(262144), b''):
            checksum.update(chunk)
        return checksum.hexdigest()


def validate(path):
    connection = sqlite3.connect(path.resolve().as_uri() + '?mode=ro&immutable=1', uri=True)
    try:
        if connection.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
            raise RuntimeError('Pemeriksaan integritas database hasil gagal.')
        if connection.execute('PRAGMA foreign_key_check').fetchall():
            raise RuntimeError('Hubungan data pada database hasil tidak valid.')
        if connection.execute('SELECT COUNT(*) FROM reports').fetchone()[0] != 14:
            raise RuntimeError('Jumlah DDR hasil tidak sesuai.')
    finally:
        connection.close()


def restore(project):
    project = project.resolve()
    payload = PACKAGE / 'recovery' / 'drilling-v088-recovered.db'
    database = project / 'drilling.db'
    if not (project / 'app.py').is_file() or not database.is_file():
        raise RuntimeError('Letakkan paket ini di folder project yang berisi app.py dan drilling.db.')
    external = os.environ.get('DRILLING_DB')
    if external and Path(external).resolve() != database:
        raise RuntimeError('DRILLING_DB menunjuk database lain. Pemulihan dibatalkan; tidak ada data ditimpa.')
    if not payload.is_file() or digest(payload) != RECOVERED_SHA256:
        raise RuntimeError('File pemulihan tidak lengkap/berubah. Ekstrak kembali paket perbaikan.')
    validate(payload)
    if digest(database) == RECOVERED_SHA256:
        validate(database)
        print('Database sudah dipulihkan. 14 DDR tersedia. Tidak ada file diganti.')
        return
    if digest(database) != DAMAGED_SHA256:
        raise RuntimeError('Database saat ini berbeda dari file yang sudah diperiksa. Untuk menjaga input terbaru, tidak ada file ditimpa. Kirim arsip folder saat ini untuk diperiksa.')
    host = os.environ.get('DRILLING_HOST', '127.0.0.1')
    if host == '0.0.0.0':
        host = '127.0.0.1'
    port = int(os.environ.get('DRILLING_PORT', '8765'))
    with socket.socket() as probe:
        probe.settimeout(1)
        if probe.connect_ex((host, port)) == 0:
            raise RuntimeError('Aplikasi masih berjalan. Hentikan terminal lama dengan Ctrl+C, lalu ulangi.')
    wal = Path(str(database) + '-wal')
    shm = Path(str(database) + '-shm')
    if wal.exists() and wal.stat().st_size:
        raise RuntimeError('Ada file WAL yang tidak ada pada arsip yang diperiksa. File mungkin berisi input tambahan. Tidak ada data ditimpa; kirim folder beserta WAL untuk diperiksa.')
    sources = [p for p in (database, wal, shm) if p.exists()]
    source_hashes = {p.name: digest(p) for p in sources}
    backup = project / 'backups' / ('pemulihan-' + datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:6])
    backup.mkdir(parents=True)
    for source in sources:
        shutil.copy2(source, backup / source.name)
        if digest(backup / source.name) != source_hashes[source.name]:
            raise RuntimeError('Verifikasi backup gagal. Database aktif belum diganti.')
    stage = project / ('recovered-stage-' + uuid.uuid4().hex + '.db')
    moved = []
    installed = False
    try:
        with payload.open('rb') as source, stage.open('xb') as target:
            shutil.copyfileobj(source, target)
            target.flush()
            os.fsync(target.fileno())
        if digest(stage) != RECOVERED_SHA256:
            raise RuntimeError('Salinan pemulihan tidak cocok. Database belum diganti.')
        validate(stage)
        for source in sources:
            if not source.exists() or digest(source) != source_hashes[source.name]:
                raise RuntimeError('File database berubah selama backup. Hentikan semua aplikasi dan ulangi.')
        if wal.exists() and wal.stat().st_size:
            raise RuntimeError('WAL baru muncul. Tidak ada database diganti.')
        for sidecar in (wal, shm):
            if sidecar.exists():
                retired = backup / ('retired-' + sidecar.name)
                os.replace(sidecar, retired)
                moved.append((sidecar, retired))
        os.replace(stage, database)
        installed = True
        validate(database)
    except Exception:
        if installed:
            rollback = project / ('rollback-' + uuid.uuid4().hex + '.db')
            shutil.copy2(backup / database.name, rollback)
            os.replace(rollback, database)
        for active, retired in reversed(moved):
            if retired.exists():
                os.replace(retired, active)
        raise
    finally:
        if stage.exists():
            stage.unlink()
    print('BERHASIL: database dipulihkan. 14 DDR, 5 rig, akun dan password tetap.')
    print('Cadangan database sebelumnya: ' + str(backup))
    print('Login kembali dengan akun sebelumnya. Refresh browser dengan Ctrl+F5.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Pemulihan database MMS Drilling yang telah diperiksa')
    parser.add_argument('--project-dir', type=Path, default=PACKAGE)
    arguments = parser.parse_args()
    try:
        restore(arguments.project_dir)
    except Exception as error:
        print('PEMULIHAN DIHENTIKAN: ' + str(error), file=sys.stderr)
        sys.exit(1)
