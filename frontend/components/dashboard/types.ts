export interface TopConstituent {
  ticker: string;
  score: number;
}

export interface SectorRankItem {
  sector_name: string;
  sector_score: number;
  top_constituent: TopConstituent;
  constituent_count: number;
  map_version: string;
}

export interface TriggerItem {
  ticker: string;
  sector_name: string;
  trigger_summary: string;
  news_urls_used: string[];
  model_used: string;
  tokens_used: number;
}

export interface ReportContent {
  date: string;
  generated_at: string;
  rankings_price: SectorRankItem[];
  rankings_volume: SectorRankItem[];
  triggers: TriggerItem[];
}

export interface DailyBriefingReport {
  id: number;
  report_type: string;
  trading_date: string | null;
  generated_at: string | null;
  status: string;
  content: ReportContent | null;
}
