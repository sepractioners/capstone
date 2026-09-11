---
name: repo-validation
description: Clone a repository to a fresh folder and validate all README instructions end-to-end, including running setup/installation commands and testing if agents (like query_agent, extraction_agent) are actually working. Use this whenever you need to verify that a project's documented setup and build steps work correctly in a clean environment, or when you want to test agent functionality against the documented instructions. Especially useful for QA, onboarding verification, or continuous validation of documentation accuracy.
compatibility: Requires git, bash/powershell, Python environment, and ability to execute shell commands
---

# Repository Validation Skill

This skill automates the process of cloning a repository and validating that all documentation instructions actually work when followed in a fresh environment. It's designed to catch documentation drift, missing setup steps, and broken agent functionality.

## When to Use This Skill

- **Documentation QA**: Verify README instructions work before shipping
- **Onboarding validation**: Test that new team members can follow the setup guide
- **Continuous validation**: Periodically check that documented steps still work
- **Agent testing**: Confirm agents (query_agent, extraction_agent) function as documented
- **Environment verification**: Ensure instructions work on different systems/configurations

## Workflow Overview

1. **Auto-detect repository** — Find the current git repo's remote URL
2. **Confirm with user** — Show detected URL and clone target folder
3. **Clone to new folder** — Create isolated test environment
4. **Analyze README** — Extract sections, check structure and clarity
5. **Extract commands** — Parse setup, install, build, deploy steps from docs
6. **Execute commands** — Run extracted commands in the cloned folder
7. **Test agents** — Verify query_agent, extraction_agent, or other agents work
8. **Generate report** — Create detailed markdown validation report with findings

## Step-by-Step Process

### Step 1: Get Repository URL and Confirm

First, identify the current git repository and get its remote URL:

```bash
git config --get remote.origin.url
```

Show the user:
- Detected repository URL
- Proposed clone location (e.g., `./repo-validation-<timestamp>/`)
- Ask for confirmation before proceeding
- Ask if there are any specific test scenarios to run (query_agent benchmark, extraction workflows, etc.)

**Edge case questions to ask the user:**
- Should we validate a specific branch? (default: main/master)
- Any authentication needed? (SSH key, token, etc.)
- Should we skip specific setup steps? (e.g., database init, external service setup)
- Are there specific agent test scenarios you want to prioritize?
- Should we use a Python virtual environment? (recommended: yes)
- Any timeout limits for long-running commands?

### Step 2: Clone Repository

Clone the repository to the new folder:

```bash
git clone --depth 1 <repo-url> <target-folder>
cd <target-folder>
```

Verify clone succeeded and capture git info:
- Commit hash
- Branch
- Remote URL confirmed

### Step 3: Parse and Validate README

Read the README.md file and:

1. **Structure validation**
   - Check for sections: Setup, Installation, Usage, Running Tests, etc.
   - Verify section headers exist and use consistent formatting
   - Look for code blocks and command examples

2. **Clarity check**
   - Look for incomplete sections (e.g., "TODO", "FIXME", "coming soon")
   - Check for outdated references (old version numbers, deprecated tools)
   - Identify ambiguous or unclear instructions
   - Flag missing prerequisites (Node version, Python version, system dependencies)

3. **Extract command blocks**
   - Find all bash/shell code blocks
   - Identify setup, install, build, test, run commands
   - Categorize by purpose (setup, dependencies, configuration, agent-specific)

### Step 4: Execute Setup Commands

For each extracted command block:

1. **Pre-execution checks**
   - Display the command before running
   - Check prerequisites (Python version, git, required tools)
   - Verify system has ~10GB disk space available

2. **Execute with isolation**
   - Run setup script appropriate for OS (setup-windows.ps1, setup-mac.sh, setup-linux.sh)
   - Capture stdout, stderr, exit code
   - Record execution time
   - Watch for interactive prompts (e.g., "Edit .env? Y/n")
   - Set reasonable timeout (300s for full setup, 60s per agent test)

