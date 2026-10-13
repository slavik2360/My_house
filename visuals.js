// Анимированные визуализации устройств (canvas) - аналоги виджетов настольной версии.
"use strict";

function rr(ctx, x, y, w, h, r) {
  r = Math.min(r, w / 2, h / 2);
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}
function circle(ctx, x, y, r) { ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); }
function lerpRgb(a, b, t) { return mixColor(a, b, t); }

// Базовый класс: canvas нужной высоты с учётом плотности пикселей экрана, анимация через общий цикл
class CanvasView {
  constructor(parent, height) {
    this.wrap = document.createElement("div");
    this.wrap.className = "viz";
    this.canvas = document.createElement("canvas");
    this.canvas.style.height = height + "px";
    this.wrap.appendChild(this.canvas);
    parent.appendChild(this.wrap);
    this.height = height;
    this.last = performance.now();
    Visuals.add(this);
  }
  prepare() {
    const dpr = window.devicePixelRatio || 1;
    const w = this.canvas.clientWidth, h = this.height;
    if (this.canvas.width !== Math.round(w * dpr) || this.canvas.height !== Math.round(h * dpr)) {
      this.canvas.width = Math.round(w * dpr);
      this.canvas.height = Math.round(h * dpr);
    }
    const ctx = this.canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    return [ctx, w, h];
  }
  frame(now) {
    const k = Math.min(3, (now - this.last) / 33); // шаг анимации относительно 30 кадров/с
    this.last = now;
    if (!this.canvas.isConnected || !this.canvas.clientWidth) return;
    if (this.step) this.step(k);
    const [ctx, w, h] = this.prepare();
    this.draw(ctx, w, h);
  }
}

// Общий цикл анимации: рисует только виджеты, которые сейчас на экране
const Visuals = {
  list: [],
  running: false,
  add(v) { this.list.push(v); this.start(); },
  clear() { this.list = []; },
  start() {
    if (this.running) return;
    this.running = true;
    const loop = now => {
      this.list = this.list.filter(v => v.canvas.isConnected);
      this.list.forEach(v => v.frame(now));
      if (this.list.length) requestAnimationFrame(loop); else this.running = false;
    };
    requestAnimationFrame(loop);
  },
};

// ---------- свет ----------

class LightPreview extends CanvasView {
  constructor(parent, d) { super(parent, 150); this.d = d; }
  draw(ctx, w, h) {
    const g = ctx.createLinearGradient(0, 0, 0, h);
    g.addColorStop(0, "#1c2733"); g.addColorStop(1, "#121a23");
    ctx.fillStyle = g; rr(ctx, 0, 0, w, h, 16); ctx.fill();
    const cx = w / 2, cy = h / 2 - 8, on = this.d.on, b = (this.d.s.brightness ?? 100) / 100, col = lightRgb(this.d);
    if (on) {
      const r = 40 + 80 * b, rg = ctx.createRadialGradient(cx, cy, 0, cx, cy, r);
      rg.addColorStop(0, rgbCss(col, 0.5 + 0.5 * b)); rg.addColorStop(0.45, rgbCss(col, 0.1 + 0.25 * b)); rg.addColorStop(1, rgbCss(col, 0));
      ctx.fillStyle = rg; circle(ctx, cx, cy, r); ctx.fill();
    }
    ctx.fillStyle = on ? rgbCss(mixColor([255, 255, 255], col, 0.55)) : "#4a5562";
    ctx.strokeStyle = on ? "#fff" : "#6b7785"; ctx.lineWidth = 2;
    circle(ctx, cx, cy, 28); ctx.fill(); ctx.stroke();
    ctx.fillStyle = "#9aa5b1"; rr(ctx, cx - 13, cy + 24, 26, 20, 5); ctx.fill();
    ctx.fillStyle = "#c8d3dd"; ctx.font = "12px -apple-system, sans-serif"; ctx.textAlign = "center";
    ctx.fillText(on ? `Яркость ${Math.round(b * 100)}%` : "Свет выключен", cx, h - 10);
  }
}

// ---------- чайник ----------

