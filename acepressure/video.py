"""Local FFmpeg helpers for admin uploads: video clips re-encoded to WebM (VP9 + optional Opus),
and alert/soundboard audio validated by content and rescued to standard MP3 when a browser
couldn't play it."""
import io, json, re, shutil, subprocess, tempfile, unicodedata, wave
from pathlib import Path
from .domain import Problem

def tool(name):
    local=Path(__file__).resolve().parent.parent/'tools'/'bin'/(name+'.exe')
    return str(local) if local.is_file() else shutil.which(name)

def transcode(content,extension,keep_audio=False):
    ffmpeg,ffprobe=tool('ffmpeg'),tool('ffprobe')
    if not ffmpeg or not ffprobe:raise Problem('Video needs FFmpeg and ffprobe on this PC. See docs/TTS_AND_MEDIA.md; GIF uploads work without them.',503)
    if extension not in ['.mp4','.webm'] or len(content)>24*1024*1024:raise Problem('Use MP4/WebM up to 24 MB and 20 seconds.')
    with tempfile.TemporaryDirectory(prefix='ace-video-') as folder:
        source=Path(folder)/('input'+extension);source.write_bytes(content);target=Path(folder)/'output.webm'
        fmt='mov' if extension=='.mp4' else 'matroska'
        probe_args=['-v','error','-protocol_whitelist','file,pipe','-f',fmt]
        try:
            r=subprocess.run([ffprobe,*probe_args,'-show_streams','-show_format','-of','json',str(source)],capture_output=True,timeout=15,check=True)
            info=json.loads(r.stdout)
            vstreams=[s for s in info['streams'] if s['codec_type']=='video']
            if len(vstreams)!=1: raise ValueError()
            v=vstreams[0]
            duration=float(info['format']['duration'])
            if not 0<duration<=20 or v['width']*v['height']>4000000: raise ValueError()
            # Base ffmpeg args: input, video map (first video stream), 20 s cap, scale/fps, VP9 codec.
            ff=[ffmpeg,*probe_args,'-i',str(source),'-map','0:v:0']
            if keep_audio:
                # Optional audio map (? makes it OK if the input has no audio).
                # Opus is the standard WebM audio codec. Mono-safe (-ac 2 lets ffmpeg upmix safely).
                ff+=['-map','0:a:0?','-c:a','libopus','-b:a','96k','-ac','2','-ar','48000']
            else:
                ff+=['-an']
            ff+=['-sn','-dn','-map_metadata','-1','-t','20','-vf',
                 "scale=w='min(1280,iw)':h='min(1280,ih)':force_original_aspect_ratio=decrease:force_divisible_by=2,fps=30",
                 '-c:v','libvpx-vp9','-pix_fmt','yuva420p','-threads','2','-deadline','realtime','-cpu-used','6','-b:v','1200k','-y',str(target)]
            subprocess.run(ff,capture_output=True,timeout=120,check=True)
            if target.stat().st_size>24*1024*1024: raise ValueError()
            return target.read_bytes()
        except Exception: raise Problem('Video could not be decoded. Use a valid MP4/WebM, at most 20 seconds and 4 megapixels.',400)

def probe_has_audio(content,extension):
    """Quick ffprobe check — does this video actually carry an audio stream?
    Used by the alert-bundle endpoint to tell the overlay whether to suppress the
    separate alert_sound (avoids double-audio when the admin uploads MP4 with sound)."""
    ffprobe=tool('ffprobe')
    if not ffprobe: return False
    with tempfile.TemporaryDirectory(prefix='ace-probe-') as folder:
        source=Path(folder)/('probe'+extension); source.write_bytes(content)
        fmt='mov' if extension=='.mp4' else 'matroska'
        try:
            r=subprocess.run([ffprobe,'-v','error','-protocol_whitelist','file,pipe','-f',fmt,'-show_streams','-of','json',str(source)],capture_output=True,timeout=10,check=True)
            info=json.loads(r.stdout)
            return any(s['codec_type']=='audio' for s in info.get('streams',[]))
        except Exception:
            return False

