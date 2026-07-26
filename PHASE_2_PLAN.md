# Phase 2 — From Infrastructure to Intelligence

**Objective:** Transition BrandPulse from a working pipeline to a business intelligence platform that answers real questions about customer sentiment and complaints.

---

## Immediate Actions (This Week)

### Step 1: Run 30-Day Snapshot
```bash
cd c:\Users\Clifford.nwanna\Dev\brandpulse
.venv\Scripts\python.exe -m brandpulse snapshot --window 30d
```

**Expected output:**
```
output/reports/
  ├── snapshot-XXXXXXXX_report.html
  ├── snapshot-XXXXXXXX_insights.json
  ├── snapshot-XXXXXXXX_phrases.csv
  ├── snapshot-XXXXXXXX_wordcloud.png
  └── (+ CSV files)
```

**Time:** ~5-10 minutes depending on data volume

---

### Step 2: Open and Review HTML Report
```
output/reports/snapshot-XXXXXXXX_report.html
```

**Questions to ask:**
- Does the report render without errors?
- Are the charts displaying real data?
- Do the insights make intuitive sense?
- Are there obvious data quality issues?

---

### Step 3: Run Exploration Notebook
```bash
jupyter notebook analysis/explore.ipynb
```

**Purpose:** Validate AI outputs and discover unexpected patterns

**Key analyses:**
```python
# 1. Sentiment distribution
df.sentiment.value_counts()
df.sentiment.value_counts(normalize=True)

# 2. Complaint categories
df.complaint_category.value_counts()

# 3. Platform breakdown
df.groupby("platform").size()
df.groupby("platform")["sentiment"].value_counts()

# 4. Top phrases by sentiment
positive_phrases = df[df.sentiment == "positive"]["phrase"].value_counts().head(20)
negative_phrases = df[df.sentiment == "negative"]["phrase"].value_counts().head(20)

# 5. Complaints trending up/down
df.groupby(["platform", "complaint_category"]).size()
```

---

## Core Analysis Questions (Priority Order)

### Tier 1: Validation (Is the AI working?)

**Q1.1: Is sentiment classification accurate?**
- Run exploratory notebook
- Hand-sample 20 records (positive, negative, neutral)
- Do they match reality?
- If accuracy < 80%, adjust lexicon or model

**Q1.2: Are complaint categories sensible?**
- Look at top 10 complaint categories
- Do they match Wema/ALAT's actual pain points?
- Are there categories that should be merged or split?
- Are there emerging categories not in `config/taxonomy.yaml`?

**Q1.3: Is language detection working?**
- Sample records from each platform
- Are they correctly tagged as English / Pidgin / Other?
- Any obvious misclassifications?

---

### Tier 2: Business Questions (What's the story?)

**Q2.1: What are customers complaining about?**
```
Top Complaint Categories (30d):
  - Transfers: 52% (842 complaints)
  - Cards: 21% (338 complaints)
  - Fraud: 15% (241 complaints)
  - Login: 8% (129 complaints)
  - Other: 4% (64 complaints)
```
→ Action: If transfers >> all others, prioritize transfer team

---

**Q2.2: What exact words are they using?**
```
Top Phrases (phrases.csv):
  - "failed transfer": 412
  - "money not reversed": 287
  - "unable to login": 156
  - "card declined": 143
  - "account locked": 89
```
→ Action: These become support ticket templates

---

**Q2.3: Where are complaints concentrated?**
```
Complaints by Platform:
  - Google Play: 65% (1,050)
  - Nairaland: 23% (370)
  - YouTube: 12% (193)
```
→ Action: Google Play is your reputation crisis point

---

**Q2.4: Is sentiment improving or declining?**
```
Compare 30d snapshots:
  - Week 1: 35% negative, 45% neutral, 20% positive
  - Week 4: 42% negative, 38% neutral, 20% positive
  → Trending: WORSE
```
→ Action: Escalate to leadership

---

**Q2.5: Are specific competitors mentioned?**
```
Competitor Mentions (insights.json):
  - Opay: Positive 47, Negative 3 → 94% positive
  - Access Bank: Positive 12, Negative 18 → 40% positive
  - GTBank: Positive 8, Negative 5 → 62% positive
```
→ Action: Understand Opay's advantages

---

**Q2.6: What emotion dominates?**
```
Emotion Distribution (if 5b enabled):
  - 😭 Frustrated: 45%
  - 😡 Angry: 28%
  - 😞 Disappointed: 18%
  - 🙏 Hopeful: 6%
  - ❤️ Satisfied: 3%
```
→ Action: Customer support retraining needed

---

### Tier 3: Strategic Questions (What should we do?)

**Q3.1: Why are Google Play reviews so negative?**
- Sample top 30 negative Google Play comments
- Are they technical bugs, feature requests, or service issues?
- Compare against Nairaland/YouTube tone

**Q3.2: Are ALAT complaints different from Wema Bank complaints?**
```python
alat_complaints = df[df.app_id == "com.wemabank.alat.prod"]["complaint_category"].value_counts()
wema_complaints = df[df.app_id == "wemabank.com.afb.prod"]["complaint_category"].value_counts()
```
- Do they have different pain points?
- Should they have different service teams?

