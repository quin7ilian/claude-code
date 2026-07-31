#!/usr/bin/env bash
# Install this repository's global Claude Code guidance, skills, agents, and MCP configuration.
#
# Idempotent: re-running is always safe and produces the same result. Repository-owned files are
# symlinked into place so they stay version-controlled; foreign files and symlinks are never
# replaced (move an existing ~/.claude/CLAUDE.md aside before the first run — see README.md).
#
# Prereqs:
#   - claude (Claude Code) installed and logged in
#   - the OS python3 (all scripts are pure stdlib — no venv, no extra deps)
#   - HINDSIGHT_API_URL / HINDSIGHT_API_KEY / HINDSIGHT_BANK_ID in ~/.claude/.env (see .env.example)
#   - OBSIDIAN_MCP_URL / OBSIDIAN_API_KEY in ~/.claude/.env for the vault workflows
#   - codex logged in via ChatGPT (codex login status) — for the review gate and codex skills
set -euo pipefail

REPO="$(cd "$(dirname "$0")" && pwd -P)"
# The same repository as seen through the other home prefix (/home/... vs /var/home/..., which
# atomic distros bind together). Links recorded under either prefix are repository-owned.
case "$REPO" in
  /var/home/*) REPO_ALT="${REPO#/var}" ;;
  /home/*)     REPO_ALT="/var$REPO" ;;
  *)           REPO_ALT="$REPO" ;;
esac
CLAUDE_HOME="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
BIN="$HOME/.local/bin"
CC_ENV="${CC_ENV:-$CLAUDE_HOME/.env}"

# Source the env file (only the keys this installer needs). Already-exported values win.
if [ -f "$CC_ENV" ]; then
  while IFS= read -r line || [ -n "$line" ]; do
    line="${line#"${line%%[![:space:]]*}"}"          # ltrim
    case "$line" in ''|\#*) continue ;; esac
    line="${line#export }"
    case "$line" in HINDSIGHT_*=*|OBSIDIAN_*=*) ;; *) continue ;; esac
    k="${line%%=*}"; v="${line#*=}"
    case "$v" in                                      # quote-/comment-tolerant
      \"*) v="${v#\"}"; v="${v%%\"*}" ;;
      \'*) v="${v#\'}"; v="${v%%\'*}" ;;
      *)   v="${v%% #*}" ;;
    esac
    v="$(printf '%s' "$v" | sed -E 's/^[[:space:]]*//; s/[[:space:]]*$//')"
    [ -n "$(eval "printf '%s' \"\${$k:-}\"")" ] || export "$k=$v"
  done < "$CC_ENV"
fi

mkdir -p "$CLAUDE_HOME/skills" "$CLAUDE_HOME/agents" "$CLAUDE_HOME/hooks" "$BIN"

