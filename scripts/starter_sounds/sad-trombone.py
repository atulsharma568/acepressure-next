#!/usr/bin/env python3
"""AcePressure sound effect: "Sad Trombone" (slug: sad-trombone).

Original and royalty-free: synthesized purely from math. No samples, no
recordings, no network. Deterministic (fixed seed). Standard library only;
runs on any Python 3.9+ (Windows, macOS, Linux).

    python3 -I sad-trombone.py <out.wav>

The generic "wah wah wah wahhh" failure trope: four notes falling a semitone
at a time (D4, C#4, C4, B3). Three short "wah"s, then a long one that sobs
with a wide, slow, deepening vibrato.

Signal chain (one monophonic "player"):
  phase-continuous PolyBLEP sawtooth (+ a little breath noise), instant
  pitch steps between notes (no portamento), soft 35-40 ms attacks
  -> two cascaded TPT state-variable low-passes (24 dB/oct, resonant) whose
     key-tracked cutoff goes closed -> open -> closed on every note: the
     plunger "wah"
  -> a moving vowel formant (TPT SVF peak, 480 -> 1350 Hz) in step with it,
     so the plunger "talks": "oo" -> "ah" -> "oo"
  -> gentle asymmetric tanh saturation (a little brass edge on the peaks)
  -> RBJ-cookbook biquads: bell-radiation high-pass (partials 2-5 lead, as
     in a real trombone), ~600 Hz body peak, 7 kHz high cut
  -> airy breath noise pulsed at the lip rate, strongest on the attacks
  -> small Schroeder/Freeverb-style room (8 damped combs, 4 allpasses)
  -> DC removal, 2 ms fade-in, 45 ms fade-out, peak-normalize to -1 dBFS
  -> 44.1 kHz mono 16-bit PCM WAV
"""

import array
import math
import os
import random
import sys
import wave

SR = 44100
SEED = 7041            # fixed seed: identical output on every run
TOTAL_S = 2.42
FADE_IN_S = 0.002
FADE_OUT_S = 0.045
PEAK_DBFS = -1.0

# (start s, length s, MIDI note, level): four notes a semitone apart.
# Levels differ slightly, as a player's would.
NOTES = [
    (0.000, 0.340, 62, 1.00),  # D4   "wah"
    (0.340, 0.340, 61, 0.95),  # C#4  "wah"
    (0.680, 0.340, 60, 0.97),  # C4   "wah"
    (1.020, 1.200, 59, 1.03),  # B3   "wahhhh" with the sobbing vibrato
]

FLOOR = 0.10           # level in the dip between notes (re-articulated, one breath)
RC_CLOSED = 1.35       # wah cutoff, plunger closed  (x note pitch)  -> muffled
RC_OPEN = 12.0         # wah cutoff, plunger open    (x note pitch)  -> brassy
WAH_Q = 2.2            # resonance of the second low-pass stage
FORMANT_CLOSED = 480.0  # moving vowel formant, Hz: "oo" ...
FORMANT_OPEN = 1350.0   # ... to "ah"
FORMANT_Q = 1.6
FORMANT_GAIN = 2.0      # +6 dB
SAT_DRIVE = 1.0
BELL_HP_HZ = 350.0
VIB_CENTS = 60.0        # final vibrato depth (+/- cents)


def midi_hz(m):
    return 440.0 * 2.0 ** ((m - 69) / 12.0)


