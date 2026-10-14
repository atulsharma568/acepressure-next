#!/usr/bin/env python3
"""
Victory Fanfare -- an original, fully synthesized brass-style fanfare
for AcePressure tip alerts.

Everything is generated from math with the Python standard library only
(math, random with a fixed seed, wave, array). No samples, no recordings,
no network. Deterministic output. Runs on Python 3.9+ (Windows/macOS/Linux).

Usage:  python3 -I victory-fanfare.py <out.wav>
Output: 44.1 kHz, mono, 16-bit PCM WAV, DC-free, peak-normalized to -1 dBFS.

Original melody (B-flat major, 160 bpm), as scale degrees:
    pickup : 5 5 5            eighth-note triplet on the dominant
    bar    : 1 3 5-  4 6 5 7  arpeggio up, then a rising broken-third line
    final  : 8                held tonic chord with swell, vibrato, timpani
Harmony: V | I . IV V | I with a second voice a 4th/3rd below the lead,
a trombone-like bass line and extra chord tones on the final chord.

Synthesis: each voice is a band-limited (PolyBLEP) sawtooth plus a weak
partner saw 3.5 cents sharp (started in phase, so the fundamental never
cancels), with an upward lip "scoop" into each note. It runs through a
4-pole low-pass (two TPT state-variable stages) whose cutoff jumps up at
every attack and then settles (brass brightness), plus a short band-passed
breath puff on each tongued attack. The held final chord gets a gentle
accent, a soft swell (louder and brighter together), and delayed vibrato.
A broad "bell" formant peak (1.4 kHz) shapes the brass bus. The timpani is
a modal model (inharmonic membrane partials, tension pitch glide,
felt-mallet noise). A small Freeverb-style hall glues the section together.
"""
import math
import random
import sys
import wave
from array import array

SR = 44100
SEED = 7319
TEMPO = 160.0
BEAT = 60.0 / TEMPO
T3 = 1.0 / 3.0

TWO_PI = 2.0 * math.pi
CENT = math.log(2.0) / 1200.0


def mtof(m):
    return 440.0 * 2.0 ** ((m - 69) / 12.0)


def smoothstep(x):
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    return x * x * (3.0 - 2.0 * x)


# ------------------------------------------------------------------ score --
# (start beat, length in beats, MIDI note, velocity).  Key: B-flat major.
LEAD = [
    (0.0, T3, 65, 0.80), (T3, T3, 65, 0.82), (2 * T3, T3, 65, 0.87),   # F F F
    (1.0, 0.5, 70, 0.90), (1.5, 0.5, 74, 0.93), (2.0, 1.0, 77, 1.00),  # Bb D F-
    (3.0, 0.5, 75, 0.95), (3.5, 0.5, 79, 0.98),                        # Eb G
    (4.0, 0.5, 77, 0.95), (4.5, 0.5, 81, 1.00),                        # F A
]
SECOND = [
    (0.0, T3, 60, 0.80), (T3, T3, 60, 0.82), (2 * T3, T3, 60, 0.87),   # C C C
    (1.0, 0.5, 65, 0.88), (1.5, 0.5, 70, 0.90), (2.0, 1.0, 74, 0.96),  # F Bb D-
    (3.0, 0.5, 70, 0.90), (3.5, 0.5, 75, 0.94),                        # Bb Eb
    (4.0, 0.5, 72, 0.93), (4.5, 0.5, 77, 0.98),                        # C F
]
BASS = [
    (0.0, T3, 53, 0.82), (T3, T3, 53, 0.84), (2 * T3, T3, 53, 0.88),   # F F F
    (1.0, 1.0, 46, 0.94), (2.0, 1.0, 46, 0.90),                        # Bb Bb
    (3.0, 1.0, 51, 0.93), (4.0, 1.0, 53, 0.97),                        # Eb F
]
PARTS = [  # (notes, gain, brightness, max timing jitter in seconds)
    (LEAD, 1.00, 1.00, 0.000),     # trumpet-like lead
    (SECOND, 0.72, 0.85, 0.004),   # darker horn-like second voice
    (BASS, 0.78, 0.95, 0.005),     # trombone-like bass
]
FINAL_BEAT = 5.0
FINAL_HOLD = 0.90          # seconds the final chord is held before release
FINAL_CHORD = [  # (MIDI, gain, brightness, vibrato depth cents, vibrato Hz)
    (82, 1.15, 1.00, 14.0, 5.60),   # Bb5  lead
    (77, 0.80, 0.90, 11.0, 5.30),   # F5
    (74, 0.70, 0.85, 10.0, 5.85),   # D5
    (58, 0.58, 0.90, 6.0, 5.10),    # Bb3  trombone
    (46, 0.82, 0.95, 3.0, 4.90),    # Bb2  bass
]
TIMPANI_MIDI = 46          # Bb2, under the final chord
TIMPANI_GAIN = 0.40
TAIL = 0.75                # seconds of release + room after the final hold
                           # (mastering pass: was 0.45 s, which faded the chord
                           # release, timpani and hall out at only ~-28 dB)
