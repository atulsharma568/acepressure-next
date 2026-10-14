#!/usr/bin/env python3
"""Air Horn - an original, fully synthesized stadium/meme air horn.

Part of the AcePressure soundboard. Every sample is computed from math:
band-limited oscillators, a seeded pseudo-random generator and hand-written
filters. No samples, no recordings, no network. Standard library only and
deterministic (fixed seed), so it runs the same on any Python 3.9+ (Windows too).

Usage:  python3 -I air-horn.py out.wav

Output: 44100 Hz, mono, 16-bit PCM WAV, peak-normalised to -1 dBFS.

Sound design
  * Rhythm: three blasts, short-short-long (0.22 s, 0.14 s, 0.65 s), 60 ms gaps.
  * Tone: an A-major chord (A4 440 Hz, C#5 554 Hz, E5 ~657 Hz). Every note
    is two slightly detuned polyBLEP sawtooths plus a nasal 30 % pulse; an
    octave-down A3 pulse/saw layer adds body.
  * Pitch: ~1 semitone upward scoop over the first 25 ms of each blast, a short
    chaotic "splat" at the onset, light, slightly irregular vibrato (~5.6 Hz,
    ~8 cents), pressure jitter and diaphragm flutter, a slow sag as the can
    empties and a droop when the valve closes.
  * Each note runs through its own asymmetric "reed" waveshaper (the horn's
    diaphragm), the mix is driven into hard-ish tanh saturation at 2x
    oversampling, then band-passed ~250 Hz - 4 kHz with "honk" and "blare" peaks.
  * An air "pssht" on every onset, breath noise inside the tone and a small
    stadium reverb tail.
"""

import array
import math
import random
import sys
import wave

SR = 44100                    # output sample rate
OS = 2                        # oversampling for oscillators + saturation
FS = SR * OS
SEED = 11                     # fixed seed -> identical output on every run
TOTAL_S = 1.42                # total file length (s)
PEAK_DBFS = -1.0
FADE_IN_S = 0.002
FADE_OUT_S = 0.060
TWO_PI = 2.0 * math.pi
LN2_1200 = math.log(2.0) / 1200.0

# (start s, length s, scoop semitones, release droop semitones, sag semitones)
BLASTS = [
    (0.000, 0.220, 1.00, 0.45, -0.06),
    (0.280, 0.140, 0.90, 0.40, -0.04),
    (0.480, 0.650, 1.10, 0.60, -0.18),
]
ATTACK_S = 0.018              # pressure build-up
SCOOP_S = 0.025               # upward pitch scoop
RELEASE_S = 0.040             # pressure release (pitch droops meanwhile)
GATE_ATTACK_S = 0.003         # post-saturation gate, keeps edges click-free
GATE_RELEASE_S = 0.020

# Chord notes: (frequency Hz, level, voices as (shape, detune cents, gain)).
# Two tightly detuned saws + a nasal 30 % pulse per note: thick but still one
# "trumpet" per note rather than a synth-style supersaw chorus. The E5 sits
# 5 cents flat (like a real, slightly out-of-tune horn) so its partials beat
# against the A4's at 5-16 Hz (rough blare) instead of a slow 1.5 Hz swell.
NOTES = [
    (440.00, 1.00, (("saw", -4.0, 0.40), ("saw", 3.5, 0.35), ("pulse", 0.5, 0.25))),
    (554.37, 0.80, (("saw", -5.0, 0.40), ("saw", 4.0, 0.35), ("pulse", 1.5, 0.25))),
    (657.36, 0.85, (("saw", -3.5, 0.40), ("saw", 5.0, 0.35), ("pulse", -1.0, 0.25))),
]
NOTE_DUTY = 0.30
SUB_FREQ = 220.0              # octave-down layer (pulse + saw)
SUB_LEVEL = 0.55
SUB_DUTY = 0.38

REED_DRIVE = 2.6              # per-note diaphragm waveshaper
REED_BIAS = 0.18              # asymmetry -> even harmonics
BUS_DRIVE = 1.5               # hard-ish saturation of the whole mix
BREATH_LEVEL = 0.45
BURST_LEVEL = 0.30            # onset air "pssht", relative to horn RMS
REVERB_WET = 0.05

# Brassy band-pass ~250 Hz - 4 kHz plus horn-bell resonances:
# (kind, Hz, Q, gain dB); the high-pass is a 4th-order Butterworth.
HORN_HP_HZ = 250.0
HORN_EQ = [
    ("lp", 4200.0, 0.85, 0.0),
    ("peak", 520.0, 1.0, -2.5),       # tame the boxy fundamentals a little
    ("peak", 1080.0, 1.0, 4.0),       # honk
    ("peak", 2800.0, 0.9, 5.5),       # blare
]


