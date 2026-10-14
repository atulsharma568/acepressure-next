export type Availability = "open" | "demo" | "paused" | "setup";

export type PublicConfig = {
  creator: string;
  welcome: string;
  minimum: number;
  maximum: number;
  voices: string[];
  voice_labels?: Record<string, string>;
  voice_genders?: Record<string, "Male" | "Female" | "Any">;
  sounds: string[];
  sound_labels?: Record<string, string>;
  allow_sound_choice: boolean;
  tts_minimum: number;
  tts_limit: number;
  avatar?: string;
  accepting_tips: boolean;
  tiers?: number[];
  tts_read_full?: boolean;
  tts_short_limit?: number;
  tts_full_from?: number;
  tts_enabled?: boolean;
  tts_engine?: string;
  availability?: Availability;
  ready?: boolean;
  demo?: boolean;
};

export type Supporter = {
  name: string;
  total: number;
  count: number;
};

export type SoundboardItem = {
  id: string;
  name: string;
  emoji?: string;
  category: string;
  min_paise: number;
  url: string;
  volume?: number;
};

export type TipPayment = {
  id: string;
  token: string;
  name: string;
  display_paise: number;
  requested_paise: number;
  status: "PENDING" | "VERIFIED" | "EXPIRED" | "MANUAL" | "REJECTED" | "REFUNDED";
  expires: number;
  upi_uri?: string | null;
  upi_id?: string;
  payee_name?: string;
  demo?: boolean;
  needs_review?: boolean;
  alert_queued?: boolean;
};

export type TipFormValues = {
  amount: string;
  name: string;
  email: string;
  remember: boolean;
  message: string;
  tts: boolean;
  voice: string;
  soundboard_id?: string;
};

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    credentials: "same-origin",
    cache: "no-store",
    headers: {
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...init?.headers
    }
  });

  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    body = null;
  }

  if (!response.ok) {
    const message =
      typeof body === "object" && body !== null && "error" in body && typeof body.error === "string"
        ? body.error
        : `Request failed (HTTP ${response.status}).`;
    throw new ApiError(message, response.status);
  }

  return body as T;
}

export function formatPaise(paise: number): string {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: paise % 100 === 0 ? 0 : 2
  }).format((paise || 0) / 100);
}

export function formatRupees(rupees: number): string {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0
  }).format(rupees || 0);
}

export function availabilityOf(config: PublicConfig | null): Availability {
  if (!config) return "setup";
  return config.availability ?? (!config.accepting_tips ? "paused" : config.demo ? "demo" : config.ready ? "open" : "setup");
}

export function voiceLabel(config: PublicConfig, voice: string): string {
  if (config.voice_labels?.[voice]) return config.voice_labels[voice];
  if (voice === "en-IN") return "English · India";
  if (voice === "hi-IN") return "Hindi · India";
  return voice;
}

export function soundLabel(config: PublicConfig, value: string): string {
  return config.sound_labels?.[value] ?? ({ chime: "Chime", pulse: "Pulse", none: "Silent" }[value] ?? value);
}

export function countdown(expires: number, now = Math.floor(Date.now() / 1000)): string {
  const remaining = Math.max(0, expires - now);
  return `${Math.floor(remaining / 60)}:${String(remaining % 60).padStart(2, "0")}`;
}
