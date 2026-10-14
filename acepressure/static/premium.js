/* ============================================================================
   AcePressure Premium Interactions (v1.3.0)
   -----------------------------------------------------------------------------
   Pure vanilla JS, no deps. Hooks into existing public/admin/overlay flows
   without changing them: looks for signals (new .pending element, tip success
   state, etc.) and layers premium polish on top.

   Features:
     - Confetti burst on tip success (public page)
     - Confetti burst on OBS alert fire (overlay)
     - Smooth number counter animation for metrics (admin)
     - Subtle tilt/parallax on hero tip card hover (desktop only)
   ============================================================================ */
'use strict';

(function () {
    /* ---------- Confetti engine (tiny, dependency-free) ---------- */
    let confettiCanvas = null, confettiCtx = null, confettiParticles = [], confettiRAF = null;

    function ensureConfettiCanvas() {
        if (confettiCanvas) return confettiCanvas;
        confettiCanvas = document.createElement('canvas');
        confettiCanvas.id = 'ace-confetti';
        document.body.appendChild(confettiCanvas);
        confettiCtx = confettiCanvas.getContext('2d');
        resizeConfettiCanvas();
        window.addEventListener('resize', resizeConfettiCanvas);
        return confettiCanvas;
    }
    function resizeConfettiCanvas() {
        if (!confettiCanvas) return;
        const dpr = window.devicePixelRatio || 1;
        confettiCanvas.width = window.innerWidth * dpr;
        confettiCanvas.height = window.innerHeight * dpr;
        confettiCanvas.style.width = window.innerWidth + 'px';
        confettiCanvas.style.height = window.innerHeight + 'px';
        if (confettiCtx) confettiCtx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }
    const CONFETTI_PALETTE = ['#ff4660', '#ff8a3d', '#ffd166', '#7a5cff', '#4ad4a3', '#ffffff'];
    function spawnConfetti(count, originX, originY) {
        ensureConfettiCanvas();
        const centerX = originX || window.innerWidth / 2;
        const centerY = originY || window.innerHeight / 3;
        for (let i = 0; i < count; i++) {
            const angle = Math.random() * Math.PI * 2;
            const speed = 6 + Math.random() * 12;
            confettiParticles.push({
                x: centerX, y: centerY,
                vx: Math.cos(angle) * speed,
                vy: Math.sin(angle) * speed - 2,
                size: 4 + Math.random() * 6,
                color: CONFETTI_PALETTE[(Math.random() * CONFETTI_PALETTE.length) | 0],
                life: 90 + Math.random() * 60,
                rotation: Math.random() * Math.PI,
                spin: (Math.random() - 0.5) * 0.3,
                shape: Math.random() < 0.5 ? 'rect' : 'circle',
            });
        }
        if (!confettiRAF) tickConfetti();
    }
    function tickConfetti() {
        confettiRAF = requestAnimationFrame(tickConfetti);
        if (!confettiCtx) return;
        confettiCtx.clearRect(0, 0, window.innerWidth, window.innerHeight);
        for (let i = confettiParticles.length - 1; i >= 0; i--) {
            const p = confettiParticles[i];
            p.vy += 0.25;             // gravity
            p.vx *= 0.995;             // drag
            p.x += p.vx; p.y += p.vy;
            p.rotation += p.spin;
            p.life -= 1;
            if (p.life <= 0 || p.y > window.innerHeight + 20) {
                confettiParticles.splice(i, 1); continue;
            }
            confettiCtx.save();
            confettiCtx.globalAlpha = Math.min(1, p.life / 60);
            confettiCtx.translate(p.x, p.y);
            confettiCtx.rotate(p.rotation);
            confettiCtx.fillStyle = p.color;
            if (p.shape === 'rect') {
                confettiCtx.fillRect(-p.size / 2, -p.size / 2, p.size, p.size * 0.6);
            } else {
                confettiCtx.beginPath();
                confettiCtx.arc(0, 0, p.size / 2, 0, Math.PI * 2);
                confettiCtx.fill();
            }
            confettiCtx.restore();
        }
        if (confettiParticles.length === 0) {
            cancelAnimationFrame(confettiRAF);
            confettiRAF = null;
            confettiCtx.clearRect(0, 0, window.innerWidth, window.innerHeight);
        }
    }
    /* Expose globally for other scripts that want to trigger it */
    window.aceConfetti = spawnConfetti;

    /* ---------- Smooth number counters (admin metrics) ---------- */
    function animateCounter(el, to, duration) {
        const from = parseFloat((el.dataset.value || el.textContent.replace(/[^0-9.-]/g, '')) || 0);
        const parsed = parseFloat(to);
        if (Number.isNaN(parsed)) { el.textContent = to; return; }
        if (from === parsed) return;
        const start = performance.now();
        const dur = duration || 700;
        const originalText = el.textContent;
        const prefix = originalText.match(/^[^\d-]*/)[0] || '';
        const suffix = originalText.match(/[^\d.,]*$/)[0] || '';
        function tick(now) {
            const t = Math.min(1, (now - start) / dur);
            const eased = 1 - Math.pow(1 - t, 3);
            const current = from + (parsed - from) * eased;
            el.textContent = prefix + Math.round(current).toLocaleString('en-IN') + suffix;
            if (t < 1) requestAnimationFrame(tick);
            else el.dataset.value = parsed;
        }
        requestAnimationFrame(tick);
    }
    /* Observer: when a .metric b node has its text replaced, animate the change */
    function wireMetricCounters() {
        const observer = new MutationObserver(muts => {
            for (const m of muts) {
                if (m.type !== 'childList') continue;
                for (const node of m.addedNodes) {
                    if (node.nodeType === 3) {   // text node
                        const parent = m.target;
                        if (parent && parent.tagName === 'B' && parent.closest && parent.closest('.metric')) {
                            const newText = parent.textContent;
                            animateCounter(parent, newText);
                        }
                    }
                }
            }
        });
        observer.observe(document.body, { childList: true, subtree: true, characterData: true });
    }

    /* ---------- Hero card parallax (desktop only, respects reduced motion) ---------- */
    function wireHeroParallax() {
        if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
        if (window.innerWidth < 900) return;
        const card = document.querySelector('.tip-focused .tip-card');
        if (!card) return;
        card.style.transition = 'transform 0.3s cubic-bezier(0.2, 0.9, 0.3, 1.3)';
        card.addEventListener('mousemove', e => {
            const r = card.getBoundingClientRect();
            const px = (e.clientX - r.left) / r.width - 0.5;
            const py = (e.clientY - r.top) / r.height - 0.5;
            card.style.transform = `perspective(1200px) rotateX(${-py * 2}deg) rotateY(${px * 2}deg) translateZ(0)`;
        });
        card.addEventListener('mouseleave', () => {
            card.style.transform = 'perspective(1200px) rotateX(0) rotateY(0)';
        });
    }

    /* ---------- Public tip page: fire confetti when payment status flips to VERIFIED / MANUAL ---------- */
    function wireTipSuccess() {
        /* Watch the #payment panel for a success state. public.js re-renders #payment on polling. */
        const payment = document.getElementById('payment');
        if (!payment) return;
        let lastStatus = null;
        const observer = new MutationObserver(() => {
            // Only a rendered celebration means VERIFIED/MANUAL; text such as "notification received,
            // awaiting creator review" must never fire confetti.
            const nowStatus = payment.querySelector('.celebration') ? 'ok' : null;
            if (nowStatus === 'ok' && lastStatus !== 'ok') {
                // public.js fires the centre burst (window.aceConfetti(140)); add the side bursts.
                setTimeout(() => spawnConfetti(80, window.innerWidth * 0.25, window.innerHeight * 0.35), 200);
                setTimeout(() => spawnConfetti(80, window.innerWidth * 0.75, window.innerHeight * 0.35), 400);
            }
            lastStatus = nowStatus;
        });
        observer.observe(payment, { childList: true, subtree: true });
    }

    /* ---------- OBS overlay: fire confetti on new alert ---------- */
    function wireOverlayAlert() {
        if (!document.body || document.body.dataset.kind !== 'alert') return;
        const stage = document.getElementById('stage');
        if (!stage) return;
        const observer = new MutationObserver(muts => {
            for (const m of muts) {
                for (const node of m.addedNodes) {
                    if (node.nodeType === 1 && node.classList && !node.classList.contains('exit')) {
                        /* A new alert card appeared */
                        spawnConfetti(90);
                        break;
                    }
                }
            }
        });
        observer.observe(stage, { childList: true });
    }

    /* ---------- Boot ---------- */
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', boot);
    } else {
        boot();
    }
    function boot() {
        try { wireMetricCounters(); } catch (_) {}
        try { wireHeroParallax(); } catch (_) {}
        try { wireTipSuccess(); } catch (_) {}
        try { wireOverlayAlert(); } catch (_) {}
    }
})();
