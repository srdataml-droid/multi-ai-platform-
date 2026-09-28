# Machine learning pipeline

The first model predicts **no-shows**: which upcoming bookings are likely to be missed, and
why. It works for every pack (a dental patient who does not come, a trades visit where
nobody is home). The same pipeline shape will carry the next models (section 6).

## 1. The pipeline

```
Staff mark each past booking "Came" / "No-show"            (Schedule page)
        │  appointments.outcome, outcome_at, outcome_by        (migration 0014)
        ▼
novaxis_core.features.labelled_rows()  → one row per booking, no personal data
        ▼
novaxis_ml.no_show train               → time split, logistic regression vs gradient boosting,
        │                                AUC and Brier score, refit on all rows
        ▼
packages/core/novaxis_core/ml_models/no_show.json   (the model: one weight per input)
        ▼
novaxis_core.no_show  (plain Python, runs on Vercel) → risk, level, reasons on the Schedule page
```

- **One definition of the inputs.** `features.py` is used for training and for live scoring,
  so the model is never scored on inputs computed differently from how it learned.
  A test checks the exported file gives exactly the trained model's answer.
- **No leakage.** Every input is known before the appointment. A customer's history counts
  only *earlier* bookings.
- **No personal data in training.** No names, numbers, ids or message text.
- **Nothing ML-heavy on the server.** scikit-learn lives in `packages/ml`, which is never
  deployed; the API scores with a weighted sum.

## 2. Inputs

| Input | Meaning |
|---|---|
| `lead_days` | Days between booking and appointment (capped at 120) |
| `hour`, `weekday` | When, in the business's time zone |
| `confirmed` | Customer replied C/confirm to a reminder before the visit |
| `prior_attended`, `prior_no_shows` | This customer's earlier outcomes |
| `service_code`, `channel`, `pack_id` | What was booked, how, and for which kind of business |

## 3. Commands

```bash
make ml-train-synthetic   # prove the pipeline on synthetic data (no database needed)
make ml-train             # train on real recorded outcomes (reads the database)
make ml-export            # the training table as CSV (ml-rows.csv) for your own notebooks
```

Training refuses with fewer than **200 bookings with an outcome and 20 no-shows**, and says
so. A model on less data would be noise presented as insight.

After training, commit `no_show.json`; the next deploy serves it. The report prints:
- both models' AUC (0.5 = coin toss, 1.0 = perfect ranking) and Brier score (lower is better);
- a "just guess the average" baseline that both must beat;
- a note on whether gradient boosting beat logistic regression by enough to be worth
  serving (more than 0.03 AUC).

## 4. What is live now

The repo ships a model trained on **synthetic data**. Synthetic data means bookings
generated with planted causes: booking far ahead and earlier misses raise risk, while
confirming and earlier visits lower it. It proves the pipeline end to end.

On the synthetic data: logistic regression AUC 0.81 and gradient boosting 0.80, against 0.50
for guessing. Training recovered every planted effect.

**A synthetic model is shown only to `demo-*` businesses, labelled "demo model trained on
synthetic data". A real business sees no score until a model trained on real outcomes
replaces the file.** (Test: `test_a_synthetic_model_is_only_ever_shown_to_demo_businesses`.)

## 5. Getting real data (the founder's part)

1. Pilot businesses press **Came / No-show** on past bookings (Schedule page, last 7 days).
   This takes seconds a day and is the whole dataset.
2. After about 200 outcomes with 20+ no-shows, run `make ml-train` and read the report.
3. Only ship if logistic regression clearly beats the average baseline on AUC and Brier.

**Using it:** today the score is shown with its reasons. Acting on it (an extra reminder for
high-risk bookings, or asking for a deposit) should go through the approval step first,
like every other action.

## 6. Next models on the same pipeline

| Model | Labels needed | Status |
|---|---|---|
| No-show risk | Came / No-show per booking | **Built** |
| Job duration (trades) | Actual start/finish per job | Needs actual times from the booking software |
| Enquiry value / urgency | Booked? value? per conversation | Needs a value field on bookings |
| Stock counting from photos | Photos with the true count | **Built** (section 7) |
| Will staff approve this? | Every Approve / Edit / Reject | **Built** (section 8) |

## 7. Stock counting from a photo (neural network)

Staff open **Stock**, take a photo of a shelf, and get a count with a red dot on each item
counted. They type the true count if it is wrong and press **Confirm**. That confirmed
count is the training label for the next version. A business with no model of its own
still saves photos and counts, so it builds its training set from day one.

### How it works

```
photo ─► novaxis_core.vision.load_image (upright, resized to 192x256, normalised)
      ─► CountNet (convolutional network) ─► density map (24x32)
      ─► count = sum of the map; dots = local peaks of the map
```

- **Density-map counting**, the standard approach for many similar objects close
  together. The network does not draw boxes; it spreads one unit of "mass" over each
  item, and the total is the count. This copes with items touching or partly hidden.
- **Labels:** a count per photo is enough. A click on each item's centre (`points` in
  `labels.jsonl`) teaches it faster. See `packages/ml/novaxis_ml/stock/data.py`.
- **Two network sizes:**
  - `tiny`: 128k weights, trains from scratch on a CPU;
  - `mobilenet`: MobileNetV3-small layers pretrained on ImageNet, plus the same counting
    head. **Use this for real photos**: a network that already knows shapes needs far
    fewer labelled photos. Its weights download on first use (Colab or a laptop).