def rc(x):
    """Raised-cosine ramp: 0 for x <= 0, 1 for x >= 1, smooth in between."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    return 0.5 - 0.5 * math.cos(math.pi * x)


def value_noise(n, rng, step_s):
    """Smooth random curve in [-1, 1]: random knots, cosine-interpolated."""
    step = max(1, int(step_s * SR))
    knots = [rng.uniform(-1.0, 1.0) for _ in range(n // step + 3)]
    out = [0.0] * n
    for i in range(n):
        j, r = divmod(i, step)
        w = rc(r / step)
        out[i] = knots[j] * (1.0 - w) + knots[j + 1] * w
    return out


# ---------------------------------------------------------------- controls

def build_controls(n, rng):
    """Per-sample pitch, amplitude, plunger openness, key and breath puff."""
    f0 = [0.0] * n
    amp = [0.0] * n
    opn = [0.0] * n
    key = [0.0] * n
    puff = [0.0] * n

    drift_p = value_noise(n, rng, 0.070)   # pitch wander (cents)
    drift_a = value_noise(n, rng, 0.090)   # level wander

    last_k = len(NOTES) - 1
    vib_phase = math.pi                    # first vibrato swing goes flat
    starts = [int(round(nt[0] * SR)) for nt in NOTES]
    for k, (_, dur, midi, level) in enumerate(NOTES):
        # contiguous notes: each one ends exactly where the next begins
        i0 = starts[k]
        i1 = n if k == last_k else starts[k + 1]
        if k < last_k:
            dur = (i1 - i0) / SR
        hz = midi_hz(midi)
        b0 = 0.0 if k == 0 else FLOOR
        for i in range(i0, i1):
            t = (i - i0) / SR
            # breath puff on the attack
            p = rc(t / 0.004) * math.exp(-max(0.0, t - 0.004) / 0.025)
            # tiny lip "settle": starts 10 cents flat, settles in ~35 ms
            cents = -10.0 * math.exp(-t / 0.012) + 4.0 * drift_p[i]

            if k < last_k:
                # ----- short "wah"
                A, R, S, TD = 0.035, 0.060, 0.80, 0.10
                if t < A:
                    a = b0 + (1.0 - b0) * rc(t / A)
                else:
                    a = S + (1.0 - S) * math.exp(-(t - A) / TD)
                    if t > dur - R:
                        # release lands exactly on the next note's start level
                        fl_end = FLOOR * NOTES[k + 1][3] / level
                        ar = S + (1.0 - S) * math.exp(-(dur - R - A) / TD)
                        a = ar + (fl_end - ar) * rc((t - (dur - R)) / R)
                TO, TC = 0.085, 0.120          # open time, closing time
                if t < TO:
                    o = rc(t / TO)
                elif t < dur - TC:
                    o = 1.0 - 0.12 * (t - TO) / (dur - TC - TO)
                else:
                    o = 0.88 * (1.0 - rc((t - (dur - TC)) / TC))
            else:
                # ----- long "wahhhh" with the deepening sob
                A, REL, S, TD = 0.040, 0.55, 0.86, 0.12
                if t < A:
                    a = b0 + (1.0 - b0) * rc(t / A)
                else:
                    a = S + (1.0 - S) * math.exp(-(t - A) / TD)
                a *= 1.0 + 0.10 * rc((t - 0.15) / 0.50)        # slight swell
                depth = rc((t - 0.10) / 0.70)                  # vibrato deepens
                rate = 5.0 - 0.9 * min(t / dur, 1.0)           # 5.0 -> 4.1 Hz
                vib_phase += 2.0 * math.pi * rate / SR
                s = math.sin(vib_phase)
                cents += VIB_CENTS * depth * s                 # wide sob
                cents -= 18.0 * rc((t - (dur - 0.30)) / 0.30)  # tired droop
                a *= 1.0 + 0.14 * depth * s                    # level wobble
                if t > dur - REL:
                    a *= 1.0 - rc((t - (dur - REL)) / REL)
                TO = 0.11
                if t < TO:
                    o = rc(t / TO)
                else:
                    o = (0.97 - 0.07 * min((t - TO) / 0.6, 1.0)
                         + 0.18 * depth * s)                   # plunger shake
                o *= 1.0 - rc((t - (dur - 0.60)) / 0.60)       # closes as it dies

            a *= level * (1.0 + 0.03 * drift_a[i])
            f0[i] = hz * 2.0 ** (cents / 1200.0)
            amp[i] = max(0.0, a)
            opn[i] = min(1.1, max(0.0, o))
            key[i] = hz
            puff[i] = p
    return f0, amp, opn, key, puff


# ---------------------------------------------------------------- DSP blocks

def polyblep_saw(freqs):
    """Phase-continuous band-limited (PolyBLEP) sawtooth."""
    out = [0.0] * len(freqs)
    ph = 0.0
    for i, f in enumerate(freqs):
        dt = f / SR
        ph += dt
        if ph >= 1.0:
            ph -= 1.0
        v = 2.0 * ph - 1.0
        if ph < dt:
            x = ph / dt
            v -= x + x - x * x - 1.0
        elif ph > 1.0 - dt:
            x = (ph - 1.0) / dt
            v -= x * x + x + x + 1.0
        out[i] = v
    return out


def svf_lowpass_tv(x, fc, q):
    """Time-varying TPT (trapezoidal) state-variable low-pass, 12 dB/oct."""
    k = 1.0 / q
    ic1 = ic2 = 0.0
    pi_sr = math.pi / SR
    y = [0.0] * len(x)
    for i, v0 in enumerate(x):
        g = math.tan(fc[i] * pi_sr)
        a1 = 1.0 / (1.0 + g * (g + k))
        a2 = g * a1
        a3 = g * a2
        v3 = v0 - ic2
        v1 = a1 * ic1 + a2 * v3
        v2 = ic2 + a2 * ic1 + a3 * v3
        ic1 = 2.0 * v1 - ic1
        ic2 = 2.0 * v2 - ic2
        y[i] = v2
    return y


def svf_peak_tv(x, fc, q, gain):
    """Time-varying TPT SVF peaking filter: x + (gain-1) * normalized band-pass.
    Used as the moving "vowel" formant of the plunger."""
    k = 1.0 / q
    ic1 = ic2 = 0.0
    pi_sr = math.pi / SR
    gk = (gain - 1.0) * k
    y = [0.0] * len(x)
    for i, v0 in enumerate(x):
        g = math.tan(fc[i] * pi_sr)
        a1 = 1.0 / (1.0 + g * (g + k))
        a2 = g * a1
        a3 = g * a2
        v3 = v0 - ic2
        v1 = a1 * ic1 + a2 * v3
        v2 = ic2 + a2 * ic1 + a3 * v3
        ic1 = 2.0 * v1 - ic1
        ic2 = 2.0 * v2 - ic2
        y[i] = v0 + gk * v1
    return y


def rbj(kind, f0, q=0.7071, gain_db=0.0):
    """RBJ audio-EQ-cookbook biquad coefficients (b0, b1, b2, a1, a2)."""
    A = 10.0 ** (gain_db / 40.0)
    w0 = 2.0 * math.pi * f0 / SR
    cw, sw = math.cos(w0), math.sin(w0)
    alpha = sw / (2.0 * q)
    if kind == "lp":
        b0, b1, b2 = (1 - cw) / 2, 1 - cw, (1 - cw) / 2
        a0, a1, a2 = 1 + alpha, -2 * cw, 1 - alpha
    elif kind == "hp":
        b0, b1, b2 = (1 + cw) / 2, -(1 + cw), (1 + cw) / 2
        a0, a1, a2 = 1 + alpha, -2 * cw, 1 - alpha
    elif kind == "bp":
        b0, b1, b2 = alpha, 0.0, -alpha
        a0, a1, a2 = 1 + alpha, -2 * cw, 1 - alpha
    elif kind == "peak":
        b0, b1, b2 = 1 + alpha * A, -2 * cw, 1 - alpha * A
        a0, a1, a2 = 1 + alpha / A, -2 * cw, 1 - alpha / A
    elif kind == "lowshelf":
        sq = 2 * math.sqrt(A) * alpha
        b0 = A * ((A + 1) - (A - 1) * cw + sq)
        b1 = 2 * A * ((A - 1) - (A + 1) * cw)
        b2 = A * ((A + 1) - (A - 1) * cw - sq)
        a0 = (A + 1) + (A - 1) * cw + sq
        a1 = -2 * ((A - 1) + (A + 1) * cw)
        a2 = (A + 1) + (A - 1) * cw - sq
    elif kind == "highshelf":
        sq = 2 * math.sqrt(A) * alpha
        b0 = A * ((A + 1) + (A - 1) * cw + sq)
        b1 = -2 * A * ((A - 1) + (A + 1) * cw)
        b2 = A * ((A + 1) + (A - 1) * cw - sq)
        a0 = (A + 1) - (A - 1) * cw + sq
        a1 = 2 * ((A - 1) - (A + 1) * cw)
        a2 = (A + 1) - (A - 1) * cw - sq
    else:
        raise ValueError(kind)
    return (b0 / a0, b1 / a0, b2 / a0, a1 / a0, a2 / a0)


def biquad(x, c):
    """Static biquad, transposed direct form II."""
    b0, b1, b2, a1, a2 = c
    z1 = z2 = 0.0
    y = [0.0] * len(x)
    for i, v in enumerate(x):
        o = b0 * v + z1
        z1 = b1 * v - a1 * o + z2
        z2 = b2 * v - a2 * o
        y[i] = o
    return y


def saturate(x, drive=1.6, bias=0.12):
    """Asymmetric tanh: soft compression plus a little even-harmonic buzz."""
    pk = max(abs(v) for v in x) or 1.0
    off = math.tanh(drive * bias)
    return [math.tanh(drive * (v / pk + bias)) - off for v in x]


def room(x, wet_ratio=0.22, size=0.74, damp=0.35, predelay_s=0.012):
    """Small mono Freeverb-style room: 8 damped combs into 4 allpasses."""
    n = len(x)
    pre = int(predelay_s * SR)
    src = [0.0] * pre + x[: n - pre]
    acc = [0.0] * n
    for d in (1116, 1188, 1277, 1356, 1422, 1491, 1557, 1617):
        d = int(d * 0.85)
        buf = [0.0] * d
        j = 0
        lp = 0.0
        for i in range(n):
            o = buf[j]
            lp = o * (1.0 - damp) + lp * damp
            buf[j] = src[i] + lp * size
            j += 1
            if j == d:
                j = 0
            acc[i] += o
    for d in (556, 441, 341, 225):
        d = int(d * 0.85)
        buf = [0.0] * d
        j = 0
        for i in range(n):
            bo = buf[j]
            v = acc[i]
            buf[j] = v + bo * 0.5
            acc[i] = bo - v
            j += 1
            if j == d:
                j = 0
    rms_dry = math.sqrt(sum(v * v for v in x) / n) or 1.0
    rms_wet = math.sqrt(sum(v * v for v in acc) / n) or 1.0
    g = wet_ratio * rms_dry / rms_wet
    return [x[i] + g * acc[i] for i in range(n)]


# ---------------------------------------------------------------- render

def render():
    rng = random.Random(SEED)
    n = int(round(TOTAL_S * SR))
    f0, amp, opn, key, puff = build_controls(n, rng)

    # lip buzz + breath through the plunger
    saw = polyblep_saw(f0)
    white = [rng.uniform(-1.0, 1.0) for _ in range(n)]
    src = [saw[i] * amp[i] + white[i] * (0.06 * amp[i] + 0.16 * puff[i])
           for i in range(n)]

    # the "wah": cutoff follows plunger openness, key-tracked, brighter when loud
    ratio = RC_OPEN / RC_CLOSED
    nyq_guard = 0.45 * SR
    fc = [min(nyq_guard, key[i] * RC_CLOSED * ratio ** opn[i] * (0.85 + 0.15 * amp[i]))
          for i in range(n)]
    y = svf_lowpass_tv(src, fc, 0.60)
    y = svf_lowpass_tv(y, fc, WAH_Q)

    # the plunger's moving vowel formant: "oo" (closed) -> "ah" (open)
    fr = FORMANT_OPEN / FORMANT_CLOSED
    ff = [FORMANT_CLOSED * fr ** opn[i] for i in range(n)]
    y = svf_peak_tv(y, ff, FORMANT_Q, FORMANT_GAIN)

    y = saturate(y, drive=SAT_DRIVE, bias=0.10)

    # bell radiation (thins the fundamental so partials 2-5 lead) + body
    y = biquad(y, rbj("hp", BELL_HP_HZ, q=0.7071))
    y = biquad(y, rbj("peak", 600.0, q=1.0, gain_db=2.5))
    y = biquad(y, rbj("lp", 7000.0))

    # airy breath on top, pulsed at the lip rate so it fuses with the tone
    pk = max(abs(v) for v in y) or 1.0
    air = biquad([rng.uniform(-1.0, 1.0) for _ in range(n)], rbj("bp", 3000.0, q=0.7))
    y = [y[i] / pk + air[i] * (0.7 + 0.3 * saw[i]) * (0.012 * amp[i] + 0.05 * puff[i])
         for i in range(n)]

    y = room(y)

    # DC removal: one-pole high-pass (~15 Hz) then subtract any residual mean
    r = 1.0 - 2.0 * math.pi * 15.0 / SR
    prev_x = prev_y = 0.0
    for i in range(n):
        v = y[i]
        prev_y = v - prev_x + r * prev_y
        prev_x = v
        y[i] = prev_y
    mean = sum(y) / n
    y = [v - mean for v in y]

    # click-free edges
    fi = int(FADE_IN_S * SR)
    fo = int(FADE_OUT_S * SR)
    for i in range(fi):
        y[i] *= i / fi
    for i in range(fo):
        y[n - 1 - i] *= rc(i / fo)

    # peak-normalize to -1 dBFS
    pk = max(abs(v) for v in y) or 1.0
    gain = 10.0 ** (PEAK_DBFS / 20.0) / pk
    return [v * gain for v in y]


def write_wav(path, samples):
    pcm = array.array("h", (max(-32767, min(32767, int(round(v * 32767.0))))
                            for v in samples))
    if sys.byteorder == "big":
        pcm.byteswap()
    folder = os.path.dirname(os.path.abspath(path))
    if folder and not os.path.isdir(folder):
        os.makedirs(folder)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def main():
    if len(sys.argv) != 2:
        sys.stderr.write("usage: python3 -I sad-trombone.py <out.wav>\n")
        return 2
    write_wav(sys.argv[1], render())
    return 0


if __name__ == "__main__":
    sys.exit(main())
