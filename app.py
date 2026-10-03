"""MMS Drilling DDR application with SQLite storage and authenticated exports."""
import json
import secrets
import os
import sqlite3
import math
import hashlib
from html import escape
from contextlib import contextmanager
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs
import auth
import ddr_detail

ROOT = Path(__file__).resolve().parent
APP_VERSION = '0.8.20'
DB = Path(os.environ.get('DRILLING_DB', ROOT / 'drilling.db'))
STATIC = ROOT / 'static'

def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')

@contextmanager
def connect():
    db = sqlite3.connect(DB,timeout=15)
    try:
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('PRAGMA journal_mode=WAL')
        with db:
            yield db
    finally:
        db.close()

def init():
    with connect() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS rigs (id INTEGER PRIMARY KEY, code TEXT UNIQUE NOT NULL, location TEXT NOT NULL, target_m REAL NOT NULL CHECK(target_m >= 0), active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)));
        CREATE TABLE IF NOT EXISTS reports (
          id INTEGER PRIMARY KEY, rig_id INTEGER NOT NULL REFERENCES rigs(id), work_date TEXT NOT NULL,
          shift TEXT NOT NULL CHECK(shift IN ('Day','Night')), start_depth REAL NOT NULL,
          end_depth REAL NOT NULL CHECK(end_depth >= start_depth), start_time TEXT NOT NULL,
          end_time TEXT NOT NULL, downtime_min INTEGER NOT NULL DEFAULT 0 CHECK(downtime_min >= 0),
          downtime_category TEXT NOT NULL DEFAULT 'None', bit_used TEXT NOT NULL DEFAULT '',
          rod_used INTEGER NOT NULL DEFAULT 0 CHECK(rod_used >= 0), mud_used REAL NOT NULL DEFAULT 0 CHECK(mud_used >= 0),
          wob REAL, rpm REAL, torque REAL, pump_pressure REAL, note TEXT NOT NULL DEFAULT '',
          operator TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'Submitted', supervisor TEXT,
          review_note TEXT, created_at TEXT NOT NULL, reviewed_at TEXT,
          UNIQUE(rig_id,work_date,shift));
        CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY, report_id INTEGER NOT NULL REFERENCES reports(id), action TEXT NOT NULL, actor TEXT NOT NULL, at TEXT NOT NULL, detail TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS rig_revisions (id INTEGER PRIMARY KEY, rig_id INTEGER NOT NULL REFERENCES rigs(id), action TEXT NOT NULL, before_json TEXT, after_json TEXT NOT NULL, actor TEXT NOT NULL, at TEXT NOT NULL);
        ''')
        if 'active' not in [x['name'] for x in db.execute('PRAGMA table_info(rigs)')]:
            db.execute('ALTER TABLE rigs ADD COLUMN active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1))')
        # Freeze report identity before any master edits; safe to repeat on startup.
        report_columns={x['name'] for x in db.execute('PRAGMA table_info(reports)')}
        for column in ('rig_code_snapshot','rig_location_snapshot'):
            if column not in report_columns:
                db.execute(f'ALTER TABLE reports ADD COLUMN {column} TEXT')
        db.execute("UPDATE reports SET rig_code_snapshot=(SELECT code FROM rigs WHERE id=reports.rig_id) WHERE rig_code_snapshot IS NULL")
        db.execute("UPDATE reports SET rig_location_snapshot=(SELECT location FROM rigs WHERE id=reports.rig_id) WHERE rig_location_snapshot IS NULL")
        if 'client_request_hash' not in [x['name'] for x in db.execute('PRAGMA table_info(reports)')]:
            db.execute('ALTER TABLE reports ADD COLUMN client_request_hash TEXT')
        if 'client_request_id' not in [x['name'] for x in db.execute('PRAGMA table_info(reports)')]:
            db.execute('ALTER TABLE reports ADD COLUMN client_request_id TEXT')
        db.execute('CREATE UNIQUE INDEX IF NOT EXISTS report_client_request_unique ON reports(operator,client_request_id) WHERE client_request_id IS NOT NULL')
        if 'ddr_detail' not in [x['name'] for x in db.execute('PRAGMA table_info(reports)')]:
            db.execute("ALTER TABLE reports ADD COLUMN ddr_detail TEXT")
        if 'program_id' not in [x['name'] for x in db.execute('PRAGMA table_info(reports)')]:
            db.execute('ALTER TABLE reports ADD COLUMN program_id INTEGER REFERENCES programs(id)')
        if not db.execute('SELECT 1 FROM rigs').fetchone():
            db.executemany('INSERT INTO rigs(code,location,target_m) VALUES(?,?,?)', [
              ('DR-01','Pit Utara',32),('DR-02','Pit Tengah',28),('DR-03','Pit Selatan',30)])

    import ddr_rules
    ddr_rules.migrate()

class Handler(BaseHTTPRequestHandler):
    def send(self, status, data, kind='application/json', cookie=None, download=None):
        raw = data if isinstance(data, bytes) else (data.encode('utf-8') if isinstance(data,str) and kind!='application/json' else json.dumps(data, ensure_ascii=False,allow_nan=False).encode())
        self.send_response(status)
        self.send_header('Content-Type', kind + ('; charset=utf-8' if kind.startswith('text/') or kind == 'application/json' else ''))
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy','no-referrer')
        self.send_header('Content-Security-Policy',"default-src 'self'; img-src 'self' data: blob: https://services.arcgisonline.com; style-src 'self' 'unsafe-inline'; script-src 'self'; base-uri 'none'; worker-src 'self' blob:; frame-ancestors 'none'")
        if download:self.send_header('Content-Disposition', 'attachment; filename="'+download+'"')
        if cookie:
            if os.environ.get('DRILLING_SECURE_COOKIES')=='1':cookie+='; Secure'
            self.send_header('Set-Cookie',cookie)
        self.end_headers()
        self.wfile.write(raw)

    def body(self):
        size = int(self.headers.get('Content-Length', '0'))
        if size < 0 or size > 100_000: raise ValueError('Ukuran data tidak valid')
        def reject_constant(value):
            raise ValueError('Angka JSON tidak valid: '+value)
        payload = json.loads(self.rfile.read(size),parse_constant=reject_constant)
        if not isinstance(payload, dict): raise ValueError('Format data harus berupa objek JSON')
        return payload

    def identity(self,path,method):
        with connect() as db:
            user=auth.current(db,self.headers.get('Cookie'))
        if not user:
            self.send(401,{'error':'Silakan login'});return None
        if method=='POST' and not secrets.compare_digest(self.headers.get('X-CSRF-Token',''),user['csrf']):
            self.send(403,{'error':'Sesi tidak valid. Muat ulang halaman.'});return None
        if not auth.allowed(user['role'],path,method):
            self.send(403,{'error':'Peran akun tidak memiliki akses untuk tindakan ini'});return None
        return user

    def do_GET(self):
        try:
            return self.get_request()
        except (ValueError,KeyError,TypeError,IndexError):
            return self.send(400,{'error':'Parameter permintaan tidak valid'})
        except sqlite3.OperationalError:
            return self.send(503,{'error':'Database belum siap atau sedang sibuk. Coba kembali.'})

    def get_request(self):
        path = urlparse(self.path).path
        if path in ('/','/index.html'):
            return self.send(200, (STATIC/'index.html').read_bytes(), 'text/html')
        map_assets={'/drilling-map.js':('drilling-map.js','text/javascript'),'/drilling-map.css':('drilling-map.css','text/css'),'/leaflet.js':('leaflet.js','text/javascript'),'/leaflet.css':('leaflet.css','text/css')}
        if path in map_assets:
            filename,kind=map_assets[path]
            return self.send(200,(STATIC/filename).read_bytes(),kind)
        if path == '/workspace-layout.css': return self.send(200, (STATIC/'workspace-layout.css').read_bytes(), 'text/css')
        if path == '/layout.js': return self.send(200, (STATIC/'layout.js').read_bytes(), 'text/javascript')
        if path == '/app.css': return self.send(200, (STATIC/'app.css').read_bytes(), 'text/css')
        if path == '/app.js': return self.send(200, (STATIC/'app.js').read_bytes(), 'text/javascript')
        if path == '/modules.js': return self.send(200, (STATIC/'modules.js').read_bytes(), 'text/javascript')
        if path == '/enhancements.js': return self.send(200, (STATIC/'enhancements.js').read_bytes(), 'text/javascript')
        if path == '/scanner.js': return self.send(200, (STATIC/'scanner.js').read_bytes(), 'text/javascript')
        if path == '/label.js': return self.send(200, (STATIC/'label.js').read_bytes(), 'text/javascript')
        if path == '/sw.js': return self.send(200, (STATIC/'sw.js').read_bytes(), 'text/javascript')
        if path == '/offline.js': return self.send(200, (STATIC/'offline.js').read_bytes(), 'text/javascript')
        if path == '/pdf.min.mjs': return self.send(200, (STATIC/'pdf.min.mjs').read_bytes(), 'text/javascript')
        if path == '/pdf.worker.min.mjs': return self.send(200, (STATIC/'pdf.worker.min.mjs').read_bytes(), 'text/javascript')
        if path == '/ddr-form.js': return self.send(200, (STATIC/'ddr-form.js').read_bytes(), 'text/javascript')
        if path == '/navigation.js': return self.send(200, (STATIC/'navigation.js').read_bytes(), 'text/javascript')
        if path == '/analytics.js': return self.send(200, (STATIC/'analytics.js').read_bytes(), 'text/javascript')
        if path == '/workspace.js': return self.send(200, (STATIC/'workspace.js').read_bytes(), 'text/javascript')
        if path == '/rigs.js': return self.send(200, (STATIC/'rigs.js').read_bytes(), 'text/javascript')
        if path == '/mms-logo.png': return self.send(200, (STATIC/'mms-logo.png').read_bytes(), 'image/png')
        if path == '/login-background.webp': return self.send(200, (STATIC/'login-background.webp').read_bytes(), 'image/webp')
        if path == '/api/version': return self.send(200,{'version':APP_VERSION,'modules':['DDR','Equipment','Core & Sample','Cost']})
        if path == '/api/login/accounts':
            with connect() as db:
                return self.send(200,[{'username':x['username']} for x in db.execute('SELECT username FROM users WHERE active=1 ORDER BY username COLLATE NOCASE')])
        if path == '/api/session':
            with connect() as db:user=auth.current(db,self.headers.get('Cookie'))
            return self.send(200,{'username':user['username'],'role':user['role'],'csrf':user['csrf']} if user else {'authenticated':False})
        if path.startswith('/api/'):
            user=self.identity(path,'GET')
            if user is None:return
        if path == '/api/drilling-map':
            return self.send(200,json.loads((ROOT/'map-data.json').read_text(encoding='utf-8')))
        if path.startswith('/api/ddr/') or (path.startswith('/api/reports/') and path.rsplit('/',1)[-1] in ('pdf','xlsx','revisions')):
            from ddr_routes import get
            try:return get(self,path,user)
            except ImportError:return self.send(503,{'error':'Komponen ekspor belum terpasang. Admin perlu menjalankan python -m pip install -r requirements.txt.'})
            except (ValueError,KeyError,TypeError) as e:return self.send(400,{'error':str(e)})
        if path == '/api/admin/deletions':
            from modules import deletion_history
            return self.send(200,deletion_history())
        if path == '/api/management':
            from modules import summary
            return self.send(200,summary())
        if path.startswith('/api/v2/'):
            from modules import collection
            try:
                name=path.split('/')[3];rows=collection(name)
                if user['role']=='operator':
                    keys=('id','name') if name=='programs' else ('id','serial','brand','kind','rig_id','installed_depth','status')
                    rows=[{k:r.get(k) for k in keys} for r in rows]
                if user['role']=='viewer' and name in ('equipment','materials'):
                    rows=[{k:v for k,v in row.items() if k!='unit_cost'} for row in rows]
                return self.send(200,rows)
            except ValueError as e:return self.send(404,{'error':str(e)})
        if path == '/api/targets/period':
            from period_targets import summary,history
            q=parse_qs(urlparse(self.path).query);period=q.get('period',['Daily'])[0];key=q.get('key',[''])[0]
            try:
                result=summary(period,key);result['history']=history(period,key)
                return self.send(200,result)
            except ValueError as e:return self.send(400,{'error':str(e)})
        if path == '/api/users':
            user=self.identity(path,'GET')
            if user is None:return
            with connect() as db:return self.send(200,[dict(x) for x in db.execute('SELECT id,username,role,active FROM users ORDER BY username')])
        if path in ('/api/label','/api/label/page'):
            query=parse_qs(urlparse(self.path).query)
            kind=query.get('kind',[''])[0]
            try:ident=int(query.get('id',[''])[0])
            except ValueError:return self.send(400,{'error':'ID tidak valid'})
            table={'boxes':'core_boxes','samples':'samples'}.get(kind)
            if not table:return self.send(400,{'error':'Tipe label tidak valid'})
            with connect() as db:row=db.execute(f'SELECT code FROM {table} WHERE id=?',(ident,)).fetchone()
            if not row:return self.send(404,{'error':'Label tidak ditemukan'})
            from identities import token_for
            with connect() as db:token=token_for(db,kind,ident)
            if not token:return self.send(404,{'error':'Identitas label tidak ditemukan'})
            if path=='/api/label/page':
                title=escape(row['code']);category='CORE BOX' if kind=='boxes' else 'SAMPLE'
                content=f'''<!doctype html><html lang="id"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Label {title}</title>
