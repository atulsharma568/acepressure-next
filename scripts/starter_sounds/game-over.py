#!/usr/bin/env python3
"""AcePressure SFX: "Game Over" (slug: game-over).

An original 8-bit chiptune "game over" sting, synthesized from math only.

  Lead   NES-style pulse channel, switching between 25% and 50% duty
         (25% on the quick notes, 50% on the long A4; the held note starts
         at 25% and "closes" to 50%).
  Bass   NES-style 4-bit stepped triangle, doubling the lead an octave below.
  Phrase original, D minor:  D5 Bb4 A4 | F4 E4 | D4~
         rhythm short-short-long | short-short | held.  The held D4 sinks
         slowly (ease-in bend, about -3.5 semitones by the very end) with a
         delayed vibrato that widens and slows while the note fades out; a
         gentle low-pass glide darkens its tail so it dies naturally.

Both oscillators are band-limited wavetables built from exact Fourier
series, so nothing aliases even during the pitch bend ("crisp, not harsh").

Standard library only, fully deterministic (no randomness at all).
Usage: python3 -I game-over.py out.wav
"""

import math
import sys
import wave
from array import array

SR = 44100
TN = 4096                 # wavetable length (power of two)
TMASK = TN - 1
F_HI = 14000.0            # no partial is ever placed at or above this
F_TAPER = 9000.0          # partials fade out smoothly from here up to F_HI

COS = [math.cos(2.0 * math.pi * i / TN) for i in range(TN)]
SIN = [math.sin(2.0 * math.pi * i / TN) for i in range(TN)]


def hz(midi):
    return 440.0 * 2.0 ** ((midi - 69) / 12.0)