class KettleView extends CanvasView {
  constructor(parent, d) {
    super(parent, 320);
    this.d = d;
    this.capacity = MODELS[d.model].capacity_ml || 1700;
    this.temp = d.s.water_temp ?? C.ROOM_TEMP;
    this.level = (d.s.water_ml || 0) / this.capacity;
    this.phase = 0; this.bubbles = []; this.steam = [];
  }
  geo(w) { return [w / 2 - 12, 76, 205]; }
  waterTop(w) { const [, y0, bh] = this.geo(w); return y0 + bh - 8 - this.level * (bh - 22); }
  step(k) {
    const s = this.d.s, w = this.canvas.clientWidth;
    this.temp += ((s.water_temp ?? C.ROOM_TEMP) - this.temp) * 0.1 * k;
    this.level += (Math.min(1, (s.water_ml || 0) / this.capacity) - this.level) * 0.12 * k;
    const heating = kettleHeating(this.d);
    this.phase += (0.09 + (heating ? 0.12 + 0.2 * Math.max(0, this.temp - 60) / 40 : 0)) * k;
    const [cx, y0, bh] = this.geo(w), top = this.waterTop(w);
    if (heating && this.level > 0.05 && this.temp > 40) {
      const it = (this.temp - 40) / 60;
      for (let i = 0; i < 3; i++) if (Math.random() < it * 0.8 * k) this.bubbles.push([cx + (Math.random() * 150 - 75), y0 + bh - 10, 2 + Math.random() * (1 + 4 * it), 1.5 + Math.random() * (1 + 3 * it)]);
    }
    this.bubbles.forEach(b => { b[1] -= b[3] * k; b[0] += Math.sin(b[1] / 9) * 0.6; });
    this.bubbles = this.bubbles.filter(b => b[1] > top + 4);
    if (this.temp > 75 && this.level > 0.05 && Math.random() < (this.temp - 75) / 25 * 0.6 * k) this.steam.push([cx - 108 + Math.random() * 12 - 6, y0 - 10, 6 + Math.random() * 4, 150]);
    this.steam.forEach(p => { p[1] -= 1.4 * k; p[0] -= (0.4 + Math.random() * 0.8 - 0.4) * k; p[2] += 0.35 * k; p[3] -= 2.4 * k; });
    this.steam = this.steam.filter(p => p[3] > 0);
  }
  bodyPath(ctx, w) {
    const [cx, y0, bh] = this.geo(w), tw = 70, bw = 94;
    ctx.beginPath();
    ctx.moveTo(cx - tw + 14, y0); ctx.lineTo(cx + tw - 14, y0);
    ctx.quadraticCurveTo(cx + tw, y0, cx + tw + 2, y0 + 16);
    ctx.lineTo(cx + bw - 2, y0 + bh - 18);
    ctx.quadraticCurveTo(cx + bw, y0 + bh, cx + bw - 18, y0 + bh);
    ctx.lineTo(cx - bw + 18, y0 + bh);
    ctx.quadraticCurveTo(cx - bw, y0 + bh, cx - bw + 2, y0 + bh - 18);
    ctx.lineTo(cx - tw - 2, y0 + 16);
    ctx.quadraticCurveTo(cx - tw, y0, cx - tw + 14, y0);
    ctx.closePath();
  }
  draw(ctx, w) {
    const d = this.d, s = d.s, [cx, y0, bh] = this.geo(w);
    const heating = kettleHeating(d), keeping = d.on && !heating && s.keep_warm;
    let led = [89, 99, 110];
    if (s.color && d.on) led = hexRgb(s.color); else if (heating) led = [255, 107, 61]; else if (keeping) led = [245, 166, 35];
    if (heating || keeping) {
      const g = ctx.createRadialGradient(cx, y0 + bh + 14, 0, cx, y0 + bh + 14, 150);
      g.addColorStop(0, rgbCss(led, 0.45)); g.addColorStop(1, rgbCss(led, 0));
      ctx.fillStyle = g; ctx.beginPath(); ctx.ellipse(cx, y0 + bh + 14, 150, 50, 0, 0, Math.PI * 2); ctx.fill();
    }
    ctx.fillStyle = "#2f3640"; rr(ctx, cx - 114, y0 + bh - 4, 228, 32, 12); ctx.fill();
    ctx.fillStyle = rgbCss(led); rr(ctx, cx - 80, y0 + bh + 10, 160, 6, 3); ctx.fill();
    // ручка
    ctx.strokeStyle = "#2f3640"; ctx.lineWidth = 16; ctx.lineCap = "round";
    ctx.beginPath(); ctx.moveTo(cx + 74, y0 + 26); ctx.bezierCurveTo(cx + 150, y0 + 22, cx + 150, y0 + 170, cx + 92, y0 + 176); ctx.stroke();
    // носик
    ctx.lineWidth = 3; ctx.strokeStyle = "#9fb3c3"; ctx.fillStyle = "rgba(225,240,250,0.5)";
    ctx.beginPath(); ctx.moveTo(cx - 66, y0 + 6); ctx.lineTo(cx - 112, y0 - 8); ctx.lineTo(cx - 106, y0 + 14); ctx.lineTo(cx - 72, y0 + 44); ctx.closePath(); ctx.fill(); ctx.stroke();
    // колба
    this.bodyPath(ctx, w); ctx.fillStyle = "rgba(225,240,250,0.45)"; ctx.fill();
    if (this.level > 0.01) {
      ctx.save(); this.bodyPath(ctx, w); ctx.clip();
      const water = lerpRgb([61, 157, 245], [255, 122, 69], (this.temp - 20) / 80), top = this.waterTop(w);
      const amp = 3 + (heating ? 5 * Math.max(0, this.temp - 60) / 40 : 0);
      [[0.45, 1.7, 0], [0.8, 0, 3]].forEach(([alpha, shift, off]) => {
        ctx.beginPath(); ctx.moveTo(cx - 120, y0 + bh + 5);
        for (let x = cx - 120; x <= cx + 120; x += 4) ctx.lineTo(x, top + off + amp * Math.sin(x / 19 + this.phase + shift) + amp * 0.4 * Math.sin(x / 7 - this.phase * 1.6));
        ctx.lineTo(cx + 120, y0 + bh + 5); ctx.closePath();
        const g = ctx.createLinearGradient(0, top, 0, y0 + bh);
        g.addColorStop(0, rgbCss(mixColor(water, [255, 255, 255], 0.2), alpha)); g.addColorStop(1, rgbCss(mixColor(water, [0, 0, 0], 0.12), alpha));
        ctx.fillStyle = g; ctx.fill();
      });
      ctx.fillStyle = "rgba(255,255,255,0.67)";
      this.bubbles.forEach(b => { circle(ctx, b[0], b[1], b[2]); ctx.fill(); });
      ctx.restore();
    }
    ctx.fillStyle = "rgba(255,255,255,0.27)"; rr(ctx, cx - 60, y0 + 22, 14, bh - 60, 7); ctx.fill();
    this.bodyPath(ctx, w); ctx.strokeStyle = "#9fb3c3"; ctx.lineWidth = 3; ctx.stroke();
    // шкала
    ctx.font = "bold 11px -apple-system, sans-serif"; ctx.textAlign = "right"; ctx.textBaseline = "middle";
    const marks = [500, 1000, 1500].filter(ml => ml < this.capacity).concat([this.capacity]);
    marks.forEach(ml => {
      const y = y0 + bh - 8 - ml / this.capacity * (bh - 22);
      ctx.strokeStyle = "rgba(95,122,143,0.8)"; ctx.lineWidth = 2; ctx.beginPath(); ctx.moveTo(cx + 42, y); ctx.lineTo(cx + 60, y); ctx.stroke();
      ctx.fillStyle = "rgba(95,122,143,0.9)"; ctx.fillText(ml === this.capacity ? "MAX" : (ml / 1000).toFixed(1), cx + 38, y);
    });
    // крышка и пар
    ctx.fillStyle = "#2f3640"; rr(ctx, cx - 62, y0 - 16, 124, 18, 8); ctx.fill(); rr(ctx, cx - 15, y0 - 28, 30, 14, 6); ctx.fill();
    this.steam.forEach(p => { ctx.fillStyle = `rgba(201,214,223,${Math.max(0, p[3]) / 255})`; ctx.beginPath(); ctx.ellipse(p[0], p[1], p[2], p[2] * 0.8, 0, 0, Math.PI * 2); ctx.fill(); });
    // температура
    ctx.textAlign = "center"; ctx.font = "bold 40px -apple-system, sans-serif";
    const tt = Math.round(this.temp) + "°";
    ctx.fillStyle = "rgba(0,0,0,0.27)"; ctx.fillText(tt, cx - 13, y0 + 70);
    ctx.fillStyle = this.level < 0.55 ? "#12293c" : "#fff"; ctx.fillText(tt, cx - 15, y0 + 68);
    ctx.font = "bold 13px -apple-system, sans-serif";
    let cap = `цель ${s.target_temp}°`, col = "#5f7a8f";
    if ((s.water_ml || 0) < C.MIN_KETTLE_WATER_ML) { cap = "Налейте воду"; col = "#e5484d"; }
    else if (heating) { cap = `нагрев до ${s.target_temp}°`; col = "#e0662f"; }
    else if (keeping) { cap = "поддержание"; col = "#c98a00"; }
    ctx.fillStyle = col; ctx.fillText(cap, cx - 15, y0 + 102);
  }
}

// ---------- кондиционер ----------

