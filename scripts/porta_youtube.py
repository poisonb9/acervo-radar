# -*- coding: utf-8 -*-
"""Porta unica pro YouTube: toda chamada passa pela sentinela do clip_engine.

    from porta_youtube import rodar, vez
    r = rodar(["yt-dlp", "--flat-playlist", ...], "listar canal",
              capture_output=True, text=True)
    with vez("rss do canal", "leve"):
        urllib.request.urlopen(...)

⛔ Regra do dono: uma chamada por vez e sempre intervalada, em QUALQUER
projeto. O estado da sentinela vive no disco desta maquina
(~/.sentinela_youtube), entao so' governa quem passa por ela.

⚠️ Carregada PELO CAMINHO DO ARQUIVO, nao por `import engine...`: outros
projetos tem um pacote `engine` proprio e o nome colidiria em silencio.

⚠️ FALHA FECHADA aqui na maquina: sem a sentinela, nao chama o YouTube.
No runner do GitHub (GITHUB_ACTIONS=true) ela nao existe e o IP nao e'
o nosso, entao a chamada passa direto.

Copia identica em: acervo-radar/scripts, maestros_da_ia e
Cozinha Importada/motor. Mudou uma, mude as tres.
"""
from __future__ import annotations

import contextlib
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

CLIP = Path(os.environ.get("CLIP_ENGINE", str(
    Path.home() / "Desktop" / "Tiktok"
    / "YouTube videos para Google Drive" / "ATUALIZADA" / "clip_engine")))
NA_NUVEM = os.environ.get("GITHUB_ACTIONS") == "true"
_S = None


def sentinela():
    """O modulo da sentinela, ou None no runner. Aqui, sem ela, para."""
    global _S
    if _S is not None:
        return _S
    arq = CLIP / "engine" / "sentinela_youtube.py"
    if not arq.exists():
        if NA_NUVEM:
            return None
        raise SystemExit(f"sentinela do YouTube nao encontrada em {arq} -- "
                         f"nao chamo o YouTube sem ela (ajuste CLIP_ENGINE)")
    spec = importlib.util.spec_from_file_location("sentinela_youtube", arq)
    _S = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(_S)
    return _S


@contextlib.contextmanager
def vez(rotulo: str, peso: str = "pesado"):
    """Segura a porta enquanto o bloco fala com o YouTube (ex.: urllib)."""
    s = sentinela()
    if s is None:
        yield
        return
    with s.vez(rotulo, peso):
        yield


def rodar(cmd: list, rotulo: str = "", peso: str | None = None,
          **kw) -> subprocess.CompletedProcess:
    """`subprocess.run(cmd, **kw)` dentro da vez da sentinela.

    O peso sai do comando (`--skip-download`, `--print`... = leve) e, se a
    saida trouxer bot-check ou 429, puxa o freio -- tentar de novo e' o que
    confirma o padrao de robo.
    """
    s = sentinela()
    if s is None:
        return subprocess.run(cmd, **kw)
    peso = peso or s.peso_do_comando([str(a) for a in cmd])
    with s.vez(rotulo or " ".join(str(a) for a in cmd[:3]), peso):
        r = subprocess.run(cmd, **kw)
    saida = ""
    for x in (r.stdout, r.stderr):
        if isinstance(x, bytes):
            x = x.decode("utf-8", "replace")
        saida += x or ""
    if s.e_bloqueio(saida):
        motivo = next((l for l in saida.splitlines() if s.e_bloqueio(l)),
                      "bot-check")
        s.puxar_freio(motivo, peso=peso)
        print(f"[sentinela] FREIO PUXADO: {motivo[:120]}", file=sys.stderr)
    return r
