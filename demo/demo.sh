#!/usr/bin/env bash
# fbrain demo script — rehearse before recording
# Usage: bash demo/demo.sh
# Record with: asciinema rec demo/icontext-demo.cast --command "bash demo/demo.sh"

set -e

# Colors
GREEN='\033[32m'; CYAN='\033[36m'; DIM='\033[2m'; RESET='\033[0m'; BOLD='\033[1m'
ok()   { echo -e "  ${GREEN}✓${RESET} $1"; }
info() { echo -e "  ${CYAN}→${RESET} $1"; }
hr()   { echo -e "  ${DIM}────────────────────────────────────────────${RESET}"; }
pause() { sleep "${1:-0.8}"; }

clear

# === fbrain init ===
echo ""
hr
echo -e "  ${BOLD}fbrain · init${RESET}"
hr
echo ""
pause 0.4
info "creating vault at ~/context"
pause 0.3
ok "shareable/   internal/   vault/   ready"
pause 0.2
ok "git repo initialised"
pause 0.2
ok "3 skill(s) installed (Claude Code + Cursor)"
pause 0.2
ok "CLAUDE.md updated — skills wired in"
hr
echo ""
echo "  Next:"
echo -e "    ${BOLD}open Claude Code${RESET} and ask:"
echo -e "      ${DIM}\"Populate my fbrain profile\"${RESET}"
echo ""
pause 1.6

# === Claude Code session: populate ===
echo ""
echo -e "  ${DIM}# Claude Code session${RESET}"
echo ""
pause 0.5
echo -e "  ${CYAN}You:${RESET} populate my fbrain profile"
echo ""
pause 1.2
echo -e "  ${GREEN}Claude:${RESET} I'll use the fbrain-populate-profile skill."
pause 0.5
echo ""
printf "    fetching last 90 days of Gmail metadata via MCP..."; pause 1.2; echo -e " ${GREEN}✓${RESET}"
printf "    extracting people, projects, topics..."; pause 1.0; echo -e "          ${GREEN}✓${RESET}"
printf "    validating (need ≥2 messages, drop SaaS senders)..."; pause 0.9; echo -e " ${GREEN}✓${RESET}"
printf "    writing internal/profile/user.md..."; pause 0.4; echo -e "             ${GREEN}✓${RESET}"
printf "    writing shareable/profile/context-card.md..."; pause 0.3; echo -e "    ${GREEN}✓${RESET}"
echo ""
ok "profile ready · 18 relationships · 4 active projects"
echo ""
pause 1.4

# === Fresh session: ask ===
echo ""
echo -e "  ${DIM}# new Claude Code session, the next day${RESET}"
echo ""
pause 0.5
echo -e "  ${CYAN}You:${RESET} what do you know about me?"
echo ""
pause 1.5
echo -e "  ${GREEN}Claude:${RESET} (reading internal/profile/user.md)"
pause 0.6
echo ""
echo "  You're Federico de Ponte — technical founder working on Floom,"
echo "  an AI app platform. Based at floom.dev. Previously built SCAILE"
echo "  (\$600K ARR). Currently focused on the v26 launch."
echo ""
pause 0.4
echo "  Key relationships: Cedrik (co-founder, daily), Marco (investor,"
echo "  weekly), Sara (design lead, weekly)."
echo ""
pause 0.4
echo "  Active threads: Floom launch, f.inc SF program, Rocketlist pipeline."
echo ""
pause 1.0
hr
echo ""
echo -e "  ${DIM}# fbrain — github.com/floomhq/fbrain${RESET}"
echo ""
