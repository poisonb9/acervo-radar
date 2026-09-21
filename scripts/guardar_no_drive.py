# -*- coding: utf-8 -*-
"""ESTAGIO 5 -- guarda a saida da semana no Drive (conta cryptozpin).

⛔ POR QUE ESTE ESTAGIO EXISTE: se o PC nao estiver disponivel, o dono ainda
   precisa alcancar o conhecimento novo. O commit no GitHub cobre o codigo e
   as fichas; este passo cobre o resgate MANUAL, numa pasta organizada por
   data, para baixar de qualquer maquina.

⭐ REUSO DECLARADO: mesma autenticacao ja' usada em `clip_engine/contas_drive.py`
   -- OAuth de USUARIO (`Credentials.from_authorized_user_info`), escopo
   `drive`, token vindo de variavel de ambiente. Nao inventa metodo novo, e
   nao usa Service Account.
   ⛔ A razao de NAO usar Service Account esta' medida naquele modulo: a SA
      do Actions nao enxerga arquivo subido por login OAuth pessoal, nem
      dentro de pasta compartilhada (404 "File not found", 28/07/2026).

⚠️ COTA E' DE QUEM CRIA O ARQUIVO, nao de quem hospeda a pasta -- medido em
   29/07/2026, quando 60 MB subidos numa pasta de outra conta sairam da cota
   de quem subiu. Compartilhar da' acesso, nao empresta espaco.

⛔ NAO SOBE: legenda em bruto, video, chave, dicionario. So' o que serve para
   resgate -- fichas, skill e o resumo da semana.

Uso (no runner):
    TOKEN_DRIVE_JSON=<conteudo do token> python guardar_no_drive.py \\
        --pasta "Acervo Radar" --entrada fichas skills
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
from datetime import datetime, timezone

SCOPES = ["https://www.googleapis.com/auth/drive"]
#: ⛔ o que NUNCA sobe, mesmo se estiver na pasta apontada
PROIBIDO = (".vtt", ".srt", ".mp4", ".webm", ".mkv", ".m4a", ".pdf", ".djvu")
PROIBIDO_NOME = ("dicionario_canais", "chaves", "token_", "client_secret")


def servico():
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    bruto = os.environ.get("TOKEN_DRIVE_JSON", "").strip()
    if bruto:
        cred = Credentials.from_authorized_user_info(json.loads(bruto), SCOPES)
    else:
        caminho = pathlib.Path(os.environ.get("TOKEN_DRIVE_FILE", "token_drive.json"))
        if not caminho.is_file():
            raise SystemExit("⛔ sem token: defina TOKEN_DRIVE_JSON ou TOKEN_DRIVE_FILE")
        cred = Credentials.from_authorized_user_file(str(caminho), SCOPES)
    return build("drive", "v3", credentials=cred, cache_discovery=False)


def pasta(srv, nome: str, pai: str | None = None) -> str:
    """Acha ou cria a pasta. Idempotente: rodar duas vezes nao duplica."""
    q = ("mimeType='application/vnd.google-apps.folder' and trashed=false "
         "and name='%s'" % nome.replace("'", "\\'"))
    if pai:
        q += " and '%s' in parents" % pai
    achados = srv.files().list(q=q, fields="files(id)", pageSize=1).execute()
    if achados.get("files"):
        return achados["files"][0]["id"]
    corpo = {"name": nome, "mimeType": "application/vnd.google-apps.folder"}
    if pai:
        corpo["parents"] = [pai]
    return srv.files().create(body=corpo, fields="id").execute()["id"]


def pode_subir(p: pathlib.Path) -> bool:
    if p.suffix.lower() in PROIBIDO:
        return False
    return not any(m in p.name.lower() for m in PROIBIDO_NOME)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pasta", default="Acervo Radar")
    ap.add_argument("--entrada", nargs="+", default=["fichas", "skills"])
    ap.add_argument("--seco", action="store_true")
    a = ap.parse_args()

    arquivos = []
    for e in a.entrada:
        raiz = pathlib.Path(e)
        if not raiz.exists():
            continue
        for p in (raiz.rglob("*") if raiz.is_dir() else [raiz]):
            if p.is_file() and pode_subir(p):
                arquivos.append(p)
    mb = sum(p.stat().st_size for p in arquivos) / 1048576
    semana = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    print("arquivos a subir: %d  (%.1f MB)  -> %s / %s"
          % (len(arquivos), mb, a.pasta, semana))
    if a.seco:
        print("⚠️  --seco: nada foi enviado.")
        return 0
    if not arquivos:
        print("nada a subir.")
        return 0

    from googleapiclient.http import MediaFileUpload
    srv = servico()
    raiz_id = pasta(srv, a.pasta)
    semana_id = pasta(srv, semana, raiz_id)
    subiu = 0
    for p in arquivos:
        # ⭐ a subpasta espelha o codigo do canal, para resgate manual
        #    ficar navegavel em vez de virar um monte de arquivo solto
        sub = p.parent.name if p.parent.name not in a.entrada else ""
        destino = pasta(srv, sub, semana_id) if sub else semana_id
        srv.files().create(
            body={"name": p.name, "parents": [destino]},
            media_body=MediaFileUpload(str(p), resumable=False),
            fields="id").execute()
        subiu += 1
        if subiu % 25 == 0:
            print("   %d/%d" % (subiu, len(arquivos)), flush=True)
    print("subidos: %d em '%s/%s'" % (subiu, a.pasta, semana))
    return 0


if __name__ == "__main__":
    sys.exit(main())
