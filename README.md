# Acervo Radar

Pipeline semanal que mantém as skills atualizadas a partir das legendas novas
dos canais do acervo. Roda no GitHub Actions, para não depender de o PC estar
ligado.

## O que este repositório NÃO contém, e por quê

⛔ **Os livros.** Nem PDF nem texto extraído. Decisão do dono em 21/09/2026.
Este pipeline é só do YouTube.

⛔ **O dicionário de canais.** Os canais aparecem como `C001`..`C015`. O
arquivo que liga código a canal (`dicionario_canais.json`) fica **fora** daqui.

⛔ **Os IDs de vídeo.** E a razão é específica: **um único ID de vídeo revela o
canal** — basta colar no navegador. Versionar os IDs anularia a codificação.
Eles vivem em `manifestos/`, que é local, com cópia no Drive. O workflow busca
o manifesto no início e o devolve no fim.

⛔ **As chaves.** Vão em GitHub Secrets, nunca em arquivo.

⚠️ **O que continua revelando conteúdo:** as fichas destiladas dizem *do que* o
canal trata, ainda que não o nomeiem. A codificação esconde a identidade, não o
assunto. Isso é limitação declarada, não descuido.

## Os quatro estágios

```
1 RADAR      yt-dlp --flat-playlist por canal
             compara com o manifesto -> devolve só os IDs NOVOS
             grátis; medido em 21/09: 1.049 IDs em 36 s

2 COLETA     FreeTranscriptAPI, 1 crédito por vídeo
             ⚠️ cobra mesmo quando o vídeo não tem legenda
             ⛔ nunca baixa vídeo — só legenda

3 DESTILACAO nemotron + gemini 3.5 / 3.6 / 3.7 em paralelo
             ⭐ a cota do Gemini é POR MODELO: medido em 21/09, o 3.8 estava
                em 0 chaves enquanto o 3.6 tinha 7. Cair de modelo em modelo
                é o que mantém o pipeline vivo quando uma cota acaba.

4 SKILL      regenera e commita
```

## ⛔ Regras que custaram caro, e que o workflow tem de respeitar

**Commit só no fim, num passo único.** Empurrar durante a corrida do radar faz
o runner perder tudo — já custou 95 vídeos e 2h26.

**Nunca mp4.** Só legenda. 1,6 GB de vídeo já derrubaram uma suíte.

**Testar um antes de esperar muito.** Toda etapa nova roda com `--limite 1`
antes do lote. Em 21/09 um lote de 33 vídeos rendeu zero fichas porque o
esquema não casava com o conteúdo — um teste de um vídeo teria mostrado isso
em 30 segundos.

**Zero ficha com zero falha não é resultado.** É a bancada dando verde sobre
lista vazia. Todo estágio reporta o que produziu, e zero exige diagnóstico.

## Se o PC não estiver disponível

As atualizações vão para a pasta do Drive, organizadas por data e por código de
canal, para download manual. ⚠️ Pendente: o destino no Drive ainda não está
configurado.

## Estrutura

```
canais/C0NN.json        contadores por canal. Sem nome, sem ID.
scripts/                radar, coleta, destilação, geração de skill
skills/                 saída regenerada
manifestos/             ⛔ LOCAL — os IDs. Ver .gitignore.
.github/workflows/      o cron semanal
```