REVERB_MIX = 0.07
BELL_FORMANT = (1400.0, 4.0, 0.8)   # brass "bell" peak: Hz, dB, Q


# ------------------------------------------------------------ brass voice --
def render_brass(buf, t0, gate, midi, vel, gain, rng, final=False,
                 vib_depth=0.0, vib_rate=5.5, bright=1.0):
    """Add one brass note (gate seconds long, plus release) into buf."""
    f0 = mtof(midi)
    start = int(round(t0 * SR))
    if final:
        att, rel_tc = 0.030, 0.085
        scoop, scoop_tc = 55.0, 0.024
        f_att, f_tc = 0.055, 0.15
    else:
        att = min(0.018, 0.25 * gate)
        rel_tc = 0.022 if gate < 0.12 else 0.030
        scoop, scoop_tc = 48.0, 0.017
        f_att, f_tc = min(0.030, 0.40 * gate), 0.060
    n_gate = int(gate * SR)
    n_tot = min(n_gate + int(rel_tc * 7.0 * SR), len(buf) - start)

    inv_sr = 1.0 / SR
    pi_sr = math.pi * inv_sr
    fmax = 0.45 * SR
    # main saw plus a weak partner +3.5 cents sharp, both started in phase so
    # a note never begins with its fundamental cancelled; they drift apart
    # only slowly (gentle ensemble shimmer instead of an octave flip).
    det = math.exp(3.5 * CENT)
    ph1 = 0.5 + 0.05 * rng.random()
    ph2 = ph1
    drift = rng.uniform(-2.0, 2.0)        # per-note intonation (cents)
    vph = rng.random() * TWO_PI
    k1, k2 = 1.0 / 0.54, 1.0 / 1.15       # 4-pole, slightly resonant
    s1a = s2a = s1b = s2b = 0.0

    # breath / tongue puff: band-passed noise at the attack
    nz_n = int(0.035 * SR)
    nz_fc = min(5000.0, 1700.0 * (f0 / 466.0) ** 0.35)
    ng = math.tan(math.pi * nz_fc * inv_sr)
    nk = 1.0 / 1.4
    na1 = 1.0 / (1.0 + ng * (ng + nk))
    na2 = ng * na1
    na3 = ng * na2
    n1 = n2 = 0.0
    nz_amp = 0.10 * vel

    rel_mult = math.exp(-1.0 / (rel_tc * SR))
    rel = 1.0
    exp, sin, tan, tanh, sqrt = math.exp, math.sin, math.tan, math.tanh, math.sqrt
    rnd = rng.random
    out_gain = gain * vel

    for i in range(n_tot):
        t = i * inv_sr
        if i < n_gate:
            tt = t
        else:
            tt = gate
            rel *= rel_mult

        # amplitude envelope: accent at the attack, then settle (or swell)
        rise = smoothstep(tt / att)
        if final:
            acc = exp(-max(0.0, tt - att) / 0.12)
            sw = smoothstep((tt - 0.12) / 0.72)
            body = 0.74 + 0.26 * sw
            a = rise * (body + (0.90 - body) * acc)
        else:
            acc = exp(-max(0.0, tt - att) / 0.06)
            sw = 0.0
            a = rise * (0.80 + 0.20 * acc)

        # brightness: rises a little after the amplitude, then settles
        frise = smoothstep(tt / f_att)
        fdec = exp(-max(0.0, tt - f_att) / f_tc)
        if final:
            br = 0.16 + 0.84 * frise * (0.30 + 0.34 * fdec + 0.42 * sw)
        else:
            br = 0.16 + 0.84 * frise * (0.24 + 0.76 * fdec)
        br *= vel * bright
        if i >= n_gate:
            br *= sqrt(rel)
            a *= rel

        # pitch: lip "scoop" into the note, plus delayed vibrato
        cents = drift - scoop * exp(-t / scoop_tc)
        if vib_depth > 0.0:
            vamt = smoothstep((t - 0.26) / 0.38)
            vs = sin(TWO_PI * vib_rate * t + vph)
            cents += vib_depth * vamt * vs
            a *= 1.0 + 0.035 * vamt * vs
        f = f0 * exp(cents * CENT)

        # two PolyBLEP sawtooths
        dt1 = f * inv_sr
        dt2 = dt1 * det
        ph1 += dt1
        if ph1 >= 1.0:
            ph1 -= 1.0
        ph2 += dt2
        if ph2 >= 1.0:
            ph2 -= 1.0
        x1 = 2.0 * ph1 - 1.0
        if ph1 < dt1:
            u = ph1 / dt1
            x1 -= u + u - u * u - 1.0
        elif ph1 > 1.0 - dt1:
            u = (ph1 - 1.0) / dt1
            x1 -= u * u + u + u + 1.0
        x2 = 2.0 * ph2 - 1.0
        if ph2 < dt2:
            u = ph2 / dt2
            x2 -= u + u - u * u - 1.0
        elif ph2 > 1.0 - dt2:
            u = (ph2 - 1.0) / dt2
            x2 -= u * u + u + u + 1.0
        s = (x1 + 0.3 * x2) * (1.0 / 1.3)

        # 4-pole low-pass, cutoff follows brightness and pitch
        fc = f0 * (1.0 + 8.0 * br) + 900.0 * br
        if fc > fmax:
            fc = fmax
        g = tan(pi_sr * fc)
        a1 = 1.0 / (1.0 + g * (g + k1))
        a2 = g * a1
        a3 = g * a2
        v3 = s - s2a
        v1 = a1 * s1a + a2 * v3
        v2 = s2a + a2 * s1a + a3 * v3
        s1a = 2.0 * v1 - s1a
        s2a = 2.0 * v2 - s2a
        b1 = 1.0 / (1.0 + g * (g + k2))
        b2 = g * b1
        b3 = g * b2
        w3 = v2 - s2b
        w1 = b1 * s1b + b2 * w3
        w2 = s2b + b2 * s1b + b3 * w3
        s1b = 2.0 * w1 - s1b
        s2b = 2.0 * w2 - s2b

        # gentle saturation: louder = a touch more edge
        y = tanh(1.5 * w2 * a) * (1.0 / 1.5)

        if i < nz_n:
            e = smoothstep(t / 0.0015) * exp(-t / 0.009)
            wn = rnd() * 2.0 - 1.0
            q3 = wn - n2
            q1 = na1 * n1 + na2 * q3
            q2 = n2 + na2 * n1 + na3 * q3
            n1 = 2.0 * q1 - n1
            n2 = 2.0 * q2 - n2
            y += nz_amp * e * q1

        buf[start + i] += out_gain * y


