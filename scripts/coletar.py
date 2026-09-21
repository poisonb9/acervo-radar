# -*- coding: utf-8 -*-
"""ESTAGIO 2 -- baixa a legenda dos videos novos pela FreeTranscriptAPI.

⛔ NUNCA BAIXA VIDEO. Regra permanente do dono: so' transcricao. A FTA nem
   permitiria -- ela tem UMA rota, `/v1/transcript`. Sondado em 21/09/2026:
   channel, videos, playlist, search e credits devolvem 404.

⛔ ELA COBRA 1 CREDITO POR CONSULTA, inclusive quando o video NAO tem
   legenda. Por isso o script pula todo ID que ja' tem arquivo em disco --
   rodar duas vezes nao paga duas vezes.

⚠️ 404 significa "sem legenda", nao falha. Medido em 21/09: de 9.400 videos,
   561 nao tinham legenda. Tratar isso como erro faria o pipeline parecer
   quebrado quando esta' certo.

⭐ ANEL DE CHAVES: 429 e' limite transitorio e so' gira a chave; 401/402/403
   queimam. Queimar por 429 esvaziaria o anel num pico de trafego.

As chaves vem de `FTA_CHAVES` (uma por linha), nunca de arquivo no repo.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://api.freetranscriptapi.com/v1/transcript"


class Anel:
    def __init__(self, chaves: list[str]) -> None:
        self.vivas = list(chaves)
        self.i = 0

    def atual(self) -> str | None:
        return self.vivas[self.i % len(self.vivas)] if self.vivas else None

    def girar(self) -> None:
        self.i += 1

    def queimar(self, k: str, porque: str) -> None:
        if k in self.vivas:
            self.vivas.remove(k)
            print("   ⚠️ chave ...%s fora do anel: %s (restam %d)"
                  % (k[-5:], porque, len(self.vivas)), flush=True)


def buscar(anel: Anel, vid: str, tentativas: int = 4):
    ultimo = "sem tentativa"
    for _ in range(tentativas):
        k = anel.atual()
        if not k:
            return None, "anel vazio"
        url = BASE + "?" + urllib.parse.urlencode({"video_url": vid})
        req = urllib.request.Request(url, headers={
            "Authorization": "Bearer " + k,
            "Accept": "application/json",
            "User-Agent": "acervo-radar/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                return json.load(r), None
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None, "sem legenda"          # ⚠️ nao e' falha
            ultimo = "HTTP %d" % e.code
            if e.code in (401, 403):
                anel.queimar(k, ultimo)
            elif e.code == 402:
                anel.queimar(k, "sem credito")
            else:
                anel.girar()
        except Exception as e:                       # noqa: BLE001
            ultimo = "rede: %s" % type(e).__name__
            time.sleep(2.0)
            anel.girar()
    return None, ultimo


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--novos", default="novos.json")
    ap.add_argument("--saida", default="legendas")
    ap.add_argument("--pausa", type=float, default=0.15)
    ap.add_argument("--seco", action="store_true")
    a = ap.parse_args()

    chaves = [l.strip() for l in os.environ.get("FTA_CHAVES", "").splitlines()
              if l.strip()]
    if not chaves and not a.seco:
        print("⛔ FTA_CHAVES vazio. Sem chave nao ha' coleta.")
        return 2

    d = json.loads(pathlib.Path(a.novos).read_text(encoding="utf-8"))
    por_cod = d.get("novos_por_codigo") or {}
    total = sum(len(v) for v in por_cod.values())
    print("videos novos: %d  (= %d creditos)" % (total, total))
    if a.seco:
        print("⚠️  --seco: nada foi pedido, nenhum credito gasto.")
        return 0
    if total == 0:
        print("nada a coletar.")
        return 0

    anel = Anel(chaves)
    raiz = pathlib.Path(a.saida)
    geral_ok = geral_sem = geral_falha = 0
    for cod, ids in sorted(por_cod.items()):
        dest = raiz / cod
        dest.mkdir(parents=True, exist_ok=True)
        ok = sem = falha = 0
        for i, vid in enumerate(ids, 1):
            alvo = dest / ("%s.json" % vid)
            if alvo.is_file():
                continue                     # ⭐ nao paga duas vezes
            dados, erro = buscar(anel, vid)
            if dados is not None:
                alvo.write_text(json.dumps(dados, ensure_ascii=False),
                                encoding="utf-8")
                ok += 1
            elif erro == "sem legenda":
                alvo.with_suffix(".sem_legenda").write_text("", encoding="utf-8")
                sem += 1
            else:
                falha += 1
                if falha <= 3:
                    print("   %s -> %s" % (vid, erro), flush=True)
            if i % 25 == 0 or i == len(ids):
                print("   %s  %d/%d  ok=%d sem_legenda=%d falha=%d chaves=%d"
                      % (cod, i, len(ids), ok, sem, falha, len(anel.vivas)),
                      flush=True)
            time.sleep(a.pausa)
        geral_ok += ok; geral_sem += sem; geral_falha += falha
        print("FIM %s: ok=%d sem_legenda=%d falha=%d" % (cod, ok, sem, falha))

    print()
    print("TOTAL ok=%d | sem_legenda=%d | falha=%d" % (geral_ok, geral_sem, geral_falha))
    if geral_ok == 0 and total > 0:
        # ⛔ zero com zero falha e' a bancada dando verde sobre lista vazia
        print("⛔ ZERO legendas com %d videos pedidos. Isto NAO e' sucesso." % total)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
