"use client";

import gsap from "gsap";
import Lenis from "lenis";
import Image from "next/image";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { LiveSignal } from "@/components/react-bits/live-signal";
import {
  api,
  availabilityOf,
  countdown,
  formatPaise,
  formatRupees,
  soundLabel,
  voiceLabel,
  type Availability,
  type PublicConfig,
  type SoundboardItem,
  type Supporter,
  type TipFormValues,
  type TipPayment
} from "@/lib/acepressure";

const PRESETS = [20, 50, 100, 200, 500];

function genderClass(gender: string | undefined): string {
  return gender?.toLowerCase() === "male" || gender?.toLowerCase() === "female" ? gender.toLowerCase() : "any";
}

function statusText(status: Availability): string {
  return {
    open: "Tips open",
    demo: "Demo mode",
    paused: "Tips paused",
    setup: "Setup in progress"
  }[status];
}

function statusMessage(status: Availability, creator: string): string {
  if (status === "demo") return "No money moves in demo mode. The dashboard can simulate a confirmation.";
  if (status === "paused") return `${creator} is taking a breather from new tips. Your time here still counts.`;
  if (status === "setup") return "The payment rail is not live yet. The form will unlock when verification is ready.";
  return "Your exact amount is reserved for this request. Payment is confirmed by the existing AcePressure bridge.";
}

function Supporters({ supporters, loading }: { supporters: Supporter[]; loading: boolean }) {
  return (
    <section className="supporters-panel" data-reveal>
      <div className="supporters-heading">
        <h2>People who backed the stream</h2>
        <span>ALL TIME · TOP 3</span>
      </div>
      {loading ? (
        <div aria-label="Loading supporters" role="status">
          <div className="skeleton" />
          <div className="skeleton" />
          <div className="skeleton" />
        </div>
      ) : supporters.length ? (
        supporters.map((supporter, index) => (
          <div className="supporter-row" key={`${supporter.name}-${index}`}>
            <span className="supporter-rank">0{index + 1}</span>
            <span className="supporter-name">{supporter.name}</span>
            <span className="supporter-total">{formatPaise(supporter.total)}</span>
          </div>
        ))
      ) : (
        <p className="empty-state">Be the first name on the board. No pressure; hanging out is always enough.</p>
      )}
    </section>
  );
}

function VoiceChoices({
  config,
  selected,
  disabled,
  onChange
}: {
  config: PublicConfig;
  selected: string;
  disabled: boolean;
  onChange: (voice: string) => void;
}) {
  return (
    <div className="voice-grid" role="radiogroup" aria-label="Readout voice">
      {config.voices.map((voice) => {
        const gender = config.voice_genders?.[voice] ?? "Any";
        const isSelected = selected === voice;
        return (
          <button
            className={`voice-choice ${genderClass(gender)} ${isSelected ? "selected" : ""}`}
            disabled={disabled}
            key={voice}
            onClick={() => onChange(voice)}
            role="radio"
            aria-checked={isSelected}
            type="button"
          >
            <span className="voice-choice-name">{voiceLabel(config, voice)}</span>
            <span className="voice-choice-code">{voice}</span>
          </button>
        );
      })}
    </div>
  );
}

function SoundChoices({
  config,
  items,
  selected,
  amount,
  onChange,
  onNote
}: {
  config: PublicConfig;
  items: SoundboardItem[];
  selected: string;
  amount: number;
  onChange: (id: string) => void;
  onNote: (note: string) => void;
}) {
  const amountPaise = amount * 100;
  return (
    <div className="soundboard-box">
      <div className="soundboard-topline">
        <strong>Choose the alert sound</strong>
        <span>OPTIONAL · ONE CLIP</span>
      </div>
      <div className="soundboard-list" role="radiogroup" aria-label="Alert sound">
        <button
          className={`sound-choice ${selected ? "" : "selected"}`}
          onClick={() => onChange("")}
          role="radio"
          aria-checked={!selected}
          type="button"
        >
          <span className="sound-emoji">✦</span>
          <span className="sound-name">Streamer&apos;s default</span>
          <span className="sound-price">default</span>
        </button>
        {items.map((item) => {
          const locked = amountPaise < item.min_paise && selected !== item.id;
          const isSelected = selected === item.id;
          return (
            <button
              className={`sound-choice ${locked ? "locked" : ""} ${isSelected ? "selected" : ""}`}
              key={item.id}
              onClick={() => {
                if (locked) {
                  onNote(`“${item.name}” unlocks at ${formatPaise(item.min_paise)}. Raise the tip or keep the default.`);
                  return;
                }
                onNote("");
                onChange(isSelected ? "" : item.id);
              }}
              role="radio"
              aria-checked={isSelected}
              aria-disabled={locked}
              type="button"
            >
              <span className="sound-emoji">{item.emoji || "◉"}</span>
              <span className="sound-name">{item.name}</span>
              <span className="sound-price">{item.min_paise ? formatPaise(item.min_paise) : "any"}</span>
            </button>
          );
        })}
      </div>
      <p className="sound-note">
        {selected ? `Selected: ${items.find((item) => item.id === selected)?.name ?? "custom sound"}.` : `Your creator’s ${soundLabel(config, config.sounds?.[0] ?? "default")} will play.`}
      </p>
    </div>
  );
}

