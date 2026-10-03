"""Additional HTTP operations; called after authentication and role checks."""
import json
from urllib.parse import parse_qs, urlparse
import ddr_rules as rules
import ddr_detail

def get(h,path,user):
    import app
    q=parse_qs(urlparse(h.path).query)
    with app.connect() as db:
        if path=='/api/ddr/summary':
            from period_targets import bounds
            a,b=bounds(q.get('period',['Daily'])[0],q.get('key',[''])[0])
            rig_id=int(q.get('rig',['0'])[0]);
            if rig_id<0:raise ValueError('Rig tidak valid')
            return h.send(200,rules.overview(db,user,a,b,rig_id))
        if path=='/api/ddr/settings':
            return h.send(200,{'units':[dict(r) for r in db.execute('SELECT * FROM rig_units')],'prices':[dict(r,prices=json.loads(r['prices'])) for r in db.execute('SELECT * FROM price_versions ORDER BY effective_date DESC,id DESC')]})
        if path=='/api/ddr/units':
            return h.send(200,[dict(r) for r in db.execute('SELECT rig_id,wob,torque,pump_pressure FROM rig_units')])
        if path=='/api/ddr/commercial':
            return h.send(200,[rules.commercial(dict(r)) for r in db.execute('SELECT r.*,COALESCE(r.rig_code_snapshot,g.code) rig FROM reports r JOIN rigs g ON g.id=r.rig_id WHERE g.active=1 ORDER BY work_date DESC,r.id DESC')])
        if path=='/api/ddr/context':
            rig=int(q.get('rig',['0'])[0]);hole=q.get('hole',[''])[0].strip().upper();day=q.get('date',[''])[0];shift=q.get('shift',['Day'])[0];exclude=int(q.get('exclude',['0'])[0])
            rows=[dict(r) for r in db.execute("SELECT * FROM reports WHERE rig_id=? AND id!=? AND status!='Rejected' ORDER BY work_date,start_time,id",(rig,exclude))]
            same=[r for r in rows if r['hole_code']==hole and hole and rules.visible(r,user)]
            def brief(r):return {k:r[k] for k in ('id','work_date','shift','start_depth','end_depth','start_time','end_time','hole_code')}
            minutes=sum(sum((b-a).total_seconds()/60 for a,b in rules.activity_slots(r)) for r in rows if r['work_date']==day and r['shift']==shift)
            return h.send(200,{'hole_reports':[brief(r) for r in same],'shift_minutes':minutes,'limit_minutes':600})
        parts=path.split('/')
        if len(parts)==5 and parts[2]=='reports' and parts[4] in ('pdf','xlsx','revisions'):
            r=db.execute('SELECT r.*,COALESCE(r.rig_code_snapshot,g.code) AS rig,COALESCE(r.rig_location_snapshot,g.location) AS location FROM reports r JOIN rigs g ON g.id=r.rig_id WHERE r.id=?',(int(parts[3]),)).fetchone()
            if not r or not rules.visible(r,user):return h.send(404,{'error':'Laporan tidak ditemukan'})
            if parts[4]=='revisions':
                return h.send(200,[dict(x) for x in db.execute('SELECT * FROM report_revisions WHERE report_id=? ORDER BY id',(r['id'],))])
            from ddr_exports import export
            data,kind=export(dict(r),parts[4]);return h.send(200,data,kind,download=f'DDR-{r["id"]}-rev{r["revision"]}.{parts[4]}')
    return h.send(404,{'error':'Tidak ditemukan'})

def post(h,path,d,user):
    import app
    with app.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        if path=='/api/ddr/units':
            ident=int(d['rig_id']);opts={'wob':('','kN','kgf','lbf'),'torque':('','Nm','kNm','lbf.ft'),'pump_pressure':('','bar','psi','MPa')}
            for k,v in opts.items():
                if d.get(k,'') not in v:raise ValueError('Satuan '+k+' tidak valid')
            source=ddr_detail.label(d.get('source'),'Referensi panel/manual',250)
            if not source:raise ValueError('Referensi panel atau manual wajib diisi')
            old=db.execute('SELECT * FROM rig_units WHERE rig_id=?',(ident,)).fetchone()
            db.execute('INSERT INTO rig_units VALUES(?,?,?,?,?,?,?) ON CONFLICT(rig_id) DO UPDATE SET wob=excluded.wob,torque=excluded.torque,pump_pressure=excluded.pump_pressure,source=excluded.source,actor=excluded.actor,at=excluded.at',(ident,d.get('wob',''),d.get('torque',''),d.get('pump_pressure',''),source,user['username'],app.now()))
            db.execute('INSERT INTO settings_audit(kind,before_json,after_json,actor,at) VALUES(?,?,?,?,?)',('units',json.dumps(dict(old)) if old else None,json.dumps(d),user['username'],app.now()))
            db.commit()
            return h.send(200,{'ok':True})
        if path=='/api/ddr/prices':
            day=str(d['effective_date']);from datetime import datetime
            if datetime.strptime(day,'%Y-%m-%d').strftime('%Y-%m-%d')!=day:raise ValueError('Tanggal harga tidak valid')
            prices=d.get('prices');allowed={'Open Hole','Core Hole',*ddr_detail.CONSUMABLES}
            if not isinstance(prices,dict) or set(prices)-allowed:raise ValueError('Daftar harga tidak valid')
            clean={k:ddr_detail.number(v,k,1e12) for k,v in prices.items() if v not in ('',None)}
            if not {'Open Hole','Core Hole'}<=clean.keys():raise ValueError('Tarif Open Hole dan Coring wajib diisi')
            source=ddr_detail.label(d.get('source'),'Sumber harga',250)
            if not source:raise ValueError('Sumber harga wajib diisi')
            db.execute('INSERT INTO price_versions(effective_date,prices,source,actor,at) VALUES(?,?,?,?,?)',(day,json.dumps(clean),source,user['username'],app.now()))
            db.commit()
            return h.send(201,{'ok':True})
        if path.endswith('/billing'):
            ident=int(path.split('/')[3]);status=d.get('status');reason=ddr_detail.label(d.get('reason'),'Alasan',500)
            if status not in ('Billable','Non-billable','Pending') or not reason:raise ValueError('Isi status tagihan dan alasan')
            old=db.execute('SELECT * FROM reports WHERE id=?',(ident,)).fetchone()
            if not old:return h.send(404,{'error':'DDR tidak ditemukan'})
            if int(d.get('expected_revision',-1))!=old['revision']:
                from period_targets import Conflict
                raise Conflict('DDR sudah berubah. Muat ulang sebelum menetapkan tagihan.')
            db.execute('UPDATE reports SET billing_status=?,billing_note=?,revision=revision+1 WHERE id=?',(status,reason,ident))
            after=dict(db.execute('SELECT * FROM reports WHERE id=?',(ident,)).fetchone())
            db.execute('INSERT INTO report_revisions(report_id,revision,before_json,after_json,reason,actor,at) VALUES(?,?,?,?,?,?,?)',(ident,after['revision'],json.dumps(dict(old)),json.dumps(after),reason,user['username'],app.now()))
            db.execute('INSERT INTO audit(report_id,action,actor,at,detail) VALUES(?,?,?,?,?)',(ident,'BILLING',user['username'],app.now(),status+': '+reason))
            db.commit()
            return h.send(200,{'ok':True})
    return h.send(404,{'error':'Tidak ditemukan'})
