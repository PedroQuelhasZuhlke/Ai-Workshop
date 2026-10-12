import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { api, getApiKey } from "../api/client";
import ProcessingOverlay from "../components/ProcessingOverlay";
import type {
  Approval,
  ExportRecord,
  Issue,
  MappingProposal,
  NormalizedRequirement,
  PartCandidate,
  PurchasePlan,
  Run,
} from "../api/types";

const STEPS = ["mapping", "requirements", "candidates", "plans"] as const;
type Step = (typeof STEPS)[number];

function stepForStatus(status: string): Step {
  if (status === "awaiting_mapping_confirmation") return "mapping";
  if (status === "normalized") return "requirements";
  if (status === "sourced") return "candidates";
  return "plans";
}

function IssueList({ issues }: { issues: Issue[] }) {
  if (issues.length === 0) return null;
  return (
    <ul style={{ paddingLeft: 18, margin: "8px 0" }}>
      {issues.map((issue, i) => (
        <li key={i} className="muted">
          <span className={`badge ${issue.severity}`}>{issue.severity}</span>{" "}
          <strong>{issue.code}</strong>: {issue.message}
        </li>
      ))}
    </ul>
  );
}

function MappingStep({
  projectId,
  runId,
  hasDownstreamWork,
  onDone,
}: {
  projectId: string;
  runId: string;
  hasDownstreamWork: boolean;
  onDone: () => void | Promise<void>;
}) {
  const [proposal, setProposal] = useState<MappingProposal | null>(null);
  const [choices, setChoices] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [processing, setProcessing] = useState(false);

  useEffect(() => {
    api.getMapping(projectId, runId).then((res) => {
      setProposal(res.mapping_proposal);
      const initial: Record<string, string> = {};
      for (const m of res.mapping_proposal.mappings) {
        if (m.source_column) initial[m.target_field] = m.source_column;
      }
      setChoices(initial);
    });
  }, [projectId, runId]);

  const availableColumns = useMemo(() => {
    if (!proposal) return [];
    const cols = new Set<string>(proposal.unmapped_columns);
    for (const m of proposal.mappings) if (m.source_column) cols.add(m.source_column);
    return Array.from(cols).sort();
  }, [proposal]);

  async function confirm() {
    if (
      hasDownstreamWork &&
      !window.confirm(
        "Re-running normalization replaces the requirement values you have already " +
          "resolved and invalidates any candidates and plans. Continue?",
      )
    ) {
      return;
    }
    setError(null);
    setProcessing(true);
    try {
      const mappings: Record<string, string | null> = {};
      for (const m of proposal?.mappings ?? []) {
        mappings[m.target_field] = choices[m.target_field] ?? null;
      }
      await api.confirmMapping(projectId, runId, mappings);
      await onDone();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setProcessing(false);
    }
  }

  if (!proposal) return <p>Loading mapping...</p>;

  return (
    <div className="card">
      <h3>Confirm column mapping</h3>
      <p className="muted">
        EDA profile: {proposal.eda_profile ?? "unrecognized"} — confirm each field resolves to the
        right source column before normalization runs.
      </p>
      <table>
        <thead>
          <tr>
            <th>Target field</th>
            <th>Source column</th>
            <th>Resolved by</th>
            <th>Confidence</th>
          </tr>
        </thead>
        <tbody>
          {proposal.mappings.map((m) => (
            <tr key={m.target_field}>
              <td>{m.target_field}</td>
              <td>
                <select
                  value={choices[m.target_field] ?? ""}
                  onChange={(e) =>
                    setChoices((c) => ({ ...c, [m.target_field]: e.target.value }))
                  }
                >
                  <option value="">(none)</option>
                  {availableColumns.map((col) => (
                    <option key={col} value={col}>
                      {col}
                    </option>
                  ))}
                </select>
              </td>
              <td>{m.method}</td>
              <td>{m.confidence.toFixed(2)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {proposal.missing_required_fields.length > 0 && (
        <p className="error-text">
          Missing required fields: {proposal.missing_required_fields.join(", ")}
        </p>
      )}
      {error && <p className="error-text">{error}</p>}
      <button onClick={confirm} disabled={processing}>
        Confirm mapping &amp; normalize
      </button>
      {processing && <ProcessingOverlay message="Processing: confirming mapping and normalizing the BOM..." />}
    </div>
  );
}

function RequirementsStep({
  projectId,
  runId,
  onDone,
  onChanged,
}: {
  projectId: string;
  runId: string;
  onDone: () => void | Promise<void>;
  onChanged: () => void | Promise<void>;
}) {
  const [requirements, setRequirements] = useState<NormalizedRequirement[] | null>(null);
  const [issues, setIssues] = useState<Issue[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [processing, setProcessing] = useState(false);

  async function refresh() {
    const res = await api.getRequirements(projectId, runId);
    setRequirements(res.requirements);
    setIssues(res.issues);
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, runId]);

  async function proceed() {
    setError(null);
    setProcessing(true);
    try {
      await api.sourceCandidates(projectId, runId);
      await onDone();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setProcessing(false);
    }
  }

  if (!requirements) return <p>Loading requirements...</p>;

  return (
    <div className="card">
      <h3>Resolve requirements</h3>
      <IssueList issues={issues.filter((i) => i.severity !== "blocking")} />
      <table>
        <thead>
          <tr>
            <th>Requirement</th>
            <th>Refdes</th>
            <th>Category</th>
            <th>Unresolved</th>
            <th>Fix</th>
          </tr>
        </thead>
        <tbody>
          {requirements.map((r) => (
            <tr key={r.requirement_id}>
              <td>{r.requirement_id}</td>
              <td>{r.reference_designators.join(", ")}</td>
              <td>{r.category}</td>
              <td>
                {r.unresolved.length === 0 ? (
                  <span className="badge info">resolved</span>
                ) : (
                  r.unresolved.map((u) => (
                    <span key={u} className="badge blocking" style={{ marginRight: 4 }}>
                      {u}
                    </span>
                  ))
                )}
              </td>
              <td style={{ minWidth: 260 }}>
                {r.unresolved.length > 0 && (
                  <InlineResolveForm
                    projectId={projectId}
                    runId={runId}
                    requirement={r}
                    onSaved={async () => {
                      await refresh();
                      await onChanged();
                    }}
                  />
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {error && <p className="error-text">{error}</p>}
      <button onClick={proceed}>Run sourcing on resolved requirements</button>
      {processing && (
        <ProcessingOverlay message="Processing: sourcing candidates and applying policy..." />
      )}
    </div>
  );
}

function InlineResolveForm({
  projectId,
  runId,
  requirement,
  onSaved,
}: {
  projectId: string;
  runId: string;
  requirement: NormalizedRequirement;
  onSaved: () => void | Promise<void>;
}) {
  const needsCategory = requirement.unresolved.includes("category");
  const parameterNames = requirement.unresolved
    .filter((u) => u.startsWith("parameters."))
    .map((u) => u.slice("parameters.".length));
  const needsFootprint = requirement.unresolved.some((u) => u.startsWith("footprint."));

  const [category, setCategory] = useState("");
  const [paramValues, setParamValues] = useState<Record<string, string>>({});
  const [footprintCode, setFootprintCode] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    setSaving(true);
    setError(null);
    try {
      const body: Parameters<typeof api.resolveRequirement>[3] = {};
      if (needsCategory && category) body.category = category;
      if (parameterNames.length > 0) {
        body.parameters = {};
        for (const name of parameterNames) {
          const value = paramValues[name] ?? "";
          body.parameters[name] = { value: value || undefined, raw_text: value || name, unit: "" };
        }
      }
      if (needsFootprint && footprintCode) body.footprint = { package_code: footprintCode };
      await api.resolveRequirement(projectId, runId, requirement.requirement_id, body);
      await onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div>
      {needsCategory && (
        <div className="field-row">
          <input
            placeholder="category"
            value={category}
            onChange={(e) => setCategory(e.target.value)}
          />
        </div>
      )}
      {parameterNames.map((name) => (
        <div className="field-row" key={name}>
          <span className="muted">{name}</span>
          <input
            placeholder="value"
            value={paramValues[name] ?? ""}
            onChange={(e) => setParamValues((p) => ({ ...p, [name]: e.target.value }))}
          />
        </div>
      ))}
      {needsFootprint && (
        <div className="field-row">
          <span className="muted">footprint code</span>
          <input value={footprintCode} onChange={(e) => setFootprintCode(e.target.value)} />
        </div>
      )}
      {error && <p className="error-text">{error}</p>}
      <button className="secondary" onClick={save} disabled={saving}>
        Save
      </button>
    </div>
  );
}

function CandidatesStep({
  projectId,
  runId,
  onDone,
}: {
  projectId: string;
  runId: string;
  onDone: () => void | Promise<void>;
}) {
  const [candidates, setCandidates] = useState<PartCandidate[] | null>(null);
  const [issues, setIssues] = useState<Issue[]>([]);
  const [boardQuantity, setBoardQuantity] = useState(100);
  const [error, setError] = useState<string | null>(null);
  const [processing, setProcessing] = useState(false);

  useEffect(() => {
    api.getCandidates(projectId, runId).then((res) => {
      setCandidates(res.candidates);
      setIssues(res.issues);
    });
  }, [projectId, runId]);

  async function buildPlans() {
    setError(null);
    setProcessing(true);
    try {
      await api.createPlans(projectId, runId, boardQuantity);
      await onDone();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setProcessing(false);
    }
  }

  if (!candidates) return <p>Loading candidates...</p>;

  return (
    <div className="card">
      <h3>Candidate review</h3>
      <IssueList issues={issues.filter((i) => i.severity === "warning")} />
      <table>
        <thead>
          <tr>
            <th>Requirement</th>
            <th>MPN</th>
            <th>Manufacturer</th>
            <th>Tier</th>
            <th>Lifecycle</th>
            <th>Policy</th>
            <th>Rationale</th>
          </tr>
        </thead>
        <tbody>
          {candidates.map((c, i) => (
            <tr key={`${c.requirement_id}-${c.mpn}-${i}`}>
              <td>{c.requirement_id}</td>
              <td>{c.mpn}</td>
              <td>{c.manufacturer}</td>
              <td>
                <span className={`badge tier${c.substitution_tier}`}>
                  tier {c.substitution_tier}
                </span>
              </td>
              <td>{c.lifecycle}</td>
              <td>
                {c.policy_results.map((pr) => (
                  <div key={pr.rule_name} className="muted">
                    <span className={`badge ${pr.passed ? "info" : "blocking"}`}>
                      {pr.passed ? "pass" : "fail"}
                    </span>{" "}
                    {pr.rule_name}: {pr.reason}
                  </div>
                ))}
              </td>
              <td>{c.rationale ?? <span className="muted">no rationale -- review policy results</span>}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {candidates.length === 0 && <p className="muted">No candidates found for any requirement.</p>}
      <div className="field-row">
        <label>Board quantity:</label>
        <input
          type="number"
          min={1}
          value={boardQuantity}
          onChange={(e) => setBoardQuantity(Number(e.target.value))}
        />
        <button onClick={buildPlans}>Build purchase plans</button>
      </div>
      {error && <p className="error-text">{error}</p>}
      {processing && (
        <ProcessingOverlay message="Processing: building purchase plans for every decision mode..." />
      )}
    </div>
  );
}

function PlansStep({ projectId, runId }: { projectId: string; runId: string }) {
  const [plans, setPlans] = useState<PurchasePlan[] | null>(null);
  const [mode, setMode] = useState<string>("lowest_cost");
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [exports, setExports] = useState<ExportRecord[]>([]);
  const [note, setNote] = useState("");
  const [reviewedHighTier, setReviewedHighTier] = useState<Set<string>>(new Set());
  const [ackStale, setAckStale] = useState<Set<string>>(new Set());
  const [supplier, setSupplier] = useState("mouser");
  const [format, setFormat] = useState("csv");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [processing, setProcessing] = useState<string | null>(null);

  async function refresh() {
    const res = await api.getPlans(projectId, runId);
    setPlans(res.plans);
    setApprovals(await api.listApprovals(projectId, runId));
    setExports(await api.listExports(projectId, runId));
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, runId]);

  const plan = plans?.find((p) => p.mode === mode);

  const highTierIds = useMemo(
    () => (plan ? Array.from(new Set(plan.lines.filter((l) => l.substitution_tier >= 2).map((l) => l.requirement_id))) : []),
    [plan],
  );
  const staleWarnings = useMemo(
    () => (plan ? plan.warnings.filter((w) => w.kind === "stale_offer") : []),
    [plan],
  );

  async function revalidate() {
    setError(null);
    setMessage(null);
    setProcessing("Processing: re-validating offers and rebuilding plans...");
    try {
      await api.revalidatePlans(projectId, runId, mode);
      await refresh();
      setMessage("Re-validated against the current time.");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setProcessing(null);
    }
  }

  async function approve() {
    setError(null);
    setMessage(null);
    setProcessing("Processing: recording approval...");
    try {
      await api.approvePlan(projectId, runId, mode, {
        reviewed_high_tier_requirement_ids: Array.from(reviewedHighTier),
        acknowledged_stale_offer_snapshot_ids: Array.from(ackStale),
        note: note || null,
      });
      await refresh();
      setMessage("Plan approved and recorded in the approval ledger.");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setProcessing(null);
    }
  }

  async function doExport() {
    setError(null);
    setMessage(null);
    setProcessing("Processing: validating and generating the export file...");
    try {
      const record = await api.exportPlan(projectId, runId, mode, supplier, format);
      await refresh();
      setMessage(`Export ${record.id} created.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setProcessing(null);
    }
  }

  async function download(url: string, filename: string) {
    setError(null);
    setProcessing("Processing: downloading export...");
    try {
      const response = await fetch(`/api${url}`, {
        headers: { "x-api-key": getApiKey() ?? "" },
      });
      if (!response.ok) {
        setError(`download failed: ${response.status}`);
        return;
      }
      const blob = await response.blob();
      const objectUrl = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = objectUrl;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(objectUrl);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setProcessing(null);
    }
  }

  if (!plans) return <p>Loading plans...</p>;

  return (
    <div className="card">
      <h3>Plan comparison</h3>
      <div className="steps">
        {plans.map((p) => (
          <span
            key={p.mode}
            className={`step ${p.mode === mode ? "active" : ""}`}
            onClick={() => setMode(p.mode)}
            style={{ cursor: "pointer" }}
          >
            {p.mode} (${p.totals.grand_total})
          </span>
        ))}
      </div>
      {plan && (
        <>
          <p>
            Grand total: <strong>{plan.totals.grand_total} {plan.totals.currency}</strong> across{" "}
            {plan.supplier_count} supplier(s), longest lead time {plan.longest_lead_time_days} days.
          </p>
          <table>
            <thead>
              <tr>
                <th>Requirement</th>
                <th>MPN</th>
                <th>Supplier</th>
                <th>SKU</th>
                <th>Qty</th>
                <th>Ext. price</th>
                <th>Tier</th>
              </tr>
            </thead>
            <tbody>
              {plan.lines.map((l) => (
                <tr key={l.requirement_id}>
                  <td>{l.requirement_id}</td>
                  <td>{l.mpn}</td>
                  <td>{l.supplier}</td>
                  <td>{l.sku}</td>
                  <td>{l.order_qty}</td>
                  <td>
                    {l.extended_price} {l.currency}
                  </td>
                  <td>
                    <span className={`badge tier${l.substitution_tier}`}>{l.substitution_tier}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {plan.unfilled.length > 0 && (
            <div>
              <strong>Unfilled requirements:</strong>
              <ul>
                {plan.unfilled.map((u) => (
                  <li key={u.requirement_id} className="error-text">
                    {u.requirement_id}: {u.reason}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {plan.warnings.length > 0 && (
            <div>
              <strong>Warnings:</strong>
              <ul>
                {plan.warnings.map((w, i) => (
                  <li key={i}>
                    <span className={`badge ${w.kind === "stale_offer" ? "stale" : "warning"}`}>
                      {w.kind}
                    </span>{" "}
                    {w.message}
                  </li>
                ))}
              </ul>
            </div>
          )}
          <button className="secondary" onClick={revalidate}>
            One-click re-validate
          </button>

          <hr />
          <h4>Approve "{mode}"</h4>
          {highTierIds.length > 0 && (
            <div>
              <p className="muted">Confirm review of tier-2+ substitutions:</p>
              {highTierIds.map((id) => (
                <label key={id} style={{ display: "block" }}>
                  <input
                    type="checkbox"
                    checked={reviewedHighTier.has(id)}
                    onChange={(e) =>
                      setReviewedHighTier((s) => {
                        const next = new Set(s);
                        if (e.target.checked) next.add(id);
                        else next.delete(id);
                        return next;
                      })
                    }
                  />{" "}
                  {id}
                </label>
              ))}
            </div>
          )}
          {staleWarnings.length > 0 && (
            <div>
              <p className="muted">
                Stale offers exist (an export will be blocked until re-validated with fresh
                supplier data -- acknowledging here does not bypass that gate):
              </p>
              {staleWarnings.map((w, i) => (
                <label key={i} style={{ display: "block" }}>
                  <input
                    type="checkbox"
                    checked={w.requirement_id ? ackStale.has(w.requirement_id) : false}
                    onChange={(e) =>
                      setAckStale((s) => {
                        const next = new Set(s);
                        if (!w.requirement_id) return next;
                        if (e.target.checked) next.add(w.requirement_id);
                        else next.delete(w.requirement_id);
                        return next;
                      })
                    }
                  />{" "}
                  {w.message}
                </label>
              ))}
            </div>
          )}
          <div className="field-row">
            <input
              placeholder="approval note"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              style={{ minWidth: 280 }}
            />
            <button onClick={approve}>Approve plan</button>
          </div>

          <h4>Approval ledger for this run</h4>
          <table>
            <thead>
              <tr>
                <th>Mode</th>
                <th>Approved by</th>
                <th>At</th>
                <th>Plan hash</th>
                <th>Note</th>
              </tr>
            </thead>
            <tbody>
              {approvals.map((a) => (
                <tr key={a.id}>
                  <td>{a.decision_mode}</td>
                  <td>{a.approved_by}</td>
                  <td>{new Date(a.approved_at).toLocaleString()}</td>
                  <td className="muted">{a.plan_hash.slice(0, 12)}…</td>
                  <td>{a.note}</td>
                </tr>
              ))}
            </tbody>
          </table>

          <hr />
          <h4>Export</h4>
          <div className="field-row">
            <select value={supplier} onChange={(e) => setSupplier(e.target.value)}>
              <option value="mouser">Mouser</option>
              <option value="digikey">DigiKey</option>
              <option value="farnell">Farnell</option>
            </select>
            <select value={format} onChange={(e) => setFormat(e.target.value)}>
              <option value="csv">CSV</option>
              <option value="xlsx">XLSX</option>
            </select>
            <button onClick={doExport}>Export "{mode}"</button>
          </div>
          <table>
            <thead>
              <tr>
                <th>Supplier</th>
                <th>Format</th>
                <th>Exported by</th>
                <th>At</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {exports.map((ex) => (
                <tr key={ex.id}>
                  <td>{ex.supplier}</td>
                  <td>{ex.format}</td>
                  <td>{ex.exported_by}</td>
                  <td>{new Date(ex.exported_at).toLocaleString()}</td>
                  <td>
                    <button
                      className="secondary"
                      onClick={() => download(ex.download_url, `${ex.supplier}-export.${ex.format}`)}
                    >
                      Download
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
      {message && <p className="muted">{message}</p>}
      {error && <p className="error-text">{error}</p>}
      {processing && <ProcessingOverlay message={processing} />}
    </div>
  );
}

export default function RunPage() {
  const { projectId, runId } = useParams<{ projectId: string; runId: string }>();
  const [run, setRun] = useState<Run | null>(null);
  const [step, setStep] = useState<Step>("mapping");

  // Updates the run without moving the view, so editing an earlier step keeps you there.
  async function refreshRun() {
    if (!projectId || !runId) return;
    setRun(await api.getRun(projectId, runId));
  }

  // Jumps to the furthest step the run has reached, after a step completes forward.
  async function advance() {
    if (!projectId || !runId) return;
    const r = await api.getRun(projectId, runId);
    setRun(r);
    setStep(stepForStatus(r.status));
  }

  useEffect(() => {
    advance();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, runId]);

  if (!projectId || !runId || !run) return <p>Loading run...</p>;

  const reachedIndex = STEPS.indexOf(stepForStatus(run.status));

  return (
    <div>
      <div className="card">
        <h2>{run.source_filename}</h2>
        <div className="steps">
          {STEPS.map((s, i) => {
            const reachable = i <= reachedIndex;
            const state = s === step ? "active" : reachable ? "done clickable" : "locked";
            return (
              <span
                key={s}
                role="button"
                tabIndex={reachable ? 0 : -1}
                aria-disabled={!reachable}
                className={`step ${state}`}
                onClick={() => reachable && setStep(s)}
                onKeyDown={(e) => {
                  if (reachable && (e.key === "Enter" || e.key === " ")) setStep(s);
                }}
              >
                {s}
              </span>
            );
          })}
        </div>
        <p className="muted">
          Click a completed step to go back and fix values. Editing requirements or re-running
          the mapping invalidates the later steps until you re-run them.
        </p>
      </div>
      {step === "mapping" && (
        <MappingStep
          projectId={projectId}
          runId={runId}
          hasDownstreamWork={run.status !== "awaiting_mapping_confirmation"}
          onDone={advance}
        />
      )}
      {step === "requirements" && (
        <RequirementsStep
          projectId={projectId}
          runId={runId}
          onDone={advance}
          onChanged={refreshRun}
        />
      )}
      {step === "candidates" && (
        <CandidatesStep projectId={projectId} runId={runId} onDone={advance} />
      )}
      {step === "plans" && <PlansStep projectId={projectId} runId={runId} />}
    </div>
  );
}
