-- ═══════════════════════════════════════════════════════════════
-- TRADING BOT DATABASE SCHEMA - FULL INITIALIZATION
-- Created: 2025-10-27
-- PostgreSQL 15.x+
-- ═══════════════════════════════════════════════════════════════
--
-- This script creates the complete database structure from scratch:
--
-- SCHEMAS:
--   - monitoring: Main operational schema (12 tables)
--   - public: Functions and triggers
--
-- TABLES (monitoring schema):
--   1. positions - Active and historical positions
--   2. orders - Order execution history
--   3. trades - Completed trades
--   4. trailing_stop_state - Trailing stop management
--   5. orders_cache - Orders cache for fast access
--   6. aged_positions - Aged positions tracking
--   7. aged_monitoring_events - Aged position events
--   8. risk_events - Risk management events
--   9. risk_violations - Risk limit violations
--  10. events - Main event log
--  11. event_performance_metrics - Performance metrics
--  12. transaction_log - Audit transaction log
--
-- FUNCTIONS:
--   - normalize_trailing_stop_side() - Auto-lowercase side column
--   - update_updated_at_column() - Auto-update timestamps
--
-- TRIGGERS:
--   - normalize_side_trigger - On trailing_stop_state
--   - update_positions_updated_at - On positions
--   - update_trades_updated_at - On trades
--
-- INDEXES: 30+ indexes for optimal query performance
--
-- Usage:
--   createdb fox_crypto
--   psql -U username -d fox_crypto -f 001_init_schema.sql
--
-- ═══════════════════════════════════════════════════════════════

--
-- PostgreSQL database dump
--

\restrict XO6pF4P3zcHAfWi2Bdyx9QnvzxWA1grOoQpTyt3OaNTd2N6c4BtCBpWbeLmCnA4

-- Dumped from database version 15.13 (Homebrew)
-- Dumped by pg_dump version 18.0

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: monitoring; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA monitoring;


