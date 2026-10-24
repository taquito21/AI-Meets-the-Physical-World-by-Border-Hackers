// Animated brand background: a drifting data network with pulses travelling along its links, slowly turning
// wireframe cubes (the cube in the FieldSight eye) and, on the login screen, a perspective floor and a scan line.
// Canvas 2D, time-based (same speed at any frame rate), paused while the tab is hidden, and a single still frame
// when the person asked the system for reduced motion.
import { useEffect, useRef } from "react";

type Variant = "login" | "app";

const TEAL = "57, 148, 150"; // #399496 (the "Sight" in the wordmark)
const LIGHT = "113, 201, 196"; // #71c9c4
const NAVY = "35, 63, 77"; // #233f4d

const SETTINGS: Record<Variant, {
  density: number; maxNodes: number; link: number; lineAlpha: number; nodeAlpha: number;
  pulseEvery: number; cubes: number; cubeAlpha: number; floor: boolean; scan: boolean; fps: number; dpr: number;
}> = {
  login: { density: 15000, maxNodes: 90, link: 150, lineAlpha: 0.32, nodeAlpha: 0.75, pulseEvery: 0.22, cubes: 3,
    cubeAlpha: 0.28, floor: true, scan: true, fps: 50, dpr: 2 },
  app: { density: 26000, maxNodes: 55, link: 130, lineAlpha: 0.16, nodeAlpha: 0.45, pulseEvery: 0.7, cubes: 2,
    cubeAlpha: 0.13, floor: false, scan: false, fps: 30, dpr: 1.5 },
};

interface Node { x: number; y: number; vx: number; vy: number; r: number; hub: boolean }
interface Pulse { a: number; b: number; t: number; speed: number }
interface Cube { x: number; y: number; size: number; vx: number; vy: number; ax: number; ay: number; wx: number; wy: number }

const CUBE_V = [-1, 1].flatMap((x) => [-1, 1].flatMap((y) => [-1, 1].map((z) => [x, y, z] as const)));
const CUBE_E: [number, number][] = [];
for (let i = 0; i < 8; i++) for (let j = i + 1; j < 8; j++) {
  const d = CUBE_V[i].reduce((s, v, k) => s + (v !== CUBE_V[j][k] ? 1 : 0), 0);
  if (d === 1) CUBE_E.push([i, j]);
}

