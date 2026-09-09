#!/usr/bin/env bash
# Benchmark the query agent across pipeline variants.
#   bash scripts/bench-query-agent.sh B2 "QUERY_INTERPRET=1 QUERY_VERIFY=1 QUERY_DETERMINISTIC_COMPOSE=1"
# Restarts the API with the given env, runs the fixed question set, appends to
# platform_testing/reports/query_bench.tsv:
#   variant  q  verdict  wall_s  llm_calls  fail_mode  answer
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

VARIANT="${1:?variant label}"
VARENV="${2:-}"
OUT=platform_testing/reports/query_bench.tsv
mkdir -p "$(dirname "$OUT")"
[ -f "$OUT" ] || printf 'variant\tq\tverdict\twall_s\tllm_calls\tfail_mode\tanswer\n' > "$OUT"

QS=(
  "How many contracts do we have, by lifecycle status?"
  "How many active vendor agreements do we have?"
  "List all co-branding agreements"
  "Break down contracts by type"
  "Which contracts mention liability insurance?"
  "What payment obligations do we have across all contracts?"
)

# verdict = pass when the answer carries the ground-truth fact for that question.
score() { # $1 = q index (1-based), $2 = answer text
  local a="$2"
  case "$1" in
    1) grep -qE '24' <<<"$a" && grep -qE '15' <<<"$a" && grep -qE '(^|[^0-9])1([^0-9]|$)' <<<"$a" ;;
    2) grep -qE '(^|[^0-9])2([^0-9]|$)' <<<"$a" && ! grep -qE '(24|40) (active )?(vendor|contract)' <<<"$a" ;;
    3) grep -qiE '(^|[^0-9])4 (contract|co-?branding)' <<<"$a" ;;
    4) grep -qE '7' <<<"$a" && grep -qE 'distribution' <<<"$a" && grep -qE 'nda[^0-9]*1' <<<"$a" ;;
    5) grep -qE '(^|[^0-9])15([^0-9]|$)' <<<"$a" ;;
    6) grep -qiE 'pay|invoic|obligation' <<<"$a" && [ "${#a}" -gt 60 ] ;;
  esac
}

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
  raw=$(env $VARENV bash scripts/agent.sh ask "$q" 2>/tmp/bench.err)
  wall=$(( $(date +%s) - start ))
  ans=$(printf '%s' "$raw" | tr '\n' ' ' | sed "s/\\\\\"/'/g" | tr -s ' ')
  calls=$(tail -n +"$((mark+1))" .run/api.log | grep -c "api/chat")

  fail=ok
  if grep -qi 'unavailable\|RemoteProtocolError\|Traceback' <<<"$raw $(cat /tmp/bench.err)"; then fail=crash
  elif [ "${#ans}" -lt "$(( ${#q} + 30 ))" ] && grep -qF "$q" <<<"$ans"; then fail=echoed_question
  fi

  if [ "$fail" != ok ]; then verdict=fail
  elif score "$i" "$ans"; then verdict=pass
  else verdict=wrong
  fi

  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$VARIANT" "$i" "$verdict" "$wall" "$calls" "$fail" "${ans:0:220}" >> "$OUT"
  echo "  Q$i  $verdict  ${wall}s  calls=$calls  $fail"
done
echo "-> $OUT"