--
-- Name: normalize_trailing_stop_side(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.normalize_trailing_stop_side() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    -- Автоматически приводим side к lowercase
    IF NEW.side IS NOT NULL THEN
        NEW.side := LOWER(NEW.side);
    END IF;
    RETURN NEW;
END;
$$;


--
-- Name: update_updated_at_column(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.update_updated_at_column() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;


--
-- Name: FUNCTION update_updated_at_column(); Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON FUNCTION public.update_updated_at_column() IS 'Trigger function to automatically set updated_at = NOW() on UPDATE. Used by multiple triggers in monitoring schema.';


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: aged_monitoring_events; Type: TABLE; Schema: monitoring; Owner: -
--

CREATE TABLE monitoring.aged_monitoring_events (
    id integer NOT NULL,
    aged_position_id character varying(255) NOT NULL,
    event_type character varying(50) NOT NULL,
    market_price numeric(20,8),
    target_price numeric(20,8),
    price_distance_percent numeric(10,4),
    action_taken character varying(100),
    success boolean,
    error_message text,
    event_metadata jsonb,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: TABLE aged_monitoring_events; Type: COMMENT; Schema: monitoring; Owner: -
--

COMMENT ON TABLE monitoring.aged_monitoring_events IS 'Aged position monitoring events - moved from public schema on 2025-10-24';


--
-- Name: aged_monitoring_events_id_seq; Type: SEQUENCE; Schema: monitoring; Owner: -
--

CREATE SEQUENCE monitoring.aged_monitoring_events_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: aged_monitoring_events_id_seq; Type: SEQUENCE OWNED BY; Schema: monitoring; Owner: -
--

ALTER SEQUENCE monitoring.aged_monitoring_events_id_seq OWNED BY monitoring.aged_monitoring_events.id;


--
-- Name: aged_positions; Type: TABLE; Schema: monitoring; Owner: -
--

CREATE TABLE monitoring.aged_positions (
    id integer NOT NULL,
    position_id character varying(255) NOT NULL,
    symbol character varying(50) NOT NULL,
    exchange character varying(50) NOT NULL,
    entry_price numeric(20,8) NOT NULL,
    target_price numeric(20,8) NOT NULL,
    phase character varying(50) NOT NULL,
    hours_aged integer NOT NULL,
    loss_tolerance numeric(10,4),
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: TABLE aged_positions; Type: COMMENT; Schema: monitoring; Owner: -
--

COMMENT ON TABLE monitoring.aged_positions IS 'Aged positions tracking - moved from public schema on 2025-10-24';


--
-- Name: aged_positions_id_seq; Type: SEQUENCE; Schema: monitoring; Owner: -
--

CREATE SEQUENCE monitoring.aged_positions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: aged_positions_id_seq; Type: SEQUENCE OWNED BY; Schema: monitoring; Owner: -
--

ALTER SEQUENCE monitoring.aged_positions_id_seq OWNED BY monitoring.aged_positions.id;


--
-- Name: event_performance_metrics; Type: TABLE; Schema: monitoring; Owner: -
--

CREATE TABLE monitoring.event_performance_metrics (
    id integer NOT NULL,
    metric_name character varying(100),
    metric_value numeric(20,8),
    tags jsonb,
    recorded_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: TABLE event_performance_metrics; Type: COMMENT; Schema: monitoring; Owner: -
--

COMMENT ON TABLE monitoring.event_performance_metrics IS 'Real-time EventLogger performance metrics. Currently unused in production.';


--
-- Name: COLUMN event_performance_metrics.tags; Type: COMMENT; Schema: monitoring; Owner: -
--

COMMENT ON COLUMN monitoring.event_performance_metrics.tags IS 'JSONB for flexible metric dimensions (e.g., {"exchange": "bybit"})';


--
-- Name: event_performance_metrics_id_seq; Type: SEQUENCE; Schema: monitoring; Owner: -
--

CREATE SEQUENCE monitoring.event_performance_metrics_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: event_performance_metrics_id_seq; Type: SEQUENCE OWNED BY; Schema: monitoring; Owner: -
--

ALTER SEQUENCE monitoring.event_performance_metrics_id_seq OWNED BY monitoring.event_performance_metrics.id;


--
-- Name: events; Type: TABLE; Schema: monitoring; Owner: -
--

CREATE TABLE monitoring.events (
    id integer NOT NULL,
    event_type character varying(50) NOT NULL,
    event_data jsonb,
    correlation_id character varying(100),
    position_id integer,
    order_id character varying(100),
    symbol character varying(50),
    exchange character varying(50),
    severity character varying(20) DEFAULT 'INFO'::character varying,
    error_message text,
    stack_trace text,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: TABLE events; Type: COMMENT; Schema: monitoring; Owner: -
--

COMMENT ON TABLE monitoring.events IS 'Event audit trail for all critical bot operations. Stores 69 event types across 7 components.';


--
-- Name: COLUMN events.event_type; Type: COMMENT; Schema: monitoring; Owner: -
--

COMMENT ON COLUMN monitoring.events.event_type IS 'Type from EventType enum (e.g., position_created, stop_loss_placed, wave_detected)';


--
-- Name: COLUMN events.event_data; Type: COMMENT; Schema: monitoring; Owner: -
--

COMMENT ON COLUMN monitoring.events.event_data IS 'JSONB payload with event-specific data';


--
-- Name: COLUMN events.correlation_id; Type: COMMENT; Schema: monitoring; Owner: -
--

COMMENT ON COLUMN monitoring.events.correlation_id IS 'Groups related events in atomic operations';


--
-- Name: COLUMN events.position_id; Type: COMMENT; Schema: monitoring; Owner: -
--

COMMENT ON COLUMN monitoring.events.position_id IS 'Soft FK to monitoring.positions.id (no constraint)';


--
-- Name: COLUMN events.severity; Type: COMMENT; Schema: monitoring; Owner: -
--

COMMENT ON COLUMN monitoring.events.severity IS 'INFO, WARNING, ERROR, or CRITICAL';


--
-- Name: events_id_seq; Type: SEQUENCE; Schema: monitoring; Owner: -
--

CREATE SEQUENCE monitoring.events_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: events_id_seq; Type: SEQUENCE OWNED BY; Schema: monitoring; Owner: -
--

ALTER SEQUENCE monitoring.events_id_seq OWNED BY monitoring.events.id;


--
-- Name: orders; Type: TABLE; Schema: monitoring; Owner: -
--

CREATE TABLE monitoring.orders (
    id integer NOT NULL,
    position_id character varying(100),
    exchange character varying(50) NOT NULL,
    symbol character varying(20) NOT NULL,
    order_id character varying(100),
    client_order_id character varying(100),
    type character varying(20) NOT NULL,
    side character varying(10) NOT NULL,
    size numeric(20,8),
    price numeric(20,8),
    status character varying(20) NOT NULL,
    filled numeric(20,8) DEFAULT 0,
    remaining numeric(20,8),
    fee numeric(20,8),
    fee_currency character varying(10),
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: orders_cache; Type: TABLE; Schema: monitoring; Owner: -
--

CREATE TABLE monitoring.orders_cache (
    id integer NOT NULL,
    exchange character varying(50) NOT NULL,
    exchange_order_id character varying(100) NOT NULL,
    symbol character varying(50) NOT NULL,
    order_type character varying(20) NOT NULL,
    side character varying(10) NOT NULL,
    price numeric(20,8),
    amount numeric(20,8) NOT NULL,
    filled numeric(20,8) DEFAULT 0,
    status character varying(20) NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    cached_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    order_data jsonb
);


--
-- Name: orders_cache_id_seq; Type: SEQUENCE; Schema: monitoring; Owner: -
--

CREATE SEQUENCE monitoring.orders_cache_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: orders_cache_id_seq; Type: SEQUENCE OWNED BY; Schema: monitoring; Owner: -
--

ALTER SEQUENCE monitoring.orders_cache_id_seq OWNED BY monitoring.orders_cache.id;


--
-- Name: orders_id_seq; Type: SEQUENCE; Schema: monitoring; Owner: -
--

CREATE SEQUENCE monitoring.orders_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: orders_id_seq; Type: SEQUENCE OWNED BY; Schema: monitoring; Owner: -
--

ALTER SEQUENCE monitoring.orders_id_seq OWNED BY monitoring.orders.id;


--
-- Name: performance_metrics; Type: TABLE; Schema: monitoring; Owner: -
--

CREATE TABLE monitoring.performance_metrics (
    id integer NOT NULL,
    period character varying(20) NOT NULL,
    total_trades integer,
    winning_trades integer,
    losing_trades integer,
    total_pnl numeric(20,8),
    win_rate numeric(5,2),
    profit_factor numeric(10,2),
    sharpe_ratio numeric(10,2),
    max_drawdown numeric(20,8),
    avg_win numeric(20,8),
    avg_loss numeric(20,8),
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: performance_metrics_id_seq; Type: SEQUENCE; Schema: monitoring; Owner: -
--

CREATE SEQUENCE monitoring.performance_metrics_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: performance_metrics_id_seq; Type: SEQUENCE OWNED BY; Schema: monitoring; Owner: -
--

ALTER SEQUENCE monitoring.performance_metrics_id_seq OWNED BY monitoring.performance_metrics.id;


--
-- Name: positions; Type: TABLE; Schema: monitoring; Owner: -
--

CREATE TABLE monitoring.positions (
    id integer NOT NULL,
    signal_id integer,
    symbol character varying(20) NOT NULL,
    exchange character varying(50) NOT NULL,
    side character varying(10) NOT NULL,
    quantity numeric(20,8) NOT NULL,
    entry_price numeric(20,8) NOT NULL,
    current_price numeric(20,8),
    stop_loss_price numeric(20,8),
    take_profit_price numeric(20,8),
    unrealized_pnl numeric(20,8),
    realized_pnl numeric(20,8),
    fees numeric(20,8) DEFAULT 0,
    status character varying(20) DEFAULT 'active'::character varying NOT NULL,
    exit_reason text,
    opened_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    closed_at timestamp with time zone,
    updated_at timestamp with time zone DEFAULT now(),
    leverage numeric(10,2) DEFAULT 1.0,
    stop_loss numeric(20,8),
    take_profit numeric(20,8),
    pnl numeric(20,8),
    pnl_percentage numeric(10,4),
    trailing_activated boolean DEFAULT false,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    error_details jsonb,
    retry_count integer DEFAULT 0,
    last_error_at timestamp with time zone,
    has_trailing_stop boolean DEFAULT true NOT NULL,
    has_stop_loss boolean DEFAULT false,
    exchange_order_id character varying(100)
);


--
-- Name: positions_id_seq; Type: SEQUENCE; Schema: monitoring; Owner: -
--

CREATE SEQUENCE monitoring.positions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: positions_id_seq; Type: SEQUENCE OWNED BY; Schema: monitoring; Owner: -
--

ALTER SEQUENCE monitoring.positions_id_seq OWNED BY monitoring.positions.id;


--
-- Name: risk_events; Type: TABLE; Schema: monitoring; Owner: -
--

CREATE TABLE monitoring.risk_events (
    id integer NOT NULL,
    event_type character varying(50) NOT NULL,
    risk_level character varying(20) NOT NULL,
    position_id character varying(100),
    details jsonb,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: risk_events_id_seq; Type: SEQUENCE; Schema: monitoring; Owner: -
--

CREATE SEQUENCE monitoring.risk_events_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: risk_events_id_seq; Type: SEQUENCE OWNED BY; Schema: monitoring; Owner: -
--

ALTER SEQUENCE monitoring.risk_events_id_seq OWNED BY monitoring.risk_events.id;


--
-- Name: risk_violations; Type: TABLE; Schema: monitoring; Owner: -
--

CREATE TABLE monitoring.risk_violations (
    id integer NOT NULL,
    violation_type character varying(50) NOT NULL,
    risk_level character varying(20) NOT NULL,
    message text,
    "timestamp" timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: risk_violations_id_seq; Type: SEQUENCE; Schema: monitoring; Owner: -
--

CREATE SEQUENCE monitoring.risk_violations_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: risk_violations_id_seq; Type: SEQUENCE OWNED BY; Schema: monitoring; Owner: -
--

ALTER SEQUENCE monitoring.risk_violations_id_seq OWNED BY monitoring.risk_violations.id;


--
-- Name: trades; Type: TABLE; Schema: monitoring; Owner: -
--

CREATE TABLE monitoring.trades (
    id integer NOT NULL,
    signal_id integer,
    symbol character varying(20) NOT NULL,
    exchange character varying(50) NOT NULL,
    side character varying(10) NOT NULL,
    order_type character varying(20),
    quantity numeric(20,8),
    price numeric(20,8),
    executed_qty numeric(20,8),
    average_price numeric(20,8),
    order_id character varying(100),
    client_order_id character varying(100),
    status character varying(20),
    fee numeric(20,8),
    fee_currency character varying(10),
    executed_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: trades_id_seq; Type: SEQUENCE; Schema: monitoring; Owner: -
--

CREATE SEQUENCE monitoring.trades_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: trades_id_seq; Type: SEQUENCE OWNED BY; Schema: monitoring; Owner: -
--

ALTER SEQUENCE monitoring.trades_id_seq OWNED BY monitoring.trades.id;


--
-- Name: trailing_stop_state; Type: TABLE; Schema: monitoring; Owner: -
--

CREATE TABLE monitoring.trailing_stop_state (
    id bigint NOT NULL,
    symbol character varying(50) NOT NULL,
    exchange character varying(50) NOT NULL,
    position_id bigint,
    state character varying(20) DEFAULT 'inactive'::character varying NOT NULL,
    is_activated boolean DEFAULT false NOT NULL,
    highest_price numeric(20,8),
    lowest_price numeric(20,8),
    current_stop_price numeric(20,8),
    stop_order_id character varying(100),
    activation_price numeric(20,8),
    activation_percent numeric(10,4),
    callback_percent numeric(10,4),
    entry_price numeric(20,8) NOT NULL,
    side character varying(10) NOT NULL,
    quantity numeric(20,8) NOT NULL,
    update_count integer DEFAULT 0,
    highest_profit_percent numeric(10,4) DEFAULT 0,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    activated_at timestamp with time zone,
    last_update_time timestamp with time zone,
    last_sl_update_time timestamp with time zone,
    last_updated_sl_price numeric(20,8),
    metadata jsonb,
    last_peak_save_time timestamp with time zone,
    last_saved_peak_price numeric(20,8)
);


--
-- Name: TABLE trailing_stop_state; Type: COMMENT; Schema: monitoring; Owner: -
--

COMMENT ON TABLE monitoring.trailing_stop_state IS 'Persistent storage for Trailing Stop state across bot restarts';


--
-- Name: COLUMN trailing_stop_state.highest_price; Type: COMMENT; Schema: monitoring; Owner: -
--

COMMENT ON COLUMN monitoring.trailing_stop_state.highest_price IS 'Highest price reached (for long positions) - CRITICAL for SL calculation';


--
-- Name: COLUMN trailing_stop_state.lowest_price; Type: COMMENT; Schema: monitoring; Owner: -
--

COMMENT ON COLUMN monitoring.trailing_stop_state.lowest_price IS 'Lowest price reached (for short positions) - CRITICAL for SL calculation';


--
-- Name: COLUMN trailing_stop_state.current_stop_price; Type: COMMENT; Schema: monitoring; Owner: -
--

COMMENT ON COLUMN monitoring.trailing_stop_state.current_stop_price IS 'Current calculated stop loss price';


--
-- Name: COLUMN trailing_stop_state.last_sl_update_time; Type: COMMENT; Schema: monitoring; Owner: -
--

COMMENT ON COLUMN monitoring.trailing_stop_state.last_sl_update_time IS 'Last successful SL update on exchange (for rate limiting)';


--
-- Name: COLUMN trailing_stop_state.last_updated_sl_price; Type: COMMENT; Schema: monitoring; Owner: -
--

COMMENT ON COLUMN monitoring.trailing_stop_state.last_updated_sl_price IS 'Last successfully updated SL price on exchange (for rate limiting)';


--
-- Name: COLUMN trailing_stop_state.last_peak_save_time; Type: COMMENT; Schema: monitoring; Owner: -
--

COMMENT ON COLUMN monitoring.trailing_stop_state.last_peak_save_time IS 'Last time peak price was saved to database (for batching)';


--
-- Name: COLUMN trailing_stop_state.last_saved_peak_price; Type: COMMENT; Schema: monitoring; Owner: -
--

COMMENT ON COLUMN monitoring.trailing_stop_state.last_saved_peak_price IS 'Last saved peak price value (for improvement-based saving)';


--
-- Name: trailing_stop_state_id_seq; Type: SEQUENCE; Schema: monitoring; Owner: -
--

CREATE SEQUENCE monitoring.trailing_stop_state_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: trailing_stop_state_id_seq; Type: SEQUENCE OWNED BY; Schema: monitoring; Owner: -
--

ALTER SEQUENCE monitoring.trailing_stop_state_id_seq OWNED BY monitoring.trailing_stop_state.id;


--
-- Name: transaction_log; Type: TABLE; Schema: monitoring; Owner: -
--

CREATE TABLE monitoring.transaction_log (
    id integer NOT NULL,
    transaction_id character varying(100),
    operation character varying(100),
    status character varying(20),
    started_at timestamp with time zone,
    completed_at timestamp with time zone,
    duration_ms integer,
    affected_rows integer,
    error_message text
);


--
-- Name: TABLE transaction_log; Type: COMMENT; Schema: monitoring; Owner: -
--

COMMENT ON TABLE monitoring.transaction_log IS 'Database transaction performance tracking. Currently unused in production.';


--
-- Name: transaction_log_id_seq; Type: SEQUENCE; Schema: monitoring; Owner: -
--

CREATE SEQUENCE monitoring.transaction_log_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: transaction_log_id_seq; Type: SEQUENCE OWNED BY; Schema: monitoring; Owner: -
--

ALTER SEQUENCE monitoring.transaction_log_id_seq OWNED BY monitoring.transaction_log.id;


--
-- Name: aged_monitoring_events id; Type: DEFAULT; Schema: monitoring; Owner: -
--

ALTER TABLE ONLY monitoring.aged_monitoring_events ALTER COLUMN id SET DEFAULT nextval('monitoring.aged_monitoring_events_id_seq'::regclass);


--
-- Name: aged_positions id; Type: DEFAULT; Schema: monitoring; Owner: -
--

ALTER TABLE ONLY monitoring.aged_positions ALTER COLUMN id SET DEFAULT nextval('monitoring.aged_positions_id_seq'::regclass);


--
-- Name: event_performance_metrics id; Type: DEFAULT; Schema: monitoring; Owner: -
--

ALTER TABLE ONLY monitoring.event_performance_metrics ALTER COLUMN id SET DEFAULT nextval('monitoring.event_performance_metrics_id_seq'::regclass);


--
-- Name: events id; Type: DEFAULT; Schema: monitoring; Owner: -
--

ALTER TABLE ONLY monitoring.events ALTER COLUMN id SET DEFAULT nextval('monitoring.events_id_seq'::regclass);


--
-- Name: orders id; Type: DEFAULT; Schema: monitoring; Owner: -
--

ALTER TABLE ONLY monitoring.orders ALTER COLUMN id SET DEFAULT nextval('monitoring.orders_id_seq'::regclass);


--
-- Name: orders_cache id; Type: DEFAULT; Schema: monitoring; Owner: -
--

ALTER TABLE ONLY monitoring.orders_cache ALTER COLUMN id SET DEFAULT nextval('monitoring.orders_cache_id_seq'::regclass);


--
-- Name: performance_metrics id; Type: DEFAULT; Schema: monitoring; Owner: -
--

ALTER TABLE ONLY monitoring.performance_metrics ALTER COLUMN id SET DEFAULT nextval('monitoring.performance_metrics_id_seq'::regclass);


--
-- Name: positions id; Type: DEFAULT; Schema: monitoring; Owner: -
--

ALTER TABLE ONLY monitoring.positions ALTER COLUMN id SET DEFAULT nextval('monitoring.positions_id_seq'::regclass);


--
-- Name: risk_events id; Type: DEFAULT; Schema: monitoring; Owner: -
--

ALTER TABLE ONLY monitoring.risk_events ALTER COLUMN id SET DEFAULT nextval('monitoring.risk_events_id_seq'::regclass);


--
-- Name: risk_violations id; Type: DEFAULT; Schema: monitoring; Owner: -
--

ALTER TABLE ONLY monitoring.risk_violations ALTER COLUMN id SET DEFAULT nextval('monitoring.risk_violations_id_seq'::regclass);


--
-- Name: trades id; Type: DEFAULT; Schema: monitoring; Owner: -
--

ALTER TABLE ONLY monitoring.trades ALTER COLUMN id SET DEFAULT nextval('monitoring.trades_id_seq'::regclass);


--
-- Name: trailing_stop_state id; Type: DEFAULT; Schema: monitoring; Owner: -
--

ALTER TABLE ONLY monitoring.trailing_stop_state ALTER COLUMN id SET DEFAULT nextval('monitoring.trailing_stop_state_id_seq'::regclass);


--
-- Name: transaction_log id; Type: DEFAULT; Schema: monitoring; Owner: -
--

ALTER TABLE ONLY monitoring.transaction_log ALTER COLUMN id SET DEFAULT nextval('monitoring.transaction_log_id_seq'::regclass);


--
-- Name: aged_monitoring_events aged_monitoring_events_pkey; Type: CONSTRAINT; Schema: monitoring; Owner: -
--

ALTER TABLE ONLY monitoring.aged_monitoring_events
    ADD CONSTRAINT aged_monitoring_events_pkey PRIMARY KEY (id);


--
-- Name: aged_positions aged_positions_pkey; Type: CONSTRAINT; Schema: monitoring; Owner: -
--

ALTER TABLE ONLY monitoring.aged_positions
    ADD CONSTRAINT aged_positions_pkey PRIMARY KEY (id);


--
-- Name: aged_positions aged_positions_position_id_key; Type: CONSTRAINT; Schema: monitoring; Owner: -
--

ALTER TABLE ONLY monitoring.aged_positions
    ADD CONSTRAINT aged_positions_position_id_key UNIQUE (position_id);


--
-- Name: event_performance_metrics event_performance_metrics_pkey; Type: CONSTRAINT; Schema: monitoring; Owner: -
--

ALTER TABLE ONLY monitoring.event_performance_metrics
    ADD CONSTRAINT event_performance_metrics_pkey PRIMARY KEY (id);


--
-- Name: events events_pkey; Type: CONSTRAINT; Schema: monitoring; Owner: -
--

ALTER TABLE ONLY monitoring.events
    ADD CONSTRAINT events_pkey PRIMARY KEY (id);


--
-- Name: orders_cache orders_cache_pkey; Type: CONSTRAINT; Schema: monitoring; Owner: -
--

ALTER TABLE ONLY monitoring.orders_cache
    ADD CONSTRAINT orders_cache_pkey PRIMARY KEY (id);


--
-- Name: orders orders_pkey; Type: CONSTRAINT; Schema: monitoring; Owner: -
--

ALTER TABLE ONLY monitoring.orders
    ADD CONSTRAINT orders_pkey PRIMARY KEY (id);


--
-- Name: performance_metrics performance_metrics_pkey; Type: CONSTRAINT; Schema: monitoring; Owner: -
--

ALTER TABLE ONLY monitoring.performance_metrics
    ADD CONSTRAINT performance_metrics_pkey PRIMARY KEY (id);


--
-- Name: positions positions_pkey; Type: CONSTRAINT; Schema: monitoring; Owner: -
--

ALTER TABLE ONLY monitoring.positions
    ADD CONSTRAINT positions_pkey PRIMARY KEY (id);


--
-- Name: risk_events risk_events_pkey; Type: CONSTRAINT; Schema: monitoring; Owner: -
--

ALTER TABLE ONLY monitoring.risk_events
    ADD CONSTRAINT risk_events_pkey PRIMARY KEY (id);


--
-- Name: risk_violations risk_violations_pkey; Type: CONSTRAINT; Schema: monitoring; Owner: -
--

ALTER TABLE ONLY monitoring.risk_violations
    ADD CONSTRAINT risk_violations_pkey PRIMARY KEY (id);


--
-- Name: trades trades_pkey; Type: CONSTRAINT; Schema: monitoring; Owner: -
--

ALTER TABLE ONLY monitoring.trades
    ADD CONSTRAINT trades_pkey PRIMARY KEY (id);


--
-- Name: trailing_stop_state trailing_stop_state_pkey; Type: CONSTRAINT; Schema: monitoring; Owner: -
--

ALTER TABLE ONLY monitoring.trailing_stop_state
    ADD CONSTRAINT trailing_stop_state_pkey PRIMARY KEY (id);


--
-- Name: transaction_log transaction_log_pkey; Type: CONSTRAINT; Schema: monitoring; Owner: -
--

ALTER TABLE ONLY monitoring.transaction_log
    ADD CONSTRAINT transaction_log_pkey PRIMARY KEY (id);


--
-- Name: transaction_log transaction_log_transaction_id_key; Type: CONSTRAINT; Schema: monitoring; Owner: -
--

ALTER TABLE ONLY monitoring.transaction_log
    ADD CONSTRAINT transaction_log_transaction_id_key UNIQUE (transaction_id);


--
-- Name: orders_cache unique_exchange_order; Type: CONSTRAINT; Schema: monitoring; Owner: -
--

ALTER TABLE ONLY monitoring.orders_cache
    ADD CONSTRAINT unique_exchange_order UNIQUE (exchange, exchange_order_id);


--
-- Name: trailing_stop_state unique_ts_per_symbol_exchange; Type: CONSTRAINT; Schema: monitoring; Owner: -
--

ALTER TABLE ONLY monitoring.trailing_stop_state
    ADD CONSTRAINT unique_ts_per_symbol_exchange UNIQUE (symbol, exchange);


--
-- Name: idx_aged_monitoring_created; Type: INDEX; Schema: monitoring; Owner: -
--

CREATE INDEX idx_aged_monitoring_created ON monitoring.aged_monitoring_events USING btree (created_at);


--
-- Name: idx_aged_monitoring_position; Type: INDEX; Schema: monitoring; Owner: -
--

CREATE INDEX idx_aged_monitoring_position ON monitoring.aged_monitoring_events USING btree (aged_position_id);


--
-- Name: idx_aged_monitoring_type; Type: INDEX; Schema: monitoring; Owner: -
--

CREATE INDEX idx_aged_monitoring_type ON monitoring.aged_monitoring_events USING btree (event_type);


--
-- Name: idx_aged_positions_created; Type: INDEX; Schema: monitoring; Owner: -
--

CREATE INDEX idx_aged_positions_created ON monitoring.aged_positions USING btree (created_at);


--
-- Name: idx_aged_positions_symbol; Type: INDEX; Schema: monitoring; Owner: -
--

CREATE INDEX idx_aged_positions_symbol ON monitoring.aged_positions USING btree (symbol);


--
-- Name: idx_event_metrics_name; Type: INDEX; Schema: monitoring; Owner: -
--

CREATE INDEX idx_event_metrics_name ON monitoring.event_performance_metrics USING btree (metric_name);


--
-- Name: idx_event_metrics_time; Type: INDEX; Schema: monitoring; Owner: -
--

CREATE INDEX idx_event_metrics_time ON monitoring.event_performance_metrics USING btree (recorded_at DESC);


--
-- Name: idx_events_correlation; Type: INDEX; Schema: monitoring; Owner: -
--

CREATE INDEX idx_events_correlation ON monitoring.events USING btree (correlation_id);


--
-- Name: idx_events_created; Type: INDEX; Schema: monitoring; Owner: -
--

CREATE INDEX idx_events_created ON monitoring.events USING btree (created_at DESC);


--
-- Name: idx_events_errors; Type: INDEX; Schema: monitoring; Owner: -
--

CREATE INDEX idx_events_errors ON monitoring.events USING btree (created_at DESC) WHERE ((severity)::text = ANY ((ARRAY['ERROR'::character varying, 'CRITICAL'::character varying])::text[]));


--
-- Name: idx_events_exchange; Type: INDEX; Schema: monitoring; Owner: -
--

CREATE INDEX idx_events_exchange ON monitoring.events USING btree (exchange) WHERE (exchange IS NOT NULL);


--
-- Name: idx_events_position; Type: INDEX; Schema: monitoring; Owner: -
--

CREATE INDEX idx_events_position ON monitoring.events USING btree (position_id);


--
-- Name: idx_events_severity; Type: INDEX; Schema: monitoring; Owner: -
--

CREATE INDEX idx_events_severity ON monitoring.events USING btree (severity);


--
-- Name: idx_events_symbol; Type: INDEX; Schema: monitoring; Owner: -
--

CREATE INDEX idx_events_symbol ON monitoring.events USING btree (symbol) WHERE (symbol IS NOT NULL);


--
-- Name: idx_events_type; Type: INDEX; Schema: monitoring; Owner: -
--

CREATE INDEX idx_events_type ON monitoring.events USING btree (event_type);


--
-- Name: idx_orders_cache_created_at; Type: INDEX; Schema: monitoring; Owner: -
--

CREATE INDEX idx_orders_cache_created_at ON monitoring.orders_cache USING btree (created_at DESC);


--
-- Name: idx_orders_cache_exchange_symbol; Type: INDEX; Schema: monitoring; Owner: -
--

CREATE INDEX idx_orders_cache_exchange_symbol ON monitoring.orders_cache USING btree (exchange, symbol);


--
-- Name: idx_orders_cache_order_id; Type: INDEX; Schema: monitoring; Owner: -
--

CREATE INDEX idx_orders_cache_order_id ON monitoring.orders_cache USING btree (exchange_order_id);


--
-- Name: idx_orders_position; Type: INDEX; Schema: monitoring; Owner: -
--

CREATE INDEX idx_orders_position ON monitoring.orders USING btree (position_id);


--
-- Name: idx_orders_status; Type: INDEX; Schema: monitoring; Owner: -
--

CREATE INDEX idx_orders_status ON monitoring.orders USING btree (status);


--
-- Name: idx_positions_exchange_order; Type: INDEX; Schema: monitoring; Owner: -
--

CREATE INDEX idx_positions_exchange_order ON monitoring.positions USING btree (exchange_order_id);


--
-- Name: idx_positions_exit_reason; Type: INDEX; Schema: monitoring; Owner: -
--

CREATE INDEX idx_positions_exit_reason ON monitoring.positions USING btree (exit_reason) WHERE (exit_reason IS NOT NULL);


--
-- Name: idx_positions_opened_at; Type: INDEX; Schema: monitoring; Owner: -
--

CREATE INDEX idx_positions_opened_at ON monitoring.positions USING btree (opened_at);


--
-- Name: idx_positions_status; Type: INDEX; Schema: monitoring; Owner: -
--

CREATE INDEX idx_positions_status ON monitoring.positions USING btree (status);


--
-- Name: idx_positions_symbol; Type: INDEX; Schema: monitoring; Owner: -
--

CREATE INDEX idx_positions_symbol ON monitoring.positions USING btree (symbol);


--
-- Name: idx_ts_state_activated; Type: INDEX; Schema: monitoring; Owner: -
--

CREATE INDEX idx_ts_state_activated ON monitoring.trailing_stop_state USING btree (is_activated);


--
-- Name: idx_ts_state_created_at; Type: INDEX; Schema: monitoring; Owner: -
--

CREATE INDEX idx_ts_state_created_at ON monitoring.trailing_stop_state USING btree (created_at DESC);


--
-- Name: idx_ts_state_exchange; Type: INDEX; Schema: monitoring; Owner: -
--

CREATE INDEX idx_ts_state_exchange ON monitoring.trailing_stop_state USING btree (exchange);


--
-- Name: idx_ts_state_peak_save_time; Type: INDEX; Schema: monitoring; Owner: -
--

CREATE INDEX idx_ts_state_peak_save_time ON monitoring.trailing_stop_state USING btree (last_peak_save_time DESC);


--
-- Name: idx_ts_state_position_id; Type: INDEX; Schema: monitoring; Owner: -
--

CREATE INDEX idx_ts_state_position_id ON monitoring.trailing_stop_state USING btree (position_id);


--
-- Name: idx_ts_state_symbol; Type: INDEX; Schema: monitoring; Owner: -
--

CREATE INDEX idx_ts_state_symbol ON monitoring.trailing_stop_state USING btree (symbol);


--
-- Name: idx_tx_log_id; Type: INDEX; Schema: monitoring; Owner: -
--

CREATE INDEX idx_tx_log_id ON monitoring.transaction_log USING btree (transaction_id);


--
-- Name: idx_tx_log_started; Type: INDEX; Schema: monitoring; Owner: -
--

CREATE INDEX idx_tx_log_started ON monitoring.transaction_log USING btree (started_at DESC);


--
-- Name: idx_tx_log_status; Type: INDEX; Schema: monitoring; Owner: -
--

CREATE INDEX idx_tx_log_status ON monitoring.transaction_log USING btree (status);


--
-- Name: idx_unique_active_position; Type: INDEX; Schema: monitoring; Owner: -
--

CREATE UNIQUE INDEX idx_unique_active_position ON monitoring.positions USING btree (symbol, exchange) WHERE ((status)::text = ANY ((ARRAY['active'::character varying, 'entry_placed'::character varying, 'pending_sl'::character varying, 'pending_entry'::character varying])::text[]));


--
-- Name: trailing_stop_state normalize_side_trigger; Type: TRIGGER; Schema: monitoring; Owner: -
--

CREATE TRIGGER normalize_side_trigger BEFORE INSERT OR UPDATE ON monitoring.trailing_stop_state FOR EACH ROW EXECUTE FUNCTION public.normalize_trailing_stop_side();


--
-- Name: positions update_positions_updated_at; Type: TRIGGER; Schema: monitoring; Owner: -
--

CREATE TRIGGER update_positions_updated_at BEFORE UPDATE ON monitoring.positions FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: TRIGGER update_positions_updated_at ON positions; Type: COMMENT; Schema: monitoring; Owner: -
--

COMMENT ON TRIGGER update_positions_updated_at ON monitoring.positions IS 'Auto-updates updated_at column on any UPDATE';


--
-- Name: trades update_trades_updated_at; Type: TRIGGER; Schema: monitoring; Owner: -
--

CREATE TRIGGER update_trades_updated_at BEFORE UPDATE ON monitoring.trades FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: TRIGGER update_trades_updated_at ON trades; Type: COMMENT; Schema: monitoring; Owner: -
--

COMMENT ON TRIGGER update_trades_updated_at ON monitoring.trades IS 'Auto-updates updated_at column on any UPDATE';


--
-- Name: trailing_stop_state trailing_stop_state_position_id_fkey; Type: FK CONSTRAINT; Schema: monitoring; Owner: -
--

ALTER TABLE ONLY monitoring.trailing_stop_state
    ADD CONSTRAINT trailing_stop_state_position_id_fkey FOREIGN KEY (position_id) REFERENCES monitoring.positions(id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--

\unrestrict XO6pF4P3zcHAfWi2Bdyx9QnvzxWA1grOoQpTyt3OaNTd2N6c4BtCBpWbeLmCnA4

