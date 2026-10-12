// Интерфейс веб-версии (iPhone / браузер): вход, комнаты, устройства, план, энергия, события.
"use strict";

const $ = sel => document.querySelector(sel);
function h(tag, cls, html) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (html !== undefined) e.innerHTML = html;
  return e;
}

const UI = { engine: null, user: null, page: "devices", roomId: null, floor: "floor1", eventFilter: "all",
             unread: 0, cards: {}, timer: null, sheetLive: null, sheetDeviceId: null };

// ---------- запуск ----------

(async function boot() {
  await initStore();
  if ("serviceWorker" in navigator && location.protocol.startsWith("http")) navigator.serviceWorker.register("sw.js").catch(() => {});
  const user = Store.data.users.find(u => u.id === Store.data.session);
  if (user) startMain(user); else showLogin();
})();

// ---------- вход / регистрация ----------

function showLogin() {
  $("#main").classList.add("hidden");
  $("#login").classList.remove("hidden");
}

document.querySelectorAll(".segment").forEach(b => b.addEventListener("click", () => {
  document.querySelectorAll(".segment").forEach(x => x.classList.toggle("active", x === b));
  $("#loginForm").classList.toggle("hidden", b.dataset.tab !== "login");
  $("#registerForm").classList.toggle("hidden", b.dataset.tab !== "register");
  $("#loginError").textContent = ""; $("#regError").textContent = "";
}));

$("#loginForm").addEventListener("submit", async e => {
  e.preventDefault();
  const name = $("#loginUser").value.trim(), pass = $("#loginPass").value;
  if (!name || !pass) { $("#loginError").textContent = "Введите имя пользователя и пароль"; return; }
  const user = await authenticate(name, pass);
  if (!user) { $("#loginError").textContent = "Неверное имя пользователя или пароль"; $("#loginPass").value = ""; return; }
  $("#loginPass").value = ""; $("#loginError").textContent = "";
  startMain(user);
});

$("#registerForm").addEventListener("submit", async e => {
  e.preventDefault();
  const name = $("#regUser").value.trim(), pass = $("#regPass").value;
  const err = $("#regError");
  if (!/^[A-Za-zА-Яа-яЁё0-9_\-]{2,32}$/.test(name)) { err.textContent = "Имя: 2–32 символа, буквы, цифры, «_» или «-»"; return; }
  if (pass.length < 4) { err.textContent = "Пароль должен содержать не менее 4 символов"; return; }
  if (pass !== $("#regPass2").value) { err.textContent = "Пароли не совпадают"; return; }
  if (findUser(name)) { err.textContent = "Пользователь с таким именем уже существует"; return; }
  const user = await createUser(name, pass);
  Store.save();
  ["#regUser", "#regPass", "#regPass2"].forEach(s => { $(s).value = ""; });
  err.textContent = "";
  startMain(user);
});

// ---------- главный экран ----------

function startMain(user) {
  UI.user = user;
  Store.data.session = user.id;
  Store.save();
  UI.engine = new Engine(user, { onTick: onTick, onEvent: onEvent });
  UI.roomId = null; UI.page = "devices"; UI.unread = 0;
  $("#login").classList.add("hidden");
  $("#main").classList.remove("hidden");
  $("#homeTitle").textContent = "🏠 Мой дом";
  $("#userBtn").textContent = "👤 " + user.username;
  renderRoomTabs();
  UI.engine.tick(false);
  renderPage();
  clearInterval(UI.timer);
  UI.timer = setInterval(() => UI.engine.tick(true), 1000);
}

function logout() {
  clearInterval(UI.timer);
  Store.save();
  Store.data.session = null;
  Store.save();
  closeSheet();
  UI.engine = null;
  showLogin();
}

function home() { return UI.engine.home; }

function renderRoomTabs() {
  const tabs = $("#roomTabs");
  tabs.innerHTML = "";
  [{ id: null, name: "Умный дом" }].concat(home().rooms).forEach(r => {
    const b = h("button", r.id === UI.roomId ? "active" : "", esc(r.name));
    b.addEventListener("click", () => { UI.roomId = r.id; renderRoomTabs(); if (UI.page === "plan") { const z = r.id !== null ? roomZone(r.name) : null; if (z) UI.floor = z[0]; } renderPage(); });
    tabs.appendChild(b);
  });
}

document.querySelectorAll(".bottom-nav button").forEach(b => b.addEventListener("click", () => {
  UI.page = b.dataset.page;
  if (UI.page === "events") UI.unread = 0;
  renderPage();
  window.scrollTo(0, 0);
}));
$("#addBtn").addEventListener("click", () => openAddDevice());
$("#roomsBtn").addEventListener("click", () => openRoomsMenu());
$("#userBtn").addEventListener("click", () => openUserMenu());

function renderPage() {
  document.querySelectorAll(".bottom-nav button").forEach(b => b.classList.toggle("active", b.dataset.page === UI.page));
  updateBadge();
  const c = $("#content");
  c.innerHTML = "";
  UI.cards = {};
  ({ devices: pageDevices, plan: pagePlan, energy: pageEnergy, events: pageEvents })[UI.page](c);
  onTick(UI.engine.state);
}

function updateBadge() {
  const b = $("#eventsBadge");
  b.textContent = UI.unread > 99 ? "99+" : UI.unread;
  b.classList.toggle("hidden", !UI.unread);
}

// ---------- обновление каждую секунду ----------

function onTick(st) {
  if (!st || !UI.engine) return;
  $("#batteryChip").textContent = `${st.charge > 1 ? "⚡" : "🔋"} ${Math.round(st.level * 100)}%  ·  ☀️ ${formatPower(st.generation)}`;
  updateEnergyBlocks(st);
  Object.keys(UI.cards).forEach(id => updateCard(Number(id)));
  const sum = $("#summary");
  if (sum) {
    const devs = home().devices;
    sum.textContent = `Устройств: ${devs.length} · включено: ${devs.filter(d => d.on).length} · нагрузка: ${formatPower(UI.engine.load())}`;
  }
  if (UI.page === "plan") updatePlanMarkers();
  if (UI.sheetLive) UI.sheetLive();
}

function onEvent(ev, toast, color) {
  if (UI.page === "events") prependEvent(ev);
  else { UI.unread++; updateBadge(); }
  if (toast) showToast(ev.icon, ev.text, color || { energy: "#f5b301", security: "#e5484d" }[ev.cat] || "#00b96b");
}

