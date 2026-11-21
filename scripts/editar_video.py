#!/usr/bin/env python3
"""Edição automática de vídeo curto para redes sociais.

Etapas: transcreve (Whisper) -> corta silêncios -> enquadra o rosto em 9:16
-> grava legenda estilo Reels -> adiciona trilha com ducking -> normaliza áudio.

Uso:
    python3 scripts/editar_video.py VIDEO [-o PASTA] [--formato 9x16|original]
        [--musica sintetica|nenhuma|ARQUIVO] [--pausa 0.6] [--modelo medium]
        [--idioma pt] [--clarear]

Saídas em PASTA (padrão: saida/<nome-do-video>/):
    video_final.mp4, legenda.srt, transcricao.txt, relatorio.json
"""
import argparse, json, re, subprocess, sys, wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
SR_MUS = 44100
OUT_W, OUT_H = 1080, 1920


def run(cmd, **kw):
    return subprocess.run(cmd, check=True, capture_output=True, text=True, **kw)


def duracao(path):
    r = run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)])
    return float(r.stdout.strip())


# ---------------------------------------------------------------- transcrição
def transcrever(video, work, modelo, idioma):
    wav = work / "audio16k.wav"
    run(["ffmpeg", "-y", "-v", "error", "-i", str(video), "-map", "0:a:0", "-ac", "1", "-ar", "16000", str(wav)])
    with wave.open(str(wav)) as w:
        audio = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
    from faster_whisper import WhisperModel  # import tardio: só carrega se precisar
    m = WhisperModel(modelo, device="cpu", compute_type="int8")
    segs, _ = m.transcribe(audio, language=idioma, word_timestamps=True, vad_filter=True)
    return [{"w": w.word.strip(), "s": w.start, "e": w.end} for s in segs for w in s.words if w.word.strip()]


def aplicar_correcoes(words, path):
    if not path.exists():
        return words
    fix = json.loads(path.read_text(encoding="utf-8"))
    for w in words:
        m = re.match(r"^(\W*)(.*?)(\W*)$", w["w"])
        pre, core, suf = m.groups()
        for errado, certo in fix.items():
            if core.lower() == errado.lower():
                w["w"] = pre + certo + suf
    return words


# ---------------------------------------------------------- corte de silêncio
def trechos_com_fala(words, dur, pausa, pad_ini=0.15, pad_fim=0.25):
    if not words:
        return [(0.0, dur)]
    blocos, ini, fim = [], words[0]["s"], words[0]["e"]
    for w in words[1:]:
        if w["s"] - fim > pausa:
            blocos.append((ini, fim)); ini = w["s"]
        fim = max(fim, w["e"])
    blocos.append((ini, fim))
    out = []
    for a, b in blocos:
        a, b = max(0.0, a - pad_ini), min(dur, b + pad_fim)
        if out and a <= out[-1][1]:
            out[-1] = (out[-1][0], b)
        else:
            out.append((a, b))
    return out


def remapear(t, keep):
    acc = 0.0
    for a, b in keep:
        if t < a: return acc
        if t <= b: return acc + t - a
        acc += b - a
    return acc


