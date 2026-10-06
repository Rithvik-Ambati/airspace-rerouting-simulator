"""Regenerate scenario_catalogue.json from the Python scenario table (the single source of truth).

    python -m simulator.export_catalogue
"""
import json
from pathlib import Path

from .scenarios import catalogue_with_effects

PATH = Path(__file__).resolve().parent.parent / "scenario_catalogue.json"

if __name__ == "__main__":
    PATH.write_text(json.dumps(catalogue_with_effects(), indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {PATH}")
