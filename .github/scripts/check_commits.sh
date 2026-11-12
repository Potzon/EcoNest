#!/usr/bin/env bash
# Revisa CADA commit de un rango de git (los merges se omiten).
#
#   bash .github/scripts/check_commits.sh origin/main..HEAD
#
# Variables opcionales:
#   REQUIRE_ISSUE_REF=true   exige "#NN" en el mensaje (por defecto solo avisa)
#   MAX_FILE_MB=5            tamaño máximo de un archivo añadido o modificado
#
# Termina con código 1 si hay algún error (los avisos no hacen fallar).
set -uo pipefail

RANGE="${1:-}"
[ -n "$RANGE" ] || { echo "Uso: $0 <rango git>   p. ej. origin/main..HEAD" >&2; exit 2; }
REQUIRE_ISSUE_REF="${REQUIRE_ISSUE_REF:-false}"
MAX_FILE_BYTES=$(( ${MAX_FILE_MB:-5} * 1024 * 1024 ))
errors=0
warnings=0
checked=0
report=""

note() { # note error|warning <sha> <mensaje>
  local level="$1" sha="${2:0:7}" msg="$3"
  if [ "$level" = error ]; then errors=$((errors + 1)); else warnings=$((warnings + 1)); fi
  report+="| $level | \`$sha\` | ${msg//|/\\|} |"$'\n'
  if [ -n "${GITHUB_ACTIONS:-}" ]; then
    msg="${msg//'%'/%25}"
    echo "::$level title=commit $sha::$msg"
  else
    echo "  [$level] $sha: $msg"
  fi
}

# Archivos que nunca deben entrar en el repositorio (secretos, pesos, datos, cachés).
# OJO: .env.example y config.example.yaml SÍ están permitidos.
is_forbidden() {
  case "$1" in
    .env | */.env | config.yaml | */config.yaml) return 0 ;;
    *.pt | *.pth | *.db | *.sqlite | *.sqlite3 | *.pyc) return 0 ;;
    __pycache__/* | */__pycache__/* | .venv/* | */.venv/*) return 0 ;;
    data/* | backend/screenshots/*) return 0 ;;
  esac
  return 1
}

while read -r sha; do
  checked=$((checked + 1))
  subject=$(git log -1 --format=%s "$sha")
  message=$(git log -1 --format=%B "$sha")

  # --- mensaje
  case "$subject" in
    fixup!* | squash!* | amend!*) note error "$sha" "commit de tipo fixup/squash: fusiónalo antes de integrar ($subject)" ;;
  esac
  if [ "${#subject}" -gt 72 ]; then
    note warning "$sha" "el título tiene ${#subject} caracteres (recomendado: máx. 72)"
  fi
  if ! grep -Eq '#[0-9]+' <<<"$message"; then
    if [ "$REQUIRE_ISSUE_REF" = true ]; then
      note error "$sha" "no referencia ninguna issue (p. ej. 'Closes #12'): $subject"
    else
      note warning "$sha" "no referencia ninguna issue (p. ej. 'Closes #12'): $subject"
    fi
  fi

  # --- archivos añadidos o modificados EN ESE commit (un secreto añadido y borrado
  #     después sigue en el historial, por eso se mira commit a commit)
  while IFS=$'\t' read -r meta path; do
    [ -n "$path" ] || continue
    if is_forbidden "$path"; then
      note error "$sha" "no debe versionarse: $path"
    fi
    blob=$(awk '{print $4}' <<<"$meta")
    size=$(git cat-file -s "$blob" 2>/dev/null || echo 0)
    if [ "$size" -gt "$MAX_FILE_BYTES" ]; then
      mb=$(awk -v s="$size" 'BEGIN { printf "%.1f", s / 1048576 }')
      note error "$sha" "archivo de $mb MB (máx. ${MAX_FILE_MB:-5} MB): $path"
    fi
  done < <(git -c core.quotePath=false diff-tree --root --no-commit-id -r --diff-filter=AM "$sha")
done < <(git rev-list --reverse --no-merges "$RANGE")

echo "Revisados $checked commit(s) en '$RANGE': $errors error(es), $warnings aviso(s)."

if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
  {
    echo "### Revisión de commits (\`$RANGE\`)"
    echo
    echo "$checked commit(s) revisados · **$errors** error(es) · **$warnings** aviso(s)"
    if [ -n "$report" ]; then
      echo
      echo "| Nivel | Commit | Detalle |"
      echo "|---|---|---|"
      printf '%s' "$report"
    fi
  } >> "$GITHUB_STEP_SUMMARY"
fi

[ "$errors" -eq 0 ]
