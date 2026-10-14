type LiveSignalProps = {
  label: string;
  tone?: "quiet" | "live" | "demo";
};

/**
 * A deliberately small React Bits-style accent: one status signal, not a
 * library of effects. It gives the page a living cue without turning checkout
 * into a motion demo.
 */
export function LiveSignal({ label, tone = "quiet" }: LiveSignalProps) {
  return (
    <span className={`live-signal live-signal-${tone}`} aria-label={label}>
      <span className="live-signal-dot" aria-hidden="true" />
      <span>{label}</span>
    </span>
  );
}