function showToast(icon, text, color) {
  const box = $("#toasts");
  const t = h("div", "toast", `<span class="ti">${icon}</span><span>${esc(text)}</span>`);
  t.style.borderLeftColor = color;
  box.appendChild(t);
  while (box.children.length > 3) box.firstChild.remove();
  setTimeout(() => { t.classList.add("out"); setTimeout(() => t.remove(), 450); }, 4500);
}

// ---------- энергия (мини-карточка и подробности) ----------

function batteryColor(level) { return level > 0.5 ? "#00b96b" : level > 0.2 ? "#f5a623" : "#e5484d"; }

function energyMiniCard() {
  const card = h("div", "card");
  card.innerHTML = `
    <div class="row"><div class="section-title" style="margin:0">☀️ Солнечная энергия</div><div class="muted" data-e="time"></div></div>
    <div class="muted" data-e="weather" style="margin:2px 0 10px"></div>
    <div class="energy-mini">
      <div class="battery-bar"><div class="fill" data-e="fill"></div><div class="pct" data-e="pct"></div></div>
      <div class="flow" data-e="flow"></div><div class="muted" data-e="stored"></div>
    </div>
    <div style="margin-top:8px">
      <div class="kv"><span class="muted">☀️ Генерация</span><b data-e="gen" style="color:#c98a00"></b></div>
      <div class="kv"><span class="muted">🏠 Потребление дома</span><b data-e="load"></b></div>
      <div class="kv"><span class="muted">⚡ Источник питания</span><b data-e="source"></b></div>
      <div class="kv"><span class="muted">⏩ Скорость времени</span><b>${speedSelect()}</b></div>
    </div>`;
  bindSpeed(card);
  return card;
}

function speedSelect() {
  return `<select data-e="speed" style="width:auto;padding:6px 10px;font-size:14px">` +
    D.simSpeeds.map(([cap, m]) => `<option value="${m}" ${m === UI.engine.minutesPerTick ? "selected" : ""}>${cap}</option>`).join("") + "</select>";
}
function bindSpeed(root) {
  root.querySelectorAll('[data-e="speed"]').forEach(s => s.addEventListener("change", () => { UI.engine.minutesPerTick = Number(s.value); }));
}

function updateEnergyBlocks(st) {
  const set = (k, v, color) => document.querySelectorAll(`[data-e="${k}"]`).forEach(e => { e.textContent = v; if (color) e.style.color = color; });
  set("time", "🕒 " + st.time);
  set("weather", st.weather);
  document.querySelectorAll('[data-e="fill"]').forEach(f => { f.style.width = `calc(${st.level * 100}% - 6px)`; f.style.background = batteryColor(st.level); });
  set("pct", `${Math.round(st.level * 100)}%${st.charge > 1 ? " ⚡" : ""}`);
  if (st.charge > 1) set("flow", "Заряжается +" + formatPower(st.charge), "#00b96b");
  else if (st.discharge > 1) set("flow", "Разряжается −" + formatPower(st.discharge), "#e08a00");
  else if (st.level >= 0.999) set("flow", "Полностью заряжен", "#00b96b");
  else set("flow", "Резерв — питание от сети", "#e5484d");
  set("stored", `${formatEnergy(st.batteryWh)} из ${formatEnergy(C.BATTERY_CAPACITY_WH)}`);
  set("gen", formatPower(st.generation));
  set("load", formatPower(st.load));
  set("source", st.source);
  if (st.gridExport > 1) set("grid", "→ отдача " + formatPower(st.gridExport), "#00b96b");
  else if (st.gridImport > 1) set("grid", "← из сети " + formatPower(st.gridImport), "#e5484d");
  else set("grid", "нет", "");
  if (UI.page === "energy") updateEnergyPage(st);
}

// ---------- устройства ----------

function pageDevices(c) {
  c.appendChild(energyMiniCard());
  c.appendChild(h("div", "summary")).id = "summary";
  const devs = home().devices.filter(d => UI.roomId === null || d.roomId === UI.roomId);
  if (!devs.length) {
    const empty = h("div", "card empty", `<div class="big">📱</div><p class="muted">${UI.roomId === null ? "В доме пока нет устройств" : "В этой комнате пока нет устройств"}.<br>Выберите тип и модель из каталога.</p>`);
    const btn = h("button", "btn primary block", "Добавить устройство");
    btn.addEventListener("click", () => openAddDevice());
    empty.appendChild(btn);
    c.appendChild(empty);
    return;
  }
  const grid = h("div", "grid");
  devs.forEach(d => grid.appendChild(deviceCard(d)));
  c.appendChild(grid);
}

function deviceCard(d) {
  const m = MODELS[d.model], t = TYPES[d.type];
  const card = h("div", "dcard");
  card.innerHTML = `<div class="dtop"><span class="dicon">${t.icon}</span><label class="switch"><input type="checkbox"><span></span></label></div>
    <div class="dname">${esc(d.name)}</div><div class="dsub">${UI.roomId === null ? esc(UI.engine.roomName(d.roomId)) + " · " : ""}${esc(m.name)}</div>
    <div class="dstatus"></div>`;
  const input = card.querySelector("input");
  input.addEventListener("change", () => { UI.engine.setOn(d, input.checked); updateCard(d.id); });
  card.querySelector(".switch").addEventListener("click", e => e.stopPropagation());
  card.addEventListener("click", () => openDevice(d.id));
  UI.cards[d.id] = { card, input, status: card.querySelector(".dstatus"), html: null };
  updateCard(d.id);
  return card;
}

function updateCard(id) {
  const c = UI.cards[id], d = home().devices.find(x => x.id === id);
  if (!c || !d) return;
  const on = d.type === "robot_vacuum" ? ["cleaning", "returning"].includes(d.s.vac_state) || d.on : !!d.on;
  c.card.classList.toggle("on", on);
  if (c.input.checked !== !!d.on) c.input.checked = !!d.on;
  const html = deviceStatusHtml(d, UI.engine.readings[d.id]);
  if (html !== c.html) { c.html = html; c.status.innerHTML = html; }
}

// ---------- шторка ----------

