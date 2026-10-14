#!/usr/bin/env python3
"""Vine Boom - an original, fully synthesized "dramatic reveal" boom.

Part of the AcePressure soundboard. Everything is computed from math (no samples,
no recordings, no network). Standard library only, deterministic (fixed seed).

Usage:  python3 -I vine-boom.py out.wav

Output: 44100 Hz, mono, 16-bit PCM WAV, peak-normalised to -1 dBFS.

Signal flow
  body    sine with an exponential pitch drop 120 Hz -> 37 Hz (tau 0.13 s, ~39 Hz
          at 0.5 s) plus a 4 ms upper chirp for the knock, into an asymmetric tanh
          (even + odd harmonics, DC tracked from a lookup table), then two gentle
          low-mid EQ bumps (90 Hz, 200 Hz) for the 80-250 Hz region.
  growl   parallel, harder-driven copy of the same oscillator kept to 120-600 Hz
          (fundamental removed) that blooms in after the attack: the 3rd-8th
          harmonics from which phone speakers let the ear infer the deep pitch.
  bwomp   (mastering pass) band-limited additive harmonics 2..K of the same
          falling pitch, weighted by a vowel-like formant gliding 800 -> 500 Hz
          under a ceiling that sinks 2.6 -> 1 kHz, summed with fixed Schroeder
          phases (low crest factor, no sharp edges for the glue to crackle on).
          It puts the "bwomp" in the 400 Hz - 2 kHz band where phone and laptop
          speakers work, so the boom no longer vanishes on them (phone-speaker
          proxy loudness drop vs full range: 17.7 LU -> 8 LU; sub level -1.5 dB).
  click   white noise through a swept 4-pole state-variable low-pass
          (3.25 kHz -> 250 Hz), high-passed at 400 Hz, ~8 ms decay: the punch.
  thump   noise band-passed around 90 Hz, ~70 ms decay: the air push.
  rumble  dark 60-250 Hz noise bed that decays with the body.
  reverb  small Freeverb-style tail (8 damped combs + 4 all-passes) fed only
          with 90-800 Hz, low-passed on return and ducked under the hit.
  master  gentle tanh glue, 20 Hz high-pass, DC removal, 2 ms / 50 ms fades,
          peak-normalise to -1 dBFS.
"""

import math
import random
import struct
import sys
import wave

SR = 44100
DUR = 1.60                     # seconds, total file length
N = int(round(SR * DUR))
SEED = 0x5EEDB00               # fixed seed -> identical output on every run
PEAK_DBFS = -1.0
FADE_IN_S = 0.002
FADE_OUT_S = 0.050
TWO_PI = 2.0 * math.pi

# ------------------------------------------------------------- tunables -----
F_START, F_END, TAU_P = 120.0, 37.0, 0.13   # main pitch drop
F_KICK, TAU_K = 70.0, 0.004                 # extra few-ms chirp on top (knock)
BODY_TAU = 0.38                             # body amplitude decay (s)
BODY_TAPER = (0.85, 1.42)                   # cosine taper to silence (s)
BODY_DRIVE, BODY_BIAS = 2.6, 0.20           # asymmetric tanh shaper
PUNCH, PUNCH_TAU = 0.40, 0.025              # post-shaper transient lift
BODY_EQ = ((90.0, 0.8, 3.5), (200.0, 0.8, 2.0))    # (Hz, Q, dB) peaking bumps
CLICK_LVL, CLICK_TAU = 5.0, 0.008
CLICK_F_HI, CLICK_F_LO, CLICK_F_TAU = 3250.0, 250.0, 0.010
CLICK_HP = 400.0                            # optional high-pass on the click (Hz)
THUMP_LVL, THUMP_HZ, THUMP_TAU = 0.6, 90.0, 0.07    # level re unit-RMS noise
RUMBLE_LVL, RUMBLE_TAU = 0.45, 0.22                 # level re unit-RMS noise
REV_FEEDBACK, REV_DAMP = 0.86, 0.70
WET = 1.5                                   # reverb return level (after bloom)
GROWL_LVL, GROWL_DRIVE, GROWL_TAU = 2.5, 5.0, 0.33    # parallel harmonic layer
BWOMP_LVL, BWOMP_TAU, BWOMP_BLOOM = 0.50, 0.35, 0.02  # phone-band harmonic layer
BWOMP_FORMANT = (800.0, 500.0, 0.25)        # formant start Hz, end Hz, glide tau (s)
BWOMP_WIDTH_OCT = 0.85                      # formant width (log-Gaussian, octaves)
BWOMP_TOP = (2600.0, 1000.0, 0.30)          # harmonics fade to zero at this frequency:
                                            # start Hz, end Hz, tau (s) - highs die first
