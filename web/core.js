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
              s: Object.assign(defaultSettings(m), settings || {}) };
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

const ENERGY_HISTORY_START = new Date(2025, 0, 1);

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
  const until = addDays(new Date(), -1);
  const lastKey = isoDate(until);
  if (home.days[lastKey]) return;
  const series = syntheticEnergyHistory(user.id, home.devices.length, until);
  Object.entries(series).forEach(([k, v]) => { if (!home.days[k]) home.days[k] = v.map(x => Math.round(x)); });
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
    const ev = { t: simTimeText(this.simMinutes), cat: category, icon, text };
    this.home.events.push(ev);
    if (this.home.events.length > 300) this.home.events.splice(0, this.home.events.length - 300);
    if (this.hooks.onEvent) this.hooks.onEvent(ev, !!toast, color);
  }

  // ---------- действия ----------

  setOn(d, on, source) {
    source = source || "user";
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