function openSheet(title, opts) {
  opts = opts || {};
  const sheet = $("#sheet");
  sheet.classList.remove("hidden");
  sheet.classList.toggle("dark", !!opts.dark);
  $("#sheetTitle").textContent = title;
  $("#sheetBack").classList.toggle("hidden", !opts.back);
  $("#sheetBack").onclick = opts.back || null;
  const body = $("#sheetBody");
  body.innerHTML = "";
  body.scrollTop = 0;
  UI.sheetLive = null;
  document.body.style.overflow = "hidden";
  return body;
}
function closeSheet() {
  $("#sheet").classList.add("hidden");
  $("#sheetBody").innerHTML = "";
  UI.sheetLive = null;
  UI.sheetDeviceId = null;
  document.body.style.overflow = "";
  if (UI.engine) renderPage();
}
$("#sheetClose").addEventListener("click", closeSheet);
document.querySelector(".sheet-backdrop").addEventListener("click", closeSheet);

// ---------- меню ----------

function openUserMenu() {
  const body = openSheet("👤 " + UI.user.username);
  const list = h("div", "menu-list");
  const info = h("div", "card", `<div class="muted">Данные дома хранятся на этом устройстве. Устройств: ${home().devices.length}, комнат: ${home().rooms.length}.</div>`);
  const out = h("button", "btn danger block", "Выйти из аккаунта");
  out.addEventListener("click", logout);
  list.append(info, out);
  body.appendChild(list);
}

function openRoomsMenu() {
  const body = openSheet("Комнаты");
  const add = h("div", "card stack");
  add.innerHTML = `<div class="section-title" style="margin:0">Новая комната</div><input placeholder="Название комнаты" maxlength="30"><div class="error"></div>`;
  const btn = h("button", "btn primary", "Добавить комнату");
  add.appendChild(btn);
  btn.addEventListener("click", () => {
    const name = add.querySelector("input").value.trim();
    if (!name) return;
    if (home().rooms.some(r => r.name.toLowerCase() === name.toLowerCase())) { add.querySelector(".error").textContent = "Такая комната уже есть"; return; }
    const room = { id: home().nextId++, name };
    home().rooms.push(room);
    UI.engine.roomTemps[room.id] = roomBaselineTemp(UI.engine.simMinutes);
    Store.save();
    UI.roomId = room.id;
    renderRoomTabs();
    closeSheet();
  });
  body.appendChild(add);
  const list = h("div", "card stack");
  list.innerHTML = `<div class="section-title" style="margin:0">Удалить комнату</div>`;
  home().rooms.forEach(r => {
    const count = home().devices.filter(d => d.roomId === r.id).length;
    const row = h("div", "row", `<span>${esc(r.name)} <span class="muted">· устройств: ${count}</span></span>`);
    const del = h("button", "btn danger", "Удалить");
    del.style.padding = "8px 12px";
    del.addEventListener("click", () => {
      if (!confirm(`Удалить комнату «${r.name}»?${count ? `\nВместе с ней будут удалены устройства: ${count}.` : ""}`)) return;
      home().rooms = home().rooms.filter(x => x.id !== r.id);
      home().devices = home().devices.filter(d => d.roomId !== r.id);
      Store.save();
      if (UI.roomId === r.id) UI.roomId = null;
      renderRoomTabs();
      UI.engine.recalc();
      openRoomsMenu();
    });
    row.appendChild(del);
    list.appendChild(row);
  });
  body.appendChild(list);
}

// ---------- добавление устройства ----------

function openAddDevice() {
  const body = openSheet("Добавить устройство", { dark: true });
  const search = h("input");
  search.placeholder = "🔍 Поиск по типу или модели";
  body.appendChild(search);
  const holder = h("div", "stack");
  body.appendChild(holder);
  const draw = () => {
    const q = search.value.trim().toLowerCase();
    holder.innerHTML = "";
    const card = h("div", "dark-card");
    card.innerHTML = `<div style="font-weight:700;font-size:17px">Добавление устройства вручную</div>`;
    D.groups.forEach(g => {
      const types = g.types.filter(t => !q || t.name.toLowerCase().includes(q) || D.catalog[t.code].some(m => m.name.toLowerCase().includes(q)));
      if (!types.length) return;
      card.appendChild(h("div", "cat-group", esc(g.name)));
      const tiles = h("div", "tiles");
      types.forEach(t => {
        const b = h("button", "tile", `<span>${t.icon}</span>${esc(t.name)}`);
        b.addEventListener("click", () => openModels(t.code, q));
        tiles.appendChild(b);
      });
      card.appendChild(tiles);
    });
    holder.appendChild(card);
  };
  search.addEventListener("input", draw);
  draw();
}

function openModels(typeCode, query) {
  const t = TYPES[typeCode], models = D.catalog[typeCode];
  const body = openSheet(`${t.icon} ${t.name}`, { dark: true, back: openAddDevice });
  body.appendChild(h("div", "hint-dark", `${models.length} ${plural(models.length, "модель", "модели", "моделей")} — отличаются мощностью и возможностями управления.`));
  models.forEach(m => {
    const card = h("div", "model" + (query && m.name.toLowerCase().includes(query) ? " hl" : ""));
    const feats = m.caps.length ? m.caps.map(c => `<span class="feat">${esc(D.capNames[c] || c)}</span>`).join(" ") : `<span class="hint-dark">Только включение / выключение</span>`;
    card.innerHTML = `<div class="row" style="align-items:flex-start"><div class="mname">${esc(m.name)}</div></div>
      <div class="mdesc">${esc(m.desc)}</div><div style="font-size:13px;color:#d0d0d6">⚡ ${modelPowerText(m)}${m.battery ? " · 🔋 " + esc(m.battery) : ""}</div>
      <div class="chips" style="gap:6px">${feats}</div>`;
    const pick = h("button", "btn primary", "Выбрать");
    pick.style.padding = "8px 16px";
    pick.addEventListener("click", () => openAddForm(m.code, query));
    card.querySelector(".row").appendChild(pick);
    body.appendChild(card);
  });
}

