#!/bin/bash
# Removes duplicate stories, every hour (ax-news-dedup.timer). DATABASE_URL
# comes from backend/.env (EnvironmentFile in ax-news-dedup.service), and
# the output goes to /var/log/ax-news/dedup.log.
#
# A duplicate, for one owner (the shared feed, or one account's own sources),
# is a later copy:
# - of the same address: a feed followed under two names, the same paper in
#   several arXiv lists, a feed that renews the ids of its items;
# - of the same title from the same source, published within 12 hours (the
#   address changed by a tracking parameter). The same title a day or weeks
#   later is a new story, a daily or weekly column: it stays.
# The first copy stays. A copy someone saved, or a note points to, stays.
# A date in the future (a feed's wrong time zone) becomes the time the story
# arrived; it used to be deleted.
set -euo pipefail
: "${DATABASE_URL:?DATABASE_URL is not set}"

echo "$(date -u '+%F %T') dedup"
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -qAt <<'SQL'
BEGIN;
WITH by_url AS (
    SELECT id, row_number() OVER (PARTITION BY coalesce(owner_user_id, 0), url ORDER BY id) AS rn
      FROM articles
     WHERE url IS NOT NULL AND url <> ''
), by_title AS (
    SELECT id, published_at, row_number() OVER w AS rn, first_value(published_at) OVER w AS first_published
      FROM articles
    WINDOW w AS (PARTITION BY coalesce(owner_user_id, 0), feed_source, lower(trim(title)) ORDER BY id)
), copies AS (
    SELECT id FROM by_url WHERE rn > 1
    UNION
    SELECT id FROM by_title
     WHERE rn > 1 AND abs(extract(epoch FROM published_at - first_published)) <= 12 * 3600
), gone AS (
    DELETE FROM articles a USING copies c
     WHERE a.id = c.id
       AND NOT EXISTS (SELECT 1 FROM user_saves s WHERE s.article_id = a.id)
       AND NOT EXISTS (SELECT 1 FROM user_knowledge k WHERE k.source_article = a.id)
    RETURNING a.id
)
SELECT 'duplicates deleted: ' || count(*) FROM gone;
WITH fixed AS (
    UPDATE articles SET published_at = ingested_at
     WHERE published_at > now() + interval '15 minutes' AND ingested_at IS NOT NULL
    RETURNING id
)
SELECT 'future dates set to arrival: ' || count(*) FROM fixed;
COMMIT;
SELECT 'stories: ' || count(*) FROM articles;
SQL