function SuccessPanel({ payment, onReset }: { payment: TipPayment; onReset: () => void }) {
  return (
    <section className="success-panel" aria-live="polite" data-reveal>
      <div className="success-mark" aria-hidden="true">✓</div>
      <p className="status-kicker">Payment confirmed · {formatPaise(payment.display_paise)}</p>
      <h2>That landed. Thank you, {payment.name}.</h2>
      <p>
        {payment.alert_queued
          ? "Your support is queued for the stream. Keep an eye out for the alert."
          : "AcePressure has the support in the ledger. The stream alert may be quiet if no session is active."}
      </p>
      <div className="receipt-row">
        <span>TIP ID</span>
        <strong>{payment.id}</strong>
      </div>
      <div className="payment-actions">
        <button className="cta" onClick={onReset} type="button">Send another tip</button>
      </div>
    </section>
  );
}

function PaymentPanel({
  payment,
  now,
  onRefresh,
  onReset,
  onCopy
}: {
  payment: TipPayment;
  now: number;
  onRefresh: () => void;
  onReset: () => void;
  onCopy: (value: string) => void;
}) {
  const confirmed = payment.status === "VERIFIED" || payment.status === "MANUAL";
  if (confirmed) return <SuccessPanel payment={payment} onReset={onReset} />;

  const closed = payment.status !== "PENDING";
  const qr = `/api/public/tips/${encodeURIComponent(payment.id)}/qr?token=${encodeURIComponent(payment.token)}`;
  const query = payment.upi_uri?.split("?")[1] ?? "";
  const appLinks = [
    ["Google Pay", `gpay://upi/pay?${query}`],
    ["PhonePe", `phonepe://pay?${query}`],
    ["Paytm", `paytmmp://upi/pay?${query}`]
  ];

  return (
    <section className="payment-panel" data-reveal>
      <p className="status-kicker">02 / 03 · Exact amount</p>
      <h2 className="payment-title">Pay <strong>{formatPaise(payment.requested_paise)}</strong>.</h2>
      <p className="payment-copy">
        The display amount is {formatPaise(payment.display_paise)}. The extra paise identifies this request; do not round it and do not pay twice.
      </p>
      {payment.demo ? (
        <div className="notice" role="status">DEMO PAYMENT · Open the private dashboard to simulate the confirmation.</div>
      ) : payment.upi_uri ? (
        <div className="payment-surface">
          <div className="qr-frame">
            <Image src={qr} alt="UPI QR with the exact requested amount" width={142} height={142} unoptimized />
          </div>
          <div>
            <p className="pay-amount-label">Send exactly</p>
            <p className="pay-amount">{formatPaise(payment.requested_paise)}</p>
            <div className="payment-detail"><span>Payee</span><strong>{payment.payee_name || "AcePressure"}</strong></div>
            <div className="payment-detail"><span>UPI ID</span><strong>{payment.upi_id || "Configured privately"}</strong></div>
            <div className="payment-links">
              <button className="copy-action" onClick={() => onCopy(payment.upi_id || "")} type="button">Copy UPI ID</button>
              <button className="copy-action" onClick={() => onCopy((payment.requested_paise / 100).toFixed(2))} type="button">Copy amount</button>
              <a href={qr} download="AcePressure-payment.png">Save QR</a>
            </div>
            <div className="payment-links" aria-label="Optional UPI apps">
              {appLinks.map(([name, href]) => <a href={href} key={name}>{name}</a>)}
            </div>
          </div>
        </div>
      ) : null}
      {closed ? (
        <div className="notice notice-error" role="alert">
          {payment.needs_review
            ? "A payment was seen and is waiting for creator review. Do not pay again."
            : "This payment window is closed. If you paid, keep the tip ID and contact the creator instead of paying again."}
        </div>
      ) : (
        <p className="payment-status"><span className="status-dot" aria-hidden="true" />Waiting for confirmation · expires in {countdown(payment.expires, now)}</p>
      )}
      <div className="receipt-row"><span>TIP ID</span><strong>{payment.id}</strong></div>
      <div className="payment-actions">
        {!closed && <button className="secondary-action" onClick={onRefresh} type="button">Check status</button>}
        <button className="back-action" onClick={onReset} type="button">Back to form</button>
      </div>
    </section>
  );
}

