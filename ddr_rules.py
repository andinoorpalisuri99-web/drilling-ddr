"""DDR ownership, hole/shift validation, unit settings and effective dated prices."""
import json
import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
import ddr_detail

class Validation(ValueError):
    def __init__(self,message,field='form',code='validation'):
        super().__init__(message);self.field=field;self.code=code


def migrate():
    import app
    with app.connect() as db:
        schema=db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='reports'").fetchone()[0]
        legacy=bool(re.search(r'UNIQUE\s*\(rig_id\s*,\s*work_date\s*,\s*shift\s*\)',schema,re.I))
        if legacy:
            backup=Path(str(app.DB)+'.pre-v080.bak')
            if not backup.exists():
                with sqlite3.connect(backup) as dest:db.backup(dest)
            db.execute('PRAGMA foreign_keys=OFF');db.execute('BEGIN IMMEDIATE')
            indexes=[r[0] for r in db.execute("SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name='reports' AND sql IS NOT NULL")]
            new=re.sub(r',\s*UNIQUE\s*\(rig_id\s*,\s*work_date\s*,\s*shift\s*\)','',schema,flags=re.I)
            new=new.replace('CREATE TABLE reports','CREATE TABLE reports_v080',1)
            db.execute(new)
            cols=','.join('"'+r['name']+'"' for r in db.execute('PRAGMA table_info(reports)'))
            db.execute(f'INSERT INTO reports_v080({cols}) SELECT {cols} FROM reports')
            db.execute('DROP TABLE reports');db.execute('ALTER TABLE reports_v080 RENAME TO reports')
            for sql in indexes:db.execute(sql)
            # Parent tables may be created by the next startup initializer.
            db.commit();db.execute('PRAGMA foreign_keys=ON')
        columns={r['name'] for r in db.execute('PRAGMA table_info(reports)')}
        for name,definition in [('hole_code',"TEXT NOT NULL DEFAULT ''"),('revision','INTEGER NOT NULL DEFAULT 0'),('billing_status',"TEXT NOT NULL DEFAULT 'Pending'"),('billing_note',"TEXT NOT NULL DEFAULT ''"),('pricing_snapshot','TEXT')]:
            if name not in columns:db.execute(f'ALTER TABLE reports ADD COLUMN {name} {definition}')
        for r in db.execute("SELECT id,ddr_detail FROM reports WHERE hole_code='' AND ddr_detail IS NOT NULL").fetchall():
            hole=json.loads(r['ddr_detail']).get('identity',{}).get('hole','').strip().upper()
            db.execute('UPDATE reports SET hole_code=? WHERE id=?',(hole,r['id']))
        db.executescript('''CREATE TABLE IF NOT EXISTS report_revisions(id INTEGER PRIMARY KEY,report_id INTEGER NOT NULL,revision INTEGER NOT NULL,before_json TEXT NOT NULL,after_json TEXT NOT NULL,reason TEXT NOT NULL,actor TEXT NOT NULL,at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS rig_units(rig_id INTEGER PRIMARY KEY REFERENCES rigs(id),wob TEXT NOT NULL DEFAULT '',torque TEXT NOT NULL DEFAULT '',pump_pressure TEXT NOT NULL DEFAULT '',source TEXT NOT NULL,actor TEXT NOT NULL,at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS price_versions(id INTEGER PRIMARY KEY,effective_date TEXT NOT NULL,prices TEXT NOT NULL,source TEXT NOT NULL,actor TEXT NOT NULL,at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS settings_audit(id INTEGER PRIMARY KEY,kind TEXT NOT NULL,before_json TEXT,after_json TEXT NOT NULL,actor TEXT NOT NULL,at TEXT NOT NULL);''')
        if not db.execute('SELECT 1 FROM price_versions').fetchone():
            db.execute("INSERT INTO price_versions(effective_date,prices,source,actor,at) VALUES(?,?,?,?,?)",('0001-01-01',json.dumps({'Open Hole':500000,'Core Hole':700000}),'Tarif awal dari diskusi MMS; material belum ditetapkan','system',app.now()))
        db.execute('CREATE INDEX IF NOT EXISTS idx_report_hole ON reports(rig_id,hole_code,work_date,shift)')


def slot(row):
    origin=datetime.strptime(row['work_date'],'%Y-%m-%d')
    a=datetime.strptime(row['start_time'],'%H:%M');b=datetime.strptime(row['end_time'],'%H:%M')
    start=origin+timedelta(hours=a.hour,minutes=a.minute)
    if row['shift']=='Night' and a.hour<12:start+=timedelta(days=1)
    end=start+timedelta(minutes=((b.hour*60+b.minute-a.hour*60-a.minute)%1440 or 1440))
    return start,end


def detail(row):
    d=row.get('ddr_detail');return json.loads(d) if isinstance(d,str) and d else (d or {})


def activity_slots(row):
    start,end=slot(row);out=[]
    for x in detail(row).get('activities',[]):
        clock=datetime.strptime(x['from'],'%H:%M');a=start.replace(hour=clock.hour,minute=clock.minute)
        if a<start:a+=timedelta(days=1)
        stop=datetime.strptime(x['to'],'%H:%M');b=a.replace(hour=stop.hour,minute=stop.minute)
        if b<=a:b+=timedelta(days=1)
        out.append((a,b))
    return out or [(start,end)]


