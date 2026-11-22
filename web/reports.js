// Отчёты веб-версии (как раздел «ОТЧЁТЫ PDF» в home.py): о состоянии устройств, об электроэнергии и сводный
// о состоянии умного дома. rpCollect() считает все цифры, rpHtml*() строят HTML с SVG-графиками,
// сохранение в PDF - через печать браузера (на iPhone: «Поделиться» → «Печать» → «Сохранить в Файлы»).
"use strict";

const RP_KINDS = [
  ["devices", "Отчёт о состоянии устройств", "📋", "Какие устройства работают, выключены, без связи или неисправны; где они стоят, заряд батареек, активность за период, проблемы и что с ними сделать."],
  ["energy", "Отчёт об электроэнергии", "⚡", "Выработка панелей, потребление, сеть и аккумулятор; счёт и экономия в тенге; сравнение с прошлым периодом; кто и где потребляет больше всего; рекомендации по экономии."],
  ["home", "Отчёт о состоянии умного дома", "🏠", "Главный сводный отчёт: общая оценка дома, энергосистема, устройства, безопасность, гарантия и обслуживание, важные события и рекомендации."],
];
const RP_TITLES = Object.fromEntries(RP_KINDS.map(k => [k[0], k[1]]));
const RP_CONTENTS = {
  devices: ["Кратко: сколько устройств работает, выключено, без связи, неисправно", "Что требует внимания и что именно сделать",
            "Все устройства по этажам и комнатам", "Батарейки датчиков и замков с прогнозом замены",
            "Активность и неисправности за период", "Паспорт: модели, серийные номера, прошивки"],
  energy: ["Главные показатели и счёт в тенге", "Сравнение с прошлым периодом", "График и таблица по дням или месяцам",
           "Кто потребляет: устройства, комнаты, категории", "Аккумулятор и сеть, окупаемость, экология", "Рекомендации по экономии"],
  home: ["Общая оценка дома от 0 до 100", "Общие сведения, энергосистема, устройства", "Безопасность: камеры, датчики, замок",
         "Гарантия и регламентное обслуживание", "Важные события за период", "Рекомендации и паспорт устройств"],
};
const RP_PERIODS = [["week", "Неделя", 7], ["month", "Месяц", 30], ["halfyear", "Полгода", 182], ["year", "Год", 365], ["custom", "Свой период", 0]];
const RP_IMPORTANT = new Set(["📵", "⚠️", "✅", "🧰", "🌿", "🔌", "🪫", "➕", "🗑"]);
const RP_SECURITY = ["door_lock", "camera", "doorbell", "safe", "smoke_sensor", "leak_sensor", "motion_sensor", "door_sensor", "presence_sensor"];
const RP_SEVERITY = { high: ["Срочно", "#e5484d"], medium: ["Важно", "#e08a00"], low: ["Планово", "#3f8fd2"] };
const RP_M_SHORT = ["янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"];
const RP_M_FULL = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"];
const RP_FLOORS = D.floors.map(f => f[0]);

const rpDate = iso => (iso ? `${iso.slice(8, 10)}.${iso.slice(5, 7)}.${iso.slice(0, 4)}` : "—");
const rpKwh = (wh, digits = 1) => (wh / 1000).toFixed(digits).replace(/\B(?=(\d{3})+(?!\d))/g, " ").replace(".", ",") + " кВт·ч";
const rpPct = x => Math.round(x) + "%";
const rpDays = n => `${n} ${plural(n, "день", "дня", "дней")}`;
const rpBadge = (label, color) => `<span class="rp-badge" style="color:${color}">● ${esc(label)}</span>`;
const rpState = st => rpBadge(DEVICE_STATES[st][0], DEVICE_STATES[st][1]);

function rpChangeText(now, before, fmt) {
  if (!before) return "сравнить не с чем — в прошлом периоде система ещё не работала";
  const pct = (now - before) / before * 100;
  if (Math.abs(pct) < 1) return `почти столько же, сколько в прошлом периоде (${fmt(before)})`;
  return `на ${Math.abs(pct).toFixed(0)}% ${pct > 0 ? "больше" : "меньше"}, чем в прошлом периоде (${fmt(before)})`;
}

function rpBuckets(days, start, end, tariff) {
  const mk = (label, title, v) => ({ label, title, gen: v[0], cons: v[1], imp: v[2], exp: v[3], cost: v[2] / 1000 * tariff });
  if (isoDiff(start, end) <= 62) {
    const out = [];
    for (let k = start; k <= end; k = isoAdd(k, 1)) if (days[k]) out.push(mk(`${k.slice(8, 10)}.${k.slice(5, 7)}`, rpDate(k), days[k]));
    return out;
  }
  const months = {};
  Object.keys(days).sort().forEach(k => {
    if (k < start || k > end) return;
    const m = months[k.slice(0, 7)] || (months[k.slice(0, 7)] = [0, 0, 0, 0]);
    days[k].forEach((v, i) => { m[i] += v; });
  });
  return Object.keys(months).sort().map(key => {
    const [y, mo] = key.split("-").map(Number);
    return mk(`${RP_M_SHORT[mo - 1]} ${String(y).slice(2)}`, `${RP_M_FULL[mo - 1]} ${y}`, months[key]);
  });
}

// ---------- сбор данных ----------

