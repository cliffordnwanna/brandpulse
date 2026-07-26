"""Accuracy/precision/recall/F1 evaluation against the labeled set (Engineering Design §15).

Runs the 5a sentiment stage (never 5b/LLM — evaluation measures the always-on
core pipeline) against ``eval/labeled_v1.csv`` and writes accuracy,
per-class precision/recall/F1, and a confusion matrix to ``output/metrics.csv``.

Note on the ``Spam`` class: the sentiment model's label set is
``Positive | Negative | Neutral | Mixed`` (Engineering Design §10) — it has
no ``Spam`` output. Spam rows are included in the confusion matrix (so a
misclassification is visible) but are, by construction, never counted as
correct; this is a known limitation of the 5a-only evaluation, not a model
bug — spam/off-topic filtering is a separate concern from sentiment.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from brandpulse.pipeline.classify.sentiment import SentimentModel
from brandpulse.pipeline.eval_dataset import load_labeled_set

ALL_LABELS = ("Positive", "Negative", "Neutral", "Mixed", "Spam")


def run_evaluation(
    labeled_rows: list[dict[str, str]], sentiment_model: SentimentModel
) -> dict[str, Any]:
    predictions: list[str] = []
    truths: list[str] = []

    for row in labeled_rows:
        result = sentiment_model.predict(row["text"], language=None)
        predictions.append(result.label)
        truths.append(row["label"])

    confusion: dict[str, dict[str, int]] = {
        truth: dict.fromkeys(ALL_LABELS, 0) for truth in ALL_LABELS
    }
    for truth, pred in zip(truths, predictions, strict=True):
        confusion[truth][pred] += 1

    total = len(truths)
    correct = sum(1 for t, p in zip(truths, predictions, strict=True) if t == p)
    accuracy = correct / total if total else 0.0

    per_class: dict[str, dict[str, float]] = {}
    for label in ALL_LABELS:
        true_positives = confusion[label][label]
        false_negatives = sum(confusion[label][other] for other in ALL_LABELS if other != label)
        false_positives = sum(confusion[other][label] for other in ALL_LABELS if other != label)

        precision = (
            true_positives / (true_positives + false_positives)
            if (true_positives + false_positives)
            else 0.0
        )
        recall = (
            true_positives / (true_positives + false_negatives)
            if (true_positives + false_negatives)
            else 0.0
        )
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0

        per_class[label] = {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "support": sum(confusion[label].values()),
        }

    return {
        "accuracy": round(accuracy, 4),
        "per_class": per_class,
        "confusion_matrix": confusion,
    }


def write_metrics_csv(path: str | Path, metrics: dict[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["metric", "class", "value"])
        writer.writerow(["accuracy", "overall", metrics["accuracy"]])
        for label, stats in metrics["per_class"].items():
            writer.writerow(["precision", label, stats["precision"]])
            writer.writerow(["recall", label, stats["recall"]])
            writer.writerow(["f1", label, stats["f1"]])
            writer.writerow(["support", label, stats["support"]])

        writer.writerow([])
        writer.writerow(["confusion_matrix", "", ""])
        writer.writerow(["true_label", *ALL_LABELS])
        for truth in ALL_LABELS:
            writer.writerow(
                [truth, *[metrics["confusion_matrix"][truth][pred] for pred in ALL_LABELS]]
            )


def evaluate(
    labeled_set_path: str | Path,
    output_path: str | Path,
    sentiment_model: SentimentModel,
) -> dict[str, Any]:
    rows = load_labeled_set(labeled_set_path)
    metrics = run_evaluation(rows, sentiment_model)
    write_metrics_csv(output_path, metrics)
    return metrics
