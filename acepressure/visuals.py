"""Bounded visual settings and decoded/re-encoded image uploads. No arbitrary CSS/HTML."""
import io, json, re, warnings
from flask import request, render_template
from PIL import Image, ImageSequence
from .domain import Problem, uid, BUILTIN_SOUNDS, SOUND_MAX_MS, display_label

DEFAULT_VISUALS = dict(theme='frame',accent='#dc3655',text='#f3efe5',background='#14161c',
    radius=16,bar_height=16,alert_width=760,goal_width=700,show_percent=True,
    alert_image='',goal_image='',logo='',image_size=96,animation='slide',alert_sound='viewer',
    alert_video_has_audio=False)

def validate_visuals(value, media):
    if not isinstance(value,dict) or set(value)-set(DEFAULT_VISUALS): raise Problem('Unknown visual setting.')
    d=DEFAULT_VISUALS|value
    for key in ['accent','text','background']:
        if not isinstance(d[key],str) or not re.fullmatch(r'#[0-9a-fA-F]{6}',d[key]): raise Problem('Use six-digit hex colors.')
    if type(d['alert_video_has_audio']) is not bool: raise Problem('Invalid alert_video_has_audio flag.')
    for key,low,high in [('radius',0,40),('bar_height',6,40),('alert_width',400,1400),('goal_width',320,1400),('image_size',48,240)]:
        if type(d[key]) is not int or not low<=d[key]<=high: raise Problem('Invalid '+key)
    if d['theme'] not in ['frame','minimal','spotlight'] or d['animation'] not in ['slide','fade','none']: raise Problem('Invalid design choice.')
    if type(d['show_percent']) is not bool: raise Problem('Invalid percentage choice.')
    if d['alert_sound'] not in ['viewer','chime','pulse','none'] and (not re.fullmatch(r'[A-Za-z0-9_-]+\.(wav|mp3|ogg)',str(d['alert_sound'])) or not (media/d['alert_sound']).is_file()): raise Problem('Choose an uploaded sound.')
    for key in ['alert_image','goal_image','logo']:
        name=d[key]
        if not isinstance(name,str) or (name and (not re.fullmatch((r'[A-Za-z0-9_-]+\.(png|webp|gif|webm)' if key=='alert_image' else r'[A-Za-z0-9_-]+\.(png|webp|gif)'),name) or not (media/name).is_file())): raise Problem('Choose an uploaded image.')
    return d

