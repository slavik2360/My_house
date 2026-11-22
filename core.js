// Ядро веб-версии: данные каталога, хранение, пользователи и симуляция дома.
// Логика перенесена из настольной версии (home.py), каталог берётся из data.js.
"use strict";

const D = window.HOME_DATA;
const C = D.const;
const LIGHT_GROUP = "Освещение";
const SENSOR_GROUP = "Датчики";

const TYPES = {};
D.groups.forEach(g => g.types.forEach(t => { TYPES[t.code] = Object.assign({}, t, { group: g.name }); }));
const ROBOT_TYPES = ["robot_vacuum", "lawn_mower"];
const MODELS = {};
Object.values(D.catalog).forEach(models => models.forEach(m => { MODELS[m.code] = m; }));

// ---------- форматирование ----------

function formatPower(w) {
  if (Math.abs(w) >= 1000) return (w / 1000).toFixed(2).replace(".", ",") + " кВт";
  if (w > 0 && w < 10) return w.toFixed(1).replace(".", ",") + " Вт";
  return Math.round(w) + " Вт";
}
function formatEnergy(wh) {
  if (Math.abs(wh) >= 1000) return (wh / 1000).toFixed(2).replace(".", ",") + " кВт·ч";
  return Math.round(wh) + " Вт·ч";
}
function formatMoney(v) {
  return Math.round(v).toString().replace(/\B(?=(\d{3})+(?!\d))/g, " ") + " ₸";
}
function simTimeText(m) {
  const h = Math.floor(m / 60) % 24, mm = Math.floor(m % 60);
  return String(h).padStart(2, "0") + ":" + String(mm).padStart(2, "0");
}
function plural(n, one, few, many) {
  if (n % 10 === 1 && n % 100 !== 11) return one;
  if (n % 10 >= 2 && n % 10 <= 4 && !(n % 100 >= 12 && n % 100 <= 14)) return few;
  return many;
}
function esc(s) {
  return String(s).replace(/[&<>"']/g, ch => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
}

// ---------- устройства ----------

function modeFactor(type, mode) {
  const list = D.modes[type] || [];
  const found = list.find(x => x[0] === mode);
  return found ? found[1] : 1;
}
function isAlwaysOn(type) {
  return D.alwaysOnTypes.includes(type) || D.alwaysOnGroups.includes(TYPES[type].group);
}
function hasCap(d, cap) {
  const m = MODELS[d.model];
  return !!m && m.caps.includes(cap);
}

function defaultSettings(model) {
  const t = model.type, caps = model.caps, s = {};
  if (caps.includes("brightness")) s.brightness = 80;
  if (caps.includes("color_temp")) s.color_temp = 4000;
  if (caps.includes("color")) s.color = null;
  if (caps.includes("target_temp")) s.target_temp = D.temps[t][2];
  if (caps.includes("mode")) s.mode = D.modes[t][0][0];
  if (caps.includes("fan_speed")) s.fan_speed = Math.max(1, Math.floor((model.levels || 3) / 2));
  if (caps.includes("volume")) s.volume = 40;
  if (caps.includes("current")) s.current = Math.min(16, model.max_current);
  if (caps.includes("load")) s.load = 100;
  if (caps.includes("keys")) s.keys = new Array(model.keys || 1).fill(false);
  if (caps.includes("lock")) s.locked = true;
  Object.keys(D.boolCaps).forEach(key => {
    if (caps.includes(key)) s[key] = ["night_vision", "motion_alerts", "auto_lock", "led", "motion_light", "recording", "rain_sensor"].includes(key);
  });
  if (model.battery) s.battery = 62 + Math.floor(Math.random() * 39);
  if (t === "kettle") { s.water_ml = 1000; s.water_temp = C.ROOM_TEMP; }
  if (ROBOT_TYPES.includes(t)) Object.assign(s, { vac_state: "docked", vac_progress: 0, vac_battery: 100, vac_return: 0 });
  if (t === "lawn_mower") s.cut_height = 40;
  if (t === "irrigation") Object.assign(s, { irr_minutes: 10, irr_elapsed: 0, irr_water: 0, moisture: 35, water_total: 0 });
  if (t === "washer") s.wash_elapsed = 0;
  return s;
}

function washerTotal(s) { return D.washDurations[s.mode] || 90; }
function washerFraction(s) { return Math.min(1, (s.wash_elapsed || 0) / washerTotal(s)); }
function washerPhase(f) {
  let name = D.washPhases[0][1];
  D.washPhases.forEach(([start, phase]) => { if (f >= start) name = phase; });
  return name;
}
function kettleHeating(d) {
  const s = d.s;
  return !!d.on && (s.water_ml || 0) >= C.MIN_KETTLE_WATER_ML && (s.water_temp ?? C.ROOM_TEMP) < (s.target_temp ?? 100) - 0.05;
}

function devicePower(d, ignoreSolar) {
  const m = MODELS[d.model];
  if (!m) return 0;
  const s = d.s, caps = m.caps, t = d.type;
  let p = m.power;
  if (ROBOT_TYPES.includes(t)) {
    const st = s.vac_state || "docked";
    if (st === "cleaning" || st === "returning") return p * modeFactor(t, s.mode);
    if (st === "paused") return 3;
    return (s.vac_battery ?? 100) < 99.5 ? 25 : 2;
  }
  if (!d.on) return 0;
  if (s.solar_only && !ignoreSolar) return d._solar || 0;
  if (t === "irrigation") return p;
  if (t === "washer") {
    const ph = washerPhase(washerFraction(s));
    if (ph === "Нагрев воды") return p * modeFactor(t, s.mode);
    return { "Стирка": 150, "Полоскание": 120, "Отжим": 450 }[ph] ?? 2;
  }
  if (t === "kettle") return kettleHeating(d) ? p : (s.keep_warm ? p * 0.06 : 1);
  if (caps.includes("load")) p = s.load || 0;
  if (caps.includes("current")) p = (s.current || 16) * C.GRID_VOLTAGE;
  if (caps.includes("brightness")) p *= 0.1 + 0.9 * (s.brightness ?? 100) / 100;
  if (caps.includes("mode")) p *= modeFactor(t, s.mode);
  if (caps.includes("fan_speed")) { const lv = m.levels || 3; p *= 0.3 + 0.7 * (s.fan_speed ?? lv) / lv; }
  if ((t === "air_conditioner" || t === "heater") && d._active === false) p *= 0.3;
  return p * (D.duty[t] ?? 1);
}
function solarFullPower(d) { return devicePower(d, true) / (D.duty[d.type] ?? 1); }

function modelPowerText(m) {
  if (m.caps.includes("load")) return "нагрузка до " + formatPower(m.power);
  if (m.caps.includes("current")) return "до " + formatPower(m.power) + " (" + m.max_current + " А)";
  const duty = D.duty[m.type] ?? 1;
  return duty < 1 ? formatPower(m.power) + " (в среднем ≈" + formatPower(m.power * duty) + ")" : formatPower(m.power);
}

function roomBaselineTemp(simMinutes) {
  const hour = (simMinutes / 60) % 24;
  return 22 + 3.5 * Math.sin(2 * Math.PI * (hour - 9) / 24);
}

function climateStatus(d, roomTemp) {
  const s = d.s;
  if (!d.on) return ["Выключен", "#8aa0b2"];
  const target = s.target_temp ?? 22, active = d._active !== false;
  if (d.type === "heater") return active ? ["🔥 Нагревает комнату", "#e0662f"] : ["✅ Температура достигнута", "#00b96b"];
  const mode = s.mode || "Охлаждение";
  if (mode === "Вентиляция") return ["🌀 Вентиляция", "#5f7a8f"];
  if (mode === "Осушение") return ["💧 Осушение воздуха", "#3d9df5"];
  if (!active) return ["✅ Температура достигнута", "#00b96b"];
  if (mode === "Обогрев" || (mode === "Авто" && roomTemp < target)) return ["🔥 Обогревает комнату", "#e0662f"];
  return ["❄️ Охлаждает комнату", "#2f8de4"];
}

// цвет света: RGB или оттенок белого по цветовой температуре
function mixColor(a, b, t) {
  t = Math.max(0, Math.min(1, t));
  return a.map((v, i) => Math.round(v + (b[i] - v) * t));
}
function ctRgb(k) {
  const t = (k - 2700) / 3800, warm = [255, 177, 92], neutral = [255, 246, 229], cold = [185, 212, 255];
  return t < 0.5 ? mixColor(warm, neutral, t * 2) : mixColor(neutral, cold, (t - 0.5) * 2);
}
function hexRgb(hex) { const n = parseInt(hex.slice(1), 16); return [n >> 16 & 255, n >> 8 & 255, n & 255]; }
function rgbCss(c, a) { return a === undefined ? `rgb(${c[0]},${c[1]},${c[2]})` : `rgba(${c[0]},${c[1]},${c[2]},${a})`; }
function lightRgb(d) {
  if (d.s.color) return hexRgb(d.s.color);
  if (d.s.color_temp !== undefined) return ctRgb(d.s.color_temp);
  return ctRgb(2700);
}

function deviceStatusHtml(d, reading) {
  const m = MODELS[d.model] || { caps: [] }, s = d.s, t = d.type, caps = m.caps, group = TYPES[t].group;
  if (d._state === "broken") return `<span style="color:#e5484d;font-weight:700">⚠️ Неисправно</span> · ${esc(d._issue || "")}`;
  if (d._state === "offline") return `<span style="color:#e08a00;font-weight:700">📵 Нет связи</span> · устройство не отвечает`;
  if (s.battery !== undefined && s.battery < 20 && d.on) return `<span style="color:#e08a00;font-weight:700">🪫 Батарейка ${s.battery}%</span> · ${reading ? esc(reading) : "замените батарейку"}`;
  if (t === "irrigation") {
    const zones = m.zones || 1, per = s.irr_minutes || 10;
    if (d.on) {
      const el = s.irr_elapsed || 0, left = zones * per - el;
      return `💦 Полив зоны ${Math.min(zones, Math.floor(el / per) + 1)} из ${zones} · осталось ${Math.floor(left / 60)}:${String(Math.floor(left % 60)).padStart(2, "0")}`;
    }
    return `💧 Влажность почвы ${Math.round(s.moisture ?? 35)}%${s.irr_water ? ` · полито ${Math.round(s.irr_water)} л` : ""}`;
  }
  if (ROBOT_TYPES.includes(t)) {
    const info = D.robotInfo[t];
    const st = s.vac_state || "docked", bat = "🔋 " + Math.round(s.vac_battery ?? 100) + "%";
    if (st === "cleaning") return `${info.icon} ${info.verb} ${Math.round((s.vac_progress || 0) * 100)}% · ${bat}`;
    if (st === "paused") return `⏸ Пауза ${Math.round((s.vac_progress || 0) * 100)}% · ${bat}`;
    if (st === "returning") return `↩️ Едет на базу · ${bat}`;
    return `🏠 На базе · ${bat}${(s.vac_battery ?? 100) < 99.5 ? " ⚡" : ""}`;
  }
  if (t === "washer") {
    if (!d.on) return s.wash_done ? "✅ Стирка завершена" : "Выключена";
    const left = washerTotal(s) * (1 - washerFraction(s));
    return `${washerPhase(washerFraction(s))} · осталось ${Math.floor(left / 60)}:${String(Math.floor(left % 60)).padStart(2, "0")}`;
  }
  if (s.solar_only && d.on) {
    const p = d._solar || 0;
    return p > 1 ? "☀️ От солнца ≈" + formatPower(p) : "☀️ Ждёт излишков солнца";
  }
  if (t === "kettle") {
    const water = ((s.water_ml || 0) / 1000).toFixed(1).replace(".", ",") + " л", temp = Math.round(s.water_temp ?? C.ROOM_TEMP);
    if (!d.on) return `Выключен · ${water} · ${temp}°C`;
    if ((s.water_ml || 0) < C.MIN_KETTLE_WATER_ML) return "⚠️ Нет воды";
    if (kettleHeating(d)) return `🔥 Нагрев ${temp}→${s.target_temp}°C · ${water}`;
    return `♨️ Поддержание ${temp}°C · ${water}`;
  }
  if (!d.on) return group === SENSOR_GROUP ? "Отключён" : "Выключено";
  const parts = [];
  if (reading) parts.push(esc(reading));
  if (caps.includes("lock")) parts.push(s.locked ? "🔒 Закрыт" : "🔓 Открыт");
  if (caps.includes("color") && s.color) parts.push(`<span style="color:${esc(s.color)}">●</span>`);
  if (caps.includes("brightness")) parts.push(s.brightness + "%");
  if (caps.includes("color_temp") && !s.color) parts.push(s.color_temp + " K");
  if (caps.includes("mode") && t !== "tv") parts.push(esc(s.mode || ""));
  if (caps.includes("target_temp")) parts.push(s.target_temp + "°C");
  if (caps.includes("fan_speed")) parts.push("ск. " + s.fan_speed);
  if (caps.includes("volume")) parts.push("🔈 " + s.volume + "%");
  if (caps.includes("current")) parts.push(s.current + " А");
  if (caps.includes("keys")) parts.push(`клавиш: ${(s.keys || []).filter(Boolean).length}/${(s.keys || []).length}`);
  const p = devicePower(d);
  if (p >= 1 && group !== SENSOR_GROUP) parts.push("≈" + formatPower(p));
  if (!parts.length) parts.push("Включено");
  if (s.off_at !== undefined && s.off_at !== null) parts.push("⏱ до " + simTimeText(s.off_at));
  return parts.join(" · ");
}

// ---------- этажи, план дома и камеры ----------

const FLOOR_NAMES = {}, FLOOR_SHORT = {};
D.floors.forEach(([code, name, short]) => { FLOOR_NAMES[code] = name; FLOOR_SHORT[code] = short; });

function roomPlanPosition(room) {
  const name = room.name.toLowerCase();
  for (const [keys, floor, x, y] of D.roomZones) {
    if (floor === room.floor && keys.some(k => name.includes(k))) return [x, y];
  }
  const [x, y] = D.floorDefaultPos[room.floor] || [0.5, 0.5];
  return [x + ((room.id * 37) % 5 - 2) * 0.07, y + ((room.id * 17) % 3 - 1) * 0.08];
}

function roomZone(roomName) {
  const name = roomName.toLowerCase();
  for (const [keys, floor, x, y] of D.roomZones) {
    if (keys.some(k => name.includes(k))) return [floor, x, y];
  }
  return ["floor1", 0.45, 0.45];
}
function sceneKind(roomName, model, floor) {
  if (model.outdoor) return "porch";
  const name = roomName.toLowerCase();
  if (floor === "site") return ["террас", "терас"].some(k => name.includes(k)) ? "terrace" : "yard";
  const table = [[["террас", "терас", "балкон", "двор", "сад", "улиц"], "terrace"], [["прихож", "коридор", "холл", "вход"], "hallway"],
                 [["гараж"], "garage"], [["кух"], "kitchen"], [["спальн", "детск"], "bedroom"]];
  for (const [keys, kind] of table) if (keys.some(k => name.includes(k))) return kind;
  return "living";
}

// ---------- хранение ----------

const STORE_KEY = "smarthome_v1";
const SEED_VERSION = 2; // 2: двор с газонокосилкой и поливом, устройства расставлены по плану

const Store = {
  data: null,
  load() {
    try { this.data = JSON.parse(localStorage.getItem(STORE_KEY) || "null"); } catch (e) { this.data = null; }
    if (!this.data || !this.data.users) this.data = { users: [], homes: {}, session: null, nextUserId: 1 };
    return this.data;
  },
  save() {
    try { localStorage.setItem(STORE_KEY, JSON.stringify(this.data, (k, v) => (k.startsWith("_") ? undefined : v))); } catch (e) { /* переполнение - не критично */ }
  },
};

function randomHex(bytes) {
  const a = new Uint8Array(bytes);
  (window.crypto || {}).getRandomValues ? crypto.getRandomValues(a) : a.forEach((_, i) => { a[i] = Math.random() * 256; });
  return Array.from(a, b => b.toString(16).padStart(2, "0")).join("");
}

async function hashPassword(password, salt) {
  if (window.crypto && crypto.subtle) {
    const key = await crypto.subtle.importKey("raw", new TextEncoder().encode(password), "PBKDF2", false, ["deriveBits"]);
    const bits = await crypto.subtle.deriveBits({ name: "PBKDF2", hash: "SHA-256", salt: new TextEncoder().encode(salt), iterations: 60000 }, key, 256);
    return Array.from(new Uint8Array(bits), b => b.toString(16).padStart(2, "0")).join("");
  }
  // запасной вариант для небезопасного контекста (file://) - простой хэш
  let h = 2166136261;
  const str = salt + ":" + password;
  for (let r = 0; r < 2000; r++) for (let i = 0; i < str.length; i++) { h ^= str.charCodeAt(i); h = Math.imul(h, 16777619) >>> 0; }
  return "fnv" + h.toString(16);
}

function newHome(userId) {
  const home = { rooms: [], devices: [], nextId: 1, batteryWh: C.BATTERY_CAPACITY_WH * 0.65, totals: { gen: 0, imp: 0, exp: 0 },
                 eco: true, tariff: C.DEFAULT_TARIFF_KZT, events: [], seedVersion: 0 };
  D.defaultRooms.forEach(name => home.rooms.push({ id: home.nextId++, name, floor: roomZone(name)[0] }));
  Store.data.homes[userId] = home;
  return home;
}

function addDevice(home, roomId, modelCode, name, settings, on) {
  const m = MODELS[modelCode];
  const d = { id: home.nextId++, roomId, type: m.type, model: modelCode, name, on: on ?? isAlwaysOn(m.type),
              s: Object.assign(defaultSettings(m), settings || {}), created: isoDate(new Date()) };
  home.devices.push(d);
  return d;
}

function seedHome(home) {
  D.seedExtraRooms.forEach(name => { if (!home.rooms.some(r => r.name === name)) home.rooms.push({ id: home.nextId++, name, floor: roomZone(name)[0] }); });
  const roomByName = {};
  home.rooms.forEach(r => { roomByName[r.name] = r.id; });
  D.seedDevices.forEach(([room, model, name, on, settings]) => {
    if (roomByName[room] === undefined) return;
    const existing = home.devices.find(d => d.roomId === roomByName[room] && d.model === model && d.name === name);
    if (existing) { if (settings.plan) existing.s.plan = Object.assign({}, settings.plan); return; }
    addDevice(home, roomByName[room], model, name, JSON.parse(JSON.stringify(settings)), !!on);
  });
  home.seedVersion = SEED_VERSION;
}

async function createUser(username, password) {
  const salt = randomHex(16);
  const user = { id: Store.data.nextUserId++, username, loginKey: username.trim().toLowerCase(), salt,
                 hash: await hashPassword(password, salt) };
  Store.data.users.push(user);
  newHome(user.id);
  return user;
}
function findUser(username) {
  const key = username.trim().toLowerCase();
  return Store.data.users.find(u => u.loginKey === key) || null;
}
async function authenticate(username, password) {
  const u = findUser(username);
  if (!u) return null;
  return (await hashPassword(password, u.salt)) === u.hash ? u : null;
}

async function initStore() {
  Store.load();
  for (const name of D.defaultUsers) if (!findUser(name)) await createUser(name, D.defaultPassword);
  // у комнат появился этаж: для старых данных определяем его по названию
  Object.values(Store.data.homes).forEach(hm => hm.rooms.forEach(r => { if (!r.floor) r.floor = roomZone(r.name)[0]; }));
  const seedUser = findUser(D.seedUser);
  const home = Store.data.homes[seedUser.id];
  if ((home.seedVersion || 0) < SEED_VERSION) seedHome(home);
  Store.save();
}

// ---------- история энергии по дням (для отчётов) ----------

function isoDate(d) { return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; }
function parseIso(s) { const [y, m, d] = s.split("-").map(Number); return new Date(y, m - 1, d); }
function addDays(d, n) { const x = new Date(d.getFullYear(), d.getMonth(), d.getDate()); x.setDate(x.getDate() + n); return x; }
function dayOfYear(d) { return Math.round((new Date(d.getFullYear(), d.getMonth(), d.getDate()) - new Date(d.getFullYear(), 0, 0)) / 864e5); }
function seededRandom(seedText) {
  let h = 1779033703 ^ seedText.length;
  for (let i = 0; i < seedText.length; i++) { h = Math.imul(h ^ seedText.charCodeAt(i), 3432918353); h = (h << 13) | (h >>> 19); }
  let a = h >>> 0;
  return () => { a |= 0; a = (a + 0x6D2B79F5) | 0; let t = Math.imul(a ^ (a >>> 15), 1 | a); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
}

// С этого дня в доме «работает» система (как HOME_SINCE в home.py): прошлые дни заполняются
// смоделированной историей - энергия и журнал событий, как будто приложением пользуются уже полгода
const HOME_SINCE = new Date(2026, 4, 18);
const ENERGY_HISTORY_START = HOME_SINCE;
const LIVE_EVENTS_LIMIT = 1000; // живых событий храним в localStorage, смоделированные - вычисляются на лету

// Правдоподобная суточная история (как в настольной версии): лето - больше солнца, зима - отопление,
// облачность меняется день ото дня, аккумулятор переносит заряд из дня в ночь. Значения в Вт·ч.
function syntheticEnergyHistory(userId, devicesCount, until) {
  const rnd = seededRandom("energy-history-" + userId);
  const reserve = C.BATTERY_CAPACITY_WH * C.BATTERY_RESERVE;
  let battery = C.BATTERY_CAPACITY_WH * 0.6, cloud = 0.3;
  const out = {};
  for (let d = ENERGY_HISTORY_START; d <= until; d = addDays(d, 1)) {
    const summer = 0.5 + 0.5 * Math.cos(2 * Math.PI * (dayOfYear(d) - 172) / 365);
    cloud = Math.min(0.95, Math.max(0, 0.55 * cloud + 0.45 * rnd() * (1.15 - 0.45 * summer)));
    const generated = C.SOLAR_PEAK_W * (1.6 + 4.2 * summer) * (1 - 0.75 * cloud);
    const base = 5500 + 180 * devicesCount, heating = Math.pow(1 - summer, 1.5) * 9000, cooling = Math.max(0, summer - 0.6) / 0.4 * 4000;
    const weekend = d.getDay() === 0 || d.getDay() === 6 ? 1.12 : 1;
    const consumed = (base + heating + cooling) * weekend * (0.85 + rnd() * 0.3);
    const daytime = consumed * 0.45, direct = Math.min(generated, daytime), surplus = generated - direct;
    const charge = Math.min(surplus, C.BATTERY_CAPACITY_WH - battery);
    battery += charge;
    const need = (daytime - direct) + (consumed - daytime), fromBattery = Math.min(need, Math.max(0, battery - reserve));
    battery -= fromBattery;
    out[isoDate(d)] = [generated, consumed, need - fromBattery, surplus - charge];
  }
  return out;
}

function backfillEnergyHistory(user, home) {
  home.days = home.days || {};
  // история начинается с HOME_SINCE - более ранние дни (старые версии писали с 2025 года) убираем
  const since = isoDate(HOME_SINCE);
  Object.keys(home.days).forEach(k => { if (k < since) delete home.days[k]; });
  const until = addDays(new Date(), -1);
  if (!home.days[isoDate(until)]) {
    const series = syntheticEnergyHistory(user.id, home.devices.length, until);
    Object.entries(series).forEach(([k, v]) => { if (!home.days[k]) home.days[k] = v.map(x => Math.round(x)); });
  }
  // «За всё время» - не меньше, чем набралось за всю историю дома
  const sums = [0, 0, 0];
  Object.values(home.days).forEach(v => { sums[0] += v[0]; sums[1] += v[2]; sums[2] += v[3]; });
  home.totals.gen = Math.max(home.totals.gen, sums[0]);
  home.totals.imp = Math.max(home.totals.imp, sums[1]);
  home.totals.exp = Math.max(home.totals.exp, sums[2]);
}

// ---------- паспорт устройства: покупка, гарантия, обслуживание, неисправности (как в home.py) ----------
// Всё детерминировано (зависит от пользователя и устройства), поэтому журнал и отчёты сходятся.
// Даты хранятся строками "ГГГГ-ММ-ДД" - их можно сравнивать как строки.

const WARRANTY_MONTHS = { washer: 24, dishwasher: 24, fridge: 24, tv: 24, robot_vacuum: 24, floor_washer: 24, lawn_mower: 24,
  irrigation: 24, dehumidifier: 24, air_purifier: 24, door_lock: 24, safe: 24, air_conditioner: 36, ev_charger: 36,
  water_heater: 36, inverter: 60, battery_bms: 120 };
const TYPE_PRICE_KZT = { washer: 230000, robot_vacuum: 180000, floor_washer: 150000, vacuum: 120000, camera: 25000,
  doorbell: 35000, door_lock: 90000, safe: 70000, temp_sensor: 9000, presence_sensor: 25000, smoke_sensor: 12000,
  door_sensor: 7000, leak_sensor: 9000, light_sensor: 8000, motion_sensor: 9000, speaker: 80000, tv: 280000,
  humidifier: 30000, heater: 45000, aroma: 15000, air_conditioner: 260000, fan: 30000, air_purifier: 70000,
  dehumidifier: 90000, router: 40000, gateway: 30000, repeater: 15000, light_strip: 18000, desk_lamp: 25000,
  bedside_lamp: 20000, ceiling_light: 45000, spot_light: 9000, bulb: 7000, night_light: 8000, socket: 7000, switch: 9000,
  remote: 8000, panel: 40000, water_dispenser: 60000, air_fryer: 45000, multicooker: 40000, fridge: 420000,
  microwave: 55000, kettle: 25000, dishwasher: 210000, lawn_mower: 650000, irrigation: 90000, inverter: 900000,
  battery_bms: 60000, ev_charger: 400000, water_heater: 120000 };
const SOLAR_SYSTEM_COST_KZT = 4500000;  // панели 6 кВт и аккумулятор 30 кВт·ч
const MAINTENANCE = {
  air_conditioner: [90, "чистка фильтров внутреннего блока"], robot_vacuum: [60, "чистка щётки и замена фильтра"],
  vacuum: [90, "чистка фильтра и контейнера"], floor_washer: [30, "самоочистка и замена фильтра"],
  humidifier: [60, "замена фильтра-испарителя"], air_purifier: [120, "замена HEPA-фильтра"],
  washer: [90, "чистка фильтра слива и уплотнителя"], dishwasher: [30, "чистка фильтра и форсунок"],
  kettle: [45, "удаление накипи"], fridge: [180, "чистка уплотнителя и решётки"], lawn_mower: [60, "заточка ножей"],
  irrigation: [90, "промывка фильтров и форсунок"], smoke_sensor: [30, "проверка датчика кнопкой «Тест»"],
  inverter: [180, "осмотр инвертора и чистка панелей"], ev_charger: [180, "проверка кабеля и разъёма"],
  heater: [180, "очистка от пыли"], water_heater: [180, "слив осадка, проверка анода"],
  camera: [180, "протирка объектива, проверка записи"] };
const BATTERY_LIFE_DAYS = { motion_sensor: 215, door_lock: 300, smoke_sensor: 1500, leak_sensor: 600, temp_sensor: 420,
  door_sensor: 700, presence_sensor: 500, safe: 900, light_sensor: 800, remote: 700, doorbell: 240 };
const BATTERY_LOW = 20;
const HISTORY_EPOCH = "2026-11-22";  // устройства до этой даты (и стартовые) считаются установленными с HOME_SINCE
const INCIDENT_PLAN = [
  [74, 3, "offline", ["leak_sensor", "door_sensor", "smoke_sensor", "temp_sensor", "motion_sensor"]],
  [128, 2, "broken", ["air_conditioner", "robot_vacuum", "washer", "dishwasher", "humidifier", "lawn_mower"]],
  [184, null, "offline", ["temp_sensor", "presence_sensor", "door_sensor", "camera", "smoke_sensor", "leak_sensor"]],
];
const FAULT_TEXTS = {
  air_conditioner: ["ошибка E1: засорён фильтр, кондиционер остановился", "фильтры очищены, ошибка сброшена"],
  robot_vacuum: ["ошибка 5: заблокирована основная щётка", "щётка очищена от намотавшихся волос"],
  washer: ["ошибка E21: не сливается вода", "прочищен фильтр сливного насоса"],
  dishwasher: ["ошибка E24: засор слива", "прочищены фильтр и сливной шланг"],
  humidifier: ["не срабатывает датчик уровня воды", "датчик очищен от налёта"],
  lawn_mower: ["застряла у забора, буксует колесо", "робот освобождён, колёса очищены"],
};
const DEVICE_STATES = { ok: ["Работает", "#00a05e"], off: ["Выключено", "#8aa0b2"], offline: ["Нет связи", "#e08a00"],
  broken: ["Неисправно", "#e5484d"] };
const ALWAYS_RUNNING_TYPES = new Set(["fridge", "inverter", "battery_bms", "router", "gateway", "repeater", "camera",
  "doorbell", "door_lock", "safe", "temp_sensor", "presence_sensor", "smoke_sensor", "door_sensor", "leak_sensor",
  "light_sensor", "motion_sensor", "socket", "switch", "panel"]);
const SEED_KEYS = new Set(D.seedDevices.map(([room, model, name]) => `${room}|${model}|${name}`));

const isoAdd = (iso, n) => isoDate(addDays(parseIso(iso), n));
const isoDiff = (a, b) => Math.round((parseIso(b) - parseIso(a)) / 864e5);  // b - a, дней
function isoAddMonths(iso, months) {
  const d = parseIso(iso), m = d.getMonth() + months, y = d.getFullYear() + Math.floor(m / 12), mm = ((m % 12) + 12) % 12;
  const last = new Date(y, mm + 1, 0).getDate();
  return isoDate(new Date(y, mm, Math.min(d.getDate(), last)));
}
function roomNameOf(home, d) { return (home.rooms.find(r => r.id === d.roomId) || {}).name || ""; }

function devicePassport(userId, home, d) {
  const rnd = seededRandom(`passport-${userId}-${d.id}`), t = d.type;
  const int = (a, b) => a + Math.floor(rnd() * (b - a + 1));
  const offset = t === "inverter" ? 0 : int(0, 20);
  const seeded = SEED_KEYS.has(`${roomNameOf(home, d)}|${d.model}|${d.name}`);
  const added = d.created && !seeded && d.created > HISTORY_EPOCH ? d.created : isoAdd(isoDate(HOME_SINCE), offset);
  const boughtEarlier = t !== "inverter" && rnd() < 0.3;
  const purchase = isoAdd(added, -(boughtEarlier ? int(200, 420) : int(0, 10)));
  const price = Math.max(990, Math.round((TYPE_PRICE_KZT[t] || 20000) * (0.8 + 0.4 * rnd()) / 1000) * 1000 - 10);
  const brand = (d.model.split("_")[0].toUpperCase().replace(/[^A-Z]/g, "").slice(0, 4)) || "DEV";
  const months = WARRANTY_MONTHS[t] || 12;
  const life = (BATTERY_LIFE_DAYS[t] || 600) * (0.9 + 0.2 * rnd());
  const serial = `${brand}-${Math.floor(rnd() * 4294967296).toString(16).toUpperCase().padStart(8, "0")}`;
  return { added, purchase, price, serial, firmware: `${int(1, 4)}.${int(0, 9)}.${int(10, 99)}`, warrantyMonths: months,
           warrantyUntil: isoAddMonths(purchase, months), batteryLife: life, boughtEarlier };
}
function devicePassports(userId, home) {
  const out = {};
  home.devices.forEach(d => { out[d.id] = devicePassport(userId, home, d); });
  return out;
}

function syntheticIncidents(home, passports) {
  const out = [], used = new Set();
  INCIDENT_PLAN.forEach(([offset, duration, kind, types]) => {
    const start = isoAdd(isoDate(HOME_SINCE), offset);
    const cands = types.flatMap(t => home.devices.filter(d => d.type === t && !used.has(d.id) && passports[d.id].added < isoAdd(start, -7)));
    if (!cands.length) return;
    const d = cands[0];
    used.add(d.id);
    let issue, fix;
    if (kind === "broken") [issue, fix] = FAULT_TEXTS[d.type] || ["устройство не отвечает на команды", "перезагружено, работает"];
    else if (d.s.battery !== undefined) [issue, fix] = ["нет связи со шлюзом — разрядилась батарейка", "заменена батарейка"];
    else [issue, fix] = ["нет связи: устройство пропало из сети Wi-Fi", "перезагружен роутер, устройство снова в сети"];
    if (duration === null) { fix = null; if (kind === "offline") issue = "нет связи со шлюзом — устройство не отвечает"; }
    out.push({ deviceId: d.id, kind, start, end: duration ? isoAdd(start, duration) : null, issue, fix, battery: fix === "заменена батарейка" });
  });
  return out;
}
function deviceIncidents(d, synthetic) {
  const resolved = d.s.resolved || {}, out = [];
  synthetic.forEach(inc => {
    if (inc.deviceId !== d.id) return;
    inc = Object.assign({}, inc);
    if (inc.end === null && resolved[inc.start]) { inc.end = resolved[inc.start]; inc.fix = "отмечено исправленным вручную"; }
    out.push(inc);
  });
  (d.s.incidents || []).forEach(inc => out.push({ deviceId: d.id, kind: inc.kind || "broken", start: inc.start, end: inc.end || null,
    issue: inc.issue || "", fix: inc.fix || null, manual: true, battery: false }));
  return out.sort((a, b) => (a.start < b.start ? -1 : a.start > b.start ? 1 : 0));
}
function activeIncident(incs, day) {
  const act = incs.filter(i => i.start <= day && (i.end === null || i.end > day));
  return act.length ? act[act.length - 1] : null;
}
function deviceState(d, incs, day) { const inc = activeIncident(incs, day); return inc ? inc.kind : d.on ? "ok" : "off"; }
function batteryLevel(d, p, incs, day) {
  if (d.s.battery === undefined) return null;
  let since = p.added;
  incs.forEach(inc => { if (inc.battery && inc.end && inc.end <= day && inc.end > since) since = inc.end; });
  if (d.s.battery_since && d.s.battery_since > since) since = d.s.battery_since;
  return Math.round(Math.max(3, Math.min(100, 100 - isoDiff(since, day) / p.batteryLife * 100)));
}
const batteryDaysLeft = (level, p) => Math.max(0, Math.floor((level - 3) / 100 * p.batteryLife));
function serviceDates(userId, d, p, until) {
  const spec = MAINTENANCE[d.type];
  if (!spec) return [];
  const out = new Set();
  let skipped = false;
  for (let k = 1; ; k++) {
    const planned = isoAdd(p.added, spec[0] * k);
    if (planned > until) break;
    const rnd = seededRandom(`service-${userId}-${d.id}-${k}`);
    if (skipped || rnd() >= 0.18) {  // примерно каждое шестое обслуживание пропущено, но не два подряд
      skipped = false;
      const done = isoAdd(planned, Math.floor(rnd() * 5));
      if (done <= until) out.add(done);
    } else skipped = true;
  }
  if (d.s.service_done && d.s.service_done <= until) out.add(d.s.service_done);
  return [...out].sort();
}
function maintenanceStatus(userId, d, p, day) {
  const spec = MAINTENANCE[d.type];
  if (!spec) return null;
  const done = serviceDates(userId, d, p, day), last = done.length ? done[done.length - 1] : null;
  const next = isoAdd(last || p.added, spec[0]), days = isoDiff(day, next);
  return { task: spec[1], interval: spec[0], last, next, days, status: days < 0 ? "overdue" : days <= 7 ? "soon" : "ok" };
}
function warrantyStatus(p, day) {
  const days = isoDiff(day, p.warrantyUntil);
  return [days < 0 ? "expired" : days <= 60 ? "ending" : "active", days];
}

function usageHours(t, day, summer, sunny) {
  const weekend = day.getDay() === 0 || day.getDay() === 6, month = day.getMonth() + 1;
  const warm = month >= 5 && month <= 9, cold = summer < 0.35, hot = summer > 0.8 && sunny > 0.65;
  if (ALWAYS_RUNNING_TYPES.has(t)) return 24;
  const table = { tv: weekend ? 5 : 3.5, speaker: 3, bulb: summer < 0.6 ? 6 : 3.5, ceiling_light: 5, spot_light: 4, desk_lamp: 3,
    bedside_lamp: 1, night_light: 8, kettle: 0.25, light_strip: (warm && weekend) || month === 12 ? 4 : 0.3,
    washer: weekend ? 0.9 : 0.5, dishwasher: 1.6, vacuum: weekend ? 0.4 : 0.1, robot_vacuum: 2, floor_washer: 0.5,
    air_conditioner: hot ? 5 : summer > 0.62 ? 1.2 : 0, heater: cold ? 6 : summer < 0.5 ? 1 : 0, humidifier: cold ? 12 : 6,
    ev_charger: sunny > 0.7 && summer > 0.4 ? 1.5 : 0.3, lawn_mower: warm ? 1.5 : 0, irrigation: warm ? 0.3 : 0,
    water_heater: 3, microwave: 0.3, multicooker: 1, air_fryer: 0.3, water_dispenser: 6, fan: hot ? 6 : 0, air_purifier: 10,
    dehumidifier: warm ? 3 : 1, aroma: 4 };
  return table[t] ?? 2;
}
// Оценка расхода каждого устройства за день (Вт·ч), масштабированная до потребления дома; "other" - фон дома
function deviceEnergySplit(home, passports, incidentsBy, key, consumed, generated) {
  const day = parseIso(key), summer = 0.5 + 0.5 * Math.cos(2 * Math.PI * (dayOfYear(day) - 172) / 365);
  const sunny = generated === undefined ? 0.8 : generated / (C.SOLAR_PEAK_W * (1.6 + 4.2 * summer));
  const raw = {};
  home.devices.forEach(d => {
    if (passports[d.id].added > key || activeIncident(incidentsBy[d.id] || [], key)) return;
    const m = MODELS[d.model];
    if (!m) return;
    raw[d.id] = m.power * (D.duty[d.type] ?? 1) * usageHours(d.type, day, summer, sunny);
  });
  const other = C.BASE_LOAD_W * 24 + 1500, total = Object.values(raw).reduce((a, b) => a + b, 0) + other;
  const k = total ? consumed / total : 0, out = { other: other * k };
  Object.entries(raw).forEach(([id, v]) => { out[id] = v * k; });
  return out;
}

// ---------- смоделированный журнал событий (как synthetic_event_history в home.py) ----------

const clock = m => { m = Math.max(0, Math.min(1439, Math.floor(m))); return `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`; };

// События прошлых дней согласованы с энергоисторией: в солнечные дни АКБ заряжается полностью и авто заряжается
// от излишков, в пасмурные - дом берёт энергию из сети и срабатывает эко-режим; летом полив и газонокосилка,
// зимой обогреватель. Каждый день детерминирован, поэтому журнал не хранится, а вычисляется заново.
function syntheticEventHistory(userId, home, dayKeys) {
  const tariff = home.tariff || C.DEFAULT_TARIFF_KZT;
  const roomName = d => (home.rooms.find(r => r.id === d.roomId) || {}).name || "";
  const byType = {};
  home.devices.forEach(d => { (byType[d.type] = byType[d.type] || []).push(d); });
  // даты установки, неисправности и обслуживание - те же, что в паспорте устройства и в отчётах
  const passports = devicePassports(userId, home), added = {};
  home.devices.forEach(d => { added[d.id] = passports[d.id].added; });
  const incidents = syntheticIncidents(home, passports), incidentsBy = {}, services = {};
  const lastKey = dayKeys.length ? dayKeys[dayKeys.length - 1] : isoDate(HOME_SINCE);
  home.devices.forEach(d => {
    incidentsBy[d.id] = deviceIncidents(d, incidents);
    services[d.id] = new Set(serviceDates(userId, d, passports[d.id], lastKey));
  });
  const washerModes = (D.modes.washer || [["Хлопок 60°"]]).map(m => m[0]);
  const out = [];
  dayKeys.forEach(key => {
    const day = parseIso(key), rnd = seededRandom(`events-${userId}-${key}`);
    const int = (a, b) => a + Math.floor(rnd() * (b - a + 1));
    const pick = xs => xs[Math.floor(rnd() * xs.length)];
    const evs = [];
    const add = (m, cat, icon, text) => evs.push({ m: Math.max(0, Math.min(1439, Math.floor(m))), cat, icon, text });
    const present = t => (byType[t] || []).filter(d => added[d.id] <= key && !activeIncident(incidentsBy[d.id], key));
    const toggle = (d, m, on = true) => add(m, "device", on ? "🟢" : "⚪", `${on ? "Включено" : "Выключено"}: ${d.name} (${roomName(d)})`);

    incidents.forEach(inc => {
      const d = home.devices.find(x => x.id === inc.deviceId);
      if (!d) return;
      if (inc.start === key) add(int(420, 1200), "device", inc.kind === "offline" ? "📵" : "⚠️", `${d.name}: ${inc.issue}`);
      if (inc.end === key && inc.fix) add(int(600, 1140), "device", "✅", `${d.name}: исправлено — ${inc.fix}`);
    });
    home.devices.forEach(d => {
      if (services[d.id].has(key)) add(int(600, 1200), "device", "🧰", `${d.name}: выполнено обслуживание — ${MAINTENANCE[d.type][1]}`);
    });

    const summer = 0.5 + 0.5 * Math.cos(2 * Math.PI * (dayOfYear(day) - 172) / 365);
    const weekend = day.getDay() === 0 || day.getDay() === 6, month = day.getMonth() + 1;
    const [gen, , imp, exp] = (home.days || {})[key] || [0, 0, 0, 0];
    const sunny = gen / (C.SOLAR_PEAK_W * (1.6 + 4.2 * summer)), rainy = sunny < 0.45;
    const warm = month >= 5 && month <= 9, cold = summer < 0.35, hot = summer > 0.8 && sunny > 0.65;
    const sunrise = 470 - 140 * summer + int(-4, 4), sunset = 1040 + 220 * summer + int(-4, 4);

    home.devices.forEach(d => { if (added[d.id] === key) add(int(600, 1260), "device", "➕", `Добавлено устройство: ${d.name} (${roomName(d)})`); });

    // энергосистема
    add(sunrise, "energy", "🌅", "Восход — солнечные панели начали выработку");
    add(sunset, "energy", "🌇", `Закат — выработка за день ${(gen / 1000).toFixed(1)} кВт·ч (≈ ${formatMoney(gen / 1000 * tariff)})`);
    if (exp > 300) add(int(750, 930), "energy", "🔋", "Аккумулятор полностью заряжен");
    if (imp > 300) {
      const low = imp > 2500 ? int(30, 150) : int(180, 300);
      add(low, "energy", "🪫", `Заряд АКБ ниже 20% (${int(17, 19)}%)`);
      const shed = [...new Set(D.ecoShedTypes.flatMap(t => present(t).map(d => d.name)))].join(", ");
      if (shed && imp > 4000) {
        add(low + 2, "energy", "🌿", `Эко-режим: АКБ ${int(18, 19)}% — отключены: ${shed}`);
        add(sunrise + int(200, 320), "energy", "🌿", `Эко-режим: АКБ ${int(40, 46)}% — снова включены: ${shed}`);
      }
      add(low + int(25, 70), "energy", "🔌", "Дом перешёл на питание от внешней сети");
      add(sunrise + int(90, 170), "energy", "🔋", "Питание от сети больше не требуется");
    }
    present("ev_charger").forEach(d => {
      if (exp > 1500 && rnd() < 0.6) {
        const start = int(660, 780);
        add(start, "energy", "☀️", `${d.name}: работает от излишков солнца (${formatPower(1800 + rnd() * (Math.min(7000, 1800 + exp / 2) - 1800))})`);
        add(Math.max(start + 60, int(900, Math.floor(sunset) - 40)), "energy", "⏸", `${d.name}: излишков нет — ждёт солнца`);
      }
    });

    // распорядок дня
    const leave = !weekend && rnd() < 0.8 ? int(475, 530) : null;
    if (leave) add(leave, "device", "🎬", `Сценарий «Ухожу из дома (выключить всё)»: изменено устройств — ${int(3, 7)}`);
    if (rnd() < 0.6) add(int(1350, 1435), "device", "🎬", `Сценарий «Выключить свет во всём доме»: изменено устройств — ${int(2, 5)}`);
    present("kettle").forEach(d => {
      const morning = weekend ? int(500, 600) : int(400, 450);
      if (rnd() < 0.03) add(morning - 3, "device", "💧", `${d.name}: нет воды — нагрев отменён`);
      add(morning, "device", "☕", `${d.name}: вода нагрета до ${pick([60, 80, 90, 100, 100])}°C`);
      if (rnd() < 0.55) add(int(1110, 1290), "device", "☕", `${d.name}: вода нагрета до ${pick([80, 90, 100])}°C`);
    });
    present("tv").forEach(d => {
      if (rnd() < 0.8) { const on = int(1140, 1260); toggle(d, on); toggle(d, Math.min(1435, on + int(60, 150)), false); }
      if (weekend && rnd() < 0.5) { const on = int(660, 900); toggle(d, on); toggle(d, on + int(40, 120), false); }
    });
    present("bulb").forEach(d => { if (sunset < 1290 || rnd() < 0.4) toggle(d, Math.max(sunset + int(-20, 20), 1080)); });
    present("bedside_lamp").forEach(d => {
      if (rnd() < 0.7) {
        const on = int(1350, 1410);
        toggle(d, on);
        if (rnd() < 0.6) add(on + pick([15, 30]), "device", "⏱", `Таймер: выключено «${d.name}»`);
      }
    });
    present("light_strip").forEach(d => {
      if ((warm && weekend) || month === 12) { toggle(d, sunset + int(5, 30)); toggle(d, int(1380, 1435), false); }
    });

    // климат
    present("air_conditioner").forEach(d => {
      if (hot && rnd() < 0.85) {
        const on = int(780, 900);
        toggle(d, on);
        add(on + int(25, 50), "device", "❄️", `${d.name}: в комнате «${roomName(d)}» достигнуто ${d.s.target_temp ?? 24}°C`);
      }
    });
    present("heater").forEach(d => {
      if (cold && rnd() < 0.8) {
        [int(390, 450)].concat(rnd() < 0.5 ? [int(1080, 1200)] : []).forEach(on => {
          toggle(d, on);
          add(on + int(20, 45), "device", "🔥", `${d.name}: в комнате «${roomName(d)}» достигнуто ${d.s.target_temp ?? 22}°C`);
        });
      }
    });

    // бытовая техника
    present("washer").forEach(d => {
      if (rnd() < (weekend ? 0.7 : 0.4)) {
        const start = int(540, 1140);
        toggle(d, start);
        add(start + int(80, 140), "device", "🧺", `${d.name}: стирка завершена (${pick(washerModes)})`);
      }
    });
    present("dishwasher").forEach(d => { if (rnd() < 0.55) toggle(d, int(1260, 1350)); });
    present("vacuum").forEach(d => {
      if (weekend && rnd() < 0.5) { const on = int(600, 720); toggle(d, on); toggle(d, on + int(15, 30), false); }
    });
    present("robot_vacuum").forEach(d => {
      if ((leave && rnd() < 0.75) || (weekend && rnd() < 0.3)) {
        const start = (leave || 600) + int(20, 90);
        toggle(d, start);
        let finish;
        if (rnd() < 0.06) { add(start + int(25, 35), "device", "🪫", `${d.name}: низкий заряд, едет на базу`); finish = start + 38; }
        else { finish = start + int(40, 55); add(finish, "device", "🤖", `${d.name}: уборка завершена, возвращается на базу`); }
        add(finish + int(3, 5), "device", "🏠", `${d.name}: на базе, заряжается`);
      }
    });

    // участок
    present("lawn_mower").forEach(d => {
      if (warm && (day.getDay() === 3 || day.getDay() === 6)) {
        const start = int(600, 660);
        if (rainy && rnd() < 0.5) {
          toggle(d, start);
          add(start + int(15, 30), "device", "🌧", `${d.name}: начался дождь — возвращается на базу`);
        } else if (!rainy) {
          toggle(d, start);
          const finish = start + int(60, 75);
          add(finish, "device", "🚜", `${d.name}: газон подстрижен, возвращается на базу`);
          add(finish + int(3, 5), "device", "🏠", `${d.name}: на базе, заряжается`);
        }
      }
    });
    present("irrigation").forEach(d => {
      if (warm && ([6, 7, 8].includes(month) || dayOfYear(day) % 2 === 0)) {
        const start = int(330, 360);
        if (rainy) add(start, "device", "🌧", `${d.name}: идёт дождь — полив отменён`);
        else {
          const minutes = d.s.irr_minutes || 10;
          toggle(d, start);
          add(start + minutes, "device", "💦", `${d.name}: полив завершён, израсходовано ${Math.round(minutes * (11 + rnd() * 3))} л воды`);
        }
      }
    });

    // безопасность
    present("motion_sensor").forEach(d => {
      const times = weekend ? Array.from({ length: int(3, 7) }, () => int(480, 1410))
        : Array.from({ length: int(1, 2) }, () => int(390, 510)).concat(Array.from({ length: int(2, 4) }, () => int(1080, 1410)));
      times.forEach(m => add(m, "security", "🏃", `Движение: ${roomName(d)} (${d.name})`));
    });
    present("door_sensor").forEach(d => {
      for (let i = int(1, 3); i > 0; i--) {
        const opened = int(420, 1350);
        add(opened, "security", "🚪", `Открыто: ${d.name} (${roomName(d)})`);
        add(opened + int(1, 8), "security", "🚪", `Закрыто: ${d.name} (${roomName(d)})`);
      }
    });
    present("presence_sensor").forEach(d => {
      add(weekend ? int(480, 600) : int(1050, 1200), "security", "👥", `Обнаружено присутствие: ${roomName(d)}`);
      if (!weekend) add(int(470, 530), "security", "👥", `Никого нет: ${roomName(d)}`);
    });
    present("camera").forEach(d => {
      if (d.s.motion_alerts === false) return;
      const outdoor = ["Двор", "Терраса", "Гараж"].includes(roomName(d));
      for (let i = outdoor ? int(0, 2) : pick([0, 0, 0, 1]); i > 0; i--) {
        add(int(420, 1320), "security", "📹", `${d.name}: обнаружен человек (${roomName(d)})`);
      }
      if (outdoor && rnd() < 0.015) add(int(60, 240), "security", "📹", `${d.name}: обнаружен человек (${roomName(d)})`);
    });
    present("doorbell").forEach(d => {
      if (rnd() < (weekend ? 0.45 : 0.3)) add(int(660, 1200), "security", "📹", `${d.name}: обнаружен человек (${roomName(d)})`);
    });

    evs.sort((a, b) => a.m - b.m);
    evs.forEach(e => out.push({ day: key, t: clock(e.m), cat: e.cat, icon: e.icon, text: e.text }));
  });
  return out;
}

// ---------- симуляция ----------

class Engine {
  constructor(user, hooks) {
    this.user = user;
    this.home = Store.data.homes[user.id];
    this.hooks = hooks; // {onEvent(ev, toast, color), onTick(state)}
    const now = new Date();
    this.startDate = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    this.simMinutes = now.getHours() * 60 + now.getMinutes() + now.getSeconds() / 60;
    backfillEnergyHistory(user, this.home);
    // у событий появилась дата: старым (без неё) ставим сегодняшнюю
    const today = isoDate(this.startDate);
    this.home.events.forEach(e => { if (!e.day) e.day = today; });
    this.home.liveDays = [...new Set((this.home.liveDays || []).concat(this.home.events.map(e => e.day)))];
    this.updateHealth();
    this.minutesPerTick = 1;
    this.cloudiness = Math.random() * 0.4;
    this.today = { gen: 0, cons: 0, imp: 0, exp: 0 };
    this.state = null;
    this.readings = {};
    this.sensorState = {};
    this.roomTemps = {};
    this.history = [];
    this.historyDay = null;
    this.flags = null;
    this.lastCameraToast = 0;
    this.saveCounter = 0;
    const base = roomBaselineTemp(this.simMinutes);
    this.home.rooms.forEach(r => { this.roomTemps[r.id] = base + (Math.random() - 0.5) * 1.2; });
  }

  get devices() { return this.home.devices; }
  simDate() { return addDays(this.startDate, Math.floor(this.simMinutes / 1440)); }
  roomFloor(id) { const r = this.room(id); return r ? r.floor : "floor1"; }

  // {iso-дата: [выработка, потребление, из сети, в сеть]} за период; текущий день - живые цифры
  energyDays(start, end) {
    const out = {}, a = isoDate(start), b = isoDate(end);
    Object.entries(this.home.days || {}).forEach(([k, v]) => { if (k >= a && k <= b) out[k] = v; });
    const today = isoDate(this.simDate());
    if (today >= a && today <= b) out[today] = [this.today.gen, this.today.cons, this.today.imp, this.today.exp];
    return out;
  }
  room(id) { return this.home.rooms.find(r => r.id === id); }
  roomName(id) { const r = this.room(id); return r ? r.name : ""; }
  load() { return this.devices.reduce((s, d) => s + devicePower(d), 0); }

  solarPower() {
    const hour = (this.simMinutes / 60) % 24;
    if (!(hour > 6 && hour < 20)) return 0;
    const sun = Math.sin(Math.PI * (hour - 6) / 14);
    return Math.max(0, C.SOLAR_PEAK_W * sun * (1 - 0.75 * this.cloudiness) * (0.97 + Math.random() * 0.06));
  }
  raining() { return this.cloudiness >= 0.85; }
  weather(gen) {
    if (this.raining()) return "🌧 Дождь";
    if (gen <= 0) return "🌙 Ночь";
    if (this.cloudiness < 0.25) return "☀️ Ясно";
    if (this.cloudiness < 0.6) return "⛅ Переменная облачность";
    return "☁️ Пасмурно";
  }

  tick(advance) {
    const home = this.home;
    if (advance) {
      const prevDay = Math.floor(this.simMinutes / 1440);
      this.simMinutes += this.minutesPerTick;
      if (Math.floor(this.simMinutes / 1440) !== prevDay) {
        // сутки закончились - сохраняем их итоги для отчётов
        const t = this.today;
        home.days[isoDate(addDays(this.startDate, prevDay))] = [t.gen, t.cons, t.imp, t.exp].map(Math.round);
        this.today = { gen: 0, cons: 0, imp: 0, exp: 0 };
      }
      const step = 0.04 * Math.sqrt(this.minutesPerTick);
      this.cloudiness = Math.min(0.95, Math.max(0, this.cloudiness + (Math.random() * 2 - 1) * step));
    }
    const hours = advance ? this.minutesPerTick / 60 : 0;
    const gen = this.solarPower(), load = C.BASE_LOAD_W + this.load(), balance = gen - load;
    let charge = 0, discharge = 0, imp = 0, exp = 0;
    const reserve = C.BATTERY_CAPACITY_WH * C.BATTERY_RESERVE;
    if (balance >= 0) {
      const room = C.BATTERY_CAPACITY_WH - home.batteryWh;
      charge = Math.min(balance, C.MAX_CHARGE_W, hours ? room / hours : balance);
      exp = balance - charge;
    } else {
      const deficit = -balance, avail = Math.max(0, home.batteryWh - reserve);
      discharge = Math.min(deficit, hours ? avail / hours : (avail > 0 ? deficit : 0));
      imp = deficit - discharge;
    }
    home.batteryWh = Math.max(0, Math.min(C.BATTERY_CAPACITY_WH, home.batteryWh + (charge - discharge) * hours));
    this.today.gen += gen * hours; this.today.cons += load * hours; this.today.imp += imp * hours; this.today.exp += exp * hours;
    home.totals.gen += gen * hours; home.totals.imp += imp * hours; home.totals.exp += exp * hours;
    let source = "☀️ Солнце";
    if (imp > 1 && discharge > 1) source = "🔋 АКБ + 🔌 сеть";
    else if (imp > 1) source = "🔌 Сеть";
    else if (discharge > 1 && gen > 1) source = "☀️ Солнце + 🔋 АКБ";
    else if (discharge > 1) source = "🔋 Аккумулятор";
    this.state = { time: simTimeText(this.simMinutes), simMinutes: this.simMinutes, advanced: advance,
                   level: home.batteryWh / C.BATTERY_CAPACITY_WH, batteryWh: home.batteryWh, generation: gen, load,
                   charge, discharge, gridImport: imp, gridExport: exp, source, weather: this.weather(gen), raining: this.raining() };
    if (advance) this.stepAll();
    this.updateReadings(advance);
    if (this.hooks.onTick) this.hooks.onTick(this.state);
    if (advance && ++this.saveCounter % 5 === 0) Store.save();
  }
  recalc() { this.tick(false); }

  log(category, icon, text, toast, color) {
    const day = isoDate(this.simDate());
    const ev = { day, t: simTimeText(this.simMinutes), cat: category, icon, text };
    const home = this.home;
    home.events.push(ev);
    if (home.events.length > LIVE_EVENTS_LIMIT) home.events.splice(0, home.events.length - LIVE_EVENTS_LIMIT);
    home.liveDays = home.liveDays || [];
    if (!home.liveDays.includes(day)) { home.liveDays.push(day); this._journal = null; }
    if (this.hooks.onEvent) this.hooks.onEvent(ev, !!toast, color);
  }

  // Весь журнал по порядку: смоделированные прошлые дни (с HOME_SINCE или с момента очистки журнала по вчера,
  // кроме дней, когда приложением пользовались) + живые события. Смоделированная часть кэшируется.
  journal() {
    const home = this.home, yesterday = isoDate(addDays(new Date(), -1));
    if (!this._journal || this._journalUntil !== yesterday) {
      const live = new Set(home.liveDays || []);
      let d = HOME_SINCE;
      if (home.journalFrom && parseIso(home.journalFrom) >= d) d = addDays(parseIso(home.journalFrom), 1);
      const keys = [];
      for (; isoDate(d) <= yesterday; d = addDays(d, 1)) if (!live.has(isoDate(d))) keys.push(isoDate(d));
      this._journal = syntheticEventHistory(this.user.id, home, keys);
      this._journalUntil = yesterday;
    }
    const all = this._journal.concat(home.events);
    return all.sort((a, b) => (a.day < b.day ? -1 : a.day > b.day ? 1 : 0));  // сортировка стабильная - время внутри дня сохраняется
  }

  clearJournal() {
    this.home.events = [];
    this.home.journalFrom = isoDate(addDays(new Date(), -1));  // смоделированная история до вчера тоже скрывается
    this._journal = null;
    Store.save();
  }

  // ---------- действия ----------

  // ---------- паспорт, неисправности, батарейки, обслуживание ----------

  updateHealth() {
    const today = isoDate(this.simDate());
    this.passports = devicePassports(this.user.id, this.home);
    this.incidents = syntheticIncidents(this.home, this.passports);
    this.home.devices.forEach(d => {
      const incs = deviceIncidents(d, this.incidents), inc = activeIncident(incs, today);
      d._state = inc ? inc.kind : null;
      d._issue = inc ? inc.issue : "";
      const level = batteryLevel(d, this.passports[d.id], incs, today);
      if (level !== null) d.s.battery = level;
    });
  }
  deviceInfo(d) {
    if (!this.passports || !this.passports[d.id]) this.updateHealth();
    const today = isoDate(this.simDate()), p = this.passports[d.id], incs = deviceIncidents(d, this.incidents);
    return { passport: p, incidents: incs, incident: activeIncident(incs, today), state: deviceState(d, incs, today),
             battery: batteryLevel(d, p, incs, today), maintenance: maintenanceStatus(this.user.id, d, p, today),
             warranty: warrantyStatus(p, today), today };
  }
  markFault(d, issue) {
    const today = isoDate(this.simDate()), kind = issue.toLowerCase().includes("связ") ? "offline" : "broken";
    (d.s.incidents = d.s.incidents || []).push({ start: today, end: null, kind, issue });
    if (d.on && kind === "broken") this.setOn(d, false, "system");
    this.updateHealth(); Store.save();
    this.log("device", kind === "offline" ? "📵" : "⚠️", `${d.name}: отмечено неисправным — ${issue}`, true, "#e5484d");
  }
  markFixed(d) {
    const today = isoDate(this.simDate());
    (d.s.incidents || []).forEach(inc => { if (!inc.end) { inc.end = today; inc.fix = "отмечено исправленным вручную"; } });
    (this.incidents || []).forEach(inc => { if (inc.deviceId === d.id && inc.end === null) (d.s.resolved = d.s.resolved || {})[inc.start] = today; });
    this.updateHealth(); Store.save();
    this.log("device", "✅", `${d.name}: исправлено (отмечено вручную)`, true);
  }
  markService(d) {
    d.s.service_done = isoDate(this.simDate());
    this.updateHealth(); Store.save();
    this.log("device", "🧰", `${d.name}: выполнено обслуживание — ${(MAINTENANCE[d.type] || [0, "обслуживание"])[1]}`, true);
  }
  markBattery(d) {
    d.s.battery_since = isoDate(this.simDate());
    this.updateHealth(); Store.save();
    this.log("device", "🔋", `${d.name}: заменена батарейка`, true);
  }

  setOn(d, on, source) {
    source = source || "user";
    if (on && source === "user" && (d._state === "broken" || d._state === "offline")) {
      if (this.hooks.onBlocked) this.hooks.onBlocked(d);
      return;
    }
    const s = d.s, t = d.type, requested = on;
    if (t === "irrigation" && on) {
      if (s.rain_sensor && this.raining()) { this.log("device", "🌧", d.name + ": идёт дождь — полив отменён", true); on = false; }
      else { s.irr_elapsed = 0; s.irr_water = 0; }
    }
    if (ROBOT_TYPES.includes(t)) {
      if (on) {
        if ((s.vac_battery ?? 100) < C.VAC_LOW_BATTERY + 10) {
          this.log("device", "🪫", `${d.name}: недостаточно заряда для ${D.robotInfo[t].start}`, true);
          on = false;
        } else {
          if ((s.vac_progress || 0) >= 1) s.vac_progress = 0;
          s.vac_state = "cleaning";
        }
      } else if (s.vac_state === "cleaning" || s.vac_state === "paused") {
        s.vac_state = "returning"; s.vac_return = 0;
      }
    }
    if (t === "washer") {
      if (on) delete s.wash_done;
      else if (source === "user") s.wash_elapsed = 0;
    }
    if (source === "user" && on && D.ecoShedTypes.includes(t) && this.state && this.state.level < C.ECO_OFF_LEVEL) {
      d._ecoOverride = true; delete s.eco_shed;
    }
    d.on = !!on;
    if (!on) { delete s.off_at; delete s.timer_min; }
    if (source === "user" && on === requested) this.log("device", on ? "🟢" : "⚪", `${on ? "Включено" : "Выключено"}: ${d.name} (${this.roomName(d.roomId)})`);
    Store.save();
    this.recalc();
  }
  changed() { Store.save(); this.recalc(); }

  runScene(code, roomId) {
    let changed = 0;
    this.devices.slice().forEach(d => {
      const isLight = TYPES[d.type].group === LIGHT_GROUP, inRoom = d.roomId === roomId;
      let target = null;
      if (code === "room_lights_on") target = isLight && inRoom ? true : null;
      else if (code === "room_off") target = inRoom && !isAlwaysOn(d.type) ? false : null;
      else if (code === "house_lights_off") target = isLight ? false : null;
      else target = !isAlwaysOn(d.type) ? false : null;
      if (target !== null && !!d.on !== target) { this.setOn(d, target, "scene"); changed++; }
    });
    const caption = (D.scenes.find(x => x[0] === code) || ["", code])[1];
    this.log("device", "🎬", `Сценарий «${caption.slice(2).trim()}»: изменено устройств — ${changed}`);
    return changed;
  }

  // ---------- физика ----------

  stepAll() {
    const minutes = this.minutesPerTick, st = this.state;
    this.devices.slice().forEach(d => {
      const s = d.s;
      if (s.off_at !== undefined && s.off_at !== null && d.on && st.simMinutes >= s.off_at) {
        this.setOn(d, false, "auto");
        this.log("device", "⏱", `Таймер: выключено «${d.name}»`);
      }
      if (d.type === "kettle") {
        const res = this.kettleStep(d);
        if (res === "done") { this.setOn(d, false, "auto"); this.log("device", "☕", `${d.name}: вода нагрета до ${s.target_temp}°C`, true); }
        else if (res === "empty") { this.setOn(d, false, "auto"); this.log("device", "💧", `${d.name}: нет воды — нагрев отменён`, true, "#e5484d"); }
      } else if (d.type === "washer") this.washerStep(d, minutes);
      else if (ROBOT_TYPES.includes(d.type)) this.vacuumStep(d, minutes);
      else if (d.type === "irrigation") this.irrigationStep(d, minutes);
    });
    this.climateStep(minutes);
    this.allocateSolar();
    this.checkEco();
    this.energyEvents();
    this.recordHistory();
  }

  kettleStep(d) {
    const s = d.s, m = MODELS[d.model], kg = (s.water_ml || 0) / 1000;
    let temp = s.water_temp ?? C.ROOM_TEMP;
    const target = s.target_temp ?? 100;
    if (d.on && kg * 1000 < C.MIN_KETTLE_WATER_ML) return "empty";
    if (kettleHeating(d)) {
      temp += m.power * C.KETTLE_SPEEDUP / (kg * 4186);
      s.water_temp = Math.min(target, temp);
      if (s.water_temp >= target - 0.05 && !s.keep_warm) return "done";
    } else if (d.on && s.keep_warm) s.water_temp = target;
    else s.water_temp = temp - (temp - C.ROOM_TEMP) * 0.004;
    return null;
  }

  washerStep(d, minutes) {
    const s = d.s;
    if (!d.on) return;
    const before = washerPhase(washerFraction(s));
    s.wash_elapsed = (s.wash_elapsed || 0) + minutes;
    if (washerFraction(s) >= 1) {
      s.wash_elapsed = 0; s.wash_done = true;
      this.setOn(d, false, "auto");
      this.log("device", "🧺", `${d.name}: стирка завершена (${s.mode})`, true);
    } else if (washerPhase(washerFraction(s)) !== before) {
      this.log("device", "🧺", `${d.name}: ${washerPhase(washerFraction(s)).toLowerCase()}`);
    }
  }

  vacuumStep(d, minutes) {
    const s = d.s, st = s.vac_state || "docked", mf = modeFactor(d.type, s.mode), info = D.robotInfo[d.type];
    if (st === "cleaning" && d.type === "lawn_mower" && s.rain_sensor && this.raining()) {
      s.vac_state = "returning"; s.vac_return = 0;
      this.log("device", "🌧", `${d.name}: начался дождь — возвращается на базу`, true);
      return;
    }
    if (st === "cleaning") {
      s.vac_progress = Math.min(1, (s.vac_progress || 0) + minutes / info.minutes);
      s.vac_battery = Math.max(0, (s.vac_battery ?? 100) - minutes * info.drain * mf);
      if (s.vac_progress >= 1) { s.vac_state = "returning"; s.vac_return = 0; this.log("device", d.type === "lawn_mower" ? "🚜" : "🤖", `${d.name}: ${info.done}, возвращается на базу`, true); }
      else if (s.vac_battery <= C.VAC_LOW_BATTERY) { s.vac_state = "returning"; s.vac_return = 0; this.log("device", "🪫", `${d.name}: низкий заряд, едет на базу`, true); }
    } else if (st === "returning") {
      s.vac_return = Math.min(1, (s.vac_return || 0) + minutes / C.VAC_RETURN_MIN);
      if (s.vac_return >= 1) {
        const finished = (s.vac_progress || 0) >= 1;
        s.vac_state = "docked"; s.vac_return = 0;
        if (finished) s.vac_progress = 0;
        d.on = false;
        this.log("device", "🏠", `${d.name}: на базе, заряжается`);
      }
    } else if (st === "docked") {
      s.vac_battery = Math.min(100, (s.vac_battery ?? 100) + minutes * C.VAC_CHARGE);
    }
  }

  irrigationStep(d, minutes) {
    const s = d.s, m = MODELS[d.model], zones = m.zones || 1;
    if (d.on) {
      const water = (m.flow || 15) * minutes;
      s.irr_elapsed = (s.irr_elapsed || 0) + minutes;
      s.irr_water = (s.irr_water || 0) + water;
      s.water_total = (s.water_total || 0) + water;
      s.moisture = Math.min(90, (s.moisture ?? 35) + 0.9 * minutes / zones);
      if (s.irr_elapsed >= zones * (s.irr_minutes || 10)) {
        s.irr_elapsed = 0;
        this.setOn(d, false, "auto");
        this.log("device", "💦", `${d.name}: полив завершён, израсходовано ${Math.round(s.irr_water)} л воды`, true);
      }
    } else {
      const sun = this.state.generation / C.SOLAR_PEAK_W;
      s.moisture = Math.max(10, (s.moisture ?? 35) - (0.01 + 0.03 * sun) * minutes);
      if (this.raining()) s.moisture = Math.min(90, s.moisture + 0.15 * minutes);
    }
  }

  climateStep(minutes) {
    const base = roomBaselineTemp(this.simMinutes);
    this.home.rooms.forEach(room => {
      let temp = this.roomTemps[room.id] ?? base;
      let controlled = false;
      this.devices.forEach(d => {
        if (d.roomId !== room.id || !["air_conditioner", "heater"].includes(d.type) || !d.on) return;
        const s = d.s, m = MODELS[d.model], target = s.target_temp ?? 22, wasActive = d._active !== false;
        let rate, dir;
        if (d.type === "heater") {
          rate = (0.05 + 0.12 * modeFactor("heater", s.mode)) * Math.sqrt(m.power / 2200);
          dir = temp < target - 0.2 ? 1 : 0;
        } else {
          rate = (0.06 + 0.1 * (s.fan_speed || 2) / (m.levels || 3)) * Math.sqrt(m.power / 1100);
          const mode = s.mode || "Охлаждение";
          if (mode === "Охлаждение") dir = temp > target + 0.2 ? -1 : 0;
          else if (mode === "Обогрев") dir = temp < target - 0.2 ? 1 : 0;
          else if (mode === "Авто") dir = temp > target + 0.4 ? -1 : (temp < target - 0.4 ? 1 : 0);
          else { d._active = true; return; }
        }
        if (dir) {
          temp += dir * rate * minutes;
          temp = dir > 0 ? Math.min(temp, target) : Math.max(temp, target);
          d._active = true;
        } else {
          temp += (target - temp) * Math.min(1, 0.5 * minutes);
          d._active = false;
          if (wasActive) this.log("device", d.type === "heater" ? "🔥" : "❄️", `${d.name}: в комнате «${room.name}» достигнуто ${target}°C`, true);
        }
        controlled = true;
      });
      if (!controlled) temp += (base - temp) * Math.min(1, 0.02 * minutes);
      this.roomTemps[room.id] = temp;
    });
  }

  allocateSolar() {
    const st = this.state;
    const solar = this.devices.filter(d => d.on && d.s.solar_only);
    this.devices.forEach(d => { if (!solar.includes(d)) d._solar = 0; });
    if (!solar.length) return;
    const house = C.BASE_LOAD_W + this.devices.filter(d => !solar.includes(d)).reduce((s, d) => s + devicePower(d), 0);
    let avail = st.level >= C.SOLAR_ONLY_MIN_LEVEL ? st.generation - house : 0;
    solar.sort((a, b) => (a.type === "ev_charger" ? 0 : 1) - (b.type === "ev_charger" ? 0 : 1));
    solar.forEach(d => {
      const full = solarFullPower(d), prev = d._solar || 0;
      let threshold = d.type === "ev_charger" ? C.EV_MIN_POWER : full * 0.9;
      if (prev > 1) threshold *= 0.75;
      const p = avail >= threshold ? (d.type === "ev_charger" ? Math.min(full, avail) : full) : 0;
      avail -= p;
      d._solar = p;
      if (prev <= 1 && p > 1) this.log("energy", "☀️", `${d.name}: работает от излишков солнца (${formatPower(p)})`, true);
      else if (prev > 1 && p <= 1) this.log("energy", "⏸", `${d.name}: излишков нет — ждёт солнца`);
    });
  }

  checkEco() {
    const level = this.state.level;
    if (this.home.eco && level < C.ECO_OFF_LEVEL) {
      const shed = this.devices.filter(d => D.ecoShedTypes.includes(d.type) && d.on && !d._ecoOverride && !d.s.solar_only);
      shed.forEach(d => { d.s.eco_shed = true; this.setOn(d, false, "eco"); });
      if (shed.length) this.log("energy", "🌿", `Эко-режим: АКБ ${Math.round(level * 100)}% — отключены: ${shed.map(d => d.name).join(", ")}`, true);
    } else if (level >= C.ECO_RESTORE_LEVEL) {
      const restored = this.devices.filter(d => d.s.eco_shed);
      restored.forEach(d => { delete d.s.eco_shed; this.setOn(d, true, "eco"); });
      this.devices.forEach(d => { delete d._ecoOverride; });
      if (restored.length) this.log("energy", "🌿", `Эко-режим: АКБ ${Math.round(level * 100)}% — снова включены: ${restored.map(d => d.name).join(", ")}`, true);
    }
  }

  energyEvents() {
    const st = this.state, level = st.level, gen = st.generation;
    if (!this.flags) { this.flags = { low: level < 0.2, grid: st.gridImport > 1, full: level >= 0.999, sun: gen > 0 }; return; }
    const f = this.flags;
    if (level < 0.2 && !f.low) { f.low = true; this.log("energy", "🪫", `Заряд АКБ ниже 20% (${Math.round(level * 100)}%)`, true, "#e5484d"); }
    else if (level > 0.25) f.low = false;
    if (st.gridImport > 50 && !f.grid) { f.grid = true; this.log("energy", "🔌", "Дом перешёл на питание от внешней сети", true, "#e5484d"); }
    else if (st.gridImport < 1 && f.grid) { f.grid = false; this.log("energy", "🔋", "Питание от сети больше не требуется"); }
    if (level >= 0.999 && !f.full) { f.full = true; this.log("energy", "🔋", "Аккумулятор полностью заряжен", true, "#00b96b"); }
    else if (level < 0.97) f.full = false;
    if (gen > 0 && !f.sun) { f.sun = true; this.log("energy", "🌅", "Восход — солнечные панели начали выработку"); }
    else if (gen <= 0 && f.sun) {
      f.sun = false;
      const kwh = this.today.gen / 1000;
      this.log("energy", "🌇", `Закат — выработка за день ${kwh.toFixed(1).replace(".", ",")} кВт·ч (≈ ${formatMoney(kwh * this.home.tariff)})`, true);
    }
  }

  recordHistory() {
    const st = this.state, day = Math.floor(st.simMinutes / 1440), minute = st.simMinutes % 1440;
    if (day !== this.historyDay) { this.historyDay = day; this.history = []; }
    const last = this.history[this.history.length - 1];
    if (!last || minute - last[0] >= 2) this.history.push([minute, st.generation, st.load, st.level, st.gridImport, st.gridExport]);
  }

  updateReadings(advanced) {
    const st = this.state, sm = st.simMinutes;
    const sensors = this.devices.filter(d => TYPES[d.type].group === SENSOR_GROUP).length;
    this.devices.forEach(d => {
      const t = d.type, room = this.roomName(d.roomId);
      const ss = this.sensorState[d.id] || (this.sensorState[d.id] = { hum: 38 + Math.random() * 14, present: false, open: false, last: null, noise: 0 });
      let text = null;
      if (t === "temp_sensor") {
        ss.noise = Math.max(-0.3, Math.min(0.3, ss.noise + (Math.random() - 0.5) * 0.06));
        ss.hum = Math.min(65, Math.max(30, ss.hum + (Math.random() - 0.5) * 0.6));
        text = `🌡 ${((this.roomTemps[d.roomId] ?? C.ROOM_TEMP) + ss.noise).toFixed(1)} °C · 💧 ${Math.round(ss.hum)}%`;
      } else if (t === "air_conditioner" || t === "heater") {
        text = `🌡 ${(this.roomTemps[d.roomId] ?? C.ROOM_TEMP).toFixed(1)}°C`;
      } else if (t === "presence_sensor") {
        if (advanced && Math.random() < 0.02) { ss.present = !ss.present; if (d.on) this.log("security", "👥", `${ss.present ? "Обнаружено присутствие" : "Никого нет"}: ${room}`); }
        text = ss.present ? "👥 Есть присутствие" : "Никого нет";
      } else if (t === "motion_sensor") {
        if (advanced && Math.random() < 0.03) { ss.last = sm; if (d.on) this.log("security", "🏃", `Движение: ${room} (${d.name})`); }
        text = ss.last === null ? "Движения не было" : (sm - ss.last < 1 ? "🏃 Движение сейчас" : `Движение ${Math.floor(sm - ss.last)} мин назад`);
      } else if (t === "door_sensor") {
        if (advanced && Math.random() < 0.01) { ss.open = !ss.open; if (d.on) this.log("security", "🚪", `${ss.open ? "Открыто" : "Закрыто"}: ${d.name} (${room})`); }
        text = ss.open ? "🚪 Открыто" : "Закрыто";
      } else if (t === "smoke_sensor") text = "✅ Дыма нет";
      else if (t === "leak_sensor") text = "✅ Протечек нет";
      else if (t === "light_sensor") text = `🔆 ${Math.round(5 + st.generation / C.SOLAR_PEAK_W * 1500)} лк`;
      else if (t === "inverter") text = "☀️ Выработка " + formatPower(st.generation);
      else if (t === "battery_bms") {
        const flow = st.charge > 1 ? "+" + formatPower(st.charge) : st.discharge > 1 ? "−" + formatPower(st.discharge) : "покой";
        text = `🔋 ${Math.round(st.level * 100)}% · ${flow}`;
      } else if (t === "gateway") text = "Датчиков в сети: " + sensors;
      else if (t === "camera" || t === "doorbell") {
        if (d.s.recording) text = "🔴 Запись";
        if (advanced && d.on && d.s.motion_alerts && Math.random() < 0.006) {
          const now = Date.now(), toast = now - this.lastCameraToast > 20000;
          if (toast) this.lastCameraToast = now;
          this.log("security", "📹", `${d.name}: обнаружен человек (${room})`, toast);
        }
      }
      if (text !== null) this.readings[d.id] = text;
    });
  }
}
