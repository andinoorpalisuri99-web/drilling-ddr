"""Phase 2-4 data operations for the local prototype."""
import json
import sqlite3
import re
from identities import issue,retire,resolve,token_for
from datetime import datetime, timezone
from app import connect, now

def initialize():
    with connect() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS equipment(id INTEGER PRIMARY KEY, serial TEXT UNIQUE NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('Bit','Rod','Rig component')), brand TEXT NOT NULL DEFAULT '', rig_id INTEGER REFERENCES rigs(id), installed_depth REAL NOT NULL DEFAULT 0 CHECK(installed_depth>=0), retired_depth REAL, max_life_m REAL CHECK(max_life_m>0), unit_cost REAL NOT NULL DEFAULT 0 CHECK(unit_cost>=0), status TEXT NOT NULL DEFAULT 'Active' CHECK(status IN ('Active','Retired')), created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS materials(id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL, unit TEXT NOT NULL, reorder_qty REAL NOT NULL DEFAULT 0 CHECK(reorder_qty>=0), unit_cost REAL NOT NULL DEFAULT 0 CHECK(unit_cost>=0));
        CREATE TABLE IF NOT EXISTS stock_moves(id INTEGER PRIMARY KEY, material_id INTEGER NOT NULL REFERENCES materials(id), rig_id INTEGER REFERENCES rigs(id), qty REAL NOT NULL CHECK(qty<>0), reason TEXT NOT NULL, reference TEXT NOT NULL DEFAULT '', actor TEXT NOT NULL, at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS core_boxes(id INTEGER PRIMARY KEY, code TEXT UNIQUE NOT NULL, rig_id INTEGER NOT NULL REFERENCES rigs(id), hole_code TEXT NOT NULL, from_depth REAL NOT NULL, to_depth REAL NOT NULL CHECK(to_depth>from_depth), recovery_m REAL NOT NULL CHECK(recovery_m>=0), lithology TEXT NOT NULL DEFAULT '', rqd_pct REAL CHECK(rqd_pct>=0 AND rqd_pct<=100), status TEXT NOT NULL DEFAULT 'At rig', created_at TEXT NOT NULL, CHECK(recovery_m<=to_depth-from_depth));
        CREATE TABLE IF NOT EXISTS samples(id INTEGER PRIMARY KEY, code TEXT UNIQUE NOT NULL, box_id INTEGER NOT NULL REFERENCES core_boxes(id), from_depth REAL NOT NULL, to_depth REAL NOT NULL CHECK(to_depth>from_depth), sample_type TEXT NOT NULL, weight_kg REAL CHECK(weight_kg>=0), qa_status TEXT NOT NULL DEFAULT 'Pending' CHECK(qa_status IN ('Pending','Accepted','Rejected')), lab_result TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS custody_events(id INTEGER PRIMARY KEY, sample_id INTEGER NOT NULL REFERENCES samples(id), stage TEXT NOT NULL CHECK(stage IN ('Collected','Packed','Logged','Dispatched','Received at lab','Archived')), from_holder TEXT NOT NULL, to_holder TEXT NOT NULL, actor TEXT NOT NULL, note TEXT NOT NULL DEFAULT '', at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS programs(id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL, contractor TEXT NOT NULL DEFAULT '', budget REAL NOT NULL DEFAULT 0 CHECK(budget>=0), target_m REAL NOT NULL DEFAULT 0 CHECK(target_m>=0), active INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS expenses(id INTEGER PRIMARY KEY, program_id INTEGER NOT NULL REFERENCES programs(id), rig_id INTEGER REFERENCES rigs(id), work_date TEXT NOT NULL, category TEXT NOT NULL CHECK(category IN ('Drilling','Equipment','Consumables','Contractor','Other')), amount REAL NOT NULL CHECK(amount>=0), reference TEXT NOT NULL, note TEXT NOT NULL DEFAULT '', actor TEXT NOT NULL, at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS invoices(id INTEGER PRIMARY KEY, program_id INTEGER NOT NULL REFERENCES programs(id), reference TEXT UNIQUE NOT NULL, billed_m REAL NOT NULL CHECK(billed_m>=0), billed_amount REAL NOT NULL CHECK(billed_amount>=0), status TEXT NOT NULL DEFAULT 'Pending' CHECK(status IN ('Pending','Matched','Variance')), note TEXT NOT NULL DEFAULT '', at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS activity(id INTEGER PRIMARY KEY, entity TEXT NOT NULL, entity_id INTEGER NOT NULL, action TEXT NOT NULL, actor TEXT NOT NULL, detail TEXT NOT NULL, at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS rig_targets(id INTEGER PRIMARY KEY, rig_id INTEGER NOT NULL REFERENCES rigs(id), period TEXT NOT NULL CHECK(period IN ('Daily','Monthly','Yearly')), target_m REAL NOT NULL CHECK(target_m>=0), updated_by TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(rig_id,period));
        CREATE TABLE IF NOT EXISTS target_revisions(id INTEGER PRIMARY KEY, rig_id INTEGER NOT NULL REFERENCES rigs(id), period TEXT NOT NULL CHECK(period IN ('Daily','Monthly','Yearly')), old_target REAL NOT NULL CHECK(old_target>=0), new_target REAL NOT NULL CHECK(new_target>=0), reason TEXT NOT NULL, actor TEXT NOT NULL, at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS deletion_log(id INTEGER PRIMARY KEY, entity TEXT NOT NULL, entity_id INTEGER NOT NULL, record_key TEXT NOT NULL, snapshot TEXT NOT NULL, reason TEXT NOT NULL, actor TEXT NOT NULL, at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS qa_revisions(id INTEGER PRIMARY KEY,sample_id INTEGER NOT NULL REFERENCES samples(id),old_status TEXT NOT NULL,new_status TEXT NOT NULL,old_result TEXT NOT NULL,new_result TEXT NOT NULL,reason TEXT NOT NULL,actor TEXT NOT NULL,at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS app_state(key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL);
        ''')
        if 'equipment_id' not in [x['name'] for x in db.execute('PRAGMA table_info(reports)')]:
            db.execute('ALTER TABLE reports ADD COLUMN equipment_id INTEGER REFERENCES equipment(id)')
        db.execute('CREATE INDEX IF NOT EXISTS idx_reports_equipment_status ON reports(equipment_id,status)')
        for rig in db.execute('SELECT id,target_m FROM rigs'):
            for period,value in (('Daily',rig['target_m']),('Monthly',0),('Yearly',0)):
                db.execute('INSERT OR IGNORE INTO rig_targets(rig_id,period,target_m,updated_by,updated_at) VALUES(?,?,?,?,?)',(rig['id'],period,value,'system',now()))
        # Existing sample data stays intact; new installations start without fabricated transactions.

def deletion_history():
    with connect() as db:
        return [
            dict(x) for x in db.execute(
                'SELECT id,entity,entity_id,record_key,reason,actor,at FROM deletion_log ORDER BY id DESC LIMIT 300'
            )
        ]


def delete_record(entity, ident, reason, actor):
    """Delete an operational record while preserving a full audit snapshot."""
    reason = str(reason or '').strip()
    if not reason:
        raise ValueError('Alasan penghapusan wajib diisi')
    if len(reason) > 250:
        raise ValueError('Alasan penghapusan maksimal 250 karakter')
    try:
        ident = int(ident)
    except (TypeError, ValueError):
        raise ValueError('ID data tidak valid')

    aliases = {
        'stock':'stock_moves','boxes':'core_boxes','samples':'samples','custody':'custody_events',
        'programs':'programs','expenses':'expenses','invoices':'invoices','equipment':'equipment',
        'materials':'materials','reports':'reports',
    }
    table = aliases.get(entity)
    if not table:
        raise ValueError('Jenis data tidak dapat dihapus')

    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute(f'SELECT * FROM {table} WHERE id=?', (ident,)).fetchone()
        if not row:
            raise ValueError('Data tidak ditemukan atau sudah dihapus')
        record = dict(row)
        snapshot = {'record': record}
        key = str(
            record.get('code') or record.get('serial') or record.get('name') or
            record.get('reference') or ident
        )

        if entity == 'reports':
            if record['status']=='Approved':raise ValueError('DDR approved tidak dapat dihapus. Ajukan koreksi melalui proses yang disahkan.')
            snapshot['audit'] = [
                dict(x) for x in db.execute('SELECT * FROM audit WHERE report_id=? ORDER BY id', (ident,))
            ]
            snapshot['revisions']=[dict(x) for x in db.execute('SELECT * FROM report_revisions WHERE report_id=? ORDER BY id',(ident,))]
            db.execute('DELETE FROM report_revisions WHERE report_id=?',(ident,))
            key = f"{record['work_date']} / {record['shift']} / report #{ident}"
            db.execute('DELETE FROM audit WHERE report_id=?', (ident,))
        elif entity == 'equipment':
            if db.execute('SELECT 1 FROM reports WHERE equipment_id=? LIMIT 1', (ident,)).fetchone():
                raise ValueError('Equipment sudah dipakai DDR. Hapus/koreksi DDR terkait terlebih dahulu.')
        elif entity == 'materials':
            if db.execute('SELECT 1 FROM stock_moves WHERE material_id=? LIMIT 1', (ident,)).fetchone():
                raise ValueError('Material memiliki mutasi stok. Hapus mutasi terkait terlebih dahulu.')
        elif entity == 'stock':
            balance=db.execute('SELECT COALESCE(SUM(qty),0) FROM stock_moves WHERE material_id=?',(record['material_id'],)).fetchone()[0]
            if balance-record['qty'] < -0.000001:raise ValueError('Penghapusan membuat saldo stok negatif. Koreksi transaksi keluar terlebih dahulu.')
        elif entity == 'boxes':
            if db.execute('SELECT 1 FROM samples WHERE box_id=? LIMIT 1', (ident,)).fetchone():
                raise ValueError('Core box memiliki sample. Hapus sample terkait terlebih dahulu.')
        elif entity == 'samples':
            if record['qa_status']!='Pending':raise ValueError('Sample dengan keputusan QA tidak dapat dihapus. Gunakan proses koreksi yang disahkan.')
            snapshot['custody'] = [
                dict(x) for x in db.execute('SELECT * FROM custody_events WHERE sample_id=? ORDER BY id', (ident,))
            ]
            db.execute('DELETE FROM custody_events WHERE sample_id=?', (ident,))
        elif entity == 'custody':
            if record['stage'] == 'Collected':
                raise ValueError('Tahap Collected dibuat bersama sample. Hapus sample jika registrasinya salah.')
            latest = db.execute(
                'SELECT id FROM custody_events WHERE sample_id=? ORDER BY id DESC LIMIT 1',
                (record['sample_id'],),
            ).fetchone()
            if not latest or latest['id'] != ident:
                raise ValueError('Hanya custody paling terakhir yang dapat dihapus agar urutan tetap konsisten.')
        elif entity == 'programs':
            linked = (
                db.execute('SELECT 1 FROM reports WHERE program_id=? LIMIT 1', (ident,)).fetchone() or
                db.execute('SELECT 1 FROM expenses WHERE program_id=? LIMIT 1', (ident,)).fetchone() or
                db.execute('SELECT 1 FROM invoices WHERE program_id=? LIMIT 1', (ident,)).fetchone()
            )
            if linked:
                raise ValueError('Program masih memiliki DDR/biaya/invoice. Hapus atau koreksi data terkait terlebih dahulu.')

        db.execute(
            'INSERT INTO deletion_log(entity,entity_id,record_key,snapshot,reason,actor,at) VALUES(?,?,?,?,?,?,?)',
            (entity,ident,key,json.dumps(snapshot,ensure_ascii=False),reason,actor,now()),
        )
        if entity in ('boxes','samples'):retire(db,entity,ident)
        db.execute(f'DELETE FROM {table} WHERE id=?', (ident,))
        log(db,entity,ident,'DELETED',actor,{'record_key':key,'reason':reason})
        return {'ok':True,'entity':entity,'id':ident,'record_key':key}


def required(d, key):
    value = str(d.get(key,'')).strip()
    if not value: raise ValueError(f'{key} wajib diisi')
    return value

def num(d,key,default=None):
    value=d.get(key)
    if value in ('',None):
        if default is None: raise ValueError(f'{key} wajib diisi')
        return default
    result=float(value)
    if result!=result or result in (float('inf'),float('-inf')): raise ValueError(f'{key} tidak valid')
    return result

def positive(v,label,zero=True):
    if v<0 or (not zero and v==0): raise ValueError(f'{label} harus positif')
    return v

def log(db, entity, ident, action, actor, data):
    db.execute('INSERT INTO activity(entity,entity_id,action,actor,detail,at) VALUES(?,?,?,?,?,?)',(entity,ident,action,actor,json.dumps(data,ensure_ascii=False),now()))

def collection(name):
    sql={
      'equipment':'''WITH usage AS (
        SELECT e.id,
          COALESCE(SUM(CASE WHEN r.status='Approved' THEN (CASE WHEN json_extract(r.ddr_detail,'$.version')=2 THEN r.end_depth-r.start_depth ELSE MAX(0, MIN(r.end_depth,COALESCE(e.retired_depth,r.end_depth))-MAX(r.start_depth,e.installed_depth)) END) ELSE 0 END),0) AS life_m,
          COALESCE(SUM(CASE WHEN r.status='Approved' AND (CASE WHEN json_extract(r.ddr_detail,'$.version')=2 THEN r.end_depth-r.start_depth ELSE MAX(0, MIN(r.end_depth,COALESCE(e.retired_depth,r.end_depth))-MAX(r.start_depth,e.installed_depth)) END)>0 THEN 1 ELSE 0 END),0) AS ddr_count
        FROM equipment e LEFT JOIN reports r ON r.equipment_id=e.id GROUP BY e.id)
        SELECT e.*,g.code rig,u.life_m,u.ddr_count,
          CASE WHEN e.max_life_m IS NOT NULL THEN MAX(e.max_life_m-u.life_m,0) END AS remaining_life_m,
          CASE WHEN e.max_life_m IS NOT NULL AND e.max_life_m>0 THEN ROUND(u.life_m/e.max_life_m*100,1) END AS utilization_pct
        FROM equipment e LEFT JOIN rigs g ON g.id=e.rig_id JOIN usage u ON u.id=e.id ORDER BY e.id DESC''',
      'materials':'''SELECT m.*,COALESCE(SUM(s.qty),0) stock FROM materials m LEFT JOIN stock_moves s ON s.material_id=m.id GROUP BY m.id ORDER BY m.name''',
      'stock':'''SELECT s.*,m.name material,m.unit,g.code rig FROM stock_moves s JOIN materials m ON m.id=s.material_id LEFT JOIN rigs g ON g.id=s.rig_id ORDER BY s.id DESC LIMIT 500''',
      'boxes':'''SELECT b.*,g.code rig,t.token FROM core_boxes b JOIN rigs g ON g.id=b.rig_id LEFT JOIN tracking_tokens t ON t.kind='boxes' AND t.object_id=b.id AND t.active=1 ORDER BY b.id DESC''',
      'samples':'''SELECT s.*,b.code box,b.hole_code,t.token FROM samples s JOIN core_boxes b ON b.id=s.box_id LEFT JOIN tracking_tokens t ON t.kind='samples' AND t.object_id=s.id AND t.active=1 ORDER BY s.id DESC''',
      'custody':'''SELECT c.*,s.code sample FROM custody_events c JOIN samples s ON s.id=c.sample_id ORDER BY c.id DESC LIMIT 500''',
      'programs':'''SELECT p.*,COALESCE((SELECT SUM(amount) FROM expenses e WHERE e.program_id=p.id AND (e.rig_id IS NULL OR e.rig_id IN (SELECT id FROM rigs WHERE active=1))),0) spent,COALESCE((SELECT SUM(end_depth-start_depth) FROM reports r WHERE r.program_id=p.id AND r.status='Approved' AND r.rig_id IN (SELECT id FROM rigs WHERE active=1)),0) approved_m FROM programs p ORDER BY p.id DESC''',
      'expenses':'''SELECT x.*,p.name program,g.code rig FROM expenses x JOIN programs p ON p.id=x.program_id LEFT JOIN rigs g ON g.id=x.rig_id ORDER BY x.id DESC LIMIT 500''',
      'invoices':'''SELECT i.*,p.name program,COALESCE((SELECT SUM(end_depth-start_depth) FROM reports r WHERE r.program_id=i.program_id AND r.status='Approved' AND r.billing_status='Billable' AND r.rig_id IN (SELECT id FROM rigs WHERE active=1)),0) program_approved_m, i.billed_m-COALESCE((SELECT SUM(end_depth-start_depth) FROM reports r WHERE r.program_id=i.program_id AND r.status='Approved' AND r.billing_status='Billable' AND r.rig_id IN (SELECT id FROM rigs WHERE active=1)),0) meter_variance FROM invoices i JOIN programs p ON p.id=i.program_id ORDER BY i.id DESC''',
      'activity':'''SELECT * FROM activity ORDER BY id DESC LIMIT 300'''
    }.get(name)
    if sql is None: raise ValueError('Endpoint tidak tersedia')
    with connect() as db: return [dict(r) for r in db.execute(sql)]

def create(name,d):
    actor=required(d,'actor')
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        if name=='equipment':
            kind=required(d,'kind')
            if kind not in ('Bit','Rod','Rig component'): raise ValueError('Jenis alat tidak valid')
            installed=positive(num(d,'installed_depth',0),'Kedalaman')
            rig_id=int(d['rig_id']) if d.get('rig_id') else None
            cur=db.execute('INSERT INTO equipment(serial,kind,brand,rig_id,installed_depth,max_life_m,unit_cost,created_at) VALUES(?,?,?,?,?,?,?,?)',(required(d,'serial'),kind,str(d.get('brand','')).strip(),rig_id,installed,positive(num(d,'max_life_m',0),'Batas umur',False) if d.get('max_life_m') else None,positive(num(d,'unit_cost',0),'Biaya'),now()))
        elif name=='retire':
            ident=int(d['equipment_id']); depth=positive(num(d,'retired_depth'),'Kedalaman')
            row=db.execute('SELECT * FROM equipment WHERE id=?',(ident,)).fetchone()
            if not row or row['status']!='Active' or depth<row['installed_depth']: raise ValueError('Alat tidak aktif atau kedalaman akhir tidak valid')
            db.execute('UPDATE equipment SET retired_depth=?,status=? WHERE id=?',(depth,'Retired',ident));cur=type('C',(),{'lastrowid':ident})()
        elif name=='materials':
            cur=db.execute('INSERT INTO materials(name,unit,reorder_qty,unit_cost) VALUES(?,?,?,?)',(required(d,'name'),required(d,'unit'),positive(num(d,'reorder_qty',0),'Reorder point'),positive(num(d,'unit_cost',0),'Harga satuan')))
        elif name=='stock':
            material_id=int(d['material_id']); qty=num(d,'qty');reason=required(d,'reason')
            if reason not in ('Receipt','Issue','Adjustment'): raise ValueError('Jenis transaksi tidak valid')
            if reason=='Receipt' and qty<=0 or reason=='Issue' and qty>=0: raise ValueError('Penerimaan harus positif, pemakaian harus negatif')
            balance=db.execute('SELECT COALESCE(SUM(qty),0) FROM stock_moves WHERE material_id=?',(material_id,)).fetchone()[0]
            if balance+qty<-0.000001: raise ValueError('Stok tidak mencukupi')
            rig=int(d['rig_id']) if d.get('rig_id') else None
            cur=db.execute('INSERT INTO stock_moves(material_id,rig_id,qty,reason,reference,actor,at) VALUES(?,?,?,?,?,?,?)',(material_id,rig,qty,reason,str(d.get('reference','')).strip(),actor,now()))
        elif name=='boxes':
            start=num(d,'from_depth');end=num(d,'to_depth');recovery=num(d,'recovery_m')
            if start<0 or end<=start or not 0<=recovery<=end-start: raise ValueError('Interval/recovery core tidak valid')
            rig=int(d['rig_id']);hole=required(d,'hole_code')
            overlap=db.execute('SELECT 1 FROM core_boxes WHERE rig_id=? AND hole_code=? AND from_depth<? AND to_depth>?',(rig,hole,end,start)).fetchone()
            if overlap: raise ValueError('Interval core box bertumpuk pada lubang yang sama')
            rqd=num(d,'rqd_pct',-1)
            if rqd!=-1 and not 0<=rqd<=100: raise ValueError('RQD harus 0–100%')
            cur=db.execute('INSERT INTO core_boxes(code,rig_id,hole_code,from_depth,to_depth,recovery_m,lithology,rqd_pct,created_at) VALUES(?,?,?,?,?,?,?,?,?)',(required(d,'code'),rig,hole,start,end,recovery,str(d.get('lithology','')).strip(),None if rqd==-1 else rqd,now()))
        elif name=='samples':
            box=int(d['box_id']); start=num(d,'from_depth');end=num(d,'to_depth')
            b=db.execute('SELECT from_depth,to_depth FROM core_boxes WHERE id=?',(box,)).fetchone()
            if not b or start<b['from_depth'] or end>b['to_depth'] or end<=start: raise ValueError('Interval sample harus di dalam core box')
            if db.execute('SELECT 1 FROM samples WHERE box_id=? AND from_depth<? AND to_depth>?',(box,end,start)).fetchone(): raise ValueError('Interval sample bertumpuk')
            weight=num(d,'weight_kg',0)
            cur=db.execute('INSERT INTO samples(code,box_id,from_depth,to_depth,sample_type,weight_kg,created_at) VALUES(?,?,?,?,?,?,?)',(required(d,'code'),box,start,end,required(d,'sample_type'),positive(weight,'Berat'),now()))
            db.execute('INSERT INTO custody_events(sample_id,stage,from_holder,to_holder,actor,at) VALUES(?,?,?,?,?,?)',(cur.lastrowid,'Collected','Rig',actor,actor,now()))
        elif name=='custody':
            sample=int(d['sample_id']);stage=required(d,'stage')
            stages=['Collected','Packed','Logged','Dispatched','Received at lab','Archived']
            if stage not in stages[1:]: raise ValueError('Tahap custody tidak valid')
            old=db.execute('SELECT id,stage,to_holder FROM custody_events WHERE sample_id=? ORDER BY id DESC LIMIT 1',(sample,)).fetchone()
            if not old or stages.index(stage)!=stages.index(old['stage'])+1: raise ValueError('Tahap custody harus berurutan')
            if d.get('expected_event_id') is not None and int(d['expected_event_id'])!=old['id']:
                raise ValueError('Riwayat serah-terima sudah berubah. Muat ulang tracking.')
            if stage=='Archived':
                qa=db.execute('SELECT qa_status FROM samples WHERE id=?',(sample,)).fetchone()
                if not qa or qa['qa_status']=='Pending':raise ValueError('QA harus diselesaikan sebelum arsip sample')
            holder=required(d,'to_holder')
            cur=db.execute('INSERT INTO custody_events(sample_id,stage,from_holder,to_holder,actor,note,at) VALUES(?,?,?,?,?,?,?)',(sample,stage,old['to_holder'],holder,actor,str(d.get('note','')).strip(),now()))
        elif name=='qa':
            ident=int(d['sample_id']);status=required(d,'qa_status')
            if status not in ('Accepted','Rejected'): raise ValueError('Status QA tidak valid')
            if not db.execute("SELECT 1 FROM custody_events WHERE sample_id=? AND stage='Received at lab'",(ident,)).fetchone(): raise ValueError('Sample belum diterima lab')
            result=str(d.get('lab_result','')).strip()
            if status=='Rejected' and not result: raise ValueError('Alasan penolakan wajib diisi')
            reason=required(d,'reason')
            if len(reason)>250:raise ValueError('Alasan QA maksimal 250 karakter')
            old=db.execute('SELECT qa_status,lab_result FROM samples WHERE id=?',(ident,)).fetchone()
            if not old:raise ValueError('Sample tidak ditemukan')
            if old['qa_status']==status and old['lab_result']==result:raise ValueError('Status dan hasil QA tidak berubah')
            db.execute('UPDATE samples SET qa_status=?,lab_result=? WHERE id=?',(status,result,ident));cur=type('C',(),{'lastrowid':ident})()
            db.execute('INSERT INTO qa_revisions(sample_id,old_status,new_status,old_result,new_result,reason,actor,at) VALUES(?,?,?,?,?,?,?,?)',(ident,old['qa_status'],status,old['lab_result'],result,reason,actor,now()))
        elif name=='programs':
            cur=db.execute('INSERT INTO programs(name,contractor,budget,target_m) VALUES(?,?,?,?)',(required(d,'name'),str(d.get('contractor','')).strip(),positive(num(d,'budget',0),'Anggaran'),positive(num(d,'target_m',0),'Target')))
        elif name=='expenses':
            category=required(d,'category')
            if category not in ('Drilling','Equipment','Consumables','Contractor','Other'): raise ValueError('Kategori biaya tidak valid')
            date=required(d,'work_date');datetime.strptime(date,'%Y-%m-%d')
            cur=db.execute('INSERT INTO expenses(program_id,rig_id,work_date,category,amount,reference,note,actor,at) VALUES(?,?,?,?,?,?,?,?,?)',(int(d['program_id']),int(d['rig_id']) if d.get('rig_id') else None,date,category,positive(num(d,'amount'),'Biaya'),required(d,'reference'),str(d.get('note','')).strip(),actor,now()))
        elif name=='invoices':
            cur=db.execute('INSERT INTO invoices(program_id,reference,billed_m,billed_amount,at) VALUES(?,?,?,?,?)',(int(d['program_id']),required(d,'reference'),positive(num(d,'billed_m'),'Meter invoice'),positive(num(d,'billed_amount'),'Nilai invoice'),now()))
        else: raise ValueError('Endpoint tidak tersedia')
        ident=cur.lastrowid
        if name in ('boxes','samples'):issue(db,name,ident)
        log(db,name,ident,'CREATED' if name not in ('retire','qa') else 'UPDATED',actor,{k:v for k,v in d.items() if k!='actor'})
        return {'id':ident}

def summary():
    with connect() as db:
        meters=db.execute("SELECT COALESCE(SUM(end_depth-start_depth),0) FROM reports WHERE status='Approved' AND rig_id IN (SELECT id FROM rigs WHERE active=1)").fetchone()[0]
        from ddr_metrics import hours
        downtime=sum(hours(dict(r))[0]['maintenance'] for r in db.execute("SELECT * FROM reports WHERE status='Approved' AND rig_id IN (SELECT id FROM rigs WHERE active=1)"))
        spent=db.execute('SELECT COALESCE(SUM(amount),0) FROM expenses WHERE rig_id IS NULL OR rig_id IN (SELECT id FROM rigs WHERE active=1)').fetchone()[0]
        budget=db.execute('SELECT COALESCE(SUM(budget),0) FROM programs WHERE active=1').fetchone()[0]
        programs=[dict(x) for x in db.execute('''SELECT p.*,COALESCE((SELECT SUM(amount) FROM expenses WHERE program_id=p.id AND (rig_id IS NULL OR rig_id IN (SELECT id FROM rigs WHERE active=1))),0) spent,COALESCE((SELECT SUM(end_depth-start_depth) FROM reports WHERE program_id=p.id AND status='Approved' AND rig_id IN (SELECT id FROM rigs WHERE active=1)),0) approved_m FROM programs p ORDER BY p.id''')]
        equipment=[dict(x) for x in db.execute("SELECT serial,kind,max_life_m,retired_depth,installed_depth FROM equipment WHERE status='Active' AND max_life_m IS NOT NULL AND (rig_id IS NULL OR rig_id IN (SELECT id FROM rigs WHERE active=1))")]
        materials=[dict(x) for x in db.execute('''SELECT m.name,m.unit,m.reorder_qty,COALESCE(SUM(s.qty),0) stock FROM materials m LEFT JOIN stock_moves s ON s.material_id=m.id GROUP BY m.id HAVING stock<=m.reorder_qty''')]
        return {'approved_m':meters,'downtime_min':downtime,'spent':spent,'budget':budget,'cost_per_m':spent/meters if meters else None,'programs':programs,'equipment_watch':equipment,'stock_alerts':materials,'pending_ddr':db.execute("SELECT COUNT(*) FROM reports WHERE status='Submitted' AND rig_id IN (SELECT id FROM rigs WHERE active=1)").fetchone()[0], 'pending_qa':db.execute("SELECT COUNT(*) FROM samples s JOIN core_boxes b ON b.id=s.box_id JOIN rigs g ON g.id=b.rig_id WHERE s.qa_status='Pending' AND g.active=1").fetchone()[0]}


def target_settings():
    with connect() as db:
        current=[dict(x) for x in db.execute("""SELECT t.id,t.rig_id,r.code AS rig,r.location,t.period,t.target_m,t.updated_by,t.updated_at
          FROM rig_targets t JOIN rigs r ON r.id=t.rig_id WHERE r.active=1
          ORDER BY r.code, CASE t.period WHEN 'Daily' THEN 1 WHEN 'Monthly' THEN 2 ELSE 3 END""")]
        history=[dict(x) for x in db.execute("""SELECT h.id,h.rig_id,r.code AS rig,h.period,h.old_target,h.new_target,h.reason,h.actor,h.at
          FROM target_revisions h JOIN rigs r ON r.id=h.rig_id ORDER BY h.id DESC LIMIT 300""")]
        return {'targets':current,'history':history}

def tracking(code):
    code=str(code or '').strip()
    if not code: raise ValueError('Scan atau masukkan kode box/sample')
    if len(code)>160:raise ValueError('Kode terlalu panjang')
    qualified=re.fullmatch(r'DRILLING:(boxes|samples):([0-9a-f]{32})',code)
    with connect() as db:
        if qualified:
            kind=qualified.group(1);ident=resolve(db,kind,qualified.group(2))
            if ident is None:raise ValueError('QR sudah tidak berlaku atau tidak ditemukan')
            table={'boxes':'core_boxes','samples':'samples'}[kind]
            item=db.execute(f'SELECT code FROM {table} WHERE id=?',(ident,)).fetchone()
            if not item:raise ValueError('Identitas QR tidak ditemukan')
            code=item['code'];forced=kind
        else:forced=None
        if not forced:
            count=db.execute('SELECT (SELECT COUNT(*) FROM samples WHERE lower(code)=lower(?))+(SELECT COUNT(*) FROM core_boxes WHERE lower(code)=lower(?))',(code,code)).fetchone()[0]
            if count>1:raise ValueError('Kode sama pada box dan sample. Gunakan QR terbaru yang mencantumkan jenis objek.')
        sample=db.execute("""SELECT s.*,b.code AS box_code,b.hole_code,b.from_depth AS box_from_depth,b.to_depth AS box_to_depth,
          r.code AS rig,r.location FROM samples s JOIN core_boxes b ON b.id=s.box_id JOIN rigs r ON r.id=b.rig_id
          WHERE lower(s.code)=lower(?)""",(code,)).fetchone() if forced!='boxes' else None
        if sample:
            custody=[dict(x) for x in db.execute("""SELECT id,stage,from_holder,to_holder,actor,note,at FROM custody_events
              WHERE sample_id=? ORDER BY id""",(sample['id'],))]
            qa_history=[dict(x) for x in db.execute('SELECT old_status,new_status,old_result,new_result,reason,actor,at FROM qa_revisions WHERE sample_id=? ORDER BY id',(sample['id'],))]
            latest=custody[-1] if custody else None
            return {'kind':'sample','sample':dict(sample),'payload':'DRILLING:samples:'+token_for(db,'samples',sample['id']),'current_stage':latest['stage'] if latest else None,'last_recipient':latest['to_holder'] if latest else None,'expected_event_id':latest['id'] if latest else None,'custody':custody,'qa_history':qa_history}
        box=db.execute("""SELECT b.*,r.code AS rig,r.location FROM core_boxes b JOIN rigs r ON r.id=b.rig_id WHERE lower(b.code)=lower(?)""",(code,)).fetchone() if forced!='samples' else None
        if box:
            samples=[]
            for row in db.execute('SELECT * FROM samples WHERE box_id=? ORDER BY from_depth,id',(box['id'],)):
                item=dict(row)
                latest=db.execute('SELECT stage,to_holder,at FROM custody_events WHERE sample_id=? ORDER BY id DESC LIMIT 1',(row['id'],)).fetchone()
                item['current_stage']=latest['stage'] if latest else None
                item['last_recipient']=latest['to_holder'] if latest else None
                item['last_movement_at']=latest['at'] if latest else None
                token=token_for(db,'samples',row['id']);item['payload']='DRILLING:samples:'+token if token else None
                samples.append(item)
            return {'kind':'box','box':dict(box),'payload':'DRILLING:boxes:'+token_for(db,'boxes',box['id']),'samples':samples}
    raise ValueError('Kode box/sample tidak ditemukan')