export function TipPage() {
  const rootRef = useRef<HTMLElement | null>(null);
  const [config, setConfig] = useState<PublicConfig | null>(null);
  const [supporters, setSupporters] = useState<Supporter[]>([]);
  const [sounds, setSounds] = useState<SoundboardItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [soundNote, setSoundNote] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [payment, setPayment] = useState<TipPayment | null>(null);
  const [now, setNow] = useState(() => Math.floor(Date.now() / 1000));
  const [copied, setCopied] = useState("");
  const [values, setValues] = useState<TipFormValues>({
    amount: "100",
    name: "",
    email: "",
    remember: false,
    message: "",
    tts: false,
    voice: "en-IN",
    soundboard_id: ""
  });

  const availability = availabilityOf(config);
  const amount = Math.floor(Number(values.amount) || 0);
  const tiers = useMemo(() => [...(config?.tiers ?? [1, 50, 200, 500])].sort((a, b) => a - b), [config?.tiers]);
  const tierIndex = tiers.reduce((current, tier) => (amount >= tier ? current + 1 : current), 0);
  const tierNames = ["Starter", "Supporter", "Big fan", "Legend", "Icon"];
  const tierIcons = ["✦", "★", "⚡", "♛", "✹"];
  const currentTier = tierNames[Math.min(tierIndex, tierNames.length - 1)];
  const currentIcon = tierIcons[Math.min(tierIndex, tierIcons.length - 1)];
  const canSubmit = Boolean(config && ["open", "demo"].includes(availability) && !submitting);

  const update = <K extends keyof TipFormValues>(key: K, value: TipFormValues[K]) => {
    setValues((previous) => ({ ...previous, [key]: value }));
  };

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      try {
        const [publicConfig, top] = await Promise.all([
          api<PublicConfig>("/api/public/config"),
          api<{ supporters: Supporter[] }>("/api/public/top")
        ]);
        if (cancelled) return;
        setConfig(publicConfig);
        setSupporters(top.supporters ?? []);
        setValues((previous) => ({
          ...previous,
          amount: String(Math.min(publicConfig.maximum, Math.max(100, publicConfig.minimum))),
          voice: publicConfig.voices[0] ?? previous.voice
        }));
        try {
          const soundboard = await api<{ items: SoundboardItem[] }>("/api/public/soundboard");
          if (!cancelled) setSounds(soundboard.items ?? []);
        } catch {
          if (!cancelled) setSounds([]);
        }
        const saved = window.sessionStorage.getItem("acepressure-next-tip");
        if (saved) {
          try {
            const savedPayment = JSON.parse(saved) as TipPayment;
            if (savedPayment?.id && savedPayment?.token) setPayment(savedPayment);
          } catch {
            window.sessionStorage.removeItem("acepressure-next-tip");
          }
        }
      } catch (loadError) {
        if (!cancelled) setError(loadError instanceof Error ? loadError.message : "Could not load the support page.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (loading || !rootRef.current || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const context = gsap.context(() => {
      gsap.fromTo("[data-reveal]", { opacity: 0, y: 16 }, { opacity: 1, y: 0, duration: 0.65, stagger: 0.06, ease: "power2.out" });
    }, rootRef.current);
    const lenis = new Lenis({ duration: 1.1, smoothWheel: true });
    let frame = 0;
    const raf = (time: number) => {
      lenis.raf(time);
      frame = window.requestAnimationFrame(raf);
    };
    frame = window.requestAnimationFrame(raf);
    return () => {
      context.revert();
      lenis.destroy();
      window.cancelAnimationFrame(frame);
    };
  }, [loading]);

  useEffect(() => {
    if (!payment || payment.status !== "PENDING") return;
    const interval = window.setInterval(() => setNow(Math.floor(Date.now() / 1000)), 1000);
    return () => window.clearInterval(interval);
  }, [payment]);

  const refreshPayment = useCallback(async () => {
    if (!payment) return;
    try {
      const latest = await api<TipPayment>(`/api/public/tips/${encodeURIComponent(payment.id)}`, {
        headers: { "X-Tip-Token": payment.token }
      });
      setPayment((previous) => (previous ? { ...previous, ...latest } : latest));
      setError("");
    } catch (pollError) {
      setError(pollError instanceof Error ? pollError.message : "Could not check this tip yet.");
    }
  }, [payment]);

  useEffect(() => {
    if (!payment || payment.status !== "PENDING") return;
    const interval = window.setInterval(() => void refreshPayment(), 20000);
    return () => window.clearInterval(interval);
  }, [payment, refreshPayment]);

  const reset = () => {
    window.sessionStorage.removeItem("acepressure-next-tip");
    setPayment(null);
    setError("");
    setCopied("");
    setSoundNote("");
  };

  const copy = async (value: string) => {
    if (!value) return;
    try {
      await navigator.clipboard.writeText(value);
      setCopied("Copied");
      window.setTimeout(() => setCopied(""), 1800);
    } catch {
      setCopied("Copy it from the field above");
    }
  };

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!config || !canSubmit) return;
    if (!Number.isInteger(amount) || amount < config.minimum || amount > config.maximum) {
      setError(`Choose a whole-rupee amount from ${formatRupees(config.minimum)} to ${formatRupees(config.maximum)}.`);
      return;
    }
    if (!values.name.trim()) {
      setError("Add a display name so the creator knows who to thank.");
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      const created = await api<TipPayment>("/api/public/tips", {
        method: "POST",
        body: JSON.stringify({
          amount: values.amount,
          name: values.name,
          email: values.email,
          remember: values.remember,
          message: values.message,
          tts: values.tts,
          voice: values.voice,
          ...(values.soundboard_id ? { soundboard_id: values.soundboard_id } : {})
        })
      });
      setPayment(created);
      window.sessionStorage.setItem("acepressure-next-tip", JSON.stringify(created));
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "The request could not be created.");
    } finally {
      setSubmitting(false);
    }
  };

  const tipForm = config && !payment ? (
    <form onSubmit={submit}>
      <div className="form-section">
        <div className="section-heading">
          <h3>Choose the amount</h3>
          <span>01 / 03</span>
        </div>
        <label className="field-label" htmlFor="amount">Whole rupees</label>
        <div className="amount-shell">
          <span className="amount-symbol" aria-hidden="true">₹</span>
          <input
            className="amount-input"
            id="amount"
            inputMode="numeric"
            max={config.maximum}
            min={config.minimum}
            name="amount"
            onChange={(event) => update("amount", event.target.value)}
            required
            step={1}
            type="number"
            value={values.amount}
          />
          <span className="amount-unit">INR</span>
        </div>
        <p className="field-help">Minimum {formatRupees(config.minimum)} · maximum {formatRupees(config.maximum)} · payment gets a small identifying paise suffix later.</p>
        <div className="preset-row" aria-label="Amount presets">
          {PRESETS.map((preset) => (
            <button className={`preset ${amount === preset ? "selected" : ""}`} disabled={preset < config.minimum || preset > config.maximum} key={preset} onClick={() => update("amount", String(preset))} type="button">
              ₹{preset}
            </button>
          ))}
        </div>
        <p className="tier-line"><span>{currentIcon}</span><span>{currentTier} · {formatRupees(amount || 0)}</span></p>
      </div>

      <div className="form-section">
        <div className="section-heading">
          <h3>Leave a note</h3>
          <span>02 / 03</span>
        </div>
        <div className="input-grid">
          <label className="input-group">
            <span className="field-label">Display name</span>
            <input className="text-input" maxLength={40} name="name" onChange={(event) => update("name", event.target.value)} placeholder="What should we call you?" required value={values.name} />
          </label>
          <label className="input-group">
            <span className="field-label">Email <span aria-hidden="true">·</span> optional</span>
            <input className="text-input" autoComplete="email" maxLength={254} name="email" onChange={(event) => update("email", event.target.value)} placeholder="Private supporter history" type="email" value={values.email} />
          </label>
        </div>
        <label className="toggle-row">
          <input checked={values.remember} onChange={(event) => update("remember", event.target.checked)} type="checkbox" />
          <span className="toggle-copy"><strong>Remember this supporter profile</strong>Only on this browser, for one year. Use this on your own device.</span>
        </label>
        <label className="input-group" style={{ display: "block", marginTop: 18 }}>
          <span className="field-label">Message</span>
          <textarea className="message-input" maxLength={config.tts_limit} name="message" onChange={(event) => update("message", event.target.value)} placeholder="Say something worth putting on stream…" rows={3} value={values.message} />
          <span className="textarea-meta"><span>Your message may appear on stream.</span><span>{values.message.length} / {config.tts_limit}</span></span>
        </label>
      </div>

      <div className="form-section">
        <div className="section-heading">
          <h3>Shape the alert</h3>
          <span>03 / 03</span>
        </div>
        <label className="toggle-row">
          <input checked={values.tts} disabled={config.tts_enabled === false} onChange={(event) => update("tts", event.target.checked)} type="checkbox" />
          <span className="toggle-copy"><strong>Read the message aloud</strong>{config.tts_enabled === false ? "Voice alerts are currently off." : `Voice alerts start from ${formatRupees(config.tts_minimum)}.`}</span>
        </label>
        {values.tts && <VoiceChoices config={config} disabled={config.tts_enabled === false} onChange={(voice) => update("voice", voice)} selected={values.voice} />}
        {sounds.length > 0 && <div style={{ marginTop: 16 }}><SoundChoices amount={amount} config={config} items={sounds} onChange={(soundboardId) => update("soundboard_id", soundboardId)} onNote={setSoundNote} selected={values.soundboard_id ?? ""} /></div>}
        {soundNote && <p className="notice notice-error" role="alert" style={{ marginTop: 12 }}>{soundNote}</p>}
      </div>

      <div className="form-actions">
        <button className="cta" disabled={!canSubmit} type="submit">{submitting ? "Preparing exact amount…" : availability === "demo" ? "Create demo tip" : "Continue to payment →"}</button>
        <p className="fine-print">No money is moved by this page until you approve the payment in your UPI app. The creator confirms the bank credit.</p>
      </div>
    </form>
  ) : null;

  return (
    <main className="site-shell min-h-screen" ref={rootRef}>
      <header className="site-header page-frame">
        <Link className="wordmark" href="/">ACE<span>PRESSURE</span><i> / SUPPORT</i></Link>
        <span className="header-note">Good games. Better company.</span>
        <span className="header-index">{loading ? "Loading" : "01 · Tip page"}</span>
      </header>

      <div className="tip-grid page-frame">
        <aside className="story-column">
          <section className="creator-panel" data-reveal>
            <p className="creator-kicker">BACK THE NEXT CLUTCH</p>
            <div className="creator-lockup">
              {config?.avatar ? <div className="avatar-frame"><Image alt={`${config.creator} avatar`} src={config.avatar} width={72} height={72} unoptimized /></div> : <div className="avatar-fallback" aria-hidden="true">A↗</div>}
              <LiveSignal label={loading ? "Connecting" : statusText(availability)} tone={availability === "demo" ? "demo" : availability === "open" ? "live" : "quiet"} />
            </div>
            <h1 className="creator-name">{config?.creator ?? "AcePressure"}</h1>
            <p className="creator-copy">{config?.welcome ?? "A calm, exact-amount way to support the stream."}</p>
            <p className="creator-detail">VALORANT · WUKONG · YOUTUBE</p>
            <dl className="stream-facts">
              <div><dt>Payment</dt><dd>UPI, exact amount</dd></div>
              <div><dt>Alerts</dt><dd>OBS ready</dd></div>
            </dl>
          </section>
          <Supporters loading={loading} supporters={supporters} />
          <p className="community-note" data-reveal>Support is optional. Staying for the next round is already a contribution.</p>
        </aside>

        <section className="checkout-column" data-reveal>
          <div className="checkout-card">
            <div className="checkout-inner">
              <div className="checkout-header">
                <div>
                  <p className="checkout-kicker">LIVE SUPPORT · PRIVATE CHECKOUT</p>
                  <h2 className="checkout-heading">Send a signal, not a transaction.</h2>
                  <p className="checkout-subhead">A compact tip, a message if you want one, and one exact UPI amount. Nothing hidden behind a giant hero.</p>
                </div>
                <span className="checkout-number">ACE / 01</span>
              </div>

              {!loading && <div className="status-strip" role="status"><span className={`status-dot ${availability}`} aria-hidden="true" /><span><strong>{statusText(availability)}.</strong> {statusMessage(availability, config?.creator ?? "AcePressure")}</span></div>}
              {error && <div className="notice notice-error" role="alert">{error}{copied && <span> · {copied}</span>}</div>}
              {!error && copied && <div className="notice" role="status">{copied}</div>}

              {payment ? <PaymentPanel now={now} onCopy={copy} onRefresh={() => void refreshPayment()} onReset={reset} payment={payment} /> : tipForm}
              {!loading && !config && <div className="notice notice-error" role="alert">The support settings could not be loaded. Refresh when AcePressure is running.</div>}
            </div>
          </div>
        </section>
      </div>

      <footer className="page-footer page-frame"><span>ACEPRESSURE · SUPPORT PAGE</span><span>Payments verified by the existing private bridge</span></footer>
    </main>
  );
}
