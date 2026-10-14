"""1.6.7: the Sound library and the Design studio take several files at once, and Design studio files keep the names they were
uploaded with."""
import io
import struct
import wave
from pathlib import Path

from PIL import Image

from acepressure.domain import known_uploads

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / 'acepressure' / 'static'


def read(name):
    return (STATIC / name).read_text(encoding='utf-8')


def block(src, start, end='\n}'):
    i = src.index(start); return src[i:src.index(end, i)]


def png(color=(220, 50, 80, 255)):
    out = io.BytesIO(); Image.new('RGBA', (32, 32), color).save(out, format='PNG'); out.seek(0); return out


def wav(seconds=0.2):
    out = io.BytesIO()
    with wave.open(out, 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(8000)
        w.writeframes(b''.join(struct.pack('<h', (i * 37) % 2000 - 1000) for i in range(int(8000 * seconds))))
    out.seek(0); return out


# ---------- Design studio: the names files were uploaded with ----------
class TestDesignStudioNames:
    def test_an_upload_returns_and_keeps_its_original_name(self, admin):
        c, h = admin
        r = c.post('/api/admin/visual-assets', data={'file': (png(), 'My Logo.png')}, headers=h)
        assert r.status_code == 200 and r.json['original_name'] == 'My Logo.png' and r.json['name'].endswith('.png')
        d = c.get('/api/admin/visuals', headers=h).json
        assert r.json['name'] in d['assets'] and d['asset_labels'][r.json['name']] == 'My Logo.png'

    def test_several_uploads_with_the_same_name_stay_apart(self, admin):
        c, h = admin
        names = [c.post('/api/admin/visual-assets', data={'file': (png((i * 60, 10, 10, 255)), 'frame.png')}, headers=h).json['name'] for i in range(3)]
        d = c.get('/api/admin/visuals', headers=h).json
        assert len(set(names)) == 3 and all(d['asset_labels'][n] == 'frame.png' for n in names)

    def test_a_path_in_the_filename_is_never_kept(self, admin):
        c, h = admin
        # Browsers send only the base name, but the server never trusts that.
        r = c.post('/api/admin/visual-assets', data={'file': (png(), '../../Users/me/Desktop/art\u202e.png')}, headers=h)
        assert r.status_code == 200 and r.json['original_name'] == 'art.png'

    def test_files_from_before_have_no_label_and_missing_files_are_not_listed(self, admin, tmp_path):
        c, h = admin
        media = tmp_path / 'media'; media.mkdir(exist_ok=True)
        (media / 'oldfile123.png').write_bytes(png().getvalue())  # uploaded by 1.6.6: no label
        r = c.post('/api/admin/visual-assets', data={'file': (png(), 'gone.png')}, headers=h)
        (media / r.json['name']).unlink()  # deleted outside the app
        d = c.get('/api/admin/visuals', headers=h).json
        assert 'oldfile123.png' in d['assets'] and 'oldfile123.png' not in d['asset_labels']
        assert r.json['name'] not in d['asset_labels'] and r.json['name'] not in d['assets']

    def test_an_alert_bundle_visual_keeps_its_name_too(self, admin):
        c, h = admin
        r = c.post('/api/admin/alert-bundle', data={'visual': (png(), 'Hype Frame.png'), 'audio': (wav(), 'boom.wav')}, headers=h)
        assert r.status_code == 200, r.json
        d = c.get('/api/admin/visuals', headers=h).json
        assert d['asset_labels'][r.json['visual']] == 'Hype Frame.png'

    def test_visual_names_never_reach_the_sound_list(self, admin):
        """They are stored as visual_labels, apart from media_labels (alert sounds), so the Sound library and the 1.6.0
        migration never see them."""
        c, h = admin
        r = c.post('/api/admin/visual-assets', data={'file': (png(), 'logo.png')}, headers=h)
        s = c.get('/api/admin/state', headers=h).json['settings']
        assert r.json['name'] in s['visual_labels'] and r.json['name'] not in (s.get('media_labels') or {})
        assert r.json['name'] not in known_uploads(s)
        assert all(e['media_filename'] != r.json['name'] for e in c.get('/api/admin/soundboard', headers=h).json['items'])

    def test_the_settings_form_cannot_write_the_labels(self, admin):
        c, h = admin
        c.post('/api/admin/settings', json={'visual_labels': {'x.png': '<b>bad</b>'}}, headers=h)
        assert 'x.png' not in (c.get('/api/admin/state', headers=h).json['settings'].get('visual_labels') or {})


# ---------- Sound library: several files are several uploads ----------
class TestSeveralSounds:
    def test_the_server_names_each_unnamed_sound_after_its_file_and_keeps_the_default(self, admin):
        """The server side a batch relies on: what Add sound sends for each file when several are chosen (no name, the shared
        fields, make_default 0) gives one row per file. The batch itself is addSounds in admin.js, pinned below and run in Chrome."""
        c, h = admin
        before = c.get('/api/admin/soundboard', headers=h).json
        made = []
        for fname in ('Bruh Moment.wav', 'emotional-damage.wav', 'GG.wav'):
            r = c.post('/api/admin/media', data={'file': (wav(), fname), 'kind': 'sound', 'emoji': '😂', 'category': 'Memes',
                                                 'min_paise': '5000', 'offered': '1', 'make_default': '0'}, headers=h)
            assert r.status_code == 200, r.json
            made.append(r.json['entry'])
        assert [e['name'] for e in made] == ['Bruh Moment', 'emotional-damage', 'GG']
        assert all(e['category'] == 'Memes' and e['emoji'] == '😂' and e['min_paise'] == 5000 and e['enabled'] for e in made)
        after = c.get('/api/admin/soundboard', headers=h).json
        assert after['default'] == before['default'], 'none of them became the default'

    def test_a_bad_file_is_refused_with_a_reason_the_list_can_show(self, admin):
        c, h = admin
        rows = len(c.get('/api/admin/soundboard', headers=h).json['items'])
        bad = c.post('/api/admin/media', data={'file': (io.BytesIO(b'not audio at all'), 'broken.mp3'), 'kind': 'sound', 'offered': '1', 'make_default': '0'}, headers=h)
        assert bad.status_code == 400 and isinstance(bad.json['error'], str) and len(bad.json['error']) > 10
        assert len(c.get('/api/admin/soundboard', headers=h).json['items']) == rows, 'no row for a refused file'
        good = c.post('/api/admin/media', data={'file': (wav(), 'fine.wav'), 'kind': 'sound', 'offered': '1', 'make_default': '0'}, headers=h)
        assert good.status_code == 200 and len(c.get('/api/admin/soundboard', headers=h).json['items']) == rows + 1


# ---------- the two forms ----------
class TestAddSoundTakesSeveralFiles:
    lib = block(read('admin.js'), 'async function library(root){')
    many = block(lib, 'const addSounds=async files=>{', '\n    // One upload at a time')

    def test_the_file_field_takes_several_files(self):
        assert "file=field(f,'Sound files · WAV, MP3 or OGG · up to 30 seconds and 8 MB each · choose several to add them all','file','file')" in self.lib
        assert 'file.required=true;file.multiple=true;' in self.lib

    def test_with_several_files_name_and_default_are_switched_off(self):
        assert "nameField.disabled=makeDefault.disabled=many;nameField.placeholder=many?'Each sound is named after its file':'';if(many)makeDefault.checked=false;add.textContent=many?'Add '+n+' sounds':'Add sound';" in self.lib

    def test_several_files_go_up_one_after_another_with_the_shared_fields(self):
        many = self.many
        assert "try{for(const [i,one] of files.entries()){batch.add.textContent=batch.text='Adding '+(i+1)+' of '+files.length+'…';" in many
        assert "const fd=new FormData();fd.set('file',one,one.name);fd.set('kind','sound');fd.set('emoji',shared.get('emoji')||'');fd.set('category',shared.get('category')||'');" in many
        assert "fd.set('min_paise',String(Math.round(+shared.get('min_rupees')||0)*100));fd.set('offered',shared.has('offered')?'1':'0');fd.set('make_default','0');" in many
        assert many.count('await fetch(') == 1, 'one request at a time, never in parallel'

    def test_the_shared_fields_are_read_once_when_the_batch_starts(self):
        # Editing the form while files upload (getting the next folder ready) must not change the files still to go.
        assert self.many.startswith("const addSounds=async files=>{const done=[],failed=[],shared=new FormData(f);")
        assert self.many.count('new FormData(f)') == 1 and 'offered.checked' not in self.many
        assert "file.disabled=true;addEventListener('beforeunload',hold);" in self.many, 'no new files can be chosen mid-batch'

    def test_a_failing_file_is_listed_and_the_rest_still_go_up(self):
        many = self.many
        assert "if(!r.ok){failed.push([one.name,x.error]);if(r.status===401||r.status===403){stop='sign';left=files.slice(i+1).map(y=>y.name);break;}continue;}" in many
        assert "catch(e){if(!(e instanceof TypeError)){failed.push([one.name,e.message]);continue;}" in many and "tooBig(one,8,'This file')" in many
        assert "box.append(el('p','Not added:'),ul);" in many and "'Not tried, so sign in again and add them: '" in many
        # el() sets textContent: a file name is never read as HTML
        assert 'innerHTML' not in many

    def test_a_lost_connection_stops_the_batch_and_says_what_to_check(self):
        many = self.many
        assert "if(r.status>=502&&r.status<=504)throw TypeError(x.error);" in many, 'Funnel answering for a stopped AcePressure'
        assert "maybe=one.name;stop='down';left=files.slice(i+1).map(y=>y.name);break;" in many
        assert "'The connection dropped while '+maybe+' was uploading, so it may have been added: check Your sounds before adding it again.'" in many
        assert "'Not tried, because AcePressure didn’t answer. Check that it is running and this device is online, then add them again: '" in many

    def test_a_redraw_during_a_batch_shows_it_busy(self):
        assert 'let soundUploads=null,soundBatch=null;' in read('admin.js')
        assert "if(soundBatch){Object.assign(soundBatch,{p2,f,file,add});add.disabled=file.disabled=true;add.textContent=soundBatch.text;}" in self.lib
        assert "const batch=soundBatch={p2,f,file,add,text:''}" in self.many and "finally{removeEventListener('beforeunload',hold);soundBatch=null;}" in self.many
        # after the start the loop only touches the form on screen, through batch
        assert "add.textContent='Adding" not in self.many and 'p2.insertBefore(box,f)' not in self.many

    def test_closing_the_page_mid_batch_asks_first(self):
        assert "hold=e=>{e.preventDefault();e.returnValue='';}" in self.many
        assert self.many.count("addEventListener('beforeunload',hold)") == 1 and self.many.count("removeEventListener('beforeunload',hold)") == 1

    def test_the_report_survives_the_redraw_and_shows_once(self):
        # under the Add button, where you clicked (stay() scrolls back there), now and after the redraw
        assert "soundUploads=box;batch.p2.querySelector('.upload-report')?.remove();batch.f.after(box);" in self.many
        assert 'p2.append(f);\n    if(soundUploads)p2.append(soundUploads);soundUploads=null;' in self.lib
        assert "for(let t=0;refreshing&&t<60;t++)await new Promise(r=>setTimeout(r,50));};" in self.many, 'the redraw after the batch is not skipped'

    def test_the_shared_fields_stay_as_set_after_a_batch(self):
        # form.reset() would untick 'Viewers can pick' and empty Category (field() sets them as properties, not defaults)
        assert 'f.reset()' not in self.many and 'reset()' not in self.many
        assert "batch.file.disabled=batch.add.disabled=false;batch.file.value='';batch.file.onchange();" in self.many

    def test_the_toast_gives_counts_and_the_names_stay_in_the_list(self):
        assert "toast(done.length?count+'.'+(missed?' '+missed+' not added: the list is under Add a sound.':''):'No sounds were added: the list is under Add a sound.');" in self.many

    def test_one_file_works_exactly_as_before(self):
        assert "if(file.files.length>1)return addSounds([...file.files]);\n        const fd=new FormData(f);fd.set('kind','sound');tooBig(fd.get('file'),8,'That sound');" in self.lib
        assert "fd.set('offered',offered.checked?'1':'0');fd.set('make_default',makeDefault.checked?'1':'0');" in self.lib


class TestDesignStudioTakesSeveralFiles:
    js = read('designer.js')
    up = block(js, 'uf.onsubmit=async e=>{', '\n upload.append(uf);')

    def test_the_file_field_takes_several_files(self):
        assert "input=field(uf,'PNG / WebP / GIF (8 MB) or MP4 / WebM (24 MB, 20 seconds) · choose several to upload them all','file','file');" in self.js
        assert "input.required=true;input.multiple=true;" in self.js

    def test_a_second_click_and_new_files_are_ignored_while_files_upload(self):
        assert "uf.onsubmit=async e=>{e.preventDefault();if(go.disabled)return;go.disabled=input.disabled=true;" in self.js
        assert "finally{removeEventListener('beforeunload',hold);artBatch=null;batch.go.disabled=batch.input.disabled=false;batch.go.textContent='Upload image';}};" in self.js

    def test_the_button_says_it_is_uploading_even_for_one_file(self):
        assert "batch.go.textContent=batch.text=files.length>1?'Uploading '+(i+1)+' of '+files.length+'…':'Uploading…';" in self.up

    def test_files_go_up_one_after_another_and_failures_are_listed(self):
        up = self.up
        assert up.count('await fetch(') == 1 and "for(const [i,pick] of files.entries())" in up
        assert "catch(err){if(files.length===1)throw err;if(!(err instanceof TypeError)){failed.push([pick.name,err.message]);continue;}" in up
        assert "out.append(el('p','Not uploaded:'),ul);" in up and 'innerHTML' not in up
        assert "if(files.length===1)toast('Uploaded '+done[0]+'. Select it above, then save.');" in up
        assert "toast(done.length?count+'.'+(missed?' '+missed+' not uploaded: see the list under Upload your artwork.':''):'No files were uploaded: see the list under Upload your artwork.');" in up

    def test_a_sign_out_or_lost_connection_stops_the_batch(self):
        up = self.up
        assert "if(r.status>=502&&r.status<=504)throw TypeError(result.error);" in up
        assert "if(!r.ok){if(files.length>1&&(r.status===401||r.status===403)){failed.push([pick.name,result.error]);stop='sign';left=files.slice(i+1).map(y=>y.name);break;}throw Error(result.error);}" in up
        assert "maybe=pick.name;stop='down';left=files.slice(i+1).map(y=>y.name);break;" in up
        assert "'The connection dropped while '+maybe+' was uploading, so it may have been uploaded: check the menus above before uploading it again.'" in up
        assert "(stop==='sign'?'Not tried, so sign in again and upload them: ':'Not tried, because AcePressure didn’t answer. Check that it is running and this device is online, then upload them again: ')" in up

    def test_a_redraw_during_a_batch_shows_it_busy_and_keeps_the_list(self):
        assert 'let artBatch=null,artReport=null;' in self.js
        assert "if(artBatch){Object.assign(artBatch,{f,go,input,report});go.disabled=input.disabled=true;go.textContent=artBatch.text;}" in self.js
        assert "if(artReport){report.className=artReport.className;report.replaceChildren(...artReport.childNodes);report.hidden=false;artReport=null;}" in self.js
        assert "const batch=artBatch={f,go,input,report,text:''}" in self.up and "out.hidden=false;if(!out.isConnected||stop==='sign')artReport=out;" in self.up
        # uploaded files are added to the menus on screen, not to a page that was redrawn away
        assert "addAsset(batch.f,result.name,result.original_name||pick.name);" in self.up and "batch.input.value='';" in self.up
        # the toast and the list name each file as the menus do, so a second logo.png can be told from the first
        assert "done.push(assetLabel(result.name,result.original_name||pick.name));" in self.up
        assert 'uf.reset()' not in self.up

    def test_closing_the_page_mid_batch_asks_first(self):
        assert "hold=e=>{e.preventDefault();e.returnValue='';};addEventListener('beforeunload',hold);" in self.up
        assert self.up.count("removeEventListener('beforeunload',hold)") == 1

    def test_menus_show_the_uploaded_name_next_to_the_stored_one(self):
        assert "const assetLabel=(name,original)=>original?original+' · '+name:name;" in self.js
        assert "d.assets.map(x=>({value:x,label:assetLabel(x,d.asset_labels?.[x])}))" in self.js
        assert "const opt=el('option',assetLabel(name,original));opt.value=name;select.append(opt);" in self.js
        assert "if(name.endsWith('.webm')&&select.name!=='alert_image')continue;" in self.js, 'a video is still only offered as the alert visual'

    def test_menus_are_sorted_by_the_name_you_know_with_none_first(self):
        assert "const assets=[{value:'',label:'None'},...d.assets.map(x=>({value:x,label:assetLabel(x,d.asset_labels?.[x])})).sort((a,b)=>a.label.localeCompare(b.label,undefined,{numeric:true,sensitivity:'base'}))];" in self.js

    def test_the_bundle_form_still_takes_one_visual_and_one_sound(self):
        lib = block(read('admin.js'), 'async function library(root){')
        bundle = lib[lib.index("const bundle=el('button','Upload bundle','primary wide');") - 1500:lib.index("}).finally(()=>bundle.disabled=false);};")]
        assert 'multiple' not in bundle


def test_long_file_names_wrap_in_the_upload_list():
    css = read('premium.css')
    assert '.upload-report { overflow-wrap: anywhere; }' in css and '.upload-report ul { margin: 6px 0 0; padding-left: 20px; }' in css
    assert "'notice upload-report':'fine upload-report'" in read('admin.js') and "'notice upload-report':'fine upload-report'" in read('designer.js')


def test_version_and_docs():
    assert (ROOT / 'VERSION').read_text(encoding='utf-8').strip() == '1.6.7'
    readme = (ROOT / 'README.md').read_text(encoding='utf-8')
    assert readme.startswith('**Version 1.6.7 — ') and '(docs/UPDATE_1.6.7.md)' in readme
    docs = lambda name: (ROOT / 'docs' / name).read_text(encoding='utf-8')
    changelog = docs('CHANGELOG.md')
    assert changelog.startswith('# 1.6.7 — ') and changelog.index('\n# 1.6.6 — ') < changelog.index('\n# 1.6.5 — ') and '@@' not in changelog
    update = docs('UPDATE_1.6.7.md')
    assert 'tests\\test_release_167.py' in update and 'AcePressure-1.6.6-windows.zip' in update
    assert (ROOT / 'docs' / 'VALIDATION_1.6.7.md').is_file()
    assert docs('TESTING.md').startswith('## Version 1.6.7 validation') and '@@' not in docs('TESTING.md')
    assert '@@' not in docs('VALIDATION_1.6.7.md') and '@@' not in update
