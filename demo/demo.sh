#!/usr/bin/env bash
# icontext demo script — rehearse before recording
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

# === icontext sync ===
echo ""
hr
echo -e "  ${BOLD}icontext · sync${RESET}"
hr
echo ""
pause 0.5

info "gmail"
printf "    connecting to fede@example.com..."; pause 0.6; echo -e "          ${GREEN}✓${RESET}"
printf "    scanning 312 messages..."; pause 1.2; echo -e "               ${GREEN}✓${RESET}"
printf "    synthesizing with Gemini..."; pause 2.0; echo -e "            ${GREEN}✓${RESET}"
printf "    writing profile..."; pause 0.4; echo -e "                    ${GREEN}✓${RESET}"
echo ""

info "linkedin"
printf "    reading Profile.pdf..."; pause 0.5; echo -e "                ${GREEN}✓${RESET}"
printf "    synthesizing with Gemini..."; pause 1.5; echo -e "            ${GREEN}✓${RESET}"
printf "    writing profile..."; pause 0.3; echo -e "                    ${GREEN}✓${RESET}"
echo ""

ok "context card ready"
hr
echo -e "  ${GREEN}✓${RESET} done  ~/context/internal/profile/user.md"
echo ""
echo "  Open Claude Code and ask:"
echo '    "What do you know about me?"'
hr
echo ""

pause 1.5

# === Show what Claude now knows ===
echo ""
echo -e "  ${DIM}# Claude Code session${RESET}"
echo ""
pause 0.8
echo -e "  ${CYAN}You:${RESET} what do you know about me?"
echo ""
pause 2.0
echo -e "  ${GREEN}Claude:${RESET} Based on your context profile, here's what I know:"
pause 0.3
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
echo -e "  ${DIM}# icontext — github.com/floomhq/icontext${RESET}"
echo ""
