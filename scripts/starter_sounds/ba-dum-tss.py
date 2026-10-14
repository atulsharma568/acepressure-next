#!/usr/bin/env python3
"""ba-dum-tss.py - original "Ba Dum Tss" rimshot sting for AcePressure.

Synthesized entirely from math: sines, seeded pseudo-random noise, RBJ-cookbook
biquads and a small Freeverb-style room. No samples, recordings or network.
Deterministic (fixed seeds). Pure standard library, Python 3.9+.

    python3 -I ba-dum-tss.py out.wav

Output: 44.1 kHz mono 16-bit PCM WAV, peak-normalized to -1 dBFS.

Timeline:
    0.000 s  "ba"  high tom (~200 Hz): pitch-dropping sine body + circular-
                   membrane overtones + short noise snap / stick knock
    0.170 s  "dum" lower (~158 Hz), rounder tom
    0.420 s  "tss" cymbal: stick tick + high-passed noise sizzle (6-14 kHz)
                   + inharmonic metallic partials, ~0.9 s decay,
                   with a soft kick underneath for the landing
A light Freeverb-style room (public-domain algorithm) glues it together.
"""
import math
import random
import sys
import wave
from array import array

SR = 44100
TWO_PI = 2.0 * math.pi

TOTAL_S = 1.50
T_BA, T_DUM, T_TSS = 0.000, 0.170, 0.420
KICK_FLAM_S = 0.006
CYM_GAIN = 0.60
CYM_CEILING = 0.5
TOM_SNAP = (1.20, 1.00)   # (ba, dum) stick snap level
TOM_KNOCK = (0.70, 0.60)  # (ba, dum) mid knock level
TOM_GAIN = (1.05, 1.00)   # (ba, dum) mix level


# ----------------------------------------------------------------- DSP basics
def rbj(kind, fc, q=0.7071, gain_db=0.0):
    """RBJ audio-EQ-cookbook biquad coefficients (b0, b1, b2, a1, a2)."""
    w0 = TWO_PI * fc / SR
    cw, sw = math.cos(w0), math.sin(w0)
    al = sw / (2.0 * q)
    if kind == "lp":
        b = ((1 - cw) / 2, 1 - cw, (1 - cw) / 2)
        a = (1 + al, -2 * cw, 1 - al)
    elif kind == "hp":
        b = ((1 + cw) / 2, -(1 + cw), (1 + cw) / 2)
        a = (1 + al, -2 * cw, 1 - al)
    elif kind == "bp":  # constant 0 dB peak gain
        b = (al, 0.0, -al)
        a = (1 + al, -2 * cw, 1 - al)
    elif kind == "peak":
        A = 10 ** (gain_db / 40)
        b = (1 + al * A, -2 * cw, 1 - al * A)
        a = (1 + al / A, -2 * cw, 1 - al / A)
    else:
        raise ValueError(kind)
    return (b[0] / a[0], b[1] / a[0], b[2] / a[0], a[1] / a[0], a[2] / a[0])


def biquad(x, kind, fc, q=0.7071, gain_db=0.0):
    b0, b1, b2, a1, a2 = rbj(kind, fc, q, gain_db)
    y = [0.0] * len(x)
    x1 = x2 = y1 = y2 = 0.0
    for i, xi in enumerate(x):
        yi = b0 * xi + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
        x2, x1, y2, y1 = x1, xi, y1, yi
        y[i] = yi
    return y


def chain(x, *stages):
    for st in stages:
        x = biquad(x, *st)
    return x


def white(n, seed):
    rnd = random.Random(seed).random
    return [2.0 * rnd() - 1.0 for _ in range(n)]


def unit_rms(x):
    e = math.sqrt(sum(v * v for v in x) / len(x))
    return [v / e for v in x] if e > 0 else x


def peak_norm(x):
    p = max(abs(v) for v in x)
    return [v / p for v in x] if p > 0 else x


