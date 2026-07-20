import raw from "./incidents.json";
import type { Incident } from "./types";

// Static export of real pipeline runs (scripts/export_incidents.py).
// Phase 2 swaps this module for fetches against the live REST API —
// callers keep the same shapes (lib/types.ts).
const incidents = (raw as { incidents: Incident[] }).incidents;

export function allIncidents(): Incident[] {
  return incidents;
}

export function getIncident(id: string): Incident | undefined {
  return incidents.find((incident) => incident.id === id);
}