# ---------------------------------------------------------------- filters ---

def rbj(kind, fc, fs, q=0.7071067811865476, gain_db=0.0):
    """RBJ audio-EQ-cookbook biquad coefficients (b0, b1, b2, a1, a2), a0 = 1."""
    w0 = TWO_PI * fc / fs
    cw = math.cos(w0)
    sw = math.sin(w0)
    alpha = sw / (2.0 * q)
    a_lin = 10.0 ** (gain_db / 40.0)
    if kind == "lp":
        b0, b1, b2 = (1 - cw) / 2, 1 - cw, (1 - cw) / 2
        a0, a1, a2 = 1 + alpha, -2 * cw, 1 - alpha
    elif kind == "hp":
        b0, b1, b2 = (1 + cw) / 2, -(1 + cw), (1 + cw) / 2
        a0, a1, a2 = 1 + alpha, -2 * cw, 1 - alpha
    elif kind == "bp":        # constant 0 dB peak gain
        b0, b1, b2 = alpha, 0.0, -alpha
        a0, a1, a2 = 1 + alpha, -2 * cw, 1 - alpha
    elif kind == "peak":
        b0, b1, b2 = 1 + alpha * a_lin, -2 * cw, 1 - alpha * a_lin
        a0, a1, a2 = 1 + alpha / a_lin, -2 * cw, 1 - alpha / a_lin
    else:
        raise ValueError(kind)
    return (b0 / a0, b1 / a0, b2 / a0, a1 / a0, a2 / a0)


def biquad(x, coeffs):
    """Transposed direct form II biquad."""
    b0, b1, b2, a1, a2 = coeffs
    y = [0.0] * len(x)
    z1 = z2 = 0.0
    for i, xi in enumerate(x):
        yi = b0 * xi + z1
        z1 = b1 * xi - a1 * yi + z2
        z2 = b2 * xi - a2 * yi
        y[i] = yi
    return y


def cascade(x, stages):
    for c in stages:
        x = biquad(x, c)
    return x