# Codecs each container extension may legitimately carry such that evergreen browsers can decode.
# v1.5.7 — reject AAC-in-.mp3 (ffprobe says ok, Chromium refuses), opus-in-.mp3, mp2/mp1-in-.mp3.
_ALLOWED_CODECS = {
    '.mp3': {'mp3'},
    '.ogg': {'vorbis', 'opus'},
    '.wav': {'pcm_s16le', 'pcm_s24le', 'pcm_s32le', 'pcm_u8', 'pcm_f32le', 'pcm_f64le', 'pcm_alaw', 'pcm_mulaw'},
}

# Uploaded audio is format-auto-detected, so restrict FFmpeg to plain container demuxers and local
# files. Without this a disguised playlist/SDP/concat file could make ffmpeg open URLs or read other
# files on the PC (newer FFmpeg builds refuse most of these on their own; older ones on PATH don't).
_SAFE_INPUT = ['-protocol_whitelist', 'file',
               '-format_whitelist', 'mp3,ogg,wav,w64,flac,aac,mov,matroska,aiff,asf']
_RESCUE_SUFFIXES = {'.mp3', '.ogg', '.wav', '.bin'}
# Fix_Audio.bat's recipe: MPEG Layer 3, 128 kbps CBR, 48 kHz stereo, no metadata.
FIX_AUDIO_ARGS = ['-codec:a', 'libmp3lame', '-b:a', '128k', '-ar', '48000', '-ac', '2',
                  '-map_metadata', '-1', '-map', '0:a:0']