class ClimateView extends CanvasView {
  constructor(parent, engine, d) { super(parent, 230); this.engine = engine; this.d = d; this.model = MODELS[d.model]; this.particles = []; this.phase = 0; }
  roomTemp() { return this.engine.roomTemps[this.d.roomId] ?? C.ROOM_TEMP; }
  kind() {
    const s = this.d.s, mode = s.mode || "Охлаждение";
    if (mode === "Вентиляция") return "air";
    if (mode === "Осушение") return "drop";
    if (mode === "Обогрев" || (mode === "Авто" && this.roomTemp() < (s.target_temp ?? 22))) return "heat";
    return "snow";
  }
  unit(w) { const uw = Math.min(440, w - 40); return [(w - uw) / 2, 16, uw, 78]; }
  step(k) {
    this.phase += 0.05 * k;
    const w = this.canvas.clientWidth, [ux, uy, uw, uh] = this.unit(w), s = this.d.s;
    if (this.d.on) {
      const fan = (s.fan_speed || 2) / (this.model.levels || 3);
      let rate = (0.6 + 2.2 * fan) * (this.d._active !== false ? 1 : 0.35) * k;
      while (rate > 0) {
        if (Math.random() < Math.min(1, rate)) {
          const x = ux + 30 + Math.random() * (uw - 60);
          this.particles.push({ x, y: uy + uh + 6, vx: (x - (ux + uw / 2)) * 0.004 + (Math.random() - 0.5) * 0.8, vy: 1 + 2.2 * fan + Math.random() * 0.8, life: 1, rot: Math.random() * 6, kind: this.kind() });
        }
        rate -= 1;
      }
    }
    this.particles.forEach(p => { p.x += p.vx * k; p.y += p.vy * k; p.vy *= 0.995; p.rot += 0.05 * k; p.life -= 0.012 * k; });
    this.particles = this.particles.filter(p => p.life > 0 && p.y < this.height + 10);
  }
  draw(ctx, w, h) {
    const temp = this.roomTemp(), t = (temp - 16) / 14, s = this.d.s, on = this.d.on;
    const g = ctx.createLinearGradient(0, 0, 0, h);
    g.addColorStop(0, rgbCss(lerpRgb([215, 233, 255], [255, 226, 207], t))); g.addColorStop(1, rgbCss(lerpRgb([238, 246, 255], [255, 243, 234], t)));
    ctx.fillStyle = g; rr(ctx, 0, 0, w, h, 16); ctx.fill();
    this.particles.forEach(p => {
      const a = 0.86 * p.life;
      if (p.kind === "snow") {
        ctx.save(); ctx.translate(p.x, p.y); ctx.rotate(p.rot); ctx.strokeStyle = `rgba(61,157,245,${a})`; ctx.lineWidth = 2;
        for (let i = 0; i < 3; i++) { ctx.beginPath(); ctx.moveTo(-6, 0); ctx.lineTo(6, 0); ctx.stroke(); ctx.rotate(Math.PI / 3); }
        ctx.restore();
      } else if (p.kind === "heat") {
        ctx.strokeStyle = `rgba(255,122,69,${a})`; ctx.lineWidth = 2.5; ctx.beginPath(); ctx.moveTo(p.x - 10, p.y);
        for (let i = 1; i < 6; i++) ctx.lineTo(p.x - 10 + i * 4, p.y + 3 * Math.sin(i * 1.4 + this.phase * 4));
        ctx.stroke();
      } else if (p.kind === "drop") {
        ctx.fillStyle = `rgba(61,157,245,${a})`; ctx.beginPath(); ctx.ellipse(p.x, p.y, 3, 4.5, 0, 0, Math.PI * 2); ctx.fill();
      } else {
        ctx.strokeStyle = `rgba(120,140,160,${a})`; ctx.lineWidth = 2; ctx.beginPath(); ctx.moveTo(p.x, p.y); ctx.lineTo(p.x - p.vx * 4, p.y - 10); ctx.stroke();
      }
    });
    const [ux, uy, uw, uh] = this.unit(w);
    ctx.fillStyle = "rgba(0,0,0,0.1)"; rr(ctx, ux, uy + 4, uw, uh, 20); ctx.fill();
    const bg = ctx.createLinearGradient(0, uy, 0, uy + uh); bg.addColorStop(0, "#fff"); bg.addColorStop(1, "#e8edf1");
    ctx.fillStyle = bg; ctx.strokeStyle = "#d3dce3"; ctx.lineWidth = 2; rr(ctx, ux, uy, uw, uh, 20); ctx.fill(); ctx.stroke();
    ctx.fillStyle = "#cfd8df"; rr(ctx, ux + 24, uy + uh - 18, uw - 48, 8, 4); ctx.fill();
    ctx.fillStyle = "#1b2430"; rr(ctx, ux + uw - 104, uy + 16, 80, 32, 8); ctx.fill();
    ctx.fillStyle = on ? "#5fd1ff" : "#3a4654"; ctx.font = "bold 18px -apple-system, sans-serif"; ctx.textAlign = "center"; ctx.textBaseline = "middle";
    ctx.fillText(on ? s.target_temp + "°C" : "--", ux + uw - 64, uy + 32);
    ctx.fillStyle = on ? "#00d27a" : "#9aa5b1"; circle(ctx, ux + 30, uy + 22, 4); ctx.fill();
    ctx.fillStyle = "#9aa5b1"; ctx.font = "11px -apple-system, sans-serif"; ctx.textAlign = "left"; ctx.fillText("inverter", ux + 40, uy + 22);
    const open = on ? 10 + 6 * Math.sin(this.phase * 1.2) : 2, fy = uy + uh - 6;
    ctx.fillStyle = "#f4f6f8"; ctx.strokeStyle = "#c5ced6"; ctx.lineWidth = 1.5;
    ctx.beginPath(); ctx.moveTo(ux + 26, fy); ctx.lineTo(ux + uw - 26, fy); ctx.lineTo(ux + uw - 34, fy + open); ctx.lineTo(ux + 34, fy + open); ctx.closePath(); ctx.fill(); ctx.stroke();
    drawTags(ctx, w, h, `🌡 В комнате ${temp.toFixed(1)}°C`, climateStatus(this.d, temp), "bottom");
  }
}

function drawTags(ctx, w, h, left, status, where) {
  ctx.font = "bold 13px -apple-system, sans-serif"; ctx.textBaseline = "middle"; ctx.textAlign = "center";
  const tw = Math.min(230, (w - 40) / 2);
  const y = where === "bottom" ? h - 36 : 14;
  ctx.fillStyle = "rgba(255,255,255,0.8)";
  rr(ctx, 12, y, tw, 26, 8); ctx.fill(); rr(ctx, w - 12 - tw, y, tw, 26, 8); ctx.fill();
  ctx.fillStyle = "#12293c"; ctx.fillText(left, 12 + tw / 2, y + 13, tw - 8);
  ctx.fillStyle = status[1]; ctx.fillText(status[0], w - 12 - tw / 2, y + 13, tw - 8);
}

// ---------- обогреватель ----------

class HeaterView extends CanvasView {
  constructor(parent, engine, d) { super(parent, 240); this.engine = engine; this.d = d; this.phase = 0; }
  roomTemp() { return this.engine.roomTemps[this.d.roomId] ?? C.ROOM_TEMP; }
  intensity() {
    if (!this.d.on) return 0;
    const base = this.d._active !== false ? modeFactor("heater", this.d.s.mode) : 0.3;
    return base * (0.9 + 0.1 * Math.sin(this.phase * 3));
  }
  step(k) { this.phase += 0.05 * k; }
  draw(ctx, w, h) {
    const temp = this.roomTemp(), t = (temp - 10) / 22, k = this.intensity();
    const g = ctx.createLinearGradient(0, 0, 0, h);
    g.addColorStop(0, rgbCss(lerpRgb([219, 232, 245], [255, 217, 194], t))); g.addColorStop(1, rgbCss(lerpRgb([241, 246, 251], [255, 241, 232], t)));
    ctx.fillStyle = g; rr(ctx, 0, 0, w, h, 16); ctx.fill();
    const hw = Math.min(320, w - 120), hx = (w - 90 - hw) / 2 + 10, hy = h - 120;
    if (k > 0) {
      for (let i = 0; i < 7; i++) {
        const x0 = hx + 30 + i * (hw - 60) / 6;
        const gr = ctx.createLinearGradient(0, hy, 0, hy - 150);
        gr.addColorStop(0, `rgba(255,110,50,${0.8 * k})`); gr.addColorStop(1, "rgba(255,110,50,0)");
        ctx.strokeStyle = gr; ctx.lineWidth = 3; ctx.lineCap = "round"; ctx.beginPath(); ctx.moveTo(x0, hy - 4);
        for (let st = 1; st < 26; st++) ctx.lineTo(x0 + 7 * Math.sin(st * 0.45 - this.phase * 4 + i), hy - 4 - st * 6);
        ctx.stroke();
      }
      const gl = ctx.createRadialGradient(hx + hw / 2, hy + 10, 0, hx + hw / 2, hy + 10, 220);
      gl.addColorStop(0, `rgba(255,120,60,${0.43 * k})`); gl.addColorStop(1, "rgba(255,120,60,0)");
      ctx.fillStyle = gl; ctx.beginPath(); ctx.ellipse(hx + hw / 2, hy + 10, 220, 90, 0, 0, Math.PI * 2); ctx.fill();
    }
    ctx.fillStyle = "#9aa5b1"; rr(ctx, hx + 30, hy + 96, 14, 20, 4); ctx.fill(); rr(ctx, hx + hw - 44, hy + 96, 14, 20, 4); ctx.fill();
    ctx.fillStyle = "#f5f6f8"; ctx.strokeStyle = "#d3dce3"; ctx.lineWidth = 2; rr(ctx, hx, hy, hw, 100, 16); ctx.fill(); ctx.stroke();
    ctx.fillStyle = "#3a4350"; rr(ctx, hx + 16, hy + 12, hw - 32, 30, 8); ctx.fill();
    ctx.fillStyle = rgbCss(lerpRgb([107, 118, 130], [255, 90, 31], k));
    for (let x = hx + 26; x < hx + hw - 26; x += 14) { rr(ctx, x, hy + 17, 7, 20, 3); ctx.fill(); }
    ctx.fillStyle = "#1b2430"; rr(ctx, hx + hw - 110, hy + 58, 90, 28, 7); ctx.fill();
    ctx.fillStyle = this.d.on ? "#ff9a5c" : "#3a4654"; ctx.font = "bold 15px -apple-system, sans-serif"; ctx.textAlign = "center"; ctx.textBaseline = "middle";
    ctx.fillText(this.d.on ? this.d.s.target_temp + "°C" : "--", hx + hw - 65, hy + 72);
    // термометр
    const tx = w - 60, ty = 24, th = h - 80, lvl = Math.max(0, Math.min(1, (temp - 10) / 22)), liq = rgbCss(lerpRgb([61, 157, 245], [255, 77, 26], lvl));
    ctx.fillStyle = "#fff"; ctx.strokeStyle = "#c5ced6"; ctx.lineWidth = 2; rr(ctx, tx - 3, ty - 3, 22, th + 6, 10); ctx.fill(); ctx.stroke();
    circle(ctx, tx + 8, ty + th + 12, 17); ctx.fill(); ctx.stroke();
    ctx.fillStyle = liq; circle(ctx, tx + 8, ty + th + 12, 12); ctx.fill(); rr(ctx, tx + 3, ty + th - th * lvl, 10, th * lvl + 6, 4); ctx.fill();
    ctx.fillStyle = "#5f7a8f"; ctx.font = "10px -apple-system, sans-serif"; ctx.textAlign = "right";
    [10, 15, 20, 25, 30].forEach(v => ctx.fillText(v, tx - 10, ty + th - th * (v - 10) / 22));
    drawTags(ctx, w - 70, h, `🌡 В комнате ${temp.toFixed(1)}°C`, climateStatus(this.d, temp), "top");
  }
}

