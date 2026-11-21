---
name: editar-video
description: Edita vídeos curtos enviados pelo usuário para o Instagram (Reels), um ou vários de uma vez — corta silêncios, grava legenda em português estilo Reels, enquadra o rosto em 9:16, adiciona trilha, gera capa e texto do post. Use quando o usuário enviar/anexar vídeos (.mov, .mp4) e pedir edição, legenda, corte, "o processo de sempre" ou só mandar os vídeos.
---

# Editar vídeos para o Instagram (em lote)

O usuário grava vários vídeos para o Instagram e quer recebê-los **prontos para postar, sem
perguntas**. Padrões já decididos: **Reels 9:16 1080×1920, legenda gravada estilo Reels + .srt,
silêncios > 0,6 s cortados, trilha sintética original com ducking, áudio -16 LUFS.**
Não pergunte nada disso; só mude se o usuário pedir — inclusive falando no próprio vídeo.

## Passos

1. **Dependências** (o ambiente "Bruno-1" já instala; confira):
   `python3 -c "import faster_whisper, cv2; assert cv2.__version__[0]=='4'" || pip install -q -r scripts/requirements.txt`
   O modelo vem do huggingface.co. Se o download for bloqueado, a sessão não está no ambiente
   "Bruno-1" (que libera huggingface.co e us.aws.cdn.hf.co): proponha a troca.
2. **Rodar TODOS os vídeos num comando só** (uploads ficam em `/root/.claude/uploads/<sessão>/`):
   `HF_HUB_DISABLE_XET=1 python3 scripts/editar_video.py /root/.claude/uploads/<sessão>/ 2>&1 | grep -vi warn`
   (aceita pasta ou lista de arquivos; ~40 s por vídeo de 15 s; vídeos já prontos são pulados).
   Para lotes longos (> ~5 min estimados), rode com `run_in_background` e avise o usuário.
   - Rosto escuro / contra a luz → `--clarear` · música do usuário → `--musica arquivo.mp3`
   - Refazer após corrigir algo → `--refazer` (a transcrição vem do cache, é rápido)
3. **Instruções faladas**: leia `saida/<nome>/transcricao.txt` de cada vídeo. Se o usuário
   pedir algo no vídeo (ex.: "tira a última frase", "música animada"), atenda e refaça só aquele.
4. **Revisar cada vídeo** antes de entregar:
   - Transcrição: nomes próprios/termos errados → adicione em `scripts/correcoes.json`
     e rode de novo com `--refazer` (e faça commit do correcoes.json: o processo aprende).
   - Quadros: `ffmpeg -v error -i saida/<nome>/video_final.mp4 -vf "fps=1/2,scale=270:-1,tile=6x1" -frames:v 1 /tmp/x.jpg`
     e olhe (rosto enquadrado? legenda legível sem cobrir o rosto?).
   - `saida/resumo_lote.json`: status e `avisos` (baixa resolução, rosto não detectado, > 3 min).
5. **Texto do post** para cada vídeo, em `saida/<nome>/post.txt`: primeira linha forte (gancho,
   é o que aparece antes do "mais"), 2–4 linhas de corpo baseadas na transcrição, uma chamada para
   ação, e 3–5 hashtags específicas do tema (não genéricas tipo #love). Tom do próprio usuário.
6. **Entregar** com SendUserFile, por vídeo: `video_final.mp4`, `capa.jpg` e `post.txt`
   (o .srt só se pedirem). Depois, um resumo curto: tabela com vídeo, duração antes→depois,
   avisos; e crítica honesta e útil do conjunto (gancho, luz, áudio, consistência da série),
   com fontes confiáveis.

## Regras

- **Nunca** faça commit de vídeos/áudios/capas do usuário (`saida/` está no .gitignore).
- Não baixe música de terceiros; use a sintética ou um arquivo enviado pelo usuário.
- Um vídeo com erro não deve parar o lote: entregue os outros e explique o erro.
