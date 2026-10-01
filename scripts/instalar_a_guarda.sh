#!/bin/sh
# ============================================================================
# Instala a GUARDA DE FRONTEIRA como gancho pre-commit.
#
# ⛔ GANCHO NAO E' VERSIONADO. Ele vive em .git/hooks/, que NAO viaja no clone.
#    Em maquina nova, ou depois de um `git clone`, RODE ISTO DE NOVO.
#    O gancho se perde; o script fica no repo. Por isso o instalador existe.
#
# ⚠️ 24/09/2026 -- a 1a versao resolvia o caminho a partir de `Documents/` e
#    por isso instalava NADA quando rodada de dentro de um clone. O teste
#    ponta-a-ponta passou verde justamente porque nao instalou nada. Agora ele
#    instala no repo em que E' EXECUTADO, e RECLAMA se nao achar a guarda.
#
# Uso:  sh scripts/instalar_a_guarda.sh        (de dentro do repo)
# ============================================================================
set -e

repo="$(git rev-parse --show-toplevel 2>/dev/null)" || {
    echo "ERRO: nao estou dentro de um repositorio git."
    exit 1
}

# A guarda mora em lugares diferentes nos dois repos. Procurar, nao supor.
guarda=""
for candidato in "scripts/guarda_de_fronteira.py" "tools/guarda_de_fronteira.py"; do
    if [ -f "$repo/$candidato" ]; then
        guarda="$candidato"
        break
    fi
done

if [ -z "$guarda" ]; then
    echo "ERRO: nao achei guarda_de_fronteira.py em scripts/ nem em tools/."
    echo "      Sem a guarda, instalar o gancho seria instalar um gancho vazio."
    exit 1
fi

gancho="$repo/.git/hooks/pre-commit"
if [ -f "$gancho" ]; then
    cp "$gancho" "$gancho.anterior"
    echo "aviso: pre-commit anterior salvo em pre-commit.anterior"
fi

# O gancho ECOA o codigo de saida real -- nunca confiar em sumario.
{
    echo '#!/bin/sh'
    echo '# Gerado por instalar_a_guarda.sh -- nao edite aqui.'
    echo "python \"\$(git rev-parse --show-toplevel)/$guarda\""
    echo 'codigo=$?'
    echo 'if [ $codigo -ne 0 ]; then'
    echo '  echo "guarda de fronteira: RECUSOU (saida=$codigo). Commit abortado."'
    echo '  exit $codigo'
    echo 'fi'
    echo 'exit 0'
} > "$gancho"
chmod +x "$gancho"

echo "ok: gancho instalado em $repo"
echo "    guarda: $guarda"
echo ""
echo "Escape explicito, se o dono decidir:  git commit --no-verify"
