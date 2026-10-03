import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
"""Create the two authorized technician accounts without overwriting existing users."""
import secrets
import app,auth

def provision():
    app.init()
    with app.connect() as db:
        auth.initialize(db)
        created=[]
        for username,name in [('ikhwan.arief','Ikhwan Arief'),('adhitya.rangga','Adhitya Rangga')]:
            row=db.execute('SELECT role,active FROM users WHERE username=?',(username,)).fetchone()
            if row:
                if row['role']!='operator' or not row['active']:
                    db.execute("UPDATE users SET role='operator',active=1 WHERE username=?",(username,))
                    db.execute('DELETE FROM sessions WHERE user_id=(SELECT id FROM users WHERE username=?)',(username,))
                    auth.event(db,'local-admin','TECHNICIAN_ROLE_SET:'+username)
                print(f'{name}: akun {username} aktif sebagai Teknisi; password lama dipertahankan.')
                continue
            password=secrets.token_urlsafe(15)
            db.execute('INSERT INTO users(username,password_hash,role) VALUES(?,?,?)',(username,auth.hash_password(password),'operator'))
            auth.event(db,'local-admin','USER_CREATED:'+username)
            created.append((username,password))
        return created

if __name__=='__main__':
    accounts=provision()
    print('\nSimpan kredensial berikut sebelum menutup terminal. Password tidak disimpan sebagai teks biasa.')
    for user,password in accounts:print(f'User: {user}\nPassword: {password}\nRole: Teknisi\n')
    print('Admin dan data DDR lama tidak diubah. Tidak ada kewajiban mengganti password saat login pertama.')