function openAddForm(modelCode, query) {
  const m = MODELS[modelCode], t = TYPES[m.type];
  const body = openSheet(m.name, { dark: true, back: () => openModels(m.type, query) });
  body.innerHTML = `<div style="text-align:center;font-size:64px">${t.icon}</div>
    <div style="text-align:center" class="hint-dark">${esc(t.name)} · ${modelPowerText(m)}</div>
    <div class="hint-dark">Название устройства</div><input id="newName" maxlength="40" value="${esc(t.name)}">
    <div class="hint-dark">Комната</div><select id="newRoom">${home().rooms.map(r => `<option value="${r.id}" ${r.id === UI.roomId ? "selected" : ""}>${esc(r.name)}</option>`).join("")}</select>
    <div class="error" id="newErr"></div>`;
  const btn = h("button", "btn primary block", "Добавить устройство");
  btn.addEventListener("click", () => {
    const name = $("#newName").value.trim();
    if (!name) { $("#newErr").textContent = "Введите название"; return; }
    if (!home().rooms.length) { $("#newErr").textContent = "Сначала добавьте комнату"; return; }
    const d = addDevice(home(), Number($("#newRoom").value), modelCode, name);
    Store.save();
    UI.engine.log("device", "➕", `Добавлено устройство: ${d.name} (${UI.engine.roomName(d.roomId)})`, true);
    UI.engine.recalc();
    closeSheet();
  });
  body.appendChild(btn);
}

// ---------- окно управления устройством ----------

