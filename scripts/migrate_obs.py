"""Creates NEW scene-collection JSON and backups. Never edits your OBS profile in place."""
import argparse,copy,json,os,shutil,sys,time
from pathlib import Path
from urllib.parse import urlencode
ROOT=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT/'.env')
p=argparse.ArgumentParser();p.add_argument('collection',type=Path);p.add_argument('--base',default=os.getenv('PUBLIC_BASE_URL','http://localhost:8765'));p.add_argument('--goal',default='');a=p.parse_args()
original=a.collection.resolve()
if not original.is_file():sys.exit('Select an exported OBS scene collection JSON.')
folder=ROOT/'data'/'migration-backups'/time.strftime('%Y%m%d-%H%M%S');folder.mkdir(parents=True,exist_ok=False)
shutil.copy2(original,folder/original.name)
old=Path(r'D:\Stream Assets\AcePressure')
if old.exists():shutil.copytree(old,folder/'old-stream-assets')
data=json.loads(original.read_text(encoding='utf-8-sig'));key=os.getenv('OVERLAY_TOKEN')
if not key:sys.exit('Run installation first; OVERLAY_TOKEN is missing.')
url=a.base.rstrip('/')+'/overlay/goal?'+urlencode({'key':key,**({'goal':a.goal} if a.goal else {})})
changes=[]
def visit(value):
    if isinstance(value,dict):
        if value.get('id')=='browser_source' and value.get('name')=='Weekly Support Goal':
            settings=value.setdefault('settings',{});settings.update(url=url,is_local_file=False,local_file='',width=700,height=180)
            changes.append('Weekly Support Goal: local HTML → database goal URL')
        # Streamlabs/BotRix/YouTube alerts, static QR and unrelated sources are preserved.
        for v in value.values():visit(v)
    elif isinstance(value,list):
        for v in value:visit(v)
visit(data);data['name']=str(data.get('name','AcePressure'))+' - Database Goals'
out=folder/'AcePressure_Database_Goals.json';out.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
(folder/'migration-report.txt').write_text('\n'.join(changes) or 'No named Weekly Support Goal browser source found. Set OBS URLs manually.',encoding='utf-8')
print('Original preserved. Backup + new collection:',folder)
print('Import the NEW collection in OBS; inspect transforms before using live. Add tip alert sources and hide the old direct-payment QR manually.')
