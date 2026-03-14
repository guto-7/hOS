const DOWNLOADS = {
  mac: "#",
  windows: "#",
  linux: "#",
};

function detectPlatform() {
  const ua = navigator.userAgent.toLowerCase();
  const platform = navigator.platform.toLowerCase();

  if (platform.includes("mac") || ua.includes("mac")) return "mac";
  if (platform.includes("win") || ua.includes("windows")) return "windows";
  if (platform.includes("linux") || ua.includes("linux")) return "linux";
  return "mac";
}

function setupDownloadButton() {
  const detected = detectPlatform();
  const button = document.getElementById("download-btn");
  const items = document.querySelectorAll(".download-item");

  const labels = {
    mac: "Download for macOS",
    windows: "Download for Windows",
    linux: "Download for Linux",
  };

  if (button) {
    button.textContent = labels[detected];
    button.href = DOWNLOADS[detected];
  }

  items.forEach((item) => {
    const key = item.getAttribute("data-platform");
    if (key && DOWNLOADS[key]) {
      item.href = DOWNLOADS[key];
    }
  });
}

function setupScrollHint() {
  const hint = document.querySelector(".scroll-hint");
  if (!hint) return;

  const onScroll = () => {
    hint.style.opacity = window.scrollY > 40 ? "0" : "0.85";
    hint.style.pointerEvents = window.scrollY > 40 ? "none" : "auto";
  };

  window.addEventListener("scroll", onScroll, { passive: true });
  onScroll();
}

