#!/bin/bash
# What a person sees installing the Mac program from a browser download: bash tools/mac/screens.sh <out dir>
# Used by .github/workflows/screens.yml on a GitHub Mac switched to Russian.
set -uo pipefail
out="$1"; mkdir -p "$out"
log() { echo "$*" | tee -a "$out/screens.log"; }
shot() { sleep "${2:-4}"; screencapture -x "$out/$1.png"; log "снимок $1"; }

# A freshly built image when given, else the published one.
dmg="$HOME/Downloads/BookPrice-mac.dmg"
if [ -n "${2:-}" ]; then
  cp "$2" "$dmg"
  log "образ: $2"
else
  url=$(curl -fsSL "https://api.github.com/repos/AlexLion89/book-price/releases?per_page=30" \
    | grep -o '"browser_download_url": *"[^"]*-mac\.dmg"' | head -n 1 | sed 's/.*"\(https[^"]*\)"$/\1/')
  log "образ: $url"
  curl -fsSL -o "$dmg" "$url"
fi
# The mark Safari puts on a download.
xattr -w com.apple.quarantine "0081;$(printf %x "$(date +%s)");Safari;" "$dmg"

open "$dmg"
shot 1-dmg-window 12
ditto "/Volumes/Ценитель/Ценитель.app" "/Applications/Ценитель.app"
xattr -w com.apple.quarantine "0081;$(printf %x "$(date +%s)");Safari;" "/Applications/Ценитель.app"
open "/Volumes/Ценитель/Если не открывается.txt"
shot 1b-readme 6
osascript -e 'quit app "TextEdit"' >/dev/null 2>&1 || true
hdiutil detach "/Volumes/Ценитель" -force -quiet || true

# `open` waits until the warning is answered: let it wait in the background.
open "/Applications/Ценитель.app" &
shot 2-blocked 10
for anchor in "" "?Security" "?General"; do
  open "x-apple.systempreferences:com.apple.settings.PrivacySecurity.extension$anchor"
  shot "3-settings$(echo "$anchor" | tr -d '?')" 6
done

# Scroll down to the button and press it — works only if this runner lets scripts drive other apps' windows; macOS may
# instead wait for a person to allow it, so the attempt gets 90 seconds.
cat > "$out/click.applescript" <<'APPLESCRIPT'
tell application "System Settings" to activate
delay 2
tell application "System Events"
  tell process "System Settings"
    set found to {}
    try
      set found to (every button of entire contents of window 1 whose name contains "открыть")
    end try
    if (count of found) > 0 then
      repeat with b in found
        try
          perform action "AXScrollToVisible" of b
        end try
      end repeat
      delay 1
      do shell script "screencapture -x " & quoted form of (system attribute "PWD") & "/" & "shots/4-open-anyway-visible.png"
      click item 1 of found
      return "нажал: " & (name of item 1 of found)
    else
      return "кнопку не нашёл"
    end if
  end tell
end tell
APPLESCRIPT
osascript "$out/click.applescript" >> "$out/screens.log" 2>&1 &
clicker=$!
( sleep 90; kill "$clicker" 2>/dev/null ) &
wait "$clicker" 2>/dev/null
log "щелчок: код $?"
shot 5-after-open-anyway 6
