"""First-run local setup. No real payment credentials are bundled."""
import getpass,os,secrets
from pathlib import Path
from werkzeug.security import generate_password_hash
ROOT=Path(__file__).resolve().parent
if __name__=='__main__':
    env=ROOT/'.env'
    if env.exists():
        print('.env already exists; preserving configuration. Use scripts/manage.py for password/token rotation.'); raise SystemExit(0)
    template=ROOT/'.env.example'
    if not template.is_file():
        print('.env.example is missing from this folder. Extract the whole AcePressure zip again, then rerun Install.bat.'); raise SystemExit(1)
    print('AcePressure first-run setup. Password input is hidden.')
    while True:
        password=getpass.getpass('Choose an admin password (at least 12 characters): ')
        if len(password)<12: print('Use at least 12 characters.'); continue
        if getpass.getpass('Repeat password: ')!=password: print('Passwords differ.'); continue
        break
    text=template.read_text(encoding='utf-8')
    for key,value in {'APP_SECRET':secrets.token_urlsafe(48),'IDENTITY_SECRET':secrets.token_urlsafe(48),'BRIDGE_TOKEN':secrets.token_urlsafe(48),'OVERLAY_TOKEN':secrets.token_urlsafe(48),'ADMIN_PASSWORD_HASH':generate_password_hash(password)}.items(): text=text.replace(key+'=\n',key+'='+value+'\n')
    env.write_text(text,encoding='utf-8')
    try: env.chmod(0o600)
    except OSError: pass
    print('Setup complete. Live payments remain disabled until configured. Start.bat opens the server. Start_Demo.bat uses a separate sandbox database.')
