# Edição automática de vídeo

Grave → mande o vídeo para o Claude (ou digite `/editar-video`) → receba o vídeo pronto.

**O que o processo faz:** transcreve a fala (Whisper), corta pausas acima de 0,6 s, enquadra
o rosto em 9:16 (1080×1920), grava legenda estilo Reels (palavra falada em amarelo), gera
`.srt` editável, adiciona trilha original que abaixa quando você fala e normaliza o volume
para -16 LUFS.

## Rodar manualmente

```bash
pip install -r scripts/requirements.txt
python3 scripts/editar_video.py MEU_VIDEO.mov            # padrão: 9:16 + trilha
python3 scripts/editar_video.py MEU_VIDEO.mov --clarear  # rosto contra a luz
python3 scripts/editar_video.py MEU_VIDEO.mov --musica minha_musica.mp3
python3 scripts/editar_video.py MEU_VIDEO.mov --formato original --musica nenhuma
```

Saída em `saida/<nome>/`: `video_final.mp4`, `legenda.srt`, `transcricao.txt`, `relatorio.json`.

## Para o resultado ficar bom (o que a edição NÃO conserta)

- **Resolução:** grave em 1080p ou 4K. Vídeo em 360p ampliado fica borrado.
- **Luz:** fique de frente para a janela, não de costas.
- **Gancho:** a primeira frase decide se a pessoa para de rolar o feed. Comece pelo ponto principal.
- **Nomes próprios:** se a legenda errar um nome, adicione em `correcoes.json`.