// ---------- термостат ----------

class ThermostatDial {
  constructor(parent, lo, hi, value, info, onChange) {
    this.lo = lo; this.hi = hi; this.value = value; this.info = info; this.onChange = onChange;
    this.el = document.createElement("div");
    this.el.className = "dial-row";
    this.el.innerHTML = `<button class="round-btn" data-d="-1">−</button><svg class="dial" viewBox="0 0 250 250"></svg><button class="round-btn" data-d="1">+</button>`;
    parent.appendChild(this.el);
    this.svg = this.el.querySelector("svg");
    this.el.querySelectorAll(".round-btn").forEach(b => b.addEventListener("click", () => this.set(this.value + Number(b.dataset.d))));
    const move = e => {
      const r = this.svg.getBoundingClientRect(), x = (e.clientX - r.left) / r.width * 250 - 125, y = (e.clientY - r.top) / r.height * 250 - 125;
      let a = Math.atan2(-y, x) * 180 / Math.PI;
      if (a < -90) a += 360;
      let t = (225 - a) / 270;
      if (t < 0 || t > 1) t = Math.abs(t) < Math.abs(t - 1) ? 0 : 1;
      this.set(this.lo + t * (this.hi - this.lo));
    };
    this.svg.addEventListener("pointerdown", e => { this.svg.setPointerCapture(e.pointerId); this.drag = true; move(e); e.preventDefault(); });
    this.svg.addEventListener("pointermove", e => { if (this.drag) move(e); });
    this.svg.addEventListener("pointerup", () => { this.drag = false; });
    this.render();
  }
  set(v) {
    v = Math.round(Math.max(this.lo, Math.min(this.hi, v)));
    if (v !== this.value) { this.value = v; this.onChange(v); }
    this.render();
  }
  pt(value, r) {
    const a = (225 - 270 * (value - this.lo) / (this.hi - this.lo)) * Math.PI / 180;
    return [125 + r * Math.cos(a), 125 - r * Math.sin(a)];
  }
  arc(from, to, r) {
    const [x1, y1] = this.pt(from, r), [x2, y2] = this.pt(to, r);
    const large = (to - from) / (this.hi - this.lo) * 270 > 180 ? 1 : 0;
    return `M${x1},${y1} A${r},${r} 0 ${large} 1 ${x2},${y2}`;
  }
  render() {
    const [room, status, color] = this.info(), R = 92;
    let ticks = "";
    for (let v = this.lo; v <= this.hi; v++) {
      const [a1, b1] = this.pt(v, R - 16), [a2, b2] = this.pt(v, R - (v % 5 === 0 ? 24 : 20));
      ticks += `<line x1="${a1}" y1="${b1}" x2="${a2}" y2="${b2}" stroke="#b9c7d2" stroke-width="2"/>`;
    }
    const [kx, ky] = this.pt(this.value, R), rt = Math.max(this.lo, Math.min(this.hi, room)), [rx, ry] = this.pt(rt, R);
    const valueArc = this.value > this.lo ? `<path d="${this.arc(this.lo, this.value, R)}" stroke="${color}" stroke-width="14" fill="none" stroke-linecap="round"/>` : "";
    this.svg.innerHTML = `
      <defs><radialGradient id="face"><stop offset="0" stop-color="#fff"/><stop offset="1" stop-color="#eef3f7"/></radialGradient></defs>
      <circle cx="125" cy="129" r="113" fill="rgba(0,0,0,0.07)"/><circle cx="125" cy="125" r="113" fill="url(#face)"/>
      <path d="${this.arc(this.lo, this.hi, R)}" stroke="#e3edf4" stroke-width="14" fill="none" stroke-linecap="round"/>
      ${valueArc}${ticks}
      <circle cx="${rx}" cy="${ry}" r="4" fill="#12293c"/>
      <circle cx="${kx}" cy="${ky}" r="11" fill="#fff" stroke="${color}" stroke-width="4"/>
      <text x="125" y="72" text-anchor="middle" font-size="11" font-weight="700" fill="#8aa0b2">ЦЕЛЬ</text>
      <text x="125" y="120" text-anchor="middle" font-size="48" font-weight="700" fill="#12293c">${this.value}°</text>
      <text x="125" y="146" text-anchor="middle" font-size="13" fill="#5f7a8f">в комнате ${room.toFixed(1)}°</text>
      <text x="125" y="168" text-anchor="middle" font-size="12" font-weight="700" fill="${color}">${esc(status)}</text>`;
  }
}

// ---------- робот-пылесос ----------

