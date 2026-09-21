# -*- coding: utf-8 -*-
"""ESTAGIO 4 -- regenera a SKILL a partir das fichas.

⛔ A SKILL E' DERIVADA. Nao editar a mao: o proximo radar sobrescreve.

⭐ A skill declara as proprias LACUNAS, e isso nao e' modestia -- e' o que
   sustenta a unica coisa que um acervo indexado faz e uma ficha nao:
   responder AUSENCIA. Uma skill que esconde o que nao cobre transforma
   "nao achei" em "nao existe", que e' o erro mais caro possivel aqui.

⚠️ DUAS LACUNAS SAO ESTRUTURAIS e vao escritas em toda geracao:
   1. a transcricao nao carrega o que estava na TELA. Em canal de design,
      "mudo isso aqui e veja" fica sem referente.
   2. video sem legenda nao entra. Medido em 21/09/2026: 561 de 9.400.

⛔ O CANAL APARECE POR CODIGO. O dicionario fica fora do repositorio.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from collections import Counter
from datetime import datetime, timezone


def carregar(raiz: pathlib.Path) -> tuple[list[dict], Counter, int]:
    fichas, por_cod, videos = [], Counter(), 0
    for p in sorted(raiz.rglob("*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            continue
        fs = d.get("fichas") or []
        if not fs:
            continue
        videos += 1
        cod = d.get("codigo", p.parent.name)
        por_cod[cod] += len(fs)
        for f in fs:
            f["_codigo"] = cod
            fichas.append(f)
    return fichas, por_cod, videos


def limpo(v) -> str:
    s = "" if v is None else str(v).strip()
    return "" if s.lower() in ("none", "null", "nao_declarado", "") else s


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fichas", default="fichas")
    ap.add_argument("--saida", default="skills")
    ap.add_argument("--nome", default="css-frontend")
    a = ap.parse_args()

    raiz = pathlib.Path(a.fichas)
    if not raiz.is_dir():
        print("⛔ pasta de fichas ausente:", raiz)
        return 2
    fichas, por_cod, videos = carregar(raiz)
    if not fichas:
        print("⛔ ZERO fichas. A skill NAO sera' regenerada -- sobrescrever "
              "uma skill boa com uma vazia e' pior que nao atualizar.")
        return 1

    ferramentas = Counter(limpo(f.get("ferramenta")) for f in fichas)
    ferramentas.pop("", None)
    demonstrado = sum(1 for f in fichas if limpo(f.get("base")).upper() == "DEMONSTRADO")
    com_passo = sum(1 for f in fichas if limpo(f.get("passo_concreto")))
    com_limite = sum(1 for f in fichas if limpo(f.get("quando_NAO_usar")))
    hoje = datetime.now(timezone.utc).date().isoformat()

    corpo = []
    corpo.append("---")
    corpo.append("name: %s" % a.nome)
    corpo.append("description: >-")
    corpo.append("  Saidas praticas destiladas de %d videos de %d canais do acervo."
                 % (videos, len(por_cod)))
    corpo.append("  %d fichas, %d com passo concreto. Use para achar o que ja'"
                 % (len(fichas), com_passo))
    corpo.append("  foi dito sobre uma ferramenta ou situacao antes de decidir.")
    corpo.append("---")
    corpo.append("")
    corpo.append("# %s" % a.nome)
    corpo.append("")
    corpo.append("Gerado em %s. ⛔ Derivado -- nao editar a mao." % hoje)
    corpo.append("")
    corpo.append("## O que ha' aqui")
    corpo.append("")
    corpo.append("| medida | valor |")
    corpo.append("|---|---|")
    corpo.append("| fichas | %d |" % len(fichas))
    corpo.append("| videos | %d |" % videos)
    corpo.append("| canais | %d |" % len(por_cod))
    corpo.append("| com passo concreto | %d (%.0f%%) |"
                 % (com_passo, 100 * com_passo / len(fichas)))
    corpo.append("| com limite declarado | %d (%.0f%%) |"
                 % (com_limite, 100 * com_limite / len(fichas)))
    corpo.append("| marcadas DEMONSTRADO | %d (%.0f%%) |"
                 % (demonstrado, 100 * demonstrado / len(fichas)))
    corpo.append("")
    corpo.append("## ⛔ O que esta skill NAO cobre")
    corpo.append("")
    corpo.append("**Ela nao prova ausencia.** Se voce nao achar algo aqui, isso")
    corpo.append("NAO significa que nenhum canal falou do assunto. Significa que")
    corpo.append("nao foi destilado. Para provar ausencia e' preciso um indice")
    corpo.append("exaustivo sobre o texto integral, e esta skill nao e' isso.")
    corpo.append("")
    corpo.append("**Ela nao ve a tela.** As fichas vem de TRANSCRICAO. Em canal")
    corpo.append("de design, boa parte do ensino e' visual -- codigo aparecendo")
    corpo.append("no editor, o antes e depois de um layout. Uma frase como")
    corpo.append("\"agora eu mudo isso aqui\" fica sem referente, e a ficha")
    corpo.append("devolve null em vez de adivinhar.")
    corpo.append("")
    corpo.append("**Video sem legenda nao entrou.** Nao ha' como saber o que")
    corpo.append("havia neles.")
    corpo.append("")
    corpo.append("**Ficha nao e' citacao.** Para a frase exata, abra o video.")
    corpo.append("")
    corpo.append("## Por canal")
    corpo.append("")
    corpo.append("| codigo | fichas |")
    corpo.append("|---|---|")
    for cod, n in sorted(por_cod.items()):
        corpo.append("| `%s` | %d |" % (cod, n))
    corpo.append("")
    corpo.append("⚠️ O canal aparece por CODIGO. O dicionario que liga codigo a")
    corpo.append("canal fica fora do repositorio, por desenho.")
    corpo.append("")
    corpo.append("## Ferramentas mais citadas")
    corpo.append("")
    for nome, n in ferramentas.most_common(25):
        corpo.append("- **%s** — %d fichas" % (nome, n))
    corpo.append("")

    dest = pathlib.Path(a.saida) / a.nome
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "SKILL.md").write_text("\n".join(corpo), encoding="utf-8")
    (dest / "fichas.json").write_text(
        json.dumps({"gerado_em": hoje, "fichas": fichas},
                   ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("SKILL escrita: %s" % (dest / "SKILL.md"))
    print("  %d fichas | %d videos | %d canais" % (len(fichas), videos, len(por_cod)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
