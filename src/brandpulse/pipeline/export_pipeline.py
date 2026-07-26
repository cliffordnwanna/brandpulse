"""The ``export`` CLI command's implementation (Milestone 6).

Exports Gold (+ Silver, for the text/platform fields Gold doesn't duplicate)
to CSV or JSON only — no HTML, no word cloud, no InsightEngine involvement
at all. This is the plain-data escape hatch for someone who wants the raw
classified data in a spreadsheet or another tool, not a report.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from brandpulse.pipeline.output_writers import write_classifications_csv, write_mentions_csv
from brandpulse.pipeline.report_pipeline import latest_gold_records
from brandpulse.storage.base import StorageBackend

ExportFormat = Literal["csv", "json"]


def export_gold(
    backend: StorageBackend, output_dir: str | Path, run_id: str, fmt: ExportFormat = "csv"
) -> list[Path]:
    gold_records = latest_gold_records(backend)
    silver_records = list(backend.read_all("silver"))

    export_dir = Path(output_dir) / "exports"
    export_dir.mkdir(parents=True, exist_ok=True)

    if fmt == "csv":
        mentions_path = write_mentions_csv(
            export_dir / f"{run_id}_mentions.csv", silver_records, run_id
        )
        classifications_path = write_classifications_csv(
            export_dir / f"{run_id}_classifications.csv", gold_records, run_id
        )
        return [mentions_path, classifications_path]

    if fmt == "json":
        path = export_dir / f"{run_id}_export.json"
        payload = {"silver": silver_records, "gold": gold_records}
        path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        return [path]

    raise ValueError(f"Unsupported export format: {fmt!r}. Supported: 'csv', 'json'.")
