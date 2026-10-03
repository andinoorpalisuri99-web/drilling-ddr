"""Local account, role, and session controls. Bind the app to localhost by default."""
import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone
from http.cookies import SimpleCookie

ROLES=('admin','operator','supervisor','geologist','stores','finance','manager','viewer')

def hash_password(password,salt=None,allow_short=False):
    if len(password)<12 and not allow_short: raise ValueError('Kata sandi minimal 12 karakter')
    salt=salt or secrets.token_bytes(16)
    digest=hashlib.scrypt(password.encode(),salt=salt,n=2**14,r=8,p=1)
    return salt.hex()+':'+digest.hex()

def verify(password,stored):
    try:
        salt,digest=stored.split(':')
        actual=hashlib.scrypt(password.encode(),salt=bytes.fromhex(salt),n=2**14,r=8,p=1)
        return hmac.compare_digest(actual,bytes.fromhex(digest))
    except (ValueError,TypeError): return False

def initialize(db):
    db.executescript('''CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, role TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1);
    CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), csrf TEXT NOT NULL, expires_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS security_events(id INTEGER PRIMARY KEY, username TEXT NOT NULL, action TEXT NOT NULL, at TEXT NOT NULL);''')
    if not db.execute('SELECT 1 FROM users').fetchone():
        password=os.environ.get('DRILLING_ADMIN_PASSWORD') or '12345678'
        db.execute('INSERT INTO users(username,password_hash,role) VALUES(?,?,?)',('admin',hash_password(password,allow_short=password=='12345678'),'admin'))
        print('FIRST RUN ADMIN USER: admin',flush=True)
        print('FIRST RUN ADMIN PASSWORD: '+password,flush=True)
        print('Simpan kata sandi ini; hanya ditampilkan saat akun pertama dibuat.',flush=True)

def event(db,username,action):
    db.execute('INSERT INTO security_events(username,action,at) VALUES(?,?,?)',(username,action,datetime.now(timezone.utc).isoformat()))

def login(db,username,password,remember=False):
    since=(datetime.now(timezone.utc)-timedelta(minutes=15)).isoformat()
    attempts=db.execute("SELECT COUNT(*) FROM security_events WHERE username=? AND action IN ('LOGIN_FAILED','LOGIN_THROTTLED') AND at>?",(username,since)).fetchone()[0]
    if attempts>=8:
        event(db,username,'LOGIN_THROTTLED');return None
    row=db.execute('SELECT * FROM users WHERE username=? AND active=1',(username,)).fetchone()
    if not row or not verify(password,row['password_hash']):
        event(db,username,'LOGIN_FAILED');return None
    token=secrets.token_urlsafe(32);csrf=secrets.token_urlsafe(24)
    expiry=(datetime.now(timezone.utc)+timedelta(days=30) if remember else datetime.now(timezone.utc)+timedelta(hours=8)).isoformat()
    db.execute('INSERT INTO sessions(token_hash,user_id,csrf,expires_at) VALUES(?,?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),row['id'],csrf,expiry))
    event(db,username,'LOGIN_SUCCESS')
    return {'token':token,'csrf':csrf,'username':row['username'],'role':row['role']}

def current(db,cookie_header):
    try:
        cookie=SimpleCookie();cookie.load(cookie_header or '');token=cookie['drilling_session'].value
    except (KeyError,ValueError):return None
    row=db.execute('''SELECT u.id,u.username,u.role,s.csrf,s.expires_at,s.token_hash FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND u.active=1''',(hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
    if not row or row['expires_at']<=datetime.now(timezone.utc).isoformat():return None
    return dict(row)

def allowed(role,path,method):
    if path=='/api/drilling-map':return method=='GET' and role in ROLES
    if role=='admin':return True
    if role=='operator':
        if method=='GET':return path in ('/api/rigs','/api/reports','/api/ddr/summary','/api/ddr/units','/api/ddr/context','/api/v2/equipment','/api/v2/programs') or (path.startswith('/api/reports/') and path.rsplit('/',1)[-1] in ('audit','pdf','xlsx'))
        return path in ('/api/reports','/api/account/password')
    if method=='GET':
        if path=='/api/ddr/summary':return True
        if path=='/api/ddr/commercial':return role in ('finance','manager')
        if path.startswith('/api/reports/') and path.rsplit('/',1)[-1] in ('pdf','xlsx'):return True
        if path in ('/api/rigs','/api/reports','/api/targets','/api/targets/period'):return True
        if path=='/api/management':return role in ('finance','manager')
        if path in ('/api/label','/api/label/page','/api/tracking'):return role in ('geologist','manager','viewer')
        if path.startswith('/api/reports/') and path.endswith('/audit'):return True
        if path.startswith('/api/v2/'):
            name=path.split('/')[3]
            if role=='viewer':return name in ('equipment','materials','stock','boxes','samples','custody')
            return (name in ('equipment','materials','stock') and role in ('stores','manager')) or (name in ('boxes','samples','custody') and role in ('geologist','manager','viewer')) or (name in ('programs','expenses','invoices') and role in ('finance','manager')) or (name in ('equipment','programs') and role=='operator')
        return False
    if path=='/api/account/password':return True
    if path=='/api/reports':return role=='operator'
    if path.startswith('/api/reports/') and path.endswith('/resubmit'):return False
    if path.startswith('/api/reports/') and path.endswith('/review'):return role=='supervisor'
    if path=='/api/targets/period':return role=='manager'
    if path.startswith('/api/v2/'):
        name=path.split('/')[3]
        return (name in ('equipment','retire','materials','stock') and role=='stores') or (name in ('boxes','samples','custody','qa') and role=='geologist') or (name in ('programs','expenses','invoices') and role=='finance')
    return False
