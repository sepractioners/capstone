#!/usr/bin/env bash
# Benchmark the query agent across pipeline variants.
#   bash scripts/bench-query-agent.sh B2 "QUERY_INTERPRET=1 QUERY_VERIFY=1 QUERY_DETERMINISTIC_COMPOSE=1"
# Restarts the API with the given env, runs the fixed question set, and appends
# rows to platform_testing/reports/query_bench.tsv:
#   variant  q  verdict  wall_s  llm_calls  fail_mode  answer
#
# Assumes: Ollama up, .venv present, .env sets LLM_MODEL. QUERY_PLAN_TOOLS is
# taken from the variant env (default 0).
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

VARIANT="${1:?variant label}"
VARENV="${2:-}"
OUT=platform_testing/reports/query_bench.tsv
mkdir -p "$(dirname "$OUT")"
[ -f "$OUT" ] || echo -e "variant\tq\tverdict\twall_s\tllm_calls\tfail_mode\tanswer" > "$OUT"

# question | expected-regex (verdict = pass if answer matches, and no fail_mode)
QS=(
  "How many contracts do we have, by lifecycle status?|24.*15.*1|1"
  "How many active vendor agreements do we have?|(^|[^0-9])2([^0-9]|$)|2"
  "List all co-branding agreements|(^|[^0-9])4([^0-9]|$)|3"
  "Break down contracts by type|7.*6.*5.*4.*4.*4.*3.*3.*3.*1|4"
  "Which contracts mention liability insurance?|(^|[^0-9])15([^0-9]|$)|5"
  "What payment obligations do we have across all contracts?|pay|6"
)

echo "== $VARIANT :: $VARENV =="
bash scripts/run-all.sh --stop >/dev/null 2>&1
# shellcheck disable=SC2086
env $VARENV bash scripts/run-all.sh --no-sync --no-frontend --no-console >/dev/null 2>&1
sleep 2
curl -sk --max-time 5 https://127.0.0.1:8443/health >/dev/null || { echo "API down"; exit 1; }

for entry in "${QS[@]}"; do
  IFS='|' read -r q rx n <<< "$entry"
  mark=$(wc -l < .run/api.log)
  start=$(date +%s)
  raw=$(env $VARENV bash scripts/agent.sh ask "$q" 2>/tmp/bench.err)
  wall=$(( $(date +%s) - start ))
  ans=$(printf '%s' "$raw" | tr '\n' ' ' | sed 's/\\"/'"'"'/g')
  calls=$(( $(wc -l < .run/api.log) - mark ))
  calls=$(tail -n +"$((mark+1))" .run/api.log | grep -c "api/chat")

  fail=""
  if grep -qi "unavailable\|RemoteProtocolError\|Traceback" <<< "$raw$(cat /tmp/bench.err)"; then fail="crash"; fi
  if [ -z "$fail" ] && [ "$(printf '%s' "$ans" | grep -o "$q" | head -1)" = "$q" ] && [ "${#ans}" -lt "$(( ${#q} + 40 ))" ]; then fail="echoed_question"; fi

  if [ -n "$fail" ]; then verdict="fail"
  elif grep -qiE "$rx" <<< "$ans"; then verdict="pass"
  else verdict="wrong"; fi

  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$VARIANT" "$n" "$verdict" "$wall" "$calls" "${fail:-ok}" "${ans:0:200}" >> "$OUT"
  echo "  Q$n $verdict ${wall}s calls=$calls ${fail:-}"
done
echo "-> $OUT"
