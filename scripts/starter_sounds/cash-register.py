#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AcePressure sound effect: "Cash Register" (cha-ching!)

Synthesized entirely from math: no samples, no recordings, no network.
Deterministic (fixed random seed). Python standard library only, 3.9+.

Usage:
    python3 -I cash-register.py out.wav

Output: 44100 Hz, mono, 16-bit PCM WAV, DC-free, peak-normalized to -1 dBFS.

Timeline
  0-100 ms  "cha": lever/drawer ratchet. Short ticks made of band-passed
            noise bursts with tiny metallic resonances, laid over a faint
            sliding scrape.
  ~104 ms   latch "chunk": a heavier click with a short low thump.
  ~117 ms   bell strike 1: a smaller, lower, softer bell.
  ~182 ms   bell strike 2: the main bright "CHING". Inharmonic partials near
            1.9k / 2.6k / 4.1k / 5.3k Hz plus upper shimmer partials. Each
            partial is a slightly split doublet (slow natural beating) with
            its own exponential decay, and higher partials decay faster.
            A short high-passed noise "ch" marks the hammer contact.
  -> rings out for about 1.1 s; 50 ms fade-out; total 1.36 s.
"""
import array
import math
import random
import sys
import wave

SR = 44100
TOTAL_S = 1.36
N = int(round(SR * TOTAL_S))
SEED = 20261011
TARGET_PEAK = 10.0 ** (-1.0 / 20.0)  # -1 dBFS
FADE_IN_S = 0.002
FADE_OUT_S = 0.050
TWO_PI = 2.0 * math.pi


def n_of(ms_val):
    """Milliseconds -> samples."""
    return int(round(ms_val * SR / 1000.0))


# --------------------------------------------------------------------------
# Filters (RBJ audio-EQ cookbook biquads, direct form I)
# --------------------------------------------------------------------------
def rbj(kind, f0, q):
    w0 = TWO_PI * f0 / SR
    cw, sw = math.cos(w0), math.sin(w0)
    alpha = sw / (2.0 * q)
    if kind == "bp":  # constant 0 dB peak gain
        b0, b1, b2 = alpha, 0.0, -alpha
    elif kind == "lp":
        b0 = b2 = (1.0 - cw) / 2.0
        b1 = 1.0 - cw
    elif kind == "hp":
        b0 = b2 = (1.0 + cw) / 2.0
        b1 = -(1.0 + cw)
    else:
        raise ValueError(kind)
    a0, a1, a2 = 1.0 + alpha, -2.0 * cw, 1.0 - alpha
    return (b0 / a0, b1 / a0, b2 / a0, a1 / a0, a2 / a0)


def biquad(x, c):
    b0, b1, b2, a1, a2 = c
    y = [0.0] * len(x)
    x1 = x2 = y1 = y2 = 0.0
    for i, xi in enumerate(x):
        yi = b0 * xi + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
        x2, x1, y2, y1 = x1, xi, y1, yi
        y[i] = yi
    return y


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------
def peak(x):
    return max(abs(v) for v in x) if x else 0.0


def normalized(x, target=1.0):
    p = peak(x)
    if p <= 0.0:
        return list(x)
    g = target / p
    return [v * g for v in x]


def mix_into(buf, start, sig, gain=1.0):
    k0 = max(0, -start)
    k1 = min(len(sig), len(buf) - start)
    for k in range(k0, k1):
        buf[start + k] += gain * sig[k]


def add_damped_sine(buf, start, freq, amp, tau, phase=0.0, attack=0):
    """Add amp*exp(-t/tau)*sin(2*pi*f*t + phase) to buf from index `start`.

    Uses the exact two-pole recursion y[n] = 2r*cos(w)*y[n-1] - r^2*y[n-2],
    which is fast in pure Python. An optional raised-cosine attack of
    `attack` samples softens the onset.
    """
    if start >= len(buf) or amp == 0.0:
        return
    w = TWO_PI * freq / SR
    r = math.exp(-1.0 / (tau * SR))
    c1, c2 = 2.0 * r * math.cos(w), -r * r
    p1 = amp * math.sin(phase - w) / r              # y[-1]
    p2 = amp * math.sin(phase - 2.0 * w) / (r * r)  # y[-2]
    # stop once the envelope is ~140 dB down
    count = min(len(buf) - start, int(tau * SR * math.log(1e7)) + 1)
    for k in range(count):
        v = c1 * p1 + c2 * p2
        p2, p1 = p1, v
        if k < attack:
            v *= 0.5 - 0.5 * math.cos(math.pi * k / attack)
        buf[start + k] += v


def noise_burst(rng, length, attack, tau, taper_frac=0.3):
    """White noise with a short attack, exponential decay (time constant
    `tau` samples) and a half-cosine taper to exactly zero at the end."""
    out = [0.0] * length
    t0 = int(length * (1.0 - taper_frac))
    for k in range(length):
        env = math.exp(-k / tau)
        if k < attack:
            env *= k / attack
        if k >= t0:
            env *= 0.5 + 0.5 * math.cos(math.pi * (k - t0) / max(1, length - t0))
        out[k] = env * (2.0 * rng.random() - 1.0)
    return out


# --------------------------------------------------------------------------
# "Cha": mechanical rattle
# --------------------------------------------------------------------------
def make_tick(rng, length_ms, fc, q, metal, body):
    """One ratchet/drawer tick: a 1-4 ms band-passed noise burst plus tiny
    metallic (and optionally wooden/plastic body) resonances."""
    L = max(8, n_of(length_ms))
    n = L + n_of(16.0)  # room for filter and resonance ring
    x = noise_burst(rng, L, attack=max(1, n_of(0.10)), tau=L / 2.5)
    x += [0.0] * (n - L)
    y = biquad(x, rbj("bp", fc, q))
    y = biquad(y, rbj("bp", fc, q * 0.7))  # second stage: steeper skirts
    y = normalized(y, 1.0)
    for f, a, t_ms in metal:
        add_damped_sine(y, 0, f, a, t_ms / 1000.0, rng.uniform(0.0, TWO_PI),
                        attack=n_of(0.08))
    for f, a, t_ms in body:
        add_damped_sine(y, 0, f, a, t_ms / 1000.0, rng.uniform(0.0, TWO_PI),
                        attack=n_of(0.30))
    return y


def make_chunk(rng):
    """Latch release at the end of the lever travel: heavier click, two
    short metallic rings and a small descending low thump."""
    L = n_of(4.5)
    n = n_of(70.0)
    x = noise_burst(rng, L, attack=n_of(0.15), tau=L / 2.2)
    x += [0.0] * (n - L)
    y = biquad(x, rbj("bp", 1750.0, 1.1))
    y = biquad(y, rbj("bp", 2100.0, 0.9))
    y = normalized(y, 0.75)
    add_damped_sine(y, 0, 2950.0, 0.30, 0.0035, rng.uniform(0, TWO_PI), n_of(0.1))
    add_damped_sine(y, 0, 4630.0, 0.22, 0.0025, rng.uniform(0, TWO_PI), n_of(0.1))
    # descending thump 210 -> 125 Hz
    ph = 0.0
    att = n_of(0.5)
    for k in range(n):
        t = k / SR
        f = 125.0 + 85.0 * math.exp(-t / 0.008)
        ph += TWO_PI * f / SR
        env = 0.55 * math.exp(-t / 0.010)
        if k < att:
            env *= 0.5 - 0.5 * math.cos(math.pi * k / att)
        y[k] += env * math.sin(ph)
    return y


def build_rattle(rng):
    buf = [0.0] * N

    # faint sliding scrape under the ticks (drawer runner / lever pivot)
    L = n_of(110.0)
    bed = [0.0] * L
    for k in range(L):
        u = k / L
        env = (0.4 + 0.6 * u) * math.sin(math.pi * u) ** 0.7
        bed[k] = env * (2.0 * rng.random() - 1.0)
    bed = biquad(bed, rbj("bp", 1400.0, 0.8))
    bed = biquad(bed, rbj("lp", 5000.0, 0.707))
    mix_into(buf, 0, normalized(bed, 0.07))

    # ratchet ticks: the lever speeds up a little as it travels
    tick_ms = [1.5, 20.5, 38.0, 53.5, 67.5, 80.5, 92.5]
    count = len(tick_ms)
    for i, t in enumerate(tick_ms):
        start = max(0, n_of(t + (rng.uniform(-0.5, 0.5) if i else 0.0)))
        hi = (i % 2 == 0)  # alternate pawl / tooth contacts
        fc = rng.uniform(3400.0, 4800.0) if hi else rng.uniform(1900.0, 2800.0)
        q = rng.uniform(1.2, 2.2)
        length_ms = rng.uniform(1.5, 3.8)
        metal = [(fc * rng.uniform(1.2, 1.7), rng.uniform(0.30, 0.45),
                  rng.uniform(1.0, 2.2))]
        body = [(rng.uniform(800.0, 1400.0), rng.uniform(0.18, 0.30),
                 rng.uniform(2.0, 3.5))]
        amp = 0.50 + 0.25 * i / (count - 1) + rng.uniform(-0.05, 0.05)
        mix_into(buf, start, make_tick(rng, length_ms, fc, q, metal, body), amp)
        # pawl bounce: a softer, shorter echo of the same contact 2.5-4 ms later
        b_start = start + n_of(rng.uniform(2.5, 4.0))
        bounce = make_tick(rng, 1.2, fc * rng.uniform(0.95, 1.1), q * 1.3,
                           [(metal[0][0], 0.3, 0.8)], [])
        mix_into(buf, b_start, bounce, amp * rng.uniform(0.32, 0.45))

    # latch "chunk"
    mix_into(buf, n_of(104.0), make_chunk(rng), 1.0)

    # keep the mechanism a little darker than the bell so the "CHING" is the
    # brightest moment (gentle 2nd-order low-pass on the rattle bus)
    return biquad(buf, rbj("lp", 9500.0, 0.707))


# --------------------------------------------------------------------------
# "Ching": bell
# --------------------------------------------------------------------------
MAIN_BELL = [
    # freq (Hz), relative amplitude, decay time constant tau (s),
    # doublet split (Hz) -> slow beat on the low partials, shimmer up high
    (1900.0, 1.00, 0.240, 1.5),
    (2600.0, 0.70, 0.185, -2.2),
    (4100.0, 0.52, 0.115, 3.4),
    (5300.0, 0.40, 0.080, -4.8),
    (6870.0, 0.27, 0.048, 6.5),
    (7640.0, 0.12, 0.036, -7.0),
    (8430.0, 0.18, 0.030, -8.0),
    (9310.0, 0.09, 0.024, 9.0),
    (10170.0, 0.08, 0.019, 10.0),
    (11050.0, 0.06, 0.016, -11.0),
    (12080.0, 0.05, 0.013, -12.0),
    (13130.0, 0.04, 0.010, 13.0),
]
DOUBLET_AMP = 0.22   # weaker twin mode
DOUBLET_TAU = 1.08   # rings slightly longer than its partner


def add_bell(buf, start, rng, fscale, amp, tau_scale, tilt):
    """Strike the bell: every partial is a doublet (two nearly coincident
    modes, as in any real, slightly asymmetric bell) for natural beating."""
    f_ref = MAIN_BELL[0][0]
    att = n_of(0.35)
    for f, a, tau, split in MAIN_BELL:
        a_eff = amp * a * (f / f_ref) ** (-tilt)
        f_eff = f * fscale
        tau_eff = tau * tau_scale
        add_damped_sine(buf, start, f_eff, a_eff, tau_eff,
                        rng.uniform(0.0, TWO_PI), att)
        add_damped_sine(buf, start, f_eff + split * fscale, a_eff * DOUBLET_AMP,
                        tau_eff * DOUBLET_TAU, rng.uniform(0.0, TWO_PI), att)


def make_strike_noise(rng, tau_ms):
    """Hammer contact "ch": a very short click plus a fast-decaying
    high-passed noise sizzle."""
    L = n_of(tau_ms * 7.0)
    a_n = max(1, n_of(0.15))
    t_fast = n_of(0.6)
    t_slow = n_of(tau_ms)
    x = [0.0] * (L + n_of(5.0))
    for k in range(L):
        env = 0.55 * math.exp(-k / t_fast) + 0.45 * math.exp(-k / t_slow)
        if k < a_n:
            env *= k / a_n
        if k > L * 0.8:
            env *= 0.5 + 0.5 * math.cos(math.pi * (k - L * 0.8) / (L * 0.2))
        x[k] = env * (2.0 * rng.random() - 1.0)
    y = biquad(x, rbj("hp", 4200.0, 0.707))
    y = biquad(y, rbj("hp", 4200.0, 0.707))
    y = biquad(y, rbj("lp", 14000.0, 0.707))
    return normalized(y, 1.0)


def build_bell(rng):
    buf = [0.0] * N
    s1 = n_of(117.0)
    s2 = n_of(182.0)
    # strike 1: smaller, lower (about a minor third down), softer, shorter
    add_bell(buf, s1, rng, fscale=1.0 / 1.19, amp=0.46, tau_scale=0.55, tilt=0.35)
    # strike 2: the main bright CHING
    add_bell(buf, s2, rng, fscale=1.0, amp=1.0, tau_scale=1.0, tilt=0.0)
    p = peak(buf)
    mix_into(buf, s1, make_strike_noise(rng, 6.0), 0.20 * p)
    mix_into(buf, s2, make_strike_noise(rng, 10.0), 0.34 * p)
    return buf


# --------------------------------------------------------------------------
# Tiny room (Schroeder: damped combs -> allpasses) for a sense of space
# --------------------------------------------------------------------------
def small_room(x, t60=0.38, damp=0.35):
    n = len(x)
    out = [0.0] * n
    for d in (613, 659, 701, 743):
        g = 10.0 ** (-3.0 * d / (t60 * SR))
        line = [0.0] * d
        idx = 0
        lp = 0.0
        for i in range(n):
            yd = line[idx]
            lp = yd * (1.0 - damp) + lp * damp
            line[idx] = x[i] + g * lp
            idx += 1
            if idx == d:
                idx = 0
            out[i] += 0.25 * yd
    for d, g in ((347, 0.5), (113, 0.5)):
        line = [0.0] * d
        idx = 0
        for i in range(n):
            vd = line[idx]
            v = out[i] + g * vd
            out[i] = -g * v + vd
            line[idx] = v
            idx += 1
            if idx == d:
                idx = 0
    return out


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def render():
    rng = random.Random(SEED)
    rattle = build_rattle(rng)
    bell = build_bell(rng)

    # balance: rattle peaks a bit below the bell peak (short clicks read
    # much quieter than a ringing bell at the same peak level)
    rg = 0.80 * peak(bell) / peak(rattle)
    dry = [b + rg * r for b, r in zip(bell, rattle)]

    wet = small_room(dry)
    pre = n_of(5.0)
    wet_gain = 0.10
    mix = dry[:]
    for i in range(pre, N):
        mix[i] += wet_gain * wet[i - pre]

    # DC / subsonic removal: 2nd-order Butterworth high-pass at 30 Hz,
    # then subtract any residual mean
    mix = biquad(mix, rbj("hp", 30.0, 0.7071))
    mean = sum(mix) / N
    mix = [v - mean for v in mix]

    # fades: 2 ms raised-cosine in, 50 ms raised-cosine out
    fi = n_of(FADE_IN_S * 1000.0)
    for k in range(fi):
        mix[k] *= 0.5 - 0.5 * math.cos(math.pi * k / fi)
    fo = n_of(FADE_OUT_S * 1000.0)
    for k in range(fo):
        mix[N - fo + k] *= 0.5 + 0.5 * math.cos(math.pi * (k + 1) / fo)

    return normalized(mix, TARGET_PEAK)


def write_wav(path, x):
    pcm = array.array("h", (max(-32768, min(32767, int(round(v * 32767.0))))
                            for v in x))
    if sys.byteorder == "big":
        pcm.byteswap()
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def main(argv):
    if len(argv) != 2:
        sys.stderr.write("usage: python3 -I cash-register.py <out.wav>\n")
        return 2
    write_wav(argv[1], render())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
