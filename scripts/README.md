# Edição automática de vídeos para o Instagram

**Fluxo:** grave quantos vídeos quiser → abra uma sessão no ambiente **Bruno-1** → anexe todos
e mande → receba cada um pronto: `video_final.mp4` + `capa.jpg` + `post.txt`.

**O que o processo faz em cada vídeo:** transcreve a fala (Whisper), corta pausas acima de
0,6 s, enquadra o rosto em 9:16 (1080×1920), grava legenda estilo Reels (palavra falada em
amarelo), gera `.srt`, adiciona trilha original que abaixa quando você fala, normaliza o
volume para -16 LUFS, gera a capa e avisa sobre problemas (baixa resolução, rosto não
encontrado, mais de 3 min).

## Rodar manualmente

```bash
pip install -r scripts/requirements.txt
python3 scripts/editar_video.py PASTA_COM_VIDEOS/          # lote inteiro
python3 scripts/editar_video.py v1.mov v2.mov --clarear    # rosto contra a luz
python3 scripts/editar_video.py v1.mov --musica minha_musica.mp3
python3 scripts/editar_video.py PASTA/ --refazer           # refaz tudo (sem re-transcrever)
```

Saída: `saida/<nome>/` por vídeo e `saida/resumo_lote.json` com o status de todos.
Vídeos já prontos são pulados; um vídeo com erro não interrompe os outros.

## Para o resultado ficar bom (o que a edição NÃO conserta)

- **Resolução:** grave em 1080p ou 4K. Vídeo em 360p ampliado fica borrado.
- **Luz:** fique de frente para a janela, não de costas.
- **Gancho:** a primeira frase decide se a pessoa para de rolar o feed. Comece pelo ponto principal.
- **Duração:** Reels aceita até 3 min, mas vídeos curtos são mais assistidos até o fim.
- **Nomes próprios:** se a legenda errar um nome, adicione em `correcoes.json`.
