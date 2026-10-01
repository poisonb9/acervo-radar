# -*- coding: utf-8 -*-
"""Embute uma familia do acervo no runner do GitHub.

⛔⛔ O QUE ESTE SCRIPT NAO FAZ: comprar cota. As chaves sao as mesmas da
    maquina local. Se o provedor recusa la', recusa aqui.

⛔ MODO SECO E' O PADRAO. A primeira corrida de qualquer familia deve contar o
   que FARIA -- quantos itens, quantos tokens, quantos lotes, quanto tempo pelo
   teto do provedor -- antes de gastar um token. Custou caro aprender que
   corrida longa que morre no meio nao deixa nada.

⚠️ O CORPUS NAO VIVE NESTE REPO. Ele tem gigabytes e fica na maquina do dono.
   O runner recebe a fatia por artefato ou por `--entrada`; sem isso, este
   script conta zero e DIZ que contou zero, em vez de fingir trabalho.
"""
import argparse
import json
import os
import pathlib
import sys
import time
import urllib.error
import urllib.request

AQUI = pathlib.Path(__file__).resolve().parent
SAIDA = AQUI.parent / "saida"
CHARS_POR_TOKEN = 3.5

# ⛔ Teto por conta, MEDIDO em 28/09/2026 -- nao e' chute nem documentacao.
#    A Voyage sem forma de pagamento responde textualmente `3 RPM and 10K TPM`.
TETOS = {
    "voyage": {"tpm": 10000, "lote_tokens": 3000, "dims": 1024},
    "jina":   {"tpm": 60000, "lote_tokens": 8000, "dims": 1024},
    "nvidia": {"tpm": None,  "lote_tokens": 3000, "dims": 2048},
    "google": {"tpm": None,  "lote_tokens": 3000, "dims": 768},
}

SECRET_DO_PROVEDOR = {
    "voyage": "VOYAGE_CHAVES",
    "jina": "JINA_CHAVES",
    "nvidia": "NVIDIA_CHAVES",
    "google": "GEMINI_CHAVES",
}


def chaves(provedor):
    """Uma por linha no secret, como o radar ja' faz."""
    bruto = os.environ.get(SECRET_DO_PROVEDOR[provedor], "")
    return [l.strip() for l in bruto.splitlines() if l.strip()]


def lotes_por_orcamento(textos, teto):
    grupos, atual, custo = [], [], 0
    for i, t in enumerate(textos):
        c = max(1, int(len(t) / CHARS_POR_TOKEN))
        if atual and custo + c > teto:
            grupos.append(atual)
            atual, custo = [], 0
        atual.append(i)
        custo += c
    if atual:
        grupos.append(atual)
    return grupos


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--provedor", default="voyage")
    ap.add_argument("--fonte", default="")
    ap.add_argument("--entrada", type=pathlib.Path, default=None,
                    help="jsonl com {id, texto}; sem ele nao ha' o que fazer")
    ap.add_argument("--seco", action="store_true")
    a = ap.parse_args()

    prov = (a.provedor or "voyage").strip()
    if prov not in TETOS:
        print("⛔ provedor desconhecido: %s" % prov)
        return 2

    ks = chaves(prov)
    print("provedor .......... %s" % prov)
    print("chaves no anel .... %d" % len(ks))
    if not ks and not a.seco:
        print("⛔ nenhuma chave no secret %s -- nada a fazer."
              % SECRET_DO_PROVEDOR[prov])
        return 1

    entrada = a.entrada
    if entrada is None:
        cand = AQUI.parent / "entrada" / ((a.fonte or "corpus") + ".jsonl")
        entrada = cand if cand.exists() else None

    if entrada is None or not entrada.exists():
        # ⛔ DIZER que nao ha' entrada, e sair 1. Corrida que nao acha o corpus
        #    e termina verde e' o defeito que faz o artefato sair vazio sem
        #    ninguem perceber -- ja' aconteceu com migracao de codigo sem dado.
        print("⛔ SEM CORPUS. Esperava %s"
              % (entrada or (AQUI.parent / "entrada" / "<fonte>.jsonl")))
        print("   O acervo nao vive neste repo (sao GB). Suba a fatia como")
        print("   artefato ou passe --entrada. NAO vou reportar sucesso vazio.")
        return 1

    itens = [json.loads(l) for l in open(entrada, encoding="utf-8")]
    textos = [it["texto"] for it in itens]
    tokens = sum(max(1, int(len(t) / CHARS_POR_TOKEN)) for t in textos)
    teto = TETOS[prov]
    grupos = lotes_por_orcamento(textos, teto["lote_tokens"])

    print("itens ............. %d" % len(itens))
    print("tokens (estimado) . %d" % tokens)
    print("lotes ............. %d (teto %d tokens)"
          % (len(grupos), teto["lote_tokens"]))
    if teto["tpm"]:
        tpm_total = teto["tpm"] * max(1, len(ks))
        print("teto do anel ...... %d tokens/min" % tpm_total)
        print("tempo previsto .... %.0f min" % (tokens / tpm_total))
    else:
        print("teto do anel ...... nao medido para %s" % prov)
        print("tempo previsto .... DESCONHECIDO -- medir antes de prometer")

    if a.seco:
        print()
        print("⚠️ MODO SECO: nada foi chamado, nada foi gasto, nada foi escrito.")
        return 0

    print("⛔ o caminho molhado ainda nao foi ligado neste script.")
    print("   Isto e' de proposito: a contagem seca vem primeiro, e so' depois")
    print("   de o dono ver o tempo previsto e' que faz sentido gastar cota.")
    return 3


if __name__ == "__main__":
    sys.exit(main())
