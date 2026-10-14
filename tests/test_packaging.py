import hashlib,json,os,shutil,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def test_migration_preserves_original(tmp_path):
    target=tmp_path/'package';(target/'scripts').mkdir(parents=True)
    shutil.copy2(ROOT/'scripts'/'migrate_obs.py',target/'scripts'/'migrate_obs.py')
    source=tmp_path/'original.json';payload={'name':'Original','sources':[{'name':'Weekly Support Goal','id':'browser_source','settings':{'is_local_file':True,'local_file':'old.html'}},{'name':'YouTube Alerts - Horizontal','id':'browser_source','settings':{'url':'https://example.test/private-token'}}]}
    source.write_text(json.dumps(payload),encoding='utf-8');before=source.read_bytes()
    r=subprocess.run([sys.executable,str(target/'scripts'/'migrate_obs.py'),str(source)],env=os.environ|{'OVERLAY_TOKEN':'o'*48,'PUBLIC_BASE_URL':'https://example.test'},capture_output=True,text=True)
    assert r.returncode==0,r.stderr
    assert source.read_bytes()==before
    generated=list(target.glob('data/migration-backups/*/AcePressure_Database_Goals.json'));assert len(generated)==1
    d=json.loads(generated[0].read_text(encoding='utf-8'));assert d['sources'][1]==payload['sources'][1];assert d['sources'][0]['settings']['height']==180;assert '/overlay/goal?' in d['sources'][0]['settings']['url']
    assert (generated[0].parent/source.name).read_bytes()==before

def test_preserved_original_manifest():
    manifest=json.loads((ROOT/'legacy'/'manifest.json').read_text(encoding='utf-8'))
    assert len(manifest)==12
    for item in manifest:
        p=ROOT/'legacy'/'original-uploads'/item['file'];assert hashlib.sha256(p.read_bytes()).hexdigest()==item['sha256']