class VacuumView extends CanvasView {
  constructor(parent, d) {
    super(parent, 300);
    this.d = d; this.rows = 9; this.phase = 0;
    this.prog = d.s.vac_progress || 0; this.ret = d.s.vac_return || 0;
    let seed = d.id * 9301 + 49297;
    const rnd = () => { seed = (seed * 9301 + 49297) % 233280; return seed / 233280; };
    this.dust = Array.from({ length: 320 }, () => [0.03 + rnd() * 0.94, 0.05 + rnd() * 0.9, 1 + rnd() * 1.6]);
    this.path = [];
    for (let i = 0; i < this.rows; i++) {
      const y = 0.9 - i * 0.8 / (this.rows - 1), xs = i % 2 === 0 ? [0.08, 0.92] : [0.92, 0.08];
      this.path.push([xs[0], y], [xs[1], y]);
    }
    this.dock = [0.04, 0.97];
  }
  map(w, h) { return [12, 44, w - 24, h - 56]; }
  px(p, w, h) { const [mx, my, mw, mh] = this.map(w, h); return [mx + p[0] * mw, my + p[1] * mh]; }
  posAt(progress, w, h) {
    const pts = this.path.map(p => this.px(p, w, h)), len = [0];
    for (let i = 1; i < pts.length; i++) len.push(len[i - 1] + Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]));
    const target = Math.max(0, Math.min(1, progress)) * len[len.length - 1];
    for (let i = 1; i < pts.length; i++) {
      if (len[i] >= target) {
        const k = (target - len[i - 1]) / ((len[i] - len[i - 1]) || 1), a = pts[i - 1], b = pts[i];
        return { x: a[0] + (b[0] - a[0]) * k, y: a[1] + (b[1] - a[1]) * k, ang: Math.atan2(b[1] - a[1], b[0] - a[0]), idx: i, pts };
      }
    }
    const l = pts[pts.length - 1];
    return { x: l[0], y: l[1], ang: 0, idx: pts.length - 1, pts };
  }
  step(k) {
    const s = this.d.s;
    this.prog += ((s.vac_progress || 0) - this.prog) * 0.08 * k;
    this.ret += ((s.vac_return || 0) - this.ret) * 0.08 * k;
    this.phase += 0.35 * k;
  }
  draw(ctx, w, h) {
    const s = this.d.s, st = s.vac_state || "docked", [mx, my, mw, mh] = this.map(w, h);
    ctx.fillStyle = "#fff"; rr(ctx, 0, 0, w, h, 16); ctx.fill();
    ctx.fillStyle = "#e6dccb"; ctx.strokeStyle = "#5d6670"; ctx.lineWidth = 5; rr(ctx, mx, my, mw, mh, 10); ctx.fill(); ctx.stroke();
    ctx.fillStyle = "#d9c7b0"; ctx.beginPath(); ctx.ellipse(mx + mw / 2, my + mh / 2, mw * 0.18, mh * 0.18, 0, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = "rgba(110,90,70,0.6)"; this.dust.forEach(([x, y, r]) => { circle(ctx, mx + x * mw, my + y * mh, r); ctx.fill(); });
    const progress = st !== "docked" || (s.vac_progress || 0) > 0 ? this.prog : 0;
    if (progress > 0.001) {
      const pos = this.posAt(progress, w, h), rowPx = mh * 0.8 / (this.rows - 1);
      ctx.beginPath(); ctx.moveTo(pos.pts[0][0], pos.pts[0][1]);
      for (let i = 1; i < pos.idx; i++) ctx.lineTo(pos.pts[i][0], pos.pts[i][1]);
      ctx.lineTo(pos.x, pos.y);
      ctx.strokeStyle = "#f8f4ec"; ctx.lineWidth = rowPx + 3; ctx.lineCap = "round"; ctx.lineJoin = "round"; ctx.stroke();
      ctx.strokeStyle = "rgba(0,0,0,0.05)"; ctx.lineWidth = 2; ctx.stroke();
    }
    const [dx, dy] = this.px(this.dock, w, h);
    ctx.fillStyle = "#2f3640"; rr(ctx, dx - 16, dy - 8, 32, 14, 4); ctx.fill();
    ctx.fillStyle = "#00d27a"; circle(ctx, dx, dy - 1, 3); ctx.fill();
    let rx, ry, ang;
    if (st === "cleaning" || st === "paused") { const p = this.posAt(this.prog, w, h); rx = p.x; ry = p.y; ang = p.ang; }
    else if (st === "returning") {
      const p = this.posAt(s.vac_progress || 0, w, h);
      rx = p.x + (dx - p.x) * this.ret; ry = p.y + (dy - 22 - p.y) * this.ret; ang = Math.atan2(dy - p.y, dx - p.x);
      ctx.setLineDash([6, 5]); ctx.strokeStyle = "rgba(0,168,90,0.6)"; ctx.lineWidth = 2; ctx.beginPath(); ctx.moveTo(rx, ry); ctx.lineTo(dx, dy - 20); ctx.stroke(); ctx.setLineDash([]);
    } else { rx = dx; ry = dy - 22; ang = -Math.PI / 2; }
    ctx.save(); ctx.translate(rx, ry); ctx.rotate(ang);
    if (st === "cleaning") {
      ctx.strokeStyle = "#5d6670"; ctx.lineWidth = 1.5;
      for (let i = 0; i < 3; i++) { const a = this.phase * 0.7 + i * 2.09; ctx.beginPath(); ctx.moveTo(10, 10); ctx.lineTo(10 + 7 * Math.cos(a), 10 + 7 * Math.sin(a)); ctx.stroke(); }
    }
    ctx.fillStyle = "#fff"; ctx.strokeStyle = "#2f3640"; ctx.lineWidth = 2; circle(ctx, 0, 0, 14); ctx.fill(); ctx.stroke();
    ctx.fillStyle = "#2f3640"; circle(ctx, -2, 0, 5); ctx.fill();
    ctx.strokeStyle = st === "cleaning" ? "#00b96b" : "#9aa5b1"; ctx.lineWidth = 3; ctx.beginPath(); ctx.arc(0, 0, 14, -0.87, 0.87); ctx.stroke();
    ctx.restore();
    const status = { cleaning: `🧹 Уборка · ${Math.round((s.vac_progress || 0) * 100)}% · ≈${Math.round((s.vac_progress || 0) * 18)} м²`,
                     paused: `⏸ Пауза · ${Math.round((s.vac_progress || 0) * 100)}%`, returning: "↩️ Возвращается на базу",
                     docked: "🏠 На базе" + ((s.vac_battery ?? 100) < 99.5 ? " · заряжается ⚡" : "") }[st];
    ctx.fillStyle = "#12293c"; ctx.font = "bold 13px -apple-system, sans-serif"; ctx.textAlign = "left"; ctx.textBaseline = "middle";
    ctx.fillText(status, 16, 22, w - 170);
    const bat = s.vac_battery ?? 100, bx = w - 150;
    ctx.strokeStyle = "#9fb3c3"; ctx.lineWidth = 2; rr(ctx, bx, 15, 100, 14, 4); ctx.stroke();
    ctx.fillStyle = bat > 40 ? "#00b96b" : bat > 15 ? "#f5a623" : "#e5484d"; rr(ctx, bx + 2, 17, 96 * bat / 100, 10, 3); ctx.fill();
    ctx.fillStyle = "#12293c"; ctx.fillText(Math.round(bat) + "%", bx + 106, 22);
  }
}

// ---------- стиральная машина ----------