def validate(db,d,exclude=0):
    hole=detail(d).get('identity',{}).get('hole','').strip().upper()
    duplicate=db.execute('SELECT id FROM reports WHERE rig_id=? AND work_date=? AND shift=? AND hole_code=? AND id!=?',(int(d['rig_id']),d['work_date'],d['shift'],hole,exclude)).fetchone()
    if duplicate:
        from period_targets import Conflict
        raise Conflict(f'DDR #{duplicate[0]} sudah ada untuk rig, hole, tanggal, dan shift ini. Hubungi admin untuk koreksi.')
    rows=[dict(r) for r in db.execute("SELECT * FROM reports WHERE rig_id=? AND id!=? AND status!='Rejected'",(int(d['rig_id']),exclude))]
    start,end=slot(d)
    for r in rows:
        same=(r['hole_code']==hole) if hole else not r['hole_code']
        if not same:continue
        rs,re=slot(r)
        suffix=f"DDR #{r['id']} · {r['work_date']} {r['shift']} · hole {hole or '(legacy tanpa ID)'}"
        if rs<start and float(d['start_depth'])<r['end_depth']-1e-6:
            raise Validation(f"Start depth {float(d['start_depth']):g} m lebih kecil dari akhir {r['end_depth']:g} m pada {suffix}. Periksa data atau hubungi admin.",'start_depth','depth_previous')
        if rs>start and float(d['end_depth'])>r['start_depth']+1e-6:
            raise Validation(f"End depth {float(d['end_depth']):g} m melampaui awal {r['start_depth']:g} m pada {suffix}. Periksa data atau hubungi admin.",'end_depth','depth_next')
        if rs==start:raise Validation('Waktu mulai sama dengan '+suffix,'start_time','duplicate')
    if detail(d).get('version')!=2:
        if any(r['work_date']==d['work_date'] and r['shift']==d['shift'] and r['hole_code']==hole for r in rows):
            from period_targets import Conflict
            raise Conflict('DDR untuk hole, rig dan shift ini sudah ada')
        return
    active=activity_slots(d);minutes=sum((b-a).total_seconds()/60 for a,b in active)
    for r in rows:
        prior=activity_slots(r)
        if any(a<y and x<b for a,b in active for x,y in prior):
            raise Validation(f"Jam aktivitas bertumpang tindih dengan DDR #{r['id']} · {r['work_date']} {r['shift']} pada rig ini. Hubungi admin bila laporan bukan milik Anda.",'activities','time_overlap')
        if r['work_date']==d['work_date'] and r['shift']==d['shift']:
            minutes+=sum((b-a).total_seconds()/60 for a,b in prior)
    if minutes>600:raise Validation(f'Total aktivitas rig pada shift ini {minutes/60:g} jam; batas 10 jam untuk seluruh DDR dalam shift.','activities','shift_limit')


def units(db,rig_id):
    r=db.execute('SELECT * FROM rig_units WHERE rig_id=?',(rig_id,)).fetchone()
    return {k:r[k] if r else '' for k in ('wob','torque','pump_pressure')}


def priced(db,d):
    r=db.execute('SELECT * FROM price_versions WHERE effective_date<=? ORDER BY effective_date DESC,id DESC LIMIT 1',(d['work_date'],)).fetchone()
    return {'id':r['id'],'effective_date':r['effective_date'],'source':r['source'],'prices':json.loads(r['prices'])} if r else None


def visible(row,user):return user['role']!='operator' or row['operator']==user['username']

def overview(db,user,start,end,rig_id=0):
    import ddr_metrics
    condition=' AND r.operator=?' if user['role']=='operator' else ''
    params=[start,end]+([user['username']] if condition else [])
    if rig_id:condition+=' AND r.rig_id=?';params.append(rig_id)
    rows=[dict(r) for r in db.execute('SELECT r.*,COALESCE(r.rig_code_snapshot,g.code) rig,g.active rig_active FROM reports r JOIN rigs g ON g.id=r.rig_id WHERE work_date>=? AND work_date<?'+condition,params)]
    condition=' AND operator=?' if user['role']=='operator' else ''
    latest=db.execute("SELECT MAX(work_date) AS latest_work_date,MAX(COALESCE(reviewed_at,created_at)) AS latest_saved_at FROM reports WHERE status!='Rejected' AND rig_id IN (SELECT id FROM rigs WHERE active=1)"+condition,([user['username']] if condition else [])).fetchone()
    excluded=[r for r in rows if not r['rig_active'] and r['status']!='Rejected']
    measures=ddr_metrics.overview(rows)
    measures['availability']={'restricted':True} if user['role']=='operator' else ddr_metrics.availability(rows)
    if user['role']!='operator':
        history=[dict(r) for r in db.execute('SELECT r.*,COALESCE(r.rig_code_snapshot,g.code) rig,g.active rig_active FROM reports r JOIN rigs g ON g.id=r.rig_id'+(' WHERE r.rig_id=?' if rig_id else ''),([rig_id] if rig_id else []))]
        measures['availability']['attention']=ddr_metrics.availability(history)['issues']
    inactive_m=sum((ddr_metrics.dec(r['end_depth'])-ddr_metrics.dec(r['start_depth']) for r in excluded),ddr_metrics.ZERO)
    rows=[r for r in rows if r['rig_active']]
    return {**measures,'scope':'active_rigs','excluded_inactive_count':len(excluded),'excluded_inactive_m':float(inactive_m),'freshness':dict(latest),'meters':measures['metrics']['actual_m'],'counts':{s:sum(r['status']==s for r in rows) for s in ('Submitted','Approved','Rejected')}}


def commercial(row):
    from ddr_metrics import commercial
    return commercial(row)
