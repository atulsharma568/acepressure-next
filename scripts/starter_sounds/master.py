#!/usr/bin/env python3
"""Master the AcePressure soundboard SFX: even loudness, safe peaks, MP3 encode.

usage:  python -I master.py <wav_folder> <mp3_folder> [slug ...]   (default: all eight)

Needs ffmpeg/ffprobe with libmp3lame on PATH. Standard library only, deterministic.

For every <wav_folder>/<slug>.wav (44.1 kHz mono 16-bit, from <slug>.py in this folder),
writes <mp3_folder>/<slug>.mp3:

 1. Measure (pass 1): ffmpeg loudnorm I=-16:TP=-1.5:LRA=11 print_format=json gives
    input_i / input_tp / input_lra / input_thresh. ffmpeg ebur128 adds the max
    momentary (400 ms) loudness, which is what a one-shot "hit" feels like.
 2. Gain: one linear gain to reach -16 LUFS integrated. Short one-shots measure
    unreliably, so two ear proxies are reported for every clip and were checked
    by hand: the max momentary (400 ms) loudness, and the same with sub-bass
    de-weighted (100 Hz high-pass, since K-weighting counts 40-60 Hz almost at
    full value while ears at normal volume do not). At -16 LUFS all eight land
    within -13.0 to -15.0 LUFS on the de-weighted momentary proxy, so no clip
    needs an extra trim. MMAX_CAP stays as a guard for future clips: it lowers
    the gain if a clip's loudest 400 ms would exceed it.
 3. Peaks (pass 2): if the gained signal's true peak would exceed -1.5 dBTP, a
    look-ahead true-peak limiter (4x oversampled inter-sample peak detection,
    1.5 ms attack ramp, 60 ms release) shaves only those peaks. This is the
    "equivalent gain plus limiter" path, used for every clip instead of ffmpeg's
    two-pass linear loudnorm because linear loudnorm (checked on ffmpeg 9.0.2,
    pass 2 with measured_* and linear=true) does not limit: it lowers the gain
    until TP fits, so the five transient-heavy clips stopped 0.3-0.9 LU short of
    -16 LUFS (vine-boom -16.93, clap -16.88, cash-register -16.55, ba-dum-tss
    -16.35, sad-trombone -16.31). Its dynamic mode, which it falls back to when
    the linear conditions fail, is not meant for 1-4 s one-shots. A clip that
    needs no limiting gets exactly the pure gain linear loudnorm would apply.
 4. Encode: float samples piped straight into libmp3lame -q:a 2, mono, 44.1 kHz
    (no intermediate 16-bit requantisation), bit-exact flags, no metadata.
    If the decoded MP3's true peak overshoots -1.5 dBTP (codec ringing), the
    limiter ceiling is lowered by the overshoot and the clip is redone.
 5. Verify: ffprobe codec + duration, loudnorm/ebur128 loudness and true peak of
    the MP3, file size; results go to <wav_folder>/master-report.json.
    The app-side check (AcePressure's own validate_or_fix_audio accepting each
    MP3 unchanged) is TestStarterSounds in tests/test_sound_library.py.
"""
import array
import json
import math
import os
import re
import subprocess
import sys
import wave

SLUGS = ['vine-boom', 'air-horn', 'cash-register', 'victory-fanfare',
         'clap', 'game-over', 'ba-dum-tss', 'sad-trombone']

SR = 44100
TARGET_I = -16.0        # LUFS integrated
TARGET_TP = -1.5        # dBTP ceiling for the mastered signal
TARGET_LRA = 11.0       # only passed to loudnorm's measuring pass
MMAX_CAP = -10.0        # LUFS: guard, loudest 400 ms may not exceed this (sub-weighted)
MP3_TP_MAX = -1.5       # dBTP: decoded MP3 must stay at or below this (as metered)
LIMIT_ATTACK_MS = 1.5
LIMIT_RELEASE_MS = 60.0
OS = 4                  # oversampling factor for true-peak detection
HALF_TAPS = 24          # interpolation kernel half-length (input samples)