3. **Handle failures gracefully**
   - Continue to next step if setup fails partially (e.g., Ollama download fails but venv succeeds)
   - Flag failures in report with full error output
   - Suggest potential fixes based on error message (missing Python, network issues, disk space)

### Step 5: Test Agents via CLI

If the repository contains agents (detected by checking for `agents/query_agent/`, `agents/extraction_agent/`, etc.):

1. **Query Agent Testing** (if present)
   - Run T1 scenario (portfolio census): `bash scripts/agent.sh ask "How many contracts do we have, by lifecycle status?"`
   - Verify response structure: `{answer, confidence, citations, grounded}`
   - Test 2-3 additional T-series questions from different templates:
     - **T1** (portfolio census): "How many contracts do we have?"
     - **T2** (filtered roster): "List all active vendor agreements"
     - **T3** (clause presence): "Which contracts mention liability insurance?"
     - **T7** (synthesis): "What payment obligations do we have across all contracts?"
   - For each test:
     - Capture full JSON response
     - Verify `confidence` is numeric (0-1)
     - Verify `citations` reference valid contract_id or "portfolio"
     - Verify `answer` is non-empty and addresses the question
     - Verify `grounded=true` (never hallucinating)

2. **Extraction Agent Testing** (if present)
   - Check agent code exists at `agents/extraction_agent/agent.py`
   - Verify RAG index building is documented: `build_rag_index.py`
   - Note: full extraction testing requires real PDFs; skip if no CUAD download

3. **Agent Configuration** (if present)
   - Verify `.env` file is properly configured (check .env.example)
   - Confirm LLM provider matches README (default: ollama for query_agent)
   - Check critical environment variables are set (QUERY_PLAN_TOOLS, etc.)

### Step 6: Generate Validation Report

Create a comprehensive markdown report with:

#### Report Structure

```markdown
# Repository Validation Report

**Repository**: [URL]
**Clone Location**: [path]
**Date**: [timestamp]
**Commit**: [hash]
**Branch**: [branch-name]

## Executive Summary
- ✅/❌ Overall status (pass/fail)
- Number of issues found
- Critical vs. warning level findings

## 1. README Structure Analysis
### Section Completeness
- [ ] Setup / Installation section exists
- [ ] Usage / Getting Started section exists
- [ ] Dependencies / Requirements section exists
- [ ] Running Tests section exists
- [ ] Configuration section exists
- [ ] Contributing section exists

### Clarity Issues
- List any incomplete sections, TODOs, or ambiguous instructions
- Note missing version requirements

### Command Extraction
- List of extracted command blocks
- Categorized by purpose (setup, build, test, etc.)

## 2. Setup and Installation Results

### Environment
- OS / Platform: [detected]
- Python version: [if applicable]
- Node version: [if applicable]
- Other relevant tool versions

### Command Execution Results

For each command:
```
**Command**: [the command]
**Status**: ✅ PASS / ⚠️ WARNING / ❌ FAIL
**Output**: [stdout excerpt]
**Error**: [stderr if any]
**Duration**: [seconds]
**Notes**: [any context]
```

### Prerequisites Check
- List missing dependencies
- Suggest installation commands

## 3. Agent Testing Results

### Query Agent (CLI Tests)

**T1 Portfolio Census**
- Command: `bash scripts/agent.sh ask "How many contracts do we have, by lifecycle status?"`
- Status: ✅ PASS / ❌ FAIL
- Response structure: Valid JSON with answer, citations, confidence, grounded
- Expected answer: "40 contracts total: active 24, approved 15, in_review 1" (or similar)
- Confidence: 0.9+ (deterministic, high confidence)
- Grounded: true (never hallucinating)

**T2 Filtered Roster**
- Command: `bash scripts/agent.sh ask "List all active vendor agreements"`
- Status: ✅ PASS / ❌ FAIL
- Response: Names of contracts, count correct
- Confidence: 0.8+ (deterministic)

**T3 Clause Presence**
- Command: `bash scripts/agent.sh ask "Which contracts mention liability insurance?"`
- Status: ✅ PASS / ❌ FAIL
- Response: Contract names matching the clause, count accurate
- Confidence: 0.9+ (exact match search)

**T7 Synthesis (Clause Evidence)**
- Command: `bash scripts/agent.sh ask "What payment obligations do we have?"`
- Status: ✅ PASS / ❌ FAIL / ⚠️ WARNING (timeout/degraded)
- Response: Synthesized answer with citations to clauses
- Confidence: 0.6-0.8 (synthesis is harder than enumeration)
- Coverage: States if sampling vs reading all contracts

### Extraction Agent
- ✅/❌ Agent code exists at `agents/extraction_agent/agent.py`
- ✅/❌ RAG index building documented
- Note: Full extraction testing requires real CUAD PDFs (optional)

### Configuration
- ✅/❌ .env properly configured (copy from .env.example)
- ✅/❌ LLM provider accessible (check QUERY_PLAN_TOOLS, default models)
- ✅/❌ Critical env vars set (QUERY_PLAN_TOOLS, model preferences)

## 4. Issues and Recommendations

### Critical Issues (blocks setup)
- [Issue 1: description]
  - Recommendation: [fix]
- [Issue 2: description]
  - Recommendation: [fix]

### Warnings (non-blocking)
- [Warning 1: description]
  - Suggestion: [improvement]

### Documentation Improvements
- [Suggestion for README clarity]
- [Missing prerequisite info]

## 5. Validation Summary

| Category | Status | Details |
|----------|--------|---------|
| README Structure | ✅/❌ | X issues found |
| Setup Commands | ✅/❌ | X of Y passed |
| Agent Functionality | ✅/❌ | All agents working / X issues |
| Prerequisites | ✅/❌ | All present / X missing |
| Overall | ✅/❌ | Ready for release / Needs work |

## 6. Next Steps

- If all pass: README is ready for distribution
- If failures: Apply recommended fixes before release
- If warnings: Address before next release cycle

**Generated by**: repo-validation skill
**Duration**: [total time]
```

