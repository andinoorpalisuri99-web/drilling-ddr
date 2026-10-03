"""Calendar-scoped rig targets. Legacy rig_targets remain as explicit fallback plans."""
import math
import re
from datetime import date, timedelta
from app import connect, now

class Conflict(Exception): pass

def initialize():
    with connect() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS period_targets (
          id INTEGER PRIMARY KEY, rig_id INTEGER NOT NULL REFERENCES rigs(id),
          period TEXT NOT NULL CHECK(period IN ('Daily','Monthly','Yearly')),
          period_key TEXT NOT NULL, target_m REAL NOT NULL CHECK(target_m>=0),
          revision INTEGER NOT NULL DEFAULT 1, updated_by TEXT NOT NULL,
          updated_at TEXT NOT NULL, UNIQUE(rig_id,period,period_key));
        CREATE TABLE IF NOT EXISTS period_target_revisions (
          id INTEGER PRIMARY KEY, target_id INTEGER NOT NULL REFERENCES period_targets(id),
          revision INTEGER NOT NULL, old_target REAL, new_target REAL NOT NULL,
          reason TEXT NOT NULL, actor TEXT NOT NULL, at TEXT NOT NULL,
          UNIQUE(target_id,revision));
        CREATE TABLE IF NOT EXISTS period_target_baselines (
          rig_id INTEGER NOT NULL REFERENCES rigs(id),period TEXT NOT NULL,
          target_m REAL NOT NULL, captured_at TEXT NOT NULL,PRIMARY KEY(rig_id,period));
        CREATE INDEX IF NOT EXISTS idx_report_period ON reports(work_date,rig_id,status);
        ''')
        db.execute('''INSERT OR IGNORE INTO period_target_baselines(rig_id,period,target_m,captured_at)
          SELECT rig_id,period,target_m,? FROM rig_targets''',(now(),))

def bounds(period,key):
    patterns={'Daily':r'\d{4}-\d{2}-\d{2}','Monthly':r'\d{4}-\d{2}','Yearly':r'\d{4}'}
    if period not in patterns or not re.fullmatch(patterns[period],str(key or '')):
        raise ValueError('Periode atau tanggal tidak valid')
    try:
        if period=='Daily':
            start=date.fromisoformat(key);end=start+timedelta(days=1)
        elif period=='Monthly':
            year,month=map(int,key.split('-'));start=date(year,month,1)
            end=date(year+1,1,1) if month==12 else date(year,month+1,1)
        else:
            year=int(key);start=date(year,1,1);end=date(year+1,1,1)
        if start.strftime({'Daily':'%Y-%m-%d','Monthly':'%Y-%m','Yearly':'%Y'}[period])!=key:raise ValueError()
        return start.isoformat(),end.isoformat()
    except (ValueError,OverflowError):raise ValueError('Tanggal di luar rentang valid')

def summary(period,key):
    start,end=bounds(period,key)
    with connect() as db:
        db.execute('BEGIN')
        freshness=dict(db.execute("""SELECT MAX(work_date) latest_work_date,
          MAX(created_at) latest_saved_at FROM reports
          WHERE status IN ('Submitted','Approved') AND rig_id IN (SELECT id FROM rigs WHERE active=1)""").fetchone())
        rows=db.execute('''SELECT g.id rig_id,g.code rig,g.location,
          p.id target_id,p.revision,p.target_m period_target,b.target_m base_target,
          COALESCE(SUM(CASE WHEN r.status!='Rejected' THEN r.end_depth-r.start_depth END),0) actual_m,
          COALESCE(SUM(CASE WHEN r.status!='Rejected' THEN r.downtime_min END),0) downtime_min,
          SUM(CASE WHEN r.status='Submitted' THEN 1 ELSE 0 END) pending_count,
          SUM(CASE WHEN r.status!='Rejected' THEN 1 ELSE 0 END) report_count
          FROM rigs g LEFT JOIN period_targets p ON p.rig_id=g.id AND p.period=? AND p.period_key=?
          LEFT JOIN period_target_baselines b ON b.rig_id=g.id AND b.period=?
          LEFT JOIN reports r ON r.rig_id=g.id AND r.work_date>=? AND r.work_date<?
          WHERE g.active=1
          GROUP BY g.id ORDER BY g.code''',(period,key,period,start,end)).fetchall()
        from ddr_metrics import hours
        maintenance={}
        for record in db.execute("SELECT * FROM reports WHERE work_date>=? AND work_date<? AND status!='Rejected' AND rig_id IN (SELECT id FROM rigs WHERE active=1)",(start,end)):
            minutes,_=hours(dict(record));maintenance[record['rig_id']]=maintenance.get(record['rig_id'],0)+minutes['maintenance']
    results=[]
    for row in rows:
        x=dict(row);x['downtime_min']=maintenance.get(x['rig_id'],0);value=x['period_target'] if x['target_id'] else x['base_target']
        x['target_m']=value;x['source']='periode' if x['target_id'] else ('rencana dasar migrasi' if value is not None else 'belum diatur')
        x['achievement_pct']=round(x['actual_m']/value*100,1) if value and value>0 else None
        results.append(x)
    missing=sum(x['target_m'] is None or x['target_m']==0 for x in results)
    total_target=sum(x['target_m'] or 0 for x in results)
    actual=sum(x['actual_m'] for x in results)
    return {'freshness':freshness,'period':period,'period_key':key,'start':start,'end':end,'rigs':results,
            'total_target_m':total_target,'actual_m':actual,'downtime_min':sum(x['downtime_min'] for x in results),
            'report_count':sum(x['report_count'] for x in results),'pending_count':sum(x['pending_count'] for x in results),
            'missing_count':missing,'achievement_pct':round(actual/total_target*100,1) if total_target>0 and not missing else None}

def save(d,actor):
    rig_id=int(d['rig_id']);period=str(d['period']);key=str(d['period_key']);bounds(period,key)
    target=float(d['target_m']);reason=str(d.get('reason') or '').strip()
    if not math.isfinite(target) or target<0:raise ValueError('Target harus angka hingga dan tidak negatif')
    if not reason or len(reason)>250:raise ValueError('Alasan revisi wajib diisi (maksimal 250 karakter)')
    expected=int(d['expected_revision']);stamp=now()
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        if not db.execute('SELECT 1 FROM rigs WHERE id=? AND active=1',(rig_id,)).fetchone():raise ValueError('Rig tidak aktif atau tidak ditemukan')
        row=db.execute('SELECT id,revision,target_m FROM period_targets WHERE rig_id=? AND period=? AND period_key=?',(rig_id,period,key)).fetchone()
        revision=row['revision'] if row else 0
        if expected!=revision:raise Conflict('Target sudah berubah. Muat ulang periode sebelum menyimpan.')
        old=row['target_m'] if row else None
        if old is not None and old==target:raise ValueError('Target baru sama dengan target saat ini')
        if row:
            db.execute('UPDATE period_targets SET target_m=?,revision=?,updated_by=?,updated_at=? WHERE id=?',(target,revision+1,actor,stamp,row['id']));ident=row['id']
        else:
            ident=db.execute('INSERT INTO period_targets(rig_id,period,period_key,target_m,revision,updated_by,updated_at) VALUES(?,?,?,?,1,?,?)',(rig_id,period,key,target,actor,stamp)).lastrowid
        db.execute('INSERT INTO period_target_revisions(target_id,revision,old_target,new_target,reason,actor,at) VALUES(?,?,?,?,?,?,?)',(ident,revision+1,old,target,reason,actor,stamp))
        return {'id':ident,'revision':revision+1,'target_m':target}

def history(period,key):
    bounds(period,key)
    with connect() as db:
        return [dict(x) for x in db.execute('''SELECT h.*,g.code rig FROM period_target_revisions h
          JOIN period_targets t ON t.id=h.target_id JOIN rigs g ON g.id=t.rig_id
          WHERE t.period=? AND t.period_key=? ORDER BY h.id DESC LIMIT 300''',(period,key))]