- **Serving:** training exports ONNX. The API runs it with ONNX Runtime (about 20 MB)
  rather than PyTorch (several GB). A test checks ONNX Runtime and PyTorch agree to 1e-4.

### What is live now

The repo ships a `tiny` counter trained on 1,500 **synthetic** shelf photos (drawn cans
and boxes on shelves). Results on 225 held-out photos:

| | Counter | Always guess the average |
|---|---|---|
| Mean absolute error | **0.87 items** | 7.2 items |
| Exactly right | 38% | 3% |
| Within 1 item | **84%** | 6% |
| Within 10% | **97%** | 23% |

Real shelves are harder: glare, depth, stacked rows, products hidden behind others. **These
numbers say nothing about real photos.** The synthetic counter is only used for `demo-*`
businesses, labelled as a demo; real businesses get no automatic count until a model
trained on real photos is shipped. (Tests: `test_a_synthetic_counter_is_only_used_for_demo_businesses`,
`test_a_real_business_collects_labels_before_any_model_exists`.)

### Training on real photos

1. Collect about 200 or more confirmed photos per kind of shelf (Stock page, or your own
   folder in the `labels.jsonl` format). Photos need durable storage to be exported (fault
   E2: set the Supabase service key).
2. `uv run python -m novaxis_ml.stock.export --out photos/`
3. Where PyTorch is installed (`pip install -r packages/ml/stock-requirements.txt`; Colab
   has it):
   `python -m novaxis_ml.stock.train --data photos/ --out stock_counter --size mobilenet --pretrained --epochs 40`
4. Read the report. Ship only if the counter clearly beats "always guess the average" on
   held-out photos, and the error is small enough for the business's use.
5. Copy `stock_counter.onnx` and `stock_counter.json` into
   `packages/core/novaxis_core/ml_models/`, commit, deploy. A model trained on `real` data
   serves every business.

To try the synthetic pipeline yourself:
`python -m novaxis_ml.stock.synthetic --out shelves --n 1500`, then
`python -m novaxis_ml.stock.train --data shelves --out stock_counter --epochs 12 --synthetic`
(about 7 minutes on a 4-core CPU).

**Not yet built:** one model per product, reading prices or labels, stock levels over time
and reorder alerts. The confirmed counts table (`stock_counts`) is the base for all of them.

## 8. Approval learning: will staff approve this as written?

Every decision in the approval queue is a free label: **Approve = 1, Edit or Reject = 0**
(an edit means the proposal was not right as it stood). The model learns which proposals
a business's staff accept, so they can see it at a glance, and so that one day a
business could choose to let the safest ones through on their own. **Today it is advice
only: the model approves nothing.**

Code: inputs `packages/core/novaxis_core/approval_features.py` (shared by training and
scoring), live scoring and the shadow report `approval_model.py`, training
`packages/ml/novaxis_ml/approvals.py`.

**Inputs (no personal data, no message text):** the kind of action, why the gate held it
(default, the trade's rule, the business's own rule), who proposed it (the model, intake,
a follow-up), the channel and trade, the text's length and whether it mentions money or
a day or time, when it was proposed, the conversation's length, and this business's past
approval rate for this kind. The rate counts only decisions made **before** the proposal
existed (tested), and starts at 50% with no history.

**When it runs:** when a proposal starts waiting, its guess is stored on it
(`action_proposals.prediction`, migration 0017) and shown on the Approvals page with its
reasons ("+ this business approved 90% of these before", "- mentions money"). If the model
fails, the proposal still reaches staff (tested).

**Shadow report** (Approvals page, "What the approval model has learnt";
`GET /approvals/learning`): of the proposals staff decided that had a guess, how often
the guess matched, and for confidence 80/90/95%: how many it would have approved and how
many of those staff did not approve. Guesses are stored before the decision, so this is
an honest test, not hindsight.

**Evaluation when training** (most recent 20% of decisions held out): AUC and Brier score,
gradient boosting as a challenger, **"history only"** (the business's own approval rate)
as the baseline to beat, and **precision at 80/90/95%**. If the model cannot beat history
only, the report says "do not rely on it".

Synthetic run (3,000 decisions with planted effects, `make ml-train-approvals-synthetic`):

| | AUC |
|---|---|
| Logistic regression (shipped) | 0.784 |
| Gradient boosting (challenger) | 0.758 |
| History only (baseline) | 0.722 |

At 90% confidence it would have approved 6% of the queue and been right **86%** of the
time: nowhere near good enough to approve anything. That is the point of the report.

**Before anyone lets it approve anything** (a founder decision, not a setting):
1. trained on at least a few hundred real decisions for that business;
2. the shadow report on *new* decisions (not training data) shows at least 99% right at the
   chosen confidence, over at least 100 proposals;
3. only for kinds whose floor is already low (never cancellations, reschedules, prices,
   payments, or anything the core rules raise), owner opt-in per kind, every automatic
   approval logged and reversible, and switched off the moment the shadow report dips.

Commands:
- `make ml-train-approvals-synthetic`: prove the pipeline.
- `make ml-train-approvals`: train on real decisions (needs 200 decisions, 20 of each
  outcome). A model trained on `real` data serves every business; a synthetic one only
  demo-* businesses.
- `make ml-export-approvals`: the training table as CSV.

