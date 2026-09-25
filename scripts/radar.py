# -*- coding: utf-8 -*-
"""ESTAGIO 1 -- enumera os canais e devolve SO' os IDs novos.

Nao gasta credito, nao chama modelo, nao baixa video. So' compara.

⛔ O CANAL NUNCA APARECE POR NOME AQUI. O dicionario `codigo -> handle` vive
   fora do repositorio e e' injetado por `--dicionario` ou pela variavel
   `DICIONARIO_CANAIS`. Sem ele, este script nao sabe o que enumerar -- e
   isso e' proposital.

⛔ O MANIFESTO DE IDS TAMBEM VIVE FORA. Um unico ID de video revela o canal,
   entao versiona-lo anularia a codificacao.

⚠️ ENUMERAR FUNCIONA; BAIXAR VIDEO NAO. Medido em 21/09/2026: o `yt-dlp`
   enumera 1.049 IDs em 36 s, mas qualquer acesso POR VIDEO devolve
   "Sign in to confirm you're not a bot" desde 16/09. Sao pontas diferentes.
   A legenda vem da FTA, no estagio 2.

⛔ E UM DIAGNOSTICO ERRADO JA' CUSTOU UMA ARQUITETURA: testei a enumeracao num
   canal que devolveu 3 videos e conclui que estava bloqueada. O canal TINHA
   3 videos. Um unico caso negativo nao prova bloqueio -- confirme num canal
   GRANDE antes de trocar de abordagem.

Uso:
    python radar.py --dicionario ../dicionario_canais.json \\
                    --manifestos ../manifestos --saida novos.json
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import subprocess
import sys
from datetime import datetime, timezone

from porta_youtube import rodar  # toda chamada ao YouTube passa pela sentinela


def enumerar(handle: str, timeout: int = 900) -> list[str]:
    r = rodar(
        ["yt-dlp", "--flat-playlist", "--ignore-errors", "--print", "%(id)s",
         "https://www.youtube.com/@%s/videos" % handle.lstrip("@")],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        rotulo=f"listar {handle}", timeout=timeout)
    return [l.strip() for l in (r.stdout or "").splitlines()
            if len(l.strip()) == 11]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dicionario", default=os.environ.get("DICIONARIO_CANAIS", ""))
    ap.add_argument("--manifestos", default="manifestos")
    ap.add_argument("--canais", default="canais")
    ap.add_argument("--saida", default="novos.json")
    ap.add_argument("--so-codigo", default="", help="roda um canal so'")
    a = ap.parse_args()

    if not a.dicionario or not pathlib.Path(a.dicionario).is_file():
        print("⛔ dicionario ausente. Sem ele o radar nao sabe o que enumerar.")
        print("   Passe --dicionario ou defina DICIONARIO_CANAIS.")
        return 2

    dic = json.loads(pathlib.Path(a.dicionario).read_text(encoding="utf-8"))["canais"]
    manif = pathlib.Path(a.manifestos)
    manif.mkdir(parents=True, exist_ok=True)
    cans = pathlib.Path(a.canais)
    cans.mkdir(parents=True, exist_ok=True)

    novos_total: dict[str, list[str]] = {}
    print("%-6s %8s %8s %8s" % ("codigo", "no canal", "conhec.", "NOVOS"))
    for cod, meta in sorted(dic.items()):
        if a.so_codigo and cod != a.so_codigo:
            continue
        try:
            atuais = enumerar(meta["handle"])
        except subprocess.TimeoutExpired:
            print("%-6s TIMEOUT" % cod)
            continue
        if not atuais:
            # ⛔ lista vazia NAO e' "canal sem novidade": e' sintoma de
            #    enumeracao falhada. Tratar como zero apagaria o canal do
            #    manifesto na gravacao abaixo.
            print("%-6s ⛔ enumeracao vazia -- PULADO (nao sobrescreve)" % cod)
            continue
        p = manif / (cod + ".json")
        conhecidos = set()
        if p.is_file():
            conhecidos = set(json.loads(p.read_text(encoding="utf-8")).get("ids") or [])
        novos = [v for v in atuais if v not in conhecidos]
        print("%-6s %8d %8d %8d" % (cod, len(atuais), len(conhecidos), len(novos)))
        if novos:
            novos_total[cod] = novos
        # o manifesto so' cresce; ID que some do canal (video removido) fica
        # registrado, senao ele voltaria a ser "novo" na semana seguinte.
        p.write_text(json.dumps(
            {"codigo": cod, "ids": sorted(conhecidos | set(atuais))},
            ensure_ascii=False), encoding="utf-8")
        (cans / (cod + ".json")).write_text(json.dumps({
            "codigo": cod,
            "prioridade": meta.get("prioridade"),
            "videos_conhecidos": len(conhecidos | set(atuais)),
            "ultima_enumeracao": datetime.now(timezone.utc).date().isoformat(),
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    pathlib.Path(a.saida).write_text(json.dumps({
        "quando_utc": datetime.now(timezone.utc).isoformat(),
        "novos_por_codigo": novos_total,
        "total": sum(len(v) for v in novos_total.values()),
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    n = sum(len(v) for v in novos_total.values())
    print()
    print("videos NOVOS nesta semana: %d  (= %d creditos FTA no estagio 2)" % (n, n))
    if n == 0:
        print("⚠️  zero novos. Se isto se repetir varias semanas, desconfie do")
        print("    RADAR antes de concluir que os canais pararam de postar.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