def register_visuals(app,store,admin):
    @app.get('/api/admin/visuals')
    def get_visuals():
        from .video import sound_labels
        media=store.path/'media'; s=store.settings()
        assets=sorted(x.name for x in media.glob('*') if x.suffix in ['.png','.webp','.gif','.webm'])
        labels=s.get('visual_labels') if isinstance(s.get('visual_labels'),dict) else {}  # 1.6.7: the names they were uploaded with
        return {'visuals':DEFAULT_VISUALS|s.get('visuals',{}),'assets':assets,'asset_labels':{a:labels[a] for a in assets if isinstance(labels.get(a),str) and labels[a]},
                'sounds':s['sounds'],'sound_labels':sound_labels(s)}
    @app.post('/api/admin/visuals')
    def save_visuals():
        """Unsent keys keep their saved values. alert_video_has_audio is server-owned (only the alert bundle sets it, and a new
        alert_image clears it). A posted alert_sound (an open 1.5.9 Design studio) becomes the default sound."""
        posted=request.get_json(silent=True)
        if not isinstance(posted,dict): raise Problem('Unknown visual setting.')
        media=store.path/'media'
        with store.db(True) as db:
            s=store.settings(db)
            stored={k:v for k,v in (DEFAULT_VISUALS|(s.get('visuals') if isinstance(s.get('visuals'),dict) else {})).items() if k in DEFAULT_VISUALS}
            merged=stored|posted
            for k in ('alert_image','goal_image','logo'):  # a file deleted outside the app must not block unrelated saves
                if k not in posted and merged[k] and not (isinstance(merged[k],str) and (media/merged[k]).is_file()): merged[k]=''
            if 'alert_sound' not in posted: merged['alert_sound']='viewer'
            d=validate_visuals(merged,media)  # a posted flag is type-checked, a posted sound must exist
            changed=None
            if d['alert_sound']!='viewer':
                f=d['alert_sound']; row=None if f in BUILTIN_SOUNDS else db.execute('SELECT id FROM soundboards WHERE media_filename=? ORDER BY display_order,created LIMIT 1',(f,)).fetchone()
                target=f if f in BUILTIN_SOUNDS else row['id'] if row else None
                if not target: raise Problem('Choose a sound from the Sound library.')
                store.put_default_sound(db,target,'design_studio'); changed=target
                d['alert_sound']='viewer'
            d['alert_video_has_audio']=bool(stored['alert_video_has_audio']) and d['alert_image']==stored['alert_image']
            db.execute("INSERT INTO settings VALUES ('visuals',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(json.dumps(d),))
            store.audit(db,'visuals_changed',detail={'keys':list(posted)})
            s=store.settings(db); reset=s.get('default_sound')=='video' and not store.video_audio_available(s)
            if reset: store.put_default_sound(db,'chime','visuals')
        return {'ok':True,'default_changed':bool(changed),'default_reset':reset}
    @app.post('/api/admin/visual-assets')
    def upload_asset():
        from .video import sanitize_original_name
        file=request.files.get('file')
        if not file: raise Problem('Choose a PNG, WebP or GIF image.')
        content=file.read(); original=sanitize_original_name(file.filename)
        if file.filename.lower().endswith(('.mp4','.webm')):
            from pathlib import Path
            from .video import transcode
            content=transcode(content,Path(file.filename).suffix.lower())
            media=store.path/'media';media.mkdir(exist_ok=True);name=uid()+'.webm';(media/name).write_bytes(content)
            with store.db(True) as db:store.audit(db,'visual_uploaded',name);store.remember_visual(db,name,original)
            return {'ok':True,'name':name,'original_name':original}
        if len(content)>8*1024*1024:raise Problem('Image limit is 8 MB.')
        try:
            with warnings.catch_warnings():
                warnings.simplefilter('error',Image.DecompressionBombWarning)
                source=Image.open(io.BytesIO(content))
                if source.format not in ['PNG','WEBP','GIF'] or source.width*source.height>4000000 or getattr(source,'n_frames',1)>120 or source.width*source.height*getattr(source,'n_frames',1)>24000000: raise ValueError()
                frames=[]; durations=[]
                for frame in ImageSequence.Iterator(source):
                    img=frame.convert('RGBA');img.thumbnail((1280,1280));frames.append(img.copy());durations.append(max(40,min(1000,frame.info.get('duration',100))))
                out=io.BytesIO()
                # Animated WebP preserves alpha without accepting active content or metadata.
                if len(frames)>1:
                    frames[0].save(out,format='WEBP',save_all=True,append_images=frames[1:],duration=durations,loop=0,lossless=True);ext='.webp'
                else: frames[0].save(out,format='PNG');ext='.png'
                if out.tell()>8*1024*1024: raise ValueError()
        except Exception: raise Problem('Use PNG/WebP/GIF up to 4 megapixels, 120 frames and 8 MB. SVG and HTML are not accepted.')
        media=store.path/'media';media.mkdir(exist_ok=True);name=uid()+ext;(media/name).write_bytes(out.getvalue())
        with store.db(True) as db: store.audit(db,'visual_uploaded',name); store.remember_visual(db,name,original)
        return {'ok':True,'name':name,'original_name':original}

    @app.post('/api/admin/alert-bundle')
    def upload_alert_bundle():
        """v1.5.5 — single-step upload of (visual, audio?) as an atomic alert bundle.

        Request: multipart/form-data with up to two files:
          - visual: PNG/WebP/GIF/MP4/WebM (required)
          - audio:  WAV/MP3/OGG (optional — only required if the visual isn't a video-with-audio)

        Behaviour:
          - Visual processed through the same validator as /api/admin/visual-assets.
          - Audio processed through the same validator as /api/admin/media kind=sound (30 s cap).
          - The visual becomes alert_image. Since 1.6.0 a separate sound becomes a sound-library row
            (hidden from viewers until the admin ticks it) and the default sound; alert_sound stays 'viewer'.
          - If the visual is a video AND the admin didn't upload a separate audio file,
            we probe whether the video has its own audio. If yes, keep the video's audio,
            set visuals.alert_video_has_audio=True and make "Alert video's own sound" the default.
            Otherwise a default that was the video's own sound goes back to Chime.
          - If both are uploaded: strip the video's audio (admin explicitly wants the uploaded sound)
            and clear the flag.
          - Settings are saved in one transaction (files removed if that fails), so one failed POST
            never leaves the system in a half-updated state.
        """
        from pathlib import Path
        from .video import transcode, probe_has_audio, validate_or_fix_audio, sanitize_original_name
        request.max_content_length=34*1024*1024  # a 24 MB video plus an 8 MB sound in one request
        vfile=request.files.get('visual')
        afile=request.files.get('audio')
        if not vfile: raise Problem('Choose a visual file (PNG/WebP/GIF/MP4/WebM).')
        vcontent=vfile.read()
        if not vcontent: raise Problem('Empty visual file.')
        ext=Path(vfile.filename or '').suffix.lower()
        if ext not in ['.png','.webp','.gif','.mp4','.webm']:
            raise Problem('Visual must be PNG/WebP/GIF/MP4/WebM.')
        is_video = ext in ['.mp4','.webm']
        media=store.path/'media'; media.mkdir(exist_ok=True)
        video_has_audio=False
        audio_in_bundle = afile is not None and (afile.filename or '').strip() != ''
        # --- Audio first (optional), so a rejected clip never leaves the visual orphaned on disk ---
        aname=None; acontent=None; audio_original_name=''; audio_auto_fixed=False
        if audio_in_bundle:
            acontent=afile.read()
            if not acontent: raise Problem('Audio file is empty.')
            if len(acontent)>8*1024*1024: raise Problem('Audio limit is 8 MB.')
            audio_original_name=sanitize_original_name(afile.filename)
            acontent,aext,adur,audio_auto_fixed=validate_or_fix_audio(acontent,max_duration_ms=SOUND_MAX_MS)
            aname=uid()+'.'+aext
        # --- Visual ---
        if is_video:
            if len(vcontent)>24*1024*1024: raise Problem('Video limit is 24 MB.')
            # Keep the video's own audio only when no separate clip came with the bundle.
            keep_video_audio = not audio_in_bundle
            if keep_video_audio:
                video_has_audio = probe_has_audio(vcontent, ext)
            vbytes = transcode(vcontent, ext, keep_audio=keep_video_audio)
            vname = uid()+'.webm'
        else:
            if len(vcontent)>8*1024*1024: raise Problem('Image limit is 8 MB.')
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter('error', Image.DecompressionBombWarning)
                    source=Image.open(io.BytesIO(vcontent))
                    if source.format not in ['PNG','WEBP','GIF'] or source.width*source.height>4000000 or getattr(source,'n_frames',1)>120:
                        raise ValueError()
                    frames=[]; durations=[]
                    for frame in ImageSequence.Iterator(source):
                        img=frame.convert('RGBA'); img.thumbnail((1280,1280))
                        frames.append(img.copy()); durations.append(max(40,min(1000,frame.info.get('duration',100))))
                    out=io.BytesIO()
                    if len(frames)>1:
                        frames[0].save(out,format='WEBP',save_all=True,append_images=frames[1:],duration=durations,loop=0,lossless=True); vext='.webp'
                    else:
                        frames[0].save(out,format='PNG'); vext='.png'
                    if out.tell()>8*1024*1024: raise ValueError()
            except Exception:
                raise Problem('Visual must be PNG/WebP/GIF up to 4 megapixels, 120 frames, 8 MB.')
            vbytes=out.getvalue()
            vname=uid()+vext
        # --- Write both files, then persist settings atomically (files removed if that fails) ---
        written=[(media/vname,vbytes)]+([(media/aname,acontent)] if aname else [])
        try:
            for path,data in written: path.write_bytes(data)
            with store.db(True) as db:
                s = store.settings(db)
                visuals = {k: v for k, v in (DEFAULT_VISUALS | (s.get('visuals') if isinstance(s.get('visuals'), dict) else {})).items() if k in DEFAULT_VISUALS}
                for k in ('goal_image', 'logo'):  # a file deleted outside the app must not block the upload
                    if visuals[k] and not (isinstance(visuals[k], str) and (media / visuals[k]).is_file()): visuals[k] = ''
                visuals['alert_image'] = vname
                visuals['alert_sound'] = 'viewer'  # the sound lives in the library and settings.default_sound
                visuals['alert_video_has_audio'] = bool(is_video and video_has_audio and not aname)  # explicit upload wins
                validated = validate_visuals(visuals, media)
                db.execute("INSERT INTO settings VALUES ('visuals',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (json.dumps(validated),))
                entry = None; default_reset = False
                if aname:
                    sid = store._insert_sound(db, name=display_label(audio_original_name) or 'Alert sound', min_paise=0, enabled=False,
                                              media_filename=aname, duration_ms=adur, audit=False)
                    store.remember_upload(db, aname, audio_original_name, audio_auto_fixed)
                    store.put_default_sound(db, sid, 'bundle')
                    entry = dict(db.execute('SELECT * FROM soundboards WHERE id=?', (sid,)).fetchone()) | {'url': '/media/' + aname}
                elif validated['alert_video_has_audio']:
                    store.put_default_sound(db, 'video', 'bundle')  # the overlay plays the video's own sound
                elif store.settings(db).get('default_sound') == 'video':
                    store.put_default_sound(db, 'chime', 'bundle'); default_reset = True
                store.remember_visual(db, vname, sanitize_original_name(vfile.filename))
                default = store.settings(db).get('default_sound')
                store.audit(db, 'alert_bundle_uploaded', detail={'visual': vname, 'audio': aname, 'video_has_audio': video_has_audio,
                                                                 'audio_original_name': audio_original_name, 'audio_auto_fixed': audio_auto_fixed})
        except Exception:
            for path,_ in written: path.unlink(missing_ok=True)
            raise
        return {'ok': True, 'visual': vname, 'audio': aname, 'video_has_audio': video_has_audio,
                'audio_auto_fixed': audio_auto_fixed, 'audio_original_name': audio_original_name,
                'entry': entry, 'default': default, 'default_reset': default_reset}

    @app.get('/admin/visual-preview')
    def visual_preview():
        admin()
        return render_template('visual-preview.html')
