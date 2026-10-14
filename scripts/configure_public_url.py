"""Configure one exact allowed public origin; never print .env secrets."""
from pathlib import Path
from urllib.parse import urlsplit
from datetime import datetime
import shutil
from dotenv import set_key

root=Path(__file__).resolve().parents[1]
env=root/'.env'
if not env.exists():raise SystemExit('Run Install.bat first.')
mode=input('Configure demo tunnel or live domain? Enter demo or live: ').strip().lower()
if mode not in ['demo','live']:raise SystemExit('No changes: choose demo or live.')
value=input('Paste the HTTPS address only (no /api path): ').strip().rstrip('/')
p=urlsplit(value)
if p.scheme!='https' or not p.hostname or p.path or p.query or p.fragment or p.username or p.password:
    raise SystemExit('No changes: enter an HTTPS origin such as https://tips.example.com')
backup=root/'configuration-backups'/datetime.now().strftime('%Y%m%d-%H%M%S-%f')
backup.mkdir(parents=True)
shutil.copy2(env,backup/'.env')
set_key(str(env),'DEMO_PUBLIC_BASE_URL' if mode=='demo' else 'PUBLIC_BASE_URL',value)
if mode=='live':set_key(str(env),'COOKIE_SECURE','true')
print('Saved. Restart the server. Live admin login uses the HTTPS address when secure cookies are enabled.')
print('Configuration backup contains secrets: keep configuration-backups private.')
