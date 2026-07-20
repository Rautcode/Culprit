"""Monorepo path shim: ai_reasoning consumes correlation_engine's pipeline
output. Real packaging (installable dists) comes with the service split in
Phase 2; until then tests wire the two source trees directly."""
import sys
from pathlib import Path

SERVICES = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SERVICES / "ai-reasoning"))
sys.path.insert(0, str(SERVICES / "correlation-engine"))
