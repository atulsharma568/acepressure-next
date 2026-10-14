How the AcePressure starter sounds are made
===========================================

Each <slug>.py here synthesizes one of the 8 starter sounds from math alone.
The scripts use only the Python standard library (no samples, recordings or
network) and fixed random seeds, so every run writes the same WAV.

Run the commands below from this folder with Python 3 (the Python that
runs AcePressure is fine).

1. Regenerate a WAV (44.1 kHz, mono, 16-bit PCM):

     python -I vine-boom.py vine-boom.wav

   The slugs are vine-boom, air-horn, cash-register, victory-fanfare, clap,
   game-over, ba-dum-tss and sad-trombone. Each script's docstring explains
   how its sound is built.

2. Master the WAVs to MP3. This needs FFmpeg with libmp3lame on PATH
   (Install_Media_Tools.bat installs FFmpeg on Windows):

     python -I master.py <wav_folder> <mp3_folder> [slug ...]

   master.py reads <wav_folder>/<slug>.wav, writes <mp3_folder>/<slug>.mp3
   and saves its measurements to <wav_folder>/master-report.json. For each
   sound it:
   - applies one gain to reach about -16 LUFS integrated loudness;
   - shaves any true peak above -1.5 dBTP with a look-ahead limiter;
   - encodes with ffmpeg/libmp3lame: VBR quality 2, mono, 44.1 kHz, no
     metadata.

The MP3s in acepressure/starter_sounds/ were made this way. Running both
steps again with the FFmpeg 9.0.2 build they were made with reproduced
them byte for byte; other FFmpeg or LAME builds may produce slightly
different bytes.

The sounds are public domain under CC0 1.0; see
acepressure/starter_sounds/README.txt.