**Q3.3: Which complaints are increasing fastest?**
```
Compare Week 1 vs Week 4:
  - Transfers: 80 → 240 (3x increase) 🔴
  - Cards: 50 → 65 (1.3x increase)
  - Login: 15 → 20 (1.3x increase)
```
→ Action: Transfer pipeline is breaking down

**Q3.4: Is one app significantly worse?**
```
Sentiment by App:
  - ALAT: 28% negative, 52% neutral, 20% positive
  - Wema Bank: 35% negative, 38% neutral, 27% positive
  - COVR: 15% negative, 60% neutral, 25% positive
```
→ Action: ALAT needs immediate UX review

---

## Validation Checklist

### Data Quality ✓
- [ ] No missing values in critical fields (platform, text, timestamp)
- [ ] Text contains real customer language (not corrupt/truncated)
- [ ] Timestamps are within expected window
- [ ] Author hashing applied (no real names visible)

### AI Accuracy ✓
- [ ] Sentiment: Hand-verify 20 random records, expect > 80% accuracy
- [ ] Complaint categories: Do top 10 match real business pain points?
- [ ] Confidence scores: Are low-confidence records actually ambiguous?
- [ ] Language detection: Sample multilingual records for correctness

### Output Files ✓
- [ ] `mentions.csv`: Row count matches Bronze collection
- [ ] `classifications.csv`: Row count = `mentions.csv` (dedup applied)
- [ ] `summary.csv`: Totals match classifications
- [ ] `connector_health.csv`: All 4 connectors represented
- [ ] `run_metadata.json`: Contains run config for reproducibility
- [ ] `insights.json`: Valid JSON, all required fields present
- [ ] `phrases.csv`: Real customer language, not corrupted
- [ ] `wordcloud.png`: Renders without artifacts

### Report Quality ✓
- [ ] HTML report opens without errors in browser
- [ ] Charts render with real data
- [ ] Insights section has actionable recommendations
- [ ] Platform limitations section displayed
- [ ] No PII visible (author names hashed)

---

## Analysis Notebook Template

See `analysis/explore.ipynb` for the full exploration framework.

Key sections:
1. **Load & Inspect** — Basic data quality checks
2. **Sentiment Overview** — Distribution across platforms
3. **Complaint Analysis** — Top categories and trends
4. **Phrase Mining** — Customer language vocabulary
5. **Platform Comparison** — Google Play vs Nairaland vs YouTube
6. **Trend Detection** — Is sentiment improving or declining?
7. **Competitor Analysis** — Who are customers comparing us to?
8. **Emotion Analysis** — What do customers feel?
9. **Business Questions** — Cross-tabulations for strategic decisions

---

## Success Criteria

**Phase 2 is successful when:**

1. ✅ **30-day snapshot runs without errors** — Full pipeline works at scale
2. ✅ **Exploration notebook validates AI** — 80%+ accuracy on hand-verified samples
3. ✅ **Outputs are actionable** — Top 3 insights directly inform product/support decisions
4. ✅ **No data quality issues** — Classifications are trustworthy
5. ✅ **Team alignment** — Wema stakeholders agree on insights and next steps

---

## After Validation: Phase 3 (Next Milestone)

If Phase 2 validates successfully:

1. **Integrate with business workflows**
   - Daily snapshot to a shared dashboard
   - Weekly insights email to leadership
   - Real-time alerts for complaint spikes

2. **Refine the taxonomy**
   - Add emerging complaint categories
   - Adjust sentiment thresholds based on false positives
   - Tune Insight Engine rules based on business priority

3. **Expand data sources** (Phase 3)
   - Instagram (requires Meta auth)
   - X/Twitter (requires paid API)
   - TikTok (requires research API approval)

4. **Build integrations**
   - Power BI dashboard
   - Slack notifications
   - CLM case routing

---

## Timeline

| Activity | Time | Owner |
|----------|------|-------|
| Run 30-day snapshot | 10 min | Clifford |
| Review HTML report | 15 min | Clifford + Wema team |
| Run exploration notebook | 30 min | Clifford |
| Validate AI accuracy | 1 hour | Clifford |
| Stakeholder review | 1 hour | Clifford + Wema team |
| **Total** | **~3 hours** | |

---

## Questions for Wema Stakeholders

Come prepared with these when reviewing outputs:

1. **"Do you recognize yourself in these complaints?"**
   - Are the top categories your actual pain points?

2. **"Would you handle Google Play differently than Nairaland?"**
   - Platform-specific issues?

3. **"What's your transfer success rate?"**
   - If we're seeing 52% complaints about transfers, what's real?

4. **"How accurate is our complaint detection?"**
   - Hand-sample 10 records, score our AI

5. **"What would change if you had this report weekly?"**
   - Is this valuable enough to automate?

6. **"Which insight surprises you the most?"**
   - This helps us tune the Insight Engine

---

## Next: Create the Exploration Notebook

See `analysis/explore.ipynb` (created next)