function openDevice(id) {
  const d = home().devices.find(x => x.id === id);
  if (!d) return;
  const m = MODELS[d.model], t = TYPES[d.type], caps = m.caps, s = d.s, eng = UI.engine;
  const body = openSheet(d.name);
  UI.sheetDeviceId = id;
  const changed = () => { eng.changed(); refresh(); };

  // шапка с питанием
  const head = h("div", "card dev-head");
  head.innerHTML = `<span class="dicon">${t.icon}</span><div class="info"><div class="name">${esc(d.name)}</div>
    <div class="muted">${esc(m.name)}</div><div class="muted">📍 ${esc(eng.roomName(d.roomId))}</div></div>
    <label class="switch"><input type="checkbox"><span></span></label>`;
  const power = head.querySelector("input");
  power.checked = !!d.on;
  power.addEventListener("change", () => { eng.setOn(d, power.checked); refresh(); });
  body.appendChild(head);
  const live = h("div", "live");
  body.appendChild(live);

  const section = (title, valueText) => {
    const box = h("div");
    const tt = h("div", "ctl-title", `<span>${esc(title)}</span><span class="val"></span>`);
    if (valueText) tt.querySelector(".val").textContent = valueText;
    box.appendChild(tt);
    body.appendChild(box);
    return [box, tt.querySelector(".val")];
  };
  const slider = (title, key, lo, hi, fmt, step, cls, onInput) => {
    step = step || 1;
    const [box, val] = section(title);
    const r = h("input");
    r.type = "range"; r.min = lo; r.max = hi; r.step = step; r.value = s[key] ?? lo;
    if (cls) r.className = cls;
    const paint = () => { val.textContent = fmt(Number(r.value)); r.style.setProperty("--p", ((r.value - lo) / (hi - lo) * 100) + "%"); };
    r.addEventListener("input", () => { s[key] = Number(r.value); paint(); if (onInput) onInput(); changed(); });
    paint();
    box.appendChild(r);
    return r;
  };
  const toggleRow = (title, checked, onChange) => {
    const row = h("div", "row", `<span class="ctl-title" style="margin:0">${esc(title)}</span><label class="switch"><input type="checkbox"><span></span></label>`);
    const inp = row.querySelector("input");
    inp.checked = checked;
    inp.addEventListener("change", () => onChange(inp.checked));
    body.appendChild(row);
    return inp;
  };
  const chips = (title, options, current, onPick) => {
    const [box] = section(title);
    const wrap = h("div", "chips");
    options.forEach(opt => {
      const b = h("button", "chip" + (opt === current ? " active" : ""), esc(opt));
      b.addEventListener("click", () => { wrap.querySelectorAll(".chip").forEach(x => x.classList.toggle("active", x === b)); onPick(opt); });
      wrap.appendChild(b);
    });
    box.appendChild(wrap);
    return wrap;
  };

  let extraRefresh = () => {};

  // --- специальные визуализации ---
  if (caps.includes("video")) {
    const cam = new CameraView(body, eng, d);
    const row = h("div", "btn-row");
    if (cam.ptz) {
      [["◀ Повернуть", -0.25], ["Повернуть ▶", 0.25]].forEach(([cap, v]) => { const b = h("button", "btn", cap); b.addEventListener("click", () => cam.panBy(v)); row.appendChild(b); });
    }
    const shot = h("button", "btn", "📸 Снимок");
    shot.addEventListener("click", () => { cam.snapshot(); showToast("📸", "Снимок сохранён в «Загрузки»", "#00b96b"); });
    row.appendChild(shot);
    body.appendChild(row);
  }
  if (d.type === "kettle") {
    new KettleView(body, d);
    const boil = h("button", "btn primary block");
    boil.style.minHeight = "50px";
    boil.addEventListener("click", () => { eng.setOn(d, !d.on); refresh(); });
    body.appendChild(boil);
    const presets = [[40, "детская смесь"], [60, "белый чай"], [70, "зелёный чай"], [80, "улун"], [90, "кофе"], [100, "кипяток"]];
    const [tbox, tval] = section("Температура нагрева");
    const pwrap = h("div", "chips");
    const tr = h("input");
    tr.type = "range"; tr.min = 40; tr.max = 100; tr.value = s.target_temp;
    const syncT = () => {
      tval.textContent = tr.value + " °C"; tr.style.setProperty("--p", ((tr.value - 40) / 60 * 100) + "%");
      pwrap.querySelectorAll(".chip").forEach(c => c.classList.toggle("active", Number(c.dataset.t) === Number(tr.value)));
    };
    presets.forEach(([tt, cap]) => {
      const b = h("button", "chip", `${tt}° ${cap}`); b.dataset.t = tt;
      b.addEventListener("click", () => { tr.value = tt; s.target_temp = tt; syncT(); changed(); });
      pwrap.appendChild(b);
    });
    tr.addEventListener("input", () => { s.target_temp = Number(tr.value); syncT(); changed(); });
    tbox.append(pwrap, tr); syncT();
    const cap = m.capacity_ml || 1700;
    const [wbox, wval] = section("Воды в чайнике");
    const wr = h("input");
    wr.type = "range"; wr.min = 0; wr.max = cap; wr.step = 50; wr.value = s.water_ml || 0;
    const setWater = ml => {
      const old = s.water_ml || 0;
      ml = Math.max(0, Math.min(cap, ml));
      if (ml > old) s.water_temp = (old * (s.water_temp ?? C.ROOM_TEMP) + (ml - old) * C.ROOM_TEMP) / ml;
      else if (ml === 0) s.water_temp = C.ROOM_TEMP;
      s.water_ml = ml; wr.value = ml;
      wval.textContent = `${(ml / 1000).toFixed(2).replace(".", ",")} л из ${(cap / 1000).toFixed(1).replace(".", ",")} л`;
      wr.style.setProperty("--p", (ml / cap * 100) + "%");
      changed();
    };
    wr.addEventListener("input", () => setWater(Number(wr.value)));
    const wrow = h("div", "btn-row");
    [["💧 До MAX", () => cap], ["+250 мл", () => (s.water_ml || 0) + 250], ["Вылить", () => 0]].forEach(([c2, f]) => {
      const b = h("button", "btn", c2); b.style.padding = "10px 6px"; b.addEventListener("click", () => setWater(f())); wrow.appendChild(b);
    });
    wbox.append(wr, wrow);
    wval.textContent = `${((s.water_ml || 0) / 1000).toFixed(2).replace(".", ",")} л из ${(cap / 1000).toFixed(1).replace(".", ",")} л`;
    wr.style.setProperty("--p", ((s.water_ml || 0) / cap * 100) + "%");
    extraRefresh = () => {
      if ((s.water_ml || 0) < C.MIN_KETTLE_WATER_ML) { boil.textContent = "💧 Налейте воду (минимум 150 мл)"; boil.className = "btn block"; }
      else if (kettleHeating(d)) {
        const left = (s.target_temp - s.water_temp) * s.water_ml / 1000 * 4186 / (m.power * C.KETTLE_SPEEDUP);
        boil.textContent = `⏹ Остановить нагрев · ≈${Math.round(left)} сек`; boil.className = "btn orange block";
      } else if (d.on) { boil.textContent = "⏹ Выключить поддержание"; boil.className = "btn amber block"; }
      else { boil.textContent = s.target_temp >= 100 ? "🔥 Вскипятить" : `🔥 Нагреть до ${s.target_temp} °C`; boil.className = "btn primary block"; }
    };
  }
  if (d.type === "air_conditioner" || d.type === "heater") {
    if (d.type === "air_conditioner") new ClimateView(body, eng, d); else new HeaterView(body, eng, d);
    const [lo, hi] = D.temps[d.type];
    const dial = new ThermostatDial(body, lo, hi, s.target_temp, () => {
      const rt = eng.roomTemps[d.roomId] ?? C.ROOM_TEMP, [st, col] = climateStatus(d, rt);
      return [rt, st, col];
    }, v => { s.target_temp = v; d._active = true; changed(); });
    extraRefresh = () => dial.render();
  }
  if (d.type === "robot_vacuum") {
    new VacuumView(body, d);
    const row = h("div", "btn-row");
    const main = h("button", "btn primary"), homeBtn = h("button", "btn", "🏠 На базу");
    main.addEventListener("click", () => {
      const st = s.vac_state || "docked";
      if (st === "cleaning") { s.vac_state = "paused"; eng.log("device", "⏸", d.name + ": пауза"); changed(); }
      else if (st === "paused") { s.vac_state = "cleaning"; changed(); }
      else { eng.setOn(d, true); refresh(); }
    });
    homeBtn.addEventListener("click", () => { if (["cleaning", "paused"].includes(s.vac_state)) { if (d.on) eng.setOn(d, false); else { s.vac_state = "returning"; s.vac_return = 0; changed(); } refresh(); } });
    row.append(main, homeBtn);
    body.appendChild(row);
    extraRefresh = () => {
      const st = s.vac_state || "docked";
      main.textContent = { cleaning: "⏸ Пауза", paused: "▶ Продолжить", returning: "↩️ Едет на базу…", docked: "▶ Начать уборку" }[st];
      main.disabled = st === "returning";
      homeBtn.disabled = !["cleaning", "paused"].includes(st);
    };
  }
  if (d.type === "washer") {
    new WasherView(body, d);
    const btn = h("button", "btn primary block");
    btn.style.minHeight = "50px";
    btn.addEventListener("click", () => { eng.setOn(d, !d.on); refresh(); });
    body.appendChild(btn);
    body.appendChild(h("div", "muted", "Время стирки идёт по часам дома (скорость симуляции)."));
    extraRefresh = () => {
      btn.textContent = d.on ? "⏹ Остановить стирку" : `▶ Запустить «${s.mode}»`;
      btn.className = d.on ? "btn orange block" : "btn primary block";
    };
  }
  let lightPrev = null;
  if (t.group === LIGHT_GROUP) lightPrev = new LightPreview(body, d);

  // --- общие элементы управления по функциям модели ---
  if (caps.includes("lock")) {
    const [box] = section("Замок");
    const b = h("button", "btn block");
    const paint = () => { b.textContent = s.locked ? "🔒 Закрыт — нажмите, чтобы открыть" : "🔓 Открыт — нажмите, чтобы закрыть"; b.className = s.locked ? "btn primary block" : "btn amber block"; };
    b.addEventListener("click", () => { s.locked = !s.locked; paint(); eng.log("security", s.locked ? "🔒" : "🔓", `${d.name}: ${s.locked ? "закрыт" : "открыт"}`); changed(); });
    paint(); box.appendChild(b);
  }
  if (caps.includes("mode")) {
    chips(d.type === "tv" ? "Источник сигнала" : "Режим работы", D.modes[d.type].map(x => x[0]), s.mode, v => { s.mode = v; changed(); });
  }
  if (caps.includes("target_temp") && !["kettle", "air_conditioner", "heater"].includes(d.type)) {
    const [lo, hi] = D.temps[d.type];
    slider(d.type === "water_heater" ? "Температура воды" : "Температура", "target_temp", lo, hi, v => v + " °C");
  }
  if (caps.includes("brightness")) slider(d.type === "panel" ? "Яркость экрана" : "Яркость", "brightness", 1, 100, v => v + "%");
  if (caps.includes("color_temp")) {
    slider("Цветовая температура", "color_temp", 2700, 6500, v => `${v} K · ${v <= 3300 ? "тёплый" : v >= 5300 ? "холодный" : "нейтральный"}`, 100, "ct",
      () => { if (s.color) { s.color = null; body.querySelectorAll(".swatch").forEach(x => x.classList.remove("active")); } });
  }
  if (caps.includes("color")) {
    const [box] = section("Цвет подсветки");
    const wrap = h("div", "chips");
    const white = h("button", "chip", "Белый");
    white.addEventListener("click", () => { s.color = null; wrap.querySelectorAll(".swatch").forEach(x => x.classList.remove("active")); changed(); });
    wrap.appendChild(white);
    D.colorPresets.forEach(col => {
      const sw = h("button", "swatch" + (s.color === col ? " active" : ""));
      sw.style.background = col;
      sw.addEventListener("click", () => { s.color = col; wrap.querySelectorAll(".swatch").forEach(x => x.classList.toggle("active", x === sw)); changed(); });
      wrap.appendChild(sw);
    });
    const custom = h("input");
    custom.type = "color"; custom.value = s.color || "#ffd27f";
    custom.style.cssText = "width:44px;height:34px;padding:2px;border-radius:10px";
    custom.addEventListener("input", () => { s.color = custom.value; wrap.querySelectorAll(".swatch").forEach(x => x.classList.remove("active")); changed(); });
    wrap.appendChild(custom);
    box.appendChild(wrap);
  }
  if (caps.includes("fan_speed")) { const lv = m.levels || 3; slider("Скорость вентилятора", "fan_speed", 1, lv, v => `${v} из ${lv}`); }
  if (caps.includes("volume")) slider("Громкость", "volume", 0, 100, v => v + "%");
  if (caps.includes("current")) slider("Ток зарядки", "current", 6, m.max_current, v => `${v} А · ${(v * C.GRID_VOLTAGE / 1000).toFixed(1).replace(".", ",")} кВт`);
  if (caps.includes("load")) slider("Подключённая нагрузка", "load", 0, m.power, formatPower, 10);
  if (caps.includes("keys")) {
    if (!s.keys) s.keys = new Array(m.keys || 1).fill(false);
    s.keys.forEach((k, i) => toggleRow(`Клавиша ${i + 1}`, k, v => { s.keys[i] = v; changed(); }));
  }
  Object.entries(D.boolCaps).forEach(([key, title]) => {
    if (caps.includes(key)) toggleRow(title, !!s[key], v => { s[key] = v; changed(); });
  });
  let timerHint = null, timerSel = null;
  if (caps.includes("timer")) {
    const [box] = section("Таймер выключения");
    timerSel = h("select");
    timerSel.innerHTML = D.timerOptions.map(([cap, mins]) => `<option value="${mins}">${cap}</option>`).join("");
    timerSel.value = s.off_at !== undefined && s.off_at !== null ? (s.timer_min || 0) : 0;
    timerSel.addEventListener("change", () => {
      const mins = Number(timerSel.value);
      if (mins) { s.timer_min = mins; s.off_at = eng.simMinutes + mins; if (!d.on) eng.setOn(d, true); }
      else { delete s.timer_min; delete s.off_at; }
      changed();
    });
    timerHint = h("div", "muted");
    box.append(timerSel, timerHint);
  }
  if (caps.includes("scenes")) {
    const [box] = section("Сценарии (по нажатию кнопки)");
    D.scenes.forEach(([code, cap]) => {
      const b = h("button", "btn block", esc(cap));
      b.style.marginBottom = "8px";
      b.addEventListener("click", () => { const n = eng.runScene(code, d.roomId); showToast("🎬", `Сценарий выполнен, изменено устройств: ${n}`, "#00b96b"); refresh(); });
      box.appendChild(b);
    });
  }
  if (m.battery) section("Питание", `🔋 ${s.battery ?? 100}% · ${m.battery}`);
  body.appendChild(h("div", "muted", `ℹ️ ${esc(m.desc)} · ${modelPowerText(m)}`));

  // нижние кнопки
  const actions = h("div", "btn-row");
  const rename = h("button", "btn", "Переименовать");
  rename.addEventListener("click", () => {
    const name = prompt("Новое название:", d.name);
    if (name && name.trim()) { d.name = name.trim().slice(0, 40); Store.save(); $("#sheetTitle").textContent = d.name; head.querySelector(".name").textContent = d.name; }
  });
  const move = h("select");
  move.innerHTML = `<option value="">Переместить…</option>` + home().rooms.filter(r => r.id !== d.roomId).map(r => `<option value="${r.id}">${esc(r.name)}</option>`).join("");
  move.addEventListener("change", () => { if (!move.value) return; d.roomId = Number(move.value); delete s.plan; Store.save(); closeSheet(); });
  const del = h("button", "btn danger", "Удалить");
  del.addEventListener("click", () => {
    if (!confirm(`Удалить устройство «${d.name}»?`)) return;
    home().devices = home().devices.filter(x => x.id !== d.id);
    eng.log("device", "🗑", "Удалено устройство: " + d.name);
    Store.save(); eng.recalc(); closeSheet();
  });
  actions.append(rename, del);
  body.append(actions, move);

  function refresh() {
    if (power.checked !== !!d.on) power.checked = !!d.on;
    const reading = eng.readings[d.id];
    live.innerHTML = d.on || d.type === "robot_vacuum"
      ? `${reading ? `<b>${esc(reading)}</b> · ` : ""}Потребление сейчас: <b>≈${formatPower(devicePower(d))}</b>`
      : "<b>Выключено</b>";
    if (timerHint) {
      if (s.off_at !== undefined && s.off_at !== null) timerHint.textContent = `Выключится в ${simTimeText(s.off_at)} (по времени дома)`;
      else { timerHint.textContent = "Таймер не установлен"; if (Number(timerSel.value)) timerSel.value = 0; }
    }
    extraRefresh();
  }
  UI.sheetLive = refresh;
  refresh();
}