BWOMP_MAX_HARM = 60
GLUE = 1.8                                  # master tanh drive


# ---------------------------------------------------------------- filters ---

def rbj(kind, fc, q=0.7071067811865476, gain_db=0.0):
    """RBJ audio-EQ-cookbook biquad coefficients (b0, b1, b2, a1, a2), a0 = 1."""
    w0 = TWO_PI * fc / SR
    cw = math.cos(w0)
    alpha = math.sin(w0) / (2.0 * q)
    if kind == "lp":
        b0, b1, b2 = (1 - cw) / 2, 1 - cw, (1 - cw) / 2
        a0, a1, a2 = 1 + alpha, -2 * cw, 1 - alpha
    elif kind == "hp":
        b0, b1, b2 = (1 + cw) / 2, -(1 + cw), (1 + cw) / 2
        a0, a1, a2 = 1 + alpha, -2 * cw, 1 - alpha
    elif kind == "bp":  # constant 0 dB peak gain
        b0, b1, b2 = alpha, 0.0, -alpha
        a0, a1, a2 = 1 + alpha, -2 * cw, 1 - alpha
    elif kind == "peak":
        A = 10.0 ** (gain_db / 40.0)
        b0, b1, b2 = 1 + alpha * A, -2 * cw, 1 - alpha * A
        a0, a1, a2 = 1 + alpha / A, -2 * cw, 1 - alpha / A
    else:
        raise ValueError(kind)
    return (b0 / a0, b1 / a0, b2 / a0, a1 / a0, a2 / a0)


def biquad(x, coeffs):
    b0, b1, b2, a1, a2 = coeffs
    y = [0.0] * len(x)
    x1 = x2 = y1 = y2 = 0.0
    for i, xi in enumerate(x):
        yi = b0 * xi + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
        x2 = x1
        x1 = xi
        y2 = y1
        y1 = yi
        y[i] = yi
    return y


def svf_lp_sweep(x, fc_of_t, q=0.7071067811865476):
    """Zavalishin TPT state-variable low-pass; the cutoff may move every sample."""
    k = 1.0 / q
    ic1 = ic2 = 0.0
    y = [0.0] * len(x)
    for i, xi in enumerate(x):
        g = math.tan(math.pi * fc_of_t(i / SR) / SR)
        a1 = 1.0 / (1.0 + g * (g + k))
        a2 = g * a1
        a3 = g * a2
        v3 = xi - ic2
        v1 = a1 * ic1 + a2 * v3
        v2 = ic2 + a2 * ic1 + a3 * v3
        ic1 = 2.0 * v1 - ic1
        ic2 = 2.0 * v2 - ic2
        y[i] = v2
    return y


def comb_lp(x, delay, feedback, damp):
    """Freeverb-style comb with a one-pole low-pass in the feedback path."""
    buf = [0.0] * delay
    idx = 0
    store = 0.0
    y = [0.0] * len(x)
    for i, xi in enumerate(x):
        out = buf[idx]
        store = out * (1.0 - damp) + store * damp
        buf[idx] = xi + store * feedback
        idx += 1
        if idx == delay:
            idx = 0
        y[i] = out
    return y


def allpass(x, delay, g):
    """Schroeder all-pass: H(z) = (-g + z^-D) / (1 - g z^-D)."""
    buf = [0.0] * delay
    idx = 0
    y = [0.0] * len(x)
    for i, xi in enumerate(x):
        d = buf[idx]
        w = xi + g * d
        buf[idx] = w
        idx += 1
        if idx == delay:
            idx = 0
        y[i] = d - g * w
    return y


def dark_reverb(x):
    """Small, heavily damped mono reverb (8 parallel combs, 4 series all-passes)."""
    predelay = int(0.010 * SR)
    xin = [0.0] * predelay + x[: len(x) - predelay]
    combs = (1116, 1188, 1277, 1356, 1422, 1491, 1557, 1617)
    acc = [0.0] * len(x)
    for d in combs:
        for i, v in enumerate(comb_lp(xin, d, REV_FEEDBACK, REV_DAMP)):
            acc[i] += v
    for d in (556, 441, 341, 225):
        acc = allpass(acc, d, 0.5)
    scale = 1.0 / len(combs)
    return [v * scale for v in acc]


# ---------------------------------------------------------------- helpers ---

def phase(t):
    """Closed-form integral of the instantaneous frequency (radians)."""
    return TWO_PI * (F_END * t
                     + (F_START - F_END) * TAU_P * (1.0 - math.exp(-t / TAU_P))
                     + F_KICK * TAU_K * (1.0 - math.exp(-t / TAU_K)))