function rpCollect(eng, start, end) {
  const home = eng.home, userId = eng.user.id, today = isoDate(eng.simDate()), tariff = home.tariff;
  const nDays = isoDiff(start, end) + 1, prevEnd = isoAdd(start, -1), prevStart = isoAdd(prevEnd, -(nDays - 1));
  const days = eng.energyDays(parseIso(prevStart), parseIso(end));
  const events = eng.journal().filter(e => e.day >= start && e.day <= end)
    .map(e => ({ day: e.day, sim_time: e.t, category: e.cat, icon: e.icon, text: e.text }));
  const passports = devicePassports(userId, home), synthetic = syntheticIncidents(home, passports), incidents = {};
  home.devices.forEach(d => { incidents[d.id] = deviceIncidents(d, synthetic); });
  const roomOf = d => home.rooms.find(r => r.id === d.roomId) || { name: "", floor: "floor1" };

  // энергия
  const periodSum = (a, b) => {
    const vals = Object.entries(days).filter(([k]) => k >= a && k <= b).map(([, v]) => v);
    return [[0, 1, 2, 3].map(i => vals.reduce((s, v) => s + v[i], 0)), vals.length];
  };
  const [[gen, cons, imp, exp], nEnergy] = periodSum(start, end);
  const [[pGen, pCons, pImp, pExp], nPrev] = periodSum(prevStart, prevEnd);
  const perDevice = {};
  let other = 0;
  const periodDays = Object.keys(days).filter(k => k >= start && k <= end).sort();
  periodDays.forEach(k => {
    const split = deviceEnergySplit(home, passports, incidents, k, days[k][1], days[k][0]);
    other += split.other;
    Object.entries(split).forEach(([id, v]) => { if (id !== "other") perDevice[id] = (perDevice[id] || 0) + v; });
  });
  const byRoom = {}, byGroup = {};
  home.devices.forEach(d => {
    const wh = perDevice[d.id] || 0, room = roomOf(d).name, group = TYPES[d.type].group;
    byRoom[room] = (byRoom[room] || 0) + wh;
    byGroup[group] = (byGroup[group] || 0) + wh;
  });
  byGroup["Фоновое потребление дома"] = other;
  const fullDays = periodDays.filter(k => k !== today).length ? periodDays.filter(k => k !== today) : periodDays;  // сегодня ещё не закончилось
  const by = (f, cmp) => fullDays.length ? fullDays.reduce((best, k) => (cmp(f(k), f(best)) ? k : best), fullDays[0]) : null;
  const energy = {
    gen, cons, imp, exp, days: nEnergy,
    prev: { gen: pGen, cons: pCons, imp: pImp, exp: pExp, days: nPrev, start: prevStart, end: prevEnd, ok: nPrev >= nDays * 0.9 },
    selfPct: cons ? (cons - imp) / cons * 100 : 0, pay: imp / 1000 * tariff, nosolar: cons / 1000 * tariff,
    saved: Math.max(0, cons - imp) / 1000 * tariff, co2: gen / 1000 * C.CO2_KG_PER_KWH, buckets: rpBuckets(days, start, end, tariff),
    byRoom, byGroup, other,
    gridDays: periodDays.filter(k => days[k][2] > 300).length, fullDays: periodDays.filter(k => days[k][3] > 300).length,
    ecoCount: events.filter(e => e.text.startsWith("Эко-режим: АКБ") && e.text.includes("отключены")).length,
    bestDay: by(k => days[k][0], (a, b) => a > b), worstDay: by(k => days[k][0], (a, b) => a < b), peakDay: by(k => days[k][1], (a, b) => a > b),
    exportPct: gen ? exp / gen * 100 : 0, daysMap: days,
  };
  energy.trees = energy.co2 / C.CO2_PER_TREE_KG;
  energy.annualSaving = energy.saved / Math.max(1, nEnergy) * 365;
  energy.paybackYears = energy.annualSaving > 0 ? SOLAR_SYSTEM_COST_KZT / energy.annualSaving : null;

  // устройства
  const names = home.devices.map(d => d.name);
  const rows = home.devices.map(d => {
    const p = passports[d.id], incs = incidents[d.id], state = deviceState(d, incs, today), room = roomOf(d);
    const m = MODELS[d.model] || { name: d.model, power: 0 };
    const unique = names.filter(n => n === d.name).length === 1;
    const mine = text => text.includes(d.name) && (unique || text.includes(room.name));
    const devEvents = events.filter(e => mine(e.text));
    const wh = perDevice[d.id] || 0, nominal = m.power * (D.duty[d.type] ?? 1), bat = batteryLevel(d, p, incs, today);
    return {
      device: d, id: d.id, name: d.name, room: room.name, roomId: d.roomId, floor: FLOOR_NAMES[room.floor] || "",
      type: TYPES[d.type].name, group: TYPES[d.type].group, model: m.name, powerRated: m.power, state, incident: activeIncident(incs, today),
      incidents: incs, battery: bat, batteryDays: bat !== null ? batteryDaysLeft(bat, p) : null,
      powerNow: state === "ok" ? devicePower(d) : 0, energy: wh, cost: wh / 1000 * tariff, hours: nominal > 0 ? wh / nominal : 0,
      switches: devEvents.filter(e => e.text.startsWith("Включено:")).length, events: devEvents.length,
      lastEvent: devEvents.length ? devEvents[devEvents.length - 1] : null, passport: p, warranty: warrantyStatus(p, today),
      maintenance: maintenanceStatus(userId, d, p, today),
      detail: state === "ok" || state === "off" ? deviceStatusHtml(d, eng.readings[d.id]).replace(/<[^>]+>/g, "") : "",
    };
  });
  const counts = { total: rows.length };
  Object.keys(DEVICE_STATES).forEach(k => { counts[k] = rows.filter(r => r.state === k).length; });
  counts.lowBattery = rows.filter(r => r.battery !== null && r.battery < BATTERY_LOW).length;

  // что требует внимания
  const attention = [];
  rows.forEach(r => {
    const inc = r.incident, p = r.passport, [wStatus] = r.warranty;
    if (r.state === "broken") attention.push(["high", r, `Неисправно с ${rpDate(inc.start)}: ${inc.issue}`, `Устранить: ${inc.issue}. ` +
      (wStatus !== "expired" ? `Устройство на гарантии до ${rpDate(p.warrantyUntil)} — ремонт бесплатно в сервисном центре.` : "Гарантия истекла — ремонт платный.")]);
    else if (r.state === "offline") attention.push(["high", r, `Нет связи с ${rpDate(inc.start)} (${rpDays(isoDiff(inc.start, today))})`,
      r.battery !== null ? "Проверьте батарейку и расстояние до шлюза, при необходимости переподключите датчик." : "Проверьте питание и Wi-Fi, перезагрузите устройство."]);
    if (r.battery !== null && r.battery < BATTERY_LOW && r.state !== "offline")
      attention.push([r.battery < 10 ? "high" : "medium", r, `Батарейка разряжена: ${r.battery}%`, `Замените батарейку — до полного разряда ≈ ${rpDays(r.batteryDays)}.`]);
    const mt = r.maintenance;
    if (mt && mt.status === "overdue") attention.push(["medium", r, `Обслуживание просрочено на ${rpDays(-mt.days)}`, `Выполните: ${mt.task}.`]);
    else if (mt && mt.status === "soon") attention.push(["low", r, `Обслуживание через ${rpDays(mt.days)} (${rpDate(mt.next)})`, `Запланируйте: ${mt.task}.`]);
    if (wStatus === "ending") attention.push(["low", r, `Гарантия заканчивается ${rpDate(p.warrantyUntil)}`, "Проверьте устройство и обратитесь в сервис, пока действует гарантия."]);
  });
  const order = { high: 0, medium: 1, low: 2 };
  attention.sort((a, b) => order[a[0]] - order[b[0]]);

  const periodIncidents = [];
  rows.forEach(r => r.incidents.forEach(inc => { if (inc.start <= end && (inc.end === null || inc.end >= start)) periodIncidents.push([r, inc]); }));
  periodIncidents.sort((a, b) => (a[1].start < b[1].start ? -1 : 1));

  // безопасность
  const sec = e => e.category === "security";
  const security = {
    rows: RP_SECURITY.flatMap(t => rows.filter(r => r.device.type === t)),
    motion: events.filter(e => sec(e) && e.icon === "🏃").length,
    people: events.filter(e => sec(e) && e.icon === "📹" && !e.text.toLowerCase().includes("звонок")).length,
    doorbell: events.filter(e => sec(e) && e.text.toLowerCase().includes("звонок")).length,
    night: events.filter(e => sec(e) && e.icon === "📹" && (e.sim_time < "06:00" || e.sim_time >= "23:00")),
    lockOpen: rows.some(r => r.device.type === "door_lock" && r.device.s.locked === false),
  };

  // гарантия и обслуживание
  const warrantyRows = rows.slice().sort((a, b) => (a.passport.warrantyUntil < b.passport.warrantyUntil ? -1 : 1));
  const maintenanceRows = rows.filter(r => r.maintenance).sort((a, b) => (a.maintenance.next < b.maintenance.next ? -1 : 1));
  const care = {
    value: rows.reduce((s, r) => s + r.passport.price, 0),
    active: rows.filter(r => r.warranty[0] === "active").length, ending: rows.filter(r => r.warranty[0] === "ending").length,
    expired: rows.filter(r => r.warranty[0] === "expired").length,
    overdue: maintenanceRows.filter(r => r.maintenance.status === "overdue").length,
    soon: maintenanceRows.filter(r => r.maintenance.status === "soon").length,
    servicesDone: events.filter(e => e.icon === "🧰").length,
  };

  // оценка дома
  const batCrit = rows.filter(r => r.battery !== null && r.battery < 10).length;
  const devScore = Math.max(0, 100 - 25 * counts.broken - 15 * counts.offline - 10 * batCrit - 5 * (counts.lowBattery - batCrit));
  const energyScore = Math.min(100, Math.round(energy.selfPct * 1.1));
  const secBad = security.rows.filter(r => r.state === "broken" || r.state === "offline").length;
  const secLow = security.rows.filter(r => r.battery !== null && r.battery < BATTERY_LOW).length;
  const secScore = Math.max(0, 100 - 20 * secBad - 10 * secLow - (security.lockOpen ? 30 : 0));
  const careScore = Math.max(0, 100 - 12 * care.overdue - 4 * care.soon - 3 * care.ending);
  const score = { total: Math.round(0.3 * devScore + 0.3 * energyScore + 0.2 * secScore + 0.2 * careScore),
    parts: [["Устройства", devScore, 30], ["Энергия", energyScore, 30], ["Безопасность", secScore, 20], ["Гарантия и обслуживание", careScore, 20]] };

  const r = { owner: eng.user.username, start, end, today, nDays, tariff, rows, counts, attention, periodIncidents, energy, security,
    warrantyRows, maintenanceRows, care, score, rooms: home.rooms, eco: home.eco, batteryLevel: home.batteryWh / C.BATTERY_CAPACITY_WH,
    important: events.filter(e => RP_IMPORTANT.has(e.icon) || security.night.includes(e)), generatedAt: new Date() };
  r.recommendations = rpRecommendations(r);
  return r;
}

