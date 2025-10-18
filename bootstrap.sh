#!/usr/bin/env bash
set -euo pipefail

COMPOSE="${COMPOSE:-docker compose}"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

# Default ports for health checks (override via .env if you like)
WEAVIATE_HOST_PORT="${WEAVIATE_HOST_PORT:-8080}"
EMBEDDING_HOST_PORT="${EMBEDDING_HOST_PORT:-8000}"
SEARCH_HOST_PORT="${SEARCH_HOST_PORT:-8888}"

usage() {
  cat <<'EOF'
Usage: ./bootstrap.sh {build|setup|load|etl} [options]

Commands
  build          Build Docker images (etl by default, or all with --all)
  setup          Bring up services, then run full "load" (schema + CSV + vectors + sanity search)
  load           Run only loader stages (expects outputs in data/outputs/*)
  etl --steps    Run unified pipeline steps selectively

Examples
  ./bootstrap.sh build
  ./bootstrap.sh build --all
  ./bootstrap.sh setup
  ./bootstrap.sh load
  ./bootstrap.sh etl --steps clean,split,parse,join,embed
  ./bootstrap.sh etl --steps load
Notes
  - Steps: clean, split, parse, join, embed, load
  - parse and join are coupled; including either enables the join stage.
  - Set ETL_RUNTIME_PIP=1 to pip-install etl/requirements.txt at runtime before pipeline.
    Useful if you don't want to rebuild the image just to add torch, etc.
EOF
}

wait_for_service() {
  local name="$1"; local url="$2"; local max_wait="${3:-300}"
  echo "⏳ Waiting for $name at $url (timeout ${max_wait}s)…"
  local start; start="$(date +%s)"
  while true; do
    if curl -fsSL "$url" >/dev/null 2>&1; then
      echo "✅ $name is ready"
      return 0
    fi
    local now; now="$(date +%s)"
    if (( now - start > max_wait )); then
      echo "❌ Timeout waiting for $name ($url)" >&2
      return 1
    fi
    sleep 2
  done
}

# ---------- Core runners ----------

run_pipeline_with_flags() {
  # Accepts pipeline flag array via "$@"
  # If ETL_RUNTIME_PIP=1, install requirements at runtime before executing pipeline
  if [[ "${ETL_RUNTIME_PIP:-0}" == "1" ]]; then
    echo "🧩 Runtime pip install (etl/requirements.txt) enabled (ETL_RUNTIME_PIP=1)."
    $COMPOSE run --no-deps --rm etl bash -lc       "pip install --no-cache-dir -r etl/requirements.txt --extra-index-url https://download.pytorch.org/whl/cpu &&        python etl/app/pipeline.py $*"
  else
    $COMPOSE run --no-deps --rm etl python etl/app/pipeline.py "$@"
  fi
}

cmd_build() {
  local build_all=0
  if [[ "${1:-}" == "--all" ]]; then build_all=1; fi

  if (( build_all )); then
    echo "🔨 Building all services…"
    $COMPOSE build
  else
    echo "🔨 Building etl service…"
    $COMPOSE build etl
  fi
  echo "✅ build done."
}

cmd_setup() {
  echo "🚀 Bringing up services…"
  $COMPOSE up -d

  # Optional readiness waits (non-fatal if they time out; loader will wait again)
  wait_for_service "Weaviate"  "http://localhost:${WEAVIATE_HOST_PORT}/v1/.well-known/ready" 240 || true
  wait_for_service "Embedding" "http://localhost:${EMBEDDING_HOST_PORT}/health" 120 || true
  wait_for_service "Search"    "http://localhost:${SEARCH_HOST_PORT}/health" 120 || true

  # Then run loader (schema + CSV + vectors + sanity search)
  cmd_load
}

cmd_load() {
  echo "📦 Running loader (schema + CSV insert + vector insert + sanity search)…"
  # When loading, we DO want dependencies alive, so no --no-deps here.
  if [[ "${ETL_RUNTIME_PIP:-0}" == "1" ]]; then
    $COMPOSE run --rm etl bash -lc       "pip install --no-cache-dir -r etl/requirements.txt --extra-index-url https://download.pytorch.org/whl/cpu &&        python etl/app/pipeline.py --skip-clean --skip-split --skip-join --skip-embed"
  else
    $COMPOSE run --rm etl python etl/app/pipeline.py --skip-clean --skip-split --skip-join --skip-embed
  fi
  echo "✅ load done."
}

cmd_etl() {
  # Syntax: ./bootstrap.sh etl --steps clean,split,parse,join,embed[,load]
  local steps_csv=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --steps) steps_csv="$2"; shift 2;;
      *) echo "Unknown option for etl: $1"; usage; exit 1;;
    esac
  done

  if [[ -z "$steps_csv" ]]; then
    echo "Missing --steps <csv>"
    usage
    exit 1
  fi

  IFS=',' read -r -a steps <<< "$steps_csv"
  has() { local x; for x in "${steps[@]}"; do [[ "$x" == "$1" ]] && return 0; done; return 1; }

  # Translate desired steps → pipeline skip flags
  flags=()
  has clean  || flags+=(--skip-clean)
  has split  || flags+=(--skip-split)
  if ! has parse && ! has join; then
    flags+=(--skip-join)
  fi
  has embed  || flags+=(--skip-embed)
  has load   || flags+=(--skip-load)

  echo "📦 ETL steps: ${steps_csv}"

  # If 'load' is requested, ensure services up and use dependencies
  if has load; then
    echo "🔌 Ensuring services are up for load step…"
    $COMPOSE up -d || true
    wait_for_service "Weaviate"  "http://localhost:${WEAVIATE_HOST_PORT}/v1/.well-known/ready" 240 || true
    wait_for_service "Embedding" "http://localhost:${EMBEDDING_HOST_PORT}/health" 120 || true
    wait_for_service "Search"    "http://localhost:${SEARCH_HOST_PORT}/health" 120 || true

    # Now run the full set including load (no --no-deps)
    if [[ "${ETL_RUNTIME_PIP:-0}" == "1" ]]; then
      $COMPOSE run --rm etl bash -lc         "pip install --no-cache-dir -r etl/requirements.txt --extra-index-url https://download.pytorch.org/whl/cpu &&          python etl/app/pipeline.py ${flags[*]}"
    else
      $COMPOSE run --rm etl python etl/app/pipeline.py "${flags[@]}"
    fi
  else
    # Non-load steps don't need service dependencies
    run_pipeline_with_flags "${flags[@]}"
  fi

  echo "✅ etl --steps completed."
}

main() {
  local action="${1:-}"; shift || true
  case "$action" in
    build) cmd_build "$@" ;;
    setup) cmd_setup ;;
    load)  cmd_load ;;
    etl)   cmd_etl "$@" ;;
    ""|-h|--help|help) usage ;;
    *) echo "Unknown action: $action"; usage; exit 1 ;;
  esac
}

main "$@"