// ---------- план дома ----------

function planGlow(d) {
  const t = d.type, s = d.s;
  if (t === "robot_vacuum") return ["cleaning", "returning"].includes(s.vac_state) ? [0, 185, 107] : null;
  if (!d.on) return null;
  if (TYPES[t].group === LIGHT_GROUP) return lightRgb(d);
  if (t === "air_conditioner") return s.mode === "Обогрев" ? [255, 122, 69] : [61, 157, 245];
  if (t === "heater" || t === "water_heater" || (t === "kettle" && kettleHeating(d))) return [255, 107, 61];
  if (t === "camera") return [229, 72, 77];
  return [0, 185, 107];
}

function devicePlanPos(d, index) {
  if (d.s.plan) return [d.s.plan.floor, d.s.plan.x, d.s.plan.y];
  const [floor, x, y] = roomZone(UI.engine.roomName(d.roomId));
  return [floor, x + ((index % 4) - 1.5) * 0.045, y + Math.floor(index / 4) * 0.06 - 0.03];
}

function pagePlan(c) {
  const chipsRow = h("div", "chips");
  chipsRow.style.marginBottom = "10px";
  D.planFloors.forEach(([code, cap]) => {
    const b = h("button", "chip" + (code === UI.floor ? " active" : ""), cap);
    b.addEventListener("click", () => { UI.floor = code; renderPage(); });
    chipsRow.appendChild(b);
  });
  c.appendChild(chipsRow);
  const wrap = h("div", "plan-wrap");
  const file = D.planFloors.find(f => f[0] === UI.floor)[2].replace(".png", ".jpg");
  wrap.innerHTML = `<img src="img/${file}" alt="План">`;
  c.appendChild(wrap);
  c.appendChild(h("div", "summary", "Светится — включено · перетащите значок, чтобы переставить · нажмите — управление"));
  const counters = {};
  const tip = h("div", "plan-tip hidden");
  wrap.appendChild(tip);
  home().devices.forEach(d => {
    const idx = counters[d.roomId] = (counters[d.roomId] ?? -1) + 1;
    const [floor, x, y] = devicePlanPos(d, idx);
    if (floor !== UI.floor) return;
    const mk = h("div", "marker", TYPES[d.type].icon);
    mk.dataset.id = d.id;
    mk.style.left = `calc(8px + ${x} * (100% - 16px))`;
    mk.style.top = `calc(8px + ${y} * (100% - 16px))`;
    let start = null, dragging = false;
    mk.addEventListener("pointerdown", e => { mk.setPointerCapture(e.pointerId); start = [e.clientX, e.clientY]; dragging = false; e.preventDefault(); });
    mk.addEventListener("pointermove", e => {
      if (!start) return;
      if (!dragging && Math.abs(e.clientX - start[0]) + Math.abs(e.clientY - start[1]) > 6) dragging = true;
      if (dragging) {
        const r = wrap.getBoundingClientRect();
        const nx = Math.min(0.99, Math.max(0.01, (e.clientX - r.left - 8) / (r.width - 16)));
        const ny = Math.min(0.99, Math.max(0.01, (e.clientY - r.top - 8) / (r.height - 16)));
        d.s.plan = { floor: UI.floor, x: nx, y: ny };
        mk.style.left = `calc(8px + ${nx} * (100% - 16px))`; mk.style.top = `calc(8px + ${ny} * (100% - 16px))`;
        tip.classList.add("hidden");
      }
    });
    mk.addEventListener("pointerup", () => {
      if (!start) return;
      start = null;
      if (dragging) { Store.save(); return; }
      openDevice(d.id);
    });
    mk.addEventListener("pointerenter", e => {
      if (e.pointerType !== "mouse") return;
      tip.textContent = d.name + " · " + deviceStatusHtml(d, UI.engine.readings[d.id]).replace(/<[^>]+>/g, "");
      tip.style.left = mk.style.left; tip.style.top = mk.style.top; tip.classList.remove("hidden");
    });
    mk.addEventListener("pointerleave", () => tip.classList.add("hidden"));
    wrap.appendChild(mk);
  });
  updatePlanMarkers();
}

