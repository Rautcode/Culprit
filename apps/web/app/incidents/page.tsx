import Link from "next/link";
import { allIncidents } from "@/lib/data";
import { SeverityDot, ConfidencePill } from "./ui";

export const metadata = { title: "Incidents · Culprit" };

export default function IncidentList() {
  const incidents = allIncidents();
  return (
    <div className="mx-auto max-w-5xl px-6 py-8">
      <div className="mb-6 flex items-baseline justify-between">
        <h1 className="text-xl font-semibold text-zinc-50">Incidents</h1>
        <span className="text-sm text-zinc-500">{incidents.length} open</span>
      </div>
      <div className="divide-y divide-zinc-800/80 rounded-lg border border-zinc-800 bg-zinc-900/40">
        {incidents.map((incident) => {
          const top = incident.rca_candidates[0];
          return (
            <Link
              key={incident.id}
              href={`/incidents/${incident.id}`}
              className="flex items-center gap-4 px-4 py-3 hover:bg-zinc-900 transition-colors"
            >
              <SeverityDot severity={incident.severity} />
              <div className="min-w-0 flex-1">
                <div className="truncate font-medium text-zinc-100">{incident.title}</div>
                <div className="mt-0.5 text-xs text-zinc-500">
                  <span className="font-mono">{incident.service}</span>
                  {" · "}
                  {incident.rca_candidates.length} candidate
                  {incident.rca_candidates.length === 1 ? "" : "s"}
                  {" · "}
                  {new Date(incident.opened_at).toLocaleString()}
                </div>
              </div>
              <span className="hidden text-xs text-zinc-500 sm:block">
                top cause <span className="font-mono text-zinc-400">{top.deploy_id}</span>
              </span>
              <ConfidencePill value={top.confidence} />
            </Link>
          );
        })}
      </div>
      <p className="mt-4 text-xs text-zinc-600">
        Every row is a real run of the correlation pipeline against a simulated
        incident from the harness catalog — nothing here is mocked UI data.
      </p>
    </div>
  );
}
