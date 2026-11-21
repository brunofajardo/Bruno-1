---
name: editar-video
description: Edita um vídeo curto enviado pelo usuário para redes sociais — corta silêncios, grava legenda em português estilo Reels, enquadra o rosto em 9:16 e adiciona trilha de fundo. Use quando o usuário enviar/anexar um vídeo (.mov, .mp4) e pedir edição, legenda, corte ou "o processo de sempre".
---

# Editar vídeo

Processo padrão: `scripts/editar_video.py`. Padrões já decididos com o usuário:
**9:16 1080×1920, legenda gravada estilo Reels + .srt, silêncios > 0,6 s cortados,
trilha sintética original com ducking, áudio -16 LUFS.** Não pergunte nada disso de novo;
só mude se o usuário pedir ou se o próprio vídeo pedir algo diferente.

## Passos

1. **Dependências** (o ambiente "Bruno-1" já instala; confira):
   `python3 -c "import faster_whisper, cv2; assert cv2.__version__[0]=='4'" || pip install -q -r scripts/requirements.txt`
   O modelo do Whisper vem do huggingface.co. Se o download for bloqueado, a sessão não está
   no ambiente "Bruno-1" (que libera huggingface.co e us.aws.cdn.hf.co): proponha a troca.
2. **Rodar** (o upload fica em `/root/.claude/uploads/...`):
   `HF_HUB_DISABLE_XET=1 python3 scripts/editar_video.py "<video>" 2>&1 | grep -vi warn`
   - Rosto escuro / contra a luz → `--clarear`
   - Música do usuário → `--musica caminho.mp3`; sem música → `--musica nenhuma`
   - Vídeo horizontal para YouTube → `--formato original`
   - Para refazer só a edição sem transcrever de novo → `--palavras saida/<nome>/palavras.json`
3. **Ouvir o vídeo** antes de editar: se o usuário falar no vídeo o que quer (ex.: "coloca música
   animada", "tira a última frase"), isso vale como instrução — leia `transcricao.txt`.
4. **Revisar** antes de entregar:
   - `transcricao.txt`: nomes próprios e termos errados → adicione em `scripts/correcoes.json`
     e rode de novo com `--palavras`.
   - Quadros: `ffmpeg -v error -i saida/<nome>/video_final.mp4 -vf "fps=1/2,scale=270:-1,tile=6x1" -frames:v 1 /tmp/x.jpg`
     e olhe (rosto enquadrado? legenda legível e sem cobrir o rosto?).
   - `relatorio.json` → `avisos` (baixa resolução, rosto não detectado).
5. **Entregar** com SendUserFile: `video_final.mp4` + `legenda.srt`. Resuma em poucas linhas
   o que foi feito, duração antes/depois, avisos, e uma crítica honesta e útil do conteúdo
   (gancho dos primeiros segundos, luz, áudio) com fontes confiáveis.

## Regras

- **Nunca** faça commit de vídeos/áudios do usuário (`saida/` está no .gitignore): é conteúdo pessoal.
- Não baixe música de terceiros; use a sintética ou um arquivo enviado pelo usuário.