class WasherView extends CanvasView {
  constructor(parent, d) { super(parent, 320); this.d = d; this.rot = 0; this.n = 0; }
  phase() { return this.d.on ? washerPhase(washerFraction(this.d.s)) : null; }
  step(k) {
    this.n += k;
    const ph = this.phase(), dir = Math.sin(this.n / 45) >= 0 ? 1 : -1;
    const speed = { null: 0, "Нагрев воды": 0.03 * dir, "Стирка": 0.09 * dir, "Полоскание": 0.11 * dir, "Отжим": 0.55 }[ph] || 0;
    this.rot += speed * k;
  }
  draw(ctx, w, h) {
    const s = this.d.s, ph = this.phase();
    const frac = this.d.on ? washerFraction(s) : (s.wash_done ? 1 : 0);
    ctx.fillStyle = "#fff"; rr(ctx, 0, 0, w, h, 16); ctx.fill();
    const narrow = w < 470, bw = 230, bx = (narrow ? (w - bw) / 2 : 20) + (ph === "Отжим" ? Math.random() * 3 - 1.5 : 0), by = 14 + (ph === "Отжим" ? Math.random() * 2.4 - 1.2 : 0), bh = narrow ? 260 : 290;
    ctx.fillStyle = "rgba(0,0,0,0.08)"; rr(ctx, bx, by + 5, bw, bh, 20); ctx.fill();
    ctx.fillStyle = "#f7f8fa"; ctx.strokeStyle = "#d3dce3"; ctx.lineWidth = 2; rr(ctx, bx, by, bw, bh, 20); ctx.fill(); ctx.stroke();
    ctx.strokeStyle = "#e1e7ec"; ctx.beginPath(); ctx.moveTo(bx, by + 52); ctx.lineTo(bx + bw, by + 52); ctx.stroke();
    ctx.fillStyle = "#1b2430"; rr(ctx, bx + 16, by + 12, 92, 28, 6); ctx.fill();
    const left = washerTotal(s) * (1 - washerFraction(s));
    ctx.fillStyle = ph ? "#5fe3a1" : "#3a4654"; ctx.font = "bold 17px -apple-system, sans-serif"; ctx.textAlign = "center"; ctx.textBaseline = "middle";
    ctx.fillText(ph ? `${Math.floor(left / 60)}:${String(Math.floor(left % 60)).padStart(2, "0")}` : (s.wash_done ? "End" : "--:--"), bx + 62, by + 26);
    ctx.fillStyle = "#eef2f5"; ctx.strokeStyle = "#c5ced6"; circle(ctx, bx + bw - 32, by + 26, 14); ctx.fill(); ctx.stroke();
    const cx = bx + bw / 2, cy = by + 52 + (bh - 52) / 2, R = narrow ? 82 : 92;
    ctx.fillStyle = "#c9d1d8"; circle(ctx, cx, cy, R); ctx.fill();
    ctx.fillStyle = "#e9eef2"; circle(ctx, cx, cy, R - 10); ctx.fill();
    const gr = R - 22;
    ctx.save(); circle(ctx, cx, cy, gr); ctx.clip();
    const glass = ctx.createRadialGradient(cx, cy, 0, cx, cy, gr); glass.addColorStop(0, "#4b5b6b"); glass.addColorStop(1, "#26313c");
    ctx.fillStyle = glass; ctx.fillRect(cx - gr, cy - gr, gr * 2, gr * 2);
    ctx.fillStyle = "rgba(255,255,255,0.1)";
    [gr * 0.55, gr * 0.82].forEach(ring => { for (let i = 0; i < 14; i++) { const a = this.rot + i * Math.PI * 2 / 14; circle(ctx, cx + ring * Math.cos(a), cy + ring * Math.sin(a), 3); ctx.fill(); } });
    if (["Нагрев воды", "Стирка", "Полоскание"].includes(ph)) {
      const level = cy + (ph === "Полоскание" ? 28 : 20);
      ctx.beginPath(); ctx.moveTo(cx - gr, cy + gr);
      for (let x = cx - gr; x <= cx + gr; x += 4) ctx.lineTo(x, level + 4 * Math.sin(x / 12 + this.rot * 3));
      ctx.lineTo(cx + gr, cy + gr); ctx.closePath();
      const water = ph === "Нагрев воды" ? mixColor([95, 168, 211], [242, 166, 90], washerFraction(s) / 0.2) : [95, 168, 211];
      ctx.fillStyle = rgbCss(water, 0.67); ctx.fill();
      if (ph === "Стирка") {
        ctx.fillStyle = "rgba(255,255,255,0.8)";
        for (let i = 0; i < 12; i++) { circle(ctx, cx - gr * 0.8 + ((i * 37 + this.n * 2) % (gr * 1.6)), level - 2 + 3 * Math.sin(i + this.n / 6), 4 + i % 3); ctx.fill(); }
      }
    }
    ["#e07a5f", "#3d405b", "#81b29a", "#f2cc8f", "#5fa8d3"].forEach((col, i) => {
      const off = i * Math.PI * 2 / 5;
      let a, r;
      if (ph === "Отжим") { r = gr * 0.78; a = this.rot + off; }
      else if (ph) { a = this.rot * 1.3 + off; r = gr * 0.35 + gr * 0.35 * Math.abs(Math.sin(this.rot * 0.8 + off * 1.7)); }
      else { a = Math.PI / 2 + (i - 2) * 0.35; r = gr * 0.7; }
      ctx.save(); ctx.translate(cx + r * Math.cos(a), cy + r * Math.sin(a)); ctx.rotate(a + Math.PI / 2);
      ctx.fillStyle = col; rr(ctx, -16, -9, 32, 18, 8); ctx.fill(); ctx.restore();
    });
    ctx.restore();
    ctx.strokeStyle = "rgba(255,255,255,0.35)"; ctx.lineWidth = 6; ctx.lineCap = "round"; ctx.beginPath(); ctx.arc(cx, cy, gr - 14, Math.PI * 1.15, Math.PI * 1.45); ctx.stroke();
    // этапы
    const steps = D.washPhases.map(x => x[1]).concat(["Готово"]);
    const cur = ph ? steps.indexOf(ph) : (s.wash_done ? steps.length - 1 : -1);
    if (narrow) {
      const y = h - 34, sw = (w - 24) / steps.length;
      steps.forEach((name, i) => {
        const done = i < cur || (s.wash_done && !ph), act = i === cur && ph;
        ctx.fillStyle = done ? "#00b96b" : act ? "#2f8de4" : "#dfe8ef"; rr(ctx, 12 + i * sw + 2, y, sw - 4, 6, 3); ctx.fill();
        ctx.fillStyle = act || done ? "#12293c" : "#8aa0b2"; ctx.font = (act ? "bold " : "") + "10px -apple-system, sans-serif"; ctx.textAlign = "center";
        ctx.fillText(name, 12 + i * sw + sw / 2, y + 18, sw - 4);
      });
    } else {
      const x0 = bx + bw + 30;
      ctx.textAlign = "left"; ctx.fillStyle = "#12293c"; ctx.font = "bold 16px -apple-system, sans-serif"; ctx.fillText(s.mode || "", x0, 30);
      ctx.fillStyle = "#5f7a8f"; ctx.font = "13px -apple-system, sans-serif";
      ctx.fillText(`Длительность ${Math.floor(washerTotal(s) / 60)}:${String(washerTotal(s) % 60).padStart(2, "0")} ч`, x0, 52);
      steps.forEach((name, i) => {
        const y = 92 + i * 38, done = i < cur || (s.wash_done && !ph), act = i === cur && ph;
        ctx.fillStyle = done ? "#00b96b" : act ? "#2f8de4" : "#dfe8ef"; circle(ctx, x0 + 12, y, 12); ctx.fill();
        ctx.fillStyle = "#fff"; ctx.font = "bold 12px -apple-system, sans-serif"; ctx.textAlign = "center"; ctx.fillText(done ? "✓" : String(i + 1), x0 + 12, y + 1);
        ctx.textAlign = "left"; ctx.fillStyle = act || done ? "#12293c" : "#8aa0b2"; ctx.font = (act ? "bold " : "") + "14px -apple-system, sans-serif"; ctx.fillText(name, x0 + 34, y);
      });
      ctx.fillStyle = "#e3edf4"; rr(ctx, x0, 290, w - x0 - 20, 10, 5); ctx.fill();
      ctx.fillStyle = "#00b96b"; rr(ctx, x0, 290, (w - x0 - 20) * frac, 10, 5); ctx.fill();
    }
  }
}

// ---------- камера ----------

const sceneCache = {};
function sceneImage(kind, variant) {
  const key = kind + "_" + variant;
  if (!sceneCache[key]) { const img = new Image(); img.src = `img/scenes/${key}.jpg`; sceneCache[key] = img; }
  return sceneCache[key];
}