export function TechBackground({ variant }: { variant: Variant }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;
    const cfg = SETTINGS[variant];
    const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const rand = (a: number, b: number) => a + Math.random() * (b - a);
    let w = 0, h = 0, raf = 0, last = performance.now(), sinceDraw = 0, sincePulse = 0, scanT = 0, floorT = 0;
    const nodes: Node[] = [];
    const pulses: Pulse[] = [];
    const cubes: Cube[] = [];

    const newNode = (): Node => {
      const speed = rand(6, 16); // px per second
      const dir = rand(0, Math.PI * 2);
      return { x: rand(0, w), y: rand(0, h), vx: Math.cos(dir) * speed, vy: Math.sin(dir) * speed,
        r: rand(1.1, 2.2), hub: Math.random() < 0.08 };
    };
    const newCube = (): Cube => ({ x: rand(0, w), y: rand(0, h), size: rand(26, w < 600 ? 46 : 70), vx: rand(-5, 5),
      vy: rand(-4, 4), ax: rand(0, 6), ay: rand(0, 6), wx: rand(0.08, 0.22), wy: rand(0.12, 0.3) });

    const resize = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, cfg.dpr);
      w = window.innerWidth;
      h = window.innerHeight;
      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(h * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      const want = Math.min(cfg.maxNodes, Math.round((w * h) / cfg.density));
      while (nodes.length < want) nodes.push(newNode());
      nodes.length = want;
      while (cubes.length < cfg.cubes) cubes.push(newCube());
      pulses.length = 0;
    };

    const drawFloor = () => {
      const horizon = h * 0.64;
      const depth = h - horizon;
      ctx.lineWidth = 1;
      for (let i = 0; i < 14; i++) { // horizontal lines rushing gently toward the viewer
        const p = ((i + floorT) % 14) / 14;
        const y = horizon + depth * p * p;
        ctx.strokeStyle = `rgba(${TEAL}, ${0.18 * p * p})`; // fades out toward the horizon
        ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke();
      }
      // Lines fanning out from the vanishing point, invisible at the horizon and stronger toward the viewer
      // (a gradient stroke, so nothing opaque is painted over the page background).
      const fan = ctx.createLinearGradient(0, horizon, 0, h);
      fan.addColorStop(0, `rgba(${TEAL}, 0)`);
      fan.addColorStop(1, `rgba(${TEAL}, 0.16)`);
      ctx.strokeStyle = fan;
      const vx = w / 2;
      ctx.beginPath();
      for (let i = -12; i <= 12; i++) { ctx.moveTo(vx, horizon); ctx.lineTo(vx + i * (w / 7), h); }
      ctx.stroke();
    };

    const drawCube = (c: Cube) => {
      const [cx, sx, cy, sy] = [Math.cos(c.ax), Math.sin(c.ax), Math.cos(c.ay), Math.sin(c.ay)];
      const pts = CUBE_V.map(([x, y, z]) => {
        const y1 = y * cx - z * sx, z1 = y * sx + z * cx; // rotate around X
        const x2 = x * cy + z1 * sy, z2 = -x * sy + z1 * cy; // then around Y
        const k = c.size / (2.6 + z2 * 0.35);
        return [c.x + x2 * k, c.y + y1 * k] as const;
      });
      ctx.strokeStyle = `rgba(${NAVY}, ${cfg.cubeAlpha})`;
      ctx.lineWidth = 1.2;
      ctx.beginPath();
      for (const [i, j] of CUBE_E) { ctx.moveTo(pts[i][0], pts[i][1]); ctx.lineTo(pts[j][0], pts[j][1]); }
      ctx.stroke();
      ctx.fillStyle = `rgba(${LIGHT}, ${cfg.cubeAlpha * 1.6})`;
      for (const [x, y] of pts) { ctx.beginPath(); ctx.arc(x, y, 1.6, 0, Math.PI * 2); ctx.fill(); }
    };

    const draw = () => {
      ctx.clearRect(0, 0, w, h);
      if (cfg.floor) drawFloor();
      if (cfg.scan) {
        const y = (scanT % 1) * (h + 160) - 80;
        const band = ctx.createLinearGradient(0, y - 80, 0, y + 80);
        band.addColorStop(0, `rgba(${LIGHT}, 0)`);
        band.addColorStop(0.5, `rgba(${LIGHT}, 0.10)`);
        band.addColorStop(1, `rgba(${LIGHT}, 0)`);
        ctx.fillStyle = band;
        ctx.fillRect(0, y - 80, w, 160);
      }
      const link2 = cfg.link * cfg.link;
      ctx.lineWidth = 1;
      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const dx = nodes[i].x - nodes[j].x, dy = nodes[i].y - nodes[j].y;
          const d2 = dx * dx + dy * dy;
          if (d2 > link2) continue;
          ctx.strokeStyle = `rgba(${TEAL}, ${cfg.lineAlpha * (1 - Math.sqrt(d2) / cfg.link)})`;
          ctx.beginPath(); ctx.moveTo(nodes[i].x, nodes[i].y); ctx.lineTo(nodes[j].x, nodes[j].y); ctx.stroke();
        }
      }
      for (const n of nodes) {
        ctx.fillStyle = `rgba(${n.hub ? TEAL : LIGHT}, ${cfg.nodeAlpha})`;
        ctx.beginPath(); ctx.arc(n.x, n.y, n.hub ? n.r + 1.2 : n.r, 0, Math.PI * 2); ctx.fill();
        if (n.hub) {
          ctx.strokeStyle = `rgba(${TEAL}, ${cfg.nodeAlpha * 0.45})`;
          ctx.beginPath(); ctx.arc(n.x, n.y, n.r + 5, 0, Math.PI * 2); ctx.stroke();
        }
      }
      for (const p of pulses) { // data travelling along a link, with a soft glow
        const a = nodes[p.a], b = nodes[p.b];
        if (!a || !b) continue;
        const x = a.x + (b.x - a.x) * p.t, y = a.y + (b.y - a.y) * p.t;
        const glow = ctx.createRadialGradient(x, y, 0, x, y, 9);
        glow.addColorStop(0, `rgba(${LIGHT}, 0.9)`);
        glow.addColorStop(1, `rgba(${LIGHT}, 0)`);
        ctx.fillStyle = glow;
        ctx.beginPath(); ctx.arc(x, y, 9, 0, Math.PI * 2); ctx.fill();
      }
      for (const c of cubes) drawCube(c);
    };

    const step = (dt: number) => {
      for (const n of nodes) {
        n.x += n.vx * dt; n.y += n.vy * dt;
        if (n.x < -20) n.x = w + 20; else if (n.x > w + 20) n.x = -20;
        if (n.y < -20) n.y = h + 20; else if (n.y > h + 20) n.y = -20;
      }
      for (const c of cubes) {
        c.x += c.vx * dt; c.y += c.vy * dt; c.ax += c.wx * dt; c.ay += c.wy * dt;
        if (c.x < -80) c.x = w + 80; else if (c.x > w + 80) c.x = -80;
        if (c.y < -80) c.y = h + 80; else if (c.y > h + 80) c.y = -80;
      }
      sincePulse += dt;
      if (sincePulse > cfg.pulseEvery && nodes.length > 1) {
        sincePulse = 0;
        const a = Math.floor(Math.random() * nodes.length);
        let best = -1, bestD = cfg.link * cfg.link;
        for (let j = 0; j < nodes.length; j++) {
          if (j === a) continue;
          const d = (nodes[a].x - nodes[j].x) ** 2 + (nodes[a].y - nodes[j].y) ** 2;
          if (d < bestD && Math.random() < 0.6) { best = j; bestD = d; }
        }
        if (best >= 0) pulses.push({ a, b: best, t: 0, speed: rand(0.6, 1.1) });
      }
      for (const p of pulses) p.t += p.speed * dt;
      for (let i = pulses.length - 1; i >= 0; i--) if (pulses[i].t >= 1) pulses.splice(i, 1);
      scanT += dt / 7.5;
      floorT += dt * 0.35;
    };

    const frame = (now: number) => {
      raf = requestAnimationFrame(frame);
      const dt = Math.min(0.1, (now - last) / 1000);
      last = now;
      step(dt);
      sinceDraw += dt;
      if (sinceDraw < 1 / cfg.fps) return; // cap the frame rate (battery on phones)
      sinceDraw = 0;
      draw();
    };
    const onVisibility = () => {
      cancelAnimationFrame(raf);
      if (!document.hidden && !still) { last = performance.now(); raf = requestAnimationFrame(frame); }
    };

    resize();
    if (still) draw();
    else raf = requestAnimationFrame(frame);
    const onResize = () => { resize(); if (still) draw(); };
    window.addEventListener("resize", onResize);
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", onResize);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [variant]);

  return (
    <div className={`tech-bg tech-bg-${variant}`} aria-hidden="true">
      <canvas ref={canvasRef} />
    </div>
  );
}
