"""Admin-only rig lifecycle. Keep rig IDs and linked operational history stable."""
import json
import math
import re
from app import connect, now


def _linked(db, rig_id):
    return any(db.execute(f'SELECT 1 FROM {table} WHERE rig_id=? LIMIT 1', (rig_id,)).fetchone()
               for table in ('reports', 'equipment', 'core_boxes', 'stock_moves', 'expenses',
                             'period_targets', 'target_revisions'))


def inventory():
    with connect() as db:
        rigs = [dict(row, has_history=bool(_linked(db, row['id'])))
                for row in db.execute('SELECT * FROM rigs ORDER BY active DESC,code COLLATE NOCASE').fetchall()]
        history = [dict(row) for row in db.execute('''SELECT h.id,h.rig_id,h.action,h.actor,h.at,
          h.before_json,h.after_json FROM rig_revisions h ORDER BY h.id DESC LIMIT 100''')]
    return {'rigs': rigs, 'history': history}


def _code(value):
    code = str(value or '').strip().upper()
    if not re.fullmatch(r'[A-Z0-9][A-Z0-9._-]{0,31}', code):
        raise ValueError('Kode rig harus 1–32 karakter: huruf, angka, titik, garis bawah, atau tanda hubung')
    return code


def _location(value):
    location = str(value or '').strip()
    if not location or len(location) > 120:
        raise ValueError('Lokasi rig wajib diisi (maksimal 120 karakter)')
    return location


def _unique(db, code, exclude=None):
    row = db.execute('SELECT id FROM rigs WHERE code=? COLLATE NOCASE', (code,)).fetchone()
    if row and row['id'] != exclude: raise ValueError('Kode rig sudah dipakai')


def _revision(db, rig_id, action, before, after, actor):
    db.execute('''INSERT INTO rig_revisions(rig_id,action,before_json,after_json,actor,at)
                  VALUES(?,?,?,?,?,?)''', (rig_id,action,
                  json.dumps(before,ensure_ascii=False) if before else None,
                  json.dumps(after,ensure_ascii=False),actor,now()))


def create(data, actor):
    code = _code(data.get('code'))
    location = _location(data.get('location'))
    try: target = float(data.get('target_m'))
    except (TypeError,ValueError): raise ValueError('Target dasar harian harus angka')
    if not math.isfinite(target) or target < 0 or target > 1_000_000:
        raise ValueError('Target dasar harian di luar rentang 0–1.000.000 m')
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        _unique(db,code)
        rig_id = db.execute('INSERT INTO rigs(code,location,target_m,active) VALUES(?,?,?,1)',
                            (code,location,target)).lastrowid
        for period,value in (('Daily',target),('Monthly',0),('Yearly',0)):
            db.execute('''INSERT INTO rig_targets(rig_id,period,target_m,updated_by,updated_at)
                          VALUES(?,?,?,?,?)''',(rig_id,period,value,actor,now()))
            db.execute('''INSERT INTO period_target_baselines(rig_id,period,target_m,captured_at)
                          VALUES(?,?,?,?)''',(rig_id,period,value,now()))
        after={'id':rig_id,'code':code,'location':location,'target_m':target,'active':1}
        _revision(db,rig_id,'CREATED',None,after,actor)
    return after


def update(data, actor):
    try: rig_id=int(data.get('id'))
    except (TypeError,ValueError): raise ValueError('ID rig tidak valid')
    if rig_id <= 0: raise ValueError('ID rig tidak valid')
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT * FROM rigs WHERE id=?',(rig_id,)).fetchone()
        if not row: raise ValueError('Rig tidak ditemukan')
        before=dict(row)
        code=_code(data['code']) if 'code' in data else row['code']
        location=_location(data.get('location',row['location']))
        if code != row['code'] or location != row['location']:
            _unique(db,code,rig_id)
        active=row['active']
        if 'active' in data:
            try: active=int(data['active'])
            except (TypeError,ValueError): raise ValueError('Status rig tidak valid')
            if active not in (0,1): raise ValueError('Status rig tidak valid')
        if not active and row['active'] and db.execute('SELECT COUNT(*) FROM rigs WHERE active=1').fetchone()[0] <= 1:
            raise ValueError('Aktifkan atau tambah rig lain sebelum menonaktifkan rig terakhir')
        after={**before,'code':code,'location':location,'active':active}
        if after == before: raise ValueError('Belum ada perubahan rig')
        db.execute('UPDATE rigs SET code=?,location=?,active=? WHERE id=?',(code,location,active,rig_id))
        _revision(db,rig_id,'DEACTIVATED' if not active else 'REACTIVATED' if not row['active'] else 'UPDATED',before,after,actor)
    return after
