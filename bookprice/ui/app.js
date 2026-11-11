"use strict";

const view = document.getElementById("view");
const STATE_LABEL = { waiting: "ждёт", running: "ищу…", done: "готово", error: "не вышло" };
const STATUS_LABEL = { draft: "ещё не выставлена", listed: "выставлена", sold: "продана" };
let pollTimer = null;
// What differs between Windows and macOS, and which browser the program drives: GET /api/system.
let SYS = { os: "windows", outbox: "на рабочем столе", browser: "Microsoft Edge", downloads: [] };
let addState = { mode: "isbn", book: null, candidates: null, condition: "excellent", error: "" };
const openSources = new Set();

function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}
function rub(n) { return n == null ? "—" : Math.round(n).toLocaleString("ru-RU") + " ₽"; }
function day(iso) { return iso ? new Date(iso).toLocaleDateString("ru-RU", { day: "numeric", month: "long" }) : ""; }

function toast(text, ms = 4000) {
  const t = document.getElementById("toast");
  t.textContent = text;
  t.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => { t.hidden = true; }, ms);
}

async function api(method, path, body) {
  const res = await fetch(path, {
    method, headers: body ? { "Content-Type": "application/json" } : {}, body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || "ошибка " + res.status);
  return data;
}

function cover(url, cls = "cover") {
  const img = url ? `<img src="${esc(url)}" alt="" referrerpolicy="no-referrer" onerror="this.remove()">` : "";
  return `<div class="${cls}">${img}</div>`;
}

async function route() {
  clearTimeout(pollTimer);
  const hash = location.hash || "#/";
  document.querySelectorAll("nav [data-route]").forEach(b =>
    b.classList.toggle("active", b.dataset.route === hash || (b.dataset.route === "#/" && hash.startsWith("#/book/"))));
  try {
    if (hash === "#/") return await renderList();
    if (hash === "#/add") return renderAdd();
    if (hash === "#/help") return renderHelp();
    const m = hash.match(/^#\/book\/(\d+)$/);
    if (m) return await renderBook(+m[1]);
    location.hash = "#/";
  } catch (e) {
    view.innerHTML = `<div class="alert">Что-то пошло не так: ${esc(e.message)}</div>`;
  }
}

/* ---------- list ---------- */

async function renderList() {
  const books = await api("GET", "/api/books");
  const due = books.filter(b => b.next_step);
  const listed = books.filter(b => b.status === "listed").length;
  const sold = books.filter(b => b.status === "sold").length;
  view.innerHTML = `
    <div class="hero">
      <div class="grow">
        <h1>Мои книги</h1>
        <p>${books.length ? `На полке ${books.length} · на Авито ${listed} · продано ${sold}` : "Полка пока пуста — самое время найти, что продать."}</p>
        <a class="primary" href="#/add">+ Добавить книгу</a>
      </div>
    </div>
    ${due.length ? `<div class="alert">🔎 Пора снизить цену: ${due.map(b => `<a href="#/book/${b.id}">${esc(b.title)}</a> — до ${rub(b.next_step.price)}`).join(", ")}</div>` : ""}
    ${books.length ? `<div class="grid">${books.map(tile).join("")}</div>`
      : `<div class="card empty"><img class="art" src="/img/search.png" alt="">
          <h2>Ни одной улики</h2>
          <p class="muted">Нажмите «Добавить книгу» и введите ISBN — 13 цифр под штрихкодом на задней обложке.</p></div>`}`;
}

function tile(b) {
  let badge = `<span class="badge">${STATUS_LABEL[b.status] || b.status}</span>`;
  if (b.status === "listed") badge = `<span class="badge listed">на Авито за ${rub(b.listed_price)}</span>`;
  if (b.status === "sold") badge = `<span class="badge sold">продана${b.sold_price ? " за " + rub(b.sold_price) : ""}</span>`;
  const warn = b.next_step ? `<span class="badge warn">снизить до ${rub(b.next_step.price)}</span>` : "";
  return `<a class="book-tile" href="#/book/${b.id}">${cover(b.cover_url)}
    <strong>${esc(b.title)}</strong><span class="muted small">${esc(b.author || "")}${b.year ? ", " + b.year : ""}</span>
    <span>${badge} ${warn}</span></a>`;
}

/* ---------- add ---------- */

function renderAdd() {
  const s = addState;
  const conditions = { new: "как новая", excellent: "отличное", good: "хорошее", marked: "с пометками или потёртостями" };
  view.innerHTML = `
    <a class="back" href="#/">← Все книги</a>
    <h1>Новая книга</h1>
    <div class="card">
      ${s.mode === "isbn" ? `
        <h2>ISBN — 13 цифр под штрихкодом</h2>
        <form id="isbn-form" class="row">
          <input class="big" id="isbn" placeholder="978-5-..." autocomplete="off" autofocus>
          <button class="primary">Найти</button>
        </form>
        <p class="small muted">Сканер штрихкодов тоже подойдёт: наведите — цифры впишутся сами.</p>
        <p><button class="link" data-mode="title">У книги нет ISBN (старое издание)</button></p>`
      : `
        <h2>Название и автор</h2>
        <form id="title-form" class="row">
          <input id="t-title" placeholder="Название" style="width: 320px" autofocus value="${esc((s.typed || {}).title || "")}">
          <input id="t-author" placeholder="Автор" style="width: 220px" value="${esc((s.typed || {}).author || "")}">
          <input id="t-year" placeholder="Год" style="width: 90px" value="${esc((s.typed || {}).year || "")}">
          <button class="primary">Найти издания</button>
        </form>
        <p><button class="link" data-mode="isbn">Есть ISBN</button></p>`}
      ${s.error ? `<div class="alert">${esc(s.error)}</div>` : ""}
      ${s.candidates ? candidatesHtml(s.candidates) : ""}
    </div>
    ${s.book ? `
      <div class="card">
        <div class="row" style="align-items: flex-start">
          ${cover(s.book.cover_url, "cover small")}
          <div>
            <h2>${esc(s.book.title)}</h2>
            <div>${esc(s.book.author)}</div>
            <div class="muted">${esc([s.book.publisher, s.book.year, s.book.isbn].filter(Boolean).join(", "))}</div>
            <h2 style="margin-top: 16px">Состояние книги</h2>
            <div class="radio">${Object.entries(conditions).map(([k, v]) =>
              `<label><input type="radio" name="cond" value="${k}" ${k === s.condition ? "checked" : ""}> ${v}</label>`).join("")}</div>
            <p><button class="primary" id="go">Найти цены</button></p>
          </div>
        </div>
      </div>` : ""}`;

  view.querySelectorAll("[data-mode]").forEach(b => b.onclick = () => {
    addState = { ...addState, mode: b.dataset.mode, error: "", candidates: null };
    renderAdd();
  });
  const isbnForm = document.getElementById("isbn-form");
  if (isbnForm) isbnForm.onsubmit = async e => {
    e.preventDefault();
    const isbn = document.getElementById("isbn").value;
    addState.error = "";
    try {
      toast("Ищу книгу…", 2000);
      const { book } = await api("POST", "/api/lookup", { isbn });
      if (book) addState.book = book;
      else addState = { ...addState, mode: "title", book: null, error: "По этому ISBN книга не нашлась. Введите название и автора." };
    } catch (err) { addState.error = err.message; }
    renderAdd();
  };
  const titleForm = document.getElementById("title-form");
  if (titleForm) titleForm.onsubmit = async e => {
    e.preventDefault();
    const title = document.getElementById("t-title").value.trim();
    const author = document.getElementById("t-author").value.trim();
    const year = parseInt(document.getElementById("t-year").value, 10) || null;
    if (!title) return;
    toast("Ищу издания…", 2000);
    const { books } = await api("POST", "/api/find", { title, author });
    addState.typed = { title, author, year };
    const distance = b => (year && b.year ? Math.abs(b.year - year) : 999);
    addState.candidates = books.slice().sort((a, b) => distance(a) - distance(b) || (b.year || 0) - (a.year || 0));
    addState.showAll = false;
    renderAdd();
  };
  const more = document.getElementById("more-editions");
  if (more) more.onclick = () => { addState.showAll = true; renderAdd(); };
  view.querySelectorAll("[data-pick]").forEach(b => b.onclick = () => {
    const i = +b.dataset.pick;
    addState.book = i < 0 ? { ...addState.typed, isbn: "" } : addState.candidates[i];
    addState.candidates = null;
    renderAdd();
  });
  view.querySelectorAll("input[name=cond]").forEach(r => r.onchange = () => { addState.condition = r.value; });
  const go = document.getElementById("go");
  if (go) go.onclick = async () => {
    go.disabled = true;
    const { id } = await api("POST", "/api/books", { book: addState.book, condition: addState.condition });
    addState = { mode: "isbn", book: null, candidates: null, condition: "excellent", error: "" };
    location.hash = `#/book/${id}`;
  };
}

const SHOWN_EDITIONS = 15;

function candidatesHtml(list) {
  const shown = addState.showAll ? list : list.slice(0, SHOWN_EDITIONS);
  return `<h2 style="margin-top: 16px">Какое издание у вас?</h2>
    <p class="small muted">Изданий нашлось ${list.length}${addState.typed && addState.typed.year ? `, ближе к ${addState.typed.year} году — сверху` : ""}.</p>
    <div class="candidates">
      ${shown.map((b, i) => `<button class="ghost" data-pick="${i}"><strong>${esc(b.year || "год ?")}</strong> · ${esc(b.publisher || "издательство ?")}
        · ${esc(b.title)} <span class="muted small">${esc(b.isbn || "")}</span></button>`).join("")}
      ${list.length > shown.length ? `<p><button class="link" id="more-editions">показать все ${list.length}</button></p>` : ""}
      <button class="ghost" data-pick="-1">Моего издания нет в списке — взять, как я ввела</button>
    </div>`;
}

/* ---------- book ---------- */

async function renderBook(id) {
  const d = await api("GET", `/api/books/${id}`);
  const job = d.job;
  const running = job && (job.status === "queued" || job.status === "running");
  const b = d.book, v = d.verdict;
  const label = Object.fromEntries(d.sources.map(s => [s.name, s.label]));

  view.innerHTML = `
    <a class="back" href="#/">← Все книги</a>
    <div class="card row" style="align-items: flex-start">
      ${cover(b.cover_url, "cover small")}
      <div style="flex: 1">
        <h1 style="margin-bottom: 4px">${esc(b.title)}</h1>
        <div>${esc(b.author)}</div>
        <div class="muted">${esc([b.publisher, b.year, b.isbn].filter(Boolean).join(", "))}</div>
        <div class="row small" style="margin-top: 10px">Состояние:
          <select id="cond">${Object.entries(d.conditions).map(([k, t]) => `<option value="${k}" ${k === b.condition ? "selected" : ""}>${t}</option>`).join("")}</select>
          <button class="link" id="del">удалить книгу</button>
        </div>
        <div class="small" style="margin-top: 10px">Особенности экземпляра <span class="muted">— отметьте, если есть:</span>
          <div class="marks">${d.copy_mark_options.map(m => `<label><input type="checkbox" data-mark="${m.key}"
            ${d.copy_marks.includes(m.key) ? "checked" : ""}> ${esc(m.label)}
            <span class="muted">${m.effect > 0 ? "+" : "−"}${Math.round(Math.abs(m.effect) * 100)} %</span></label>`).join("")}</div>
        </div>
      </div>
    </div>
    ${running ? progressHtml(job, label) : ""}
    ${job && job.status === "error" ? `<div class="alert">Поиск сломался: ${esc(job.error)}. Нажмите «Искать заново»; если повторится — «Отчёт об ошибке».</div>` : ""}
    ${running && !Object.keys(d.runs).length ? `<div class="card muted">Вердикт появится, когда лиса вернётся с уликами — обычно через минуту.</div>` : `
    ${verdictHtml(d)}
    ${dossierHtml(d)}
    ${statusHtml(d)}
    <div class="card">
      <h2>Текст для объявления</h2>
      <textarea id="ad" readonly>${esc(d.ad_text)}</textarea>
      <p><button class="ghost" id="copy">Скопировать</button></p>
    </div>
    <div class="card">
      <div class="row" style="justify-content: space-between"><div><div class="kicker">Улики</div><h2 style="margin: 0">Что нашлось на площадках</h2></div>
        <button class="ghost" id="again" ${running ? "disabled" : ""}>Искать заново</button></div>
      <p class="small muted">Галочка — предложение учитывается в цене. Снимите её, если это другое издание или не та книга.</p>
      ${d.sources.map(s => sourceHtml(s, d)).join("")}
    </div>`}`;

  const on = (elementId, event, fn) => { const el = document.getElementById(elementId); if (el) el[event] = fn; };
  on("cond", "onchange", async e => { await api("POST", `/api/books/${id}`, { condition: e.target.value }); route(); });
  view.querySelectorAll("input[data-mark]").forEach(c => c.onchange = async () => {
    const marks = [...view.querySelectorAll("input[data-mark]:checked")].map(x => x.dataset.mark);
    await api("POST", `/api/books/${id}`, { copy_marks: marks });
    route();
  });
  on("del", "onclick", async () => {
    if (!confirm("Удалить книгу и всё, что о ней нашлось?")) return;
    await api("DELETE", `/api/books/${id}`);
    location.hash = "#/";
  });
  on("copy", "onclick", async () => {
    await navigator.clipboard.writeText(d.ad_text);
    toast("Текст скопирован — вставьте его в описание объявления");
  });
  on("again", "onclick", async () => { await api("POST", `/api/books/${id}/search`); route(); });
  view.querySelectorAll("input[data-ext]").forEach(c => c.onchange = async () => {
    await api("POST", `/api/books/${id}/mark`, { source: c.dataset.source, ext_id: c.dataset.ext, counted: c.checked });
    route();
  });
  view.querySelectorAll("form[data-manual]").forEach(f => f.onsubmit = async e => {
    e.preventDefault();
    await api("POST", `/api/books/${id}/manual`, { source: f.dataset.manual, price: f.price.value || null });
    route();
  });
  view.querySelectorAll("[data-toggle]").forEach(t => t.onclick = () => {
    const name = t.dataset.toggle;
    openSources.has(name) ? openSources.delete(name) : openSources.add(name);
    route();
  });
  view.querySelectorAll("form[data-price]").forEach(f => f.onsubmit = async e => {
    e.preventDefault();
    const price = parseInt(f.price.value, 10);
    const kind = f.dataset.price;
    if (kind !== "sold" && !price) return toast("Впишите цену");
    await api("POST", `/api/books/${id}/${kind === "sold" ? "sold" : "listed"}`, { price: price || null, event: kind });
    route();
  });

  if (running) pollTimer = setTimeout(route, 1500);
}

function progressHtml(job, label) {
  const captcha = job.captcha
    ? `<div class="alert big">${esc(label[job.captcha] || job.captcha)} просит подтвердить, что вы не робот.
        Перейдите в окно «Поиск цен» и пройдите проверку там — поиск продолжится сам.</div>` : "";
  return `${captcha}<div class="card sleuth"><img src="/img/search.png" alt="">
    <div><h2><span class="spinner"></span> Лиса идёт по следу — около минуты</h2>
    ${job.stage ? `<p class="small muted" style="margin-top: -6px">${esc(job.stage)}</p>` : ""}
    <div class="chips">${Object.entries(job.sources).map(([n, st]) =>
      `<span class="chip ${st}">${esc(label[n] || n)}: ${STATE_LABEL[st] || st}</span>`).join("")}</div></div></div>`;
}

function dossierHtml(d) {
  const x = d.dossier;
  if (!x || !(x.facts.length || x.factors.length)) return "";
  const pct = p => `+${Math.round(p * 100)} %`;
  return `<div class="card"><div class="kicker">Досье</div>
    <h2>Насколько книга редкая и ценная</h2>
    <table class="facts">${x.facts.map(([k, v]) => `<tr><td class="muted">${esc(k)}</td><td>${esc(v)}</td></tr>`).join("")}
      ${x.collectible.length ? `<tr><td class="muted">Коллекционные признаки</td><td>${esc(x.collectible.join(", "))}</td></tr>` : ""}
    </table>
    ${x.factors.length ? `<ul class="small reasons">${x.factors.map(f =>
      `<li><strong>${esc(f.label)}</strong> — ${esc(f.detail)}${f.premium ? ` <span class="badge warn">${pct(f.premium)}</span>` : ""}</li>`).join("")}</ul>` : ""}
    ${x.premium ? `<p style="margin-bottom: 0"><strong>Надбавка к начальной цене: ${pct(x.premium)}.</strong>
      <span class="muted small">Не больше +50 %; нижний предел не меняется — если не продаётся, цена вернётся к рынку.</span></p>` : ""}
  </div>`;
}

function verdictHtml(d) {
  const v = d.verdict;
  if (v.start == null) {
    return `<div class="card"><h2>Цену подсказать не получилось</h2>
      <p>${v.reasons.map(esc).join("<br>")}</p></div>`;
  }
  return `<div class="card">
    <div class="verdict">
      <div><div class="kicker">Вердикт</div><div class="muted small">Выставить за</div><div class="price">${rub(v.start)}</div></div>
      <div><div class="muted small">Не опускаться ниже</div><div class="floor">${rub(v.floor)}</div></div>
    </div>
    ${v.schedule.length > 1 ? `<div class="small muted" style="margin-top: 10px">Если не продаётся — снижать раз в ${v.step_days} дней:</div>
      <div class="steps">${v.schedule.map(p => `<span>${rub(p)}</span>`).join("→")}</div>` : ""}
    ${v.as_lot ? `<div class="alert">Книга недорогая — выгоднее выставить её одним объявлением вместе с другими.</div>` : ""}
    <ul class="small reasons">${v.reasons.map(r => `<li>${esc(r)}</li>`).join("")}</ul>
  </div>`;
}

function statusHtml(d) {
  const b = d.book, v = d.verdict;
  if (b.status === "sold") {
    return `<div class="card"><div class="kicker">Дело закрыто</div><h2 style="margin: 0">Продана${b.sold_price ? " за " + rub(b.sold_price) : ""} ${day(b.sold_at)} 🎉</h2></div>`;
  }
  const soldForm = `<form data-price="sold" class="row">Продала за <input class="price" name="price" inputmode="numeric"> ₽
      <button class="ghost">Отметить проданной</button></form>`;
  if (b.status === "listed") {
    const step = d.next_step;
    return `<div class="card">
      <h2>На Авито за ${rub(b.listed_price)} с ${day(b.price_changed_at)}</h2>
      ${step ? `<div class="alert">Висит ${step.days} дн. без продажи — можно снизить до ${rub(step.price)}.
        <form data-price="lowered" class="row" style="margin-top: 8px"><input type="hidden" name="price" value="${step.price}">
        <button class="primary">Снизила до ${rub(step.price)}</button></form></div>` : ""}
      <form data-price="changed" class="row" style="margin-bottom: 10px">Поменяла цену на
        <input class="price" name="price" inputmode="numeric"> ₽ <button class="ghost">Сохранить</button></form>
      ${soldForm}
    </div>`;
  }
  return `<div class="card">
    <form data-price="listed" class="row">Выставила на Авито за
      <input class="price" name="price" inputmode="numeric" value="${v.start || ""}"> ₽
      <button class="primary">Запомнить</button></form>
    <p class="small muted">Через неделю без продажи программа подскажет, до скольких снизить.</p>
  </div>`;
}

function sourceHtml(s, d) {
  const run = d.runs[s.name];
  const items = d.found.filter(f => f.offer.source === s.name);
  const on = items.filter(f => f.counted), off = items.filter(f => !f.counted);
  const show = openSources.has(s.name);
  const manual = d.manual[s.name];
  const canManual = s.kind !== "dealer";
  let state = "";
  if (!run) state = `<span class="muted small">ещё не искали</span>`;
  else if (run.error) state = `<span class="small" style="color: var(--bad)">не получилось прочитать</span>`;
  else state = `<span class="muted small">найдено ${run.count}, подходят ${on.length}</span>`;
  return `<div class="source-head"><h2 style="margin: 12px 0 4px">${esc(s.label)}</h2>
      <span>${state} ${run && run.search_url ? `· <a href="${esc(run.search_url)}" target="_blank">открыть поиск</a>` : ""}</span></div>
    ${on.length ? `<table>${on.map(rowHtml).join("")}</table>` : ""}
    ${off.length ? `<p><button class="link small" data-toggle="${s.name}">${show ? "скрыть" : "показать"} остальные (${off.length})</button></p>
      ${show ? `<table>${off.map(rowHtml).join("")}</table>` : ""}` : ""}
    ${canManual ? `<form data-manual="${s.name}" class="row small" style="margin: 6px 0 4px">
      ${manual ? `Вписано вручную: <strong>${rub(manual)}</strong>` : "Нашли цену сами?"}
      <input class="price" name="price" inputmode="numeric" placeholder="₽" value="${manual || ""}">
      <button class="ghost">${manual ? "Изменить" : "Добавить"}</button></form>` : ""}`;
}

function rowHtml(f) {
  const o = f.offer;
  const meta = [o.note, o.place, o.age].filter(Boolean).join(" · ");
  return `<tr class="${f.counted ? "" : "off"}">
    <td style="width: 28px"><input type="checkbox" data-source="${esc(o.source)}" data-ext="${esc(o.ext_id || o.url)}" ${f.counted ? "checked" : ""}></td>
    <td class="p">${rub(o.price)}</td>
    <td><a href="${esc(o.url)}" target="_blank">${esc(o.title || "без названия")}</a>
      ${o.text ? `<div class="small muted">${esc(o.text.slice(0, 160))}</div>` : ""}
      ${o.desc ? `<div class="small muted">${esc(o.desc.slice(0, 200))}</div>` : ""}
      <div class="small muted">${esc(meta)}${meta ? " · " : ""}${esc(f.reason)}</div></td></tr>`;
}

/* ---------- help ---------- */

function renderHelp() {
  view.innerHTML = `<a class="back" href="#/">← Все книги</a>
  <h1>Как пользоваться</h1>
  <div class="card">
    <ol>
      <li><strong>Добавьте книгу.</strong> Впишите ISBN — 13 цифр под штрихкодом на задней обложке. Если ISBN нет (старая книга) — название, автора и год, потом выберите своё издание из списка.</li>
      <li><strong>Выберите состояние</strong> и нажмите «Найти цены». Откроется отдельное окно «Поиск цен»${SYS.browser ? ` (${esc(SYS.browser)})` : ""} — в нём программа сама ходит по магазинам и Авито (Читай-город, Лабиринт, Book24, Буквоед, Республика, Библио-Глобус, Дом книги (СПб), Московский дом книги, Озон, Wildberries, Яндекс Маркет, Авито, alib и Мешок), минуты полторы-две. Трогать его не нужно: когда поиск закончится, оно закроется само.</li>
      <li><strong>Если площадка спросит «вы не робот?»</strong> — программа напишет об этом крупно. Перейдите в окно «Поиск цен», пройдите проверку, дальше поиск пойдёт сам.</li>
      <li><strong>Посмотрите, что нашлось.</strong> Снимите галочки у чужих изданий и комплектов — цена пересчитается.</li>
      <li><strong>Выставьте объявление</strong>, скопировав готовый текст, и отметьте в программе цену. Через неделю без продажи программа подскажет, до скольких снизить.</li>
    </ol>
    <p>Вернуться к списку книг — кнопка «Мои книги» вверху, ссылка «← Все книги» или клавиша Esc. Закрыть программу — кнопка «Выйти» или просто закрыть это окно. Ваши собственные окна и вкладки браузера программа не трогает: у неё свои отдельные окна со своим профилем.</p>
    <p>Если что-то не работает — нажмите «Отчёт об ошибке» вверху. ${SYS.os === "mac" ? "Откроется Finder с zip-файлом" : "На рабочем столе появится zip-файл"}: пришлите его тому, кто помогает с программой. В нём журнал работы и ваш список книг с найденными ценами — по нему видно, почему программа так посчитала. Сама программа ничего никуда не отправляет.</p>
  </div>
  ${browserCardHtml()}
  <div class="card">
    <h2>Проверка площадок</h2>
    <p class="small muted">Для того, кто помогает с программой: прогоняет все площадки на двух книгах и сохраняет снимки страниц в zip ${esc(SYS.outbox)}. Занимает пару минут.</p>
    <div class="row"><input id="check-isbn" placeholder="ещё ISBN, необязательно" style="width: 260px"><button class="ghost" id="check">Проверить площадки</button></div>
    <pre id="check-log" class="small" style="white-space: pre-wrap"></pre>
    <p class="small muted">Без захода на сайты: откроет окно поиска на несколько секунд и закроет — видно, что браузер слушается программу.</p>
    <div class="row"><button class="ghost" id="window-test">Проверить окно поиска</button> <span id="window-test-log" class="small"></span></div>
  </div>`;
  document.getElementById("window-test").onclick = async () => {
    await api("POST", "/api/window-test");
    pollWindowTest();
  };
  const pick = document.getElementById("browser-pick");
  if (pick) pick.onchange = async () => {
    try {
      SYS = await api("POST", "/api/browser", { key: pick.value });
      document.getElementById("browser-note").innerHTML = `Готово: поиск пойдёт в ${esc(SYS.browser)} со следующей книги.
        Окно программы откроется в нём после перезапуска. <button class="ghost" id="browser-restart">Перезапустить сейчас</button>`;
      document.getElementById("browser-restart").onclick = restartNow;
    } catch (e) { toast(e.message, 6000); }
  };
  document.getElementById("check").onclick = async () => {
    await api("POST", "/api/check", { isbn: document.getElementById("check-isbn").value.trim() });
    pollCheck();
  };
  pollCheck();
}

function browserCardHtml() {
  const list = SYS.browsers || [];
  if (!list.length) return "";
  const choice = list.length > 1
    ? `<select id="browser-pick">${list.map(b =>
        `<option value="${esc(b.key)}" ${b.key === SYS.browser_key ? "selected" : ""}>${esc(b.label)}</option>`).join("")}</select>`
    : `<strong>${esc(list[0].label)}</strong> — другого подходящего на компьютере нет.`;
  return `<div class="card">
    <h2>Браузер</h2>
    <p class="small muted">В каком браузере программа открывает свои окна и ищет цены. Ваши окна, вкладки и пароли в нём она не трогает: у неё свои отдельные окна.</p>
    <div class="row">${choice}</div>
    <p class="small" id="browser-note"></p>
  </div>`;
}

async function restartNow() {
  const st = await api("GET", "/api/update-status");
  if (st.busy) return toast("Сейчас идёт поиск — дождитесь его конца", 6000);
  await api("POST", "/api/restart");
  view.innerHTML = `<div class="card"><span class="spinner"></span> Перезапускаюсь — окно откроется заново…</div>`;
}

async function pollCheck() {
  const box = document.getElementById("check-log");
  if (!box) return;
  const st = await api("GET", "/api/check");
  box.textContent = st.lines.join("\n");
  const running = st.status === "queued" || st.status === "running";
  document.getElementById("check").disabled = running;
  if (running) pollTimer = setTimeout(pollCheck, 1500);
}

async function pollWindowTest() {
  const box = document.getElementById("window-test-log");
  if (!box) return;
  const st = await api("GET", "/api/window-test");
  const running = st.status === "queued" || st.status === "running";
  box.textContent = running ? "окно поиска открыто…" : st.status === "done" ? `работает: ${st.browser}`
    : st.status === "error" ? `не вышло: ${st.error}` : "";
  document.getElementById("window-test").disabled = running;
  if (running) setTimeout(pollWindowTest, 1000);
}

/* ---------- header ---------- */

document.querySelectorAll("nav [data-action]").forEach(btn => btn.onclick = async () => {
  const action = btn.dataset.action;
  try {
    if (action === "help") location.hash = "#/help";
    if (action === "home") location.hash = "#/";
    if (action === "add") location.hash = "#/add";
    if (action === "report") {
      toast("Собираю отчёт…", 2000);
      const { path, where } = await api("POST", "/api/report");
      toast(`Отчёт сохранён ${where}: ${path.split(/[\\/]/).pop()}`, 8000);
    }
    if (action === "update") await updateNow(true);
    if (action === "quit") {
      if (!confirm("Закрыть программу? Окно поиска тоже закроется.")) return;
      await api("POST", "/api/quit");
      view.innerHTML = `<div class="card">Программа закрыта. Это окно можно закрыть.</div>`;
      setTimeout(() => window.close(), 500);
    }
  } catch (e) { toast(e.message, 6000); }
});

async function updateNow(ask) {
  const st = await api("GET", "/api/update-status");
  if (st.busy) return toast("Сейчас идёт поиск — дождитесь его конца и обновите", 6000);
  toast("Проверяю обновления…", 2000);
  const r = await api("POST", "/api/update");
  if (r.error) return toast(r.error, 6000);
  if (!r.updated) return toast(`У вас последняя версия (${r.version})`);
  if (ask && !confirm(`Скачана версия ${r.version}. Перезапустить программу сейчас?`)) return;
  await api("POST", "/api/restart");
  document.getElementById("update-banner").hidden = true;
  view.innerHTML = `<div class="card"><span class="spinner"></span> Обновляюсь до ${esc(r.version)} — окно откроется заново…</div>`;
}

function offerUpdate(st) {
  const banner = document.getElementById("update-banner");
  const u = st && st.available;
  if (!u || sessionStorage.getItem("update-later") === u.version) return;
  banner.innerHTML = `<div class="grow"><strong>Вышла новая версия ${esc(u.version)}</strong> (у вас ${esc(st.version)}).
      ${esc(u.summary)}</div>
    <button class="primary" id="update-now">Обновить сейчас</button><button class="later" id="update-later">Позже</button>`;
  banner.hidden = false;
  document.getElementById("update-now").onclick = () => updateNow(false).catch(e => toast(e.message, 6000));
  document.getElementById("update-later").onclick = () => {
    sessionStorage.setItem("update-later", u.version);
    banner.hidden = true;
  };
}

// Ask again every 3 s until the program has heard back from GitHub, then every half hour.
async function watchUpdates() {
  const st = await api("GET", "/api/update-status").catch(() => null);
  if (st) document.getElementById("version").textContent = "версия " + st.version;
  offerUpdate(st);
  setTimeout(watchUpdates, st && st.checked ? 30 * 60000 : 3000);
}

// Without Chrome, Edge or Yandex Browser the page has opened in the default browser (Safari, Firefox): say what to
// install — searching is impossible until then.
async function checkSystem() {
  const st = await api("GET", "/api/system").catch(() => null);
  if (!st) return;
  SYS = st;
  const banner = document.getElementById("browser-banner");
  if (st.browser) { banner.hidden = true; return; }
  banner.innerHTML = `<div class="grow"><strong>Нужен другой браузер.</strong> ${esc(st.no_browser)}
      Установите любой из них и откройте «Ценитель» заново.</div>
    ${st.downloads.map(d => `<a class="button" href="${esc(d.url)}" target="_blank" rel="noopener">${esc(d.label)}</a>`).join("")}`;
  banner.hidden = false;
}

checkSystem().then(route);
watchUpdates();
setInterval(() => fetch("/api/ping").catch(() => {}), 60000);
// Closing this window turns the program off; a reload asks for the page again at once and cancels that.
window.addEventListener("pagehide", () => navigator.sendBeacon("/api/closed"));
window.addEventListener("hashchange", route);
document.addEventListener("keydown", e => {
  const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement && document.activeElement.tagName);
  if (e.key === "Escape" && !typing && location.hash !== "#/") location.hash = "#/";
});