function updatePlanMarkers() {
  document.querySelectorAll(".marker").forEach(mk => {
    const d = home().devices.find(x => x.id === Number(mk.dataset.id));
    if (!d) return;
    const g = planGlow(d);
    mk.style.borderColor = g ? rgbCss(g) : "#b9c7d2";
    mk.style.boxShadow = g ? `0 0 18px 8px ${rgbCss(g, 0.55)}` : "none";
    mk.classList.toggle("dim", UI.roomId !== null && d.roomId !== UI.roomId);
  });
}

// ---------- энергия ----------

function pageEnergy(c) {
  const st = UI.engine.state;
  c.innerHTML = `
    <div class="tiles4">
      <div class="card stat"><div class="t">☀️ Выработано сегодня</div><div class="v" id="tGen" style="color:#c98a00"></div><div class="s" id="tGenS"></div></div>
      <div class="card stat"><div class="t">💰 Сэкономлено сегодня</div><div class="v" id="tSaved" style="color:#00b96b"></div><div class="s" id="tSavedS"></div></div>
      <div class="card stat"><div class="t">🔌 Куплено из сети</div><div class="v" id="tBought"></div><div class="s" id="tBoughtS"></div></div>
      <div class="card stat"><div class="t">🌱 CO₂ не выброшено</div><div class="v" id="tCo2"></div><div class="s">${C.CO2_KG_PER_KWH} кг CO₂ на кВт·ч сети РК</div></div>
    </div>
    <div class="card" style="margin-top:12px"><div class="section-title">📊 Энергия за сутки</div><div id="chartHost"></div></div>
    <div class="stack" style="margin-top:12px">
      <div class="card" id="detailsCard"></div>
      <div class="cols3 stack">
        <div class="card"><div class="row"><div class="section-title" style="margin:0">🌿 Эко-режим</div><label class="switch"><input type="checkbox" id="ecoSwitch"><span></span></label></div>
          <p class="muted">При заряде АКБ ниже ${C.ECO_OFF_LEVEL * 100}% автоматически отключаются мощные второстепенные устройства и включаются обратно при ${C.ECO_RESTORE_LEVEL * 100}%: ${D.ecoShedTypes.map(t => TYPES[t].name.toLowerCase()).join(", ")}. Охрана, датчики и холодильник продолжают работать.</p>
          <b id="ecoStatus"></b></div>
        <div class="card"><div class="section-title">☀️ Излишки солнца</div>
          <p class="muted">Зарядка авто и бойлер с режимом «Только от излишков солнца» работают, лишь когда панели дают больше, чем потребляет дом, а АКБ заряжена от ${C.SOLAR_ONLY_MIN_LEVEL * 100}%.</p>
          <b id="surplus"></b><div id="solarList" style="margin-top:6px;font-size:14px"></div></div>
        <div class="card"><div class="section-title">💰 За всё время</div>
          <div class="kv"><span class="muted">Тариф, ₸/кВт·ч</span><input id="tariff" type="number" step="0.5" min="1" style="width:90px;padding:6px 8px"></div>
          <div class="kv"><span class="muted">☀️ Выработано</span><b id="aGen"></b></div>
          <div class="kv"><span class="muted">💰 Сэкономлено</span><b id="aSaved" style="color:#00b96b"></b></div>
          <div class="kv"><span class="muted">🔌 Оплачено за сеть</span><b id="aBought"></b></div>
          <div class="kv"><span class="muted">🌱 CO₂ не выброшено</span><b id="aCo2"></b></div>
          <div class="kv"><span class="muted">🌳 Как деревьев за год</span><b id="aTrees"></b></div></div>
      </div>
    </div>`;
  new EnergyChart($("#chartHost"), UI.engine);
  const det = $("#detailsCard");
  det.appendChild(energyMiniCard());
  det.classList.remove("card");
  det.firstChild.insertAdjacentHTML("beforeend", `
    <div class="kv"><span class="muted">🔌 Обмен с сетью</span><b data-e="grid"></b></div>
    <div class="kv"><span class="muted">📈 Выработано за сутки</span><b id="dGen"></b></div>
    <div class="kv"><span class="muted">📉 Потреблено за сутки</span><b id="dCons"></b></div>`);
  const eco = $("#ecoSwitch");
  eco.checked = home().eco;
  eco.addEventListener("change", () => { home().eco = eco.checked; Store.save(); UI.engine.log("energy", "🌿", eco.checked ? "Эко-режим включён" : "Эко-режим выключен"); });
  const tariff = $("#tariff");
  tariff.value = home().tariff;
  tariff.addEventListener("change", () => { const v = Number(tariff.value); if (v > 0) { home().tariff = v; Store.save(); updateEnergyPage(UI.engine.state); } });
  if (st) updateEnergyPage(st);
}