# ------------------------------------------------------------------ ffmpeg --

def run(cmd, data=None):
    return subprocess.run(cmd, input=data, capture_output=True, check=True)


def raw_input_args():
    return ['-f', 'f32le', '-ar', str(SR), '-ac', '1', '-i', 'pipe:0']


def f32(x):
    a = array.array('f', x)
    if sys.byteorder == 'big':
        a.byteswap()
    return a.tobytes()


def loudnorm_measure(path):
    err = run(['ffmpeg', '-nostats', '-hide_banner', '-i', path, '-af',
               'loudnorm=I=%g:TP=%g:LRA=%g:print_format=json' % (TARGET_I, TARGET_TP, TARGET_LRA),
               '-f', 'null', '-']).stderr.decode()
    js = json.loads(err[err.rindex('{'):err.rindex('}') + 1])
    return {k: float(js[k]) for k in ('input_i', 'input_tp', 'input_lra', 'input_thresh')}


def ebur128(args, data=None):
    """Integrated loudness, LRA, true peak and max momentary loudness via ffmpeg.
    A trailing ['-af', chain] in args is prepended to the meter."""
    pre = ''
    if len(args) >= 2 and args[-2] == '-af':
        pre, args = args[-1] + ',', args[:-2]
    err = run(['ffmpeg', '-nostats', '-hide_banner'] + args +
              ['-af', pre + 'ebur128=peak=true', '-f', 'null', '-'], data).stderr.decode()
    head, _, summ = err.partition('Summary:')
    mom = [float(v) for v in re.findall(r'\bM:\s*(-?[\d.]+)', head)]
    tp = re.search(r'Peak:\s+(-?[\d.]+|-inf) dBFS', summ).group(1)
    return {'I': float(re.search(r'I:\s+(-?[\d.]+) LUFS', summ).group(1)),
            'LRA': float(re.search(r'LRA:\s+(-?[\d.]+) LU', summ).group(1)),
            'TP': -200.0 if tp == '-inf' else float(tp),
            'Mmax': max(mom) if mom else -200.0}


def probe(path):
    info = json.loads(run(['ffprobe', '-v', 'error', '-show_streams', '-show_format',
                           '-of', 'json', path]).stdout)
    a = [s for s in info['streams'] if s.get('codec_type') == 'audio'][0]
    return {'codec': a.get('codec_name'), 'sample_rate': int(a.get('sample_rate', 0)),
            'channels': a.get('channels'), 'duration_s': float(info['format']['duration']),
            'bit_rate': int(info['format'].get('bit_rate', 0))}


def decode_mp3(path):
    raw = run(['ffmpeg', '-v', 'error', '-i', path, '-f', 'f32le', '-ac', '1',
               '-ar', str(SR), 'pipe:1']).stdout
    a = array.array('f', raw)
    if sys.byteorder == 'big':
        a.byteswap()
    return list(a)


def encode_mp3(x, path):
    run(['ffmpeg', '-v', 'error', '-y'] + raw_input_args() +
        ['-map_metadata', '-1', '-fflags', '+bitexact', '-flags:a', '+bitexact',
         '-c:a', 'libmp3lame', '-q:a', '2', '-ac', '1', '-ar', str(SR), path], f32(x))


# --------------------------------------------------------------- DSP bits --

def read_wav(path):
    with wave.open(path, 'rb') as w:
        if (w.getnchannels(), w.getsampwidth(), w.getframerate()) != (1, 2, SR):
            raise SystemExit('%s: expected 44.1 kHz mono 16-bit' % path)
        a = array.array('h', w.readframes(w.getnframes()))
    if sys.byteorder == 'big':
        a.byteswap()
    return [v / 32768.0 for v in a]