link_owned_path() {
  source_path="$1"
  target_path="$2"

  if [ -L "$target_path" ]; then
    current_source="$(readlink "$target_path")"
    if [ "$current_source" != "$source_path" ] \
        && [[ "$current_source" != "$REPO"/* ]] && [[ "$current_source" != "$REPO_ALT"/* ]]; then
      echo "ERROR: refusing to replace foreign symlink: $target_path -> $current_source" >&2
      return 1
    fi
  elif [ -e "$target_path" ]; then
    echo "ERROR: refusing to replace existing path: $target_path" >&2
    return 1
  fi

  ln -sfn "$source_path" "$target_path"
  echo "  $target_path -> $source_path"
}

echo "Pruning retired repository-owned links"
# Remove only symlinks that point into this repository and no longer resolve (renamed or
# removed components). Never touch regular paths or symlinks owned by another setup.
prune_dangling() {
  for installed_path in "$@"; do
    [ -L "$installed_path" ] || continue
    installed_source="$(readlink "$installed_path")"
    case "$installed_source" in
      "$REPO"/*|"$REPO_ALT"/*)
        if [ ! -e "$installed_source" ]; then
          rm -f -- "$installed_path"
          echo "  pruned: $installed_path"
        fi
        ;;
    esac
  done
}
prune_dangling "$CLAUDE_HOME/SYSTEM.md" "$CLAUDE_HOME"/skills/* "$CLAUDE_HOME"/agents/* \
  "$CLAUDE_HOME"/hooks/* "$BIN"/*

echo "Installing global Claude Code guidance"
link_owned_path "$REPO/dot-claude/CLAUDE.md" "$CLAUDE_HOME/CLAUDE.md"

echo "Installing skills"
for skill_path in "$REPO"/dot-claude/skills/*; do
  [ -d "$skill_path" ] || continue
  link_owned_path "$skill_path" "$CLAUDE_HOME/skills/$(basename "$skill_path")"
done

echo "Installing agents"
for agent_path in "$REPO"/dot-claude/agents/*.md; do
  [ -f "$agent_path" ] || continue
  link_owned_path "$agent_path" "$CLAUDE_HOME/agents/$(basename "$agent_path")"
done

echo "Installing bin scripts"
link_owned_path "$REPO/bin/codex-review" "$BIN/codex-review"
command -v codex-review >/dev/null 2>&1 || \
  echo "WARN: $BIN is not on PATH — add it so the review gate can run." >&2
command -v codex >/dev/null 2>&1 || \
  echo "WARN: codex is not on PATH; install and log in the Codex CLI before using the review gate or codex skills." >&2

echo "Configuring Hindsight MCP"
if [ -z "${HINDSIGHT_API_KEY:-}" ] || [ -z "${HINDSIGHT_API_URL:-}" ] || [ -z "${HINDSIGHT_BANK_ID:-}" ]; then
  echo "  SKIP: HINDSIGHT_API_URL / HINDSIGHT_API_KEY / HINDSIGHT_BANK_ID not all set (see $CC_ENV, .env.example). Then re-run."
else
  url="${HINDSIGHT_API_URL%/}/mcp"
  # --scope user → available in every project. X-Bank-Id pins the connection to the bank;
  # without it the server falls back to its default bank and recall silently returns nothing.
  # Output redirected so the bearer token is never echoed.
  claude mcp remove --scope user hindsight >/dev/null 2>&1 || true
  if claude mcp add --scope user --transport http hindsight "$url" \
       --header "Authorization: Bearer $HINDSIGHT_API_KEY" \
       --header "X-Bank-Id: $HINDSIGHT_BANK_ID" >/dev/null 2>&1; then
    echo "  registered hindsight (user scope) -> $url (bank: $HINDSIGHT_BANK_ID)"
  else
    echo "  WARN: 'claude mcp add' failed for hindsight — check 'claude mcp list'." >&2
  fi
fi

echo "Configuring Obsidian MCP"
if [ -z "${OBSIDIAN_MCP_URL:-}" ] || [ -z "${OBSIDIAN_API_KEY:-}" ]; then
  echo "  SKIP: OBSIDIAN_MCP_URL / OBSIDIAN_API_KEY not set (see $CC_ENV, .env.example). Then re-run."
else
  claude mcp remove --scope user obsidian >/dev/null 2>&1 || true
  if claude mcp add --scope user --transport http obsidian "$OBSIDIAN_MCP_URL" \
       --header "Authorization: Bearer $OBSIDIAN_API_KEY" >/dev/null 2>&1; then
    echo "  registered obsidian (user scope) -> $OBSIDIAN_MCP_URL"
  else
    echo "  WARN: 'claude mcp add' failed for obsidian — check 'claude mcp list'." >&2
  fi
fi

echo "Configuring session hooks (retention, memory primer, repository instructions)"
link_owned_path "$REPO/scripts/retain_hindsight.py" "$CLAUDE_HOME/hooks/retain_hindsight.py"
link_owned_path "$REPO/scripts/prime_hindsight.py" "$CLAUDE_HOME/hooks/prime_hindsight.py"
link_owned_path "$REPO/scripts/inject_repo_instructions.py" \
  "$CLAUDE_HOME/hooks/inject_repo_instructions.py"
link_owned_path "$REPO/scripts/gate_repo_instructions.py" \
  "$CLAUDE_HOME/hooks/gate_repo_instructions.py"
python3 "$REPO/scripts/configure_settings.py" \
  --settings "$CLAUDE_HOME/settings.json" \
  --python "$(command -v python3)" \
  --script "$CLAUDE_HOME/hooks/retain_hindsight.py" \
  --primer-script "$CLAUDE_HOME/hooks/prime_hindsight.py" \
  --instructions-script "$CLAUDE_HOME/hooks/inject_repo_instructions.py" \
  --gate-script "$CLAUDE_HOME/hooks/gate_repo_instructions.py" \
  --env-file "$CC_ENV" \
  --state-dir "$CLAUDE_HOME/hindsight-retention"

echo
echo "Installed. Restart Claude Code sessions to pick up CLAUDE.md, the MCP servers, and the Stop hook."
