"""Complaint category classification (Engineering Design §9.1, §10, Milestone 5/6).

Same adapter pattern as ``sentiment.py``: ``ComplaintClassifier`` is the
interface, ``KeywordComplaintClassifier`` is the offline default, and
``HuggingFaceZeroShotComplaintClassifier`` wires the real zero-shot model
named in the milestone spec (``facebook/bart-large-mnli``) without being the
default. See ``docs/models.md``.

The taxonomy itself (the category list) lives in ``config/taxonomy.yaml``
(Milestone 6, reviewer feedback) — never hardcoded here. ``COMPLAINT_TAXONOMY``
is the default-path taxonomy, loaded once at import time so existing code
that imports it directly keeps working; anything that needs a
non-default/custom taxonomy should construct ``KeywordComplaintClassifier``
with an explicit ``taxonomy`` argument instead of relying on the module
default.
"""

from __future__ import annotations

import re
from typing import Protocol

from brandpulse.config.taxonomy import DEFAULT_TAXONOMY_PATH, load_taxonomy
from brandpulse.pipeline.classify.result import StageResult

COMPLAINT_TAXONOMY: tuple[str, ...] = load_taxonomy(DEFAULT_TAXONOMY_PATH).complaint_categories

UNKNOWN_CATEGORY = "Unknown"

ZERO_SHOT_MODEL_ID = "facebook/bart-large-mnli"


class ComplaintClassifier(Protocol):
    """Interface every complaint-category classifier implementation satisfies."""

    def classify(self, text: str, language: str | None) -> StageResult:
        """Classify ``text`` against ``COMPLAINT_TAXONOMY``, or ``Unknown``."""
        ...


# Deliberately conservative per-category keyword sets — precision over
# recall, same rationale as the Milestone 4 language-detection markers:
# text that matches nothing maps to Unknown (fed to 5b/BERTopic overflow)
# rather than being force-fit into the wrong category.
_CATEGORY_KEYWORDS: dict[str, set[str]] = {
    "Transfers": {"transfer", "transfers", "send money", "beneficiary", "nip", "interbank"},
    "Debit Issues": {"debited", "debit", "wrongly debited", "double debit", "deducted"},
    "Credit Delay": {"credit delay", "not credited", "yet to reflect", "pending credit"},
    "Login Issues": {"login", "log in", "cant login", "can't login", "password", "otp"},
    "App Crash": {"crash", "crashed", "crashing", "freeze", "freezes", "hangs", "not opening"},
    "Card Problems": {"card", "atm card", "debit card", "card blocked", "card declined"},
    "ATM": {"atm", "cash machine", "dispense", "swallowed my card"},
    "POS": {"pos", "point of sale", "terminal"},
    "USSD": {"ussd", "*945#", "short code"},
    "Fraud": {"fraud", "scam", "unauthorized", "stolen", "hacked", "phishing"},
    "Loans": {"loan", "loans", "repayment", "overdraft", "credit facility"},
    "Customer Service": {
        "customer service",
        "customer care",
        "support",
        "no response",
        "unresponsive",
        "complaint",
    },
    "Branches": {"branch", "branches", "teller", "queue"},
    "Charges": {"charge", "charges", "fee", "fees", "commission", "vat"},
    "Account Opening": {"account opening", "open an account", "kyc registration", "onboarding"},
    "KYC": {"kyc", "bvn", "nin", "verification", "know your customer"},
    "Competitor Mention": {"gtbank", "access bank", "uba", "firstbank", "opay", "moniepoint"},
    "General Feedback": {"app", "bank", "service", "experience"},
}


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[\w'*]+", text.lower())


class KeywordComplaintClassifier:
    """Default complaint classifier: category keyword/phrase matching.

    Offline, deterministic, no model download. Picks the category with the
    most distinct keyword matches; ties and zero matches fall through to
    ``Unknown``. ``taxonomy`` restricts which categories are considered
    (defaults to every category in ``config/taxonomy.yaml``) — the keyword
    sets themselves are matching logic, not taxonomy data, so they stay in
    Python; only the taxonomy *list* is externalized.
    """

    def __init__(self, taxonomy: tuple[str, ...] = COMPLAINT_TAXONOMY) -> None:
        self._taxonomy = set(taxonomy)

    def classify(self, text: str, language: str | None) -> StageResult:
        text_lower = text.lower()
        tokens = set(_tokenize(text))

        scores: dict[str, list[str]] = {}
        for category, keywords in _CATEGORY_KEYWORDS.items():
            if category not in self._taxonomy:
                continue
            matched = [
                kw for kw in keywords if (kw in tokens if " " not in kw else kw in text_lower)
            ]
            if matched:
                scores[category] = matched

        # "General Feedback" keywords are too generic to win outright — only
        # used as a last resort when nothing more specific matched.
        specific_scores = {c: m for c, m in scores.items() if c != "General Feedback"}

        if not specific_scores:
            if "General Feedback" in scores:
                return StageResult(
                    label="General Feedback",
                    confidence=0.5,
                    reason=f"Only generic terms matched: {', '.join(scores['General Feedback'])}.",
                )
            return StageResult(
                label=UNKNOWN_CATEGORY,
                confidence=0.3,
                reason="No taxonomy keywords matched this text.",
            )

        best_category = max(specific_scores, key=lambda c: len(specific_scores[c]))
        matched = specific_scores[best_category]
        confidence = round(min(0.6 + 0.1 * len(matched), 0.95), 2)
        return StageResult(
            label=best_category,
            confidence=confidence,
            reason=f"Matched keywords: {', '.join(matched)}.",
        )


class HuggingFaceZeroShotComplaintClassifier:
    """Real zero-shot classifier against ``COMPLAINT_TAXONOMY`` (Milestone spec).

    Not the default — requires ``transformers``/``torch`` and a HuggingFace
    Hub download. See ``docs/models.md``. Import deferred to ``__init__``.
    """

    def __init__(
        self, model_id: str = ZERO_SHOT_MODEL_ID, confidence_threshold: float = 0.5
    ) -> None:
        from transformers import pipeline  # noqa: PLC0415

        self._model_id = model_id
        self._confidence_threshold = confidence_threshold
        self._pipeline = pipeline("zero-shot-classification", model=model_id)

    def classify(self, text: str, language: str | None) -> StageResult:
        result = self._pipeline(text, candidate_labels=list(COMPLAINT_TAXONOMY))
        top_label = result["labels"][0]
        top_score = float(result["scores"][0])

        if top_score < self._confidence_threshold:
            return StageResult(
                label=UNKNOWN_CATEGORY,
                confidence=top_score,
                reason=f"{self._model_id} top match ({top_label}) below confidence threshold.",
            )

        return StageResult(
            label=top_label,
            confidence=top_score,
            reason=f"{self._model_id} zero-shot classification.",
        )
