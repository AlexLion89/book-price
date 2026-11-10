"""The built macOS program, end to end, without visiting any site: python tools/mac/smoke.py <Ценитель.app> <out dir>
[--arch=x86_64]

A "user's" Google Chrome with three tabs is running all along, and the program is told to use that same Chrome app:
the hardest case for "never touch the user's browser". Checked: the program starts, opens its window and the search
window, restarts as an update does, quits when its window is closed and via «Выйти», and leaves nothing running —
while the user's Chrome keeps its process and its tabs. Screenshots and logs go to <out dir>.
"""
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

APP = Path(sys.argv[1]).resolve()
OUT = Path(sys.argv[2]).resolve()
ARCH = next((a.split("=", 1)[1] for a in sys.argv[3:] if a.startswith("--arch=")), "")
EXE = APP / "Contents" / "MacOS" / "BookPrice"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
DATA = Path.home() / "Library" / "Application Support" / "BookPrice"
URL = "http://127.0.0.1:8769/"
USER_PROFILE = Path("/tmp/bp-user-chrome")
DEBUG_PORT = 9333
TABS = [f"data:text/html;charset=utf-8,<title>Вкладка пользователя {n}</title><h1>{n}</h1>" for n in (1, 2, 3)]

OUT.mkdir(parents=True, exist_ok=True)
results = []


def check(name, ok, detail=""):
    results.append({"check": name, "ok": bool(ok), "detail": str(detail)})
    print(("OK   " if ok else "FAIL ") + name + (f" — {detail}" if detail else ""), flush=True)
    return ok


def get(path, timeout=5):
    with urllib.request.urlopen(URL + path, timeout=timeout) as r:
        return json.load(r)