def smoothstep(e0, e1, t):
    u = min(1.0, max(0.0, (t - e0) / (e1 - e0)))
    return u * u * (3.0 - 2.0 * u)


def taper(t, t1, t2):
    if t <= t1:
        return 1.0
    if t >= t2:
        return 0.0
    return 0.5 * (1.0 + math.cos(math.pi * (t - t1) / (t2 - t1)))


def unit_rms(x):
    r = math.sqrt(sum(v * v for v in x) / len(x))
    return [v / r for v in x]


def dc_table(drive, bias, a_max=1.6, steps=160, n=512):
    """Cycle-average (DC) of the asymmetric shaper for sine amplitude a."""
    off = math.tanh(drive * bias)
    tab = []
    for j in range(steps + 1):
        a = a_max * j / steps
        acc = 0.0
        for k in range(n):
            acc += math.tanh(drive * (a * math.sin(TWO_PI * k / n) + bias)) - off
        tab.append(acc / n)
    return tab, a_max / steps


# ---------------------------------------------------------------- layers ----

def body_layer():
    """Pitch-dropping sine into an asymmetric tanh (even + odd harmonics).

    The shaper's slowly varying DC offset is cancelled from a lookup table so the
    body stays centred without a high-pass transient.
    """
    off = math.tanh(BODY_DRIVE * BODY_BIAS)
    tab, da = dc_table(BODY_DRIVE, BODY_BIAS)
    last = len(tab) - 2
    t1, t2 = BODY_TAPER
    y = [0.0] * N
    for i in range(N):
        t = i / SR
        a = math.exp(-t / BODY_TAU) * (1.0 + 0.25 * math.exp(-t / 0.05)) * taper(t, t1, t2)
        pos = a / da
        j = min(int(pos), last)
        dc = tab[j] + (tab[j + 1] - tab[j]) * (pos - j)
        shaped = math.tanh(BODY_DRIVE * (a * math.sin(phase(t)) + BODY_BIAS)) - off - dc
        y[i] = (1.0 + PUNCH * math.exp(-t / PUNCH_TAU)) * shaped
    for fc, q, g in BODY_EQ:
        y = biquad(y, rbj("peak", fc, q, g))
    return y


def growl_layer():
    """Parallel, harder-driven copy of the oscillator, kept to 120-600 Hz.

    It carries the 3rd-8th harmonics that phone speakers can reproduce (the ear
    infers the deep fundamental from them).  The 4th-order high-pass removes the
    fundamental, and the layer blooms in over 60 ms so it never smears the attack.
    """
    t1, t2 = BODY_TAPER
    y = [0.0] * N
    off = math.tanh(GROWL_DRIVE * 0.1)
    for i in range(N):
        t = i / SR
        a = math.exp(-t / BODY_TAU) * taper(t, t1, t2)
        env = smoothstep(0.0, 0.06, t) * math.exp(-t / GROWL_TAU)
        y[i] = env * (math.tanh(GROWL_DRIVE * (a * math.sin(phase(t)) + 0.1)) - off)
    for c in (rbj("hp", 120.0), rbj("hp", 120.0), rbj("lp", 600.0)):
        y = biquad(y, c)
    return y


def bwomp_layer():
    """Band-limited harmonic "bwomp" that follows the boom's falling pitch.

    Harmonics 2..K of the body's phase are weighted by a log-Gaussian formant
    that glides from 800 Hz to 500 Hz ("bwOOm") and fade linearly to zero at a
    ceiling that itself sinks from 2.6 kHz to 1 kHz (high harmonics die first,
    so the tail darkens). A harmonic that enters or leaves as the pitch falls
    does so at zero amplitude, and nothing ever aliases. Fixed Schroeder
    phases keep the crest factor low, and the smooth waveform gives the master
    glue no edges to crackle on.
    """
    t1, t2 = BODY_TAPER
    k_max = BWOMP_MAX_HARM
    theta = [math.pi * k * k / k_max for k in range(k_max + 1)]
    f_a, f_b, f_tau = BWOMP_FORMANT
    top_a, top_b, top_tau = BWOMP_TOP
    inv_width = 1.0 / (math.log(2.0) * BWOMP_WIDTH_OCT)
    y = [0.0] * N
    for i in range(N):
        t = i / SR
        env = smoothstep(0.0, BWOMP_BLOOM, t) * math.exp(-t / BWOMP_TAU) * taper(t, t1, t2)
        if env < 1e-7:
            continue
        # instantaneous frequency = d(phase)/dt / 2pi
        f = F_END + (F_START - F_END) * math.exp(-t / TAU_P) + F_KICK * math.exp(-t / TAU_K)
        ph = phase(t)
        fc = f_b + (f_a - f_b) * math.exp(-t / f_tau)
        top = top_b + (top_a - top_b) * math.exp(-t / top_tau)
        acc = 0.0
        for k in range(2, k_max + 1):
            fk = k * f
            if fk >= top:
                break
            x = math.log(fk / fc) * inv_width
            acc += math.exp(-0.5 * x * x) * (1.0 - fk / top) * math.sin(k * ph + theta[k])
        y[i] = env * acc
    return y


