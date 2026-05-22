export type EventRow = {
  id: number;
  code: string;
  doc_type: string;
  filed_at: string;
  source_month: string | null;
};

export type Summary = {
  codes: { code: string; n: number; last_filed: string; name: string | null }[];
  years: string[];
  months: string[];
  doc_types: string[];
};

export type Quota = {
  tokens: number;
  used: number;
  remaining: number;
  limit: number;
  by_token: { token_suffix: string; used: number; remaining: number; exhausted: boolean }[];
};

export type Candle = {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
};

export type ChipDay = {
  date: string;
  foreign_net: number;
  trust_net: number;
  dealer_net: number;
  total_net: number;
  margin_balance: number | null;
  short_balance: number | null;
};

export type CB = {
  bond_code: string;
  stock_code: string | null;
  name: string;
  conv_price: number | null;
  conv_start: string | null;
  conv_end: string | null;
  issue_date: string | null;
  maturity_date: string | null;
  issue_amount: number | null;
  outstanding_amount: number | null;
  coupon_rate: number | null;
  put_date: string | null;
  put_price: number | null;
  listing_status: string | null;
};

export type ReturnPoint = { date: string; close: number; return_pct: number };

export type Chip = {
  window: [string, string];
  institutional: {
    foreign_net: number;
    trust_net: number;
    dealer_net: number;
    total_net: number;
  };
  margin: { margin_delta: number | null; short_delta: number | null };
};

export type EventDetail = {
  id: number;
  doc_type: string;
  case_status: string | null;
  file_link: string | null;
  market: string | null;
  filed_at: string;
  anchor_date: string | null;
  anchor_open: number | null;
  returns: Record<string, ReturnPoint>;
  chip: Chip | Record<string, never>;
};

export type Stats = Record<
  string,
  Record<string, { n: number; avg_return_pct: number; win_rate_pct: number } | null>
>;

export type Backtest = {
  code: string;
  events: EventDetail[];
  stats: Stats;
};

export type OverviewStock = {
  code: string;
  market: string | null;
  name: string | null;
  has_bond: boolean;
  has_issue: boolean;
  event_count: number;
  last_event: string;
  price_change_pct: number | null;
};

export type OverviewResponse = {
  stocks: OverviewStock[];
  summary: {
    total: number;
    cb_count: number;
    issue_count: number;
    avg_price_change: number | null;
  };
  years: string[];
  months: string[];
};

export type ScrapeJob = {
  id: number;
  status: "running" | "success" | "failed";
  started_at: string;
  finished_at: string | null;
  rows_inserted: number;
  log: string[];
  log_total: number;
};

async function j<T>(url: string, opts?: RequestInit): Promise<T> {
  const r = await fetch(url, opts);
  if (!r.ok) {
    const text = await r.text();
    throw new Error(`${r.status}: ${text}`);
  }
  return r.json();
}

export const api = {
  summary: () => j<Summary>("/api/events/summary"),
  events: (params: { year?: string; month?: string; code?: string; doc_type?: string } = {}) => {
    const qs = new URLSearchParams();
    if (params.year) qs.set("year", params.year);
    if (params.month) qs.set("month", params.month);
    if (params.code) qs.set("code", params.code);
    if (params.doc_type) qs.set("doc_type", params.doc_type);
    return j<EventRow[]>(`/api/events?${qs}`);
  },
  quota: () => j<Quota>("/api/quota"),
  kline: (code: string, days = 730) =>
    j<{ code: string; data: Candle[] }>(`/api/kline/${code}?days=${days}`),
  chip: (code: string, days = 540) =>
    j<{ code: string; data: ChipDay[] }>(`/api/chip/${code}?days=${days}`),
  cb: (code: string) => j<{ code: string; data: CB[] }>(`/api/cb/${code}`),
  backtest: (code: string) => j<Backtest>(`/api/backtest/${code}`),
  overview: (params: { year?: string; month?: string } = {}) => {
    const qs = new URLSearchParams();
    if (params.year) qs.set("year", params.year);
    if (params.month) qs.set("month", params.month);
    return j<OverviewResponse>(`/api/overview?${qs}`);
  },
  startScrape: () => j<{ job_id: number }>("/api/scrape", { method: "POST" }),
  scrapeJob: (id: number, since = 0) =>
    j<ScrapeJob>(`/api/scrape/${id}?since=${since}`),
};
