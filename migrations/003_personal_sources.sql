-- Migration 003: personal sources, saved articles, display preferences.
-- Applied: 2026-10-25 (ui-rework). Additive only: the code before it runs
-- unchanged on a database that has it.
--
-- An account's own sources (user_feeds) are fetched by sources-worker.py
-- and their articles stored with owner_user_id set: they are that account's
-- alone, never in the public feed, the sitemaps or the TV.

ALTER TABLE user_feeds
    ADD COLUMN IF NOT EXISTS kind            text DEFAULT 'rss',
    ADD COLUMN IF NOT EXISTS site_url        text,
    ADD COLUMN IF NOT EXISTS etag            text,
    ADD COLUMN IF NOT EXISTS last_modified   text,
    ADD COLUMN IF NOT EXISTS last_fetched_at timestamptz,
    ADD COLUMN IF NOT EXISTS last_ok_at      timestamptz,
    ADD COLUMN IF NOT EXISTS last_error      text,
    ADD COLUMN IF NOT EXISTS error_count     integer DEFAULT 0,
    ADD COLUMN IF NOT EXISTS item_count      integer DEFAULT 0;

ALTER TABLE articles
    ADD COLUMN IF NOT EXISTS owner_user_id integer REFERENCES users(id) ON DELETE CASCADE,
    ADD COLUMN IF NOT EXISTS user_feed_id  integer REFERENCES user_feeds(id) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS articles_owner_published_idx
    ON articles (owner_user_id, published_at DESC) WHERE owner_user_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS articles_user_feed_idx
    ON articles (user_feed_id) WHERE user_feed_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS user_saves (
    user_id    integer NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    article_id integer NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    saved_at   timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, article_id)
);

CREATE TABLE IF NOT EXISTS user_prefs (
    user_id    integer PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    prefs      jsonb NOT NULL DEFAULT '{}'::jsonb,
    updated_at timestamptz NOT NULL DEFAULT now()
);