def transcode_audio(content, extension, max_duration_ms=20000):
    """Re-encode an upload a browser can't play to standard MP3 using Fix_Audio.bat's recipe.
    Returns MP3 bytes, or None when ffmpeg is missing, the input has no decodable audio, or the
    output doesn't pass probe_audio_file. Output stops 5 s past the cap instead of AT the cap,
    so callers can reject over-long clips rather than silently truncating them."""
    if extension not in _RESCUE_SUFFIXES: raise ValueError(f'unexpected extension hint {extension!r}')
    ffmpeg = tool('ffmpeg')
    if not ffmpeg or not content or len(content) < 8 or len(content) > 24*1024*1024: return None
    with tempfile.TemporaryDirectory(prefix='ace-afix-') as folder:
        src = Path(folder) / ('input' + extension); src.write_bytes(content)
        dst = Path(folder) / 'output.mp3'
        try:
            subprocess.run([ffmpeg, '-v', 'error', '-y', *_SAFE_INPUT, '-i', str(src), *FIX_AUDIO_ARGS,
                            '-t', str(max_duration_ms // 1000 + 5), str(dst)],
                           capture_output=True, timeout=30, check=True)
        except Exception:
            return None
        if not dst.is_file() or dst.stat().st_size < 256: return None
        fixed = dst.read_bytes()
    return fixed if probe_audio_file(fixed, '.mp3')['valid'] is True else None

def validate_or_fix_audio(content, max_duration_ms=20000):
    """Validate an uploaded alert/soundboard clip by its bytes (never the client's filename).
    Returns (bytes, extension_without_dot, duration_ms, auto_fixed). Playable files come back
    untouched; files a browser couldn't play are rescued via transcode_audio when FFmpeg is
    installed. Clips over the cap are refused whether or not they needed fixing."""
    if not content: raise Problem('Choose a non-empty audio file.')
    cap = f'{max_duration_ms // 1000} seconds'
    head = content[:12]
    if head[:4] == b'RIFF' and head[8:12] == b'WAVE':
        try:
            with wave.open(io.BytesIO(content)) as w:
                pcm = w.getcomptype() == 'NONE' and w.getframerate() > 0
                # Streamed WAVs declare 0xFFFFFFFF sizes; count only the frames actually present.
                frames = min(w.getnframes(), max(0, len(content) - 44) // max(1, w.getnchannels() * w.getsampwidth()))
                duration_ms = int(1000 * frames / w.getframerate()) if pcm else 0
        except Exception:
            pcm = False  # μ-law / ADPCM / float WAV, or a damaged header
        if not pcm:
            return _rescue(content, '.wav', max_duration_ms, f'WAV must be PCM, {cap} or less.')
        if duration_ms > max_duration_ms: raise Problem(f'WAV must be PCM, {cap} or less.')
        return content, 'wav', duration_ms, False
    if head[:3] == b'ID3' or (len(head) >= 2 and head[0] == 0xFF and (head[1] & 0xE0) == 0xE0):
        ext, label, header_duration = '.mp3', 'MP3', _mp3_duration_ms
    elif head[:4] == b'OggS':
        ext, label, header_duration = '.ogg', 'OGG', _ogg_duration_ms
    else:
        return _rescue(content, '.bin', max_duration_ms, 'Unrecognised audio format. Use .wav (PCM), .mp3, or .ogg.')
    probe = probe_audio_file(content, ext)
    if probe['valid'] is None and ext == '.mp3' and _mpeg_layer(content) != 1:
        # Without FFmpeg nothing can be converted; refuse instead of storing a file browsers won't play.
        raise Problem("This isn't a standard MP3 (it looks like AAC, MPEG Layer I/II, or has no audio), so browsers "
                      "can't play it. Run Install_Media_Tools.bat once, then upload it again: AcePressure will convert it automatically.")
    if probe['valid'] is False:
        # A failed probe's duration is a bitrate guess (raw ADTS with leading silence reads 5-25x
        # too long), so the length is only judged after conversion.
        return _rescue(content, ext, max_duration_ms, probe['reason'] or f'{label} file is not a decodable audio stream.')
    duration_ms = probe['duration_ms'] or header_duration(content)  # header parse when ffprobe is absent
    # Container durations can be stale (a clip cut from a longer VBR file keeps the old Xing count)
    # or bitrate guesses, so decode before refusing. 500 ms covers encoder padding, as in _rescue.
    if duration_ms > max_duration_ms + 500:
        duration_ms = _decoded_duration_ms(content, ext, max_duration_ms) or duration_ms
    if duration_ms > max_duration_ms + 500: raise Problem(f'{label} is longer than {cap}; trim it first.')
    return content, ext[1:], duration_ms, False

def _rescue(content, ext, max_duration_ms, reason):
    too_long = f'This clip is longer than {max_duration_ms // 1000} seconds; trim it first.'
    fixed = transcode_audio(content, ext, max_duration_ms)
    if fixed is None: raise Problem(reason)
    fixed_ms = probe_audio_file(fixed, '.mp3')['duration_ms'] or 0
    # LAME adds ~50 ms of encoder padding; tolerate it so a clip right at the cap isn't refused.
    if fixed_ms > max_duration_ms + 500: raise Problem(too_long)
    return fixed, 'mp3', fixed_ms, True

def _decoded_duration_ms(content, ext, max_duration_ms):
    """Length found by decoding (to 8 kHz mono PCM, stopping at cap+5 s). None without FFmpeg."""
    ffmpeg = tool('ffmpeg')
    if not ffmpeg: return None
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / ('in' + ext); src.write_bytes(content)
        try:
            r = subprocess.run([ffmpeg, '-v', 'error', *_SAFE_INPUT, '-i', str(src), '-map', '0:a:0',
                                '-t', str(max_duration_ms // 1000 + 5), '-ac', '1', '-ar', '8000', '-f', 's16le', 'pipe:1'],
                               capture_output=True, timeout=30, check=True)
        except Exception:
            return None
    return len(r.stdout) * 1000 // 16000 or None

def _id3_end(data):
    if data[:3] == b'ID3' and len(data) > 10:
        s = data[6:10]
        return 10 + ((s[0] << 21) | (s[1] << 14) | (s[2] << 7) | s[3])  # synchsafe tag size
    return 0

def _mpeg_layer(data):
    """Layer bits of the first frame sync after any ID3 tag: 1 = Layer III (MP3), 2/3 = Layer II/I,
    0 = ADTS (AAC), None = no audio frame found."""
    start = _id3_end(data)
    for i in range(start, min(start + 65536, len(data) - 1)):
        if data[i] == 0xFF and (data[i+1] & 0xE0) == 0xE0:
            return (data[i+1] >> 1) & 3
    return None

def _mp3_duration_ms(data):
    """Best-effort MP3 duration without ffprobe: the Xing/Info or VBRI frame count when present
    (LAME, VBR and Fix_Audio.bat output), else a CBR estimate from the first frame. 0 if unknown."""
    offset = _id3_end(data)
    if offset + 4 > len(data): return 0
    for i in range(offset, min(offset + 2048, len(data) - 4)):
        if data[i] == 0xFF and (data[i+1] & 0xE0) == 0xE0:
            header = (data[i] << 24) | (data[i+1] << 16) | (data[i+2] << 8) | data[i+3]
            version = (header >> 19) & 3; layer = (header >> 17) & 3
            bitrate_idx = (header >> 12) & 0xF; sample_idx = (header >> 10) & 3
            if layer != 1 or bitrate_idx in (0, 0xF) or sample_idx == 3: continue
            mpeg1 = [0,32,40,48,56,64,80,96,112,128,160,192,224,256,320,0]
            mpeg2 = [0,8,16,24,32,40,48,56,64,80,96,112,128,144,160,0]
            bitrate = (mpeg1[bitrate_idx] if version == 3 else mpeg2[bitrate_idx]) * 1000
            rate = {3: (44100, 48000, 32000), 2: (22050, 24000, 16000), 0: (11025, 12000, 8000)}.get(version, (0, 0, 0))[sample_idx]
            per_frame = 1152 if version == 3 else 576
            mono = (header >> 6) & 3 == 3
            xing = i + 4 + ((17 if mono else 32) if version == 3 else (9 if mono else 17))
            flags = int.from_bytes(data[xing+4:xing+8], 'big') if data[xing:xing+4] in (b'Xing', b'Info') else 0
            if rate and flags & 1:
                ms = int.from_bytes(data[xing+8:xing+12], 'big') * per_frame * 1000 / rate
                declared = int.from_bytes(data[xing+12:xing+16], 'big') if flags & 2 else 0
                if declared:  # a clip cut from a longer file keeps the old header: scale by bytes present
                    ms *= min(1.0, (len(data) - i) / declared)
                return int(ms)
            if rate and data[i+36:i+40] == b'VBRI':
                return int(int.from_bytes(data[i+50:i+54], 'big') * per_frame * 1000 / rate)
            return int((len(data) - i) * 8 * 1000 / bitrate) if bitrate else 0
    return 0

def _ogg_duration_ms(data):
    """Best-effort Ogg Vorbis/Opus duration from the last page's granule position. 0 if unknown."""
    if len(data) < 64 or data[:4] != b'OggS': return 0
    last = data.rfind(b'OggS')
    if last < 0 or last + 14 > len(data): return 0
    granule = int.from_bytes(data[last+6:last+14], 'little', signed=False)
    hdr = data.find(b'\x01vorbis')
    if 0 <= hdr and hdr + 16 <= len(data):
        rate = int.from_bytes(data[hdr+12:hdr+16], 'little', signed=False)
        return int(granule * 1000 / rate) if rate else 0
    hdr = data.find(b'OpusHead')
    if 0 <= hdr and hdr + 12 <= len(data):  # Opus granules always count 48 kHz samples
        return max(0, int((granule - int.from_bytes(data[hdr+10:hdr+12], 'little')) * 1000 / 48000))
    return 0

# Bidi controls can make "evil\u202egnp.mp3" display as "evilpng.mp3"; ZWJ/ZWNJ stay because emoji
# sequences and Indic/Persian spellings need them.
_INVISIBLE_TRICKS = set('\u061c\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069\ufeff')

def sanitize_original_name(name):
    """Basename of an uploader-supplied filename, for display only (never used as a path)."""
    if not isinstance(name, str): return ''
    base = name.replace('\\', '/').rsplit('/', 1)[-1]
    name = ''.join(c for c in base if c not in _INVISIBLE_TRICKS
                   and unicodedata.category(c) not in ('Cc', 'Cs', 'Zl', 'Zp')).strip()
    return name if len(name) <= 120 else name[:117] + '...'

def sound_labels(settings, strip_extension=False):
    """Stored sound name -> the filename the admin uploaded. Repeats are numbered ("meme.mp3 (2)")
    so dropdowns stay unambiguous; sounds uploaded before 1.5.9 have no entry (show the stored name).
    The viewer variant (strip_extension) also steers clear of the built-in Chime/Pulse/Silent."""
    names, out = settings.get('media_labels') or {}, {}
    used = {'chime', 'pulse', 'silent'} if strip_extension else set()
    for stored in settings.get('sounds', []):
        label = names.get(stored)
        if not label: continue
        if strip_extension:
            label = re.sub(r'\.(mp3|ogg|oga|opus|wav|m4a|aac|flac|webm|wma|aiff?)$', '', label, flags=re.I) or label
        candidate, n = label, 1
        while candidate.casefold() in used:
            n += 1
            candidate = f'{label} ({n})'
        used.add(candidate.casefold())
        out[stored] = candidate
    return out


def probe_audio_file(content, extension):
    """Validate that a standalone audio file (WAV/MP3/OGG) has a decodable audio stream
    AND that the detected codec matches the expected container extension.

    Returns a dict: {'valid': bool|None, 'codec': str|None, 'duration_ms': int|None, 'reason': str|None}

    When ffprobe is not available, returns {'valid': None, ...} — the caller should fall back
    to its own magic-byte check. 'valid': False means the file would fail to play in a browser:
      - MP3 files that are JUST an ID3 tag with no audio frames
      - AAC-ADTS files renamed to .mp3 (sync bytes identical to MP3)
      - MPEG Layer 1 / Layer 2 files (codec mp1/mp2)
      - Any codec/extension mismatch
    All these cause the browser's "no supported source was found" error.
    """
    ffprobe = tool('ffprobe')
    if not ffprobe: return {'valid': None, 'codec': None, 'duration_ms': None, 'reason': 'ffprobe not installed'}
    with tempfile.TemporaryDirectory(prefix='ace-aprobe-') as folder:
        src = Path(folder) / ('audio' + extension)
        src.write_bytes(content)
        try:
            r = subprocess.run([ffprobe, '-v', 'error', *_SAFE_INPUT, '-show_streams', '-show_format', '-of', 'json', str(src)],
                               capture_output=True, timeout=10, check=True)
            info = json.loads(r.stdout)
            audio_streams = [s for s in info.get('streams', []) if s.get('codec_type') == 'audio']
            if not audio_streams:
                return {'valid': False, 'codec': None, 'duration_ms': None,
                        'reason': 'File has no audio stream (ID3 tag or metadata only).'}
            a = audio_streams[0]
            codec = a.get('codec_name', 'unknown')
            duration = float(info.get('format', {}).get('duration', 0) or a.get('duration', 0) or 0)
            duration_ms = int(duration * 1000)
            if codec in ['mp1', 'mp2']:
                return {'valid': False, 'codec': codec, 'duration_ms': duration_ms,
                        'reason': f'MPEG Layer {codec[-1]} audio is not supported by browsers. Re-export as standard MP3 (Layer 3) or OGG.'}
            allowed = _ALLOWED_CODECS.get(extension.lower())
            if allowed is not None and codec not in allowed:
                nice = {'mp3': 'MP3', 'ogg': 'OGG Vorbis/Opus', 'wav': 'WAV PCM'}.get(extension.lstrip('.').lower(), extension)
                return {'valid': False, 'codec': codec, 'duration_ms': duration_ms,
                        'reason': f'File is {codec.upper()} audio but was uploaded as {nice}. Re-export as actual {nice} or rename the file to the correct extension.'}
            return {'valid': True, 'codec': codec, 'duration_ms': duration_ms, 'reason': None}
        except Exception:
            # Upload paths only show this after transcode_audio has also failed, so pointing the
            # admin at Fix_Audio.bat (the same recipe) would send them in circles.
            return {'valid': False, 'codec': None, 'duration_ms': None,
                    'reason': 'This audio file could not be decoded (no valid audio stream). Re-export from your source editor as a standard MP3 (constant bitrate, 128 kbps) or WAV (PCM, 16-bit).'}