def smooth_limit(x, ceiling, attack_s=0.0015, release_s=0.025):
    """Peak limiter with a smooth gain curve: instant-drop forward pass with
    exponential release, then a backward pass that ramps into each dip."""
    n = len(x)
    req = [ceiling / abs(v) if abs(v) > ceiling else 1.0 for v in x]
    rel = math.exp(-1.0 / (release_s * SR))
    att = math.exp(-1.0 / (attack_s * SR))
    g, cur = [1.0] * n, 1.0
    for i in range(n):
        cur = min(req[i], 1.0 - (1.0 - cur) * rel)
        g[i] = cur
    cur = 1.0
    for i in range(n - 1, -1, -1):
        cur = min(g[i], 1.0 - (1.0 - cur) * att)
        g[i] = cur
    return [v * gi for v, gi in zip(x, g)]


def mix_into(dst, src, at_s, gain):
    o = int(round(at_s * SR))
    for i, v in enumerate(src):
        j = o + i
        if j >= len(dst):
            break
        dst[j] += gain * v


# ---------------------------------------------------------------------- tom
# Circular-membrane mode ratios (Bessel zeros) with relative level and a
# decay multiplier (higher modes die faster).
MODES = ((1.00, 1.00, 1.00), (1.59, 0.48, 0.42), (2.14, 0.24, 0.30),
         (2.30, 0.18, 0.26), (2.65, 0.10, 0.21), (2.92, 0.06, 0.17),
         # Upper modes: brief, but they carry the "bonk" that small phone
         # speakers can actually reproduce.
         (3.16, 0.06, 0.15), (3.50, 0.05, 0.13), (3.60, 0.045, 0.12),
         (4.06, 0.035, 0.10), (4.23, 0.03, 0.09))


def tom(f0, length, decay, bend, snap, thud, knock, seed):
    n = int(length * SR)
    # Pitch envelope shared by all modes: fast drop plus a slow sag.
    bendf = [1.0 + bend * math.exp(-i / (SR * 0.016)) + 0.04 * math.exp(-i / (SR * 0.12))
             for i in range(n)]
    body = [0.0] * n
    for ratio, amp, dscale in MODES:
        w = TWO_PI * f0 * ratio / SR
        k = math.exp(-1.0 / (SR * decay * dscale))
        env, ph = amp, 0.0
        for i in range(n):
            ph += w * bendf[i]
            body[i] += env * math.sin(ph)
            env *= k
    snap_n = unit_rms(chain(white(n, seed), ("hp", 1200.0), ("bp", 3000.0, 0.8), ("lp", 8000.0)))
    thud_n = unit_rms(biquad(white(n, seed + 1), "bp", f0 * 2.4, 1.4))
    knock_n = unit_rms(biquad(white(n, seed + 2), "bp", 1100.0, 1.0))  # stick on head
    out = [0.0] * n
    for i in range(n):
        t = i / SR
        att = 1.0 - math.exp(-t / 0.0007)
        punch = 1.0 + 0.5 * math.exp(-t / 0.010)
        out[i] = (body[i] * punch * att
                  + snap * snap_n[i] * math.exp(-t / 0.007) * att
                  + knock * knock_n[i] * math.exp(-t / 0.012) * att
                  + thud * thud_n[i] * math.exp(-t / 0.020) * att)
    return peak_norm(out)


def kick(length, f_end=56.0, decay=0.075):
    """Soft bass-drum thump layered under the cymbal for the final accent."""
    n = int(length * SR)
    out, ph = [0.0] * n, 0.0
    for i in range(n):
        t = i / SR
        f = f_end * (1.0 + 1.4 * math.exp(-t / 0.025))
        ph += TWO_PI * f / SR
        out[i] = math.sin(ph) * math.exp(-t / decay) * (1.0 - math.exp(-t / 0.001))
    return peak_norm(out)


# ------------------------------------------------------------------- cymbal
PARTIALS = (  # (Hz, level, decay s): sparse inharmonic "ping" modes; all
    # decay faster than the sizzle tail so no whistle is left at the end.
    (3413.0, 0.26, 0.21), (4127.0, 0.30, 0.19), (4783.0, 0.24, 0.18),
    (5263.0, 0.34, 0.17), (6011.0, 0.30, 0.16), (6987.0, 0.36, 0.15),
    (7741.0, 0.30, 0.14), (8689.0, 0.32, 0.13), (9817.0, 0.26, 0.11),
    (10531.0, 0.22, 0.10))