def noise_layers(rng):
    white = [rng.random() * 2.0 - 1.0 for _ in range(N)]

    n_click = int(0.08 * SR)
    fc = lambda t: CLICK_F_LO + (CLICK_F_HI - CLICK_F_LO) * math.exp(-t / CLICK_F_TAU)
    click = svf_lp_sweep(svf_lp_sweep(white[:n_click], fc), fc)
    if CLICK_HP:
        click = biquad(click, rbj("hp", CLICK_HP))
    click = [v * math.exp(-i / SR / CLICK_TAU) for i, v in enumerate(click)]
    click += [0.0] * (N - n_click)

    thump = unit_rms(biquad(biquad(white, rbj("bp", THUMP_HZ, 0.8)), rbj("lp", 220.0)))
    thump = [v * math.exp(-i / SR / THUMP_TAU) for i, v in enumerate(thump)]

    rumble = [rng.random() * 2.0 - 1.0 for _ in range(N)]
    for c in (rbj("lp", 250.0), rbj("lp", 250.0), rbj("hp", 60.0)):
        rumble = biquad(rumble, c)
    rumble = unit_rms(rumble)
    rumble = [v * math.exp(-i / SR / RUMBLE_TAU) * taper(i / SR, 0.7, 1.3)
              for i, v in enumerate(rumble)]
    return click, thump, rumble


# ---------------------------------------------------------------- render ----

def render():
    rng = random.Random(SEED)
    body = body_layer()
    growl = growl_layer()
    bwomp = bwomp_layer()
    click, thump, rumble = noise_layers(rng)

    dry = [body[i] + GROWL_LVL * growl[i] + BWOMP_LVL * bwomp[i] + CLICK_LVL * click[i]
           + THUMP_LVL * thump[i] + RUMBLE_LVL * rumble[i] for i in range(N)]

    # Reverb sees only 90-800 Hz: a dark low-mid "room"; the sub stays dry and tight.
    send = dry
    for c in (rbj("hp", 90.0), rbj("hp", 90.0), rbj("lp", 800.0)):
        send = biquad(send, c)
    wet = biquad(dark_reverb(send), rbj("lp", 1200.0))
    # Lightly "ducked" return: drier under the hit, blooming into the tail.
    mix = [dry[i] + WET * (0.55 + 0.45 * smoothstep(0.25, 0.85, i / SR)) * wet[i]
           for i in range(N)]

    # Gentle master saturation: rounds the first peaks, adds audible harmonics.
    pk = max(abs(v) for v in mix)
    ng = math.tanh(GLUE)
    mix = [math.tanh(GLUE * v / pk) / ng for v in mix]

    # Remove sub-sonic content / DC (2nd-order Butterworth HP at 20 Hz).
    mix = biquad(mix, rbj("hp", 20.0))

    # Click-free edges: 2 ms raised-cosine fade-in, 50 ms fade-out.
    n_in = int(FADE_IN_S * SR)
    n_out = int(FADE_OUT_S * SR)
    w = [1.0] * N
    for i in range(n_in):
        w[i] = 0.5 - 0.5 * math.cos(math.pi * i / n_in)
    for k in range(n_out):
        w[N - 1 - k] = 0.5 - 0.5 * math.cos(math.pi * k / n_out)
    mix = [v * g for v, g in zip(mix, w)]
    # Zero the residual DC without disturbing the silent endpoints.
    m = sum(mix) / sum(w)
    mix = [v - m * g for v, g in zip(mix, w)]

    peak = max(abs(v) for v in mix)
    gain = (10.0 ** (PEAK_DBFS / 20.0)) / peak
    return [v * gain for v in mix]


def write_wav(path, samples):
    pcm = [max(-32768, min(32767, int(round(v * 32767.0)))) for v in samples]
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(struct.pack("<%dh" % len(pcm), *pcm))


def main(argv):
    if len(argv) != 2:
        sys.stderr.write("usage: python3 -I vine-boom.py <out.wav>\n")
        return 2
    write_wav(argv[1], render())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
