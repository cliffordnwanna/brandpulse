"""Synthetic labeled evaluation set generator (Engineering Design §15, Milestone 5).

No hand-labeled 500-example set exists yet in this repo. Rather than
fabricate labels dressed up as ground truth, this generates a clearly
synthetic set from template sentences per class — enough to validate the
pipeline mechanically (does classification run end-to-end, do metrics
compute correctly) but explicitly **not** a substitute for real labeled
data. ``eval/labeled_v1.csv``'s header carries a ``synthetic`` column set to
``true`` for every row generated this way, so the distinction is visible in
the data itself, not just in a docstring.
"""

from __future__ import annotations

import csv
import random
from pathlib import Path

_TEMPLATES: dict[str, list[str]] = {
    "Positive": [
        "The new update made transfers so much faster, well done!",
        "Wema Bank app dey work well well, no wahala at all.",
        "Excellent customer service today, my issue was resolved in minutes.",
        "I love how easy it is to open an account with ALAT.",
        "Great experience with the USSD code, worked first try.",
        "Their support team resolved my card issue quickly, very impressed.",
        "Smooth and reliable app, best banking experience so far.",
        "Thank you Wema for fixing the login issue so fast.",
        "The app is fast and the interface is very easy to use.",
        "Really happy with how quickly my loan was approved.",
    ],
    "Negative": [
        "My transfer failed three times today and no one from support responded.",
        "This app dey stress me well well, e no dey work at all.",
        "I was wrongly debited twice and still no refund after a week.",
        "The ATM swallowed my card and nobody at the branch could help.",
        "Terrible customer service, I have been on hold for over an hour.",
        "App keeps crashing every time I try to check my balance.",
        "Charges on this account are ridiculous, they take money for nothing.",
        "Still waiting for my credit to reflect since three days ago.",
        "I think this is fraud, someone accessed my account without my consent.",
        "Worst banking app I have ever used, constant login issues.",
    ],
    "Neutral": [
        "What time does the Ikeja branch close today?",
        "How do I update my BVN details on the app?",
        "Does this bank support USSD transfers to other banks?",
        "Just checking if the new update is out yet.",
        "What documents are needed to open a savings account?",
        "Is there a limit on daily ATM withdrawals?",
        "Can I use ALAT outside Nigeria?",
        "How long does KYC verification usually take?",
        "Where can I find my account statement in the app?",
        "What is the current exchange rate on this platform?",
    ],
    "Mixed": [
        "The app is fast but customer service is really slow to respond.",
        "Transfers work great, but the charges are way too high.",
        "I like the new interface but login still fails sometimes.",
        "Good rates on loans, though the approval process was frustrating.",
        "The USSD code works fine but the app itself keeps crashing.",
        "Customer care was helpful, but it took forever to reach them.",
        "Account opening was easy, but KYC verification dragged on for weeks.",
        "Nice app design, but I still experience random login issues.",
        "Fast service at the branch, but ATM is often out of cash.",
        "Great support this time, though my last two complaints went unanswered.",
    ],
    "Spam": [
        "Click here to win a free iPhone now!!! www.totally-legit-prize.example",
        "Make 500k weekly from home, DM me for details.",
        "Congratulations, you have been selected for a cash reward, claim now.",
        "Follow my page for forex trading tips and guaranteed profit.",
        "This is not about banking, check out my new music video.",
        "Buy followers cheap, message me on WhatsApp for pricing.",
        "Investment opportunity, double your money in 7 days guaranteed.",
        "Unrelated advert: best generator prices in Lagos, call now.",
        "Random test comment asdkjhaskjdh 12345.",
        "Sharing my crypto giveaway link, first 100 people get free coins.",
    ],
}

CLASSES = ("Positive", "Negative", "Neutral", "Mixed", "Spam")
FIELDNAMES = ("mention_id", "text", "label", "synthetic")


def generate_labeled_set(n_per_class: int = 100, seed: int = 42) -> list[dict[str, str]]:
    """Generate ``n_per_class`` synthetic rows per class (default 500 total).

    Templates are sampled with replacement and lightly perturbed (a numeric
    suffix) so ``n_per_class`` can exceed the template count per class while
    each row still has distinct ``text``/``mention_id``.
    """
    rng = random.Random(seed)
    rows: list[dict[str, str]] = []

    for label in CLASSES:
        templates = _TEMPLATES[label]
        for i in range(n_per_class):
            base_text = rng.choice(templates)
            text = base_text if i < len(templates) else f"{base_text} (#{i})"
            rows.append(
                {
                    "mention_id": f"synthetic-{label.lower()}-{i:04d}",
                    "text": text,
                    "label": label,
                    "synthetic": "true",
                }
            )

    rng.shuffle(rows)
    return rows


def write_labeled_set(path: str | Path, rows: list[dict[str, str]]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def load_labeled_set(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open("r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))