# ---------------------------------------------------------------- timpani --
def render_timpani(buf, t0, midi, amp, rng):
    """Modal kettle-drum hit: inharmonic membrane modes + thud + felt noise."""
    f = mtof(midi)
    start = int(round(t0 * SR))
    modes = [  # (ratio to principal tone, amplitude, decay seconds)
        (1.000, 1.00, 0.45), (1.504, 0.46, 0.32), (1.742, 0.18, 0.20),
        (1.996, 0.32, 0.25), (2.245, 0.10, 0.16), (2.440, 0.14, 0.17),
        (2.800, 0.06, 0.12), (2.940, 0.06, 0.11),
    ]
    n = len(buf) - start   # ring to the end of the file; the master fade ends it
    inv_sr = 1.0 / SR
    m = len(modes)
    ph = [0.0] * m
    env = [md[1] for md in modes]
    dec = [math.exp(-inv_sr / md[2]) for md in modes]
    inc = [TWO_PI * f * md[0] * inv_sr for md in modes]
    th_ph, th_env = 0.0, 0.70
    th_dec = math.exp(-inv_sr / 0.06)
    nz_env = 1.1
    nz_dec = math.exp(-inv_sr / 0.006)
    c = 1.0 - math.exp(-TWO_PI * 900.0 * inv_sr)
    lp1 = lp2 = 0.0
    exp, sin = math.exp, math.sin
    rnd = rng.random
    for i in range(n):
        t = i * inv_sr
        glide = 1.0 + 0.03 * exp(-t / 0.045)   # tension glide after impact
        s = 0.0
        for j in range(m):
            ph[j] += inc[j] * glide
            env[j] *= dec[j]
            s += env[j] * sin(ph[j])
        th_ph += TWO_PI * f * 0.62 * (1.0 + 0.35 * exp(-t / 0.025)) * inv_sr
        th_env *= th_dec
        s += th_env * sin(th_ph)
        wn = rnd() * 2.0 - 1.0
        lp1 += c * (wn - lp1)
        lp2 += c * (lp1 - lp2)
        nz_env *= nz_dec
        s += nz_env * lp2
        buf[start + i] += amp * smoothstep(t / 0.002) * s