def tamed_noise(n, seed, *stages):
    """Band-limited unit-RMS noise with its rare random spikes held to ~3x RMS
    (crest-factor control before any envelope is applied, so transients
    shaped later by the envelopes stay intact)."""
    return smooth_limit(unit_rms(chain(white(n, seed), *stages)), 3.0)


def cymbal(length, seed):
    n = int(length * SR)
    siz = tamed_noise(n, seed, ("hp", 6000.0), ("hp", 6000.0), ("lp", 14000.0),
                      ("lp", 14000.0), ("peak", 9000.0, 0.9, 3.0))
    air = tamed_noise(n, seed + 1, ("hp", 10000.0), ("lp", 14500.0), ("lp", 14500.0))
    wash = tamed_noise(n, seed + 2, ("hp", 3500.0), ("lp", 7000.0))
    tick = tamed_noise(n, seed + 3, ("hp", 2500.0), ("lp", 11000.0))

    # Metallic bank: six inharmonic square oscillators, band-passed high.
    # The squares are deliberately naive: their aliases only add more
    # inharmonic clang, and the steep band-pass keeps it in 5-13 kHz.
    bank = [0.0] * n
    for f in (317.3, 449.1, 548.9, 703.7, 829.3, 1061.9):
        inc, ph = f / SR, (f * 0.0137) % 1.0
        for i in range(n):
            bank[i] += 1.0 if ph < 0.5 else -1.0
            ph += inc
            if ph >= 1.0:
                ph -= 1.0
    metal = smooth_limit(unit_rms(chain(bank, ("hp", 5000.0), ("hp", 5000.0),
                                        ("bp", 7500.0, 0.9), ("lp", 13000.0))), 3.0)

    # Explicit inharmonic partials, each with a slightly detuned twin so they
    # beat (shimmer) instead of sounding like a steady whistle.
    part = [0.0] * n
    for f, a, d in PARTIALS:
        for twin, ta in ((1.0, 1.0), (1.0031, 0.6)):
            w = TWO_PI * f * twin / SR
            k = math.exp(-1.0 / (SR * d))
            env, ph = a * ta, 0.0
            for i in range(n):
                part[i] += env * math.sin(ph)
                ph += w
                env *= k

    out = [0.0] * n
    for i in range(n):
        t = i / SR
        att = 1.0 - math.exp(-t / 0.0012)
        e_siz = (0.35 * math.exp(-t / 0.040) + 0.65 * math.exp(-t / 0.26)) * att
        e_air = math.exp(-t / 0.14) * (1.0 - math.exp(-t / 0.004))
        e_wash = math.exp(-t / 0.060) * att
        e_tick = math.exp(-t / 0.0030) * (1.0 - math.exp(-t / 0.0005))
        e_met = math.exp(-t / 0.16) * att
        out[i] = (1.00 * siz[i] * e_siz + 0.45 * air[i] * e_air + 0.30 * wash[i] * e_wash
                  + 1.50 * tick[i] * e_tick + 0.75 * metal[i] * e_met + 0.30 * part[i] * att)
    # Light smooth limiting of the summed layers (no waveshaping, so no extra
    # highs or inter-sample overs) so chance pile-ups of layer peaks do not
    # set the cymbal level; the stick transient still pokes out.
    return peak_norm(smooth_limit(peak_norm(out), CYM_CEILING))


