"""1.6.0 release-candidate review fixes on the tip page and the admin Sound library (tip[0]-tip[5], admin[0]-admin[2]).
Static checks on public.js, admin.js and premium.css, like the other frontend tests, plus the server contracts those pages
rely on: the price each public sound carries, the 400 backstop for a pick the tip doesn't cover, and the picks switch."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / 'acepressure' / 'static'


def read(name): return (STATIC / name).read_text(encoding='utf-8')


def block(src, start, end='\n}'):
    """Source from `start` to the next `end` (a function body, by default)."""
    i = src.index(start); return src[i:src.index(end, i)]


def line(src, start):
    """The whole line that contains `start`."""
    i = src.index(start); return src[src.rindex('\n', 0, i) + 1:src.index('\n', i)]


# ---------- tip[0]: the amount never clears a pick; Pay refuses a pick the tip doesn't cover, where the viewer can see it ----------
class TestTypingKeepsThePick:
    def test_the_amount_input_only_redraws(self):
        js = read('public.js')
        amount = "$('#amount').addEventListener('input',()=>{renderSoundboardGrid();updateTierMeter();});"
        assert js.count(amount) == 1
        assert not re.search(r"addEventListener\('input',\(\)=>\{[^}]*keepPickAffordable", js), 'typing 150 passes through 1 and 15'

    def test_only_a_reloaded_list_clears_a_pick(self):
        js = read('public.js')
        # Leaving the amount box used to clear the pick, and a tap elsewhere hid that note off-screen: the tip then went out without it.
        assert "addEventListener('change'" not in js and 'pickCheck' not in js
        assert "$('#amount').dispatchEvent(new Event('input'));};});" in js, 'a preset only redraws'
        build = block(js, 'async function buildSoundboard(){')
        assert js.count('keepPickAffordable();') == 1 and 'keepPickAffordable();updateTierMeter();renderSoundboardGrid();' in build

    def test_pay_refuses_a_pick_the_amount_does_not_cover_without_dropping_it(self):
        js = read('public.js'); submit = line(js, "$('#tip-form').onsubmit=")
        assert 'const short=unaffordablePick();if(short){refusePick(short);return;}' in submit
        assert submit.index('if(short){') < submit.index("$('#pay-button').disabled=true") < submit.index("api('/api/public/tips'")
        refuse = block(js, 'function refusePick(it){', 'setPayEnabled();}')
        assert "pickRefusal=n.textContent='“'+it.name+'” needs a tip of at least '+INR(it.min_paise)+'. Raise your tip or choose another sound.';" in refuse
        assert "if(!seen(n))n.scrollIntoView({block:'center'" in refuse, 'Enter in the amount box must not leave the screen unchanged'
        assert "else if(seen($('#amount')))$('#amount').focus({preventScroll:true});" in refuse, 'no phone keyboard scrolling the message away'
        assert 'soundboard_id' not in refuse and 'keepPickAffordable' not in submit, 'the pick is kept, never silently dropped'

    def test_the_refusal_goes_once_its_cause_does(self):
        render = block(read('public.js'), 'function renderSoundboardGrid(){')
        assert "if(pickRefusal&&!unaffordablePick()){if($('#form-error').textContent===pickRefusal)$('#form-error').textContent='';pickRefusal='';}" in render
        assert render.index('pickRefusal') < render.index('for(const it of list)'), 'before the empty-list early return'

    def test_the_pick_stays_drawn_as_picked_while_an_amount_is_typed(self):
        js = read('public.js')
        assert 'const locked=amt<it.min_paise&&selected!==it.id;' in js

    def test_one_affordability_check_for_the_reload_and_for_pay(self):
        js = read('public.js')
        assert 'function unaffordablePick(){' in js and 'it.min_paise>Math.floor(+$(\'#amount\').value||0)*100?it:null' in js
        keep = block(js, 'function keepPickAffordable(){')
        assert 'const it=unaffordablePick();if(!it)return false;' in keep and 'return true;' in keep
        assert 'so your pick was cleared. The streamer’s default will play.' in keep


# ---------- tip[1]: a tapped locked tile says what unlocks it on its own price chip ----------
class TestLockedTileNudge:
    def test_the_chip_says_what_unlocks_it_for_a_moment(self):
        render = block(read('public.js'), 'function renderSoundboardGrid(){')
        assert "const price=it.min_paise?'₹'+(it.min_paise/100):'Any tip',min=el('span',price,'tile-min');" in render
        locked = block(render, 'tile.onclick=()=>{if(locked){', 'return;}')
        assert locked.index("sbNote('Tip at least ₹'") < locked.index("tile.classList.add('nudge')"), 'the live-region note is kept'
        assert "min.textContent='Tip '+price+'+';" in locked
        assert "tile.nudgeTimer=setTimeout(()=>{tile.classList.remove('nudge');min.textContent=price;},2500);" in locked
        assert 'clearTimeout(tile.nudgeTimer)' in locked and 'void tile.offsetWidth' in locked, 'a second tap restarts it'
        assert 'scrollIntoView' not in render, 'the page never scrolls'

    def test_the_nudge_animates_except_under_reduced_motion(self):
        css = read('premium.css')
        assert '.soundboard-tile.locked.nudge { opacity: .85; filter: none; }' in css
        assert re.search(r'\.soundboard-tile\.nudge \.tile-min \{[^}]*animation: sb-nudge ', css)
        assert '@keyframes sb-nudge {' in css
        assert '@media (prefers-reduced-motion: reduce) { .soundboard-tile.nudge .tile-min { animation: none; } }' in css


# ---------- tip[2]: keyboard focus survives the grid rebuild ----------
class TestGridKeepsKeyboardFocus:
    def test_focus_moves_to_the_same_tile_after_a_rebuild(self):
        js = read('public.js')
        render = block(js, 'function renderSoundboardGrid(){')
        assert 'tile.dataset.id=it.id;' in render and "tile.dataset.id='';" in block(js, 'function defaultTile(')
        remember = 'focused=grid.contains(document.activeElement)?document.activeElement.dataset.id:undefined;'
        refocus = 'if(focused!==undefined)[...grid.children].find(t=>t.dataset.id===focused)?.focus();'
        assert render.index(remember) < render.index('grid.replaceChildren();') < render.index('grid.append(tile);') < render.index(refocus)


# ---------- tip[3]: the empty note stays in the accessibility tree ----------
class TestNoteStaysALiveRegion:
    def test_the_empty_note_is_kept_rendered(self):
        css = read('premium.css')
        assert '#soundboard-note:empty { margin: 0; }' in css
        assert not re.search(r'#soundboard-note[^{]*\{[^}]*display:\s*none', css)
        html = (ROOT / 'acepressure' / 'templates' / 'public.html').read_text(encoding='utf-8')
        assert '<p id="soundboard-note" class="field-hint" role="status" aria-live="polite"></p>' in html


# ---------- tip[4]: category pills report the selected one ----------
class TestPillsReportTheirSelection:
    def test_aria_selected_follows_every_click(self):
        js = read('public.js')
        assert "for(const x of pillHost.children){x.classList.toggle('selected',x.textContent===cat);x.setAttribute('aria-selected',String(x.textContent===cat));}" in js
        assert "b.setAttribute('aria-selected',String(cat===soundboardFilter.cat));" in js, 'and on first draw'


# ---------- tip[5]: a second tap on ▶ replaces the preview without an error ----------
class TestDoubleTapPreview:
    def test_abort_errors_are_ignored_first(self):
        js = read('public.js')
        tile = block(js, 'async function playSoundboardPreview(')
        assert "}catch(e){if(e&&e.name==='AbortError')return;tile.classList.remove('playing');$('#form-error').textContent='Preview blocked by browser: '+e.message;}" in tile
        assert "}}catch(e){if(e&&e.name==='AbortError')return;$('#form-error').textContent='Preview failed: '+(e.message||'unknown error');}}" in js
        assert "$('#form-error').textContent='Preview failed to load.'" in tile, 'real load failures still show'


# ---------- admin[0]: with viewer picks off, the library toasts don't promise the tip page ----------
class TestLibraryToastsWithPicksOff:
    SENTENCE = ' Viewer picks are off, so the tip page hides your sounds until you turn them on above.'

    def test_upload_and_starter_toasts_end_with_the_picks_off_sentence(self):
        lib = block(read('admin.js'), 'async function library(root){')
        assert f"const HIDDEN=d.picks_on?'':'{self.SENTENCE}';" in lib
        live = line(lib, 'live=(resp.entry&&resp.entry.enabled?')
        assert "(e.url||HIDDEN?'':' It’s now on your tip page.')" in live and live.endswith(')+HIDDEN;')
        seed = line(lib, "toast(ready.length?'Added '+ready.length")
        assert "(HIDDEN?'':' viewers can pick now')" in seed and "' waiting for your clips.':'.')+HIDDEN:r.created.length?" in seed
        assert "its first clip makes it pickable.'+HIDDEN:'Starter sounds already added.'" in seed
        # Add sound says it too when the new sound is offered to viewers (an unoffered default plays on every tip anyway).
        added = line(lib, "toast((x.auto_fixed?'✓ Added \"'+label+'\".")
        assert added.endswith("+(x.entry?.enabled?HIDDEN:''));")

    def test_the_library_data_carries_the_switch(self, admin):
        c, h = admin
        assert c.get('/api/admin/soundboard', headers=h).json['picks_on'] is True
        assert c.post('/api/admin/settings', json={'allow_sound_choice': False}, headers=h).status_code == 200
        assert c.get('/api/admin/soundboard', headers=h).json['picks_on'] is False
        assert c.get('/api/public/soundboard').json == {'items': []}, 'which is why the toasts must not say “on your tip page”'


# ---------- admin[1]: a second click while an upload runs is ignored ----------
class TestUploadButtonsIgnoreASecondClick:
    def test_add_sound_and_upload_bundle_are_guarded(self):
        admin_js = read('admin.js')
        lib = block(admin_js, 'async function library(root){')
        assert "const add=el('button','Add sound','primary wide');" in lib
        assert "f.onsubmit=e=>{e.preventDefault();if(add.disabled)return;add.disabled=true;stay(async()=>{" in lib
        assert "}).finally(()=>add.disabled=false);};" in lib
        assert "const bundle=el('button','Upload bundle','primary wide');bf.append(bundle);" in lib
        assert "bf.onsubmit=e=>{e.preventDefault();if(bundle.disabled)return;bundle.disabled=true;stay(async()=>{" in lib
        assert "}).finally(()=>bundle.disabled=false);};" in lib
        # finally always runs because action() catches every error and stay() returns its promise.
        assert 'async function action(fn){try{await fn();await refresh();}catch(e){toast(e.message);}}' in admin_js
        assert 'function stay(fn){const y=scrollY;return action(fn).then(()=>scrollTo(0,y));}' in admin_js


# ---------- admin[2]: long unbroken names and categories wrap inside the phone cards ----------
class TestLibraryCardsWrapLongNames:
    def test_the_name_cell_breaks_anywhere_on_phones(self):
        css = read('premium.css')
        start = css.index('/* Sound library rows become cards: seven columns cannot fit a phone. */')
        phone = css[css.rindex('@media (max-width: 700px) {', 0, start):css.index('\n}', start)]
        assert '.library-table td:nth-child(2) { grid-area: name; font-weight: 700; overflow-wrap: anywhere; }' in phone
        # Not the category: its track would shrink below its longest word and break "Reactions" mid-word at 320 px.
        assert '.library-table td:nth-child(3) { grid-area: cat; }' in phone


# ---------- the server side the tip page relies on (the backstop stays) ----------
class TestPickPriceContract:
    def test_public_sounds_carry_their_price_and_the_server_refuses_a_short_tip(self, app, admin):
        c, h = admin
        assert c.post('/api/admin/soundboard/seed', json={}, headers=h).json['ready']
        fanfare = next(e for e in c.get('/api/admin/soundboard', headers=h).json['items'] if e['name'] == 'Victory Fanfare')
        assert c.post('/api/admin/soundboard/' + fanfare['id'], json={'min_paise': 10000}, headers=h).status_code == 200
        listed = {e['id']: e for e in c.get('/api/public/soundboard').json['items']}
        assert listed[fanfare['id']]['min_paise'] == 10000, 'the tip page checks the pick against this price'
        tip = lambda amount: c.post('/api/public/tips', json={'amount': amount, 'name': 'Asha', 'soundboard_id': fanfare['id']})
        with app.store.db() as db: before = db.execute('SELECT COUNT(*) FROM tips').fetchone()[0]
        r = tip(50)
        assert r.status_code == 400 and r.json['error'] == 'Tip at least ₹100 to play this sound.'
        with app.store.db() as db: assert db.execute('SELECT COUNT(*) FROM tips').fetchone()[0] == before
        r = tip(150)
        assert r.status_code == 201
        with app.store.db() as db:
            assert db.execute('SELECT soundboard_id FROM tips WHERE id=?', (r.json['id'],)).fetchone()[0] == fanfare['id']
