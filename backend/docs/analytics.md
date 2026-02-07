# Business Usage Analytics (Local DB)

## DB Schema

Table: `analytics_events` (stored in the existing SQLite DB configured by `USAGE_DB_PATH`)

```sql
CREATE TABLE IF NOT EXISTS analytics_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    event_name TEXT NOT NULL,            -- "transform_job"
    user_id_hash TEXT NOT NULL,          -- sha256(user_id) prefix, no raw user id
    plan_tier TEXT NOT NULL,             -- placeholder: "free" / "pro"
    transformation_type TEXT NOT NULL,   -- clean / group / merge / mixed / other
    operation_count INTEGER NOT NULL,
    file_size_bytes INTEGER,
    processing_ms INTEGER NOT NULL,
    status TEXT NOT NULL,                -- success / error
    error_code TEXT,                     -- null for success
    output_format TEXT                   -- csv / xlsx
);
```

## Backend Hook

Hook point: `POST /api/transform` (`backend/app/routers/transform.py`)

Captured per job:
- `transformation_type` (from plan operations)
- `file_size_bytes` (from upload metadata)
- `processing_ms` (wall-clock elapsed time)
- `status` + `error_code`
- `plan_tier` (currently placeholder: `free`)

Notes:
- No file content is stored.
- No external analytics service is used.
- Logging failures are swallowed to keep request path performance-safe.

## Example Analysis Queries

### 1) Success rate by transformation type
```sql
SELECT
  transformation_type,
  COUNT(*) AS total_jobs,
  SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) AS success_jobs,
  ROUND(
    100.0 * SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) / COUNT(*),
    2
  ) AS success_rate_pct
FROM analytics_events
GROUP BY transformation_type
ORDER BY total_jobs DESC;
```

### 2) Median-ish processing time proxy (p50 approx via avg) and p95-like max by type
```sql
SELECT
  transformation_type,
  AVG(processing_ms) AS avg_processing_ms,
  MAX(processing_ms) AS max_processing_ms
FROM analytics_events
WHERE status = 'success'
GROUP BY transformation_type
ORDER BY avg_processing_ms DESC;
```

### 3) Daily funnel free vs pro placeholder
```sql
SELECT
  DATE(created_at) AS day,
  plan_tier,
  COUNT(*) AS total_jobs,
  SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) AS success_jobs,
  SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) AS error_jobs
FROM analytics_events
GROUP BY DATE(created_at), plan_tier
ORDER BY day DESC, plan_tier;
```
