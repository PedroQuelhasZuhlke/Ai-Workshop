// Minimal, honest typings for the JSON shapes the backend actually returns.
// Not full mirrors of every contract field -- only what the UI reads or writes.

export interface DevUser {
  id: string;
  display_name: string;
  api_key: string;
}

export interface Project {
  id: string;
  name: string;
  created_at: string;
  role: "viewer" | "engineer" | "owner";
}

export interface Run {
  id: string;
  project_id: string;
  source_filename: string;
  status: string;
  created_at: string;
  board_quantity: number | null;
}

export interface Issue {
  severity: "blocking" | "warning" | "info";
  code: string;
  message: string;
  item_id: string | null;
}

export interface ColumnMapping {
  target_field: string;
  source_column: string | null;
  method: string;
  confidence: number;
}

export interface MappingProposal {
  source_file: string;
  eda_profile: string | null;
  mappings: ColumnMapping[];
  unmapped_columns: string[];
  missing_required_fields: string[];
  requires_confirmation: boolean;
}

export interface ParameterValue {
  value: string | null;
  unit: string;
  tolerance_pct: string | null;
  min: string | null;
  max: string | null;
  raw_text: string;
  source: string;
}

export interface Footprint {
  package_code: string | null;
  mounting: string | null;
  pin_count: number | null;
  pitch_mm: string | null;
  length_mm: string | null;
  width_mm: string | null;
  height_mm: string | null;
  thermal_pad: boolean | null;
  raw_text: string | null;
}

export interface NormalizedRequirement {
  requirement_id: string;
  reference_designators: string[];
  quantity_per_board: number;
  category: string;
  parameters: Record<string, ParameterValue>;
  footprint: Footprint;
  specified_mpn: { mpn: string; manufacturer: string | null } | null;
  criticality: string;
  compliance_required: string[];
  notes: string | null;
  confidence: { score: number; reasons: string[] };
  unresolved: string[];
}

export interface PolicyResult {
  rule_name: string;
  passed: boolean;
  reason: string;
}

export interface Evidence {
  description: string;
  url: string | null;
  snapshot_id: string | null;
  field_name: string | null;
}

export interface PartCandidate {
  requirement_id: string;
  mpn: string;
  manufacturer: string;
  lifecycle: string;
  compliance: string[];
  substitution_tier: number;
  policy_results: PolicyResult[];
  rationale: string | null;
  evidence: Evidence[];
  offers: Array<{
    supplier: string;
    sku: string;
    stock: number | null;
    moq: number;
    spq: number;
    price_breaks: Array<{ quantity: number; unit_price: string; currency: string }>;
    lead_time_days: number | null;
    snapshot_id: string;
    fetched_at: string;
  }>;
}

export interface PlanLine {
  requirement_id: string;
  mpn: string;
  manufacturer: string;
  supplier: string;
  sku: string;
  substitution_tier: number;
  order_qty: number;
  unit_price: string;
  extended_price: string;
  currency: string;
  snapshot_id: string;
}

export interface PlanWarning {
  kind: string;
  requirement_id: string | null;
  message: string;
}

export interface UnfilledRequirement {
  requirement_id: string;
  reason: string;
}

export interface PurchasePlan {
  mode: string;
  board_quantity: number;
  attrition_pct: string;
  lines: PlanLine[];
  totals: {
    currency: string;
    supplier_subtotals: Record<string, string>;
    shipping_total: string;
    grand_total: string;
  };
  longest_lead_time_days: number;
  supplier_count: number;
  unfilled: UnfilledRequirement[];
  warnings: PlanWarning[];
  snapshot_ids: string[];
}

export interface Approval {
  id: string;
  run_id: string;
  decision_mode: string;
  plan_hash: string;
  approved_by: string;
  approved_at: string;
  reviewed_high_tier_requirement_ids: string[];
  acknowledged_stale_offer_snapshot_ids: string[];
  note: string | null;
}

export interface ExportRecord {
  id: string;
  run_id: string;
  supplier: string;
  format: string;
  plan_hash: string;
  exported_by: string;
  exported_at: string;
  download_url: string;
}
