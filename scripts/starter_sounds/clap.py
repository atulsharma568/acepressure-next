#!/usr/bin/env python3
"""Clap - an original, fully synthesized burst of enthusiastic audience applause.

Part of the AcePressure soundboard. Everything is computed from math (no samples,
no recordings, no network). Standard library only, deterministic (fixed seed).

How it works
  * A virtual audience of 170 people is simulated. Each person has a distance
    from the microphone, a hand-cavity resonance (1-2.4 kHz), a clapping rate
    (about 4-6 claps per second), timing jitter and a start and stop time.
  * Every single clap is a 6-20 ms burst of noise: fast attack, a short hold
    while the palms meet, then an exponential decay. It goes through an RBJ
    band-pass resonator and is mixed with a faster-decaying broadband "crack" and
    a little low "body". Level, centre frequency, Q, length and crack amount
    change slightly from clap to clap.
  * Distance sets each person's direct level and brightness. Every clap also feeds
    a small Schroeder/Freeverb-style room (early reflections, damped combs and
    allpasses), so far-away hands sound diffuse and near hands sound dry.
  * People join quickly at the start, clap steadily, then slow down, get softer
    and drop out one by one; a few closer people keep going a little longer.
  * Two people right next to the mic add a few sharper, brighter claps on top.
    The crowd bed is gently peak-limited (at most 4 dB) so it is not drowned out
    by them, and their claps are placed 3.5 dB above the bed's peaks.

Usage:  python3 -I clap.py out.wav

Output: 44100 Hz, mono, 16-bit PCM WAV, peak-normalised to -1 dBFS.
"""

import array
import math
import random
import sys
import wave

SR = 44100
DUR = 2.75                    # seconds, total file length
N = int(round(SR * DUR))
SEED = 0xC1A9                 # fixed seed -> identical output on every run
PEAK_DBFS = -1.0
FADE_IN_S = 0.002
FADE_OUT_S = 0.045
TWO_PI = 2.0 * math.pi
LN1000 = math.log(1000.0)     # decay to -60 dB

# Audience layout
N_CROWD = 170
R_MIN, R_MAX = 3.5, 12.0      # metres from the mic (uniform over floor area)
CROWD_GAIN = 0.80             # nearest crowd member, relative to the near pair
CROWD_CAP = 0.9               # loudest single crowd clap, relative to CROWD_GAIN
WIND_DOWN_S = 0.40            # people slow down and soften before stopping
WET_DB = -5.0                 # room level relative to the crowd's direct sound
BED_LIMIT_DB = 4.0            # crowd bed: shave at most this off its loudest peaks
NEAR_OVER_DB = 3.5            # near pair's loudest clap vs the crowd bed's peaks


# ---------------------------------------------------------------- filters ---

def rbj(kind, fc, q=0.7071067811865476, gain_db=0.0):
    """RBJ audio-EQ-cookbook biquad coefficients (b0, b1, b2, a1, a2), a0 = 1."""
    w0 = TWO_PI * fc / SR
    cw = math.cos(w0)
    sw = math.sin(w0)
    alpha = sw / (2.0 * q)
    if kind == "lp":
        b0, b1, b2 = (1 - cw) / 2, 1 - cw, (1 - cw) / 2
        a0, a1, a2 = 1 + alpha, -2 * cw, 1 - alpha
    elif kind == "hp":
        b0, b1, b2 = (1 + cw) / 2, -(1 + cw), (1 + cw) / 2
        a0, a1, a2 = 1 + alpha, -2 * cw, 1 - alpha
    elif kind == "bp":  # constant 0 dB peak gain
        b0, b1, b2 = alpha, 0.0, -alpha
        a0, a1, a2 = 1 + alpha, -2 * cw, 1 - alpha
    elif kind == "hs":  # high shelf, slope S = 1
        a = 10.0 ** (gain_db / 40.0)
        al = sw / math.sqrt(2.0)
        sa = 2.0 * math.sqrt(a) * al
        b0 = a * ((a + 1) + (a - 1) * cw + sa)
        b1 = -2 * a * ((a - 1) + (a + 1) * cw)
        b2 = a * ((a + 1) + (a - 1) * cw - sa)
        a0 = (a + 1) - (a - 1) * cw + sa
        a1 = 2 * ((a - 1) - (a + 1) * cw)
        a2 = (a + 1) - (a - 1) * cw - sa
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


# ---------------------------------------------------------------- random ---

