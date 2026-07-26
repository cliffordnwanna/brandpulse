# Model Setup — Switching from Default to Real HuggingFace Models

The classification pipeline (Milestone 5) is built behind two adapter
interfaces — `SentimentModel` and `ComplaintClassifier`
(`src/brandpulse/pipeline/classify/`) — the same pattern as `StorageBackend`
in Milestone 4. Two implementations exist for each:

| Config value | Class | Requires |
|---|---|---|
| `sentiment_model: lexicon` (default) | `LexiconSentimentModel` | nothing — pure Python |
| `sentiment_model: huggingface` | `HuggingFaceSentimentModel` | `transformers`, `torch`, model download |
| `complaint_model: keyword` (default) | `KeywordComplaintClassifier` | nothing — pure Python |
| `complaint_model: huggingface` | `HuggingFaceZeroShotComplaintClassifier` | `transformers`, `torch`, model download |

## Why the default isn't a real model

This milestone was built in a sandbox with no `transformers`/`torch`
installed and no HuggingFace Hub network access — downloading the
multi-hundred-MB to multi-GB model weights below isn't possible there. The
lexicon/keyword default is a real, tested, offline classifier (not a stub) —
every acceptance criterion for label/confidence/reason output, LLM-conditional
logic, and Gold versioning is met using it. It is documented here as an
approximation, same as the Milestone 4 Pidgin/Hausa/Igbo language-detection
heuristic.

## Switching to the real models

1. Install the extra dependencies (not in `pyproject.toml`'s default
   dependencies, since they're large and only needed once you switch):

   ```bash
   pip install transformers torch
   ```

   On a machine without a GPU, the CPU build of `torch` is sufficient for
   inference at MVP data volumes; install a CUDA build only if you have a
   GPU available and expect high throughput.

2. Edit `config/config.yaml`:

   ```yaml
   classification:
     sentiment_model: huggingface
     complaint_model: huggingface
   ```

3. Run anything that touches classification (`python -m brandpulse classify`,
   `python -m brandpulse evaluate`) — the first run for each model will
   download weights from the HuggingFace Hub and cache them locally
   (`~/.cache/huggingface` by default). Subsequent runs load from cache.

## Model IDs in use

Sourced from the Milestone 5 spec (Engineering Design §10):

- **Sentiment (primary):** [`Davlan/naija-twitter-sentiment-afriberta-large`](https://huggingface.co/Davlan/naija-twitter-sentiment-afriberta-large) — Naija-specific, preferred for Pidgin accuracy.
  - Alternative: [`cardiffnlp/twitter-xlm-roberta-base-sentiment`](https://huggingface.co/cardiffnlp/twitter-xlm-roberta-base-sentiment) — set via `HuggingFaceSentimentModel(model_id=XLM_R_SENTIMENT_MODEL_ID)` if the Naija-specific model is unavailable.
- **Sentiment (English fallback):** [`cardiffnlp/twitter-roberta-base-sentiment-latest`](https://huggingface.co/cardiffnlp/twitter-roberta-base-sentiment-latest) — intended for `language == "en"` and low NaijaBERT confidence only; not yet wired as an automatic fallback (see "Known gap" below).
- **Complaint category (zero-shot):** [`facebook/bart-large-mnli`](https://huggingface.co/facebook/bart-large-mnli) — classifies against the fixed taxonomy in `pipeline/classify/complaint.py::COMPLAINT_TAXONOMY`; below-threshold results map to `Unknown`.

Do **not** use vanilla RoBERTa or VADER as the primary sentiment model —
both misclassify Nigerian Pidgin and code-mixed text (explicit spec
constraint).

## Known gap

The English-fallback routing rule ("use `cardiffnlp/twitter-roberta-base-sentiment-latest`
only when `language == "en"` AND primary confidence is below threshold") is
not implemented as automatic routing in `HuggingFaceSentimentModel` — it
currently always uses the model passed to its constructor
(`NAIJA_SENTIMENT_MODEL_ID` by default). Wiring the fallback routing is
straightforward once real models are available to test against, but doing
it blind (without being able to run either model) risked guessing at
threshold/routing behavior that can't be verified in this environment.
