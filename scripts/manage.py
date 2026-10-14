import argparse,getpass,os,secrets,shutil,sqlite3,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT));os.chdir(ROOT)
from dotenv import load_dotenv,set_key
from werkzeug.security import generate_password_hash
from acepressure.domain import Store
p=argparse.ArgumentParser();p.add_argument('command',choices=['backup','restore','reset-password','rotate-bridge','rotate-overlay']);p.add_argument('--file');args=p.parse_args()
load_dotenv(ROOT/'.env');directory=os.getenv('DATA_DIR','data')
if args.command=='reset-password':
    pw=getpass.getpass('New password (12+ characters): ')
    if len(pw)<12:sys.exit('Too short')
    if getpass.getpass('Repeat password: ')!=pw:sys.exit('Passwords differ')
    if not os.getenv('IDENTITY_SECRET'):set_key(ROOT/'.env','IDENTITY_SECRET',os.environ['APP_SECRET'])
    set_key(ROOT/'.env','ADMIN_PASSWORD_HASH',generate_password_hash(pw));set_key(ROOT/'.env','APP_SECRET',secrets.token_urlsafe(48));print('Password reset; restart server. Existing logins invalidated. Supporter grouping is preserved.')
elif args.command.startswith('rotate-'):
    key='BRIDGE_TOKEN' if args.command.endswith('bridge') else 'OVERLAY_TOKEN'
    set_key(ROOT/'.env',key,secrets.token_urlsafe(48));print('Token updated in .env. Restart server and update the affected clients.')
elif args.command=='backup':
    s=Store(directory,os.environ['APP_SECRET']);print(s.backup())
elif args.command=='restore':
    if not args.file:sys.exit('--file backup.sqlite3 is required. Stop the server before restoring.')
    if input('Stop the server first. Type RESTORE to replace the database after a backup: ')!='RESTORE':sys.exit(1)
    source=Path(args.file).resolve()
    with sqlite3.connect('file:'+source.as_posix()+'?mode=ro',uri=True) as db:
        if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':sys.exit('Backup integrity check failed')
        if not db.execute("SELECT name FROM sqlite_master WHERE name='tips'").fetchone():sys.exit('Not an AcePressure database')
    s=Store(directory,os.environ['APP_SECRET']);print('Pre-restore backup:',s.backup())
    for suffix in ['-wal','-shm']:Path(str(s.dbpath)+suffix).unlink(missing_ok=True)
    shutil.copy2(source,s.dbpath);print('Restored. Restart server and check totals.')