class Rng:
    """Seeded randomness built only on random.random() (Mersenne Twister), whose
    output is identical on every Python 3 version and platform."""

    def __init__(self, seed):
        self.random = random.Random(seed).random
        self._spare = None

    def uniform(self, a, b):
        return a + (b - a) * self.random()

    def gauss(self):
        """Standard normal deviate (Box-Muller)."""
        if self._spare is not None:
            z, self._spare = self._spare, None
            return z
        r = math.sqrt(-2.0 * math.log(1.0 - self.random()))
        a = TWO_PI * self.random()
        self._spare = r * math.sin(a)
        return r * math.cos(a)

    def sample(self, items, k):
        pool = list(items)
        return [pool.pop(int(self.random() * len(pool))) for _ in range(k)]


# ------------------------------------------------------------ single clap ---

def clap_burst(rnd, f0, q, dur_ms, crack, crack_lp_hz, attack_ms, hold_ms,
               body=0.0, body_hz=400.0):
    """One hand clap, peak-normalised to 1.0.

    Noise burst (linear attack, short full-level hold while the palms meet,
    then an exponential decay reaching -60 dB dur_ms after the hold)
    -> band-pass resonator at f0, plus a broadband crack (600 Hz high-pass,
    crack_lp_hz low-pass) that decays about twice as fast, plus an optional
    low "body" resonance (palm thump heard on claps close to the mic).
    """
    tau = dur_ms * 0.001 / LN1000
    n_atk = max(2, int(attack_ms * 0.001 * SR + 0.5))
    n_hold = n_atk + int(hold_ms * 0.001 * SR + 0.5)
    ring = q / (math.pi * f0)                      # resonator time constant
    n = n_hold + int((dur_ms * 0.001 + 6.0 * ring) * SR) + 8
    b0, _, b2, a1, a2 = rbj("bp", f0, q)
    c0, _, c2, d1, d2 = rbj("bp", body_hz, 1.2)
    kd = math.exp(-1.0 / (tau * SR))
    kc = math.exp(-1.0 / (0.45 * tau * SR))
    hp_p = math.exp(-TWO_PI * 600.0 / SR)          # one-pole high-pass pole
    lp_g = 1.0 - math.exp(-TWO_PI * crack_lp_hz / SR)
    z1 = z2 = s1 = s2 = 0.0
    hp_x = hp_y = lp = 0.0
    e = ec = 1.0
    out = [0.0] * n
    for i in range(n):
        if i < n_atk:
            env = envc = (i + 1.0) / n_atk
        elif i < n_hold:
            env = envc = 1.0
        else:
            e *= kd
            ec *= kc
            env, envc = e, ec
        w = rnd() * 2.0 - 1.0
        x = w * env
        y = b0 * x + z1                            # band-pass (b1 = 0)
        z1 = -a1 * y + z2
        z2 = b2 * x - a2 * y
        c = w * envc * crack                       # crack: HP 600 Hz, LP
        hp_y = hp_p * (hp_y + c - hp_x)
        hp_x = c
        lp += lp_g * (hp_y - lp)
        bo = c0 * x + s1                           # body band-pass
        s1 = -d1 * bo + s2
        s2 = c2 * x - d2 * bo
        out[i] = y + lp + body * bo
    taper = min(n // 4, 44)                        # 1 ms end taper
    for i in range(taper):
        out[n - 1 - i] *= i / taper
    pk = max(max(out), -min(out))
    if pk > 0.0:
        inv = 1.0 / pk
        out = [v * inv for v in out]
    return out


def punch(burst):
    """Energy in the first 5 ms of a (peak-normalised) clap."""
    return sum(v * v for v in burst[:int(0.005 * SR)])


def add_into(buf, start, src, gain):
    end = min(len(buf), start + len(src))
    if end <= start:
        return
    buf[start:end] = [a + b * gain for a, b in zip(buf[start:end], src)]


# --------------------------------------------------------------- audience ---

def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def excitement(t):
    """Slow swell of the whole crowd: a little louder in the middle."""
    return 1.0 + 0.15 * math.exp(-((t - 0.80) / 0.40) ** 2)


def make_people(rng):
    people = []
    for _ in range(N_CROWD):
        u = rng.random()
        r = math.sqrt(R_MIN ** 2 + (R_MAX ** 2 - R_MIN ** 2) * u)
        prox = R_MIN / r                       # 1.0 (nearest) .. ~0.3 (back)
        people.append({
            "gain": CROWD_GAIN * prox,             # direct sound ~ 1/r
            "f0": math.exp(rng.uniform(math.log(1000.0), math.log(2400.0))),
            "q": rng.uniform(1.8, 4.2),
            "dur": rng.uniform(8.0, 18.0),
            "crack": rng.uniform(0.18, 0.40),
            "crack_lp": 4800.0 + 4800.0 * prox,
            "attack": rng.uniform(0.25, 0.70),
            "hold": rng.uniform(0.3, 1.2),
            "rate": rng.uniform(3.8, 5.8),
            "jitter": rng.uniform(0.025, 0.06),
            # triangular spread: the crowd swells in over ~0.3 s
            "onset": 0.010 + 0.16 * (rng.random() + rng.random()),
            "stop": clamp(1.88 + 0.26 * rng.gauss(), 1.32, 2.36),
            "dmin": 6.0, "dmax": 18.0, "wd_depth": 0.55,
            "body": rng.uniform(0.10, 0.30),
            "body_hz": rng.uniform(320.0, 650.0),
            "near": False, "var": 0.20,
            "pick": 1,
        })
    # a few eager people start straight away
    for p in rng.sample(people, 8):
        p["onset"] = rng.uniform(0.004, 0.060)
    # a few fairly close people keep going a little longer than the rest
    close = [p for p in people if p["gain"] > 0.45 * CROWD_GAIN]
    for p in rng.sample(close, 4):
        p["stop"] = rng.uniform(2.12, 2.36)
        p["wd_depth"] = 0.30
    # two people right next to the mic: sharper, brighter claps on top
    people.append({"gain": 1.00, "f0": 2300.0, "q": 1.6, "dur": 10.0,
                   "crack": 0.75, "crack_lp": 12500.0, "attack": 0.15,
                   "hold": 1.8, "rate": 4.60, "jitter": 0.03, "onset": 0.002,
                   "stop": 0.70, "dmin": 8.5, "dmax": 12.0, "wd_depth": 0.0,
                   "body": 0.45, "body_hz": 420.0, "near": True, "var": 0.08,
                   "pick": 8})
    people.append({"gain": 0.95, "f0": 1850.0, "q": 2.0, "dur": 10.5,
                   "crack": 0.65, "crack_lp": 11500.0, "attack": 0.15,
                   "hold": 2.0, "rate": 5.00, "jitter": 0.035, "onset": 0.76,
                   "stop": 1.70, "dmin": 8.5, "dmax": 12.5, "wd_depth": 0.3,
                   "body": 0.40, "body_hz": 380.0, "near": True, "var": 0.08,
                   "pick": 8})
    return people


def render_audience(rng):
    crowd = [0.0] * N
    near = [0.0] * N
    send = [0.0] * N
    rnd = rng.random
    gauss = rng.gauss
    n_claps = 0
    for p in make_people(rng):
        dry = near if p["near"] else crowd
        t = p["onset"]
        stop = p["stop"]
        while t < stop:
            wd = clamp((t - (stop - WIND_DOWN_S)) / WIND_DOWN_S, 0.0, 1.0)
            swell = 1.0 if p["near"] else excitement(t)
            strength = (math.exp(p["var"] * gauss()) * swell
                        * (1.0 - p["wd_depth"] * wd))
            kw = dict(
                f0=p["f0"] * math.exp(0.07 * gauss()),
                q=p["q"] * math.exp(0.12 * gauss()),
                dur_ms=clamp(p["dur"] * math.exp(0.15 * gauss()),
                             p["dmin"], p["dmax"]),
                crack=p["crack"] * math.exp(0.20 * gauss()),
                crack_lp_hz=p["crack_lp"],
                attack_ms=p["attack"],
                hold_ms=p["hold"] * math.exp(0.15 * gauss()),
                body=p["body"],
                body_hz=p["body_hz"],
            )
            burst = clap_burst(rnd, **kw)
            # near claps: keep the noise take with the most energy per peak,
            # so they read as solid claps without spiking the peak level
            for _ in range(p["pick"] - 1):
                alt = clap_burst(rnd, **kw)
                if punch(alt) > punch(burst):
                    burst = alt
            start = int(t * SR)
            amp = p["gain"] * strength
            if not p["near"]:
                amp = min(amp, CROWD_CAP * CROWD_GAIN)
            add_into(dry, start, burst, amp)
            add_into(send, start, burst, strength)
            n_claps += 1
            period = (1.0 / p["rate"]) * (1.0 + p["jitter"] * gauss())
            t += period * (1.0 + 0.35 * wd)
    return crowd, near, send, n_claps


# ------------------------------------------------------------------- room ---

def comb(x, delay, feedback, damp):
    buf = [0.0] * delay
    out = [0.0] * len(x)
    idx = 0
    store = 0.0
    d2 = 1.0 - damp
    for i, xi in enumerate(x):
        o = buf[idx]
        store = o * d2 + store * damp
        buf[idx] = xi + store * feedback
        idx += 1
        if idx == delay:
            idx = 0
        out[i] = o
    return out


def allpass(x, delay, feedback=0.5):
    buf = [0.0] * delay
    out = [0.0] * len(x)
    idx = 0
    for i, xi in enumerate(x):
        b = buf[idx]
        out[i] = b - xi
        buf[idx] = xi + b * feedback
        idx += 1
        if idx == delay:
            idx = 0
    return out


def room(send):
    n = len(send)
    # early reflections (pre-delayed taps)
    taps = ((0.0071, 0.55), (0.0113, -0.45), (0.0157, 0.40),
            (0.0199, -0.33), (0.0243, 0.28), (0.0291, -0.22))
    er = [0.0] * n
    for dt, g in taps:
        d = int(dt * SR)
        er[d:] = [a + b * g for a, b in zip(er[d:], send[:n - d])]
    pre = int(0.012 * SR)
    rev_in = [0.0] * pre + send[:n - pre]
    rev_in = [a + 0.5 * b for a, b in zip(rev_in, er)]
    combs = (1116, 1188, 1277, 1356, 1422, 1491, 1557, 1617)
    tail = [0.0] * n
    for d in combs:
        c = comb(rev_in, d, 0.80, 0.35)
        tail = [a + b for a, b in zip(tail, c)]
    for d in (556, 441, 341, 225):
        tail = allpass(tail, d)
    return [0.6 * a + 0.125 * b for a, b in zip(er, tail)]


# --------------------------------------------------------------- limiter ---

def limiter(x, ceiling, look_ms=1.5, release_ms=60.0):
    """Look-ahead peak limiter: gain ramps down over look_ms before any sample
    above the ceiling, then recovers exponentially. Output never exceeds it."""
    n = len(x)
    look = max(1, int(look_ms * 0.001 * SR))
    env = [1.0] * n
    for i, v in enumerate(x):
        a = abs(v)
        if a > ceiling:
            r = ceiling / a
            for j in range(max(0, i - look), i + 1):
                gj = 1.0 - (1.0 - r) * (j - (i - look)) / look
                if gj < env[j]:
                    env[j] = gj
    rel = math.exp(-1.0 / (release_ms * 0.001 * SR))
    g = 1.0
    out = [0.0] * n
    for i, v in enumerate(x):
        t = env[i]
        g = t if t < g else t + (g - t) * rel
        out[i] = v * g
    return out


# ------------------------------------------------------------------- main ---

def rms(x):
    return math.sqrt(sum(v * v for v in x) / max(1, len(x)))


def peak(x):
    return max(max(x), -min(x))


def tone(x):
    """Final EQ: no rumble, a touch less fizz, 4th-order low-pass at 14 kHz."""
    x = biquad(x, rbj("hp", 70.0))
    x = biquad(x, rbj("hs", 6500.0, gain_db=-3.0))
    x = biquad(x, rbj("lp", 14000.0, 0.5412))
    return biquad(x, rbj("lp", 14000.0, 1.3066))


def render():
    rng = Rng(SEED)
    crowd, near, send, n_claps = render_audience(rng)
    wet = room(send)

    # crowd bed = direct crowd + room, gently limited so it sits up front
    g = 10.0 ** (WET_DB / 20.0) * rms(crowd) / max(1e-12, rms(wet))
    bed = [a + g * b for a, b in zip(crowd, wet)]
    ceiling = peak(bed) * 10.0 ** (-BED_LIMIT_DB / 20.0)
    bed = limiter(bed, ceiling, release_ms=40.0)

    # the two people next to the mic stay clean and land on top of the bed
    k = ceiling * 10.0 ** (NEAR_OVER_DB / 20.0) / peak(near)
    near = tone([k * v for v in near])
    bed = tone(bed)
    x = [a + b for a, b in zip(bed, near)]
    # where a near clap happens to line up with a loud crowd clap, shave the
    # sum back to the near clap's own peak so it, not luck, sets the level
    x = limiter(x, peak(near) * 10.0 ** (0.3 / 20.0), look_ms=1.0,
                release_ms=15.0)

    mean = sum(x) / len(x)                          # DC removal
    x = [v - mean for v in x]

    n_in = int(FADE_IN_S * SR)
    for i in range(n_in):
        x[i] *= 0.5 - 0.5 * math.cos(math.pi * i / n_in)
    n_out = int(FADE_OUT_S * SR)
    for i in range(n_out):
        x[N - 1 - i] *= 0.5 - 0.5 * math.cos(math.pi * i / n_out)

    pk = max(max(x), -min(x))
    scale = (10.0 ** (PEAK_DBFS / 20.0)) / pk
    return [v * scale for v in x], n_claps


def write_wav(path, x):
    pcm = array.array("h", (int(round(clamp(v, -1.0, 1.0) * 32767.0)) for v in x))
    if sys.byteorder == "big":
        pcm.byteswap()
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def main():
    if len(sys.argv) != 2:
        sys.stderr.write("usage: python3 -I clap.py out.wav\n")
        sys.exit(2)
    x, n_claps = render()
    write_wav(sys.argv[1], x)
    print("wrote %s (%d claps, %.2f s)" % (sys.argv[1], n_claps, len(x) / SR))


if __name__ == "__main__":
    main()