# ------------------------------------------------------------- enquadramento
def centro_do_rosto(video, work, dur):
    """Mediana do centro do rosto (frações 0-1) em ~15 quadros; None se não achar."""
    import cv2
    fr = work / "frames"; fr.mkdir(exist_ok=True)
    for f in fr.glob("*.jpg"): f.unlink()
    run(["ffmpeg", "-y", "-v", "error", "-i", str(video), "-vf", f"fps={15 / max(dur, 1):.4f}", str(fr / "f%03d.jpg")])
    casc = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    xs, ys, size = [], [], None
    for f in sorted(fr.glob("*.jpg")):
        img = cv2.imread(str(f)); size = img.shape[1], img.shape[0]
        faces = casc.detectMultiScale(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), 1.1, 5, minSize=(img.shape[1] // 10,) * 2)
        if len(faces):
            x, y, w, h = max(faces, key=lambda r: r[2] * r[3])
            xs.append((x + w / 2) / size[0]); ys.append((y + h / 2) / size[1])
    if not xs:
        return None, size
    return (float(np.median(xs)), float(np.median(ys))), size


def filtro_enquadramento(formato, centro, size):
    w, h = size
    if formato == "original":
        ow, oh = (w, h) if h >= 1080 else (round(w * 1080 / h / 2) * 2, 1080)
        return f"scale={ow}:{oh}:flags=lanczos", (ow, oh), max(1, oh / h)
    cx, cy = centro or (0.5, 0.4)
    if w / h > 9 / 16:  # mais largo que 9:16 -> corta laterais
        cw, ch = int(h * 9 / 16) // 2 * 2, h
        x, y = int(min(max(cx * w - cw / 2, 0), w - cw)), 0
    else:               # mais alto -> corta em cima/embaixo, rosto no terço superior
        cw, ch = w, int(w * 16 / 9) // 2 * 2
        x, y = 0, int(min(max(cy * h - ch * 0.4, 0), h - ch))
    return f"crop={cw}:{ch}:{x}:{y},scale={OUT_W}:{OUT_H}:flags=lanczos", (OUT_W, OUT_H), OUT_H / ch


# ------------------------------------------------------------------ legendas
def ts_ass(t):
    t = max(0.0, t); return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"


def ts_srt(t):
    ms = int(round(max(0.0, t) * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def montar_legendas(words, total, res, work):
    W, H = res
    maxc = 16 if W < H else 28           # caracteres por linha
    fonte = int(W * 0.085) if W < H else int(H * 0.07)
    margem = int(H * 0.27) if W < H else int(H * 0.10)
    chunks, cur = [], []
    for w in words:
        if cur and len(" ".join(x["w"] for x in cur + [w])) > maxc:
            chunks.append(cur); cur = []
        cur.append(w)
        if len(cur) == 3 or w["w"][-1] in ",.!?":
            chunks.append(cur); cur = []
    if cur: chunks.append(cur)
    ev, srt = [], []
    for i, ch in enumerate(chunks):
        fim_bloco = chunks[i + 1][0]["s"] if i + 1 < len(chunks) else total
        srt.append(f"{i + 1}\n{ts_srt(ch[0]['s'])} --> {ts_srt(fim_bloco)}\n{' '.join(x['w'] for x in ch)}\n")
        for j, w in enumerate(ch):
            ini, fim = w["s"], (ch[j + 1]["s"] if j + 1 < len(ch) else fim_bloco)
            if fim - ini < 0.05: continue
            txt = " ".join(("{\\c&H00E5FF&}" + x["w"].upper() + "{\\c&HFFFFFF&}") if k == j else x["w"].upper()
                           for k, x in enumerate(ch))
            ev.append(f"Dialogue: 0,{ts_ass(ini)},{ts_ass(fim)},Reels,,0,0,0,,{{\\fad(40,0)}}{txt}")
    (work / "legenda.srt").write_text("\n".join(srt), encoding="utf-8")
    (work / "legenda.ass").write_text(f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Reels,Inter Display,{fonte},&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,1,0,1,{max(3, fonte // 13)},3,2,{W // 15},{W // 15},{margem},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
""" + "\n".join(ev) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- trilha
def trilha_sintetica(dur, path):
    """Trilha original (C-G-Am-F, 100 bpm): pad, baixo, arpejo, kick e hi-hat."""
    t = np.arange(int(SR_MUS * dur)) / SR_MUS
    note = lambda n: 440 * 2 ** ((n - 69) / 12)
    chords = [[60, 64, 67], [55, 59, 62], [57, 60, 64], [53, 57, 60]]
    beat = 0.6; bar = beat * 4; mus = np.zeros_like(t)
    for k in range(int(dur / bar) + 1):
        ch, t0 = chords[k % 4], k * bar
        seg = (t >= t0) & (t < t0 + bar); tt = t[seg] - t0
        pad = sum(np.sin(2 * np.pi * note(n) * tt) + 0.3 * np.sin(2 * np.pi * note(n) * 2.003 * tt) for n in ch)
        mus[seg] += 0.06 * pad * np.minimum(1, tt / 0.3) * np.minimum(1, (bar - tt) / 0.2)
        mus[seg] += 0.12 * np.sin(2 * np.pi * note(ch[0] - 24) * tt) * np.exp(-tt * 1.5)
        arp = ch + [ch[0] + 12]
        for s, idx in enumerate([0, 1, 2, 3, 2, 1, 0, 1]):
            a0 = t0 + s * beat / 2; m = (t >= a0) & (t < a0 + beat); x = t[m] - a0
            mus[m] += 0.09 * np.sin(2 * np.pi * note(arp[idx] + 12) * x) * np.exp(-x * 6)
    for b in range(int(dur / beat) + 1):
        a0 = b * beat; m = (t >= a0) & (t < a0 + 0.25); x = t[m] - a0
        mus[m] += 0.25 * np.sin(2 * np.pi * (50 + 80 * np.exp(-x * 30)) * x) * np.exp(-x * 12)
        h0 = a0 + beat / 2; m = (t >= h0) & (t < h0 + 0.05); x = t[m] - h0
        mus[m] += 0.03 * np.random.default_rng(b).standard_normal(m.sum()) * np.exp(-x * 80)
    mus = (mus / (np.abs(mus).max() or 1) * 0.9 * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR_MUS); w.writeframes(mus.tobytes())


# ---------------------------------------------------------------- render
def renderizar(video, work, keep, total, vfiltro, upscale, clarear, musica):
    n = len(keep)
    fc = "".join(f"[0:v]trim={a:.3f}:{b:.3f},setpts=PTS-STARTPTS[v{i}];"
                 f"[0:a:0]atrim={a:.3f}:{b:.3f},asetpts=PTS-STARTPTS,afade=t=in:d=0.03,"
                 f"afade=t=out:st={max(0, b - a - 0.03):.3f}:d=0.03[a{i}];" for i, (a, b) in enumerate(keep))
    fc += "".join(f"[v{i}][a{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=1[vc][ac];"
    extra = (",eq=brightness=0.03:gamma=1.08:saturation=1.05" if clarear else "") + \
            (",unsharp=5:5:0.6" if upscale > 1.5 else "")
    fc += f"[vc]{vfiltro}{extra},ass=legenda.ass,format=yuv420p[vout];"
    fc += "[ac]highpass=f=80,loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000[voz0];"
    inputs = ["-i", str(video)]
    if musica == "nenhuma":
        fc += "[voz0]alimiter=limit=0.95[aout]"
    else:
        if musica == "sintetica":
            trilha_sintetica(total + 1, work / "trilha.wav"); inputs += ["-i", str(work / "trilha.wav")]
        else:
            inputs += ["-stream_loop", "-1", "-i", str(Path(musica).resolve())]
        fc += ("[voz0]asplit[voz][sc];"
               f"[1:a]aformat=channel_layouts=mono,atrim=0:{total:.3f},asetpts=PTS-STARTPTS,volume=0.35,"
               f"afade=t=in:d=0.8,afade=t=out:st={max(0, total - 1):.3f}:d=1,aresample=48000[mus];"
               "[mus][sc]sidechaincompress=threshold=0.03:ratio=6:attack=20:release=400[duck];"
               "[voz][duck]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95[aout]")
    out = work / "video_final.mp4"
    run(["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", fc, "-map", "[vout]", "-map", "[aout]",
         "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-c:a", "aac", "-b:a", "192k",
         "-movflags", "+faststart", str(out)], cwd=work)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video", type=Path)
    ap.add_argument("-o", "--saida", type=Path)
    ap.add_argument("--formato", choices=["9x16", "original"], default="9x16")
    ap.add_argument("--musica", default="sintetica", help="sintetica | nenhuma | caminho de um arquivo de áudio")
    ap.add_argument("--pausa", type=float, default=0.6, help="pausas maiores que isso (s) são cortadas")
    ap.add_argument("--modelo", default="medium", help="tiny|base|small|medium|large-v3")
    ap.add_argument("--idioma", default="pt")
    ap.add_argument("--clarear", action="store_true", help="clareia levemente (rosto contra a luz)")
    ap.add_argument("--correcoes", type=Path, default=ROOT / "correcoes.json")
    ap.add_argument("--palavras", type=Path, help="JSON de palavras já transcritas (pula o Whisper)")
    a = ap.parse_args()

    video = a.video.resolve()
    work = (a.saida or Path.cwd() / "saida" / video.stem).resolve(); work.mkdir(parents=True, exist_ok=True)
    dur = duracao(video)

    print("1/4 Transcrevendo...", flush=True)
    words = json.loads(a.palavras.read_text()) if a.palavras else transcrever(video, work, a.modelo, a.idioma)
    (work / "palavras.json").write_text(json.dumps(words, ensure_ascii=False, indent=1), encoding="utf-8")
    words = aplicar_correcoes(words, a.correcoes)

    print("2/4 Cortando silêncios e enquadrando...", flush=True)
    keep = trechos_com_fala(words, dur, a.pausa)
    total = sum(b - a_ for a_, b in keep)
    for w in words:
        w["s"], w["e"] = remapear(w["s"], keep), remapear(w["e"], keep)
    centro, size = centro_do_rosto(video, work, dur)
    vfiltro, res, upscale = filtro_enquadramento(a.formato, centro, size)

    print("3/4 Gerando legendas...", flush=True)
    montar_legendas(words, total, res, work)
    (work / "transcricao.txt").write_text(" ".join(w["w"] for w in words) + "\n", encoding="utf-8")

    print("4/4 Renderizando...", flush=True)
    out = renderizar(video, work, keep, total, vfiltro, upscale, a.clarear, a.musica)

    avisos = []
    if min(size) < 1080:
        avisos.append(f"Original em baixa resolução ({size[0]}x{size[1]}): ampliado {upscale:.1f}x, vai parecer suave. Grave em 1080p ou 4K.")
    if centro is None and a.formato == "9x16":
        avisos.append("Rosto não detectado: recorte centralizado. Confira o enquadramento.")
    if not words:
        avisos.append("Nenhuma fala detectada: sem legenda e sem corte.")
    rel = {"entrada": str(video), "saida": str(out), "duracao_original": round(dur, 2), "duracao_final": round(total, 2),
           "trechos_mantidos": [[round(x, 2), round(y, 2)] for x, y in keep], "resolucao_original": size,
           "resolucao_final": res, "centro_rosto": centro, "transcricao": " ".join(w["w"] for w in words), "avisos": avisos}
    (work / "relatorio.json").write_text(json.dumps(rel, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(rel, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as e:
        sys.exit(f"Erro no comando: {' '.join(map(str, e.cmd))[:300]}\n{e.stderr}")