def _kernels():
    """Kaiser-windowed sinc interpolators for the OS-1 fractional positions."""
    def i0(z):
        s, t, k = 1.0, 1.0, 1
        while t > 1e-12 * s:
            t *= (z / (2.0 * k)) ** 2
            s += t
            k += 1
        return s
    beta = 8.0
    ks = []
    for p in range(1, OS):
        frac = p / OS
        taps = []
        for n in range(-HALF_TAPS + 1, HALF_TAPS + 1):       # x[i + n]
            d = n - frac
            sinc = math.sin(math.pi * d) / (math.pi * d)
            r = d / HALF_TAPS
            win = i0(beta * math.sqrt(max(0.0, 1.0 - r * r))) / i0(beta)
            taps.append(sinc * win)
        ks.append(taps)
    return ks


KERNELS = _kernels()


def true_peaks(x, floor):
    """Per-sample true peak: max |signal| over [i, i+1) at OS x oversampling.
    Interpolation is only evaluated where a peak above `floor` is possible."""
    n = len(x)
    ax = [abs(v) for v in x]
    tp = ax[:]
    lo, hi = HALF_TAPS - 1, HALF_TAPS
    for i in range(n - 1):
        if max(ax[i], ax[i + 1]) < floor:
            continue
        a, b = i - lo, i + hi + 1
        if a < 0 or b > n:
            seg = [x[j] if 0 <= j < n else 0.0 for j in range(a, b)]
        else:
            seg = x[a:b]
        best = tp[i]
        for taps in KERNELS:
            v = abs(sum(s * t for s, t in zip(seg, taps)))
            if v > best:
                best = v
        tp[i] = best
    return tp


def tp_db(x):
    pk = max(true_peaks(x, 0.5 * max(abs(v) for v in x)))
    return 20.0 * math.log10(pk) if pk > 0 else -200.0


def limit(x, ceiling_db):
    """Look-ahead true-peak limiter. Gain is instant-down/exponential-up in a
    forward pass, then a backward pass ramps it down ahead of every peak."""
    c = 10.0 ** (ceiling_db / 20.0)
    tp = true_peaks(x, 0.5 * c)
    req = [c / p if p > c else 1.0 for p in tp]
    rel = math.exp(-1.0 / (LIMIT_RELEASE_MS * 1e-3 * SR))
    att = math.exp(-1.0 / (LIMIT_ATTACK_MS * 1e-3 * SR / 3.0))   # ~99 % in 1.5 ms
    g = [1.0] * len(x)
    cur = 1.0
    for i, r in enumerate(req):
        cur = min(r, 1.0 - (1.0 - cur) * rel)
        g[i] = cur
    cur = 1.0
    for i in range(len(x) - 1, -1, -1):
        cur = min(g[i], 1.0 - (1.0 - cur) * att)
        g[i] = cur
    gr_db = -20.0 * math.log10(min(g))
    return [v * gi for v, gi in zip(x, g)], gr_db


def rms_db(x):
    r = math.sqrt(sum(v * v for v in x) / max(1, len(x)))
    return 20.0 * math.log10(r) if r > 0 else -200.0


def active_rms_db(x):
    """RMS over the 50 ms windows within 20 dB of the loudest one (ear proxy)."""
    w = int(0.05 * SR)
    wins = [x[k:k + w] for k in range(0, len(x) - w + 1, w)]
    lv = [rms_db(s) for s in wins]
    top = max(lv)
    keep = [v for s, l in zip(wins, lv) if l > top - 20.0 for v in s]
    return rms_db(keep), top


# ------------------------------------------------------------------ main --

