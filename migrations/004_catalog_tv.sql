-- Migration 004: the world feed catalog, TV screens, a language per source.
-- Applied: with tv-rework. Additive only: the code before it runs unchanged
-- on a database that has it.
--
-- feed_catalog: every feed AX-NEWS offers (catalog/feeds.json, loaded at
-- start-up). active: fetched for everyone — by FreshRSS (provider
-- 'freshrss', the shared tech feeds) or by sources-worker.py through a
-- user_feeds row without an owner (provider 'catalog', shared by an admin).
-- An account follows a catalog feed through its own user_feeds row
-- (catalog_id), like any source it adds.

CREATE TABLE IF NOT EXISTS feed_catalog (
    id          serial PRIMARY KEY,
    url         text NOT NULL UNIQUE,
    title       text NOT NULL,
    site_url    text,
    category    text NOT NULL,
    domain      text NOT NULL,
    lang        text NOT NULL DEFAULT 'en',
    region      text,
    provider    text NOT NULL DEFAULT 'catalog',
    active      boolean NOT NULL DEFAULT false,
    items       integer NOT NULL DEFAULT 0,
    newest      timestamptz,
    checked_at  timestamptz,
    listed      boolean NOT NULL DEFAULT true,   -- still in catalog/feeds.json
    updated_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS feed_catalog_domain_idx ON feed_catalog (domain, category);

ALTER TABLE user_feeds
    ADD COLUMN IF NOT EXISTS catalog_id integer REFERENCES feed_catalog(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS lang       text;
-- One shared (ownerless) row per catalog feed.
CREATE UNIQUE INDEX IF NOT EXISTS user_feeds_shared_catalog_idx
    ON user_feeds (catalog_id) WHERE user_id IS NULL;

-- A TV screen: an account's choice of topics, layout and theme, shown at
-- /tv/<token> on a screen nobody signs in to. The token is the only key:
-- whoever has the address sees what the screen shows (the account's own
-- sources included, if it says so) and nothing else.
CREATE TABLE IF NOT EXISTS tv_screens (
    id          serial PRIMARY KEY,
    user_id     integer NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token       text NOT NULL UNIQUE,
    name        text NOT NULL,
    config      jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now(),
    last_seen_at timestamptz,
    last_seen_ua text
);
CREATE INDEX IF NOT EXISTS tv_screens_user_idx ON tv_screens (user_id);

-- Startup bookkeeping (the catalog file's hash, so it is loaded once).
CREATE TABLE IF NOT EXISTS app_meta (
    key   text PRIMARY KEY,
    value text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);