## Implementation Notes

### When Running Setup Commands

- Use platform-appropriate setup script (setup-windows.ps1, setup-mac.sh, setup-linux.sh)
- Activate venv before running Python-based commands
- If setup takes >5 minutes, note progress and expected time remaining
- If a command fails, attempt to diagnose:
  - Missing Python 3.12+? Note version requirement
  - Missing uv? Suggest installation
  - Disk space? Check available space
  - Network? Check internet connection for downloads (CUAD, Ollama)
  - Permission error? Suggest chmod or run-as-admin
  - Database locked? Check for stale processes
- Best-effort: Some parts can fail gracefully (e.g., Ollama download) and setup continues

### When Testing Agents

- Query Agent: Run with a timeout (default: 60 seconds per question, 120s total for all tests)
- If agent times out, note as a warning (may indicate slow model or network)
- If agent errors, capture the full error and stack trace
- Test coverage: At least one question from each major template category (T1-T9)
- Expected results:
  - T1 (census): 40 contracts, exact counts
  - T2 (roster): Contract names and counts
  - T3 (clause presence): Matching contract names
  - T7 (synthesis): Multi-sentence answer with coverage statement
- Validate JSON schema: answer, confidence (0-1), citations (with contract_id), grounded (true/false)
- Confidence levels: T1-T3 should be 0.8+; T7 synthesis 0.6-0.8

### Error Handling

- **Clone fails**: Check network, authentication, URL validity
- **Command not found**: Offer installation guidance
- **Permission denied**: Suggest chmod or run-as-admin
- **Timeout**: Offer to increase timeout or skip that step
- **Agent fails**: Capture full error for debugging

### Report Output

- Save markdown report to: `./repo-validation-report-<timestamp>.md`
- Display key findings in the conversation
- Highlight any critical issues that need fixing
- Provide actionable recommendations for each issue

## Configuration

The skill automatically detects:
- Current git repository and remote URL
- Project type (Python? Node? Polyglot?)
- Presence of agents and test frameworks
- Environment (Windows/Mac/Linux)

The user can customize:
- Clone target folder location
- Which branch to test
- Which commands to skip
- Agent test scenarios to run
- Timeout values
