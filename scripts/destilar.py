# -*- coding: utf-8 -*-
"""ESTAGIO 3 -- destila as legendas novas em fichas.

⭐⭐ A COTA DO GEMINI E' POR MODELO, e esta e' a descoberta que torna o
    pipeline viavel. Medido em 21/09/2026, nas MESMAS 9 chaves:

        gemini-3.8-flash .. 0 chaves com cota
        gemini-3.7-flash .. 4
        gemini-3.6-flash .. 7
        gemini-3.5-flash .. 6

    Trocar de CHAVE nao recupera cota; trocar de MODELO recupera. Por isso
    `--modelos` e' uma cadeia, e nao um valor.

⛔ FALSO VERDE, o defeito que mais enganou nesta casa: um lote pode devolver
   ZERO ficha sem erro nenhum. Em 21/09 um lote de 33 videos rendeu zero
   porque o esquema nao casava com o conteudo, e o processo saiu com
   sucesso. Por isso este script SEMPRE reporta o que produziu, e zero em
   tudo devolve codigo 1.

⛔ E O PARSER ACEITA DUAS FORMAS: array de objetos OU array de arrays
   posicionais. O nemotron devolve a segunda com frequencia, e a versao
   antiga descartava tudo em silencio.

Chaves por ambiente: GEMINI_CHAVES, NVIDIA_CHAVES, OPENROUTER_CHAVES.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import urllib.error
import urllib.request

CHARS_POR_LOTE = 9000

URL_GEMINI = ("https://generativelanguage.googleapis.com/v1beta/models/"
              "%s:generateContent?key=%s")
URL_NV = "https://integrate.api.nvidia.com/v1/chat/completions"
URL_OR = "https://openrouter.ai/api/v1/chat/completions"
MODELO_NEMO = "nvidia/nemotron-3-super-120b-a12b"

CAMPOS = ("situacao", "saida", "ferramenta", "passo_concreto",
          "quando_NAO_usar", "base")

INSTRUCAO = """Voce extrai SAIDAS PRATICAS de uma transcricao de video.

Devolva APENAS um array JSON. Cada item e um objeto com estes campos:

  "situacao"        quando alguem precisaria disto. Frase curta e concreta.
  "saida"           o que fazer. Acionavel, nao generico.
  "ferramenta"      nome da ferramenta/servico citado, ou null.
  "passo_concreto"  comando, ajuste, propriedade ou sequencia citada, ou null.
  "quando_NAO_usar" limite, ressalva ou caso em que falha. null se nao dito.
  "base"            "DEMONSTRADO" se o video mostra funcionando;
                    "AFIRMADO" se e' so' afirmado.

