# -*- coding: utf-8 -*-
"""Leva as legendas JA' COLETADAS ate' a nuvem, e as traz de volta la' dentro.

⛔⛔ O PROBLEMA QUE ISTO RESOLVE, e ele foi MEDIDO em 23/09/2026:
    o estagio 2 cobra 1 credito FTA por video, INCLUSIVE quando o video nao
    tem legenda. Numa corrida em que os manifestos ainda nao foram
    promovidos, o radar reapresenta como "novos" videos cuja legenda JA'
    esta' no disco do dono: 1.140 de 1.585. Sem este caminho, a unica saida
    e' repagar por transcricao que ja' existe.

⭐ REUSO DECLARADO: mesma autenticacao de `lote-extracao/tools/drive_io.py`
   -- OAuth de USUARIO, escopo `drive`, token em `TOKEN_DRIVE_JSON`. Nao
   inventa metodo novo, e nao usa Service Account (aquele modulo mediu que a
   SA do Actions nao enxerga arquivo subido por login pessoal).

⛔ POR QUE UM PACOTE, E NAO ARQUIVO A ARQUIVO. Duas razoes, e a primeira e'
   correcao, nao desempenho:
   1. `drive_io.baixar` e `drive_io.enviar` sao PLANOS -- listam e gravam
      numa pasta so'. As legendas vivem em `legendas/C0xx/<id>.json`, e o
      `destilar.py` le o codigo do canal de `p.parent.name`. Subir plano
      faria TODA ficha nascer com o codigo errado, em silencio.
   2. 1.084 arquivos sao 1.084 chamadas de API em cada ponta.
   O pacote preserva a arvore e faz UMA chamada.

⛔ ISTO NAO PUBLICA NADA. O destino e' uma pasta do Drive, privada e
   autenticada por secret. A fronteira da casa e' o REPOSITORIO, que e'
   publico desde 23/09 -- transcricao de terceiro nunca entra nele. E' a
   mesma divisao que o `drive_io.py` ja' declara: "o corpus ENTRA pelo
   Drive, o resultado SAI pelo Drive, o repositorio carrega so' codigo".

⚠️ O QUE ESTE CAMINHO NAO RECUPERA: video que ficou `.sem_legenda` ou que
   falhou na coleta. Medido em 21/09: 53 sem legenda e 3 falhas em 1.140.
   Esses so' voltam numa coleta nova -- um video pode ter ganhado legenda
   depois. Quem usar este atalho esta' trocando ~5% de cobertura por ~72%
   de credito economizado, e a troca fica escrita aqui em vez de escondida.

Uso:
    # na maquina do dono, depois de uma coleta
    python scripts/legendas_io.py enviar --origem legendas --pasta "Acervo Legendas"

    # no runner, antes do estagio 3
    python scripts/legendas_io.py baixar --destino legendas --pasta "Acervo Legendas"
"""
from __future__ import annotations

import argparse
import io
import json
import os
import pathlib
import sys
import tarfile
import tempfile
from datetime import datetime, timezone

SCOPES = ["https://www.googleapis.com/auth/drive"]

#: ⛔ nunca sobe, mesmo dentro da arvore apontada. A lista e' a mesma do
#   `drive_io.py`, por reuso -- e nao inclui extensao de legenda DE PROPOSITO:
#   legenda e' exatamente a carga que este modulo existe para mover.
PROIBIDO_NOME = ("dicionario_canais", "chaves", "token_", "client_secret", ".env")

PREFIXO = "legendas_"
SUFIXO = ".tar.gz"


def servico():
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    bruto = os.environ.get("TOKEN_DRIVE_JSON", "").strip()
    if not bruto:
        sys.exit("⛔ TOKEN_DRIVE_JSON ausente. Sem ele nao ha' como falar com o Drive.")
    cred = Credentials.from_authorized_user_info(json.loads(bruto), SCOPES)
    return build("drive", "v3", credentials=cred, cache_discovery=False)


def achar_pasta(srv, nome: str, criar: bool = False) -> str:
    q = ("mimeType='application/vnd.google-apps.folder' and trashed=false "
         "and name='%s'" % nome.replace("'", "\\'"))
    r = srv.files().list(q=q, fields="files(id,name)", pageSize=5).execute()
    fs = r.get("files") or []
    if fs:
        return fs[0]["id"]
    if not criar:
        sys.exit("⛔ pasta '%s' nao existe no Drive." % nome)
    meta = {"name": nome, "mimeType": "application/vnd.google-apps.folder"}
    return srv.files().create(body=meta, fields="id").execute()["id"]