# --------------------------------------------------------------------- room
def room(x, size=0.5, feedback=0.72, damp=0.45, predelay_s=0.007):
    """Small Freeverb-style room: parallel damped combs into series allpasses."""
    pre = int(predelay_s * SR)
    src = [0.0] * pre + x
    n = len(src)
    acc = [0.0] * n
    for d0 in (1116, 1188, 1277, 1356, 1422, 1491, 1557, 1617):
        d = int(d0 * size)
        buf, idx, store = [0.0] * d, 0, 0.0
        for i in range(n):
            o = buf[idx]
            store = o * (1.0 - damp) + store * damp
            buf[idx] = src[i] + store * feedback
            idx = idx + 1 if idx + 1 < d else 0
            acc[i] += o
    for d0 in (556, 441, 341, 225):
        d = int(d0 * size)
        buf, idx = [0.0] * d, 0
        for i in range(n):
            b = buf[idx]
            buf[idx] = acc[i] + b * 0.5
            acc[i] = b - acc[i]
            idx = idx + 1 if idx + 1 < d else 0
    return acc[:len(x)]


# --------------------------------------------------------------- finishing
def finish(x, fade_in_s=0.002, fade_out_s=0.050, peak_dbfs=-1.0):
    n = len(x)
    # DC blocker (one-pole high-pass ~20 Hz).
    r = math.exp(-TWO_PI * 20.0 / SR)
    y, x1, y1 = [0.0] * n, 0.0, 0.0
    for i, v in enumerate(x):
        y1 = v - x1 + r * y1
        x1 = v
        y[i] = y1
    fi, fo = int(fade_in_s * SR), int(fade_out_s * SR)
    for i in range(fi):
        y[i] *= 0.5 - 0.5 * math.cos(math.pi * i / fi)
    for j in range(fo):
        y[n - fo + j] *= 0.5 + 0.5 * math.cos(math.pi * (j + 1) / fo)
    # Remove any residual mean with a full-length sine^2 window so the
    # faded endpoints stay at exactly zero.
    win = [math.sin(math.pi * i / (n - 1)) ** 2 for i in range(n)]
    c = sum(y) / sum(win)
    y = [v - c * w for v, w in zip(y, win)]
    g = (10 ** (peak_dbfs / 20.0)) / max(abs(v) for v in y)
    return [v * g for v in y]


def write_wav(path, x):
    pcm = array("h", (max(-32767, min(32767, int(round(v * 32767.0)))) for v in x))
    if sys.byteorder == "big":
        pcm.byteswap()
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def render():
    n = int(TOTAL_S * SR)
    toms = [0.0] * n
    mix_into(toms, tom(200.0, TOTAL_S - T_BA, decay=0.11, bend=0.50, snap=TOM_SNAP[0],
                       thud=0.32, knock=TOM_KNOCK[0], seed=11), T_BA, TOM_GAIN[0])
    mix_into(toms, tom(158.0, TOTAL_S - T_DUM, decay=0.14, bend=0.45, snap=TOM_SNAP[1],
                       thud=0.32, knock=TOM_KNOCK[1], seed=21), T_DUM, TOM_GAIN[1])
    # Gentle tanh bus saturation: rounder peaks and a few harmonics so the
    # toms still read on small phone/laptop speakers.
    drive = 1.5
    p = max(abs(v) for v in toms)
    toms = [math.tanh(drive * v / p) / math.tanh(drive) for v in toms]

    dry = toms[:]
    mix_into(dry, cymbal(TOTAL_S - T_TSS, seed=31), T_TSS, CYM_GAIN)
    # Kick lands a natural 6 ms flam after the cymbal so its first lobe does
    # not stack on top of the stick tick.
    mix_into(dry, kick(TOTAL_S - T_TSS - KICK_FLAM_S), T_TSS + KICK_FLAM_S, 0.30)

    wet = room(biquad(dry, "hp", 180.0))
    e_dry = sum(v * v for v in dry)
    e_wet = sum(v * v for v in wet)
    wet_gain = math.sqrt(e_dry / e_wet) * 10 ** (-15.0 / 20.0) if e_wet > 0 else 0.0
    return finish([d + wet_gain * w for d, w in zip(dry, wet)])


def main(argv):
    if len(argv) != 2:
        sys.stderr.write("usage: python3 -I ba-dum-tss.py <out.wav>\n")
        return 2
    write_wav(argv[1], render())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