⛔ Campo que a transcricao nao sustenta recebe null. Preencher por
plausibilidade e' o defeito que esta ficha existe para nao cometer.
⚠️ A transcricao NAO carrega o que esta' na TELA. Se a fala for "mudo isso
aqui e veja", nao invente o que era: devolva null.
Se o video nao tiver nenhuma saida pratica, devolva [].
"""


def chaves(nome: str) -> list[str]:
    return [l.strip() for l in os.environ.get(nome, "").splitlines() if l.strip()]


def rotas(modelos: list[str]) -> list[tuple]:
    """(rota, modelo, url, chaves) na ordem de tentativa."""
    out = []
    for m in modelos:
        if m == "nemotron":
            for fam, url in (("NVIDIA_CHAVES", URL_NV),
                             ("OPENROUTER_CHAVES", URL_OR)):
                ks = chaves(fam)
                if ks:
                    out.append(("oai", MODELO_NEMO, url, ks))
        else:
            ks = chaves("GEMINI_CHAVES")
            if ks:
                out.append(("gemini", m, URL_GEMINI, ks))
    return out


def para_json(txt: str) -> list[dict]:
    t = txt.strip()
    i, j = t.find("["), t.rfind("]")
    if i < 0 or j < 0:
        raise ValueError("sem array JSON na resposta")
    dados = json.loads(t[i:j + 1])
    saida = []
    for x in dados:
        if isinstance(x, dict):
            saida.append(x)
        elif isinstance(x, list):
            # ⛔ array POSICIONAL. Tamanho diferente levanta erro em vez de
            #    virar ficha torta -- campo deslocado e' pior que lote falho.
            if len(x) != len(CAMPOS):
                raise ValueError("array posicional com %d campos" % len(x))
            saida.append(dict(zip(CAMPOS, x)))
    return saida


def pedir(rota: str, modelo: str, url: str, chave: str, texto: str) -> str:
    prompt = INSTRUCAO + "\n\n---TEXTO---\n" + texto
    if rota == "gemini":
        corpo = json.dumps({
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0, "maxOutputTokens": 8192}}).encode()
        req = urllib.request.Request(url % (modelo, chave), data=corpo,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=240) as r:
            d = json.load(r)
        partes = d["candidates"][0]["content"]["parts"]
        # ⚠️ modelo de raciocinio pode por o pensamento em parts[0].
        #    Pegar o primeiro com "text" que nao seja marcado como thought.
        for p in partes:
            if "text" in p and not p.get("thought"):
                return p["text"]
        return partes[0].get("text", "")
    corpo = json.dumps({"model": modelo, "temperature": 0,
                        "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request(url, data=corpo, headers={
        "Content-Type": "application/json", "Authorization": "Bearer " + chave})
    with urllib.request.urlopen(req, timeout=240) as r:
        return json.load(r)["choices"][0]["message"]["content"]


def chamar(cadeia: list[tuple], texto: str) -> tuple[list[dict], str]:
    ultimo = "sem tentativa"
    for rota, modelo, url, ks in cadeia:
        for k in ks:
            try:
                return para_json(pedir(rota, modelo, url, k, texto)), modelo
            except urllib.error.HTTPError as e:
                ultimo = "%s HTTP %d" % (modelo, e.code)
                if e.code == 429:
                    break          # ⭐ cota do MODELO acabou: proximo modelo
            except Exception as e:  # noqa: BLE001
                ultimo = "%s %s" % (modelo, type(e).__name__)
    raise RuntimeError(ultimo)


def lotes(t: str) -> list[str]:
    """Fatia em pedacos de CHARS_POR_LOTE. Funciona SEM quebras de linha.

    ⛔ A versao anterior fatiava so' por linha. Legenda da FTA nao tem
    quebra nenhuma -- e' uma linha unica -- entao `splitlines()` devolvia 1
    elemento e o limite NUNCA era aplicado: um video de 239.738 chars foi
    enviado como UM lote so'. O modelo devolveu as primeiras fichas e o
    resto se perdeu em silencio, sem erro e sem log. Medido em 21/09/2026:
    um video 24x maior que outro rendeu o MESMO numero de fichas, que foi
    o sintoma que denunciou o problema.

    Por isso a linha comprida demais e' quebrada por tamanho. Vale para
    qualquer fonte futura que venha sem quebras.
    """
    out, atual, n = [], [], 0
    for linha in t.splitlines(keepends=True):
        # linha que sozinha estoura o lote: parte em pedacos
        while len(linha) > CHARS_POR_LOTE:
            if atual:
                out.append("".join(atual)); atual, n = [], 0
            corte = linha.rfind(" ", 0, CHARS_POR_LOTE) + 1 or CHARS_POR_LOTE
            out.append(linha[:corte])
            linha = linha[corte:]
        if n + len(linha) > CHARS_POR_LOTE and atual:
            out.append("".join(atual)); atual, n = [], 0
        atual.append(linha); n += len(linha)
    if atual:
        out.append("".join(atual))
    return out


def texto_da_legenda(p: pathlib.Path) -> str:
    """So' a FALA. Nunca o JSON cru.

    ⭐ A FTA devolve `transcript` como LISTA de trechos
    (`{"text": ..., "start": ..., "duration": ...}`). Serializar essa lista
    manda `start` e `duration` para o modelo: medido em 21/09/2026 numa
    corrida real de 3 videos, **58% dos caracteres eram metadado** -- 88 mil
    tokens jogados fora em tres videos. Numa semana cheia isso sozinho
    queima a cota que o anel de chaves existe para poupar.
    """
    d = json.loads(p.read_text(encoding="utf-8", errors="replace"))
    t = d.get("transcript") or d.get("text") or ""
    if isinstance(t, str):
        return t
    if isinstance(t, list):
        partes = []
        for s in t:
            if isinstance(s, dict):
                partes.append(str(s.get("text") or ""))
            elif isinstance(s, str):
                partes.append(s)
        # \n e nao espaco: da' ao `lotes()` pontos naturais de corte, em vez
        # de uma linha unica de centenas de milhares de caracteres.
        junto = "\n".join(x.strip() for x in partes if x.strip())
        if junto:
            return junto
    # formato desconhecido: melhor mandar tudo do que mandar nada, mas o
    # aviso tem de aparecer, senao a degradacao passa silenciosa.
    print("   ⚠️ transcript em formato inesperado (%s) em %s: caindo no JSON cru"
          % (type(t).__name__, p.name), flush=True)
    return json.dumps(t, ensure_ascii=False)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--entrada", default="legendas")
    ap.add_argument("--saida", default="fichas")
    # ⭐ gemini-flash-lite-latest fecha a cadeia de proposito: medido em
    #    21/09/2026, foi o UNICO Gemini que respondeu 200 nas 7 chaves boas
    #    enquanto 3.6 e 3.5 devolviam 429 em todas elas. Como a cota e' POR
    #    MODELO, uma cadeia sem ele pode terminar sem nenhuma rota Gemini
    #    viva -- foi o que aconteceu no dia em que isto foi escrito.
    ap.add_argument("--modelos", default="nemotron,gemini-3.6-flash,"
                                         "gemini-3.5-flash,gemini-3.7-flash,"
                                         "gemini-flash-lite-latest")
    ap.add_argument("--limite", type=int, default=0, help="⭐ use 1 antes do lote")
    a = ap.parse_args()

    cadeia = rotas([m.strip() for m in a.modelos.split(",") if m.strip()])
    if not cadeia:
        print("⛔ nenhuma chave de modelo no ambiente.")
        return 2
    print("cadeia de modelos:", " -> ".join("%s(%d chaves)" % (m, len(k))
                                            for _, m, _, k in cadeia))

    ent = pathlib.Path(a.entrada)
    sai = pathlib.Path(a.saida)
    sai.mkdir(parents=True, exist_ok=True)
    arquivos = sorted(ent.rglob("*.json"))
    if a.limite:
        arquivos = arquivos[:a.limite]
    print("legendas a destilar:", len(arquivos))

    total_fichas = falhos = 0
    usados: dict[str, int] = {}
    for n, p in enumerate(arquivos, 1):
        cod = p.parent.name
        destino = sai / cod / (p.stem + ".json")
        if destino.is_file():
            continue
        destino.parent.mkdir(parents=True, exist_ok=True)
        texto = texto_da_legenda(p)
        if len(texto) < 200:
            continue
        fichas = []
        for lote in lotes(texto):
            try:
                fs, modelo = chamar(cadeia, lote)
                fichas.extend(fs)
                usados[modelo] = usados.get(modelo, 0) + 1
            except Exception as e:  # noqa: BLE001
                falhos += 1
                if falhos <= 3:
                    print("   lote falhou: %s" % str(e)[:90], flush=True)
        destino.write_text(json.dumps(
            {"codigo": cod, "video": p.stem, "fichas": fichas,
             "modelos_usados": usados,
             "AVISO": ("ficha nao e' citacao. A transcricao nao carrega o "
                       "que estava na TELA.")},
            ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        total_fichas += len(fichas)
        if n % 20 == 0 or n == len(arquivos):
            print("   %d/%d | fichas %d | falhos %d"
                  % (n, len(arquivos), total_fichas, falhos), flush=True)

    print()
    print("fichas: %d | lotes falhos: %d | modelos: %s"
          % (total_fichas, falhos, usados))
    if total_fichas == 0 and arquivos:
        print("⛔ ZERO fichas com %d legendas. Isto NAO e' sucesso -- ou o"
              " esquema nao casa com o conteudo, ou nao houve cota." % len(arquivos))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
