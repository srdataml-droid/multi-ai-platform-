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
| Stock counting from photos | Photos with the true count | A neural network (object detection), trained on a GPU (Colab). Check the detector's licence: some popular ones are AGPL |
