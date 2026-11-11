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