function updateEnergyPage(st) {
  if (!$("#tGen")) return;
  const eng = UI.engine, hm = home(), tariff = hm.tariff;
  const gen = eng.today.gen / 1000, used = Math.max(0, eng.today.gen - eng.today.exp) / 1000, bought = eng.today.imp / 1000;
  const kwh = v => v.toFixed(2).replace(".", ",") + " кВт·ч";
  $("#tGen").textContent = kwh(gen); $("#tGenS").textContent = "в дом / в АКБ: " + kwh(used);
  $("#tSaved").textContent = formatMoney(used * tariff); $("#tSavedS").textContent = `по тарифу ${tariff} ₸/кВт·ч`;
  $("#tBought").textContent = formatMoney(bought * tariff); $("#tBought").style.color = bought > 0.01 ? "#e5484d" : "";
  $("#tBoughtS").textContent = kwh(bought) + " из сети";
  $("#tCo2").textContent = (gen * C.CO2_KG_PER_KWH).toFixed(1).replace(".", ",") + " кг";
  $("#dGen").textContent = formatEnergy(eng.today.gen); $("#dCons").textContent = formatEnergy(eng.today.cons);
  const tg = hm.totals.gen / 1000, tu = Math.max(0, hm.totals.gen - hm.totals.exp) / 1000, co2 = tg * C.CO2_KG_PER_KWH;
  $("#aGen").textContent = tg.toFixed(1).replace(".", ",") + " кВт·ч";
  $("#aSaved").textContent = formatMoney(tu * tariff);
  $("#aBought").textContent = formatMoney(hm.totals.imp / 1000 * tariff);
  $("#aCo2").textContent = co2.toFixed(1).replace(".", ",") + " кг";
  $("#aTrees").textContent = (co2 / C.CO2_PER_TREE_KG).toFixed(2).replace(".", ",");
  const shed = hm.devices.filter(d => d.s.eco_shed).map(d => d.name), es = $("#ecoStatus");
  if (!hm.eco) { es.textContent = "Эко-режим выключен"; es.style.color = "#8aa0b2"; }
  else if (shed.length) { es.textContent = "⚠️ Сейчас отключены: " + shed.join(", "); es.style.color = "#e08a00"; }
  else { es.textContent = `✅ Активен · АКБ ${Math.round(st.level * 100)}%`; es.style.color = "#00b96b"; }
  const surplus = st.generation - st.load;
  $("#surplus").textContent = surplus > 0 ? "Сейчас излишек: " + formatPower(surplus) : "Сейчас излишков нет";
  const solar = hm.devices.filter(d => d.s.solar_only);
  $("#solarList").innerHTML = solar.length ? solar.map(d => {
    const p = d._solar || 0;
    const stt = !d.on ? '<span style="color:#8aa0b2">выключено</span>' : p > 1 ? `<span style="color:#00b96b">работает · ${formatPower(p)}</span>` : '<span style="color:#e08a00">ждёт излишков</span>';
    return `${TYPES[d.type].icon} ${esc(d.name)} — ${stt}`;
  }).join("<br>") : '<span class="muted">Нет устройств с этим режимом</span>';
}

// ---------- события ----------

function pageEvents(c) {
  const row = h("div", "row");
  row.style.marginBottom = "10px";
  const chipsWrap = h("div", "chips");
  [["all", "Все"], ["energy", "⚡ Энергия"], ["device", "📱 Устройства"], ["security", "🛡 Охрана"]].forEach(([code, cap]) => {
    const b = h("button", "chip" + (code === UI.eventFilter ? " active" : ""), cap);
    b.addEventListener("click", () => { UI.eventFilter = code; renderPage(); });
    chipsWrap.appendChild(b);
  });
  const clear = h("button", "btn danger", "Очистить");
  clear.style.padding = "8px 12px";
  clear.addEventListener("click", () => { if (confirm("Очистить журнал событий?")) { home().events = []; Store.save(); renderPage(); } });
  row.append(chipsWrap, clear);
  c.appendChild(row);
  const list = h("div", "events");
  list.id = "eventsList";
  const evs = home().events.filter(e => UI.eventFilter === "all" || e.cat === UI.eventFilter).slice().reverse();
  if (!evs.length) list.appendChild(h("div", "ev muted", "Событий пока нет"));
  evs.forEach(e => list.appendChild(eventRow(e)));
  c.appendChild(list);
}
function eventRow(e) { return h("div", "ev " + e.cat, `<span class="tm">${e.t}</span><span>${e.icon}</span><span>${esc(e.text)}</span>`); }
function prependEvent(e) {
  const list = $("#eventsList");
  if (!list || (UI.eventFilter !== "all" && UI.eventFilter !== e.cat)) return;
  if (list.firstChild && list.firstChild.classList.contains("muted")) list.innerHTML = "";
  list.insertBefore(eventRow(e), list.firstChild);
}
