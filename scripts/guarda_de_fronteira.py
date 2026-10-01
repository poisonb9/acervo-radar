#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GUARDA DE FRONTEIRA -- recusa commit que carregue o que nao pode virar publico.

⛔ POR QUE ELA EXISTE
   O `.gitignore` fecha CAMINHOS: `*.pdf`, `livros-biblioteca/`, `manifestos/`.
   Um caminho novo escapa. Um livro salvo como `notas_do_capitulo.txt` passa
   pelo .gitignore inteiro sem encostar em nenhuma linha.

   Esta guarda nao olha o NOME. Ela le os BYTES que o commit vai gravar e
   decide pelo que mediu. Nome e' escolha de quem salvou; tamanho e conteudo
   nao sao.

   ⇒ As duas camadas se somam. O .gitignore continua sendo a primeira.

⛔ O QUE ELA NAO FAZ
   Nao inspeciona o que ja' esta' no historico -- so' o que esta' no index
   AGORA. Segredo ja' comitado nao volta com esta guarda: volta com revogacao.

USO
   Automatico, via .git/hooks/pre-commit (ver instalar_a_guarda.sh).
   Manual:  python scripts/guarda_de_fronteira.py
   Pinos :  python scripts/guarda_de_fronteira.py --autoteste
"""

import re
import subprocess
import sys

# ---------------------------------------------------------------------------
# LIMIARES -- cada um com a medicao que o justifica, feita em 24/09/2026.
# ---------------------------------------------------------------------------

# Maior arquivo legitimo medido: 16,7 KB (scripts/destilar.py) no acervo-radar
# e 17,9 KB (tools/medicoes/medir_d_minimo.py) no series-compute-pub.
# 64 KiB da' ~3,6x de folga. Uma obra do acervo tem MEGABYTES: nao chega perto.
LIMITE_BYTES = 64 * 1024

# Uma corrida de base64 longa nao aparece em codigo escrito a mao. O dicionario
# de canais codificado nasce exatamente assim.
LIMITE_BASE64 = 512

# O alfabeto base64 tem 64 simbolos, e uma corrida de 512 chars de dado real
# usa quase todos. Texto repetitivo longo usa poucos. 16 e' o corte: bem acima
# do que texto repetido alcanca, bem abaixo do que base64 real produz.
MINIMO_DE_SIMBOLOS_BASE64 = 16

# Um ID de video do YouTube tem 11 chars. Um punhado num teste e' normal;
# uma lista deles e' um manifesto, e um unico ID ja' revela o canal.
LIMITE_IDS_DE_VIDEO = 8

# Marcas de segredo, por FORMA do valor -- nao por nome de variavel.
MARCAS_DE_SEGREDO = (
    (re.compile(rb"AIza[0-9A-Za-z_\-]{35}"), "chave Google/Gemini (AIza...)"),
    (re.compile(rb"sk-[0-9A-Za-z]{20,}"), "chave estilo OpenAI (sk-...)"),
    (re.compile(rb"nvapi-[0-9A-Za-z_\-]{20,}"), "chave NVIDIA (nvapi-...)"),
    (re.compile(rb"sk-or-v1-[0-9a-f]{20,}"), "chave OpenRouter (sk-or-v1-...)"),
    (re.compile(rb"ghp_[0-9A-Za-z]{30,}"), "token GitHub classico (ghp_...)"),
    (re.compile(rb"github_pat_[0-9A-Za-z_]{30,}"), "token GitHub fino (github_pat_...)"),
    (re.compile(rb"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "chave privada PEM"),
)

#: ⭐ O rotulo da unica marca isentada para o proprio fonte. Comparar pelo
#:   ROTULO, e nao pelo indice da tupla, para que reordenar `MARCAS_DE_SEGREDO`
#:   nao mova a isencao para outra marca em silencio.
_MARCA_PEM = "chave privada PEM"

#: ⭐ O caminho deste arquivo como o `git` o nomeia no index: relativo a' raiz
#:   do repositorio, com barra normal. ⛔ NAO derivar de `__file__`: o commit
#:   pode vir de qualquer cwd, e o que importa e' o nome NO INDEX.
_MEU_CAMINHO = "scripts/guarda_de_fronteira.py"


def _normalizar(caminho):
    """Caminho do index em forma canonica, para comparar por igualdade."""
    return str(caminho).replace("\\", "/").lstrip("./")

_BASE64_LONGO = re.compile(rb"[A-Za-z0-9+/]{%d,}={0,2}" % LIMITE_BASE64)
_ID_DE_VIDEO = re.compile(rb"[\"'][0-9A-Za-z_\-]{11}[\"']")


def examinar(caminho, dados):
    """Devolve a lista de motivos para RECUSAR estes bytes. Vazia = liberado.

    Funcao pura: recebe bytes, nao toca em git nem em disco. E' o que os
    pinos exercitam.
    """
    motivos = []

    tamanho = len(dados)
    if tamanho > LIMITE_BYTES:
        motivos.append(
            "tem %s bytes (%.1f KB); o teto e' %s bytes (%d KB)"
            % (f"{tamanho:,}", tamanho / 1024, f"{LIMITE_BYTES:,}", LIMITE_BYTES // 1024)
        )

    # Byte nulo => binario. PDF, EPUB, DJVU, MP4 e imagem caem todos aqui,
    # qualquer que seja a extensao com que tenham sido salvos.
    if b"\x00" in dados:
        motivos.append("contem byte nulo: e' arquivo BINARIO, nao texto/codigo")

    # ⛔⛔ A GUARDA SE RECUSAVA A SI MESMA, e isso a tornava ininstalavel.
    #    Medido em 01/10/2026: `git add scripts/guarda_de_fronteira.py` dava
    #    "contem o que parece ser chave privada PEM" -- e estava certo pelos
    #    BYTES: a l. 61 e' o proprio padrao `-----BEGIN [A-Z ]*PRIVATE KEY-----`
    #    (literal, sem metacaractere, logo ele casa consigo mesmo) e o
    #    autoteste tem a fixture `-----BEGIN RSA PRIVATE KEY-----`.
    #    ⇒ Consequencia real: ela NAO chegava a outra maquina nem ao runner.
    #      Guarda que nao pode ser instalada nao protege nada.
    #
    # ⭐ A ISENCAO E' DUPLAMENTE ESTREITA, de proposito:
    #    1. so' para ESTE arquivo, por IGUALDADE do caminho inteiro -- nunca
    #       por prefixo nem por pasta (um `guarda_de_fronteira.py.bak` NAO
    #       entra, e `scripts/outra/guarda_de_fronteira.py` tambem nao);
    #    2. so' para a marca PEM. As outras continuam valendo AQUI DENTRO:
    #       uma chave `AIza`, `sk-`, `ghp_` ou `nvapi-` colada neste arquivo
    #       ainda e' recusada. As outras marcas nao casam consigo mesmas
    #       porque seus padroes tem metacaractere (`[0-9A-Za-z_\-]{35}`).
    #
    # ⚠️ BURACO RESIDUAL, DECLARADO: uma chave PEM de VERDADE colada neste
    #    arquivo passaria. E' o preco de a guarda poder existir, e e' o menor
    #    que eu consegui -- qualquer isenção mais larga abriria mais.
    for padrao, nome in MARCAS_DE_SEGREDO:
        if nome == _MARCA_PEM and _normalizar(caminho) == _MEU_CAMINHO:
            continue
        if padrao.search(dados):
            motivos.append("contem o que parece ser %s" % nome)

    # ⚠️ Dois pinos vermelhos em 24/09 moldaram esta regra:
    #    1. 63.000 letras 'a' casavam com o alfabeto base64 -> falso positivo.
    #    2. Exigir digito+maiuscula+minuscula corrigia (1), mas base64 legitimo
    #       pode nao ter digito nenhum -> teria aberto um buraco real.
    #    O que separa os dois casos e' VARIEDADE: base64 usa quase todo o
    #    alfabeto de 64; texto repetido usa um punhado de simbolos.
    for corrida in _BASE64_LONGO.findall(dados):
        distintos = len(set(corrida))
        if distintos >= MINIMO_DE_SIMBOLOS_BASE64:
            motivos.append(
                "contem corrida base64 de %d chars com %d simbolos distintos; "
                "base64 nao e' segredo, e' outra grafia" % (len(corrida), distintos)
            )
            break

    ids = set(_ID_DE_VIDEO.findall(dados))
    if len(ids) >= LIMITE_IDS_DE_VIDEO:
        motivos.append(
            "contem %d possiveis IDs de video (teto: %d); um so' ja' revela o canal"
            % (len(ids), LIMITE_IDS_DE_VIDEO)
        )

    return motivos


def _git(*args):
    r = subprocess.run(
        ["git"] + list(args), capture_output=True, check=False
    )
    if r.returncode != 0:
        raise RuntimeError(
            "git %s falhou (rc=%d): %s"
            % (" ".join(args), r.returncode, r.stderr.decode("utf-8", "replace").strip())
        )
    return r.stdout


def arquivos_no_index():
    """Nomes dos arquivos que este commit vai Adicionar, Copiar ou Modificar."""
    saida = _git("diff", "--cached", "--name-only", "--diff-filter=ACM", "-z")
    return [n.decode("utf-8", "replace") for n in saida.split(b"\x00") if n]


def bytes_no_index(caminho):
    """Os bytes EXATOS que serao gravados -- do index, nao do working tree.

    ⛔ Ler o arquivo do disco seria o erro classico: o que vai para o commit
    e' o que foi adicionado, e os dois podem divergir.
    """
    return _git("show", ":" + caminho)


def verificar_o_commit():
    caminhos = arquivos_no_index()
    if not caminhos:
        print("guarda de fronteira: nada no index. Nada a verificar.")
        return 0

    reprovados = []
    maior = 0
    for caminho in caminhos:
        try:
            dados = bytes_no_index(caminho)
        except RuntimeError as e:
            print("guarda de fronteira: NAO CONSEGUI LER '%s' -> %s" % (caminho, e))
            print("ATENCAO: recusando por precaucao: guarda que nao mede nao libera.")
            return 1
        maior = max(maior, len(dados))
        motivos = examinar(caminho, dados)
        if motivos:
            reprovados.append((caminho, motivos))

    print(
        "guarda de fronteira: %d arquivo(s) no index, maior = %s bytes (%.1f KB)"
        % (len(caminhos), f"{maior:,}", maior / 1024)
    )

    if not reprovados:
        print("guarda de fronteira: LIBERADO.")
        return 0

    print("")
    print("=" * 74)
    print("*** COMMIT RECUSADO -- %d arquivo(s) reprovado(s)" % len(reprovados))
    print("=" * 74)
    for caminho, motivos in reprovados:
        print("")
        print("  %s" % caminho)
        for m in motivos:
            print("      - %s" % m)
    print("")
    print("O que fazer:")
    print("  1. Se NAO deveria ir para a nuvem:  git restore --staged <arquivo>")
    print("     e acrescente o padrao ao .gitignore, com o motivo escrito.")
    print("  2. Se for segredo: ele ja' vazou para o disco. REVOGUE a credencial.")
    print("  3. Se for legitimo e grande, a decisao e' do dono -- nao contorne")
    print("     sozinho. O escape existe e e' explicito:  git commit --no-verify")
    print("")
    return 1


# ---------------------------------------------------------------------------
# PINOS -- provam o COMPORTAMENTO, exercitando cada limiar nos dois lados.
# ---------------------------------------------------------------------------

def _autoteste():
    casos = []

    def caso(nome, dados, espera_recusa):
        casos.append((nome, dados, espera_recusa))

    codigo_real = b"import re\n\ndef f(x):\n    return x + 1\n" * 20

    # --- o que TEM de passar (senao a guarda e' inutil: ninguem commita mais)
    caso("codigo python comum", codigo_real, False)
    caso("json de canal anonimo (108 B)",
         b'{\n  "codigo": "C001",\n  "prioridade": 1,\n'
         b'  "videos_conhecidos": 420,\n  "ultima_enumeracao": "2026-09-21"\n}\n',
         False)
    caso("arquivo de 63 KB (logo abaixo do teto)",
         (codigo_real * 40)[: LIMITE_BYTES - 1024], False)
    # ⚠️ Este pino nasceu de um vermelho: 63 KB da letra 'a' eram recusados
    #    como base64. Fica como regressao -- texto repetitivo NAO e' segredo.
    caso("texto repetitivo longo, sem mistura de classes",
         b"a" * (LIMITE_BYTES - 1024), False)
    caso("poucos IDs de video (teste legitimo)",
         b'ids = ["dQw4w9WgXcQ", "aBcDeFgHiJk"]\n', False)
    caso("base64 curto (um hash, um icone pequeno)",
         b'ASSINATURA = "' + b"aGVsbG8x" * 20 + b'"\n', False)

    # --- o que TEM de ser recusado
    caso("livro salvo como .txt (300 KB de texto)", b"O mercado " * 30000, True)
    caso("exatamente no teto + 1 byte", b"a" * (LIMITE_BYTES + 1), True)
    caso("PDF renomeado para .md", b"%PDF-1.7\n\x00\x01binario\x00", True)
    caso("chave Gemini colada no codigo",
         b'K = "AIza' + b"B" * 35 + b'"\n', True)
    caso("token GitHub fino",
         b'T = "github_pat_' + b"1A2b3C4d5E" * 4 + b'"\n', True)
    caso("chave privada PEM",
         b"-----BEGIN RSA PRIVATE KEY-----\nMIIE\n", True)
    # ⛔ Base64 de VERDADE, gerado na hora a partir de um dicionario plausivel.
    #    Inventar a string a mao ja' produziu dois pinos enganosos: a minha
    #    imitacao nao tinha digito, e depois nao tinha variedade. O dado real
    #    e' que decide.
    import base64 as _b64
    import json as _json
    dicionario_plausivel = _json.dumps(
        {"C%03d" % i: "UC%s" % ("aZ9bY8cX7dW6eV5fU4gT3hS2" [:22]) for i in range(1, 31)}
    ).encode()
    caso("dicionario de canais em base64",
         b'D = "' + _b64.b64encode(dicionario_plausivel) + b'"\n', True)
    # 11 chars exatos -- o formato real do ID do YouTube.
    caso("manifesto de IDs de video",
         b"[" + b", ".join(b'"vid%08d"' % i for i in range(30)) + b"]", True)

    # ⭐⭐ PINOS DA ISENCAO DO PROPRIO FONTE (01/10/2026). Sao QUATRO, e os
    #    quatro sao necessarios: com menos, "isentou o fonte" e "parou de
    #    olhar PEM" ficam indistinguiveis -- o mesmo defeito que o detector
    #    de 48-de-48 teve em 27/07.
    _PEM = b"-----BEGIN RSA PRIVATE KEY-----\nMIIE\n"
    _AIZA = b'K = "AIza' + b"B" * 35 + b'"\n'
    pinos_isencao = [
        # 1. SENSIBILIDADE da isencao: o proprio fonte passa com PEM.
        ("isencao: o proprio fonte com PEM passa",
         _MEU_CAMINHO, _PEM, False),
        # 2. ESPECIFICIDADE: outro arquivo com o MESMO PEM continua recusado.
        #    Sem este, a isencao poderia ter desligado a marca para todos.
        ("isencao NAO vaza: outro arquivo com PEM e' recusado",
         "scripts/outra_coisa.py", _PEM, True),
        # 3. ESCOPO POR MARCA: no proprio fonte, chave AIza AINDA e' recusada.
        #    Sem este, a isencao poderia ter desligado TODAS as marcas aqui.
        ("isencao e' so' do PEM: AIza no proprio fonte e' recusada",
         _MEU_CAMINHO, _AIZA, True),
        # 4. IGUALDADE, nao prefixo: um vizinho de nome parecido NAO herda.
        ("isencao e' por caminho EXATO: o .bak nao herda",
         _MEU_CAMINHO + ".bak", _PEM, True),
    ]

    falhas = 0
    for nome, cam, dados, espera_recusa in pinos_isencao:
        motivos = examinar(cam, dados)
        houve = bool(motivos)
        ok = houve == espera_recusa
        if not ok:
            falhas += 1
        print("  %s  %-46s  esperado=%s  medido=%s%s"
              % ("ok  " if ok else "FALHA", nome,
                 "RECUSA" if espera_recusa else "passa ",
                 "RECUSA" if houve else "passa ",
                 ("  <- " + motivos[0]) if (not ok and motivos) else ""))

    for nome, dados, espera_recusa in casos:
        motivos = examinar("caso_de_teste", dados)
        houve_recusa = bool(motivos)
        ok = houve_recusa == espera_recusa
        if not ok:
            falhas += 1
        print(
            "  %s  %-46s  esperado=%s  medido=%s%s"
            % (
                "ok  " if ok else "FALHA",
                nome,
                "RECUSA" if espera_recusa else "passa ",
                "RECUSA" if houve_recusa else "passa ",
                ("  <- " + motivos[0]) if (not ok and motivos) else "",
            )
        )

    # -----------------------------------------------------------------------
    # PINO DE REGRESSAO -- 24/09/2026
    # A guarda recusou um livro de 360 KB, mas ESTOUROU no emoji ao imprimir o
    # motivo: console do Windows e' cp1252. O commit foi abortado pelo CRASH,
    # nao pela decisao -- e o dono nao via por que. Guarda que nao consegue
    # dizer o motivo nao serve.
    # Prova por VALOR: toda linha que a guarda imprime tem de caber em cp1252.
    # -----------------------------------------------------------------------
    import io as _io
    import contextlib as _ctx

    capturado = _io.StringIO()
    with _ctx.redirect_stdout(capturado):
        _mostrar_recusa_de_exemplo()
    texto = capturado.getvalue()
    try:
        texto.encode("cp1252")
        print("  ok    saida da recusa cabe em cp1252 (%d chars)" % len(texto))
    except UnicodeEncodeError as e:
        falhas += 1
        print("  FALHA saida da recusa NAO cabe em cp1252: %s" % e)
    casos.append(("cp1252", b"", False))  # conta no total

    print("")
    # ⛔ O denominador era `len(casos)` e NAO contava os pinos da isencao --
    #    4 pinos rodavam, podiam falhar e reprovar a suite, e o relatorio
    #    continuaria dizendo "15 de 15". Contagem parada esconde guarda parada.
    total = len(casos) + len(pinos_isencao)
    print("pinos: %d de %d passaram" % (total - falhas, total))
    return 1 if falhas else 0


def _mostrar_recusa_de_exemplo():
    """Imprime o bloco de recusa completo, sem tocar em git. So' para o pino."""
    reprovados = [("livro_disfarcado.md", examinar("x", b"O mercado " * 40000))]
    print("=" * 74)
    print("*** COMMIT RECUSADO -- %d arquivo(s) reprovado(s)" % len(reprovados))
    print("=" * 74)
    for caminho, motivos in reprovados:
        print("  %s" % caminho)
        for m in motivos:
            print("      - %s" % m)
    print("O que fazer:")
    print("  1. Se NAO deveria ir para a nuvem:  git restore --staged <arquivo>")
    print("  2. Se for segredo: REVOGUE a credencial.")
    print("  3. Escape explicito:  git commit --no-verify")


if __name__ == "__main__":
    if "--autoteste" in sys.argv:
        sys.exit(_autoteste())
    sys.exit(verificar_o_commit())