# ------------------------------------------------------------------ hall ---
def hall_reverb(x, room=0.80, damp=0.30, predelay=0.012):
    """Mono Freeverb-style reverb (8 damped combs + 4 allpasses)."""
    n = len(x)
    pd = int(predelay * SR)
    # keep lows and fizz out of the reverb input
    hp_c = math.exp(-TWO_PI * 180.0 / SR)
    lp_c = 1.0 - math.exp(-TWO_PI * 6000.0 / SR)
    xin = [0.0] * n
    hp_y = hp_x = lp = 0.0
    for i in range(n):
        v = x[i]
        hp_y = hp_c * (hp_y + v - hp_x)
        hp_x = v
        lp += lp_c * (hp_y - lp)
        xin[i] = lp
    clen = [1116, 1188, 1277, 1356, 1422, 1491, 1557, 1617]
    alen = [556, 441, 341, 225]
    cb = [[0.0] * L for L in clen]
    ci = [0] * len(clen)
    cf = [0.0] * len(clen)
    ab = [[0.0] * L for L in alen]
    ai = [0] * len(alen)
    out = [0.0] * n
    d1 = 1.0 - damp
    nc = len(clen)
    na = len(alen)
    for i in range(n):
        inp = xin[i - pd] if i >= pd else 0.0
        acc = 0.0
        for c in range(nc):
            b = cb[c]
            k = ci[c]
            o = b[k]
            cf[c] = o * d1 + cf[c] * damp
            b[k] = inp + cf[c] * room
            k += 1
            if k == clen[c]:
                k = 0
            ci[c] = k
            acc += o
        acc *= 0.125
        for a in range(na):
            b = ab[a]
            k = ai[a]
            bo = b[k]
            o = bo - acc
            b[k] = acc + bo * 0.5
            k += 1
            if k == alen[a]:
                k = 0
            ai[a] = k
            acc = o
        out[i] = acc
    return out