class CameraView extends CanvasView {
  constructor(parent, engine, d) {
    super(parent, 0);
    this.engine = engine; this.d = d; this.model = MODELS[d.model];
    this.ptz = !!this.model.ptz; this.pan = 0.5; this.panTarget = 0.5; this.person = null; this.n = 0;
    this.canvas.style.height = "auto"; this.canvas.style.aspectRatio = "16 / 9";
  }
  kind() { return sceneKind(this.engine.roomName(this.d.roomId), this.model); }
  panBy(v) { this.panTarget = Math.max(0, Math.min(1, this.panTarget + v)); }
  prepare() { this.height = this.canvas.clientWidth * 9 / 16; return super.prepare(); }
  step(k) {
    this.n += k;
    this.pan += (this.panTarget - this.pan) * 0.12 * k;
    if (!this.person) {
      if (this.d.on && Math.random() < 0.006 * k) {
        const dir = Math.random() < 0.5 ? -1 : 1;
        this.person = { x: dir > 0 ? -0.1 : 1.1, dir, speed: 0.003 + Math.random() * 0.002, phase: 0,
                        color: ["#3d6fb6", "#b5523b", "#4f9a6a", "#7b5ea7", "#333d4a"][Math.floor(Math.random() * 5)] };
      }
    } else {
      this.person.x += this.person.dir * this.person.speed * k;
      this.person.phase += 0.32 * k;
      if (this.person.x < -0.15 || this.person.x > 1.15) this.person = null;
    }
  }
  draw(ctx, w, h) {
    const s = this.d.s;
    ctx.save(); rr(ctx, 0, 0, w, h, 14); ctx.clip();
    if (!this.d.on) {
      ctx.fillStyle = "#0d1117"; ctx.fillRect(0, 0, w, h);
      ctx.fillStyle = "#6b7785"; ctx.font = "16px -apple-system, sans-serif"; ctx.textAlign = "center"; ctx.textBaseline = "middle";
      ctx.fillText("📷  Камера выключена", w / 2, h / 2); ctx.restore(); return;
    }
    const st = this.engine.state || { simMinutes: 720 }, hour = (st.simMinutes / 60) % 24, night = !(hour >= 6.5 && hour < 19.5);
    const lights = this.engine.devices.some(x => x.on && x.roomId === this.d.roomId && TYPES[x.type].group === LIGHT_GROUP);
    const kind = this.kind(), outdoor = kind === "terrace" || kind === "porch", lit = lights && !outdoor, ir = night && !lit && s.night_vision;
    const variant = !night ? "day" : ir ? "ir" : "night", img = sceneImage(kind, variant);
    // панорама 1600x600, кадр - 2/3 ширины; поворотные камеры двигают кадр
    const viewFrac = 2 / 3, sx = (this.ptz ? this.pan : 0.5) * (1 - viewFrac);
    if (img.complete && img.naturalWidth) ctx.drawImage(img, sx * img.naturalWidth, 0, img.naturalWidth * viewFrac, img.naturalHeight, 0, 0, w, h);
    else { ctx.fillStyle = "#1b2430"; ctx.fillRect(0, 0, w, h); }
    if (this.person) {
      const px = (this.person.x - sx) / viewFrac * w, porch = kind === "porch";
      const foot = h * (porch ? 0.86 : 0.95), ph = h * (porch ? 0.42 : 0.62);
      drawPerson(ctx, px, foot, ph, this.person.phase, ir ? "#9a9a9a" : this.person.color);
      if (s.motion_alerts !== false && px > -40 && px < w + 40) {
        ctx.strokeStyle = "#00e676"; ctx.lineWidth = 2; ctx.strokeRect(px - ph * 0.22, foot - ph * 1.12, ph * 0.44, ph * 1.14);
        ctx.fillStyle = "#00a85a"; ctx.fillRect(px - ph * 0.22, foot - ph * 1.12 - 18, 112, 18);
        ctx.fillStyle = "#fff"; ctx.font = "bold 11px -apple-system, sans-serif"; ctx.textAlign = "left"; ctx.textBaseline = "middle";
        ctx.fillText(`Человек ${88 + Math.floor(this.n / 7) % 10}%`, px - ph * 0.22 + 6, foot - ph * 1.12 - 9);
      }
    }
    if (night && !ir) { ctx.fillStyle = lit ? "rgba(255,170,70,0.12)" : "rgba(5,10,25,0.72)"; ctx.fillRect(0, 0, w, h); }
    if (ir) { ctx.fillStyle = "rgba(30,60,30,0.18)"; ctx.fillRect(0, 0, w, h); }
    for (let i = 0; i < (night ? 220 : 100); i++) { ctx.fillStyle = `rgba(255,255,255,${0.05 + Math.random() * 0.17})`; ctx.fillRect(Math.random() * w, Math.random() * h, 1, 1); }
    const vg = ctx.createRadialGradient(w / 2, h / 2, w * 0.38, w / 2, h / 2, w * 0.7);
    vg.addColorStop(0, "rgba(0,0,0,0)"); vg.addColorStop(1, "rgba(0,0,0,0.55)"); ctx.fillStyle = vg; ctx.fillRect(0, 0, w, h);
    ctx.font = "bold 11px -apple-system, sans-serif"; ctx.textBaseline = "middle";
    const tag = (text, x, y, right, bg) => {
      const tw = ctx.measureText(text).width + 14, xx = right ? x - tw : x;
      ctx.fillStyle = bg || "rgba(0,0,0,0.5)"; rr(ctx, xx, y, tw, 20, 6); ctx.fill();
      ctx.fillStyle = "#fff"; ctx.textAlign = "left"; ctx.fillText(text, xx + 7, y + 10);
      return tw;
    };
    tag(`${this.d.name} · ${this.engine.roomName(this.d.roomId)}`, 8, 8);
    const now = new Date();
    tag(`${String(now.getDate()).padStart(2, "0")}.${String(now.getMonth() + 1).padStart(2, "0")}.${now.getFullYear()} ${simTimeText(st.simMinutes)}:${String(now.getSeconds()).padStart(2, "0")}`, w - 8, 8, true);
    tag("LIVE · " + (this.model.resolution || "1080p"), 8, h - 28);
    let xr = w - 8;
    if (s.recording && Math.floor(this.n / 12) % 2 === 0) xr -= tag("● REC", xr, h - 28, true, "rgba(200,30,30,0.8)") + 6;
    if (ir) tag("IR · ночное видение", xr, h - 28, true);
    else if (night && lit) tag("💡 свет в комнате", xr, h - 28, true);
    else if (night) tag("ночь · ИК выключен", xr, h - 28, true);
    ctx.restore();
  }
  snapshot() {
    const a = document.createElement("a");
    a.download = `${this.d.name}_${Date.now()}.png`.replace(/\s+/g, "_");
    a.href = this.canvas.toDataURL("image/png");
    a.click();
  }
}

function drawPerson(ctx, x, foot, height, phase, color) {
  const s = height / 180, sw = Math.sin(phase) * 14 * s;
  ctx.lineCap = "round";
  ctx.strokeStyle = "#2b2f36"; ctx.lineWidth = 17 * s;
  ctx.beginPath(); ctx.moveTo(x, foot - 86 * s); ctx.lineTo(x + sw, foot); ctx.moveTo(x, foot - 86 * s); ctx.lineTo(x - sw, foot); ctx.stroke();
  ctx.strokeStyle = color; ctx.lineWidth = 13 * s;
  ctx.beginPath(); ctx.moveTo(x, foot - 140 * s); ctx.lineTo(x - sw * 0.9, foot - 82 * s); ctx.moveTo(x, foot - 140 * s); ctx.lineTo(x + sw * 0.9, foot - 82 * s); ctx.stroke();
  ctx.fillStyle = color; rr(ctx, x - 24 * s, foot - 152 * s, 48 * s, 74 * s, 16 * s); ctx.fill();
  ctx.fillStyle = "#e2b48c"; ctx.beginPath(); ctx.ellipse(x, foot - 170 * s, 17 * s, 18 * s, 0, 0, Math.PI * 2); ctx.fill();
  ctx.fillStyle = "#3b2a20"; ctx.beginPath(); ctx.arc(x, foot - 175 * s, 18 * s, Math.PI, 0); ctx.fill();
}

// ---------- график энергии ----------

class EnergyChart extends CanvasView {
  constructor(parent, engine) {
    super(parent, 260);
    this.engine = engine; this.hover = null;
    const pick = e => { const r = this.canvas.getBoundingClientRect(); this.hover = e.clientX - r.left; };
    this.canvas.addEventListener("pointermove", pick);
    this.canvas.addEventListener("pointerdown", pick);
    this.canvas.addEventListener("pointerleave", () => { this.hover = null; });
  }
  draw(ctx, w, h) {
    const L = 46, R = 38, T = w < 480 ? 46 : 34, B = 26, pw = w - L - R, ph = h - T - B;
    const hist = this.engine.history;
    const maxKw = Math.ceil(Math.max(C.SOLAR_PEAK_W / 1000, ...hist.map(x => x[2] / 1000)) * 1.1);
    const X = m => L + m / 1440 * pw, Yk = wt => T + ph - wt / 1000 / maxKw * ph, Yl = l => T + ph - l * ph;
    ctx.font = "10px -apple-system, sans-serif"; ctx.textBaseline = "middle";
    ctx.fillStyle = "#eef2f8"; ctx.fillRect(X(0), T, X(360) - X(0), ph); ctx.fillRect(X(1200), T, X(1440) - X(1200), ph);
    for (let i = 0; i <= 4; i++) {
      const y = T + ph - i * ph / 4;
      ctx.strokeStyle = "#e3edf4"; ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(L, y); ctx.lineTo(L + pw, y); ctx.stroke();
      ctx.fillStyle = "#8aa0b2"; ctx.textAlign = "right"; ctx.fillText((maxKw * i / 4).toFixed(1) + " кВт", L - 4, y);
      ctx.textAlign = "left"; ctx.fillText(i * 25 + "%", L + pw + 4, y);
    }
    ctx.textAlign = "center";
    for (let hr = 0; hr <= 24; hr += 6) ctx.fillText(String(hr).padStart(2, "0") + ":00", X(hr * 60), T + ph + 14);
    ctx.setLineDash([5, 4]); ctx.strokeStyle = "#e6b422"; ctx.lineWidth = 1.5; ctx.beginPath();
    for (let m = 0; m <= 1440; m += 10) { const hr = m / 60, wt = hr > 6 && hr < 20 ? C.SOLAR_PEAK_W * Math.sin(Math.PI * (hr - 6) / 14) : 0; m ? ctx.lineTo(X(m), Yk(wt)) : ctx.moveTo(X(m), Yk(wt)); }
    ctx.stroke(); ctx.setLineDash([]);
    if (hist.length >= 2) {
      ctx.beginPath(); ctx.moveTo(X(hist[0][0]), T + ph);
      hist.forEach(x => ctx.lineTo(X(x[0]), Yk(x[1])));
      ctx.lineTo(X(hist[hist.length - 1][0]), T + ph); ctx.closePath(); ctx.fillStyle = "rgba(245,179,1,0.35)"; ctx.fill();
      [[1, "#f5b301", 2, Yk], [2, "#2f8de4", 2, Yk], [3, "#00b96b", 2.5, Yl]].forEach(([i, col, lw, f]) => {
        ctx.beginPath(); hist.forEach((x, j) => (j ? ctx.lineTo(X(x[0]), f(x[i])) : ctx.moveTo(X(x[0]), f(x[i])))); ctx.strokeStyle = col; ctx.lineWidth = lw; ctx.stroke();
      });
    } else { ctx.fillStyle = "#8aa0b2"; ctx.font = "12px -apple-system, sans-serif"; ctx.fillText("График заполняется по ходу симуляции…", L + pw / 2, T + ph / 2); }
    if (this.engine.state) {
      const nx = X(this.engine.state.simMinutes % 1440);
      ctx.setLineDash([3, 3]); ctx.strokeStyle = "#12293c"; ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(nx, T); ctx.lineTo(nx, T + ph); ctx.stroke(); ctx.setLineDash([]);
      ctx.fillStyle = "#12293c"; ctx.font = "10px -apple-system, sans-serif"; ctx.textAlign = "right"; ctx.fillText("сейчас", nx - 4, T + 8);
    }
    // легенда: переносится на вторую строку, если не помещается (узкий экран телефона)
    let lx = 8, ly = 9; ctx.textAlign = "left"; ctx.font = "11px -apple-system, sans-serif";
    [["#f5b301", "Выработка"], ["#2f8de4", "Потребление"], ["#00b96b", "Заряд АКБ"], ["#e6b422", "Прогноз (ясно)"]].forEach(([col, cap], i) => {
      const itemW = 26 + ctx.measureText(cap).width;
      if (lx + itemW > w) { lx = 8; ly += 15; }
      ctx.strokeStyle = col; ctx.lineWidth = 3; ctx.setLineDash(i === 3 ? [4, 3] : []); ctx.beginPath(); ctx.moveTo(lx, ly); ctx.lineTo(lx + 16, ly); ctx.stroke(); ctx.setLineDash([]);
      ctx.fillStyle = "#3f5e75"; ctx.fillText(cap, lx + 20, ly); lx += itemW + 8;
    });
    if (this.hover !== null && hist.length) {
      const m = (this.hover - L) / pw * 1440;
      const near = hist.reduce((a, b) => (Math.abs(b[0] - m) < Math.abs(a[0] - m) ? b : a));
      if (Math.abs(near[0] - m) < 40) {
        const hx = X(near[0]);
        ctx.strokeStyle = "#9fb3c3"; ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(hx, T); ctx.lineTo(hx, T + ph); ctx.stroke();
        const lines = [simTimeText(near[0]), "☀️ " + formatPower(near[1]), "🏠 " + formatPower(near[2]), "🔋 " + Math.round(near[3] * 100) + "%"];
        if (near[4] > 1) lines.push("🔌 " + formatPower(near[4]));
        const bx = Math.min(hx + 8, w - 128), bh = lines.length * 16 + 10;
        ctx.fillStyle = "rgba(18,41,60,0.92)"; rr(ctx, bx, T + 4, 120, bh, 8); ctx.fill();
        ctx.fillStyle = "#fff"; ctx.font = "11px -apple-system, sans-serif";
        lines.forEach((ln, i) => ctx.fillText(ln, bx + 8, T + 14 + i * 16));
      }
    }
  }
}