<style>body{{font:15px Arial,sans-serif;color:#27372b;margin:24px}}.label{{box-sizing:border-box;width:100mm;min-height:80mm;padding:7mm;border:1px solid #cbd5cb;display:grid;justify-items:start;gap:3mm}}.logo{{width:31mm;height:14mm;object-fit:contain}}.qr{{width:38mm;height:38mm}}h1{{font-size:20px;overflow-wrap:anywhere;margin:0}}small{{letter-spacing:.12em;color:#546659}}button{{margin:20px 0;padding:12px 18px}}@media print{{body{{margin:0}}button,p{{display:none}}.label{{border:0}}}}</style>
<button id="printLabel" disabled>Cetak label</button><p id="printStatus">Memuat QR…</p><section class="label"><img class="logo" src="/mms-logo.png" alt="MMS"><small>{category} · MMS DRILLING</small><img id="labelQR" class="qr" src="/api/label?kind={kind}&amp;id={ident}" alt="QR {title}"><h1>{title}</h1><small>Scan untuk membuka riwayat identitas</small></section><script src="/label.js"></script></html>'''
                return self.send(200,content,'text/html')
            try:
                from reportlab.graphics.barcode import createBarcodeDrawing
                from reportlab.graphics import renderSVG
            except ImportError:return self.send(503,{'error':'Paket reportlab diperlukan untuk membuat QR'})
            svg=renderSVG.drawToString(createBarcodeDrawing('QR',value=f'DRILLING:{kind}:{token}',barLevel='M'))
            raw_svg=svg.encode('utf-8') if isinstance(svg,str) else svg
            return self.send(200,raw_svg,'image/svg+xml')
        if path == '/api/targets':
            from modules import target_settings
            return self.send(200,target_settings())
        if path == '/api/tracking':
            from modules import tracking
            code=parse_qs(urlparse(self.path).query).get('code',[''])[0]
            try:return self.send(200,tracking(code))
            except ValueError as e:return self.send(404,{'error':str(e)})
        if path == '/api/rigs':
            with connect() as db:
                columns='id,code,location,active' if user['role']=='operator' else '*'
                return self.send(200,[dict(x) for x in db.execute('SELECT '+columns+' FROM rigs WHERE active=1 ORDER BY code')])
        if path == '/api/rigs/manage':
            from rig_master import inventory
            return self.send(200,inventory())
        if path == '/api/reports':
            query = parse_qs(urlparse(self.path).query)
            try:
                limit=int(query.get('limit',['200'])[0]);offset=int(query.get('offset',['0'])[0])
                if not 1<=limit<=500 or offset<0:raise ValueError()
            except ValueError:return self.send(400,{'error':'Parameter halaman tidak valid'})
            with connect() as db:
                where=[];params=[]
                if user['role']=='operator':where.append('r.operator=?');params.append(user['username'])
                if query.get('date'):
                    value=query['date'][0]
                    try:
                        if datetime.strptime(value,'%Y-%m-%d').strftime('%Y-%m-%d')!=value:raise ValueError()
                    except ValueError:return self.send(400,{'error':'Tanggal tidak valid'})
                    where.append('r.work_date=?');params.append(value)
                if query.get('rig'):where.append('COALESCE(r.rig_code_snapshot,g.code)=?');params.append(query['rig'][0])
                clause=' WHERE '+' AND '.join(where) if where else ''
                rows=db.execute('SELECT r.*,COALESCE(r.rig_code_snapshot,g.code) AS rig,COALESCE(r.rig_location_snapshot,g.location) AS location,g.target_m,g.active AS rig_active,p.name AS program,e.serial AS equipment_serial,e.kind AS equipment_kind FROM reports r JOIN rigs g ON r.rig_id=g.id LEFT JOIN programs p ON p.id=r.program_id LEFT JOIN equipment e ON e.id=r.equipment_id'+clause+' ORDER BY r.work_date DESC,r.id DESC LIMIT ? OFFSET ?',(*params,limit,offset)).fetchall()
                result=[dict(x,ddr_detail=json.loads(x['ddr_detail']) if x['ddr_detail'] else None) for x in rows]
                for r in result:
                    from ddr_metrics import hours, meterage
                    r['time_minutes'],r['time_issues']=hours(r)
                    r['downtime_min']=r['time_minutes']['maintenance']
                    r['production_metrics']=meterage(r)
                    if user['role'] not in ('admin','finance','manager'):
                        for key in ('pricing_snapshot','billing_note'):r.pop(key,None)
                    if user['role']=='operator':r.pop('target_m',None)
                return self.send(200,result)
        if path.startswith('/api/reports/') and path.endswith('/audit'):
            try: ident = int(path.split('/')[3])
            except ValueError: return self.send(400, {'error':'ID tidak valid'})
            with connect() as db:
                row=db.execute('SELECT operator FROM reports WHERE id=?',(ident,)).fetchone()
                if not row or (user['role']=='operator' and row['operator']!=user['username']):return self.send(404,{'error':'Laporan tidak ditemukan'})
                return self.send(200,[dict(x) for x in db.execute('SELECT * FROM audit WHERE report_id=? ORDER BY id',(ident,))])
        return self.send(404, {'error':'Tidak ditemukan'})

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            if path == '/api/logout':
                with connect() as db:
                    user=auth.current(db,self.headers.get('Cookie'))
                    if user:
                        if not secrets.compare_digest(self.headers.get('X-CSRF-Token',''),user['csrf']):
                            return self.send(403,{'error':'Sesi tidak valid. Muat ulang halaman.'})
                        db.execute('DELETE FROM sessions WHERE token_hash=?',(user['token_hash'],))
                return self.send(200,{'ok':True},cookie='drilling_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0')
            data = self.body()
            if path == '/api/login':
                with connect() as db: result=auth.login(db,str(data.get('username','')),str(data.get('password','')),str(data.get('remember',''))=='1')
                if not result:return self.send(401,{'error':'Nama akun atau kata sandi salah'})
                return self.send(200,{k:result[k] for k in ('username','role','csrf')},cookie=f"drilling_session={result['token']}; HttpOnly; SameSite=Strict; Path=/"+('; Max-Age=2592000' if str(data.get('remember',''))=='1' else ''))
            user=self.identity(path,'POST')
            if user is None:return
            if path.startswith('/api/ddr/') or (path.startswith('/api/reports/') and path.endswith('/billing')):
                from ddr_routes import post
                return post(self,path,data,user)
            if path == '/api/rigs':
                from rig_master import create
                return self.send(201,create(data,user['username']))
            if path == '/api/rigs/update':
                from rig_master import update
                return self.send(200,update(data,user['username']))
            if path == '/api/users':
                username=str(data.get('username','')).strip();password=str(data.get('password',''));role=str(data.get('role',''))
                if not username or role not in auth.ROLES:raise ValueError('Nama akun atau peran tidak valid')
                with connect() as db:
                    cur=db.execute('INSERT INTO users(username,password_hash,role) VALUES(?,?,?)',(username,auth.hash_password(password),role))
                    auth.event(db,user['username'],'USER_CREATED:'+username)
                return self.send(201,{'id':cur.lastrowid})
            if path == '/api/account/password':
                old=str(data.get('old_password') or '');new=str(data.get('new_password') or '')
                with connect() as db:
                    row=db.execute('SELECT password_hash FROM users WHERE id=?',(user['id'],)).fetchone()
                    if not auth.verify(old,row['password_hash']):return self.send(403,{'error':'Kata sandi saat ini salah'})
                    db.execute('UPDATE users SET password_hash=? WHERE id=?',(auth.hash_password(new),user['id']))
                    db.execute('DELETE FROM sessions WHERE user_id=?',(user['id'],))
                    auth.event(db,user['username'],'PASSWORD_CHANGED')
                return self.send(200,{'ok':True},cookie='drilling_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0')
            if path == '/api/users/status':
                ident=int(data['id']);active=int(data['active'])
                if active not in (0,1) or ident==user['id']:raise ValueError('Status akun tidak valid')
                with connect() as db:
                    if not db.execute('SELECT 1 FROM users WHERE id=?',(ident,)).fetchone():return self.send(404,{'error':'Akun tidak ditemukan'})
                    db.execute('UPDATE users SET active=? WHERE id=?',(active,ident))
                    db.execute('DELETE FROM sessions WHERE user_id=?',(ident,))
                    auth.event(db,user['username'],f'ACCOUNT_STATUS:{ident}:{active}')
                return self.send(200,{'ok':True})
            if path == '/api/users/reset':
                ident=int(data['id']);password=str(data['password'])
                with connect() as db:
                    if not db.execute('SELECT 1 FROM users WHERE id=?',(ident,)).fetchone():return self.send(404,{'error':'Akun tidak ditemukan'})
                    db.execute('UPDATE users SET password_hash=? WHERE id=?',(auth.hash_password(password),ident))
                    db.execute('DELETE FROM sessions WHERE user_id=?',(ident,))
                    auth.event(db,user['username'],f'PASSWORD_RESET:{ident}')
                return self.send(200,{'ok':True})
            if path == '/api/targets':
                return self.send(410,{'error':'Rencana dasar dibekukan demi riwayat. Atur target pada tanggal, bulan, atau tahun tertentu.'})
            if path == '/api/targets/period':
                from period_targets import save
                return self.send(200,save(data,user['username']))
            if path == '/api/admin/delete':
                from modules import delete_record
                return self.send(200,delete_record(data.get('entity'),data.get('id'),data.get('reason'),user['username']))
            if path.startswith('/api/v2/'):
                from modules import create
                data['actor']=user['username']
                return self.send(201,create(path.split('/')[3],data))
            if path == '/api/reports':
                if user['role']=='operator' and (not isinstance(data.get('ddr_detail'),dict) or data['ddr_detail'].get('version')!=2):raise ValueError('Gunakan form DDR terbaru dan lengkapi detail aktivitas/hole.')
                data['operator']=user['username']
                return self.create_report(data)
            if path.startswith('/api/reports/') and path.endswith('/resubmit'):
                data['operator']=user['username'];data['_editor']=user['username']
                return self.create_report(data,int(path.split('/')[3]))
            if path.startswith('/api/reports/') and path.endswith('/review'):
                data['supervisor']=user['username'];data['_review_role']=user['role']
                return self.review(int(path.split('/')[3]),data)
            return self.send(404, {'error':'Tidak ditemukan'})
        except Exception as e:
            from period_targets import Conflict
            if isinstance(e,Conflict):return self.send(409,{'error':str(e)})
            if isinstance(e,sqlite3.IntegrityError):return self.send(409,{'error':'Data duplikat, referensi tidak ada, atau melanggar aturan database.'})
            if isinstance(e,sqlite3.OperationalError):return self.send(503,{'error':'Database belum siap atau sedang sibuk. Coba kembali.'})
            if not isinstance(e,(ValueError,KeyError,TypeError,json.JSONDecodeError)):raise
            return self.send(400, {'error':str(e),'field':getattr(e,'field','form'),'code':getattr(e,'code','validation')})

    def create_report(self, d, resubmit_id=None):
        client_id=str(d.get('client_request_id') or '').strip() if resubmit_id is None else ''
        request_hash=hashlib.sha256(json.dumps({k:v for k,v in d.items() if k!='client_request_id'},sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest() if client_id else None
        if client_id:
            import uuid
            try: client_id=str(uuid.UUID(client_id))
            except ValueError: raise ValueError('Identitas kirim DDR tidak valid')
            with connect() as db:
                existing=db.execute('SELECT id,client_request_hash FROM reports WHERE operator=? AND client_request_id=?',(str(d['operator']),client_id)).fetchone()
            if existing:
                if existing['client_request_hash']!=request_hash:return self.send(409,{'error':'Identitas kirim sudah dipakai untuk isi DDR yang berbeda; periksa laporan tersimpan'})
                return self.send(200,{'id':existing['id'],'duplicate':True})
        date = str(d['work_date'])
        if datetime.strptime(date,'%Y-%m-%d').strftime('%Y-%m-%d')!=date:raise ValueError('Tanggal tidak valid')
        shift = str(d['shift'])
        if shift not in ('Day','Night'): raise ValueError('Shift tidak valid')
        start,end = float(d['start_depth']),float(d['end_depth'])
        if not math.isfinite(start) or not math.isfinite(end):raise ValueError('Kedalaman tidak valid')
        if start < 0 or end < start: raise ValueError('End depth harus ≥ start depth')
        start_time,end_time = str(d['start_time']),str(d['end_time'])
        for t in (start_time,end_time): datetime.strptime(t,'%H:%M')
        duration = (int(end_time[:2])*60+int(end_time[3:]))-(int(start_time[:2])*60+int(start_time[3:]))
        if duration <= 0: duration += 1440
        downtime = int(d.get('downtime_min') or 0)
        if downtime < 0 or downtime > duration: raise ValueError('Downtime melebihi durasi shift')
        category = str(d.get('downtime_category') or 'None')
        if category not in ('None','Breakdown','Standby','Weather','Administrative','Other'): raise ValueError('Kategori downtime tidak valid')
        operator = str(d['operator']).strip()
        if not operator: raise ValueError('Nama operator wajib diisi')
        rig_id = int(d['rig_id'])
        program_id = int(d['program_id']) if d.get('program_id') else None
        equipment_id = int(d['equipment_id']) if d.get('equipment_id') else None
        rod_used=int(d.get('rod_used') or 0); mud_used=float(d.get('mud_used') or 0)
        if rod_used < 0 or not math.isfinite(mud_used) or mud_used < 0: raise ValueError('Pemakaian material tidak valid')
        detail_data=ddr_detail.parse(d['ddr_detail'],start,end,start_time,end_time) if d.get('ddr_detail') is not None else None
        if detail_data is not None:
            detail_data['identity']['day']=datetime.strptime(date,'%Y-%m-%d').strftime('%A')
            detail_data['summary']['total_meter_m']=round(end-start,2)
            detail_data['summary']['shift_hours']=round(duration/60,2)
            from ddr_metrics import hours
            time_minutes,_=hours({'ddr_detail':detail_data})
            downtime=time_minutes['maintenance']
            category='Breakdown' if downtime else 'None'
        if downtime and category == 'None': raise ValueError('Pilih kategori downtime')
        ddr_detail.validate_preparer(detail_data)
        detail_data['identity']['preparer_confirmed_by']=str(d.get('_editor') or d['operator'])
        detail_data['identity']['preparer_confirmed_at']=now()
        detail_json=json.dumps(detail_data,ensure_ascii=False)
        measurements=[float(d[k]) if d.get(k) not in ('',None) else None for k in ('wob','rpm','torque','pump_pressure')]
        if any(v is not None and (not math.isfinite(v) or v<0) for v in measurements):raise ValueError('Parameter rig tidak valid')
        with connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if client_id:
                existing=db.execute('SELECT id,client_request_hash FROM reports WHERE operator=? AND client_request_id=?',(str(d['operator']),client_id)).fetchone()
                if existing:
                    if existing['client_request_hash']!=request_hash:return self.send(409,{'error':'Identitas kirim sudah dipakai untuk isi DDR yang berbeda; periksa laporan tersimpan'})
                    return self.send(200,{'id':existing['id'],'duplicate':True})
            if resubmit_id is not None:
                original=db.execute('SELECT * FROM reports WHERE id=?',(resubmit_id,)).fetchone()
                if not original:return self.send(404,{'error':'Laporan tidak ditemukan'})
                if not str(d.get('correction_reason','')).strip():raise ValueError('Alasan koreksi wajib diisi')
                if int(d.get('expected_revision',-1))!=original['revision']:
                    return self.send(409,{'error':'DDR berubah sejak dibuka. Muat ulang sebelum koreksi.'})
                operator=original['operator']
            import ddr_rules
            check=dict(d,ddr_detail=detail_data)
            ddr_rules.validate(db,check,resubmit_id or 0)
            if detail_data and detail_data.get('version')==2:
                expected_units=ddr_rules.units(db,rig_id)
                historical_units=resubmit_id is not None and original['rig_id']==rig_id and detail_data.get('units')==ddr_rules.detail(dict(original)).get('units')
                if detail_data.get('readings') and detail_data.get('units')!=expected_units and not historical_units:raise ValueError('Satuan rig berubah atau belum sesuai master; muat ulang data rig.')
            rig = db.execute('SELECT id,active FROM rigs WHERE id=?',(rig_id,)).fetchone()
            if not rig: raise ValueError('Rig tidak ditemukan')
            if not rig['active'] and resubmit_id is None:raise ValueError('Rig tidak aktif. Pilih rig aktif atau hubungi admin.')
            if program_id and not db.execute('SELECT 1 FROM programs WHERE id=?',(program_id,)).fetchone(): raise ValueError('Program tidak ditemukan')
            equipment=None; bit_used=str(d.get('bit_used') or '').strip()
            if equipment_id:
                equipment=db.execute('SELECT id,serial,kind,rig_id,installed_depth,retired_depth,status FROM equipment WHERE id=?',(equipment_id,)).fetchone()
                if not equipment: raise ValueError('Bit/equipment tidak ditemukan')
                if equipment['kind']!='Bit': raise ValueError('Equipment DDR harus berjenis Bit')
                historic_equipment=resubmit_id is not None and original['equipment_id']==equipment_id and original['rig_id']==rig_id
                if equipment['status']!='Active' and not historic_equipment: raise ValueError('Bit/equipment sudah tidak aktif')
                if equipment['rig_id'] is not None and equipment['rig_id']!=rig_id and not historic_equipment: raise ValueError('Bit/equipment terdaftar pada rig lain')
                if (detail_data or {}).get('version')!=2 and end <= equipment['installed_depth']: raise ValueError('Interval DDR belum mencapai kedalaman pasang bit/equipment')
                bit_used=equipment['serial']
            values=(rig_id,date,shift,start,end,start_time,end_time,downtime,category,bit_used,rod_used,mud_used,
                    *measurements,str(d.get('note') or '').strip(),operator,original['created_at'] if resubmit_id else now(),program_id,equipment_id)
            if resubmit_id is None:
                # Deleted report numbers must never identify a new report.
                next_id=db.execute("SELECT MAX(value)+1 FROM (SELECT COALESCE(MAX(id),0) value FROM reports UNION ALL SELECT COALESCE(MAX(entity_id),0) FROM deletion_log WHERE entity='reports' UNION ALL SELECT COALESCE(MAX(report_id),0) FROM report_revisions)").fetchone()[0]
                cursor=db.execute('''INSERT INTO reports(id,rig_id,work_date,shift,start_depth,end_depth,start_time,end_time,downtime_min,downtime_category,bit_used,rod_used,mud_used,wob,rpm,torque,pump_pressure,note,operator,created_at,program_id,equipment_id)
                  VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(next_id,*values))
                report_id=cursor.lastrowid
            else:
                db.execute('''UPDATE reports SET rig_id=?,work_date=?,shift=?,start_depth=?,end_depth=?,start_time=?,end_time=?,downtime_min=?,downtime_category=?,bit_used=?,rod_used=?,mud_used=?,wob=?,rpm=?,torque=?,pump_pressure=?,note=?,operator=?,created_at=?,program_id=?,equipment_id=?,status='Submitted',supervisor=NULL,review_note=NULL,reviewed_at=NULL WHERE id=?''',(*values,resubmit_id))
                report_id=resubmit_id
            if resubmit_id is None or original['rig_id'] != rig_id:
                db.execute('UPDATE reports SET rig_code_snapshot=(SELECT code FROM rigs WHERE id=?),rig_location_snapshot=(SELECT location FROM rigs WHERE id=?) WHERE id=?',(rig_id,rig_id,report_id))
            if not resubmit_id:
                db.execute('UPDATE reports SET client_request_id=?,client_request_hash=? WHERE id=?',(client_id or None,request_hash,report_id))
            snapshot=original['pricing_snapshot'] if resubmit_id and original['work_date']==date and original['pricing_snapshot'] else json.dumps(ddr_rules.priced(db,d))
            bill=original['billing_status'] if resubmit_id else ('Pending' if (detail_data or {}).get('redrill',{}).get('kind')=='Redrill' else 'Billable')
            if resubmit_id and ddr_rules.detail(dict(original)).get('redrill',{}).get('kind','Normal')!=(detail_data or {}).get('redrill',{}).get('kind','Normal'):bill='Pending'
            db.execute('UPDATE reports SET ddr_detail=?,hole_code=?,pricing_snapshot=?,billing_status=?,revision=revision+? WHERE id=?',(detail_json,(detail_data or {}).get('identity',{}).get('hole',''),snapshot,bill,1 if resubmit_id else 0,report_id))
            if resubmit_id:
                after=dict(db.execute('SELECT * FROM reports WHERE id=?',(report_id,)).fetchone())
                db.execute('INSERT INTO report_revisions(report_id,revision,before_json,after_json,reason,actor,at) VALUES(?,?,?,?,?,?,?)',(report_id,after['revision'],json.dumps(dict(original)),json.dumps(after),str(d['correction_reason']).strip(),d['_editor'],now()))
            detail={'meterage':end-start,'shift':shift,'ddr_format':'Master DDR_JO' if detail_data else 'legacy'}
            if equipment: detail.update({'equipment_id':equipment['id'],'equipment_serial':equipment['serial']})
            db.execute('INSERT INTO audit(report_id,action,actor,at,detail) VALUES(?,?,?,?,?)',(report_id,'CORRECTED' if resubmit_id else 'SUBMITTED',d.get('_editor',operator),now(),json.dumps(detail)))
            # A successful response must only leave after the DDR is committed,
            # so offline clients can safely remove the accepted outbox entry.
            db.commit()
            return self.send(200 if resubmit_id else 201,{'id':report_id})

    def review(self, ident, d):
        action = str(d['action'])
        supervisor = str(d['supervisor']).strip()
        note = str(d.get('note') or '').strip()
        if action not in ('Approved','Rejected') or not supervisor: raise ValueError('Review tidak valid')
        if action == 'Rejected' and not note: raise ValueError('Alasan penolakan wajib diisi')
        with connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT status,operator,revision FROM reports WHERE id=?',(ident,)).fetchone()
            if not row: return self.send(404,{'error':'Laporan tidak ditemukan'})
            if int(d.get('expected_revision',-1))!=row['revision']:
                return self.send(409,{'error':'DDR berubah sejak dibuka. Muat ulang sebelum review.'})
            if row['status'] != 'Submitted': return self.send(409,{'error':'Laporan sudah direview'})
            if row['operator']==supervisor and d.get('_review_role')!='admin':return self.send(403,{'error':'Pembuat DDR tidak dapat menyetujui laporannya sendiri'})
            db.execute('UPDATE reports SET status=?,supervisor=?,review_note=?,reviewed_at=?,revision=revision+1 WHERE id=?',(action,supervisor,note,now(),ident))
            db.execute('INSERT INTO audit(report_id,action,actor,at,detail) VALUES(?,?,?,?,?)',(ident,action.upper(),supervisor,now(),note))
            db.commit()
            return self.send(200,{'status':action})

if __name__ == '__main__':
    init()
    from modules import initialize
    initialize()
    from period_targets import initialize as initialize_period_targets
    initialize_period_targets()
    from identities import initialize as initialize_identities
    initialize_identities()
    with connect() as db:auth.initialize(db)
    port = int(os.environ.get('PORT') or os.environ.get('DRILLING_PORT','8765'))
    host = os.environ.get('DRILLING_HOST', '0.0.0.0' if os.environ.get('PORT') else '127.0.0.1')
    print(f'Drilling Intelligence: http://{host}:{port}')
    ThreadingHTTPServer((host,port),Handler).serve_forever()
