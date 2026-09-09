#!/usr/bin/env bash
# Bootstrap GitHub labels + tracking issues for ADR-0001/0002/0003.
#
# Idempotent-ish: labels use --force; issues are skipped if an open/closed issue
# with the exact same title already exists. Safe to re-run.
#
# Requires: gh (authenticated), run from the repo root.
#   gh auth status
#   bash scripts/gh-bootstrap-tracking-issues.sh
#
# Dry run (print what would happen, create nothing):
#   DRY_RUN=1 bash scripts/gh-bootstrap-tracking-issues.sh
set -euo pipefail

DRY_RUN="${DRY_RUN:-0}"
run() { if [ "$DRY_RUN" = "1" ]; then echo "DRY: $*"; else "$@"; fi; }

command -v gh >/dev/null || { echo "gh not found on PATH"; exit 1; }
gh auth status >/dev/null 2>&1 || { echo "gh not authenticated - run: gh auth login"; exit 1; }

REPO="$(gh repo view --json nameWithOwner -q .nameWithOwner)"
echo "Repo: $REPO"

# --------------------------------------------------------------------------
# 1. Labels
# --------------------------------------------------------------------------
# name|hex|description
LABELS='
epic|3E4B9E|Tracking issue spanning an ADR
adr-0001|0E8A16|Offline-first data + contract-type catalog
adr-0002|1D76DB|Query-agent review substrate
adr-0003|5319E7|Query-agent stress corpus
decision|D93F0B|Resolves an ADR open question; gates a status change
setup|FBCA04|Setup / install scripts
rag|0052CC|RAG knowledge base / index
query-agent|006B75|Query-agent behaviour / evaluation
synthetic-data|BFD4F4|Generator / seed_contracts.py
datasets|C2E0C6|Public-dataset ingestion / licensing
eval|FEF2C0|Test harnesses / accuracy metrics
docs|0075CA|Documentation
tests|BFDADC|Automated tests / invariants
blocked|B60205|Waiting on a decision or another issue
'
echo "== Labels =="
while IFS='|' read -r name hex desc; do
  [ -z "$name" ] && continue
  run gh label create "$name" --color "$hex" --description "$desc" --force
done <<< "$LABELS"

# --------------------------------------------------------------------------
# 2. Task issues
# --------------------------------------------------------------------------
# idx|title|labels(comma-sep)|blocked_by(space-sep idx)|epic(1|2|3)
TASKS='
1|Decide catalog format (TOML vs JSONL) and sequencing (minimal fix vs full refactor)|decision,adr-0001||1
2|Create contract_types.toml - schema + initial entries with grounding flags|adr-0001,datasets|1|1
3|Catalog -> RAG contract_profile generator; set knowledge_type correctly for all profiles|adr-0001,rag|2|1
4|Delete SAMPLE_RAG_KNOWLEDGE from seed_database.py; single RAG-seed path|adr-0001,rag|3|1
5|Refactor seed_contracts.py to derive types / clauses / field lists from the catalog|adr-0001,synthetic-data|2|1
6|Switch download_cuad_subset.py from kagglehub to huggingface_hub.snapshot_download (allow_patterns)|adr-0001,datasets||1
7|Make CUAD opt-in (--with-cuad) with interactive category picker + non-interactive fallback|adr-0001,datasets,setup|6|1
8|Rewrite setup-windows.ps1 / setup-linux.sh / setup-mac.sh: no default dataset network; add synthetic-seed step; wire --with-cuad|adr-0001,setup|5 7|1
9|Reconcile or remove tools/setup/main.py|adr-0001,setup|8|1
10|Invariant tests: generator subset of catalog; one profile per type; knowledge_type == contract_profile; eval truth subset of catalog|adr-0001,tests|3 5|1
11|Docs: README, SETUP.md, synthetic_data_loader/README.md, rename kaggle-cuad.md -> datasets.md, update data-lifecycle.md|adr-0001,docs|8|1
12|Clear ADR-0001 open questions; flip Status to Accepted|decision,adr-0001|4 8 9 10 11|1
13|Pin review snapshot parameters (seed string + contract count)|decision,adr-0002||2
14|Snapshot regeneration script -> emits contract-type/lifecycle distribution table + sample-question answers|adr-0002,query-agent,eval|13|2
15|Write docs/query-agent-review-scope.md - claims, reproduce recipe, in/out scope, glossary, sample Q&A|adr-0002,docs|14|2
16|Test: planner emits a contract_type string that misses the facet value (deterministic guard must catch it)|adr-0002,query-agent,tests||2
17|(optional) Query-agent scenario set in platform_testing/|adr-0002,query-agent,eval|13|2
18|Clear ADR-0002 open questions; flip Status to Accepted|decision,adr-0002|15 16|2
19|Resolve ADR-0003 open questions (corpus size, CUAD categories, embedding model, LEDGAR in/out, size budget, eval timing, procurement add-on)|decision,adr-0003||3
20|Define data/stress_corpus/ schema + deterministic synthesis rules for lifecycle_status and contract_value / currency|adr-0003,datasets|19|3
21|Maintainer build script: CUAD master_clauses.csv + ACORD -> normalized JSONL + pre-computed embeddings|adr-0003,datasets|20|3
22|data/stress_corpus/ATTRIBUTION.md + CHANGES per source; add entry to the app licenses page|adr-0003,docs,datasets|21|3
23|Bulk-load step in setup - load the stress corpus as a separate organization/tenant|adr-0003,setup|21|3
24|(optional) ACORD retrieval eval harness (NDCG / recall@k) over search_clauses|adr-0003,eval,query-agent|23|3
25|(optional) Bounded USASpending / OCDS slice for deterministic-tool scale stress (no clause text)|adr-0003,datasets,eval|23|3
26|Clear ADR-0003 open questions; flip Status to Accepted|decision,adr-0003|22 23|3
'