// ---------- отчёт за период ----------

function kwhText(wh, digits) {
  return (wh / 1000).toFixed(digits ?? 1).replace(".", ",").replace(/\B(?=(\d{3})+(?!\d))/g, " ") + " кВт·ч";
}

// Столбики потребления: часть от солнца/АКБ (зелёная) и из сети (красная, платная) + линия выработки
class ReportChart extends CanvasView {
  constructor(parent) {
    super(parent, 270);
    this.buckets = []; this.hover = null;
    const pick = e => {
      const r = this.canvas.getBoundingClientRect(), L = 52, pw = r.width - L - 12;
      const i = Math.floor((e.clientX - r.left - L) / (pw / Math.max(1, this.buckets.length)));
      this.hover = i >= 0 && i < this.buckets.length ? i : null;
    };
    this.canvas.addEventListener("pointermove", pick);
    this.canvas.addEventListener("pointerdown", pick);
    this.canvas.addEventListener("pointerleave", () => { this.hover = null; });
  }
  setData(buckets) { this.buckets = buckets; this.hover = null; }
  draw(ctx, w, h) {
    const L = 52, R = 12, T = 44, B = 26, pw = w - L - R, ph = h - T - B;
    ctx.font = "11px -apple-system, sans-serif"; ctx.textBaseline = "middle";
    let lx = 4, ly = 9;
    [["#00b96b", "От солнца и АКБ", 0], ["#e5484d", "Из сети (платно)", 0], ["#f5b301", "Выработка", 1]].forEach(([col, cap, line]) => {
      const iw = 24 + ctx.measureText(cap).width;
      if (lx + iw > w) { lx = 4; ly += 16; }
      if (line) { ctx.strokeStyle = col; ctx.lineWidth = 3; ctx.beginPath(); ctx.moveTo(lx, ly); ctx.lineTo(lx + 16, ly); ctx.stroke(); }
      else { ctx.fillStyle = col; rr(ctx, lx, ly - 6, 14, 12, 3); ctx.fill(); }
      ctx.fillStyle = "#3f5e75"; ctx.textAlign = "left"; ctx.fillText(cap, lx + 20, ly); lx += iw + 10;
    });
    const b = this.buckets;
    if (!b.length) { ctx.fillStyle = "#8aa0b2"; ctx.textAlign = "center"; ctx.fillText("Нет данных за выбранный период", w / 2, T + ph / 2); return; }
    const top = Math.max(...b.map(x => Math.max(x.cons, x.gen))) * 1.12 || 1000;
    const Y = v => T + ph - v / top * ph;
    for (let i = 0; i <= 4; i++) {
      const v = top * i / 4, y = Y(v);
      ctx.strokeStyle = "#e3edf4"; ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(L, y); ctx.lineTo(L + pw, y); ctx.stroke();
      ctx.fillStyle = "#8aa0b2"; ctx.textAlign = "right"; ctx.fillText((v / 1000).toFixed(top >= 8000 ? 0 : 1) + " кВт·ч", L - 4, y);
    }
    const slot = pw / b.length, bw = Math.max(2, Math.min(28, slot * 0.68)), every = Math.max(1, Math.ceil(b.length / Math.max(1, pw / 46)));
    const pts = [];
    b.forEach((x, i) => {
      const cx = L + slot * (i + 0.5), grid = Math.min(x.imp, x.cons), solar = Math.max(0, x.cons - grid);
      const dim = this.hover !== null && this.hover !== i;
      ctx.fillStyle = `rgba(0,185,107,${dim ? 0.45 : 0.85})`; ctx.fillRect(cx - bw / 2, Y(solar), bw, T + ph - Y(solar));
      ctx.fillStyle = `rgba(229,72,77,${dim ? 0.5 : 0.9})`; ctx.fillRect(cx - bw / 2, Y(solar + grid), bw, Y(solar) - Y(solar + grid));
      pts.push([cx, Y(x.gen)]);
      if (i % every === 0) { ctx.fillStyle = "#8aa0b2"; ctx.textAlign = "center"; ctx.fillText(x.label, cx, T + ph + 14); }
    });
    ctx.strokeStyle = "#f5b301"; ctx.lineWidth = 2.5; ctx.beginPath();
    pts.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y))); ctx.stroke();
    if (b.length <= 40) { ctx.fillStyle = "#f5b301"; pts.forEach(([x, y]) => { circle(ctx, x, y, 3); ctx.fill(); }); }
    if (this.hover !== null) {
      const x = b[this.hover], cx = L + slot * (this.hover + 0.5);
      const lines = [x.title, "☀️ " + kwhText(x.gen), "🏠 " + kwhText(x.cons), "🔌 из сети " + kwhText(x.imp), "💳 " + formatMoney(x.cost)];
      const bx = Math.min(Math.max(4, cx - 80), w - 168), bh = lines.length * 16 + 10;
      ctx.fillStyle = "rgba(18,41,60,0.93)"; rr(ctx, bx, T + 2, 164, bh, 8); ctx.fill();
      ctx.fillStyle = "#fff"; ctx.textAlign = "left";
      lines.forEach((ln, i) => ctx.fillText(ln, bx + 8, T + 12 + i * 16));
    }
  }
}