function rpScoreLabel(score) {
  if (score >= 85) return ["Отличное", "#00a05e"];
  if (score >= 70) return ["Хорошее", "#5bb318"];
  if (score >= 50) return ["Требует внимания", "#e08a00"];
  return ["Плохое", "#e5484d"];
}

function rpRecommendations(r) {
  const recs = [], e = r.energy, month = 30 / Math.max(1, e.days);
  r.attention.forEach(([sev, row, problem, action]) => { if (sev !== "low") recs.push(["devices", `${row.name} (${row.room}): ${problem.toLowerCase()}. ${action}`]); });
  if (e.cons && e.imp / e.cons > 0.2) {
    const shift = r.rows.filter(x => ["washer", "dishwasher"].includes(x.device.type)).reduce((s, x) => s + x.energy, 0) * 0.5;
    let text = `${(e.imp / e.cons * 100).toFixed(0)}% энергии куплено из сети — в основном ночью и в пасмурные дни (${rpDays(e.gridDays)} из ${e.days}).`;
    if (shift > 0) text += ` Запускайте стирку и посудомойку днём (11:00–16:00), когда работают панели: это примерно ${rpKwh(shift * month)} и ≈ ${formatMoney(shift * month / 1000 * r.tariff)} в месяц.`;
    recs.push(["energy", text]);
  }
  const heat = r.rows.filter(x => x.device.type === "heater").reduce((s, x) => s + x.energy, 0);
  if (heat && e.cons && heat / e.cons > 0.25)
    recs.push(["energy", `Обогрев — ${(heat / e.cons * 100).toFixed(0)}% потребления дома. Снижение температуры на 1 °C экономит около 6% энергии на отопление — ≈ ${formatMoney(heat * 0.06 * month / 1000 * r.tariff)} в месяц.`]);
  if (e.gen && e.exportPct > 15) recs.push(["energy", `${e.exportPct.toFixed(0)}% выработки (${rpKwh(e.exp)}) ушло в сеть бесплатно: аккумулятор был полон. В солнечные дни включайте мощные приборы и зарядку авто днём.`]);
  if (!r.eco) recs.push(["energy", "Эко-режим выключен. Включите его, чтобы при низком заряде АКБ второстепенные мощные приборы отключались автоматически."]);
  r.rows.forEach(x => { if (x.device.type === "ev_charger" && !x.device.s.solar_only) recs.push(["energy", `${x.name}: включите режим «Только от излишков солнца» — авто будет заряжаться бесплатной энергией панелей.`]); });
  if (r.security.lockOpen) recs.push(["security", "Входной замок открыт — закройте его или включите автозакрытие."]);
  if (r.security.night.length) recs.push(["security", `Ночью камеры ${r.security.night.length} раз замечали человека — просмотрите записи за эти даты (список в разделе «Безопасность»).`]);
  const ending = r.rows.filter(x => x.warranty[0] === "ending");
  if (ending.length) recs.push(["care", "Скоро заканчивается гарантия: " + ending.map(x => `${x.name} (${rpDate(x.passport.warrantyUntil)})`).join(", ") + ". Проверьте эти устройства, пока ремонт бесплатный."]);
  if (!recs.length) recs.push(["home", "Замечаний нет: устройства исправны, обслуживание выполнено вовремя."]);
  return recs;
}

// ---------- SVG-графики ----------

function rpEnergyChart(buckets, w = 690, h = 250) {
  const L = 64, T = 40, R = 16, B = 28, pw = w - L - R, ph = h - T - B;
  let svg = `<svg class="rp-chart" viewBox="0 0 ${w} ${h}" width="100%" xmlns="http://www.w3.org/2000/svg" font-family="inherit">`;
  [["#00b96b", "Потребление от солнца и АКБ", 0], ["#e5484d", "Потребление из сети (платно)", 220], ["#f5b301", "Выработка панелей", 440]].forEach(([c, t, x], i) => {
    svg += i === 2 ? `<line x1="${L + x}" y1="14" x2="${L + x + 18}" y2="14" stroke="${c}" stroke-width="3"/>` : `<rect x="${L + x}" y="8" width="14" height="12" rx="3" fill="${c}"/>`;
    svg += `<text x="${L + x + 22}" y="18" font-size="11" fill="#3f5e75">${t}</text>`;
  });
  if (!buckets.length) return svg + `<text x="${w / 2}" y="${h / 2}" text-anchor="middle" fill="#8aa0b2">Нет данных за выбранный период</text></svg>`;
  const top = Math.max(...buckets.map(b => Math.max(b.cons, b.gen))) * 1.12 || 1000;
  const y = wh => T + ph - wh / top * ph;
  for (let i = 0; i <= 4; i++) {
    const v = top * i / 4, yy = y(v);
    svg += `<line x1="${L}" y1="${yy}" x2="${w - R}" y2="${yy}" stroke="#e3edf4"/><text x="${L - 8}" y="${yy + 4}" font-size="10" text-anchor="end" fill="#8aa0b2">${(v / 1000).toFixed(top / 1000 >= 8 ? 0 : 1)} кВт·ч</text>`;
  }
  const n = buckets.length, slot = pw / n, bw = Math.max(2, Math.min(34, slot * 0.68)), every = Math.max(1, Math.ceil(n / (pw / 52)));
  const pts = [];
  buckets.forEach((b, i) => {
    const cx = L + slot * (i + 0.5), grid = Math.min(b.imp, b.cons), solar = Math.max(0, b.cons - grid);
    svg += `<rect x="${cx - bw / 2}" y="${y(solar)}" width="${bw}" height="${T + ph - y(solar)}" fill="#00b96b" opacity="0.8"/>`;
    svg += `<rect x="${cx - bw / 2}" y="${y(solar + grid)}" width="${bw}" height="${y(solar) - y(solar + grid)}" fill="#e5484d" opacity="0.85"/>`;
    pts.push(`${cx},${y(b.gen)}`);
    if (i % every === 0) svg += `<text x="${cx}" y="${h - 8}" font-size="10" text-anchor="middle" fill="#8aa0b2">${b.label}</text>`;
  });
  svg += `<polyline points="${pts.join(" ")}" fill="none" stroke="#f5b301" stroke-width="2.5"/>`;
  if (n <= 40) pts.forEach(p => { const [cx, cy] = p.split(","); svg += `<circle cx="${cx}" cy="${cy}" r="3" fill="#f5b301"/>`; });
  return svg + "</svg>";
}

