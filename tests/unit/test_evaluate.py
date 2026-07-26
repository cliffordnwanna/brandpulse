"""Unit tests for the evaluation runner (Milestone 5, Engineering Design §15).

``eval/evaluate.py`` lives outside ``src/brandpulse`` (a project script, not
part of the installable package), so it's loaded by path here the same way
the CLI's ``evaluate`` command loads it.
"""

import importlib.util
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_evaluate_module():
    spec = importlib.util.spec_from_file_location(
        "brandpulse_eval", _REPO_ROOT / "eval" / "evaluate.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _StubSentimentModel:
    """Predicts a fixed label regardless of text, for controllable metrics."""

    def __init__(self, fixed_label: str):
        self._fixed_label = fixed_label

    def predict(self, text, language):
        from brandpulse.pipeline.classify.result import StageResult

        return StageResult(label=self._fixed_label, confidence=0.9, reason="stub")


def test_run_evaluation_perfect_predictor_on_single_class():
    evaluate_module = _load_evaluate_module()
    rows = [{"text": "x", "label": "Positive"} for _ in range(5)]
    metrics = evaluate_module.run_evaluation(rows, _StubSentimentModel("Positive"))

    assert metrics["accuracy"] == 1.0
    assert metrics["per_class"]["Positive"]["precision"] == 1.0
    assert metrics["per_class"]["Positive"]["recall"] == 1.0
    assert metrics["per_class"]["Positive"]["f1"] == 1.0


def test_run_evaluation_always_wrong_predictor():
    evaluate_module = _load_evaluate_module()
    rows = [{"text": "x", "label": "Positive"} for _ in range(5)]
    metrics = evaluate_module.run_evaluation(rows, _StubSentimentModel("Negative"))

    assert metrics["accuracy"] == 0.0
    assert metrics["per_class"]["Positive"]["recall"] == 0.0


def test_run_evaluation_confusion_matrix_shape():
    evaluate_module = _load_evaluate_module()
    rows = [{"text": "x", "label": "Positive"}, {"text": "y", "label": "Negative"}]
    metrics = evaluate_module.run_evaluation(rows, _StubSentimentModel("Positive"))

    matrix = metrics["confusion_matrix"]
    assert matrix["Positive"]["Positive"] == 1
    assert matrix["Negative"]["Positive"] == 1
    assert matrix["Negative"]["Negative"] == 0


def test_spam_class_never_counted_correct_by_construction():
    """The sentiment model's label set has no 'Spam' output — a Spam row can
    never be a true positive, which is documented behavior, not a bug."""
    evaluate_module = _load_evaluate_module()
    rows = [{"text": "x", "label": "Spam"}]
    metrics = evaluate_module.run_evaluation(rows, _StubSentimentModel("Neutral"))
    assert metrics["per_class"]["Spam"]["recall"] == 0.0


def test_write_metrics_csv_creates_file(tmp_path):
    evaluate_module = _load_evaluate_module()
    rows = [{"text": "x", "label": "Positive"}, {"text": "y", "label": "Negative"}]
    metrics = evaluate_module.run_evaluation(rows, _StubSentimentModel("Positive"))

    output_path = tmp_path / "metrics.csv"
    evaluate_module.write_metrics_csv(output_path, metrics)

    assert output_path.exists()
    content = output_path.read_text(encoding="utf-8")
    assert "accuracy" in content
    assert "confusion_matrix" in content


def test_evaluate_end_to_end_against_real_lexicon_model(tmp_path):
    from brandpulse.pipeline.classify.sentiment import LexiconSentimentModel

    evaluate_module = _load_evaluate_module()
    rows = [
        {"text": "Great app, easy transfers, very fast!", "label": "Positive"},
        {"text": "Terrible, my transfer failed and support is unresponsive.", "label": "Negative"},
    ]
    output_path = tmp_path / "metrics.csv"
    metrics = evaluate_module.evaluate(
        labeled_set_path=_write_rows_to_csv(tmp_path, rows),
        output_path=output_path,
        sentiment_model=LexiconSentimentModel(),
    )
    assert output_path.exists()
    assert metrics["accuracy"] == 1.0


def _write_rows_to_csv(tmp_path, rows):
    import csv

    path = tmp_path / "labeled.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["mention_id", "text", "label", "synthetic"])
        writer.writeheader()
        for i, row in enumerate(rows):
            writer.writerow(
                {
                    "mention_id": f"id-{i}",
                    "text": row["text"],
                    "label": row["label"],
                    "synthetic": "true",
                }
            )
    return path