# ------------------------------------------------------------- utilities --
def biquad(x, b0, b1, b2, a0, a1, a2):
    b0 /= a0
    b1 /= a0
    b2 /= a0
    a1 /= a0
    a2 /= a0
    y = [0.0] * len(x)
    x1 = x2 = y1 = y2 = 0.0
    for i, v in enumerate(x):
        o = b0 * v + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
        x2, x1 = x1, v
        y2, y1 = y1, o
        y[i] = o
    return y


def peaking(x, fc, gain_db, q):
    """RBJ-cookbook peaking EQ."""
    A = 10.0 ** (gain_db / 40.0)
    w = TWO_PI * fc / SR
    al = math.sin(w) / (2.0 * q)
    cw = math.cos(w)
    return biquad(x, 1 + al * A, -2 * cw, 1 - al * A,
                  1 + al / A, -2 * cw, 1 - al / A)


def highpass(x, fc, q=0.7071):
    w = TWO_PI * fc / SR
    al = math.sin(w) / (2.0 * q)
    cw = math.cos(w)
    return biquad(x, (1 + cw) / 2, -(1 + cw), (1 + cw) / 2,
                  1 + al, -2 * cw, 1 - al)


def write_wav(path, x):
    peak = max(abs(v) for v in x) or 1.0
    scale = (10.0 ** (-1.0 / 20.0)) / peak * 32767.0
    pcm = array('h', [int(round(v * scale)) for v in x])
    if sys.byteorder == 'big':
        pcm.byteswap()
    with wave.open(path, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


# ------------------------------------------------------------------- main --
def main():
    if len(sys.argv) != 2:
        sys.stderr.write("usage: python3 -I victory-fanfare.py <out.wav>\n")
        sys.exit(2)
    rng = random.Random(SEED)
    t_final = FINAL_BEAT * BEAT
    n = int((t_final + FINAL_HOLD + TAIL) * SR)

    brass = [0.0] * n
    for notes, gain, bright, jitter in PARTS:
        for (b, length, midi, vel) in notes:
            t0 = b * BEAT + (rng.uniform(0.0, jitter) if jitter else 0.0)
            if length < 0.4:
                legato = 0.76          # crisp tongued triplets
            elif length <= 0.5:
                legato = 0.84
            else:
                legato = 0.90
            render_brass(brass, t0, length * BEAT * legato, midi, vel, gain,
                         rng, bright=bright)

    for (midi, gain, bright, vd, vr) in FINAL_CHORD:
        t0 = t_final + rng.uniform(0.0, 0.006)
        render_brass(brass, t0, FINAL_HOLD, midi, 1.0, gain, rng, final=True,
                     vib_depth=vd, vib_rate=vr, bright=bright)

    # bell formant on the brass bus, then the timpani joins
    dry = peaking(brass, *BELL_FORMANT)
    render_timpani(dry, t_final + 0.002, TIMPANI_MIDI, TIMPANI_GAIN, rng)

    wet = hall_reverb(dry)
    mix = [d + REVERB_MIX * w for d, w in zip(dry, wet)]

    # DC / subsonic removal, then exact zero mean
    mix = highpass(mix, 22.0)
    mean = sum(mix) / len(mix)
    mix = [v - mean for v in mix]

    # click-free edges: 2 ms raised-cosine fade-in, 55 ms fade-out
    fi = int(0.002 * SR)
    for i in range(fi):
        mix[i] *= 0.5 - 0.5 * math.cos(math.pi * i / fi)
    fo = int(0.055 * SR)
    for i in range(fo):
        mix[n - 1 - i] *= 0.5 - 0.5 * math.cos(math.pi * i / fo)

    write_wav(sys.argv[1], mix)


if __name__ == "__main__":
    main()