function rpHbars(items, maxValue, w = 690) {
  if (!items.length) return "";
  const rowH = 24, labelW = 230, textW = 150, barW = w - labelW - textW - 16, top = maxValue || Math.max(...items.map(i => i[1])) || 1;
  let svg = `<svg class="rp-chart" viewBox="0 0 ${w} ${rowH * items.length + 6}" width="100%" xmlns="http://www.w3.org/2000/svg">`;
  items.forEach(([label, value, color, text], i) => {
    const yy = 3 + i * rowH, short = label.length > 34 ? label.slice(0, 33) + "…" : label;
    svg += `<text x="${labelW - 8}" y="${yy + 16}" font-size="12" text-anchor="end" fill="#1d3346">${esc(short)}</text>`;
    svg += `<rect x="${labelW}" y="${yy + 5}" width="${barW}" height="${rowH - 10}" rx="4" fill="#eef3f7"/>`;
    svg += `<rect x="${labelW}" y="${yy + 5}" width="${Math.max(3, barW * Math.min(1, value / top))}" height="${rowH - 10}" rx="4" fill="${color}"/>`;
    svg += `<text x="${labelW + barW + 8}" y="${yy + 16}" font-size="11" font-weight="700" fill="#3f5e75">${esc(text)}</text>`;
  });
  return svg + "</svg>";
}

function rpDonut(items, center, sub, w = 560) {
  const h = Math.max(170, 24 * items.length + 16), size = h - 16, cx = 8 + size / 2, cy = 8 + size / 2, rad = size / 2 - 27;
  const total = items.reduce((s, i) => s + i[1], 0) || 1, circ = 2 * Math.PI * rad;
  let svg = `<svg class="rp-chart" viewBox="0 0 ${w} ${h}" width="100%" xmlns="http://www.w3.org/2000/svg">`;
  let offset = 0;
  items.forEach(([, v, color]) => {
    const len = v / total * circ;
    if (len > 0) svg += `<circle cx="${cx}" cy="${cy}" r="${rad}" fill="none" stroke="${color}" stroke-width="26" stroke-dasharray="${len} ${circ - len}" stroke-dashoffset="${-offset}" transform="rotate(-90 ${cx} ${cy})"/>`;
    offset += len;
  });
  svg += `<text x="${cx}" y="${cy + 4}" font-size="22" font-weight="800" text-anchor="middle" fill="#12293c">${esc(center)}</text>`;
  svg += `<text x="${cx}" y="${cy + 22}" font-size="10" text-anchor="middle" fill="#6b8396">${esc(sub)}</text>`;
  const x = size + 40, lineH = Math.min(24, (h - 10) / Math.max(1, items.length)), y0 = 6 + Math.max(0, (h - 12 - lineH * items.length) / 2);
  items.forEach(([label, , color, text], i) => {
    const yy = y0 + i * lineH;
    svg += `<rect x="${x}" y="${yy + lineH / 2 - 6}" width="12" height="12" rx="3" fill="${color}"/>`;
    svg += `<text x="${x + 20}" y="${yy + lineH / 2 + 4}" font-size="12" fill="#1d3346">${esc(label)}</text>`;
    svg += `<text x="${w - 4}" y="${yy + lineH / 2 + 4}" font-size="12" font-weight="700" text-anchor="end" fill="#1d3346">${esc(text)}</text>`;
  });
  return svg + "</svg>";
}

function rpGauge(score, color) {
  const rad = 69, circ = 2 * Math.PI * rad, len = score / 100 * circ;
  return `<svg class="rp-gauge" viewBox="0 0 170 170" width="170" height="170" xmlns="http://www.w3.org/2000/svg">
    <circle cx="85" cy="85" r="${rad}" fill="none" stroke="#e6eef4" stroke-width="16"/>
    <circle cx="85" cy="85" r="${rad}" fill="none" stroke="${color}" stroke-width="16" stroke-linecap="round" stroke-dasharray="${len} ${circ - len}" transform="rotate(-90 85 85)"/>
    <text x="85" y="96" font-size="40" font-weight="800" text-anchor="middle" fill="#12293c">${score}</text>
    <text x="85" y="118" font-size="12" text-anchor="middle" fill="#6b8396">из 100</text></svg>`;
}

// ---------- HTML ----------

