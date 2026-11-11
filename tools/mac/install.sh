#!/bin/bash
# Установка «Ценителя» на Mac одной строкой в Терминале:
#   curl -fsSL https://raw.githubusercontent.com/AlexLion89/book-price/main/tools/mac/install.sh | bash
#
# Скачивает образ последнего выпуска с программой для Mac, кладёт «Ценитель» в «Программы» и запускает.
# Отметку «скачано из интернета», из-за которой macOS просит разрешения в настройках, ставят браузеры; curl её не
# ставит, поэтому так программа открывается сразу. Ничего, кроме самого «Ценителя», скрипт не меняет.
set -euo pipefail

REPO="AlexLion89/book-price"
APP="Ценитель.app"

say() { printf '\n\033[1m%s\033[0m\n' "$*"; }
fail() { printf '\n\033[31m%s\033[0m\n' "$*" >&2; exit 1; }

say "Ищу последнюю версию «Ценителя» для Mac…"
# Выпуски идут от новых к старым; первый образ для Mac в списке — самый свежий.
url=$(curl -fsSL "https://api.github.com/repos/$REPO/releases?per_page=30" \
  | grep -o '"browser_download_url": *"[^"]*-mac\.dmg"' | head -n 1 | sed 's/.*"\(https[^"]*\)"$/\1/') || true
[ -n "$url" ] || fail "Не нашёл программу для Mac на странице выпусков. Проверьте интернет и попробуйте ещё раз."

work=$(mktemp -d)
trap 'hdiutil detach "$work/mnt" -quiet >/dev/null 2>&1 || true; rm -rf "$work"' EXIT

say "Скачиваю ${url##*/} (около 100 МБ)…"
curl -fL --progress-bar -o "$work/Cenitel.dmg" "$url" || fail "Не получилось скачать. Проверьте интернет и попробуйте ещё раз."

# A running copy keeps its files open: ask it to quit first (the program answers only on this computer).
if curl -fs -m 2 http://127.0.0.1:8769/api/ping >/dev/null 2>&1; then
  say "Закрываю запущенный «Ценитель»…"
  curl -fs -m 5 -X POST -H 'Content-Type: application/json' -d '{}' http://127.0.0.1:8769/api/quit >/dev/null 2>&1 || true
  sleep 5
fi

mkdir -p "$work/mnt"
hdiutil attach -nobrowse -readonly -quiet -mountpoint "$work/mnt" "$work/Cenitel.dmg" </dev/null || fail "Скачанный файл не открылся. Попробуйте ещё раз."

target="/Applications"
if [ ! -w "$target" ]; then
  # Not an administrator: the user's own «Программы» folder works just as well.
  target="$HOME/Applications"
  mkdir -p "$target"
fi
say "Кладу «Ценитель» в папку «Программы» ($target)…"
rm -rf "${target:?}/$APP"
ditto "$work/mnt/$APP" "$target/$APP"
xattr -dr com.apple.quarantine "$target/$APP" 2>/dev/null || true

say "Готово! Запускаю «Ценитель» — окно программы откроется в вашем браузере."
open "$target/$APP"
printf 'Дальше программу можно открывать как обычно: Launchpad или Finder → «Программы» → «Ценитель».\n'
printf 'Окно Терминала можно закрыть.\n'
