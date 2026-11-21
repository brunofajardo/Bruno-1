"""Corta silêncios, gera trilha original, grava legenda estilo Reels e mixa o áudio."""
import json, subprocess, sys, wave, numpy as np
from pathlib import Path

SRC, WORDS, OUT = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
WORK = OUT.parent
# Trechos com fala (segundos), com folga de ~0,15 s
KEEP = [(1.55, 3.15), (5.40, 9.95), (12.25, 15.55)]
FIX = {"Claudio,": "Claude,"}  # Whisper ouviu "Claudio"
SR = 44100

# ---- 1. Remapear tempos das palavras para a linha do tempo cortada
words = json.load(open(WORDS))
def remap(t):
    acc = 0.0
    for a, b in KEEP:
        if t < a: return acc
        if t <= b: return acc + t - a
        acc += b - a
    return acc
total = sum(b - a for a, b in KEEP)
for w in words:
    w["w"] = FIX.get(w["w"].strip(), w["w"].strip())
    w["s"], w["e"] = remap(w["s"]), remap(w["e"])

# ---- 2. Legendas ASS: blocos de até 3 palavras, palavra atual em amarelo
def ts(t):
    t = max(0, t); h = int(t // 3600); m = int(t % 3600 // 60); s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"
chunks, cur = [], []
for w in words:
    cur.append(w)
    if len(cur) == 3 or w["w"][-1] in ",.!?":
        chunks.append(cur); cur = []
if cur: chunks.append(cur)
ev = []
for i, ch in enumerate(chunks):
    end_chunk = chunks[i + 1][0]["s"] if i + 1 < len(chunks) else total
    for j, w in enumerate(ch):
        st = w["s"] if j else ch[0]["s"]
        en = ch[j + 1]["s"] if j + 1 < len(ch) else end_chunk
        if en - st < 0.05: continue
        txt = " ".join(("{\\c&H00E5FF&}" + x["w"].upper() + "{\\c&HFFFFFF&}") if k == j else x["w"].upper()
                       for k, x in enumerate(ch))
        ev.append(f"Dialogue: 0,{ts(st)},{ts(en)},Reels,,0,0,0,,{{\\fad(40,0)}}{txt}")
srt = []
for i, ch in enumerate(chunks):
    en = chunks[i + 1][0]["s"] if i + 1 < len(chunks) else total
    srt.append(f"{i+1}\n{ts(ch[0]['s']).replace('.', ',')}0 --> {ts(en).replace('.', ',')}0\n{' '.join(x['w'] for x in ch)}\n")
(WORK / "legenda.srt").write_text("\n".join(srt).replace("0:00:", "00:00:"), encoding="utf-8")
(WORK / "legenda.ass").write_text(f"""[Script Info]
ScriptType: v4.00+
PlayResX: 720
PlayResY: 960
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Reels,Inter Display,64,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,1,0,1,5,2,2,40,40,230,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
""" + "\n".join(ev) + "\n", encoding="utf-8")

# ---- 3. Trilha original sintetizada (C - G - Am - F, 100 bpm)
bpm = 100; beat = 60 / bpm; dur = total + 1
t = np.arange(int(SR * dur)) / SR
def note(f): return 440 * 2 ** ((f - 69) / 12)
chords = [[60, 64, 67], [55, 59, 62], [57, 60, 64], [53, 57, 60]]
music = np.zeros_like(t)
bar = beat * 4
for k in range(int(dur / bar) + 1):
    ch = chords[k % 4]; t0 = k * bar
    seg = (t >= t0) & (t < t0 + bar); tt = t[seg] - t0
    pad = sum(np.sin(2 * np.pi * note(n) * tt) + 0.3 * np.sin(2 * np.pi * note(n) * 2.003 * tt) for n in ch)
    music[seg] += 0.06 * pad * np.minimum(1, tt / 0.3) * np.minimum(1, (bar - tt) / 0.2)
    music[seg] += 0.12 * np.sin(2 * np.pi * note(ch[0] - 24) * tt) * np.exp(-tt * 1.5)  # baixo
    for s in range(8):  # arpejo em colcheias
        n = (ch + [ch[0] + 12])[[0, 1, 2, 3, 2, 1, 0, 1][s]] + 12
        a0 = t0 + s * beat / 2; m = (t >= a0) & (t < a0 + beat); x = t[m] - a0
        music[m] += 0.09 * np.sin(2 * np.pi * note(n) * x) * np.exp(-x * 6)
for b in range(int(dur / beat) + 1):  # kick suave + hi-hat
    a0 = b * beat; m = (t >= a0) & (t < a0 + 0.25); x = t[m] - a0
    music[m] += 0.25 * np.sin(2 * np.pi * (50 + 80 * np.exp(-x * 30)) * x) * np.exp(-x * 12)
    h0 = a0 + beat / 2; m = (t >= h0) & (t < h0 + 0.05); x = t[m] - h0
    music[m] += 0.03 * np.random.default_rng(b).standard_normal(m.sum()) * np.exp(-x * 80)
music *= np.minimum(1, t / 0.8) * np.minimum(1, (dur - 1 - t).clip(0) / 1.0)  # fade in/out
music = (music / np.abs(music).max() * 0.9 * 32767).astype(np.int16)
with wave.open(str(WORK / "trilha.wav"), "wb") as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes(music.tobytes())

# ---- 4. Corte + legenda + mix com ducking da música sob a voz
parts = "".join(f"[0:v]trim={a}:{b},setpts=PTS-STARTPTS[v{i}];[0:a:0]atrim={a}:{b},asetpts=PTS-STARTPTS,"
                f"afade=t=in:d=0.04,afade=t=out:st={b-a-0.04}:d=0.04[a{i}];" for i, (a, b) in enumerate(KEEP))
cat = "".join(f"[v{i}][a{i}]" for i in range(len(KEEP))) + f"concat=n={len(KEEP)}:v=1:a=1[vc][ac];"
fc = (parts + cat +
      "[vc]scale=720:960:flags=lanczos,ass=" + str(WORK / "legenda.ass") + "[vout];"
      "[ac]highpass=f=80,loudnorm=I=-16:TP=-1.5:LRA=11,asplit[voz][sc];"
      f"[1:a]atrim=0:{total},volume=0.35,aresample=48000[mus];"
      "[mus][sc]sidechaincompress=threshold=0.03:ratio=6:attack=20:release=400[duck];"
      "[voz][duck]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95[aout]")
subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(SRC), "-i", str(WORK / "trilha.wav"),
                "-filter_complex", fc, "-map", "[vout]", "-map", "[aout]",
                "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(OUT)], check=True)
print(f"OK: {OUT} ({total:.2f}s)")
