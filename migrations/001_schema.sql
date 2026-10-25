-- AX-NEWS database schema, as it runs on ax-lab05 (pg_dump --schema-only,
-- 2026-10-25). Load it into an empty database owned by the application user:
--   psql "$DATABASE_URL" -f migrations/001_schema.sql
-- It already contains the columns of later migrations (002).

--
-- PostgreSQL database dump
--


-- Dumped from database version 16.15 (Ubuntu 16.15-0ubuntu0.24.04.1)
-- Dumped by pg_dump version 16.15 (Ubuntu 16.15-0ubuntu0.24.04.1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: access_logs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.access_logs (
    id integer NOT NULL,
    user_id integer,
    username text,
    ip_address text,
    endpoint text,
    method text,
    article_id integer,
    category text,
    user_agent text,
    status_code integer,
    duration_ms double precision,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: access_logs_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.access_logs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: access_logs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.access_logs_id_seq OWNED BY public.access_logs.id;


--
-- Name: architecture_docs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.architecture_docs (
    id integer NOT NULL,
    section text NOT NULL,
    title text NOT NULL,
    content text NOT NULL,
    sort_order integer DEFAULT 0,
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: architecture_docs_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.architecture_docs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: architecture_docs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.architecture_docs_id_seq OWNED BY public.architecture_docs.id;


--
-- Name: article_views; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.article_views (
    id integer NOT NULL,
    article_id integer NOT NULL,
    ip_hash text NOT NULL,
    viewed_at timestamp with time zone DEFAULT now()
);


--
-- Name: article_views_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.article_views_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: article_views_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.article_views_id_seq OWNED BY public.article_views.id;


--
-- Name: articles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.articles (
    id integer NOT NULL,
    freshrss_id text,
    feed_source text,
    category text,
    title text NOT NULL,
    url text,
    published_at timestamp with time zone,
    content_raw text,
    image_url text,
    ingested_at timestamp with time zone DEFAULT now(),
    country_code text,
    entities jsonb DEFAULT '[]'::jsonb,
    sentiment text DEFAULT 'neutral'::text,
    sentiment_score double precision DEFAULT 0.0,
    enriched_at timestamp with time zone,
    original_lang text,
    original_title text,
    original_content text,
    translated_at timestamp with time zone,
    translation_status text DEFAULT 'pending'::text,
    view_count integer DEFAULT 0,
    audio_status character varying(20) DEFAULT 'none'::character varying,
    audio_summary_text text,
    audio_url text,
    audio_duration_seconds integer,
    audio_generated_at timestamp with time zone,
    audio_error text
);


--
-- Name: articles_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.articles_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: articles_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.articles_id_seq OWNED BY public.articles.id;


--
-- Name: claude_sessions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.claude_sessions (
    id integer NOT NULL,
    user_id integer,
    article_id integer,
    messages jsonb DEFAULT '[]'::jsonb NOT NULL,
    knowledge_extracted jsonb DEFAULT '[]'::jsonb,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: claude_sessions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.claude_sessions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: claude_sessions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.claude_sessions_id_seq OWNED BY public.claude_sessions.id;


--
-- Name: tech_stack; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.tech_stack (
    id integer NOT NULL,
    category text NOT NULL,
    name text NOT NULL,
    badge_color text NOT NULL,
    badge_logo text,
    sort_order integer DEFAULT 0
);


--
-- Name: tech_stack_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.tech_stack_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: tech_stack_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.tech_stack_id_seq OWNED BY public.tech_stack.id;


--
-- Name: user_feeds; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_feeds (
    id integer NOT NULL,
    user_id integer,
    freshrss_id text NOT NULL,
    name text NOT NULL,
    url text NOT NULL,
    category text,
    active boolean DEFAULT true,
    added_at timestamp with time zone DEFAULT now()
);


--
-- Name: user_feeds_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.user_feeds_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: user_feeds_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.user_feeds_id_seq OWNED BY public.user_feeds.id;


--
-- Name: user_knowledge; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_knowledge (
    id integer NOT NULL,
    user_id integer,
    domain text NOT NULL,
    gap_identified text,
    gap_resolved text,
    source_article integer,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: user_knowledge_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.user_knowledge_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: user_knowledge_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.user_knowledge_id_seq OWNED BY public.user_knowledge.id;


--
-- Name: user_reads; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_reads (
    id integer NOT NULL,
    user_id integer,
    article_id integer,
    read_at timestamp with time zone DEFAULT now()
);


--
-- Name: user_reads_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.user_reads_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: user_reads_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.user_reads_id_seq OWNED BY public.user_reads.id;


--
-- Name: user_sessions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_sessions (
    id text NOT NULL,
    user_id integer,
    created_at timestamp with time zone DEFAULT now(),
    expires_at timestamp with time zone DEFAULT (now() + '30 days'::interval)
);


--
-- Name: users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.users (
    id integer NOT NULL,
    username text NOT NULL,
    email text,
    created_at timestamp with time zone DEFAULT now(),
    password_hash text,
    is_admin boolean DEFAULT false,
    email_verified boolean DEFAULT true,
    approved boolean DEFAULT false,
    approved_at timestamp with time zone,
    approved_by integer
);


--
-- Name: users_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.users_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: users_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.users_id_seq OWNED BY public.users.id;


--
-- Name: access_logs id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.access_logs ALTER COLUMN id SET DEFAULT nextval('public.access_logs_id_seq'::regclass);


--
-- Name: architecture_docs id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.architecture_docs ALTER COLUMN id SET DEFAULT nextval('public.architecture_docs_id_seq'::regclass);


--
-- Name: article_views id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.article_views ALTER COLUMN id SET DEFAULT nextval('public.article_views_id_seq'::regclass);


--
-- Name: articles id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.articles ALTER COLUMN id SET DEFAULT nextval('public.articles_id_seq'::regclass);


--
-- Name: claude_sessions id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.claude_sessions ALTER COLUMN id SET DEFAULT nextval('public.claude_sessions_id_seq'::regclass);


--
-- Name: tech_stack id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tech_stack ALTER COLUMN id SET DEFAULT nextval('public.tech_stack_id_seq'::regclass);


--
-- Name: user_feeds id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_feeds ALTER COLUMN id SET DEFAULT nextval('public.user_feeds_id_seq'::regclass);


--
-- Name: user_knowledge id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_knowledge ALTER COLUMN id SET DEFAULT nextval('public.user_knowledge_id_seq'::regclass);


--
-- Name: user_reads id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_reads ALTER COLUMN id SET DEFAULT nextval('public.user_reads_id_seq'::regclass);


--
-- Name: users id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users ALTER COLUMN id SET DEFAULT nextval('public.users_id_seq'::regclass);


--
-- Name: access_logs access_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.access_logs
    ADD CONSTRAINT access_logs_pkey PRIMARY KEY (id);


--
-- Name: architecture_docs architecture_docs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.architecture_docs
    ADD CONSTRAINT architecture_docs_pkey PRIMARY KEY (id);


--
-- Name: article_views article_views_article_id_ip_hash_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.article_views
    ADD CONSTRAINT article_views_article_id_ip_hash_key UNIQUE (article_id, ip_hash);


--
-- Name: article_views article_views_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.article_views
    ADD CONSTRAINT article_views_pkey PRIMARY KEY (id);


--
-- Name: articles articles_freshrss_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.articles
    ADD CONSTRAINT articles_freshrss_id_key UNIQUE (freshrss_id);


--
-- Name: articles articles_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.articles
    ADD CONSTRAINT articles_pkey PRIMARY KEY (id);


--
-- Name: claude_sessions claude_sessions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.claude_sessions
    ADD CONSTRAINT claude_sessions_pkey PRIMARY KEY (id);


--
-- Name: tech_stack tech_stack_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tech_stack
    ADD CONSTRAINT tech_stack_pkey PRIMARY KEY (id);


--
-- Name: user_feeds user_feeds_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_feeds
    ADD CONSTRAINT user_feeds_pkey PRIMARY KEY (id);


--
-- Name: user_feeds user_feeds_user_id_freshrss_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_feeds
    ADD CONSTRAINT user_feeds_user_id_freshrss_id_key UNIQUE (user_id, freshrss_id);


--
-- Name: user_knowledge user_knowledge_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_knowledge
    ADD CONSTRAINT user_knowledge_pkey PRIMARY KEY (id);


--
-- Name: user_reads user_reads_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_reads
    ADD CONSTRAINT user_reads_pkey PRIMARY KEY (id);


--
-- Name: user_reads user_reads_user_id_article_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_reads
    ADD CONSTRAINT user_reads_user_id_article_id_key UNIQUE (user_id, article_id);


--
-- Name: user_sessions user_sessions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_sessions
    ADD CONSTRAINT user_sessions_pkey PRIMARY KEY (id);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: users users_username_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_username_key UNIQUE (username);


--
-- Name: idx_access_logs_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_access_logs_created ON public.access_logs USING btree (created_at DESC);


--
-- Name: idx_access_logs_endpoint; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_access_logs_endpoint ON public.access_logs USING btree (endpoint);


--
-- Name: idx_access_logs_ip; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_access_logs_ip ON public.access_logs USING btree (ip_address);


--
-- Name: idx_access_logs_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_access_logs_user ON public.access_logs USING btree (user_id);


--
-- Name: idx_article_views_article; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_article_views_article ON public.article_views USING btree (article_id);


--
-- Name: idx_articles_category; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_articles_category ON public.articles USING btree (category);


--
-- Name: idx_articles_country; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_articles_country ON public.articles USING btree (country_code);


--
-- Name: idx_articles_enriched; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_articles_enriched ON public.articles USING btree (enriched_at);


--
-- Name: idx_articles_entities; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_articles_entities ON public.articles USING gin (entities);


--
-- Name: idx_articles_freshrss_id_unique; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX idx_articles_freshrss_id_unique ON public.articles USING btree (freshrss_id) WHERE (freshrss_id IS NOT NULL);


--
-- Name: idx_articles_freshrss_unique; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX idx_articles_freshrss_unique ON public.articles USING btree (freshrss_id) WHERE (freshrss_id IS NOT NULL);


--
-- Name: idx_articles_lang; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_articles_lang ON public.articles USING btree (original_lang);


--
-- Name: idx_articles_published; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_articles_published ON public.articles USING btree (published_at DESC);


--
-- Name: idx_articles_sentiment; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_articles_sentiment ON public.articles USING btree (sentiment);


--
-- Name: idx_articles_title_source; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_articles_title_source ON public.articles USING btree (lower(TRIM(BOTH FROM title)), feed_source);


--
-- Name: idx_articles_translated; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_articles_translated ON public.articles USING btree (translated_at);


--
-- Name: idx_articles_translation_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_articles_translation_status ON public.articles USING btree (translation_status);


--
-- Name: idx_sessions_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_sessions_user ON public.user_sessions USING btree (user_id);


--
-- Name: idx_sessions_user_art; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_sessions_user_art ON public.claude_sessions USING btree (user_id, article_id);


--
-- Name: idx_user_feeds_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_user_feeds_user ON public.user_feeds USING btree (user_id);


--
-- Name: idx_user_reads_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_user_reads_user ON public.user_reads USING btree (user_id);


--
-- Name: idx_users_email; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX idx_users_email ON public.users USING btree (email) WHERE (email IS NOT NULL);


--
-- Name: idx_users_email_unique; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX idx_users_email_unique ON public.users USING btree (email) WHERE (email IS NOT NULL);


--
-- Name: access_logs access_logs_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.access_logs
    ADD CONSTRAINT access_logs_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: article_views article_views_article_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.article_views
    ADD CONSTRAINT article_views_article_id_fkey FOREIGN KEY (article_id) REFERENCES public.articles(id) ON DELETE CASCADE;


--
-- Name: claude_sessions claude_sessions_article_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.claude_sessions
    ADD CONSTRAINT claude_sessions_article_id_fkey FOREIGN KEY (article_id) REFERENCES public.articles(id) ON DELETE CASCADE;


--
-- Name: claude_sessions claude_sessions_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.claude_sessions
    ADD CONSTRAINT claude_sessions_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: user_feeds user_feeds_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_feeds
    ADD CONSTRAINT user_feeds_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: user_knowledge user_knowledge_source_article_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_knowledge
    ADD CONSTRAINT user_knowledge_source_article_fkey FOREIGN KEY (source_article) REFERENCES public.articles(id);


--
-- Name: user_knowledge user_knowledge_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_knowledge
    ADD CONSTRAINT user_knowledge_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: user_reads user_reads_article_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_reads
    ADD CONSTRAINT user_reads_article_id_fkey FOREIGN KEY (article_id) REFERENCES public.articles(id) ON DELETE CASCADE;


--
-- Name: user_reads user_reads_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_reads
    ADD CONSTRAINT user_reads_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: user_sessions user_sessions_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_sessions
    ADD CONSTRAINT user_sessions_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: users users_approved_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_approved_by_fkey FOREIGN KEY (approved_by) REFERENCES public.users(id);


--
-- PostgreSQL database dump complete
--