def butterworth(kind, fc, fs, order):
    """Butterworth low/high-pass of even order as a list of biquads."""
    stages = []
    for k in range(order // 2):
        q = 1.0 / (2.0 * math.cos(math.pi * (2 * k + 1) / (2 * order)))
        stages.append(rbj(kind, fc, fs, q))
    return stages


# ------------------------------------------------------------ generators ---

def smooth_noise(rng, n, fs, rate_hz):
    """Random curve in [-1, 1]: a new random value every 1/rate_hz seconds,
    cosine-interpolated in between (smooth, band-limited wobble)."""
    step = fs / rate_hz
    pts = [rng.uniform(-1.0, 1.0) for _ in range(int(n / step) + 3)]
    out = [0.0] * n
    for i in range(n):
        x = i / step
        k = int(x)
        w = 0.5 - 0.5 * math.cos(math.pi * (x - k))
        out[i] = pts[k] + (pts[k + 1] - pts[k]) * w
    return out


def add_saw(out, base_dt, ratio, jitter, jit_amt, gain, phase):
    """Accumulate a polyBLEP (band-limited) sawtooth into `out`.
    base_dt = f0 / FS; ratio[i] = shared pitch ratio; jitter[i] in [-1, 1]."""
    ph = phase
    for i in range(len(out)):
        dt = base_dt * ratio[i] * (1.0 + jit_amt * jitter[i])
        ph += dt
        if ph >= 1.0:
            ph -= 1.0
        if ph < dt:
            x = ph / dt
            blep = x + x - x * x - 1.0
        elif ph > 1.0 - dt:
            x = (ph - 1.0) / dt
            blep = x * x + x + x + 1.0
        else:
            blep = 0.0
        out[i] += gain * (2.0 * ph - 1.0 - blep)


def add_pulse(out, base_dt, ratio, jitter, jit_amt, gain, phase, duty):
    """Accumulate a polyBLEP pulse (difference of two sawtooths)."""
    ph = phase
    for i in range(len(out)):
        dt = base_dt * ratio[i] * (1.0 + jit_amt * jitter[i])
        ph += dt
        if ph >= 1.0:
            ph -= 1.0
        ph2 = ph + duty
        if ph2 >= 1.0:
            ph2 -= 1.0
        v = 2.0 * (ph - ph2)
        if ph < dt:
            x = ph / dt
            v -= x + x - x * x - 1.0
        elif ph > 1.0 - dt:
            x = (ph - 1.0) / dt
            v -= x * x + x + x + 1.0
        if ph2 < dt:
            x = ph2 / dt
            v += x + x - x * x - 1.0
        elif ph2 > 1.0 - dt:
            x = (ph2 - 1.0) / dt
            v += x * x + x + x + 1.0
        out[i] += gain * v


def reed(note, press, lp_a, drive, bias):
    """Pressure-scaled, pressure-brightened, asymmetric tanh waveshaper."""
    tb = math.tanh(drive * bias)
    y = 0.0
    for i in range(len(note)):
        y += lp_a[i] * (note[i] * press[i] - y)        # one-pole low-pass
        note[i] = math.tanh(drive * (y + bias)) - tb
    return note


def render_blast(rng, length_s, scoop_st, droop_st, sag_st):
    """One horn blast at the oversampled rate (before bus saturation)."""
    n = int(round(length_s * FS))
    inv_fs = 1.0 / FS
    vib_rate = 5.6 + rng.uniform(-0.3, 0.3)
    vib_phase = rng.uniform(0.0, TWO_PI)
    vib_depth = 0.08                                    # semitones
    vib_wobble = smooth_noise(rng, n, FS, 3.0)          # irregular vibrato rate
    press_jit = smooth_noise(rng, n, FS, 9.0)
    pitch_jit = smooth_noise(rng, n, FS, 7.0)
    splat = smooth_noise(rng, n, FS, 180.0)
    flutter = smooth_noise(rng, n, FS, 45.0)            # diaphragm flutter

    ratio = [0.0] * n
    press = [0.0] * n
    lp_a = [0.0] * n
    rel0 = length_s - RELEASE_S
    for i in range(n):
        t = i * inv_fs
        st = 0.0
        if t < SCOOP_S:                                 # upward scoop
            st -= scoop_st * (1.0 - t / SCOOP_S) ** 1.6
        st += 0.35 * splat[i] * math.exp(-t / 0.006)    # onset splat
        vib_phase += TWO_PI * vib_rate * (1.0 + 0.12 * vib_wobble[i]) * inv_fs
        vf = (t - 0.020) / 0.080                        # vibrato fades in
        if vf > 0.0:
            st += vib_depth * min(vf, 1.0) * math.sin(vib_phase)
        st += 0.04 * pitch_jit[i] + 0.03 * flutter[i]
        st += sag_st * (t / length_s)
        if t < ATTACK_S:
            a = t / ATTACK_S
            p = 1.0 - (1.0 - a) * (1.0 - a)
        else:
            p = 1.0
        if t > rel0:
            r = min((t - rel0) / RELEASE_S, 1.0)
            st -= droop_st * r * math.sqrt(r)
            p *= 0.5 + 0.5 * math.cos(math.pi * r)
        p *= 1.0 + 0.03 * press_jit[i]
        ratio[i] = 2.0 ** (st / 12.0)
        press[i] = p
        fc = 900.0 + 15000.0 * p * p                    # brighter with pressure
        lp_a[i] = 1.0 - math.exp(-TWO_PI * fc * inv_fs)

    out = [0.0] * n
    for f0, level, voices in NOTES:
        note = [0.0] * n
        for shape, dc, g in voices:
            jit = smooth_noise(rng, n, FS, 11.0)
            base = f0 * 2.0 ** (dc / 1200.0) * inv_fs
            if shape == "saw":
                add_saw(note, base, ratio, jit, 2.5 * LN2_1200, g, rng.random())
            else:
                add_pulse(note, base, ratio, jit, 2.5 * LN2_1200, g, rng.random(),
                          NOTE_DUTY)
        reed(note, press, lp_a, REED_DRIVE, REED_BIAS)
        for i in range(n):
            out[i] += level * note[i]

    sub = [0.0] * n
    add_pulse(sub, SUB_FREQ * inv_fs, ratio, smooth_noise(rng, n, FS, 11.0),
              2.5 * LN2_1200, 0.6, rng.random(), SUB_DUTY)
    add_saw(sub, SUB_FREQ * 2.0 ** (7.0 / 1200.0) * inv_fs, ratio,
            smooth_noise(rng, n, FS, 11.0), 2.5 * LN2_1200, 0.4, rng.random())
    reed(sub, press, lp_a, 2.0, 0.10)

    breath = [rng.uniform(-1.0, 1.0) for _ in range(n)]
    breath = biquad(breath, rbj("bp", 2200.0, FS, 0.6))
    for i in range(n):
        out[i] += SUB_LEVEL * sub[i] + BREATH_LEVEL * press[i] * breath[i]
    return out


# ---------------------------------------------------------------- reverb ---

def reverb(x, wet):
    """Small Schroeder/Freeverb-style room: 4 damped combs + 2 allpasses."""
    n = len(x)
    pre = int(0.010 * SR)
    xin = [0.0] * pre + x[: n - pre]
    acc = [0.0] * n
    for delay, fb in ((1116, 0.77), (1277, 0.76), (1422, 0.76), (1557, 0.75)):
        buf = [0.0] * delay
        idx = 0
        damp = 0.45
        filt = 0.0
        for i in range(n):
            y = buf[idx]
            filt = y * (1.0 - damp) + filt * damp
            buf[idx] = xin[i] + filt * fb
            idx += 1
            if idx == delay:
                idx = 0
            acc[i] += y
    for delay in (556, 341):
        buf = [0.0] * delay
        idx = 0
        for i in range(n):
            b = buf[idx]
            v = acc[i]
            acc[i] = b - v
            buf[idx] = v + b * 0.5
            idx += 1
            if idx == delay:
                idx = 0
    return [xi + wet * 0.25 * ai for xi, ai in zip(x, acc)]


# ------------------------------------------------------------------ main ---

def rms(x):
    return math.sqrt(sum(v * v for v in x) / max(1, len(x)))


def main():
    if len(sys.argv) != 2:
        sys.exit("usage: python3 -I air-horn.py out.wav")
    out_path = sys.argv[1]
    rng = random.Random(SEED)

    n_os = int(round(TOTAL_S * FS))
    bus = [0.0] * n_os
    gate = [0.0] * n_os
    ga = GATE_ATTACK_S * FS
    gr = GATE_RELEASE_S * FS
    for start, length, scoop, droop, sag in BLASTS:
        blast = render_blast(rng, length, scoop, droop, sag)
        s0 = int(round(start * FS))
        m = len(blast)
        for i in range(m):
            bus[s0 + i] += blast[i]
            if i < ga:
                g = 0.5 - 0.5 * math.cos(math.pi * i / ga)
            elif i > m - gr:
                g = 0.5 - 0.5 * math.cos(math.pi * (m - i) / gr)
            else:
                g = 1.0
            gate[s0 + i] = g

    # Hard-ish saturation of the whole mix, gated, at 2x oversampling.
    clipped = 0
    for i in range(n_os):
        z = BUS_DRIVE * bus[i]
        if z > 1.5 or z < -1.5:
            clipped += 1
        bus[i] = math.tanh(z) * gate[i]
    active = sum(1 for g in gate if g > 0.0)

    # Anti-alias low-pass and decimate to 44.1 kHz.
    bus = cascade(bus, butterworth("lp", 18000.0, FS, 8))
    x = bus[::OS]
    n = len(x)

    # Brassy band-pass ~250 Hz - 4 kHz, with honk and blare peaks.
    eq = butterworth("hp", HORN_HP_HZ, SR, 4)
    eq += [rbj(kind, hz, SR, q, gain) for kind, hz, q, gain in HORN_EQ]
    x = cascade(x, eq)
    horn_rms = rms([v for v, g in zip(x, gate[::OS]) if g >= 1.0])

    # Air "pssht" as each valve opens.
    burst_len = int(0.060 * SR)
    for start, _length, _s, _d, _g in BLASTS:
        s0 = int(round(start * SR))
        nz = [rng.uniform(-1.0, 1.0) for _ in range(burst_len)]
        nz = cascade(nz, [rbj("bp", 3400.0, SR, 0.8), rbj("hp", 1500.0, SR)])
        for i in range(burst_len):
            t = i / SR
            env = (1.0 - math.exp(-t / 0.0007)) * math.exp(-t / 0.012)
            if s0 + i < n:
                x[s0 + i] += BURST_LEVEL * horn_rms * 3.0 * env * nz[i]

    x = reverb(x, REVERB_WET)

    # Clean-up: DC, fades, peak normalisation.
    mean = sum(x) / n
    x = [v - mean for v in x]
    fi = int(FADE_IN_S * SR)
    fo = int(FADE_OUT_S * SR)
    for i in range(fi):
        x[i] *= i / fi
    for i in range(fo):
        x[n - 1 - i] *= 0.5 - 0.5 * math.cos(math.pi * i / fo)
    peak = max(abs(v) for v in x)
    scale = 10.0 ** (PEAK_DBFS / 20.0) / peak
    pcm = array.array("h", (int(round(v * scale * 32767.0)) for v in x))
    if sys.byteorder == "big":
        pcm.byteswap()
    with wave.open(out_path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    print("air-horn: %d samples (%.3f s), clip ratio %.2f, horn rms %.3f"
          % (n, n / SR, clipped / max(1, active), horn_rms), file=sys.stderr)


if __name__ == "__main__":
    main()