def smooth(x):
    """Raised-cosine ramp: 0 for x <= 0, 1 for x >= 1."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    return 0.5 - 0.5 * math.cos(math.pi * x)


def taper(f):
    if f <= F_TAPER:
        return 1.0
    if f >= F_HI:
        return 0.0
    return 0.5 + 0.5 * math.cos(math.pi * (f - F_TAPER) / (F_HI - F_TAPER))


# ---------------------------------------------------------------- wavetables

def build_table(partials):
    """partials: (k, a_cos, b_sin) triples -> one cycle of TN samples."""
    tab = [0.0] * TN
    for k, a, b in partials:
        for i in range(TN):
            j = (k * i) & TMASK
            tab[i] += a * COS[j] + b * SIN[j]
    return tab


def pulse_table(duty, f_top):
    """Zero-mean pulse wave (+-1 swing), band-limited for fundamentals <= f_top.

    Fourier series of a pulse of width `duty` centred on phase 0:
        x(t) = sum_k 4/(pi k) * sin(pi k duty) * cos(k t)
    """
    parts = []
    k = 1
    while k * f_top < F_HI:
        a = 4.0 / (math.pi * k) * math.sin(math.pi * k * duty) * taper(k * f_top)
        if abs(a) > 1e-9:
            parts.append((k, a, 0.0))
        k += 1
    return build_table(parts)


# The 2A03 triangle steps through these 32 levels (4-bit) every cycle.
NES_TRI = [15, 14, 13, 12, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1, 0,
           0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15]


def nes_triangle_table(f_top):
    """The stepped NES triangle, band-limited via its exact Fourier series."""
    n = len(NES_TRI)
    vals = [(v - 7.5) / 7.5 for v in NES_TRI]          # zero-mean, +-1
    parts = []
    k = 1
    while k * f_top < F_HI:
        a = b = 0.0
        for s, v in enumerate(vals):
            t0 = 2.0 * math.pi * s / n
            t1 = 2.0 * math.pi * (s + 1) / n
            a += v * (math.sin(k * t1) - math.sin(k * t0))
            b += v * (math.cos(k * t0) - math.cos(k * t1))
        w = taper(k * f_top) / (math.pi * k)
        if (abs(a) + abs(b)) * w > 1e-9:
            parts.append((k, a * w, b * w))
        k += 1
    return build_table(parts)


# ---------------------------------------------------------------- rendering

def render(buf, t_on, gate, f0, tables, env, gain, pitch=None,
           phase0=0.25, xfade=0.010):
    """Mix one note into buf.

    tables   list of (t_switch, table) in time order, first t_switch == 0.
             At each switch the two tables are crossfaded over `xfade`
             seconds (an NES duty change, minus the click).
    env(t)   amplitude envelope, t = seconds since note-on.
    pitch(t) pitch offset in semitones (bend + vibrato), or None.
    """
    n_on = int(round(t_on * SR))
    n = int(round(gate * SR))
    ph = phase0
    cur = 0
    last = len(tables) - 1
    for i in range(n):
        t = i / SR
        while cur < last and t >= tables[cur + 1][0]:
            cur += 1
        x = ph * TN
        j = int(x)
        fr = x - j
        j1 = (j + 1) & TMASK
        tab = tables[cur][1]
        s = tab[j] + (tab[j1] - tab[j]) * fr
        if cur > 0:
            w = smooth((t - tables[cur][0]) / xfade)
            if w < 1.0:
                old = tables[cur - 1][1]
                so = old[j] + (old[j1] - old[j]) * fr
                s = so + (s - so) * w
        buf[n_on + i] += gain * env(t) * s
        f = f0 if pitch is None else f0 * 2.0 ** (pitch(t) / 12.0)
        ph += f / SR
        if ph >= 1.0:
            ph -= 1.0


def env_pluck(gate, sus=0.55, dec=0.065, att=0.003, rel=0.012):
    """NES-ish volume envelope: instant hit, quick decay to a sustain level."""
    def e(t):
        g = smooth(t / att) if t < att else 1.0
        g *= sus + (1.0 - sus) * math.exp(-t / dec)
        if t > gate - rel:
            g *= smooth((gate - t) / rel)
        return g
    return e


def env_gate(gate, att=0.003, rel=0.010):
    """The triangle has no volume control: just on/off (de-clicked)."""
    def e(t):
        g = smooth(t / att) if t < att else 1.0
        if t > gate - rel:
            g *= smooth((gate - t) / rel)
        return g
    return e


def env_held(gate, hold, power, att=0.003):
    """Hit, settle, hold, then fade smoothly to exactly zero at `gate`."""
    def e(t):
        g = smooth(t / att) if t < att else 1.0
        g *= 0.82 + 0.18 * math.exp(-t / 0.06)
        if t > hold:
            x = (t - hold) / (gate - hold)
            g *= (1.0 - x) ** power if x < 1.0 else 0.0
        return g
    return e


def held_pitch(gate, bend=-3.5, bend_start=0.20, bend_curve=1.45,
               vib_start=0.12, vib_ramp=0.40, vib_depth=0.28, vib_grow=0.12,
               rate0=5.8, rate1=4.6):
    """Slow downward bend (ease-in) plus a delayed vibrato that widens and
    slows down as the note dies."""
    def p(t):
        b = 0.0
        if t > bend_start:
            x = (t - bend_start) / (gate - bend_start)
            b = bend * x ** bend_curve
        d = vib_depth * smooth((t - vib_start) / vib_ramp)
        d += vib_grow * smooth((t - vib_start - vib_ramp) / (gate - vib_start - vib_ramp))
        vph = 2.0 * math.pi * (rate0 * t + (rate1 - rate0) * t * t / (2.0 * gate))
        return b + d * math.sin(vph)
    return p


def darken(x, n0, n1, t_open, f_from, f_to):
    """One-pole low-pass on x[n0:n1], in place. Cutoff stays at f_from for
    t_open seconds, then glides exponentially down to f_to at n1."""
    ns = n0 + int(t_open * SR)
    y = 0.0
    for i in range(n0, n1):
        fc = f_from if i < ns else f_from * (f_to / f_from) ** ((i - ns) / (n1 - ns))
        y += (1.0 - math.exp(-2.0 * math.pi * fc / SR)) * (x[i] - y)
        x[i] = y


# ---------------------------------------------------------------- the score

U = 0.155          # one short step, seconds
GAP = 0.018        # articulation gap before the next note
LEAD_GAIN = 1.0
BASS_GAIN = 0.75

# (midi note, steps, duty) -- original phrase, D minor
PHRASE = [
    (74, 1, 0.25),   # D5
    (70, 1, 0.25),   # Bb4
    (69, 2, 0.50),   # A4  (resting point of the first half)
    (65, 1, 0.25),   # F4
    (64, 1, 0.25),   # E4
]
HELD_MIDI = 62     # D4, the low held note (bass doubles at D3)
HELD_DUR = 1.36
DUTY_SWITCH = 0.32  # held note: 25% duty -> 50% duty at this time


def synth():
    t_held = sum(steps for _, steps, _ in PHRASE) * U
    total = t_held + HELD_DUR
    buf = [0.0] * (int(round(total * SR)) + 1)

    t = 0.0
    for midi, steps, duty in PHRASE:
        gate = steps * U - GAP
        f = hz(midi)
        env = env_pluck(gate) if steps == 1 else env_pluck(gate, sus=0.60, dec=0.09)
        render(buf, t, gate, f, [(0.0, pulse_table(duty, f))], env, LEAD_GAIN)
        fb = f / 2.0
        render(buf, t, gate, fb, [(0.0, nes_triangle_table(fb))],
               env_gate(gate), BASS_GAIN)
        t += steps * U

    # held note: lead and bass share one pitch curve (exact octave doubling)
    f = hz(HELD_MIDI)
    pitch = held_pitch(HELD_DUR)
    f_top = f * 2.0 ** (0.5 / 12.0)          # vibrato headroom; bend only goes down
    # 50% duty carries more RMS than 25%; trim it so the switch reads as a
    # timbre change ("the note closes"), not a swell.
    lead_tabs = [(0.0, pulse_table(0.25, f_top)),
                 (DUTY_SWITCH, [v * 0.90 for v in pulse_table(0.50, f_top)])]
    held = [0.0] * len(buf)
    render(held, t_held, HELD_DUR, f, lead_tabs,
           env_held(HELD_DUR, hold=0.34, power=1.35), LEAD_GAIN, pitch=pitch)
    # as the note dies its top end dies first, so the tail never turns buzzy
    n_on = int(round(t_held * SR))
    darken(held, n_on, len(held), 0.25, 16000.0, 2200.0)
    for i in range(n_on, len(buf)):
        buf[i] += held[i]
    render(buf, t_held, HELD_DUR, f / 2.0, [(0.0, nes_triangle_table(f_top / 2.0))],
           env_held(HELD_DUR, hold=0.28, power=2.0), BASS_GAIN, pitch=pitch)
    return buf


# ---------------------------------------------------------------- mastering

def dc_block(x, fc=20.0):
    r = math.exp(-2.0 * math.pi * fc / SR)
    y = [0.0] * len(x)
    px = py = 0.0
    for i, v in enumerate(x):
        py = v - px + r * py
        px = v
        y[i] = py
    return y


def master(x, fade_in=0.002, fade_out=0.040, peak_db=-1.0):
    x = dc_block(x)
    mean = sum(x) / len(x)
    x = [v - mean for v in x]
    n_in = int(fade_in * SR)
    n_out = int(fade_out * SR)
    for i in range(n_in):
        x[i] *= smooth(i / n_in)
    n = len(x)
    for i in range(n_out):
        x[n - 1 - i] *= smooth(i / n_out)
    peak = max(abs(v) for v in x)
    g = 10.0 ** (peak_db / 20.0) / peak
    return [v * g for v in x]


def write_wav(path, x):
    pcm = array('h', [max(-32767, min(32767, int(round(v * 32767.0)))) for v in x])
    if sys.byteorder == 'big':
        pcm.byteswap()
    with wave.open(path, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def main(argv):
    if len(argv) != 2:
        sys.stderr.write("usage: python3 -I game-over.py out.wav\n")
        return 2
    write_wav(argv[1], master(synth()))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
