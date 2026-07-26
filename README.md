# BrandPulse

### AI-Powered Customer Voice Intelligence Platform

> Transform public customer conversations into actionable business intelligence.

BrandPulse is a production-oriented AI platform that collects customer conversations from multiple public channels, classifies sentiment and complaints using AI, and generates executive-ready reports that help organizations understand customer perception, emerging issues, and brand health.

The platform is designed to work with any organization by simply changing the monitored keywords.

---

## Key Features

- Multi-platform customer data collection
- AI-powered sentiment analysis
- Complaint classification
- Emotion and intent detection
- Emoji-aware customer intelligence
- Emerging issue detection
- Phrase mining and keyword analysis
- Executive HTML reports
- Modular connector architecture
- Production-ready Bronze → Silver → Gold data pipeline

---

## Architecture

```
                Public Data Sources
        (Google Play • YouTube • Nairaland)

                        │
                        ▼
                 Connector Layer
                        │
                        ▼
                 Bronze Storage
            (Raw immutable records)
                        │
                        ▼
                 Silver Pipeline
      Cleaning • Deduplication • PII Removal
      Language Detection • Emoji Normalization
                        │
                        ▼
             AI Classification Pipeline
     Sentiment • Complaints • Severity
     Emotion • Intent • Competitor Detection
                        │
                        ▼
                  Gold Dataset
                        │
                        ▼
                 Insight Engine
                        │
                        ▼
        Executive Reports (HTML / JSON / CSV)
```

---

## Project Structure

```
brandpulse/
│
├── src/
│   └── brandpulse/
│
├── docs/
│
├── config/
│
├── prompts/
│
├── tests/
│
├── eval/
│
├── output/          # Generated reports (ignored)
├── state/           # Runtime checkpoints (ignored)
├── storage/         # Local Bronze/Silver storage (ignored)
│
├── CLAUDE.md
├── TASKS.md
└── README.md
```

---

## Current Capabilities

### Supported Platforms

| Platform | Status |
|----------|--------|
| Google Play | ✅ |
| YouTube | ✅ |
| Nairaland | ✅ |
| Apple App Store | Partial (robots.txt restrictions) |

---

### AI Capabilities

- Sentiment Analysis
- Complaint Classification
- Emotion Detection
- Intent Detection
- Severity Detection
- Competitor Recognition
- Recommendation Generation
- Phrase Mining
- Emoji Analysis
- Executive Summary Generation

---

## Technology Stack

- Python
- Pydantic
- Pandas
- BeautifulSoup
- Google APIs
- Azure OpenAI / Groq (optional)
- pytest
- HTML/CSS Reporting

---

## Getting Started

### Install

```bash
pip install -e .
```

### Configure

Create a `.env` file.

```text
YOUTUBE_API_KEY=...
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_ENDPOINT=...
AZURE_OPENAI_DEPLOYMENT=...
```

### Run

```bash
python -m brandpulse snapshot --window 30d
```

The pipeline will:

1. Collect customer conversations
2. Clean and normalize data
3. Classify each mention
4. Generate insights
5. Produce an executive HTML report

---

## Documentation

| Document | Description |
|----------|-------------|
| `docs/PRD.md` | Product requirements |
| `docs/EngineeringDesign.md` | System architecture |
| `TASKS.md` | Development roadmap |
| `CLAUDE.md` | Development instructions |
| `claude/milestones/` | Milestone implementation prompts |

---

## Current Status

### MVP Complete

- Multi-platform ingestion
- Production data pipeline
- AI classification
- Executive reporting
- End-to-end orchestration
- Local storage backend
- Evaluation framework

---

## Roadmap

Future work focuses on improving intelligence quality rather than architecture.

- Improve complaint classification accuracy
- Reduce "Unknown" complaint labels
- Better Nigerian English & Pidgin sentiment detection
- Expand supported platforms
- Power BI integration
- REST API
- Azure Blob Storage backend
- Microsoft Fabric Lakehouse backend
- Real-time monitoring

---

## Design Principles

BrandPulse was built around a few core engineering principles:

- Modular architecture
- Backend-independent storage
- Connector abstraction
- Versioned data pipeline
- Production-first design
- AI provider independence
- Test-driven development
- Human-readable reports

---

## License

MIT License