function startNetworkAnimation() {
  const canvas = document.getElementById("network-canvas");
  if (!canvas) return;

  const ctx = canvas.getContext("2d");
  if (!ctx) return;

  let width = 0;
  let height = 0;
  let animationFrameId = null;

  const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const isMobile = () => window.matchMedia("(max-width: 767px)").matches;

  const particles = [];
  const glowClouds = [];
  const strands = [];

  function resize() {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    width = window.innerWidth;
    height = window.innerHeight;

    canvas.width = Math.floor(width * dpr);
    canvas.height = Math.floor(height * dpr);
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;

    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  function random(min, max) {
    return Math.random() * (max - min) + min;
  }

  function vesselCenterX(t) {
    return width * 0.1 + t * width * 0.8;
  }

  function vesselCenterY(t) {
    return (
      height * 0.5 +
      Math.sin(t * Math.PI * 1.1 - 0.5) * height * 0.09 +
      Math.sin(t * Math.PI * 2.0 + 0.8) * height * 0.025
    );
  }

  function vesselRadius(t) {
    const base = isMobile() ? height * 0.09 : height * 0.11;
    return base + Math.sin(t * Math.PI * 1.2 + 0.4) * height * 0.01;
  }

  function getFlowPoint(t, lateral = 0) {
    const x = vesselCenterX(t);
    const y = vesselCenterY(t);

    const dx = width * 0.8;
    const dy =
      Math.cos(t * Math.PI * 1.1 - 0.5) * (Math.PI * 1.1) * height * 0.09 +
      Math.cos(t * Math.PI * 2.0 + 0.8) * (Math.PI * 2.0) * height * 0.025;

    const len = Math.hypot(dx, dy) || 1;
    const nx = -dy / len;
    const ny = dx / len;

    const radius = vesselRadius(t);

    return {
      x: x + nx * lateral * radius,
      y: y + ny * lateral * radius,
      angle: Math.atan2(dy, dx),
      radius,
    };
  }

  function createParticle() {
    return {
      t: random(-0.2, 1.2),
      lateral: random(-0.78, 0.78),
      speed: random(0.00005, 0.00012) * (isMobile() ? 0.85 : 1),
      size: random(2.2, 7.5) * (isMobile() ? 0.85 : 1),
      alpha: random(0.28, 0.9),
      blur: random(8, 18),
      elongation: random(1, 1.8),
      tint: Math.random() > 0.72 ? "warm" : "teal",
      phase: random(0, Math.PI * 2),
    };
  }

  function createGlowCloud() {
    return {
      t: random(0, 1),
      lateral: random(-0.35, 0.35),
      radius: random(60, 130) * (isMobile() ? 0.8 : 1),
      alpha: random(0.04, 0.1),
      tint: Math.random() > 0.5 ? "warm" : "teal",
    };
  }

  function createStrand(offset) {
    return {
      offset,
      alpha: random(0.05, 0.12),
      width: random(1, 2),
    };
  }

  function setupScene() {
    particles.length = 0;
    glowClouds.length = 0;
    strands.length = 0;

    const particleCount = isMobile() ? 34 : 62;
    const cloudCount = isMobile() ? 4 : 7;

    for (let i = 0; i < particleCount; i += 1) {
      particles.push(createParticle());
    }

    for (let i = 0; i < cloudCount; i += 1) {
      glowClouds.push(createGlowCloud());
    }

    strands.push(
      createStrand(-0.32),
      createStrand(-0.08),
      createStrand(0.16)
    );
  }

  function buildFlowPath(padding = 0) {
    const steps = 90;
    const top = [];
    const bottom = [];

    for (let i = 0; i <= steps; i += 1) {
      const t = i / steps;
      top.push(getFlowPoint(t, -(1 + padding)));
      bottom.push(getFlowPoint(t, 1 + padding));
    }

    ctx.beginPath();
    ctx.moveTo(top[0].x, top[0].y);

    for (let i = 1; i < top.length; i += 1) {
      ctx.lineTo(top[i].x, top[i].y);
    }

    for (let i = bottom.length - 1; i >= 0; i -= 1) {
      ctx.lineTo(bottom[i].x, bottom[i].y);
    }

    ctx.closePath();
  }

  function drawBackgroundGlow() {
    const g1 = ctx.createRadialGradient(
      width * 0.42, height * 0.42, 0,
      width * 0.42, height * 0.42, Math.max(width, height) * 0.55
    );
    g1.addColorStop(0, "rgba(120, 24, 36, 0.12)");
    g1.addColorStop(1, "rgba(0,0,0,0)");

    ctx.fillStyle = g1;
    ctx.fillRect(0, 0, width, height);

    const g2 = ctx.createRadialGradient(
      width * 0.58, height * 0.52, 0,
      width * 0.58, height * 0.52, Math.max(width, height) * 0.45
    );
    g2.addColorStop(0, "rgba(160, 40, 60, 0.08)");
    g2.addColorStop(1, "rgba(0,0,0,0)");

    ctx.fillStyle = g2;
    ctx.fillRect(0, 0, width, height);
  }

  function drawClouds() {
    for (const cloud of glowClouds) {
      const p = getFlowPoint(cloud.t, cloud.lateral);
      const color = `rgba(255, 120, 120, ${cloud.alpha})`;

      const gradient = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, cloud.radius);
      gradient.addColorStop(0, color);
      gradient.addColorStop(1, "rgba(0,0,0,0)");

      ctx.fillStyle = gradient;
      ctx.beginPath();
      ctx.arc(p.x, p.y, cloud.radius, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  function drawSoftTube() {
    ctx.save();
    buildFlowPath(-0.12);
    ctx.clip();

    const gradient = ctx.createLinearGradient(0, height * 0.3, width, height * 0.7);
    gradient.addColorStop(0, "rgba(255, 120, 110, 0.05)");
    gradient.addColorStop(0.45, "rgba(255, 220, 200, 0.08)");
    gradient.addColorStop(1, "rgba(255, 120, 110, 0.04)");

    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, width, height);

    ctx.restore();
  }

  function drawStrands(time) {
    ctx.save();
    buildFlowPath(-0.22);
    ctx.clip();

    for (const strand of strands) {
      ctx.beginPath();
      ctx.lineWidth = strand.width;
      ctx.strokeStyle = `rgba(255, 210, 190, ${strand.alpha})`;

      const steps = 70;
      for (let i = 0; i <= steps; i += 1) {
        const t = i / steps;
        const wave = Math.sin(time * 0.0008 + t * 8 + strand.offset * 6) * 0.045;
        const p = getFlowPoint(t, strand.offset + wave);

        if (i === 0) ctx.moveTo(p.x, p.y);
        else ctx.lineTo(p.x, p.y);
      }

      ctx.stroke();
    }

    ctx.restore();
  }

  function drawParticle(particle, time) {
    particle.t += particle.speed;
    if (particle.t > 1.2) {
      particle.t = -0.2;
      particle.lateral = random(-0.78, 0.78);
      particle.size = random(2.2, 7.5) * (isMobile() ? 0.85 : 1);
      particle.alpha = random(0.28, 0.9);
      particle.elongation = random(1, 1.8);
      particle.tint = Math.random() > 0.72 ? "warm" : "teal";
    }

    const wobble = Math.sin(time * 0.0014 + particle.phase) * 0.05;
    const p = getFlowPoint(particle.t, particle.lateral + wobble);

    const color = `rgba(255, 140, 110, ${particle.alpha})`;

    ctx.save();
    ctx.translate(p.x, p.y);
    ctx.rotate(p.angle);

    ctx.shadowBlur = particle.blur;
    ctx.shadowColor = "rgba(200, 60, 80, 0.45)";

    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.ellipse(
      0,
      0,
      particle.size * particle.elongation,
      particle.size,
      0,
      0,
      Math.PI * 2
    );
    ctx.fill();

    ctx.restore();
  }

  function drawCoreCluster(time) {
    const centerT = 0.43;
    const steps = 14;

    for (let i = 0; i < steps; i += 1) {
      const angle = time * 0.00035 + i * 0.45;
      const lateral = Math.sin(angle) * 0.18;
      const t = centerT + Math.cos(angle) * 0.035;
      const p = getFlowPoint(t, lateral);

      const r = 3 + (i % 3);
      const alpha = 0.18 + (i % 4) * 0.04;

      ctx.save();
      ctx.shadowBlur = 18;
      ctx.shadowColor = "rgba(255, 170, 90, 0.35)";
      ctx.fillStyle = `rgba(255, 185, 110, ${alpha})`;
      ctx.beginPath();
      ctx.arc(p.x, p.y, r * 2.1, 0, Math.PI * 2);
      ctx.fill();

      ctx.fillStyle = `rgba(255, 215, 140, ${alpha + 0.08})`;
      ctx.beginPath();
      ctx.arc(p.x, p.y, r, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();
    }
  }

  function frame(time = 0) {
    ctx.clearRect(0, 0, width, height);

    drawBackgroundGlow();
    drawClouds();
    drawSoftTube();

    ctx.save();
    buildFlowPath(-0.18);
    ctx.clip();

    drawStrands(time);

    for (const particle of particles) {
      drawParticle(particle, time);
    }

    drawCoreCluster(time);

    ctx.restore();

    if (!prefersReducedMotion) {
      animationFrameId = requestAnimationFrame(frame);
    }
  }

  function handleResize() {
    resize();
    setupScene();
  }

  resize();
  setupScene();
  frame();

  window.addEventListener("resize", handleResize);

  if (prefersReducedMotion && animationFrameId) {
    cancelAnimationFrame(animationFrameId);
  }
}

function setupFaqPanel() {
  const toggle = document.getElementById("faq-toggle");
  const panel = document.getElementById("faq-panel");
  const close = document.getElementById("faq-close");

  if (!toggle || !panel || !close) return;

  function openPanel() {
    panel.hidden = false;
    toggle.setAttribute("aria-expanded", "true");
  }

  function closePanel() {
    panel.hidden = true;
    toggle.setAttribute("aria-expanded", "false");
  }

  toggle.addEventListener("click", () => {
    if (panel.hidden) openPanel();
    else closePanel();
  });

  close.addEventListener("click", closePanel);

  document.addEventListener("click", (event) => {
    const target = event.target;
    if (!(target instanceof Node)) return;

    if (!panel.hidden && !panel.contains(target) && !toggle.contains(target)) {
      closePanel();
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closePanel();
  });
}

setupFaqPanel();
setupDownloadButton();
setupScrollHint();
startNetworkAnimation();