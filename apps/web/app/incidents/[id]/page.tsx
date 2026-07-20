import { notFound } from "next/navigation";
import { allIncidents, getIncident } from "@/lib/data";
import type { RCACandidate } from "@/lib/types";
import { SeverityDot, ConfidenceBar } from "../ui";

export function generateStaticParams() {
  return allIncidents().map((incident) => ({ id: incident.id }));
}

export default async function IncidentDetail({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const incident = getIncident(id);
  if (!incident) notFound();

  return (
    <div className="mx-auto max-w-6xl px-6 py-8">
      <header className="mb-6">
        <div className="flex items-center gap-3">
          <SeverityDot severity={incident.severity} />
          <h1 className="text-xl font-semibold text-zinc-50">{incident.title}</h1>
          <span className="rounded-full border border-amber-800/60 px-2 py-0.5 text-xs text-amber-300">
            {incident.status}
          </span>
        </div>
        <p className="mt-1 text-sm text-zinc-500">
          <span className="font-mono">{incident.service}</span>
          {" · opened "}
          {new Date(incident.opened_at).toLocaleString()}
          {" · severity "}
          {incident.severity}
        </p>
      </header>

      <div className="grid gap-6 lg:grid-cols-[minmax(260px,1fr)_2fr]">
        {/* Timeline pane */}
        <section className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-4">
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-zinc-400">
            Timeline
          </h2>
          <ol className="space-y-2">
            {incident.timeline.map((event, i) => (
              <li key={i} className="flex gap-3 text-sm">
                <span className="w-16 shrink-0 font-mono text-xs text-zinc-500">
                  {new Date(event.occurred_at).toLocaleTimeString([], {
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </span>
                <span className="shrink-0 rounded bg-zinc-800 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-zinc-400">
                  {event.type.replace("_", " ")}
                </span>
                <span className="truncate font-mono text-xs text-zinc-300">{event.ref}</span>
              </li>
            ))}
          </ol>
        </section>

        {/* Investigation pane */}
        <section className="space-y-4">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-zinc-400">
            Root cause candidates
          </h2>
          {incident.rca_candidates.map((candidate) => (
            <Candidate key={candidate.deploy_id} candidate={candidate} />
          ))}

          {incident.proposed_remediation && (
            <div className="rounded-lg border border-emerald-900/60 bg-emerald-950/20 p-4">
              <h3 className="text-sm font-semibold text-emerald-300">Proposed fix</h3>
              <code className="mt-1 block font-mono text-sm text-emerald-200">
                {incident.proposed_remediation}
              </code>
              <p className="mt-2 text-xs text-zinc-500">
                Propose-only in Phase 1 — execution requires the guardrailed
                remediation service and human approval (docs/10-roadmap.md).
              </p>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

function Candidate({ candidate }: { candidate: RCACandidate }) {
  const pct = Math.round(candidate.confidence * 100);
  const b = candidate.confidence_breakdown;
  const isTop = candidate.rank === 1;
  return (
    <div
      className={`rounded-lg border p-4 ${
        isTop ? "border-emerald-800/70 bg-zinc-900/60" : "border-zinc-800 bg-zinc-900/30"
      }`}
    >
      <div className="flex items-baseline gap-3">
        <span className="text-xs font-mono text-zinc-500">#{candidate.rank}</span>
        <span className="font-mono text-sm text-zinc-100">{candidate.deploy_id}</span>
        <span className="text-xs text-zinc-500">
          {candidate.service} · by {candidate.deployed_by} ·{" "}
          {new Date(candidate.occurred_at).toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit",
          })}
        </span>
        <span className="ml-auto font-mono text-sm text-zinc-200">{pct}%</span>
      </div>
      <p className="mt-1 text-sm text-zinc-300">{candidate.summary}</p>
      <div className="mt-3">
        <ConfidenceBar value={candidate.confidence} />
      </div>

      <details className="group mt-3">
        <summary className="cursor-pointer select-none text-xs text-zinc-400 hover:text-zinc-200">
          Why {pct}%? — rules {Math.round(b.rule_score * 100)}%, history{" "}
          {Math.round(b.rag_score * 100)}%, LLM {b.llm_adjustment >= 0 ? "+" : ""}
          {Math.round(b.llm_adjustment * 100)}%
        </summary>
        <div className="mt-3 space-y-2 border-l border-zinc-800 pl-4">
          {candidate.rule_hits.map((rule) => (
            <EvidenceRow key={rule} rule={rule} value={candidate.evidence[rule]} />
          ))}
          {"alerts_correlated" in candidate.evidence && (
            <div className="text-xs text-zinc-400">
              <span className="font-mono text-zinc-300">storm correlation</span>: explains{" "}
              {String(candidate.evidence["alerts_correlated"])} alert(s) in this incident
            </div>
          )}
        </div>
      </details>
    </div>
  );
}

function EvidenceRow({ rule, value }: { rule: string; value: unknown }) {
  return (
    <div className="text-xs">
      <span className="font-mono text-zinc-300">{rule}</span>
      <pre className="mt-0.5 overflow-x-auto whitespace-pre-wrap break-all text-zinc-500">
        {JSON.stringify(value, null, 1)}
      </pre>
    </div>
  );
}