declare -A NUM        # idx -> created issue number
declare -A TITLE      # idx -> title
declare -A LABELS_OF  # idx -> labels
declare -A BLOCKS_OF  # idx -> blocked-by idx list
declare -A EPIC_OF    # idx -> epic (1|2|3)

find_issue() { gh issue list --repo "$REPO" --state all --search "in:title \"$1\"" --json number,title \
  -q ".[] | select(.title == \"$1\") | .number" | head -n1; }

echo "== Task issues =="
while IFS='|' read -r idx title labels blocked epic; do
  idx="$(echo "${idx:-}" | xargs)"; [ -z "$idx" ] && continue
  title="$(echo "$title" | sed 's/^ *//; s/ *$//')"
  labels="$(echo "$labels" | xargs)"
  TITLE[$idx]="$title"; LABELS_OF[$idx]="$labels"; BLOCKS_OF[$idx]="$(echo "$blocked" | xargs)"; EPIC_OF[$idx]="$(echo "$epic" | xargs)"

  existing="$(find_issue "$title" || true)"
  if [ -n "$existing" ]; then
    echo "  skip (exists as #$existing): $title"
    NUM[$idx]="$existing"; continue
  fi
  label_args=(); IFS=',' read -ra L <<< "$labels"; for l in "${L[@]}"; do label_args+=(--label "$l"); done
  body="Task $idx of the ADR implementation plan (docs/implementation-plan.md). Cross-references added in a follow-up pass."
  if [ "$DRY_RUN" = "1" ]; then
    echo "DRY: gh issue create --title \"$title\" ${label_args[*]}"
    NUM[$idx]="DRY-$idx"
  else
    url="$(gh issue create --repo "$REPO" --title "$title" --body "$body" "${label_args[@]}")"
    NUM[$idx]="${url##*/}"
    echo "  created #${NUM[$idx]}: $title"
  fi
done <<< "$TASKS"

# --------------------------------------------------------------------------
# 3. Epics (with checklists linking the task issues)
# --------------------------------------------------------------------------
epic_meta() {
  case "$1" in
    1) echo "[Epic] ADR-0001: offline-first contract data + single type catalog|adr/0001-offline-first-contract-data-and-type-catalog.md|epic,adr-0001|setup-* completes offline with no dataset network call; catalog drives generator + RAG; invariants green; ADR-0001 -> Accepted." ;;
    2) echo "[Epic] ADR-0002: bounded query-agent review substrate|adr/0002-query-agent-evaluation-substrate.md|epic,adr-0002|Pinned snapshot regenerable from a clean clone; docs/query-agent-review-scope.md published; ADR-0002 -> Accepted." ;;
    3) echo "[Epic] ADR-0003: pre-built query-agent stress corpus|adr/0003-query-agent-stress-corpus.md|epic,adr-0003|data/stress_corpus/ artifact + embeddings build via script; bulk-load as separate tenant; per-source attribution; ADR-0003 -> Accepted." ;;
  esac
}

declare -A EPIC_NUM
echo "== Epics =="
for e in 1 2 3; do
  IFS='|' read -r etitle epath elabels edod <<< "$(epic_meta "$e")"
  checklist=""
  for idx in $(echo "${!TITLE[@]}" | tr ' ' '\n' | sort -n); do
    [ "${EPIC_OF[$idx]}" = "$e" ] || continue
    checklist+="- [ ] #${NUM[$idx]} ${TITLE[$idx]}"$'\n'
  done
  body="ADR: docs/${epath}"$'\n\n'"**Definition of done:** ${edod}"$'\n\n'"## Tasks"$'\n'"${checklist}"
  existing="$(find_issue "$etitle" || true)"
  label_args=(); IFS=',' read -ra L <<< "$elabels"; for l in "${L[@]}"; do label_args+=(--label "$l"); done
  if [ -n "$existing" ]; then
    echo "  update epic #$existing"
    run gh issue edit "$existing" --repo "$REPO" --body "$body"
    EPIC_NUM[$e]="$existing"
  elif [ "$DRY_RUN" = "1" ]; then
    echo "DRY: gh issue create --title \"$etitle\" ${label_args[*]}"; EPIC_NUM[$e]="DRY-E$e"
  else
    url="$(gh issue create --repo "$REPO" --title "$etitle" --body "$body" "${label_args[@]}")"
    EPIC_NUM[$e]="${url##*/}"; echo "  created epic #${EPIC_NUM[$e]}: $etitle"
  fi
done

# --------------------------------------------------------------------------
# 4. Cross-reference pass: "Part of #epic" + "Blocked by #..."
# --------------------------------------------------------------------------
echo "== Cross-references =="
for idx in $(echo "${!TITLE[@]}" | tr ' ' '\n' | sort -n); do
  [ "${DRY_RUN}" = "1" ] && { echo "DRY: xref task $idx"; continue; }
  n="${NUM[$idx]}"; e="${EPIC_NUM[${EPIC_OF[$idx]}]}"
  blk=""
  for b in ${BLOCKS_OF[$idx]}; do blk+=" #${NUM[$b]}"; done
  extra="Part of #${e}."
  [ -n "$blk" ] && extra+=$'\n'"Blocked by:${blk}"
  [ -n "$blk" ] && run gh issue edit "$n" --repo "$REPO" --add-label blocked
  base="Task $idx of the ADR implementation plan (docs/implementation-plan.md)."
  run gh issue edit "$n" --repo "$REPO" --body "${base}"$'\n\n'"${extra}"
done

echo "Done."
