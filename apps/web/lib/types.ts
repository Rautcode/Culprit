// Shapes match scripts/export_incidents.py, which mirrors the future REST
// API responses (docs/06-api-design.md). When the live API lands (Phase 2),
// these types describe its payloads too.

export interface AlertSummary {
  id: string;
  service: string;
  title: string;
  severity: string;
  fired_at: string;
}

export interface TimelineEvent {
  type: string;
  occurred_at: string;
  ref: string;
}

export interface ConfidenceBreakdown {
  rule_score: number;
  rag_score: number;
  llm_adjustment: number;
}

export interface RCACandidate {
  rank: number;
  deploy_id: string;
  service: string;
  summary: string;
  deployed_by: string;
  occurred_at: string;
  confidence: number;
  confidence_breakdown: ConfidenceBreakdown;
  rule_hits: string[];
  evidence: Record<string, unknown>;
}

export interface Incident {
  id: string;
  title: string;
  service: string;
  severity: string;
  status: string;
  opened_at: string;
  difficulty: string;
  description: string;
  alerts: AlertSummary[];
  timeline: TimelineEvent[];
  rca_candidates: RCACandidate[];
  proposed_remediation: string | null;
}
