"""Stable QR identities with tombstones so deleted labels never point to reused row IDs."""
import secrets
from app import connect, now

TABLES={'boxes':'core_boxes','samples':'samples'}

def initialize():
    with connect() as db:
        db.executescript('''CREATE TABLE IF NOT EXISTS tracking_tokens (
          token TEXT PRIMARY KEY, kind TEXT NOT NULL CHECK(kind IN ('boxes','samples')),
          object_id INTEGER NOT NULL, active INTEGER NOT NULL CHECK(active IN (0,1)), created_at TEXT NOT NULL);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_active_tracking ON tracking_tokens(kind,object_id) WHERE active=1;''')
        for kind,table in TABLES.items():
            for row in db.execute(f'''SELECT x.id FROM {table} x LEFT JOIN tracking_tokens t
              ON t.kind=? AND t.object_id=x.id AND t.active=1 WHERE t.token IS NULL''',(kind,)).fetchall():
                db.execute('INSERT INTO tracking_tokens(token,kind,object_id,active,created_at) VALUES(?,?,?,1,?)',(secrets.token_hex(16),kind,row['id'],now()))

def issue(db,kind,ident):
    token=secrets.token_hex(16)
    db.execute('INSERT INTO tracking_tokens(token,kind,object_id,active,created_at) VALUES(?,?,?,1,?)',(token,kind,ident,now()))
    return token

def retire(db,kind,ident):
    db.execute('UPDATE tracking_tokens SET active=0 WHERE kind=? AND object_id=? AND active=1',(kind,ident))

def token_for(db,kind,ident):
    row=db.execute('SELECT token FROM tracking_tokens WHERE kind=? AND object_id=? AND active=1',(kind,ident)).fetchone()
    return row['token'] if row else None

def resolve(db,kind,token):
    row=db.execute('SELECT object_id FROM tracking_tokens WHERE kind=? AND token=? AND active=1',(kind,token)).fetchone()
    return row['object_id'] if row else None
