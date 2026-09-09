#!/usr/bin/env bash
# Benchmark the query agent across pipeline variants.
#   bash scripts/bench-query-agent.sh B2 "QUERY_INTERPRET=1 QUERY_VERIFY=1 QUERY_DETERMINISTIC_COMPOSE=1"
# Restarts the API with the given env, runs the fixed question set, appends raw
# rows to platform_testing/reports/query_bench.tsv:
#   variant \t q \t wall_s \t llm_calls \t answer
# Score with:  python scripts/bench_score.py
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

VARIANT="${1:?variant label}"
VARENV="${2:-}"
OUT=platform_testing/reports/query_bench.tsv
mkdir -p "$(dirname "$OUT")"
[ -f "$OUT" ] || printf 'variant\tq\twall_s\tllm_calls\tanswer\n' > "$OUT"

QS=(
  "How many contracts do we have, by lifecycle status?"
  "How many active vendor agreements do we have?"
  "List all co-branding agreements"
  "Break down contracts by type"
  "Which contracts mention liability insurance?"
  "What payment obligations do we have across all contracts?"
)

echo "== $VARIANT :: $VARENV =="
bash scripts/run-all.sh --stop >/dev/null 2>&1
# shellcheck disable=SC2086
env $VARENV bash scripts/run-all.sh --no-sync --no-frontend --no-console >/dev/null 2>&1
sleep 2
curl -sk --max-time 5 https://127.0.0.1:8443/health >/dev/null || { echo "API down"; exit 1; }

i=0
for q in "${QS[@]}"; do
  i=$((i+1))
  mark=$(wc -l < .run/api.log)
  start=$(date +%s)
  # shellcheck disable=SC2086
  raw=$(env $VARENV bash scripts/agent.sh ask "$q" 2>/tmp/bench.err || true)
  wall=$(( $(date +%s) - start ))
  err=$(cat /tmp/bench.err)
  calls=$(tail -n +"$((mark+1))" .run/api.log | grep -c "api/chat" || true)
  ans=$(printf '%s %s' "$raw" "$err" | tr '\n\t' '  ' | tr -s ' ')
  printf '%s\t%s\t%s\t%s\t%s\n' "$VARIANT" "$i" "$wall" "$calls" "${ans:0:400}" >> "$OUT"
  echo "  Q$i  ${wall}s  calls=$calls"
done
echo "-> $OUT"
