export const fmtCost = (usd: number) => (usd < 0.01 ? `$${usd.toFixed(4)}` : `$${usd.toFixed(3)}`);
export const fmtTokens = (n: number) => (n >= 1000 ? `${(n / 1000).toFixed(1)}k` : `${n}`);
export const fmtDuration = (s: number) => (s < 60 ? `${s.toFixed(0)}s` : `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`);
export const fmtAgo = (ts: number) => {
  const d = Date.now() / 1000 - ts;
  if (d < 60) return "just now";
  if (d < 3600) return `${Math.floor(d / 60)}m ago`;
  if (d < 86400) return `${Math.floor(d / 3600)}h ago`;
  return new Date(ts * 1000).toLocaleDateString();
};

export const STATUS_META: Record<string, { label: string; tone: string }> = {
  running: { label: "Running", tone: "signal" },
  awaiting_human: { label: "Needs you", tone: "human" },
  success: { label: "Verified success", tone: "verified" },
  unverified: { label: "Done · unverified", tone: "signal" },
  partial: { label: "Partial", tone: "signal" },
  failed_verification: { label: "Failed verification", tone: "risk" },
  failed: { label: "Failed", tone: "risk" },
  blocked: { label: "Blocked", tone: "human" },
  cancelled: { label: "Cancelled", tone: "muted" },
  interrupted: { label: "Interrupted", tone: "muted" },
  error: { label: "Error", tone: "risk" },
};

export const TONE: Record<string, string> = {
  signal: "text-signal border-signal/30 bg-signal/10",
  verified: "text-verified border-verified/30 bg-verified/10",
  risk: "text-risk border-risk/30 bg-risk/10",
  human: "text-human border-human/30 bg-human/10",
  info: "text-info border-info/30 bg-info/10",
  muted: "text-ink-300 border-white/10 bg-white/5",
};
