# Runbook

What to do when something is wrong with the live service. Hosting is described in ADR 0013.

| Piece | Where |
|---|---|
| Dashboard | Vercel project `novaxis-web`, https://novaxis-web.vercel.app |
| API | Vercel project `novaxis-api`, https://novaxis-api.vercel.app |
| Database | Supabase project `novaxis-worker` (London) |
| Timer | Supabase `cron.job` named `novaxis-tick`, every minute, `POST /internal/tick` |
| Timer secret | Supabase Vault secret `novaxis_cron_secret`, equal to Vercel `NOVAXIS_CRON_SECRET` |
| Health monitor | `.github/workflows/monitor.yml`, every 15 minutes |

## 1. How you find out

- **The monitor fails.** GitHub emails the repository owner when a scheduled workflow run
  fails. Open the failed run: the first step prints the `/health/deep` body, which names the
  failing check.
- **A staff push alert** from a business ("could not send", "needs a person").
- **The operator console** (`/operator`) lists businesses with problems: worker off, alerts
  off, failed or waiting jobs, bridge or calendar trouble, billing state.

GitHub turns scheduled workflows off after 60 days without a commit on a public repository.
If the monitor stops appearing in the Actions tab, re-enable it there.

## 2. Reading `/health/deep`

`curl https://novaxis-api.vercel.app/health/deep` returns 200 when every check passes and
503 otherwise. Each check has `ok` and a detail.

| Check | Means | First action |
|---|---|---|
| `database` | The API cannot reach Postgres | Supabase dashboard: project status, then the pooler. Check `NOVAXIS_DATABASE_URL` was not changed |
| `schema_current` | The database is behind the deployed code | Cold start migration failed. Read the API runtime logs for the Alembic error. `POST /internal/migrate` with the cron secret runs it by hand |
| `stuck_jobs` | Jobs queued for more than 15 minutes for businesses whose worker is on | The timer is not running or every tick fails. Go to section 3 |
| `failed_jobs_last_hour` | Jobs gave up after their retries | Query `jobs` where `state = 'failed'` for `last_error`. One business: look at its settings. All businesses: a deploy broke something, go to section 5 |
| `emergency_alerts_not_delivered_24h` | An emergency reached us but no staff member was told | Most urgent. Phone the business. Then check that business has push alerts on (Settings, Alerts) and an on-call contact |

## 3. The timer

Recent runs, newest first (Supabase SQL editor):

```sql
select status_code, left(content::text, 200), created
from net._http_response order by created desc limit 10;
```

- `401`: the Vault secret and `NOVAXIS_CRON_SECRET` differ. Section 4.
- `500`: the job loop crashed. API runtime logs for `/internal/tick`.
- No rows for minutes: `select * from cron.job_run_details order by start_time desc limit 5;`
  and confirm `cron.job` `novaxis-tick` is `active`.

## 4. Rotating the timer secret

1. Generate a value: `python -c "import secrets; print(secrets.token_urlsafe(32))"`.
2. Vercel `novaxis-api`, Settings, Environment Variables: set `NOVAXIS_CRON_SECRET`.
3. Supabase SQL editor:
   `select vault.update_secret((select id from vault.secrets where name = 'novaxis_cron_secret'), '<value>');`
4. Redeploy `novaxis-api` so the new value is live.

Between steps 3 and 4 one or two ticks return 401. That is expected. Nothing is lost: the
next tick picks the jobs up.

## 5. A deploy broke production

1. Vercel `novaxis-api` (or `novaxis-web`), Deployments: pick the last good deployment,
   **Instant Rollback**.
2. Migrations are additive, so rolled-back code runs against the newer schema. Do not
   downgrade the database.
3. Fix forward on `main`. CI must pass before the fix reaches production (section 6).

## 6. How code reaches production

CI (`.github/workflows/ci.yml`) runs lint, types, unit, RLS and browser tests on every push.
When all pass on `main`, the `promote` job fast-forwards the `production` branch to that
commit.

This gates the live site only if each Vercel project deploys production from `production`.
Set it once per project: Vercel project, Settings, Environments, Production, Branch
Tracking, branch `production`. Until then every push to `main` goes live before its tests
finish.

## 7. Stopping the AI

- **One business**: the owner (or the operator, acting as that business from the operator
  console) unticks "Worker enabled" in Settings. Automated sends stop within one job cycle.
  Staff can still reply by hand.
- **Everyone**: set `NOVAXIS_INLINE_WORKER=false` on `novaxis-api` and redeploy, and
  `select cron.alter_job((select jobid from cron.job where jobname = 'novaxis-tick'), active := false);`
  Jobs queue up and run when both are turned back on.

## 8. Time limits

A Vercel function run has a maximum duration [VERIFY the current default and maximum for
this plan in Vercel's function duration docs]. These keep a job inside it:

| Variable (Vercel `novaxis-api`) | Value | Why |
|---|---|---|
| `NOVAXIS_LLM_TIMEOUT_SECONDS` | 20 | One model call |
| `NOVAXIS_LLM_MAX_RETRIES` | 1 | At most two calls per step |
| `NOVAXIS_WORKER_LEASE_SECONDS` | 180 | A job cut off with its function is retried after 3 minutes |

The tick drains jobs for up to 40 seconds and a request drains for up to 20 seconds
(`NOVAXIS_INLINE_WORKER_BUDGET_SECONDS`). A job started near the end of that window can run
past it. The lease must stay longer than the longest single job.