def empacotar(origem: pathlib.Path, destino: pathlib.Path) -> tuple[int, int]:
    """Empacota preservando `C0xx/<id>.json`. Devolve (arquivos, bytes)."""
    n = 0
    with tarfile.open(destino, "w:gz") as tar:
        for p in sorted(origem.rglob("*")):
            if not p.is_file():
                continue
            if any(x in p.name.lower() for x in PROIBIDO_NOME):
                print("   ⛔ PULADO por nome proibido: %s" % p.name, flush=True)
                continue
            tar.add(p, arcname=str(p.relative_to(origem)))
            n += 1
    return n, destino.stat().st_size


def enviar(srv, pasta_id: str, origem: pathlib.Path) -> int:
    from googleapiclient.http import MediaFileUpload

    if not origem.is_dir():
        sys.exit("⛔ origem '%s' nao existe." % origem)
    carimbo = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    with tempfile.TemporaryDirectory() as tmp:
        pacote = pathlib.Path(tmp) / (PREFIXO + carimbo + SUFIXO)
        n, tam = empacotar(origem, pacote)
        if not n:
            sys.exit("⛔ nada a enviar: '%s' nao tem arquivo." % origem)
        print("pacote: %s | %d arquivos | %.1f MB" % (pacote.name, n, tam / 1e6),
              flush=True)
        meta = {"name": pacote.name, "parents": [pasta_id]}
        srv.files().create(body=meta,
                           media_body=MediaFileUpload(str(pacote), resumable=True),
                           fields="id").execute()
    print("enviado: %s" % pacote.name)
    return n


def mais_novo(srv, pasta_id: str) -> dict:
    r = srv.files().list(
        q="'%s' in parents and trashed=false" % pasta_id,
        orderBy="createdTime desc",
        fields="files(id,name,size,createdTime)", pageSize=50).execute()
    fs = [f for f in (r.get("files") or [])
          if f["name"].startswith(PREFIXO) and f["name"].endswith(SUFIXO)]
    if not fs:
        sys.exit("⛔ nenhum pacote '%s*%s' na pasta. Rode `enviar` antes."
                 % (PREFIXO, SUFIXO))
    return fs[0]


def baixar(srv, pasta_id: str, destino: pathlib.Path) -> int:
    from googleapiclient.http import MediaIoBaseDownload

    f = mais_novo(srv, pasta_id)
    print("pacote mais novo: %s (%s bytes, %s)"
          % (f["name"], f.get("size", "?"), f.get("createdTime", "?")), flush=True)
    destino.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        local = pathlib.Path(tmp) / f["name"]
        req = srv.files().get_media(fileId=f["id"])
        buf = io.FileIO(str(local), "wb")
        dl = MediaIoBaseDownload(buf, req, chunksize=8 * 1024 * 1024)
        pronto = False
        while not pronto:
            _, pronto = dl.next_chunk()
        buf.close()
        # ⛔ `data` filter: tarfile do Python 3.12+ recusa membro com caminho
        #    absoluto ou `..`. Sem isso, um pacote adulterado escreveria fora
        #    de `destino`. O pacote e' nosso, mas a guarda custa uma linha.
        with tarfile.open(local, "r:gz") as tar:
            try:
                tar.extractall(destino, filter="data")
            except TypeError:                      # Python < 3.12
                tar.extractall(destino)
    n = sum(1 for _ in destino.rglob("*.json"))
    print("extraidos: %d arquivos .json em %s" % (n, destino))
    return n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("acao", choices=["enviar", "baixar"])
    ap.add_argument("--pasta", default="Acervo Legendas")
    ap.add_argument("--origem", default="legendas")
    ap.add_argument("--destino", default="legendas")
    a = ap.parse_args()

    srv = servico()
    if a.acao == "enviar":
        pid = achar_pasta(srv, a.pasta, criar=True)
        n = enviar(srv, pid, pathlib.Path(a.origem))
        print("OK: %d legendas no Drive" % n)
    else:
        pid = achar_pasta(srv, a.pasta)
        n = baixar(srv, pid, pathlib.Path(a.destino))
        if not n:
            print("⛔ pacote vazio. Sem legenda nao ha' o que destilar.")
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