class RpHtml {
  constructor() { this.parts = []; this.no = 0; }
  add(html) { this.parts.push(html); }
  text() { return this.parts.join(""); }
  title(title, r, subtitle) {
    this.add(`<h1>${esc(title)}</h1><p class="rp-muted">Умный дом пользователя <b>${esc(r.owner)}</b> · период <b>${rpDate(r.start)} — ${rpDate(r.end)}</b> (${rpDays(r.nDays)}) · сформирован ${r.generatedAt.toLocaleString("ru-RU", { dateStyle: "short", timeStyle: "short" })}</p>`);
    if (subtitle) this.add(`<p class="rp-muted">${esc(subtitle)}</p>`);
  }
  section(title, newPage) { this.no++; this.add(`<h2${newPage ? ' class="rp-break"' : ""}><span>${this.no}.</span> ${esc(title)}</h2>`); }
  sub(title) { this.add(`<h3>${esc(title)}</h3>`); }
  p(html, muted) { this.add(`<p${muted ? ' class="rp-muted"' : ""}>${html}</p>`); }
  note(html) { this.add(`<p class="rp-note">${html}</p>`); }
  box(title, items, color = "#00a05e", bg = "#eefaf4") {
    this.add(`<div class="rp-box" style="border-color:${color};background:${bg}"><span class="rp-box-title">${esc(title)}</span>${items.map(i => `<p>• ${i}</p>`).join("")}</div>`);
  }
  kpis(tiles) {
    this.add(`<div class="rp-kpis">${tiles.map(([label, value, sub, color]) => `<div class="rp-kpi"><div class="rp-muted">${esc(label)}</div><div class="v" style="color:${color || "#12293c"}">${value}</div><div class="rp-note">${sub}</div></div>`).join("")}</div>`);
  }
  table(headers, rows, align) {
    align = align || "l".repeat(headers.length);
    const al = { l: "left", r: "right", c: "center" };
    let html = `<div class="rp-table-wrap"><table class="rp-table"><thead><tr>${headers.map((hd, i) => `<th style="text-align:${al[align[i]]}">${hd}</th>`).join("")}</tr></thead><tbody>`;
    html += rows.map(row => `<tr>${row.map((c, i) => `<td style="text-align:${al[align[i]]}">${c}</td>`).join("")}</tr>`).join("");
    if (!rows.length) html += `<tr><td colspan="${headers.length}" class="rp-muted">Нет данных</td></tr>`;
    this.add(html + "</tbody></table></div>");
  }
  kv(pairs) { this.table(["Параметр", "Значение"], pairs.map(([k, v]) => [esc(k), v])); }
}

const rpBattery = lvl => (lvl === null ? '<span class="rp-muted">—</span>' : `<b style="color:${lvl < 10 ? "#e5484d" : lvl < BATTERY_LOW ? "#e08a00" : "#00a05e"}">${lvl}%</b>`);
function rpWarranty(row) {
  const [st, days] = row.warranty, until = rpDate(row.passport.warrantyUntil);
  if (st === "expired") return `<span style="color:#8aa0b2">истекла ${until}</span>`;
  if (st === "ending") return `<b style="color:#e08a00">до ${until} (осталось ${rpDays(days)})</b>`;
  return `<span style="color:#00a05e">до ${until}</span> <span class="rp-muted">(≈ ${Math.floor(days / 30)} мес.)</span>`;
}
function rpMaint(m) {
  if (!m) return '<span class="rp-muted">не требуется</span>';
  if (m.status === "overdue") return `<b style="color:#e5484d">просрочено на ${rpDays(-m.days)}</b>`;
  if (m.status === "soon") return `<b style="color:#e08a00">через ${rpDays(m.days)}</b>`;
  return `<span style="color:#00a05e">в норме, следующее ${rpDate(m.next)}</span>`;
}
const rpEventLine = e => [`${rpDate(e.day)} ${e.sim_time}`, esc(e.text)];
const rpName = row => `<b>${esc(row.name)}</b><br><span class="rp-muted">${esc(row.room)}</span>`;

function rpDevicesOverview(h, r) {
  const c = r.counts;
  h.add(rpDonut(["ok", "off", "offline", "broken"].map(k => [DEVICE_STATES[k][0], c[k], DEVICE_STATES[k][1], `${c[k]} (${(c[k] / Math.max(1, c.total) * 100).toFixed(0)}%)`]), String(c.total), "устройств"));
}
function rpAttention(h, r, levels) {
  levels = levels || ["high", "medium", "low"];
  const rows = r.attention.filter(a => levels.includes(a[0])).map(([sev, row, problem, action]) => [rpBadge(...RP_SEVERITY[sev]), rpName(row), esc(problem), esc(action)]);
  if (rows.length) h.table(["Важность", "Устройство", "Проблема", "Что сделать"], rows);
  else h.box("Проблем нет", ["Все устройства исправны, батарейки заряжены, обслуживание выполнено вовремя."]);
}
function rpByRoom(h, r) {
  RP_FLOORS.forEach(floor => r.rooms.filter(room => room.floor === floor).forEach(room => {
    const rows = r.rows.filter(row => row.roomId === room.id);
    if (!rows.length) return;
    h.sub(`${room.name} · ${FLOOR_NAMES[floor]} — ${rows.length} ${plural(rows.length, "устройство", "устройства", "устройств")}, работают ${rows.filter(x => x.state === "ok").length}`);
    h.table(["Устройство", "Состояние", "Мощность сейчас", "Работа за период", "Батарея", "Последнее событие"], rows.map(row => {
      const last = row.lastEvent;
      return [`<b>${esc(row.name)}</b><br><span class="rp-muted">${esc(row.model)}</span>`,
        `${rpState(row.state)}<br><span class="rp-muted">${esc(row.incident ? row.incident.issue : row.detail)}</span>`,
        row.powerNow >= 1 ? formatPower(row.powerNow) : "—", `${row.hours.toFixed(0)} ч<br><span class="rp-muted">${row.switches} вкл.</span>`,
        rpBattery(row.battery), last ? `<span class="rp-note">${rpDate(last.day).slice(0, 5)} ${last.sim_time} — ${esc(last.text)}</span>` : "—"];
    }), "llrrcl");
  }));
}
function rpBatteries(h, r) {
  const rows = r.rows.filter(x => x.battery !== null).sort((a, b) => a.battery - b.battery);
  if (!rows.length) { h.p("Устройств с батарейным питанием нет.", true); return; }
  h.add(rpHbars(rows.map(x => [`${x.name} (${x.room})`, x.battery, x.battery < 10 ? "#e5484d" : x.battery < BATTERY_LOW ? "#e08a00" : "#00b96b", `${x.battery}% · ≈ ${rpDays(x.batteryDays)}`]), 100));
  h.note(`Батарейки разряжаются постепенно со дня установки или последней замены. Ниже ${BATTERY_LOW}% — пора менять, ниже 10% — датчик может отключиться в любой момент. «≈ N дней» — сколько осталось до полного разряда.`);
}
function rpIncidents(h, r) {
  h.table(["Дата", "Устройство", "Что случилось", "Длительность", "Итог"], r.periodIncidents.map(([row, inc]) => [
    rpDate(inc.start), rpName(row), esc(inc.issue), rpDays(Math.max(1, isoDiff(inc.start, inc.end || r.today))),
    inc.end ? `${rpBadge("устранено", "#00a05e")}<br><span class="rp-muted">${rpDate(inc.end)}: ${esc(inc.fix || "")}</span>` : rpBadge("не устранено", "#e5484d")]));
}
function rpEnergyKpis(h, r) {
  const e = r.energy;
  h.kpis([
    ["Выработали панели", rpKwh(e.gen), `в среднем ${rpKwh(e.gen / Math.max(1, e.days))} в день`, "#c98a00"],
    ["Потребил дом", rpKwh(e.cons), `в среднем ${rpKwh(e.cons / Math.max(1, e.days))} в день`],
    ["Взято из сети", rpKwh(e.imp), e.cons ? `${(e.imp / e.cons * 100).toFixed(0)}% потребления` : "", "#e5484d"],
    ["К оплате за сеть", formatMoney(e.pay), `по тарифу ${r.tariff} ₸/кВт·ч`, "#e5484d"],
    ["Сэкономлено солнцем", formatMoney(e.saved), `без панелей счёт был бы ${formatMoney(e.nosolar)}`, "#00a05e"],
    ["Самообеспеченность", rpPct(e.selfPct), "доля потребления без покупки из сети", "#00a05e"],
  ]);
}
function rpConsumers(h, r, top = 10) {
  const rows = r.rows.filter(x => x.energy > 0).sort((a, b) => b.energy - a.energy), cons = r.energy.cons || 1;
  h.add(rpHbars(rows.slice(0, top).map(x => [`${x.name} (${x.room})`, x.energy, "#3f8fd2", `${rpKwh(x.energy)} · ${(x.energy / cons * 100).toFixed(0)}%`])));
  return rows;
}
function rpRooms(h, r) {
  const e = r.energy, cons = e.cons || 1;
  h.add(rpHbars(Object.entries(e.byRoom).filter(([, v]) => v > 0).sort((a, b) => b[1] - a[1]).map(([n, v]) => [n, v, "#00b96b", `${rpKwh(v)} · ${formatMoney(v / 1000 * r.tariff)}`])));
  h.note(`Ещё ${rpKwh(e.other)} (${(e.other / cons * 100).toFixed(0)}%) — фоновое потребление дома, которое не относится к умным устройствам: обычные розетки, освещение, роутер провайдера.`);
}
function rpRecs(h, r, sections) {
  const recs = r.recommendations.filter(([sec]) => !sections || sections.includes(sec) || sec === "home").map(x => x[1]);
  h.add(`<ol class="rp-recs">${(recs.length ? recs : ["Замечаний нет."]).map(t => `<li>${esc(t)}</li>`).join("")}</ol>`);
}
function rpPassport(h, r) {
  h.table(["Устройство", "Модель", "Серийный номер", "Прошивка", "Установлено", "Мощность"], r.rows.map(x => [
    `<b>${esc(x.name)}</b><br><span class="rp-muted">${esc(x.room)} · ${esc(x.type)}</span>`, esc(x.model), x.passport.serial, x.passport.firmware,
    rpDate(x.passport.added), formatPower(x.powerRated)]), "lllcrr");
}
const rpMethod = h => h.note("Как считались цифры: выработка, потребление, покупка из сети и отдача в сеть — по суточной истории энергосистемы (сегодняшний день — по данным симуляции). Расход отдельных устройств оценивается по мощности модели и типичному времени работы с учётом сезона и масштабируется так, чтобы сумма совпала с потреблением дома. Деньги — по тарифу, заданному в программе. Отданная в сеть энергия не оплачивается.");

function rpHtmlDevices(r) {
  const h = new RpHtml(), c = r.counts;
  h.title(RP_TITLES.devices, r);
  const problems = r.attention.filter(a => a[0] !== "low");
  const floors = new Set(r.rooms.map(x => x.floor)).size;
  const used = r.rows.filter(x => !ALWAYS_RUNNING_TYPES.has(x.device.type)).sort((a, b) => b.hours - a.hours)[0];
  const summary = [
    `В доме <b>${c.total}</b> ${plural(c.total, "устройство", "устройства", "устройств")} в ${r.rooms.length} ${plural(r.rooms.length, "комнате", "комнатах", "комнатах")} (${floors} ${plural(floors, "этаж/зона", "этажа/зоны", "этажей/зон")}).`,
    `Сейчас работают <b>${c.ok}</b>, выключены ${c.off}, без связи <b>${c.offline}</b>, неисправны <b>${c.broken}</b>.`,
    problems.length ? `Требуют внимания: <b>${problems.length}</b> — ${problems.slice(0, 3).map(a => `${esc(a[1].name)} (${esc(a[2].toLowerCase())})`).join("; ")}.` : "Срочных проблем нет.",
    c.lowBattery ? `Батарейки: ${c.lowBattery} ${plural(c.lowBattery, "устройство", "устройства", "устройств")} с зарядом ниже ${BATTERY_LOW}%.` : "Все батарейки заряжены.",
  ];
  if (used && used.hours > 0) summary.push(`Чаще всего использовали: <b>${esc(used.name)}</b> (${esc(used.room)}) — ≈ ${used.hours.toFixed(0)} ч работы за период.`);
  const bad = c.broken || c.offline;
  h.box("Кратко", summary, bad ? "#e5484d" : "#00a05e", bad ? "#fdf0f0" : "#eefaf4");
  h.section("Общее состояние");
  rpDevicesOverview(h, r);
  h.kpis([["Всего устройств", String(c.total), `в ${r.rooms.length} комнатах`], ["Работают", String(c.ok), "включены и на связи", "#00a05e"],
    ["Выключены", String(c.off), "исправны, но выключены", "#6b8396"], ["Нет связи", String(c.offline), "не отвечают шлюзу / Wi-Fi", "#e08a00"],
    ["Неисправны", String(c.broken), "нужен ремонт", "#e5484d"], ["Слабые батарейки", String(c.lowBattery), `заряд ниже ${BATTERY_LOW}%`, "#e08a00"]]);
  h.section("Что требует внимания");
  h.p("Список отсортирован по важности: сначала то, что нужно сделать срочно.", true);
  rpAttention(h, r);
  h.section("Устройства по этажам и комнатам", true);
  h.p("Для каждого устройства: где стоит, модель, состояние сейчас, мощность, сколько часов оно работало и сколько раз его включали за период, заряд батарейки и последнее событие из журнала.", true);
  rpByRoom(h, r);
  h.section("Батарейки датчиков и замков");
  rpBatteries(h, r);
  h.section("Активность за период");
  h.sub("Самые используемые устройства (часов работы за период)");
  h.add(rpHbars(r.rows.filter(x => x.hours > 0 && !ALWAYS_RUNNING_TYPES.has(x.device.type)).sort((a, b) => b.hours - a.hours).slice(0, 10)
    .map(x => [`${x.name} (${x.room})`, x.hours, "#7b61ff", `${x.hours.toFixed(0)} ч · ${x.switches} вкл.`])));
  h.sub("Неисправности и потеря связи за период");
  rpIncidents(h, r);
  h.section("Рекомендации");
  rpRecs(h, r, ["devices", "care"]);
  h.section("Паспорт устройств", true);
  rpPassport(h, r);
  return h.text();
}

function rpHtmlEnergy(r) {
  const h = new RpHtml(), e = r.energy, prev = e.prev;
  h.title(RP_TITLES.energy, r);
  const rows = r.rows.filter(x => x.energy > 0).sort((a, b) => b.energy - a.energy), top = rows[0];
  const summary = [
    `Панели выработали <b>${rpKwh(e.gen)}</b>, дом потребил <b>${rpKwh(e.cons)}</b> — ${rpChangeText(e.cons, prev.ok ? prev.cons : null, rpKwh)}.`,
    `Из сети куплено <b>${rpKwh(e.imp)}</b> на <b>${formatMoney(e.pay)}</b>; без солнечных панелей счёт был бы ${formatMoney(e.nosolar)} — сэкономлено <b>${formatMoney(e.saved)}</b>.`,
    `Самообеспеченность <b>${rpPct(e.selfPct)}</b>: столько энергии дом получил от солнца и аккумулятора.`,
    `Дом брал энергию из сети в ${rpDays(e.gridDays)} из ${e.days}; аккумулятор заряжался полностью в ${rpDays(e.fullDays)}.`,
  ];
  if (top) summary.push(`Больше всего потребляет: <b>${esc(top.name)}</b> (${esc(top.room)}) — ${rpKwh(top.energy)}, ${(top.energy / Math.max(1, e.cons) * 100).toFixed(0)}% всего потребления.`);
  h.box("Кратко", summary);
  h.section("Главные показатели");
  rpEnergyKpis(h, r);
  h.section("Баланс энергии и сравнение с прошлым периодом");
  h.p(prev.ok ? `Прошлый период для сравнения: ${rpDate(prev.start)} — ${rpDate(prev.end)} (столько же дней).`
    : `Прошлый период (${rpDate(prev.start)} — ${rpDate(prev.end)}) захватывает время до запуска системы (${rpDate(isoDate(HOME_SINCE))}), поэтому сравнение не проводится — выберите период покороче.`, true);
  const delta = (now, before, goodUp = true) => {
    if (!before || !prev.ok) return "—";
    const pct = (now - before) / before * 100, good = (pct >= 0) === goodUp;
    return `<b style="color:${good ? "#00a05e" : "#e5484d"}">${pct >= 0 ? "+" : "−"}${Math.abs(pct).toFixed(0)}%</b>`;
  };
  const pSelf = prev.cons ? (prev.cons - prev.imp) / prev.cons * 100 : 0, pPay = prev.imp / 1000 * r.tariff, pSaved = Math.max(0, prev.cons - prev.imp) / 1000 * r.tariff;
  h.table(["Показатель", "Этот период", "Прошлый период", "Изменение"], [
    ["Выработка панелей", rpKwh(e.gen), rpKwh(prev.gen), delta(e.gen, prev.gen)],
    ["Потребление дома", rpKwh(e.cons), rpKwh(prev.cons), delta(e.cons, prev.cons, false)],
    ["Куплено из сети", rpKwh(e.imp), rpKwh(prev.imp), delta(e.imp, prev.imp, false)],
    ["Отдано в сеть (бесплатно)", rpKwh(e.exp), rpKwh(prev.exp), delta(e.exp, prev.exp, false)],
    ["Самообеспеченность", rpPct(e.selfPct), prev.cons ? rpPct(pSelf) : "—", prev.cons && prev.ok ? `${(e.selfPct - pSelf).toFixed(0)} п.п.` : "—"],
    ["К оплате за сеть", formatMoney(e.pay), formatMoney(pPay), delta(e.pay, pPay, false)],
    ["Сэкономлено солнцем", formatMoney(e.saved), formatMoney(pSaved), delta(e.saved, pSaved)],
  ], "lrrr");
  h.note("Зелёным отмечены изменения к лучшему, красным — к худшему.");
  const daily = r.nDays <= 62;
  h.section(`Потребление и выработка ${daily ? "по дням" : "по месяцам"}`, true);
  h.add(rpEnergyChart(e.buckets));
  h.note("Столбик — потребление дома: зелёная часть получена от солнца и аккумулятора, красная куплена из сети. Жёлтая линия — выработка солнечных панелей.");
  h.table([daily ? "День" : "Месяц", "Выработка", "Потребление", "Из сети", "В сеть", "К оплате"],
    e.buckets.map(b => [b.title, rpKwh(b.gen), rpKwh(b.cons), b.imp > 1 ? `<span style="color:#c0392b">${rpKwh(b.imp)}</span>` : rpKwh(b.imp), rpKwh(b.exp), formatMoney(b.cost)])
      .concat([["<b>Итого</b>", `<b>${rpKwh(e.gen)}</b>`, `<b>${rpKwh(e.cons)}</b>`, `<b>${rpKwh(e.imp)}</b>`, `<b>${rpKwh(e.exp)}</b>`, `<b>${formatMoney(e.pay)}</b>`]]), "lrrrrr");
  if (e.bestDay) h.p(`Самый солнечный день — <b>${rpDate(e.bestDay)}</b> (${rpKwh(e.daysMap[e.bestDay][0])}), самый пасмурный — <b>${rpDate(e.worstDay)}</b> (${rpKwh(e.daysMap[e.worstDay][0])}), больше всего потребили <b>${rpDate(e.peakDay)}</b> (${rpKwh(e.daysMap[e.peakDay][1])}).`);
  h.section("Кто потребляет энергию", true);
  h.sub("10 самых «прожорливых» устройств");
  const all = rpConsumers(h, r);
  h.sub("По комнатам");
  rpRooms(h, r);
  h.sub("По категориям");
  const pal = ["#00b96b", "#3f8fd2", "#f5b301", "#e5484d", "#7b61ff", "#ff8a3d", "#14b8a6", "#8aa0b2"];
  h.add(rpDonut(Object.entries(e.byGroup).filter(([, v]) => v > 0).sort((a, b) => b[1] - a[1]).slice(0, 8)
    .map(([n, v], i) => [n, v, pal[i % pal.length], `${rpKwh(v)} · ${(v / Math.max(1, e.cons) * 100).toFixed(0)}%`]), (e.cons / 1000).toFixed(0), "кВт·ч всего"));
  h.sub("Все устройства");
  h.table(["Устройство", "Комната", "Энергия", "Доля", "Стоимость", "Часов работы"],
    all.map(x => [esc(x.name), esc(x.room), rpKwh(x.energy), `${(x.energy / Math.max(1, e.cons) * 100).toFixed(1)}%`, formatMoney(x.cost), x.hours.toFixed(0)]), "llrrrr");
  h.section("Аккумулятор и внешняя сеть");
  h.kpis([["Дней с покупкой из сети", `${e.gridDays} из ${e.days}`, "аккумулятор разряжался ночью", "#e5484d"],
    ["Дней с полной зарядкой АКБ", `${e.fullDays} из ${e.days}`, "излишки уходили в сеть", "#00a05e"],
    ["Срабатываний эко-режима", String(e.ecoCount), "отключение мощных приборов при заряде < 20%", "#e08a00"]]);
  h.p(`Аккумулятор ёмкостью ${C.BATTERY_CAPACITY_WH / 1000} кВт·ч переносит дневную энергию солнца на вечер и ночь. Когда заряд падает до резерва ${C.BATTERY_RESERVE * 100}%, дом переходит на внешнюю сеть — это и есть «покупка из сети». Сейчас заряд ${(r.batteryLevel * 100).toFixed(0)}%.`);
  h.section("Деньги");
  h.table(["Статья", "Сумма"], [["Без солнечных панелей заплатили бы", formatMoney(e.nosolar)],
    ["Фактически к оплате за сеть", `<b style="color:#e5484d">${formatMoney(e.pay)}</b>`], ["Экономия за период", `<b style="color:#00a05e">${formatMoney(e.saved)}</b>`],
    ["Экономия в пересчёте на год", formatMoney(e.annualSaving)], ["Стоимость панелей и аккумулятора", formatMoney(SOLAR_SYSTEM_COST_KZT)],
    ["Окупаемость при текущем тарифе", e.paybackYears ? `≈ ${e.paybackYears.toFixed(0)} лет` : "—"]], "lr");
  h.note(`Тариф ${r.tariff} ₸ за кВт·ч задаётся на вкладке «Энергия». При росте тарифа экономия растёт, а окупаемость сокращается.`);
  h.section("Экология");
  h.kpis([["CO₂ не выброшено", `${Math.round(e.co2).toLocaleString("ru-RU")} кг`, `${C.CO2_KG_PER_KWH} кг CO₂ на кВт·ч сети РК`, "#00a05e"],
    ["Как деревьев за год", e.trees.toFixed(0), `одно дерево поглощает ≈ ${C.CO2_PER_TREE_KG} кг CO₂ в год`, "#00a05e"],
    ["Отдано в сеть", rpKwh(e.exp), `${e.exportPct.toFixed(0)}% выработки`]]);
  h.section("Рекомендации по экономии");
  rpRecs(h, r, ["energy"]);
  rpMethod(h);
  return h.text();
}

function rpHtmlHome(r) {
  const h = new RpHtml(), e = r.energy, c = r.counts, s = r.security, care = r.care, [label, color] = rpScoreLabel(r.score.total);
  h.title(RP_TITLES.home, r, "Сводный отчёт: устройства, электроэнергия, безопасность, гарантия и обслуживание.");
  h.add(`<div class="rp-score">${rpGauge(r.score.total, color)}<div class="rp-score-text"><div class="rp-muted">Общая оценка состояния дома</div>
    <div class="rp-score-label" style="color:${color}">${label}</div>
    <table class="rp-parts">${r.score.parts.map(([n, v, w]) => `<tr><td>${esc(n)} <span class="rp-muted">(вес ${w}%)</span></td><td style="text-align:right"><b style="color:${rpScoreLabel(v)[1]}">${v}</b> / 100</td></tr>`).join("")}</table></div></div>`);
  const problems = r.attention.filter(a => a[0] !== "low");
  h.box("Кратко", [
    `Устройства: работают ${c.ok} из ${c.total}, без связи ${c.offline}, неисправны ${c.broken}` + (problems.length ? `; требуют внимания — ${problems.length}.` : "; проблем нет."),
    `Энергия: выработано ${rpKwh(e.gen)}, потреблено ${rpKwh(e.cons)}, самообеспеченность ${rpPct(e.selfPct)}, к оплате ${formatMoney(e.pay)}, сэкономлено ${formatMoney(e.saved)}.`,
    `Безопасность: камеры заметили людей ${s.people} раз, датчики движения сработали ${s.motion} раз` + (s.night.length ? `, ночных обнаружений ${s.night.length}` : ", ночью посторонних не было") + (s.lockOpen ? ". Входной замок открыт!" : "."),
    `Гарантия: на гарантии ${care.active + care.ending} устройств, скоро истекает ${care.ending}, истекла ${care.expired}. Обслуживание: просрочено ${care.overdue}, скоро ${care.soon}.`,
  ], color, "#f4f8fb");
  h.section("Общие сведения о доме");
  const floors = new Set(r.rooms.map(x => x.floor));
  h.kv([["Владелец", esc(r.owner)], ["Система работает с", `${rpDate(isoDate(HOME_SINCE))} (${rpDays(isoDiff(isoDate(HOME_SINCE), r.today))})`],
    ["Этажи и зоны", RP_FLOORS.filter(f => floors.has(f)).map(f => FLOOR_NAMES[f]).join(", ")], ["Комнат", String(r.rooms.length)],
    ["Умных устройств", String(c.total)], ["Солнечные панели", `${C.SOLAR_PEAK_W / 1000} кВт (пиковая мощность)`],
    ["Аккумулятор", `${C.BATTERY_CAPACITY_WH / 1000} кВт·ч, заряд сейчас ${(r.batteryLevel * 100).toFixed(0)}%`],
    ["Тариф на электроэнергию", `${r.tariff} ₸ за кВт·ч`], ["Эко-режим", r.eco ? "включён" : "выключен"], ["Стоимость умных устройств", formatMoney(care.value)]]);
  h.section("Энергосистема", true);
  rpEnergyKpis(h, r);
  h.add(rpEnergyChart(e.buckets, 690, 230));
  h.p(`Потребление ${rpChangeText(e.cons, e.prev.ok ? e.prev.cons : null, rpKwh)}. Дом покупал энергию из сети в ${rpDays(e.gridDays)} из ${e.days}, эко-режим срабатывал ${e.ecoCount} раз. CO₂ не выброшено: ${Math.round(e.co2).toLocaleString("ru-RU")} кг (как ${e.trees.toFixed(0)} деревьев за год).`);
  h.section("Устройства");
  rpDevicesOverview(h, r);
  h.sub("Требуют внимания");
  rpAttention(h, r, ["high", "medium"]);
  h.sub("Неисправности за период");
  rpIncidents(h, r);
  h.section("Потребление по комнатам и устройствам", true);
  h.sub("По комнатам");
  rpRooms(h, r);
  h.sub("Главные потребители");
  rpConsumers(h, r, 8);
  h.section("Безопасность");
  h.kpis([["Люди на камерах", String(s.people), "срабатываний детекции", "#c0392b"], ["Датчики движения", String(s.motion), "срабатываний"],
    ["Звонки в дверь", String(s.doorbell), "посетители"], ["Ночные обнаружения", String(s.night.length), "с 23:00 до 06:00", s.night.length ? "#e5484d" : "#00a05e"],
    ["Входной замок", s.lockOpen ? "Открыт" : "Закрыт", "сейчас", s.lockOpen ? "#e5484d" : "#00a05e"], ["Охранных устройств", String(s.rows.length), "камеры, замки, датчики"]]);
  h.table(["Устройство", "Комната", "Состояние", "Батарея", "Событий за период"], s.rows.map(x => [esc(x.name), esc(x.room), rpState(x.state), rpBattery(x.battery), String(x.events)]), "lllcr");
  if (s.night.length) { h.sub("Ночные обнаружения"); h.table(["Когда", "Событие"], s.night.map(rpEventLine)); }
  h.section("Гарантия и обслуживание", true);
  h.kpis([["Стоимость устройств", formatMoney(care.value), `${c.total} устройств`], ["На гарантии", String(care.active + care.ending), `из них скоро истекает ${care.ending}`, "#00a05e"],
    ["Гарантия истекла", String(care.expired), "ремонт платный", "#8aa0b2"], ["Обслуживание просрочено", String(care.overdue), "нужно выполнить", care.overdue ? "#e5484d" : "#00a05e"],
    ["Скоро обслуживание", String(care.soon), "в ближайшие 7 дней", "#e08a00"], ["Выполнено за период", String(care.servicesDone), "работ по обслуживанию"]]);
  h.sub("Гарантия");
  h.table(["Устройство", "Куплено", "Цена", "Срок", "Гарантия"], r.warrantyRows.map(x => [rpName(x), rpDate(x.passport.purchase), formatMoney(x.passport.price), `${x.passport.warrantyMonths} мес.`, rpWarranty(x)]), "lrrcl");
  h.sub("Регламентное обслуживание");
  h.table(["Устройство", "Что делать", "Как часто", "Последний раз", "Статус"], r.maintenanceRows.map(x => [rpName(x), esc(x.maintenance.task), `раз в ${x.maintenance.interval} дн.`, rpDate(x.maintenance.last), rpMaint(x.maintenance)]), "llccl");
  h.section("Важные события за период", true);
  h.p("Неисправности, обслуживание, переходы на сеть, эко-режим, ночные обнаружения. Обычные события (включения, датчики движения) смотрите во вкладке «События».", true);
  h.table(["Когда", "Событие"], r.important.slice(-60).reverse().map(rpEventLine));
  if (r.important.length > 60) h.note(`Показаны последние 60 из ${r.important.length} событий.`);
  h.section("Рекомендации");
  rpRecs(h, r);
  h.section("Приложение: паспорт устройств", true);
  rpPassport(h, r);
  rpMethod(h);
  return h.text();
}

const RP_BUILDERS = { devices: rpHtmlDevices, energy: rpHtmlEnergy, home: rpHtmlHome };
function rpBuild(kind, eng, start, end) { return RP_BUILDERS[kind](rpCollect(eng, start, end)); }
