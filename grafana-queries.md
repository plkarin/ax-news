# AX-NEWS Grafana Dashboard Queries
## Datasource: PostgreSQL → 192.168.1.105:5432 / ax_news

### Panel 1 — Active users last 24h (Stat)
SELECT COUNT(DISTINCT username) as "Active Users"
FROM access_logs
WHERE created_at > NOW() - INTERVAL '24 hours'
AND username IS NOT NULL;

### Panel 2 — Connections by IP (Table)
SELECT ip_address, username, COUNT(*) as requests,
       MAX(created_at) as last_seen
FROM access_logs
WHERE created_at > $__timeFrom()::timestamptz
GROUP BY ip_address, username
ORDER BY requests DESC
LIMIT 20;

### Panel 3 — Articles read per user (Bar chart)
SELECT username, COUNT(*) as articles_read
FROM access_logs
WHERE endpoint LIKE '/api/articles/%'
AND method = 'GET'
AND username IS NOT NULL
AND created_at > $__timeFrom()::timestamptz
GROUP BY username
ORDER BY articles_read DESC;

### Panel 4 — Top categories (Bar chart)
SELECT a.category, COUNT(*) as views
FROM access_logs al
JOIN articles a ON a.id = al.article_id
WHERE al.created_at > $__timeFrom()::timestamptz
AND al.article_id IS NOT NULL
GROUP BY a.category
ORDER BY views DESC
LIMIT 10;

### Panel 5 — API response time (Time series)
SELECT
  date_trunc('minute', created_at) as time,
  AVG(duration_ms) as "Avg ms",
  MAX(duration_ms) as "Max ms"
FROM access_logs
WHERE created_at > $__timeFrom()::timestamptz
GROUP BY 1 ORDER BY 1;

### Panel 6 — Requests per minute (Time series)
SELECT
  date_trunc('minute', created_at) as time,
  COUNT(*) as requests
FROM access_logs
WHERE created_at > $__timeFrom()::timestamptz
GROUP BY 1 ORDER BY 1;

### Panel 7 — Total users (Stat)
SELECT COUNT(*) as "Total Users" FROM users;

### Panel 8 — Total articles (Stat)
SELECT COUNT(*) as "Total Articles"
FROM articles WHERE published_at <= NOW();

### Panel 9 — Articles translated today (Stat)
SELECT COUNT(*) as "Translated Today"
FROM articles
WHERE translated_at > NOW() - INTERVAL '24 hours'
AND original_lang != 'en';

### Panel 10 — Error rate (Time series)
SELECT
  date_trunc('minute', created_at) as time,
  COUNT(*) FILTER (WHERE status_code >= 400) as errors,
  COUNT(*) as total
FROM access_logs
WHERE created_at > $__timeFrom()::timestamptz
GROUP BY 1 ORDER BY 1;