def master(slug, src_dir, dst_dir):
    src = os.path.join(src_dir, slug + '.wav')
    dst = os.path.join(dst_dir, slug + '.mp3')
    x = read_wav(src)
    meas = loudnorm_measure(src)
    e_in = ebur128(['-i', src])
    e_sub = ebur128(['-i', src, '-af', 'highpass=f=100'])
    gain_db = TARGET_I - meas['input_i']
    capped = False
    if e_sub['Mmax'] + gain_db > MMAX_CAP:
        gain_db = MMAX_CAP - e_sub['Mmax']
        capped = True
    g = 10.0 ** (gain_db / 20.0)
    y0 = [v * g for v in x]
    ceiling = TARGET_TP
    for attempt in range(4):
        tp0 = tp_db(y0)
        if tp0 > ceiling:
            y, gr = limit(y0, ceiling - 0.05)
        else:
            y, gr = y0, 0.0
        e_wav = ebur128(raw_input_args(), f32(y))
        encode_mp3(y, dst)
        ln_mp3 = loudnorm_measure(dst)          # 0.01 dB resolution
        if ln_mp3['input_tp'] <= MP3_TP_MAX or attempt == 3:
            break
        ceiling -= (ln_mp3['input_tp'] - MP3_TP_MAX) + 0.05
    e_mp3 = ebur128(['-i', dst])
    e_mp3_sub = ebur128(['-i', dst, '-af', 'highpass=f=100'])
    dec = decode_mp3(dst)
    arms, top50 = active_rms_db(dec)
    pr = probe(dst)
    return {
        'slug': slug, 'src': src, 'mp3': dst,
        'input': {'I': meas['input_i'], 'TP': meas['input_tp'], 'LRA': meas['input_lra'],
                  'thresh': meas['input_thresh'], 'Mmax': e_in['Mmax'],
                  'Mmax_sub_deweighted': e_sub['Mmax']},
        'gain_db': round(gain_db, 2), 'mmax_capped': capped,
        'tp_before_limit': round(tp0, 2), 'limiter_ceiling_dbtp': round(ceiling - 0.05, 2),
        'limiter_max_gr_db': round(gr, 2),
        'mastered_float': e_wav,
        'output_mp3': {'I': ln_mp3['input_i'], 'TP': ln_mp3['input_tp'],
                       'LRA': ln_mp3['input_lra'], 'I_ebur128': e_mp3['I'],
                       'TP_ebur128': e_mp3['TP'], 'Mmax': e_mp3['Mmax'],
                       'Mmax_sub_deweighted': e_mp3_sub['Mmax'],
                       'sample_peak_dbfs': round(20 * math.log10(max(abs(v) for v in dec)), 2),
                       'active_rms_db': round(arms, 2), 'loudest_50ms_db': round(top50, 2)},
        'probe': pr, 'bytes': os.path.getsize(dst),
    }


def main(argv):
    if len(argv) < 3:
        sys.stderr.write('usage: python -I master.py <wav_folder> <mp3_folder> [slug ...]\n')
        return 2
    src_dir, dst_dir = argv[1], argv[2]
    os.makedirs(dst_dir, exist_ok=True)
    slugs = argv[3:] or SLUGS
    report = []
    for s in slugs:
        r = master(s, src_dir, dst_dir)
        report.append(r)
        o = r['output_mp3']
        print('%-16s gain %+5.2f dB%s  limiter %4.2f dB | MP3 I %6.2f  TP %6.2f  Mmax %6.1f '
              '(sub-dw %6.1f)  peak %6.2f  actRMS %6.1f | %s %5.3f s %d B'
              % (s, r['gain_db'], ' (Mmax cap)' if r['mmax_capped'] else '           ',
                 r['limiter_max_gr_db'], o['I'], o['TP'], o['Mmax'], o['Mmax_sub_deweighted'],
                 o['sample_peak_dbfs'], o['active_rms_db'], r['probe']['codec'],
                 r['probe']['duration_s'], r['bytes']))
    path = os.path.join(src_dir, 'master-report.json')
    old = []
    if argv[3:] and os.path.exists(path):
        with open(path, encoding='utf-8') as f:
            old = [r for r in json.load(f) if r['slug'] not in slugs]
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(sorted(old + report, key=lambda r: SLUGS.index(r['slug'])), f, indent=1)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