def post(path, body=b"{}", timeout=10):
    req = urllib.request.Request(URL + path, data=body, method="POST", headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def ping():
    try:
        return get("api/ping", 2).get("ok")
    except Exception:
        return False


def wait(cond, limit, step=0.5):
    end = time.time() + limit
    while time.time() < end:
        if cond():
            return True
        time.sleep(step)
    return False


def ps():
    out = subprocess.run(["ps", "-axww", "-o", "pid=,command="], capture_output=True).stdout.decode("utf-8", "replace")
    rows = []
    for line in out.splitlines():
        pid, _, command = line.strip().partition(" ")
        if pid.isdigit():
            rows.append((int(pid), command))
    return rows


def ours():
    """Browser processes (not helpers) started with a profile in the program's data folder."""
    return [(p, c) for p, c in ps() if f"--user-data-dir={DATA}" in c and "--type=" not in c]


def program_running():
    return [(p, c) for p, c in ps() if str(EXE) in c]


def user_tabs():
    """The user's tabs by id and address: a title may still be empty while a tab loads."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{DEBUG_PORT}/json/list", timeout=5) as r:
            return sorted(f'{t["id"]} {t["url"][:40]}' for t in json.load(r) if t.get("type") == "page")
    except Exception as e:
        return [f"нет ответа: {e}"]


def alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    st = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True).stdout.decode().strip()
    return bool(st) and not st.startswith("Z")


def shot(name):
    path = OUT / f"{name}.png"
    subprocess.run(["screencapture", "-x", str(path)], capture_output=True)
    print("снимок", path.name, flush=True)


def launch(extra_env=None):
    env = {**os.environ, "BOOKPRICE_BROWSER": CHROME, **(extra_env or {})}
    cmd = (["arch", f"-{ARCH}"] if ARCH else []) + [str(EXE)]
    return subprocess.Popen(cmd, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main():
    shutil.rmtree(USER_PROFILE, ignore_errors=True)
    user = subprocess.Popen([CHROME, f"--user-data-dir={USER_PROFILE}", "--no-first-run", "--no-default-browser-check",
                             f"--remote-debugging-port={DEBUG_PORT}", *TABS],
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    wait(lambda: len(user_tabs()) == 3 and not user_tabs()[0].startswith("нет ответа"), 40)
    tabs_before = user_tabs()
    check("Chrome «пользователя» с тремя вкладками", len(tabs_before) == 3, tabs_before)
    assert not ping(), "порт 8769 уже занят"

    arch = subprocess.run(["lipo", "-archs", str(EXE)], capture_output=True, text=True).stdout.strip()
    check("программа универсальная (Intel + Apple M)", "x86_64" in arch and "arm64" in arch, arch)

    print("A. запуск", ARCH or "родной", flush=True)
    app = launch()
    check("программа поднялась", wait(ping, 90), get("api/ping") if ping() else "нет ответа")
    check("окно программы открыто", wait(lambda: len(ours()) == 1, 30), [c[:160] for _, c in ours()])
    time.sleep(4)
    shot(f"1-window{'-' + ARCH if ARCH else ''}")
    system = get("api/system")
    check("программа видит браузер", system.get("browser") == "Google Chrome", system)
    if ARCH:
        check("запущена под " + ARCH, system.get("machine") == ARCH, system.get("machine"))

    print("B. окно поиска", flush=True)
    post("api/window-test")
    wait(lambda: get("api/window-test").get("status") == "running", 30)
    time.sleep(3)
    shot(f"2-search-window{'-' + ARCH if ARCH else ''}")
    wait(lambda: get("api/window-test").get("status") in ("done", "error"), 60)
    state = get("api/window-test")
    check("окно поиска открылось и закрылось", state.get("status") == "done", state)
    check("вкладки пользователя на месте после окна поиска", user_tabs() == tabs_before, user_tabs())

    print("C. перезапуск, как после обновления", flush=True)
    post("api/restart")
    check("старая копия вышла", wait(lambda: app.poll() is not None, 40))
    check("новая копия поднялась", wait(ping, 90))
    check("после перезапуска одно окно", wait(lambda: len(ours()) == 1, 30) and (time.sleep(4) or len(ours()) == 1),
          [c[:120] for _, c in ours()])

    print("D. пользователь закрыл окно программы", flush=True)
    window = ours()
    for pid, _ in window:
        os.kill(pid, signal.SIGTERM)
    check("программа выключилась сама", wait(lambda: not ping(), 40) and wait(lambda: not program_running(), 20),
          program_running())
    check("её окон не осталось", wait(lambda: not ours(), 20), ours())
    check("Chrome пользователя жив", alive(user.pid))
    check("вкладки пользователя на месте", user_tabs() == tabs_before, user_tabs())

    print("E. повторный запуск и «Выйти»", flush=True)
    launch()
    check("поднялась снова", wait(ping, 90))
    wait(lambda: len(ours()) == 1, 30)
    time.sleep(3)
    shot(f"3-again{'-' + ARCH if ARCH else ''}")
    post("api/quit")
    check("«Выйти» выключает программу", wait(lambda: not ping(), 40) and wait(lambda: not program_running(), 20))
    check("и закрывает её окно", wait(lambda: not ours(), 20), ours())
    check("Chrome пользователя жив в конце", alive(user.pid))
    check("вкладки пользователя в конце те же", user_tabs() == tabs_before, user_tabs())

    user.terminate()
    log = DATA / "logs" / "app.log"
    if log.exists():
        shutil.copy(log, OUT / f"app{'-' + ARCH if ARCH else ''}.log")


try:
    main()
except Exception as e:
    check("проверка дошла до конца", False, f"{type(e).__name__}: {e}")
    log = DATA / "logs" / "app.log"
    if log.exists():
        shutil.copy(log, OUT / f"app{'-' + ARCH if ARCH else ''}.log")
finally:
    for pid, _ in program_running() + ours():
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    (OUT / f"smoke{'-' + ARCH if ARCH else ''}.json").write_text(json.dumps(results, ensure_ascii=False, indent=1),
                                                                 encoding="utf-8")
failed = [r for r in results if not r["ok"]]
print(f"итог: {len(results) - len(failed)} из {len(results)}", flush=True)
sys.exit(1 if failed else 0)
