--
-- PostgreSQL database dump
--

\restrict Idez8L2LWS1btaNranFxDrq6iMpyA7ycvwjgsBeqhyVpCvezTXXgp4cHxwgE0tx

-- Dumped from database version 16.10 (Ubuntu 16.10-0ubuntu0.24.04.1)
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
-- Name: monitoring; Type: SCHEMA; Schema: -; Owner: elcrypto
--

CREATE SCHEMA monitoring;


ALTER SCHEMA monitoring OWNER TO elcrypto;

--
-- Name: check_unprotected_positions(); Type: FUNCTION; Schema: monitoring; Owner: elcrypto
--

CREATE FUNCTION monitoring.check_unprotected_positions() RETURNS TABLE(symbol character varying, exchange character varying, entry_price numeric, current_price numeric, pnl numeric, hours_open numeric)
    LANGUAGE plpgsql
    AS $$
BEGIN
    RETURN QUERY
    SELECT 
        p.symbol,
        p.exchange,
        p.entry_price,
        p.current_price,
        p.pnl,
        EXTRACT(EPOCH FROM (NOW() - p.opened_at))/3600 as hours_open
    FROM monitoring.positions p
    WHERE p.status = 'OPEN'
        AND p.has_stop_loss = FALSE
        AND p.has_trailing_stop = FALSE;
END;
$$;


ALTER FUNCTION monitoring.check_unprotected_positions() OWNER TO elcrypto;

--
-- Name: update_daily_stats(); Type: FUNCTION; Schema: monitoring; Owner: elcrypto
--

CREATE FUNCTION monitoring.update_daily_stats() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    -- Update or insert daily stats
    INSERT INTO monitoring.daily_stats (
        date,
        total_trades,
        successful_trades,
        failed_trades,
        binance_trades,
        bybit_trades
    )
    VALUES (
        CURRENT_DATE,
        1,
        CASE WHEN NEW.status = 'FILLED' THEN 1 ELSE 0 END,
        CASE WHEN NEW.status = 'FAILED' THEN 1 ELSE 0 END,
        CASE WHEN NEW.exchange = 'binance' THEN 1 ELSE 0 END,
        CASE WHEN NEW.exchange = 'bybit' THEN 1 ELSE 0 END
    )
    ON CONFLICT (date) DO UPDATE SET
        total_trades = monitoring.daily_stats.total_trades + 1,
        successful_trades = monitoring.daily_stats.successful_trades + 
            CASE WHEN NEW.status = 'FILLED' THEN 1 ELSE 0 END,
        failed_trades = monitoring.daily_stats.failed_trades + 
            CASE WHEN NEW.status = 'FAILED' THEN 1 ELSE 0 END,
        binance_trades = monitoring.daily_stats.binance_trades + 
            CASE WHEN NEW.exchange = 'binance' THEN 1 ELSE 0 END,
        bybit_trades = monitoring.daily_stats.bybit_trades + 
            CASE WHEN NEW.exchange = 'bybit' THEN 1 ELSE 0 END,
        updated_at = NOW();
    
    RETURN NEW;
END;
$$;


ALTER FUNCTION monitoring.update_daily_stats() OWNER TO elcrypto;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: alert_rules; Type: TABLE; Schema: monitoring; Owner: elcrypto
--

CREATE TABLE monitoring.alert_rules (
    id bigint NOT NULL,
    rule_name character varying(100) NOT NULL,
    rule_type character varying(50) NOT NULL,
    threshold_value numeric(20,4),
    threshold_time_minutes integer,
    enabled boolean DEFAULT true,
    last_triggered timestamp with time zone,
    trigger_count integer DEFAULT 0,
    metadata jsonb,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


ALTER TABLE monitoring.alert_rules OWNER TO elcrypto;

--
-- Name: alert_rules_id_seq; Type: SEQUENCE; Schema: monitoring; Owner: elcrypto
--

CREATE SEQUENCE monitoring.alert_rules_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE monitoring.alert_rules_id_seq OWNER TO elcrypto;

--
-- Name: alert_rules_id_seq; Type: SEQUENCE OWNED BY; Schema: monitoring; Owner: elcrypto
--

ALTER SEQUENCE monitoring.alert_rules_id_seq OWNED BY monitoring.alert_rules.id;


--
-- Name: applied_migrations; Type: TABLE; Schema: monitoring; Owner: elcrypto
--

CREATE TABLE monitoring.applied_migrations (
    id integer NOT NULL,
    migration_file character varying(255) NOT NULL,
    applied_at timestamp without time zone DEFAULT now(),
    checksum character varying(64),
    status character varying(20) DEFAULT 'success'::character varying
);


ALTER TABLE monitoring.applied_migrations OWNER TO elcrypto;

--
-- Name: applied_migrations_id_seq; Type: SEQUENCE; Schema: monitoring; Owner: elcrypto
--

CREATE SEQUENCE monitoring.applied_migrations_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE monitoring.applied_migrations_id_seq OWNER TO elcrypto;

--
-- Name: applied_migrations_id_seq; Type: SEQUENCE OWNED BY; Schema: monitoring; Owner: elcrypto
--

ALTER SEQUENCE monitoring.applied_migrations_id_seq OWNED BY monitoring.applied_migrations.id;


--
-- Name: daily_stats; Type: TABLE; Schema: monitoring; Owner: elcrypto
--

CREATE TABLE monitoring.daily_stats (
    id bigint NOT NULL,
    date date NOT NULL,
    total_trades integer DEFAULT 0,
    successful_trades integer DEFAULT 0,
    failed_trades integer DEFAULT 0,
    total_volume_usd numeric(20,2) DEFAULT 0,
    total_pnl_usd numeric(20,2) DEFAULT 0,
    positions_opened integer DEFAULT 0,
    positions_closed integer DEFAULT 0,
    positions_protected integer DEFAULT 0,
    max_drawdown_usd numeric(20,2),
    binance_trades integer DEFAULT 0,
    bybit_trades integer DEFAULT 0,
    metadata jsonb,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


ALTER TABLE monitoring.daily_stats OWNER TO elcrypto;

--
-- Name: daily_stats_id_seq; Type: SEQUENCE; Schema: monitoring; Owner: elcrypto
--

CREATE SEQUENCE monitoring.daily_stats_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE monitoring.daily_stats_id_seq OWNER TO elcrypto;

--
-- Name: daily_stats_id_seq; Type: SEQUENCE OWNED BY; Schema: monitoring; Owner: elcrypto
--

ALTER SEQUENCE monitoring.daily_stats_id_seq OWNED BY monitoring.daily_stats.id;


--
-- Name: performance_metrics; Type: TABLE; Schema: monitoring; Owner: elcrypto
--

CREATE TABLE monitoring.performance_metrics (
    id bigint NOT NULL,
    metric_date date NOT NULL,
    metric_hour integer NOT NULL,
    exchange character varying(20) NOT NULL,
    signals_received integer DEFAULT 0,
    orders_placed integer DEFAULT 0,
    orders_filled integer DEFAULT 0,
    orders_failed integer DEFAULT 0,
    avg_execution_time_ms integer,
    positions_opened integer DEFAULT 0,
    positions_closed integer DEFAULT 0,
    positions_protected integer DEFAULT 0,
    total_volume_usd numeric(20,2),
    realized_pnl numeric(20,2),
    unrealized_pnl numeric(20,2),
    created_at timestamp with time zone DEFAULT now(),
    CONSTRAINT performance_metrics_metric_hour_check CHECK (((metric_hour >= 0) AND (metric_hour < 24)))
);


ALTER TABLE monitoring.performance_metrics OWNER TO elcrypto;

--
-- Name: performance_metrics_id_seq; Type: SEQUENCE; Schema: monitoring; Owner: elcrypto
--

CREATE SEQUENCE monitoring.performance_metrics_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE monitoring.performance_metrics_id_seq OWNER TO elcrypto;

--
-- Name: performance_metrics_id_seq; Type: SEQUENCE OWNED BY; Schema: monitoring; Owner: elcrypto
--

ALTER SEQUENCE monitoring.performance_metrics_id_seq OWNED BY monitoring.performance_metrics.id;


--
-- Name: positions; Type: TABLE; Schema: monitoring; Owner: elcrypto
--

CREATE TABLE monitoring.positions (
    id bigint NOT NULL,
    trade_id bigint,
    symbol character varying(20) NOT NULL,
    exchange character varying(20) NOT NULL,
    side character varying(10) NOT NULL,
    quantity numeric(20,8) NOT NULL,
    entry_price numeric(20,8) NOT NULL,
    current_price numeric(20,8),
    pnl numeric(20,8),
    pnl_percent numeric(10,4),
    has_stop_loss boolean DEFAULT false,
    stop_loss_price numeric(20,8),
    has_take_profit boolean DEFAULT false,
    take_profit_price numeric(20,8),
    has_trailing_stop boolean DEFAULT false,
    trailing_activation numeric(20,8),
    trailing_callback numeric(10,4),
    status character varying(20) DEFAULT 'OPEN'::character varying,
    opened_at timestamp with time zone DEFAULT now(),
    closed_at timestamp with time zone,
    updated_at timestamp with time zone DEFAULT now(),
    leverage numeric(10,2) DEFAULT 1.0,
    stop_loss numeric(20,8),
    take_profit numeric(20,8),
    pnl_percentage numeric(10,4),
    trailing_activated boolean DEFAULT false,
    created_at timestamp without time zone DEFAULT now(),
    exit_reason character varying(50),
    unrealized_pnl numeric DEFAULT 0
);


ALTER TABLE monitoring.positions OWNER TO elcrypto;

--
-- Name: COLUMN positions.pnl; Type: COMMENT; Schema: monitoring; Owner: elcrypto
--

COMMENT ON COLUMN monitoring.positions.pnl IS 'Alias for unrealized_pnl';


--
-- Name: COLUMN positions.leverage; Type: COMMENT; Schema: monitoring; Owner: elcrypto
--

COMMENT ON COLUMN monitoring.positions.leverage IS 'Position leverage multiplier';


--
-- Name: COLUMN positions.stop_loss; Type: COMMENT; Schema: monitoring; Owner: elcrypto
--

COMMENT ON COLUMN monitoring.positions.stop_loss IS 'Alias for stop_loss_price';


--
-- Name: COLUMN positions.take_profit; Type: COMMENT; Schema: monitoring; Owner: elcrypto
--

COMMENT ON COLUMN monitoring.positions.take_profit IS 'Alias for take_profit_price';


--
-- Name: COLUMN positions.pnl_percentage; Type: COMMENT; Schema: monitoring; Owner: elcrypto
--

COMMENT ON COLUMN monitoring.positions.pnl_percentage IS 'PnL as percentage of investment';


--
-- Name: COLUMN positions.trailing_activated; Type: COMMENT; Schema: monitoring; Owner: elcrypto
--

COMMENT ON COLUMN monitoring.positions.trailing_activated IS 'Whether trailing stop is activated';


--
-- Name: COLUMN positions.created_at; Type: COMMENT; Schema: monitoring; Owner: elcrypto
--

COMMENT ON COLUMN monitoring.positions.created_at IS 'Alias for opened_at';


--
-- Name: positions_id_seq; Type: SEQUENCE; Schema: monitoring; Owner: elcrypto
--

CREATE SEQUENCE monitoring.positions_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE monitoring.positions_id_seq OWNER TO elcrypto;

--
-- Name: positions_id_seq; Type: SEQUENCE OWNED BY; Schema: monitoring; Owner: elcrypto
--

ALTER SEQUENCE monitoring.positions_id_seq OWNED BY monitoring.positions.id;


--
-- Name: processed_signals; Type: TABLE; Schema: monitoring; Owner: elcrypto
--

CREATE TABLE monitoring.processed_signals (
    id integer NOT NULL,
    signal_id character varying(255) NOT NULL,
    symbol character varying(50) NOT NULL,
    action character varying(20) NOT NULL,
    score_week numeric(10,2),
    score_month numeric(10,2),
    processed_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    result character varying(50),
    position_id integer,
    error_message text,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT valid_action CHECK (((action)::text = ANY ((ARRAY['BUY'::character varying, 'SELL'::character varying, 'LONG'::character varying, 'SHORT'::character varying, 'CLOSE'::character varying])::text[])))
);


ALTER TABLE monitoring.processed_signals OWNER TO elcrypto;

--
-- Name: TABLE processed_signals; Type: COMMENT; Schema: monitoring; Owner: elcrypto
--

COMMENT ON TABLE monitoring.processed_signals IS 'Tracks all processed trading signals to prevent duplicate processing';


--
-- Name: COLUMN processed_signals.signal_id; Type: COMMENT; Schema: monitoring; Owner: elcrypto
--

COMMENT ON COLUMN monitoring.processed_signals.signal_id IS 'Unique identifier from signal source';


--
-- Name: COLUMN processed_signals.result; Type: COMMENT; Schema: monitoring; Owner: elcrypto
--

COMMENT ON COLUMN monitoring.processed_signals.result IS 'Processing result: success, skipped, failed, etc';


--
-- Name: processed_signals_id_seq; Type: SEQUENCE; Schema: monitoring; Owner: elcrypto
--

CREATE SEQUENCE monitoring.processed_signals_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE monitoring.processed_signals_id_seq OWNER TO elcrypto;

--
-- Name: processed_signals_id_seq; Type: SEQUENCE OWNED BY; Schema: monitoring; Owner: elcrypto
--

ALTER SEQUENCE monitoring.processed_signals_id_seq OWNED BY monitoring.processed_signals.id;


--
-- Name: protection_events; Type: TABLE; Schema: monitoring; Owner: elcrypto
--

CREATE TABLE monitoring.protection_events (
    id bigint NOT NULL,
    position_id bigint,
    symbol character varying(20) NOT NULL,
    exchange character varying(20) NOT NULL,
    event_type character varying(50) NOT NULL,
    protection_type character varying(20),
    price_level numeric(20,8),
    activation_price numeric(20,8),
    callback_rate numeric(10,4),
    success boolean DEFAULT true,
    error_message text,
    created_at timestamp with time zone DEFAULT now()
);


ALTER TABLE monitoring.protection_events OWNER TO elcrypto;

--
-- Name: protection_events_id_seq; Type: SEQUENCE; Schema: monitoring; Owner: elcrypto
--

CREATE SEQUENCE monitoring.protection_events_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE monitoring.protection_events_id_seq OWNER TO elcrypto;

--
-- Name: protection_events_id_seq; Type: SEQUENCE OWNED BY; Schema: monitoring; Owner: elcrypto
--

ALTER SEQUENCE monitoring.protection_events_id_seq OWNED BY monitoring.protection_events.id;


--
-- Name: system_health; Type: TABLE; Schema: monitoring; Owner: elcrypto
--

CREATE TABLE monitoring.system_health (
    id bigint NOT NULL,
    service_name character varying(50) NOT NULL,
    status character varying(20) NOT NULL,
    binance_connected boolean,
    bybit_connected boolean,
    database_connected boolean,
    last_signal_processed timestamp with time zone,
    signals_processed_count integer DEFAULT 0,
    positions_protected_count integer DEFAULT 0,
    error_count integer DEFAULT 0,
    last_error text,
    metadata jsonb,
    created_at timestamp with time zone DEFAULT now()
);


ALTER TABLE monitoring.system_health OWNER TO elcrypto;

--
-- Name: system_health_id_seq; Type: SEQUENCE; Schema: monitoring; Owner: elcrypto
--

CREATE SEQUENCE monitoring.system_health_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE monitoring.system_health_id_seq OWNER TO elcrypto;

--
-- Name: system_health_id_seq; Type: SEQUENCE OWNED BY; Schema: monitoring; Owner: elcrypto
--

ALTER SEQUENCE monitoring.system_health_id_seq OWNED BY monitoring.system_health.id;


--
-- Name: trades; Type: TABLE; Schema: monitoring; Owner: elcrypto
--

CREATE TABLE monitoring.trades (
    id bigint NOT NULL,
    signal_id bigint NOT NULL,
    trading_pair_id integer,
    symbol character varying(20) NOT NULL,
    exchange character varying(20) NOT NULL,
    side character varying(10) NOT NULL,
    quantity numeric(20,8),
    executed_qty numeric(20,8),
    price numeric(20,8),
    status character varying(20) NOT NULL,
    order_id character varying(100),
    error_message text,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


ALTER TABLE monitoring.trades OWNER TO elcrypto;

--
-- Name: trades_id_seq; Type: SEQUENCE; Schema: monitoring; Owner: elcrypto
--

CREATE SEQUENCE monitoring.trades_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE monitoring.trades_id_seq OWNER TO elcrypto;

--
-- Name: trades_id_seq; Type: SEQUENCE OWNED BY; Schema: monitoring; Owner: elcrypto
--

ALTER SEQUENCE monitoring.trades_id_seq OWNED BY monitoring.trades.id;


--
-- Name: v_current_positions; Type: VIEW; Schema: monitoring; Owner: elcrypto
--

CREATE VIEW monitoring.v_current_positions AS
 SELECT p.id,
    p.symbol,
    p.exchange,
    p.side,
    p.quantity,
    p.entry_price,
    p.current_price,
    p.pnl,
    p.pnl_percent,
        CASE
            WHEN (p.has_stop_loss OR p.has_trailing_stop) THEN 'PROTECTED'::text
            ELSE 'UNPROTECTED'::text
        END AS protection_status,
    p.has_stop_loss,
    p.stop_loss_price,
    p.has_take_profit,
    p.take_profit_price,
    p.has_trailing_stop,
    p.trailing_activation,
    p.trailing_callback,
    p.opened_at,
    (EXTRACT(epoch FROM (now() - p.opened_at)) / (3600)::numeric) AS hours_open,
    t.signal_id
   FROM (monitoring.positions p
     LEFT JOIN monitoring.trades t ON ((p.trade_id = t.id)))
  WHERE ((p.status)::text = 'OPEN'::text)
  ORDER BY p.opened_at DESC;


ALTER VIEW monitoring.v_current_positions OWNER TO elcrypto;

--
-- Name: v_daily_pnl; Type: VIEW; Schema: monitoring; Owner: elcrypto
--

CREATE VIEW monitoring.v_daily_pnl AS
 SELECT date(closed_at) AS date,
    exchange,
    count(*) AS positions_closed,
    sum(pnl) AS total_pnl,
    avg(pnl_percent) AS avg_pnl_percent,
    max(pnl) AS best_trade,
    min(pnl) AS worst_trade
   FROM monitoring.positions
  WHERE (((status)::text = 'CLOSED'::text) AND (closed_at IS NOT NULL))
  GROUP BY (date(closed_at)), exchange
  ORDER BY (date(closed_at)) DESC;


ALTER VIEW monitoring.v_daily_pnl OWNER TO elcrypto;

--
-- Name: v_hourly_performance; Type: VIEW; Schema: monitoring; Owner: elcrypto
--

CREATE VIEW monitoring.v_hourly_performance AS
 SELECT date_trunc('hour'::text, created_at) AS hour,
    exchange,
    count(*) AS total_trades,
    count(*) FILTER (WHERE ((status)::text = 'FILLED'::text)) AS successful,
    count(*) FILTER (WHERE ((status)::text = 'FAILED'::text)) AS failed,
    round(((100.0 * (count(*) FILTER (WHERE ((status)::text = 'FILLED'::text)))::numeric) / (NULLIF(count(*), 0))::numeric), 2) AS success_rate,
    string_agg(DISTINCT
        CASE
            WHEN (((status)::text = 'FAILED'::text) AND (error_message IS NOT NULL)) THEN "left"(error_message, 50)
            ELSE NULL::text
        END, '; '::text) AS error_summary
   FROM monitoring.trades
  WHERE (created_at > (now() - '48:00:00'::interval))
  GROUP BY (date_trunc('hour'::text, created_at)), exchange
  ORDER BY (date_trunc('hour'::text, created_at)) DESC;


ALTER VIEW monitoring.v_hourly_performance OWNER TO elcrypto;

--
-- Name: v_recent_signals; Type: VIEW; Schema: monitoring; Owner: elcrypto
--

CREATE VIEW monitoring.v_recent_signals AS
 SELECT sh.id,
    sh.created_at,
    sh.score_week,
    sh.score_month,
    tp.pair_symbol,
    tp.exchange_id,
        CASE
            WHEN (t.id IS NOT NULL) THEN 'PROCESSED'::text
            ELSE 'PENDING'::text
        END AS status,
    t.status AS trade_status
   FROM ((fas.scoring_history sh
     JOIN public.trading_pairs tp ON ((sh.trading_pair_id = tp.id)))
     LEFT JOIN monitoring.trades t ON ((sh.id = t.signal_id)))
  WHERE (sh.created_at > (now() - '01:00:00'::interval))
  ORDER BY sh.created_at DESC;


ALTER VIEW monitoring.v_recent_signals OWNER TO elcrypto;

--
-- Name: v_symbol_performance; Type: VIEW; Schema: monitoring; Owner: elcrypto
--

CREATE VIEW monitoring.v_symbol_performance AS
 SELECT symbol,
    exchange,
    count(*) AS total_attempts,
    count(*) FILTER (WHERE ((status)::text = 'FILLED'::text)) AS successful,
    count(*) FILTER (WHERE ((status)::text = 'FAILED'::text)) AS failed,
    round(((100.0 * (count(*) FILTER (WHERE ((status)::text = 'FILLED'::text)))::numeric) / (NULLIF(count(*), 0))::numeric), 2) AS success_rate,
    max(created_at) AS last_trade
   FROM monitoring.trades
  WHERE (created_at > (now() - '7 days'::interval))
  GROUP BY symbol, exchange
 HAVING (count(*) > 1)
  ORDER BY (round(((100.0 * (count(*) FILTER (WHERE ((status)::text = 'FILLED'::text)))::numeric) / (NULLIF(count(*), 0))::numeric), 2)), (count(*)) DESC;


ALTER VIEW monitoring.v_symbol_performance OWNER TO elcrypto;

--
-- Name: alert_rules id; Type: DEFAULT; Schema: monitoring; Owner: elcrypto
--

ALTER TABLE ONLY monitoring.alert_rules ALTER COLUMN id SET DEFAULT nextval('monitoring.alert_rules_id_seq'::regclass);


--
-- Name: applied_migrations id; Type: DEFAULT; Schema: monitoring; Owner: elcrypto
--

ALTER TABLE ONLY monitoring.applied_migrations ALTER COLUMN id SET DEFAULT nextval('monitoring.applied_migrations_id_seq'::regclass);


--
-- Name: daily_stats id; Type: DEFAULT; Schema: monitoring; Owner: elcrypto
--

ALTER TABLE ONLY monitoring.daily_stats ALTER COLUMN id SET DEFAULT nextval('monitoring.daily_stats_id_seq'::regclass);


--
-- Name: performance_metrics id; Type: DEFAULT; Schema: monitoring; Owner: elcrypto
--

ALTER TABLE ONLY monitoring.performance_metrics ALTER COLUMN id SET DEFAULT nextval('monitoring.performance_metrics_id_seq'::regclass);


--
-- Name: positions id; Type: DEFAULT; Schema: monitoring; Owner: elcrypto
--

ALTER TABLE ONLY monitoring.positions ALTER COLUMN id SET DEFAULT nextval('monitoring.positions_id_seq'::regclass);


--
-- Name: processed_signals id; Type: DEFAULT; Schema: monitoring; Owner: elcrypto
--

ALTER TABLE ONLY monitoring.processed_signals ALTER COLUMN id SET DEFAULT nextval('monitoring.processed_signals_id_seq'::regclass);


--
-- Name: protection_events id; Type: DEFAULT; Schema: monitoring; Owner: elcrypto
--

ALTER TABLE ONLY monitoring.protection_events ALTER COLUMN id SET DEFAULT nextval('monitoring.protection_events_id_seq'::regclass);


--
-- Name: system_health id; Type: DEFAULT; Schema: monitoring; Owner: elcrypto
--

ALTER TABLE ONLY monitoring.system_health ALTER COLUMN id SET DEFAULT nextval('monitoring.system_health_id_seq'::regclass);


--
-- Name: trades id; Type: DEFAULT; Schema: monitoring; Owner: elcrypto
--

ALTER TABLE ONLY monitoring.trades ALTER COLUMN id SET DEFAULT nextval('monitoring.trades_id_seq'::regclass);


--
-- Data for Name: alert_rules; Type: TABLE DATA; Schema: monitoring; Owner: elcrypto
--

COPY monitoring.alert_rules (id, rule_name, rule_type, threshold_value, threshold_time_minutes, enabled, last_triggered, trigger_count, metadata, created_at, updated_at) FROM stdin;
1	unprotected_position_5min	UNPROTECTED_POSITION	\N	5	t	\N	0	\N	2025-09-09 13:39:28.479077+00	2025-09-09 13:39:28.479077+00
2	position_loss_5pct	POSITION_PNL	-5.0000	\N	t	\N	0	\N	2025-09-09 13:39:28.479077+00	2025-09-09 13:39:28.479077+00
3	position_profit_10pct	POSITION_PNL	10.0000	\N	t	\N	0	\N	2025-09-09 13:39:28.479077+00	2025-09-09 13:39:28.479077+00
4	system_error_threshold	SYSTEM_ERROR	10.0000	60	t	\N	0	\N	2025-09-09 13:39:28.479077+00	2025-09-09 13:39:28.479077+00
\.


--
-- Data for Name: applied_migrations; Type: TABLE DATA; Schema: monitoring; Owner: elcrypto
--

COPY monitoring.applied_migrations (id, migration_file, applied_at, checksum, status) FROM stdin;
1	add_exit_reason_column.sql	2025-10-04 02:27:02.262397	\N	success
3	add_missing_position_fields.sql	2025-10-04 02:27:48.87375	\N	success
5	add_realized_pnl_column.sql	2025-10-04 02:28:09.316902	\N	success
6	create_processed_signals_table.sql	2025-10-04 02:28:09.654725	\N	success
7	fix_field_sync.sql	2025-10-04 02:28:10.396842	\N	success
\.


--
-- Data for Name: daily_stats; Type: TABLE DATA; Schema: monitoring; Owner: elcrypto
--

COPY monitoring.daily_stats (id, date, total_trades, successful_trades, failed_trades, total_volume_usd, total_pnl_usd, positions_opened, positions_closed, positions_protected, max_drawdown_usd, binance_trades, bybit_trades, metadata, created_at, updated_at) FROM stdin;
8012	2025-10-08	132	132	0	0.00	0.00	0	0	0	\N	132	0	\N	2025-10-08 11:35:12.441819+00	2025-10-08 23:51:45.276983+00
8144	2025-10-09	152	152	0	0.00	0.00	0	0	0	\N	152	0	\N	2025-10-09 00:21:09.94965+00	2025-10-09 15:50:30.410912+00
\.


--
-- Data for Name: performance_metrics; Type: TABLE DATA; Schema: monitoring; Owner: elcrypto
--

COPY monitoring.performance_metrics (id, metric_date, metric_hour, exchange, signals_received, orders_placed, orders_filled, orders_failed, avg_execution_time_ms, positions_opened, positions_closed, positions_protected, total_volume_usd, realized_pnl, unrealized_pnl, created_at) FROM stdin;
1	2025-09-13	17	Binance	0	0	0	0	\N	0	0	0	\N	\N	\N	2025-09-13 17:56:46.024081+00
2	2025-09-13	17	Bybit	0	0	0	0	\N	0	0	0	\N	\N	\N	2025-09-13 17:56:46.101472+00
153	2025-09-14	4	Binance	0	0	0	0	\N	0	0	0	\N	\N	\N	2025-09-14 04:00:45.337196+00
154	2025-09-14	4	Bybit	0	0	0	0	\N	0	0	0	\N	\N	\N	2025-09-14 04:00:45.417741+00
309	2025-09-14	13	Binance	0	0	0	0	\N	0	0	0	\N	\N	\N	2025-09-14 13:15:43.658081+00
3	2025-09-13	18	Binance	0	0	0	0	\N	0	0	0	\N	\N	\N	2025-09-13 18:01:46.418423+00
4	2025-09-13	18	Bybit	0	0	0	0	\N	0	0	0	\N	\N	\N	2025-09-13 18:01:46.495203+00
310	2025-09-14	13	Bybit	0	0	0	0	\N	0	0	0	\N	\N	\N	2025-09-14 13:15:43.740404+00
105	2025-09-14	2	Binance	0	0	0	0	\N	0	0	0	\N	\N	\N	2025-09-14 02:00:33.612022+00
106	2025-09-14	2	Bybit	0	0	0	0	\N	0	0	0	\N	\N	\N	2025-09-14 02:00:33.692666+00
57	2025-09-14	0	Binance	0	0	0	0	\N	0	0	0	\N	\N	\N	2025-09-14 00:00:22.84538+00
58	2025-09-14	0	Bybit	0	0	0	0	\N	0	0	0	\N	\N	\N	2025-09-14 00:00:22.925036+00
13	2025-09-13	22	Binance	0	0	0	0	\N	0	0	0	\N	\N	\N	2025-09-13 22:20:13.164229+00
14	2025-09-13	22	Bybit	0	0	0	0	\N	0	0	0	\N	\N	\N	2025-09-13 22:20:13.244098+00
269	2025-09-14	9	Binance	0	0	0	0	\N	0	0	0	\N	\N	\N	2025-09-14 09:01:12.20938+00
270	2025-09-14	9	Bybit	0	0	0	0	\N	0	0	0	\N	\N	\N	2025-09-14 09:01:12.290075+00
225	2025-09-14	7	Binance	0	0	0	0	\N	0	0	0	\N	\N	\N	2025-09-14 07:01:01.853776+00
226	2025-09-14	7	Bybit	0	0	0	0	\N	0	0	0	\N	\N	\N	2025-09-14 07:01:01.934368+00
177	2025-09-14	5	Binance	0	0	0	0	\N	0	0	0	\N	\N	\N	2025-09-14 05:00:50.371705+00
178	2025-09-14	5	Bybit	0	0	0	0	\N	0	0	0	\N	\N	\N	2025-09-14 05:00:50.451122+00
129	2025-09-14	3	Binance	0	0	0	0	\N	0	0	0	\N	\N	\N	2025-09-14 03:00:39.819068+00
130	2025-09-14	3	Bybit	0	0	0	0	\N	0	0	0	\N	\N	\N	2025-09-14 03:00:39.898688+00
81	2025-09-14	1	Binance	0	0	0	0	\N	0	0	0	\N	\N	\N	2025-09-14 01:00:28.388109+00
82	2025-09-14	1	Bybit	0	0	0	0	\N	0	0	0	\N	\N	\N	2025-09-14 01:00:28.467539+00
33	2025-09-13	23	Binance	0	0	0	0	\N	0	0	0	\N	\N	\N	2025-09-13 23:00:17.008791+00
34	2025-09-13	23	Bybit	0	0	0	0	\N	0	0	0	\N	\N	\N	2025-09-13 23:00:17.16741+00
293	2025-09-14	10	Binance	0	0	0	0	\N	0	0	0	\N	\N	\N	2025-09-14 10:01:17.436145+00
294	2025-09-14	10	Bybit	0	0	0	0	\N	0	0	0	\N	\N	\N	2025-09-14 10:01:17.515267+00
247	2025-09-14	8	Binance	0	0	0	0	\N	0	0	0	\N	\N	\N	2025-09-14 08:06:06.634747+00
248	2025-09-14	8	Bybit	0	0	0	0	\N	0	0	0	\N	\N	\N	2025-09-14 08:06:06.714639+00
201	2025-09-14	6	Binance	0	0	0	0	\N	0	0	0	\N	\N	\N	2025-09-14 06:00:55.892368+00
202	2025-09-14	6	Bybit	0	0	0	0	\N	0	0	0	\N	\N	\N	2025-09-14 06:00:56.050011+00
\.


--
-- Data for Name: positions; Type: TABLE DATA; Schema: monitoring; Owner: elcrypto
--

COPY monitoring.positions (id, trade_id, symbol, exchange, side, quantity, entry_price, current_price, pnl, pnl_percent, has_stop_loss, stop_loss_price, has_take_profit, take_profit_price, has_trailing_stop, trailing_activation, trailing_callback, status, opened_at, closed_at, updated_at, leverage, stop_loss, take_profit, pnl_percentage, trailing_activated, created_at, exit_reason, unrealized_pnl) FROM stdin;
68	\N	ALICEUSDT	binance	sell	555.00000000	0.35800000	0.35100000	0.00000000	\N	t	0.36516000	f	\N	t	\N	\N	closed	2025-10-08 23:36:17.091016+00	2025-10-09 02:40:58.816311+00	2025-10-09 02:40:58.816311+00	10.00	\N	\N	0.0000	t	2025-10-08 23:36:17.091016	PHANTOM_AGED	1.927254149999999999209876477834768593311309814453125
116	\N	PENGUUSDT	binance	sell	6347.00000000	0.03139800	0.03129800	0.00000000	\N	t	0.03202596	f	\N	t	\N	\N	closed	2025-10-09 03:36:14.024672+00	2025-10-09 06:55:35.786271+00	2025-10-09 06:55:35.786271+00	10.00	\N	\N	0.0000	f	2025-10-09 03:36:14.024672	PHANTOM_CLEANUP	0.563930950000000041910652726073749363422393798828125
159	\N	OPUSDT	binance	sell	281.00000000	0.70900000	0.69740000	0.00000000	\N	t	0.72318000	f	\N	t	\N	\N	closed	2025-10-09 07:22:14.470311+00	2025-10-09 08:31:16.51744+00	2025-10-09 08:31:16.51744+00	10.00	\N	\N	0.0000	t	2025-10-09 07:22:14.470311	PHANTOM_CLEANUP	3.334843370000000195574330064118839800357818603515625
149	\N	ORDIUSDT	binance	sell	24.00000000	8.04200000	7.88000000	0.00000000	\N	t	8.20284000	f	\N	t	\N	\N	closed	2025-10-09 06:21:25.988893+00	2025-10-09 08:31:16.773192+00	2025-10-09 08:31:16.773192+00	10.00	\N	\N	0.0000	f	2025-10-09 06:21:25.988893	PHANTOM_CLEANUP	4.2574307999999998486373442574404180049896240234375
230	\N	BANDUSDT	binance	sell	300.00000000	0.66430000	0.66420000	\N	\N	t	0.67758600	f	\N	t	\N	\N	active	2025-10-09 15:50:17.042359+00	\N	2025-10-09 16:11:53.061202+00	10.00	\N	\N	\N	f	2025-10-09 15:50:17.042359	\N	0.0299999999999999988897769753748434595763683319091796875
231	\N	DOTUSDT	binance	sell	49.00000000	3.98500000	4.00295325	\N	\N	t	4.06470000	f	\N	t	\N	\N	active	2025-10-09 15:50:23.555746+00	\N	2025-10-09 16:11:53.220189+00	10.00	\N	\N	\N	f	2025-10-09 15:50:23.555746	\N	-0.87970924999999999815969431438134051859378814697265625
232	\N	CHZUSDT	binance	sell	4924.00000000	0.04047000	0.04058382	\N	\N	t	0.04127940	f	\N	t	\N	\N	active	2025-10-09 15:50:30.575891+00	\N	2025-10-09 16:11:53.377684+00	10.00	\N	\N	\N	f	2025-10-09 15:50:30.575891	\N	-0.56044967999999995011961573254666291177272796630859375
226	\N	ARUSDT	binance	sell	35.00000000	5.58500000	5.62500000	\N	\N	t	5.69670000	f	\N	t	\N	\N	active	2025-10-09 14:36:48.10687+00	\N	2025-10-09 16:12:03.356256+00	10.00	\N	\N	\N	f	2025-10-09 14:36:48.10687	\N	-1.399999999999999911182158029987476766109466552734375
181	\N	REDUSDT	binance	buy	429.00000000	0.46760000	0.46650000	\N	\N	t	0.47695200	f	\N	t	\N	\N	active	2025-10-09 10:51:26.939574+00	\N	2025-10-09 16:12:03.518467+00	10.00	\N	\N	\N	f	2025-10-09 10:51:26.939574	\N	-0.4718999999999999861444166526780463755130767822265625
223	\N	UNIUSDT	binance	sell	25.00000000	7.70400000	7.72800000	\N	\N	t	7.85808000	f	\N	t	\N	\N	active	2025-10-09 14:36:26.441243+00	\N	2025-10-09 16:12:03.698371+00	10.00	\N	\N	\N	f	2025-10-09 14:36:26.441243	\N	-0.59999999999999997779553950749686919152736663818359375
227	\N	ETCUSDT	binance	sell	10.00000000	18.83000000	18.84900000	\N	\N	t	19.20660000	f	\N	t	\N	\N	active	2025-10-09 15:37:18.89112+00	\N	2025-10-09 16:12:03.863813+00	10.00	\N	\N	\N	f	2025-10-09 15:37:18.89112	\N	-0.190000000000000002220446049250313080847263336181640625
229	\N	KNCUSDT	binance	sell	618.00000000	0.32300000	0.32240000	\N	\N	t	0.32946000	f	\N	t	\N	\N	active	2025-10-09 15:37:34.321216+00	\N	2025-10-09 16:12:04.047027+00	10.00	\N	\N	\N	f	2025-10-09 15:37:34.321216	\N	0.37080000000000001847411112976260483264923095703125
224	\N	ATAUSDT	binance	sell	5089.00000000	0.03930000	0.03943752	\N	\N	t	0.04008600	f	\N	t	\N	\N	active	2025-10-09 14:36:33.27834+00	\N	2025-10-09 16:12:04.202418+00	10.00	\N	\N	\N	f	2025-10-09 14:36:33.27834	\N	-0.69983927999999995250846041017211973667144775390625
216	\N	ALGOUSDT	binance	sell	917.40000000	0.21700000	0.21563056	\N	\N	t	0.22134000	f	\N	t	\N	\N	active	2025-10-09 13:51:28.639571+00	\N	2025-10-09 16:12:04.378498+00	10.00	\N	\N	\N	f	2025-10-09 13:51:28.639571	\N	1.256324250000000031235458664014004170894622802734375
62	\N	API3USDT	binance	buy	226.00000000	0.88520000	0.80820000	\N	\N	t	0.90290400	f	\N	t	\N	\N	active	2025-10-08 23:21:10.719398+00	\N	2025-10-09 16:12:04.535368+00	10.00	\N	\N	\N	f	2025-10-08 23:21:10.719398	\N	-17.4020000000000010231815394945442676544189453125
228	\N	ADAUSDT	binance	sell	248.00000000	0.80440000	0.80320000	\N	\N	t	0.82048800	f	\N	t	\N	\N	active	2025-10-09 15:37:27.175036+00	\N	2025-10-09 16:12:04.6912+00	10.00	\N	\N	\N	f	2025-10-09 15:37:27.175036	\N	0.29759999999999997566391130021656863391399383544921875
222	\N	RLCUSDT	binance	sell	193.00000000	1.03160000	1.04284781	\N	\N	t	1.05223200	f	\N	t	\N	\N	active	2025-10-09 14:36:16.506456+00	\N	2025-10-09 16:12:04.856125+00	10.00	\N	\N	\N	f	2025-10-09 14:36:16.506456	\N	-2.1708273299999998329212758108042180538177490234375
151	\N	KERNELUSDT	binance	buy	893.00000000	0.22390000	0.21634776	\N	\N	t	0.22837800	f	\N	t	\N	\N	active	2025-10-09 06:36:13.705777+00	\N	2025-10-09 16:12:05.010009+00	10.00	\N	\N	\N	t	2025-10-09 06:36:13.705777	\N	-6.74415032000000014278384696808643639087677001953125
219	\N	GRTUSDT	binance	sell	2473.00000000	0.08056000	0.07996000	\N	\N	t	0.08217120	f	\N	t	\N	\N	active	2025-10-09 13:51:49.022727+00	\N	2025-10-09 16:12:05.189415+00	10.00	\N	\N	\N	f	2025-10-09 13:51:49.022727	\N	1.483800000000000007815970093361102044582366943359375
38	\N	PHBUSDT	binance	sell	332.00000000	0.60020000	0.59880000	0.00000000	\N	t	0.61220400	f	\N	t	\N	\N	closed	2025-10-08 20:51:26.180399+00	2025-10-09 00:16:29.027666+00	2025-10-09 00:16:29.027666+00	10.00	\N	\N	0.0000	f	2025-10-08 20:51:26.180399	PHANTOM_AGED	0.315000000000000002220446049250313080847263336181640625
217	\N	NEARUSDT	binance	sell	69.00000000	2.87110000	2.84213441	\N	\N	t	2.92852200	f	\N	t	\N	\N	active	2025-10-09 13:51:35.276117+00	\N	2025-10-09 16:12:05.355794+00	10.00	\N	\N	\N	f	2025-10-09 13:51:35.276117	\N	1.9987250700000001035760988088441081345081329345703125
225	\N	DYDXUSDT	binance	sell	358.00000000	0.55800000	0.55949964	\N	\N	t	0.56916000	f	\N	t	\N	\N	active	2025-10-09 14:36:42.168146+00	\N	2025-10-09 16:12:05.526157+00	10.00	\N	\N	\N	f	2025-10-09 14:36:42.168146	\N	-0.5368711200000000349774609276209957897663116455078125
46	\N	LINKUSDT	binance	sell	8.00000000	22.43700000	22.41700000	0.00000000	\N	t	22.88574000	f	\N	t	\N	\N	closed	2025-10-08 21:51:13.172868+00	2025-10-09 01:26:31.837341+00	2025-10-09 01:26:31.837341+00	10.00	\N	\N	0.0000	f	2025-10-08 21:51:13.172868	PHANTOM_AGED	0.0700925599999999981992715447631780989468097686767578125
113	\N	STORJUSDT	binance	sell	890.00000000	0.22420000	0.22840000	0.00000000	\N	t	0.22868400	f	\N	t	\N	\N	closed	2025-10-09 02:51:25.304669+00	2025-10-09 04:16:24.13348+00	2025-10-09 04:16:24.13348+00	10.00	\N	\N	0.0000	f	2025-10-09 02:51:25.304669	PHANTOM_CLEANUP	-4.198334700000000196951077668927609920501708984375
153	\N	UNIUSDT	binance	sell	25.00000000	7.87300000	7.70700000	0.00000000	\N	t	8.03046000	f	\N	t	\N	\N	closed	2025-10-09 06:36:29.503775+00	2025-10-09 08:52:16.333473+00	2025-10-09 08:52:16.333473+00	10.00	\N	\N	0.0000	f	2025-10-09 06:36:29.503775	PHANTOM_CLEANUP	3.49407900000000015694467947469092905521392822265625
147	\N	ATOMUSDT	binance	sell	49.00000000	4.06600000	4.01100000	0.00000000	\N	t	4.14732000	f	\N	t	\N	\N	closed	2025-10-09 06:21:12.954411+00	2025-10-09 09:02:35.600455+00	2025-10-09 09:02:35.600455+00	10.00	\N	\N	0.0000	f	2025-10-09 06:21:12.954411	PHANTOM_CLEANUP	3.131843330000000147350647239363752305507659912109375
120	\N	FUNUSDT	binance	sell	23261.00000000	0.00856100	0.00873800	0.00000000	\N	t	0.00873222	f	\N	t	\N	\N	closed	2025-10-09 03:36:41.668357+00	2025-10-09 09:33:21.923897+00	2025-10-09 09:33:21.923897+00	10.00	\N	\N	0.0000	f	2025-10-09 03:36:41.668357	PHANTOM_CLEANUP	-4.11719699999999999562305674771778285503387451171875
141	\N	MASKUSDT	binance	sell	157.00000000	1.26510000	1.24090000	0.00000000	\N	t	1.29040200	f	\N	t	\N	\N	closed	2025-10-09 05:35:21.880546+00	2025-10-09 08:41:49.2568+00	2025-10-09 08:41:49.2568+00	10.00	\N	\N	0.0000	f	2025-10-09 05:35:21.880546	PHANTOM_CLEANUP	3.63699449000000019083245206275023519992828369140625
158	\N	VELODROMEUSDT	binance	sell	4364.00000000	0.04582000	0.04507000	0.00000000	\N	t	0.04673640	f	\N	t	\N	\N	closed	2025-10-09 06:51:27.652539+00	2025-10-09 08:41:49.642308+00	2025-10-09 08:41:49.642308+00	10.00	\N	\N	0.0000	t	2025-10-09 06:51:27.652539	PHANTOM_CLEANUP	2.70568000000000008498091119690798223018646240234375
154	\N	NEARUSDT	binance	sell	68.00000000	2.90500000	2.86000000	0.00000000	\N	t	2.96310000	f	\N	t	\N	\N	closed	2025-10-09 06:36:35.703815+00	2025-10-09 08:41:49.843158+00	2025-10-09 08:41:49.843158+00	10.00	\N	\N	0.0000	f	2025-10-09 06:36:35.703815	PHANTOM_CLEANUP	2.8559999999999998721023075631819665431976318359375
152	\N	TRBUSDT	binance	sell	6.00000000	32.98900000	32.30800000	0.00000000	\N	t	33.64878000	f	\N	t	\N	\N	closed	2025-10-09 06:36:22.993381+00	2025-10-09 08:41:50.037291+00	2025-10-09 08:41:50.037291+00	10.00	\N	\N	0.0000	f	2025-10-09 06:36:22.993381	PHANTOM_CLEANUP	3.311999999999999833022457096376456320285797119140625
32	\N	BANDUSDT	binance	sell	291.00000000	0.68550000	0.68230000	0.00000000	\N	t	0.69921000	f	\N	t	\N	\N	closed	2025-10-08 20:36:22.130243+00	2025-10-09 00:37:02.387272+00	2025-10-09 00:37:02.387272+00	10.00	\N	\N	0.0000	f	2025-10-08 20:36:22.130243	PHANTOM_CLEANUP	0.303561099999999972620656762956059537827968597412109375
34	\N	NKNUSDT	binance	sell	7727.00000000	0.02581000	0.02572000	0.00000000	\N	t	0.02632620	f	\N	t	\N	\N	closed	2025-10-08 20:36:36.35382+00	2025-10-09 00:37:02.64235+00	2025-10-09 00:37:02.64235+00	10.00	\N	\N	0.0000	f	2025-10-08 20:36:36.35382	PHANTOM_CLEANUP	0.11206728000000000522451415463365265168249607086181640625
24	\N	DEGOUSDT	binance	sell	175.00000000	1.13660000	1.13490000	0.00000000	\N	t	1.15933200	f	\N	t	\N	\N	closed	2025-10-08 19:36:17.966604+00	2025-10-09 00:37:02.83264+00	2025-10-09 00:37:02.83264+00	10.00	\N	\N	0.0000	f	2025-10-08 19:36:17.966604	PHANTOM_CLEANUP	0.2225999999999999923172566695939167402684688568115234375
40	\N	PUNDIXUSDT	binance	sell	636.00000000	0.31440000	0.31350000	0.00000000	\N	t	0.32068800	f	\N	t	\N	\N	closed	2025-10-08 20:51:38.644584+00	2025-10-09 00:37:03.016118+00	2025-10-09 00:37:03.016118+00	10.00	\N	\N	0.0000	f	2025-10-08 20:51:38.644584	PHANTOM_CLEANUP	0.1396672599999999875297618245895137079060077667236328125
114	\N	AVAXUSDT	binance	sell	7.00000000	28.13600000	28.07400000	0.00000000	\N	t	28.69872000	f	\N	t	\N	\N	closed	2025-10-09 02:51:31.529643+00	2025-10-09 08:41:50.228105+00	2025-10-09 08:41:50.228105+00	10.00	\N	\N	0.0000	f	2025-10-09 02:51:31.529643	PHANTOM_CLEANUP	0.433999999999999996891375531049561686813831329345703125
160	\N	HIGHUSDT	binance	sell	429.00000000	0.46404230	0.45590000	0.00000000	\N	t	0.47332315	f	\N	t	\N	\N	closed	2025-10-09 07:22:22.317234+00	2025-10-09 08:41:50.420427+00	2025-10-09 08:41:50.420427+00	10.00	\N	\N	0.0000	f	2025-10-09 07:22:22.317234	PHANTOM_CLEANUP	3.77061399000000019299250197946093976497650146484375
146	\N	SPXUSDT	binance	sell	135.00000000	1.47450000	1.44830000	0.00000000	\N	t	1.50399000	f	\N	t	\N	\N	closed	2025-10-09 05:51:41.671628+00	2025-10-09 08:41:50.917478+00	2025-10-09 08:41:50.917478+00	10.00	\N	\N	0.0000	f	2025-10-09 05:51:41.671628	PHANTOM_CLEANUP	3.53699999999999992184029906638897955417633056640625
155	\N	DODOXUSDT	binance	sell	4272.00000000	0.04659800	0.04550900	0.00000000	\N	t	0.04752996	f	\N	t	\N	\N	closed	2025-10-09 06:36:42.275706+00	2025-10-09 08:41:51.096198+00	2025-10-09 08:41:51.096198+00	10.00	\N	\N	0.0000	f	2025-10-09 06:36:42.275706	PHANTOM_CLEANUP	4.33099631999999967746362017351202666759490966796875
121	\N	SUSDT	binance	sell	718.00000000	0.27780000	0.27770000	0.00000000	\N	t	0.28335600	f	\N	t	\N	\N	closed	2025-10-09 03:51:12.380736+00	2025-10-09 07:01:57.847044+00	2025-10-09 07:01:57.847044+00	10.00	\N	\N	0.0000	f	2025-10-09 03:51:12.380736	PHANTOM_AGED	0.08459999999999999464872502130674547515809535980224609375
122	\N	VETUSDT	binance	sell	8913.00000000	0.02239100	0.02229000	0.00000000	\N	t	0.02283882	f	\N	t	\N	\N	closed	2025-10-09 03:51:19.555542+00	2025-10-09 07:01:58.472406+00	2025-10-09 07:01:58.472406+00	10.00	\N	\N	0.0000	f	2025-10-09 03:51:19.555542	PHANTOM_AGED	0.7635600000000000164845914696343243122100830078125
33	\N	EGLDUSDT	binance	sell	14.00000000	13.49900000	13.47417526	0.00000000	\N	t	13.76898000	f	\N	t	\N	\N	closed	2025-10-08 20:36:29.204413+00	2025-10-09 00:16:32.563935+00	2025-10-09 00:16:50.607989+00	10.00	\N	\N	0.0000	f	2025-10-08 20:36:29.204413	PHANTOM_AGED	0.134053590000000000248547848968883045017719268798828125
125	\N	SSVUSDT	binance	sell	25.00000000	7.91900000	7.90000000	0.00000000	\N	t	8.07738000	f	\N	t	\N	\N	closed	2025-10-09 03:51:40.420853+00	2025-10-09 07:02:01.178157+00	2025-10-09 07:02:01.178157+00	10.00	\N	\N	0.0000	f	2025-10-09 03:51:40.420853	PHANTOM_AGED	1.101341750000000008213874025386758148670196533203125
76	\N	PROMUSDT	binance	sell	19.00000000	10.06200000	10.09012644	0.00000000	\N	t	10.26324000	f	\N	t	\N	\N	closed	2025-10-09 00:21:10.198768+00	2025-10-09 11:56:39.538113+00	2025-10-09 11:56:39.538113+00	10.00	\N	\N	0.0000	f	2025-10-09 00:21:10.198768	PHANTOM_AGED	-0.039377009999999997014175079357301001437008380889892578125
148	\N	IOSTUSDT	binance	sell	65338.00000000	0.00306000	0.00299900	0.00000000	\N	t	0.00312120	f	\N	t	\N	\N	closed	2025-10-09 06:21:19.595883+00	2025-10-09 09:02:35.340576+00	2025-10-09 09:02:35.340576+00	10.00	\N	\N	0.0000	f	2025-10-09 06:21:19.595883	PHANTOM_CLEANUP	4.116293999999999897454472375102341175079345703125
36	\N	DOGSUSDT	binance	sell	1672240.00000000	0.00011950	0.00012210	0.00000000	\N	t	0.00012189	f	\N	f	\N	\N	closed	2025-10-08 20:51:13.453704+00	2025-10-08 22:02:16.997199+00	2025-10-08 22:02:16.997199+00	10.00	\N	\N	0.0000	f	2025-10-08 20:51:13.453704	PHANTOM_CLEANUP	-4.23076719999999983912175594014115631580352783203125
203	\N	GPSUSDT	binance	sell	14958.00000000	0.01336000	0.01296000	0.00000000	\N	t	0.01362720	f	\N	t	\N	\N	closed	2025-10-09 12:51:40.355678+00	2025-10-09 14:11:17.961103+00	2025-10-09 14:11:17.961103+00	10.00	\N	\N	0.0000	f	2025-10-09 12:51:40.355678	PHANTOM_CLEANUP	6.993463320000000038589860196225345134735107421875
214	\N	FHEUSDT	binance	sell	4256.00000000	0.04698000	0.04616000	0.00000000	\N	t	0.04791960	f	\N	t	\N	\N	closed	2025-10-09 13:36:38.808728+00	2025-10-09 14:11:18.205108+00	2025-10-09 14:11:18.205108+00	10.00	\N	\N	0.0000	f	2025-10-09 13:36:38.808728	PHANTOM_CLEANUP	3.125223360000000116798446470056660473346710205078125
164	\N	ASTRUSDT	binance	sell	7701.00000000	0.02596800	0.02578600	0.00000000	\N	t	0.02648736	f	\N	t	\N	\N	closed	2025-10-09 08:21:18.231374+00	2025-10-09 09:12:54.92318+00	2025-10-09 09:12:54.92318+00	10.00	\N	\N	0.0000	t	2025-10-09 08:21:18.231374	PHANTOM_CLEANUP	1.6788179999999999214566059890785254538059234619140625
162	\N	NEOUSDT	binance	sell	32.00000000	6.14000000	6.04500000	0.00000000	\N	t	6.26280000	f	\N	t	\N	\N	closed	2025-10-09 07:52:12.670587+00	2025-10-09 09:12:55.189065+00	2025-10-09 09:12:55.189065+00	10.00	\N	\N	0.0000	t	2025-10-09 07:52:12.670587	PHANTOM_CLEANUP	0.09385880000000000611404260553172207437455654144287109375
99	\N	GTCUSDT	binance	sell	711.00000000	0.28000000	0.27400000	0.00000000	\N	t	0.28560000	f	\N	t	\N	\N	closed	2025-10-09 01:51:25.179155+00	2025-10-09 02:41:47.07008+00	2025-10-09 02:41:47.07008+00	10.00	\N	\N	0.0000	f	2025-10-09 01:51:25.179155	PHANTOM_CLEANUP	4.0434143399999999957117324811406433582305908203125
71	\N	KASUSDT	binance	sell	2654.00000000	0.07498000	0.07392000	0.00000000	\N	t	0.07647960	f	\N	t	\N	\N	closed	2025-10-08 23:36:35.110936+00	2025-10-09 02:41:47.258909+00	2025-10-09 02:41:47.258909+00	10.00	\N	\N	0.0000	f	2025-10-08 23:36:35.110936	PHANTOM_CLEANUP	2.76015999999999994685140336514450609683990478515625
197	\N	MYROUSDT	binance	sell	10989.00000000	0.01805000	0.01782000	0.00000000	\N	t	0.01841100	f	\N	t	\N	\N	closed	2025-10-09 12:36:33.032462+00	2025-10-09 14:11:18.392242+00	2025-10-09 14:11:18.392242+00	10.00	\N	\N	0.0000	f	2025-10-09 12:36:33.032462	PHANTOM_CLEANUP	3.296699999999999963762320476234890520572662353515625
192	\N	TAKEUSDT	binance	sell	705.00000000	0.28352000	0.27486000	0.00000000	\N	t	0.28919040	f	\N	t	\N	\N	closed	2025-10-09 11:51:24.306267+00	2025-10-09 12:07:23.053824+00	2025-10-09 12:07:23.053824+00	10.00	\N	\N	0.0000	f	2025-10-09 11:51:24.306267	PHANTOM_CLEANUP	0.1239120900000000025098501055254018865525722503662109375
199	\N	GOATUSDT	binance	sell	2430.00000000	0.08198000	0.08120000	0.00000000	\N	t	0.08361960	f	\N	t	\N	\N	closed	2025-10-09 12:36:46.578761+00	2025-10-09 14:11:18.553627+00	2025-10-09 14:11:18.553627+00	10.00	\N	\N	0.0000	f	2025-10-09 12:36:46.578761	PHANTOM_CLEANUP	1.9615446000000000825735924081527628004550933837890625
67	\N	HOMEUSDT	binance	sell	6574.00000000	0.03028600	0.02981500	0.00000000	\N	t	0.03089172	f	\N	t	\N	\N	closed	2025-10-08 23:36:10.415754+00	2025-10-09 02:41:47.455979+00	2025-10-09 02:41:47.455979+00	10.00	\N	\N	0.0000	f	2025-10-08 23:36:10.415754	PHANTOM_CLEANUP	3.017400260000000056237468015751801431179046630859375
70	\N	BLURUSDT	binance	sell	2695.00000000	0.07370000	0.07220000	0.00000000	\N	t	0.07517400	f	\N	t	\N	\N	closed	2025-10-08 23:36:28.943682+00	2025-10-09 02:41:47.650964+00	2025-10-09 02:41:47.650964+00	10.00	\N	\N	0.0000	t	2025-10-08 23:36:28.943682	PHANTOM_CLEANUP	4.01555000000000017479351299698464572429656982421875
87	\N	AIOUSDT	binance	sell	1382.00000000	0.14448000	0.14081000	0.00000000	\N	t	0.14736960	f	\N	t	\N	\N	closed	2025-10-09 00:51:27.652823+00	2025-10-09 02:41:47.827415+00	2025-10-09 02:41:47.827415+00	10.00	\N	\N	0.0000	t	2025-10-09 00:51:27.652823	PHANTOM_CLEANUP	4.6701373200000002583465175121091306209564208984375
74	\N	SSVUSDT	binance	sell	24.00000000	8.02400000	7.84000000	0.00000000	\N	t	8.18448000	f	\N	t	\N	\N	closed	2025-10-08 23:51:38.615601+00	2025-10-09 03:02:21.825781+00	2025-10-09 03:02:21.825781+00	10.00	\N	\N	0.0000	f	2025-10-08 23:51:38.615601	PHANTOM_AGED	5.9526705599999996110227584722451865673065185546875
171	\N	XPINUSDT	binance	sell	185994.00000000	0.00107410	0.00109429	\N	\N	t	0.00109558	f	\N	t	\N	\N	closed	2025-10-09 09:51:39.089425+00	\N	2025-10-09 10:53:06.804111+00	10.00	\N	\N	\N	f	2025-10-09 09:51:39.089425	\N	-3.755218859999999825305394551833160221576690673828125
163	\N	ZILUSDT	binance	sell	18779.00000000	0.01060000	0.01052000	\N	\N	t	0.01081200	f	\N	t	\N	\N	closed	2025-10-09 07:52:19.202051+00	\N	2025-10-09 10:53:07.062739+00	10.00	\N	\N	\N	f	2025-10-09 07:52:19.202051	\N	1.50232000000000009976020010071806609630584716796875
55	\N	HOLOUSDT	binance	sell	930.00000000	0.21450000	0.22030000	0.00000000	\N	t	0.21879000	f	\N	t	\N	\N	closed	2025-10-08 22:36:32.272015+00	2025-10-09 00:22:35.923389+00	2025-10-09 00:22:35.923389+00	10.00	\N	\N	0.0000	f	2025-10-08 22:36:32.272015	PHANTOM_CLEANUP	-3.960814200000000173673697645426727831363677978515625
41	\N	TOWNSUSDT	binance	sell	10554.00000000	0.01890000	0.01877000	0.00000000	\N	t	0.01927800	f	\N	t	\N	\N	closed	2025-10-08 21:21:46.82584+00	2025-10-09 00:22:36.176427+00	2025-10-09 00:22:36.176427+00	10.00	\N	\N	0.0000	f	2025-10-08 21:21:46.82584	PHANTOM_CLEANUP	0.236302559999999994833075334099703468382358551025390625
207	\N	CRVUSDT	binance	sell	274.00000000	0.72600000	0.71800000	0.00000000	\N	t	0.74052000	f	\N	t	\N	\N	closed	2025-10-09 13:21:37.483738+00	2025-10-09 14:42:01.910276+00	2025-10-09 14:42:01.910276+00	10.00	\N	\N	0.0000	f	2025-10-09 13:21:37.483738	PHANTOM_CLEANUP	2.48870912000000021890855350648052990436553955078125
195	\N	BSVUSDT	binance	sell	8.00000000	24.98000000	24.64000000	0.00000000	\N	t	25.47960000	f	\N	t	\N	\N	closed	2025-10-09 12:36:20.36363+00	2025-10-09 14:42:02.09431+00	2025-10-09 14:42:02.09431+00	10.00	\N	\N	0.0000	f	2025-10-09 12:36:20.36363	PHANTOM_CLEANUP	2.399999999999999911182158029987476766109466552734375
206	\N	DOTUSDT	binance	sell	49.00000000	4.04800000	3.99600000	0.00000000	\N	t	4.12896000	f	\N	t	\N	\N	closed	2025-10-09 13:21:27.823176+00	2025-10-09 14:42:02.280219+00	2025-10-09 14:42:02.280219+00	10.00	\N	\N	0.0000	f	2025-10-09 13:21:27.823176	PHANTOM_CLEANUP	2.298745820000000161797970577026717364788055419921875
221	\N	MILKUSDT	binance	sell	4826.00000000	0.04143000	0.04081000	0.00000000	\N	t	0.04225860	f	\N	t	\N	\N	closed	2025-10-09 14:21:49.728787+00	2025-10-09 14:42:02.472803+00	2025-10-09 14:42:02.472803+00	10.00	\N	\N	0.0000	t	2025-10-09 14:21:49.728787	PHANTOM_CLEANUP	3.506764640000000099462340585887432098388671875
220	\N	ZEREBROUSDT	binance	sell	11293.00000000	0.01767000	0.01739000	0.00000000	\N	t	0.01802340	f	\N	t	\N	\N	closed	2025-10-09 14:21:43.068986+00	2025-10-09 14:42:02.656932+00	2025-10-09 14:42:02.656932+00	10.00	\N	\N	0.0000	f	2025-10-09 14:21:43.068986	PHANTOM_CLEANUP	2.810714770000000140015572469565086066722869873046875
218	\N	FILUSDT	binance	sell	87.00000000	2.26600000	2.24200000	0.00000000	\N	t	2.31132000	f	\N	t	\N	\N	closed	2025-10-09 13:51:42.489289+00	2025-10-09 14:42:02.838363+00	2025-10-09 14:42:02.838363+00	10.00	\N	\N	0.0000	f	2025-10-09 13:51:42.489289	PHANTOM_CLEANUP	2.074896929999999972693558447645045816898345947265625
4	\N	1000000MOGUSDT	binance	sell	252.00000000	0.79170000	0.78097685	0.00000000	\N	t	0.80753400	f	\N	f	\N	\N	closed	2025-10-08 18:06:29.403618+00	2025-10-08 19:24:35.723006+00	2025-10-08 19:24:35.723006+00	10.00	\N	\N	0.0000	t	2025-10-08 18:06:29.403618	PHANTOM_CLEANUP	2.7022338000000001301259544561617076396942138671875
196	\N	AXLUSDT	binance	sell	686.00000000	0.29060000	0.28610000	0.00000000	\N	t	0.29641200	f	\N	t	\N	\N	closed	2025-10-09 12:36:26.732172+00	2025-10-09 14:42:03.020823+00	2025-10-09 14:42:03.020823+00	10.00	\N	\N	0.0000	f	2025-10-09 12:36:26.732172	PHANTOM_CLEANUP	3.016403739999999888965476202429272234439849853515625
201	\N	AGLDUSDT	binance	sell	363.00000000	0.54700000	0.53960000	0.00000000	\N	t	0.55794000	f	\N	t	\N	\N	closed	2025-10-09 12:51:27.574703+00	2025-10-09 14:42:03.209201+00	2025-10-09 14:42:03.209201+00	10.00	\N	\N	0.0000	f	2025-10-09 12:51:27.574703	PHANTOM_CLEANUP	2.443135199999999951359086480806581676006317138671875
89	\N	BARDUSDT	binance	sell	258.00000000	0.76900000	0.76700000	0.00000000	\N	t	0.78438000	f	\N	t	\N	\N	closed	2025-10-09 01:21:11.590949+00	2025-10-09 04:47:28.995893+00	2025-10-09 04:47:28.995893+00	10.00	\N	\N	0.0000	f	2025-10-09 01:21:11.590949	PHANTOM_AGED	0.1439999999999999891198143586734659038484096527099609375
22	\N	SKATEUSDT	binance	sell	3732.00000000	0.05346930	0.05325000	0.00000000	\N	t	0.05453869	f	\N	f	\N	\N	closed	2025-10-08 19:22:38.81169+00	2025-10-08 22:25:41.894436+00	2025-10-08 22:25:41.894436+00	10.00	\N	\N	0.0000	f	2025-10-08 19:22:38.81169	PHANTOM_CLEANUP	0.73371120000000000782591769166174344718456268310546875
198	\N	REIUSDT	binance	sell	13262.00000000	0.01496000	0.01487035	0.00000000	\N	t	0.01525920	f	\N	t	\N	\N	closed	2025-10-09 12:36:39.373011+00	2025-10-09 15:42:42.443021+00	2025-10-09 15:42:42.443021+00	10.00	\N	\N	0.0000	f	2025-10-09 12:36:39.373011	PHANTOM_CLEANUP	1.1889383000000000034646063795662485063076019287109375
204	\N	ETHWUSDT	binance	sell	144.00000000	1.38058330	1.36530000	\N	\N	t	1.40819497	f	\N	t	\N	\N	closed	2025-10-09 12:51:54.731859+00	\N	2025-10-09 14:12:53.800449+00	10.00	\N	\N	\N	f	2025-10-09 12:51:54.731859	\N	2.200799519999999898089981797966174781322479248046875
80	\N	KAVAUSDT	binance	sell	616.00000000	0.32400000	0.32330000	0.00000000	\N	t	0.33048000	f	\N	t	\N	\N	closed	2025-10-09 00:36:16.21061+00	2025-10-09 04:15:47.928474+00	2025-10-09 04:15:47.928474+00	10.00	\N	\N	0.0000	f	2025-10-09 00:36:16.21061	PHANTOM_AGED	0.3207573599999999913734427536837756633758544921875
128	\N	SNXUSDT	binance	sell	183.00000000	1.08900000	1.08400000	0.00000000	\N	t	1.11078000	f	\N	t	\N	\N	closed	2025-10-09 04:21:26.202456+00	2025-10-09 07:27:44.963013+00	2025-10-09 07:27:44.963013+00	10.00	\N	\N	0.0000	f	2025-10-09 04:21:26.202456	PHANTOM_CLEANUP	0.284799999999999997601918266809661872684955596923828125
156	\N	HOTUSDT	binance	sell	229095.00000000	0.00087300	0.00087000	0.00000000	\N	t	0.00089046	f	\N	t	\N	\N	closed	2025-10-09 06:51:14.057322+00	2025-10-09 07:27:45.244326+00	2025-10-09 07:27:45.244326+00	10.00	\N	\N	0.0000	t	2025-10-09 06:51:14.057322	PHANTOM_CLEANUP	0.004866320000000000367545993640305823646485805511474609375
26	\N	ARUSDT	binance	sell	33.00000000	6.01600000	6.00000000	0.00000000	\N	t	6.13632000	f	\N	f	\N	\N	closed	2025-10-08 19:51:11.845888+00	2025-10-08 22:57:42.398385+00	2025-10-08 22:57:42.398385+00	10.00	\N	\N	0.0000	f	2025-10-08 19:51:11.845888	PHANTOM_CLEANUP	0.0415999999999999980904163976447307504713535308837890625
25	\N	MILKUSDT	binance	sell	4482.00000000	0.04448000	0.04411000	0.00000000	\N	t	0.04536960	f	\N	f	\N	\N	closed	2025-10-08 19:36:24.247465+00	2025-10-08 22:57:42.664111+00	2025-10-08 22:57:42.664111+00	10.00	\N	\N	0.0000	f	2025-10-08 19:36:24.247465	PHANTOM_CLEANUP	0.071504139999999993815293919396935962140560150146484375
129	\N	ENSUSDT	binance	sell	9.00000000	20.95800000	20.80700000	0.00000000	\N	t	21.37716000	f	\N	t	\N	\N	closed	2025-10-09 04:21:33.187833+00	2025-10-09 07:27:45.42939+00	2025-10-09 07:27:45.42939+00	10.00	\N	\N	0.0000	f	2025-10-09 04:21:33.187833	PHANTOM_CLEANUP	0.1214723699999999961818275551195256412029266357421875
186	\N	FETUSDT	binance	sell	378.00000000	0.52660000	0.51831543	\N	\N	t	0.53713200	f	\N	t	\N	\N	closed	2025-10-09 11:21:32.968392+00	\N	2025-10-09 14:12:54.058098+00	10.00	\N	\N	\N	f	2025-10-09 11:21:32.968392	\N	3.131567459999999858411001696367748081684112548828125
212	\N	SANTOSUSDT	binance	sell	103.00000000	1.92500000	1.89400000	0.00000000	\N	t	1.96350000	f	\N	t	\N	\N	closed	2025-10-09 13:36:25.964717+00	2025-10-09 14:42:01.648601+00	2025-10-09 14:42:01.648601+00	10.00	\N	\N	0.0000	t	2025-10-09 13:36:25.964717	PHANTOM_CLEANUP	2.793528919999999970968929119408130645751953125
178	\N	BANKUSDT	binance	sell	1538.00000000	0.12973660	0.12756311	\N	\N	t	0.13233133	f	\N	t	\N	\N	closed	2025-10-09 10:36:40.564825+00	\N	2025-10-09 11:03:40.213727+00	10.00	\N	\N	\N	f	2025-10-09 10:36:40.564825	\N	3.342812240000000212347686101566068828105926513671875
175	\N	LQTYUSDT	binance	sell	280.00000000	0.71400000	0.71538599	\N	\N	t	0.72828000	f	\N	t	\N	\N	closed	2025-10-09 10:36:12.758451+00	\N	2025-10-09 11:03:40.466078+00	10.00	\N	\N	\N	f	2025-10-09 10:36:12.758451	\N	-0.01385989999999999965074604091341825551353394985198974609375
3	\N	SCRUSDT	binance	sell	723.00000000	0.27650000	0.27420000	0.00000000	\N	t	0.28203000	f	\N	f	\N	\N	closed	2025-10-08 18:06:23.006967+00	2025-10-08 21:09:24.67492+00	2025-10-08 21:09:24.67492+00	10.00	\N	\N	0.0000	f	2025-10-08 18:06:23.006967	PHANTOM_CLEANUP	0.5082999999999999740651901447563432157039642333984375
5	\N	PNUTUSDT	binance	sell	928.00000000	0.21499000	0.21370849	0.00000000	\N	t	0.21928980	f	\N	f	\N	\N	closed	2025-10-08 18:06:36.210192+00	2025-10-08 21:09:24.948147+00	2025-10-08 21:09:24.948147+00	10.00	\N	\N	0.0000	f	2025-10-08 18:06:36.210192	PHANTOM_CLEANUP	0.10636532999999999404838746386303682811558246612548828125
1	\N	FLUXUSDT	binance	sell	1056.00000000	0.18910000	0.18854401	0.00000000	\N	t	0.19288200	f	\N	f	\N	\N	closed	2025-10-08 18:06:09.995645+00	2025-10-08 21:09:25.142341+00	2025-10-08 21:09:25.142341+00	10.00	\N	\N	0.0000	f	2025-10-08 18:06:09.995645	PHANTOM_CLEANUP	0.11620191000000000547398570915902382694184780120849609375
83	\N	A2ZUSDT	binance	sell	35198.00000000	0.00567600	0.00557828	0.00000000	\N	t	0.00578952	f	\N	t	\N	\N	closed	2025-10-09 00:36:35.197686+00	2025-10-09 02:52:38.850463+00	2025-10-09 02:52:38.850463+00	10.00	\N	\N	0.0000	f	2025-10-09 00:36:35.197686	PHANTOM_CLEANUP	3.439548559999999977065954226418398320674896240234375
90	\N	CFXUSDT	binance	sell	1358.00000000	0.14713000	0.14495000	0.00000000	\N	t	0.15007260	f	\N	t	\N	\N	closed	2025-10-09 01:21:18.249296+00	2025-10-09 02:52:39.111432+00	2025-10-09 02:52:39.111432+00	10.00	\N	\N	0.0000	f	2025-10-09 01:21:18.249296	PHANTOM_CLEANUP	3.299939999999999873381284487550146877765655517578125
73	\N	1000SHIBUSDT	binance	sell	16220.00000000	0.01230300	0.01213493	0.00000000	\N	t	0.01254906	f	\N	t	\N	\N	closed	2025-10-08 23:51:32.70888+00	2025-10-09 02:52:39.302559+00	2025-10-09 02:52:39.302559+00	10.00	\N	\N	0.0000	t	2025-10-08 23:51:32.70888	PHANTOM_CLEANUP	2.7260954000000001684611561358906328678131103515625
101	\N	DUSKUSDT	binance	sell	3117.00000000	0.06403000	0.06268000	0.00000000	\N	t	0.06531060	f	\N	t	\N	\N	closed	2025-10-09 01:51:37.939988+00	2025-10-09 02:52:39.457188+00	2025-10-09 02:52:39.457188+00	10.00	\N	\N	0.0000	t	2025-10-09 01:51:37.939988	PHANTOM_CLEANUP	4.207950000000000301270119962282478809356689453125
79	\N	FILUSDT	binance	sell	84.00000000	2.35400000	2.29800000	0.00000000	\N	t	2.40108000	f	\N	t	\N	\N	closed	2025-10-09 00:21:31.283065+00	2025-10-09 02:52:39.651742+00	2025-10-09 02:52:39.651742+00	10.00	\N	\N	0.0000	f	2025-10-09 00:21:31.283065	PHANTOM_CLEANUP	4.70399999999999973709918776876293122768402099609375
82	\N	DMCUSDT	binance	sell	59364.00000000	0.00336800	0.00325100	0.00000000	\N	t	0.00343536	f	\N	t	\N	\N	closed	2025-10-09 00:36:28.943004+00	2025-10-09 02:52:39.854201+00	2025-10-09 02:52:39.854201+00	10.00	\N	\N	0.0000	f	2025-10-09 00:36:28.943004	PHANTOM_CLEANUP	6.94558799999999987306864568381570279598236083984375
96	\N	STGUSDT	binance	sell	966.00000000	0.20690000	0.20460000	0.00000000	\N	t	0.21103800	f	\N	t	\N	\N	closed	2025-10-09 01:36:35.677353+00	2025-10-09 02:52:40.047497+00	2025-10-09 02:52:40.047497+00	10.00	\N	\N	0.0000	f	2025-10-09 01:36:35.677353	PHANTOM_CLEANUP	2.318400000000000016342482922482304275035858154296875
98	\N	ONTUSDT	binance	sell	1579.70000000	0.12580000	0.12400000	0.00000000	\N	t	0.12831600	f	\N	t	\N	\N	closed	2025-10-09 01:51:18.809013+00	2025-10-09 02:52:40.249221+00	2025-10-09 02:52:40.249221+00	10.00	\N	\N	0.0000	f	2025-10-09 01:51:18.809013	PHANTOM_CLEANUP	2.6977010799999998624798536184243857860565185546875
30	\N	BIGTIMEUSDT	binance	sell	4095.00000000	0.04872000	0.04858000	\N	\N	t	0.04969440	f	\N	f	\N	\N	closed	2025-10-08 19:51:36.998872+00	\N	2025-10-08 23:08:35.266458+00	10.00	\N	\N	\N	f	2025-10-08 19:51:36.998872	\N	0.57330000000000003179678742526448331773281097412109375
23	\N	RAREUSDT	binance	sell	3941.00000000	0.05059000	0.05043962	\N	\N	t	0.05160180	f	\N	f	\N	\N	closed	2025-10-08 19:36:11.888854+00	\N	2025-10-08 23:08:35.524177+00	10.00	\N	\N	\N	f	2025-10-08 19:36:11.888854	\N	0.08511507999999999574125553181147552095353603363037109375
20	\N	OXTUSDT	binance	sell	4011.00000000	0.04969000	0.04944000	\N	\N	t	0.05068380	f	\N	f	\N	\N	closed	2025-10-08 19:22:18.555932+00	\N	2025-10-08 23:08:35.69244+00	10.00	\N	\N	\N	f	2025-10-08 19:22:18.555932	\N	1.0027500000000000301980662698042578995227813720703125
18	\N	USTCUSDT	binance	sell	17975.00000000	0.01108800	0.01103469	\N	\N	t	0.01130976	f	\N	f	\N	\N	closed	2025-10-08 18:51:38.253974+00	\N	2025-10-08 23:08:35.856033+00	10.00	\N	\N	\N	f	2025-10-08 18:51:38.253974	\N	0.95824724999999999486277602045447565615177154541015625
78	\N	XTZUSDT	binance	sell	292.00000000	0.68210000	0.67200000	0.00000000	\N	t	0.69574200	f	\N	t	\N	\N	closed	2025-10-09 00:21:24.342368+00	2025-10-09 02:52:40.447716+00	2025-10-09 02:52:40.447716+00	10.00	\N	\N	0.0000	f	2025-10-09 00:21:24.342368	PHANTOM_CLEANUP	2.936197239999999819559661773382686078548431396484375
43	\N	MUBARAKUSDT	binance	sell	4968.00000000	0.04021000	0.04040000	0.00000000	\N	t	0.04101420	f	\N	t	\N	\N	closed	2025-10-08 21:36:12.498809+00	2025-10-09 00:43:42.513736+00	2025-10-09 00:43:42.513736+00	10.00	\N	\N	0.0000	f	2025-10-08 21:36:12.498809	PHANTOM_AGED	0.235532880000000000020321522242738865315914154052734375
200	\N	XVGUSDT	binance	sell	27851.00000000	0.00718090	0.00713500	0.00000000	\N	t	0.00732452	f	\N	t	\N	\N	closed	2025-10-09 12:51:20.4471+00	2025-10-09 13:02:57.151443+00	2025-10-09 13:02:57.151443+00	10.00	\N	\N	0.0000	t	2025-10-09 12:51:20.4471	PHANTOM_CLEANUP	2.482638140000000159801629706635139882564544677734375
42	\N	FLOCKUSDT	binance	sell	717.00000000	0.27790000	0.27711097	0.00000000	\N	t	0.28345800	f	\N	t	\N	\N	closed	2025-10-08 21:21:53.426045+00	2025-10-09 02:09:08.609182+00	2025-10-09 02:09:08.609182+00	10.00	\N	\N	0.0000	f	2025-10-08 21:21:53.426045	PHANTOM_AGED	0.13571315999999999934999550532666034996509552001953125
66	\N	MANAUSDT	binance	sell	615.00000000	0.32450000	0.31890000	0.00000000	\N	t	0.33099000	f	\N	t	\N	\N	closed	2025-10-08 23:21:36.146054+00	2025-10-09 01:37:59.492291+00	2025-10-09 01:37:59.492291+00	10.00	\N	\N	0.0000	f	2025-10-08 23:21:36.146054	PHANTOM_CLEANUP	3.1364999999999998436805981327779591083526611328125
52	\N	HBARUSDT	binance	sell	908.00000000	0.21909000	0.21790000	0.00000000	\N	t	0.22347180	f	\N	t	\N	\N	closed	2025-10-08 22:36:13.379777+00	2025-10-09 01:37:59.759885+00	2025-10-09 01:37:59.759885+00	10.00	\N	\N	0.0000	f	2025-10-08 22:36:13.379777	PHANTOM_CLEANUP	0.402480000000000004423128530106623657047748565673828125
53	\N	HOTUSDT	binance	sell	224971.00000000	0.00088800	0.00088000	0.00000000	\N	t	0.00090576	f	\N	t	\N	\N	closed	2025-10-08 22:36:20.084266+00	2025-10-09 01:37:59.938819+00	2025-10-09 01:37:59.938819+00	10.00	\N	\N	0.0000	f	2025-10-08 22:36:20.084266	PHANTOM_CLEANUP	0.071225819999999995246753314859233796596527099609375
31	\N	DOGEUSDT	binance	sell	773.00000000	0.25854000	0.25599000	0.00000000	\N	t	0.26371080	f	\N	f	\N	\N	closed	2025-10-08 20:36:14.720087+00	2025-10-08 23:39:58.840686+00	2025-10-08 23:39:58.840686+00	10.00	\N	\N	0.0000	f	2025-10-08 20:36:14.720087	PHANTOM_CLEANUP	1.9479599999999999138111661522998474538326263427734375
54	\N	APTUSDT	binance	sell	38.00000000	5.17690000	5.12190000	0.00000000	\N	t	5.28043800	f	\N	t	\N	\N	closed	2025-10-08 22:36:26.194048+00	2025-10-09 01:38:00.10213+00	2025-10-09 01:38:00.10213+00	10.00	\N	\N	0.0000	f	2025-10-08 22:36:26.194048	PHANTOM_CLEANUP	2.174565579999999886950945438002236187458038330078125
102	\N	FLUIDUSDT	binance	sell	30.00000000	6.59500000	6.51500000	0.00000000	\N	t	6.72690000	f	\N	t	\N	\N	closed	2025-10-09 02:21:12.359443+00	2025-10-09 03:13:55.065149+00	2025-10-09 03:13:55.065149+00	10.00	\N	\N	0.0000	f	2025-10-09 02:21:12.359443	PHANTOM_CLEANUP	2.618619600000000158246393766603432595729827880859375
93	\N	XAIUSDT	binance	sell	4826.00000000	0.04139000	0.04061000	0.00000000	\N	t	0.04221780	f	\N	t	\N	\N	closed	2025-10-09 01:21:38.779741+00	2025-10-09 03:13:55.330213+00	2025-10-09 03:13:55.330213+00	10.00	\N	\N	0.0000	f	2025-10-09 01:21:38.779741	PHANTOM_CLEANUP	4.6619159999999997268105289549566805362701416015625
110	\N	CAKEUSDT	binance	sell	51.00000000	3.85049410	4.00530000	0.00000000	\N	t	3.92750398	f	\N	t	\N	\N	closed	2025-10-09 02:36:38.327621+00	2025-10-09 03:13:55.514358+00	2025-10-09 03:13:55.514358+00	10.00	\N	\N	0.0000	f	2025-10-09 02:36:38.327621	PHANTOM_CLEANUP	-4.0650003899999997969416654086671769618988037109375
48	\N	MTLUSDT	binance	sell	313.00000000	0.63580000	0.63287331	0.00000000	\N	t	0.64851600	f	\N	t	\N	\N	closed	2025-10-08 21:51:26.235346+00	2025-10-09 00:55:24.345759+00	2025-10-09 00:55:24.345759+00	10.00	\N	\N	0.0000	f	2025-10-08 21:51:26.235346	PHANTOM_CLEANUP	0.1814547800000000099540642395368195138871669769287109375
10	\N	GASUSDT	binance	sell	65.00000000	3.06000000	3.05500000	0.00000000	\N	t	3.12120000	f	\N	f	\N	\N	closed	2025-10-08 18:36:27.976788+00	2025-10-08 21:41:06.640868+00	2025-10-08 21:41:06.640868+00	10.00	\N	\N	0.0000	f	2025-10-08 18:36:27.976788	PHANTOM_CLEANUP	0.10799999999999999877875467291232780553400516510009765625
58	\N	SKATEUSDT	binance	sell	3752.00000000	0.05312100	0.05297034	0.00000000	\N	t	0.05418342	f	\N	t	\N	\N	closed	2025-10-08 22:51:20.424104+00	2025-10-09 02:09:07.961796+00	2025-10-09 02:09:07.961796+00	10.00	\N	\N	0.0000	f	2025-10-08 22:51:20.424104	PHANTOM_AGED	0.56527632000000005429996008388116024434566497802734375
59	\N	FLUIDUSDT	binance	sell	30.00000000	6.63800000	6.62800000	0.00000000	\N	t	6.77076000	f	\N	t	\N	\N	closed	2025-10-08 22:51:26.685195+00	2025-10-09 02:09:52.760422+00	2025-10-09 02:09:52.760422+00	10.00	\N	\N	0.0000	f	2025-10-08 22:51:26.685195	PHANTOM_CLEANUP	0.2141762799999999966615860103047452867031097412109375
69	\N	HFTUSDT	binance	sell	2675.00000000	0.07424000	0.07270000	0.00000000	\N	t	0.07572480	f	\N	t	\N	\N	closed	2025-10-08 23:36:22.84664+00	2025-10-09 02:40:58.025589+00	2025-10-09 02:40:58.025589+00	10.00	\N	\N	0.0000	f	2025-10-08 23:36:22.84664	PHANTOM_AGED	3.0893575000000002006572685786522924900054931640625
187	\N	BSUUSDT	bybit	short	1982.00000000	0.10088000	\N	\N	\N	t	0.10289760	f	\N	t	\N	\N	active	2025-10-09 11:25:06.634075+00	\N	2025-10-09 15:43:42.53392+00	1.00	\N	\N	\N	f	2025-10-09 11:25:06.634075	\N	0
182	\N	GORKUSDT	bybit	short	7660.00000000	0.02609000	\N	\N	\N	t	0.02661180	f	\N	t	\N	\N	active	2025-10-09 10:53:07.681076+00	\N	2025-10-09 15:43:42.702981+00	1.00	\N	\N	\N	f	2025-10-09 10:53:07.681076	\N	0
180	\N	TAKEUSDT	binance	sell	696.00000000	0.28689000	0.28107000	0.00000000	\N	t	0.29262780	f	\N	t	\N	\N	closed	2025-10-09 10:51:20.399665+00	2025-10-09 11:09:10.958022+00	2025-10-09 11:09:10.958022+00	10.00	\N	\N	0.0000	t	2025-10-09 10:51:20.399665	PHANTOM_CLEANUP	3.06111936000000017799038687371648848056793212890625
179	\N	BOBAUSDT	bybit	short	1980.00000000	0.10097000	\N	\N	\N	t	0.10298940	f	\N	t	\N	\N	active	2025-10-09 10:45:03.940818+00	\N	2025-10-09 15:43:43.045663+00	1.00	\N	\N	\N	f	2025-10-09 10:45:03.940818	\N	0
166	\N	DODOUSDT	bybit	short	3969.00000000	0.05038000	\N	\N	\N	t	0.05138760	f	\N	t	\N	\N	active	2025-10-09 09:23:05.72623+00	\N	2025-10-09 15:43:43.215684+00	1.00	\N	\N	\N	f	2025-10-09 09:23:05.72623	\N	0
165	\N	L3USDT	bybit	short	1000.00000000	0.03256500	\N	\N	\N	t	0.03321630	f	\N	t	\N	\N	active	2025-10-09 08:31:06.611415+00	\N	2025-10-09 15:43:43.428408+00	1.00	\N	\N	\N	f	2025-10-09 08:31:06.611415	\N	0
168	\N	ALCHUSDT	binance	sell	2675.00000000	0.07447000	0.07602000	0.00000000	\N	t	0.07595940	f	\N	t	\N	\N	closed	2025-10-09 09:36:19.327127+00	2025-10-09 10:14:19.53797+00	2025-10-09 10:14:19.53797+00	10.00	\N	\N	0.0000	f	2025-10-09 09:36:19.327127	PHANTOM_CLEANUP	-4.4581549999999996458655004971660673618316650390625
188	\N	REZUSDT	binance	sell	14245.00000000	0.01397000	0.01414000	0.00000000	\N	t	0.01424940	f	\N	t	\N	\N	closed	2025-10-09 11:36:10.070482+00	2025-10-09 12:28:19.529556+00	2025-10-09 12:28:32.200074+00	10.00	\N	\N	0.0000	f	2025-10-09 11:36:10.070482	PHANTOM_CLEANUP	-4.2735000000000002984279490192420780658721923828125
123	\N	GRTUSDT	binance	sell	2443.00000000	0.08144000	0.08123000	0.00000000	\N	t	0.08306880	f	\N	t	\N	\N	closed	2025-10-09 03:51:27.589+00	2025-10-09 07:38:31.033127+00	2025-10-09 07:38:31.033127+00	10.00	\N	\N	0.0000	f	2025-10-09 03:51:27.589	PHANTOM_CLEANUP	0.1923600000000000032063240951174520887434482574462890625
13	\N	LISTAUSDT	binance	sell	394.00000000	0.50622540	0.51750000	0.00000000	\N	t	0.51634991	f	\N	f	\N	\N	closed	2025-10-08 18:36:51.693079+00	2025-10-08 19:34:59.015553+00	2025-10-08 19:34:59.015553+00	10.00	\N	\N	0.0000	f	2025-10-08 18:36:51.693079	PHANTOM_CLEANUP	-4.51551580000000019055050870520062744617462158203125
11	\N	QNTUSDT	binance	sell	1.00000000	102.52000000	102.26000000	0.00000000	\N	t	104.57040000	f	\N	f	\N	\N	closed	2025-10-08 18:36:34.453458+00	2025-10-08 21:41:06.904341+00	2025-10-08 21:41:06.904341+00	10.00	\N	\N	0.0000	f	2025-10-08 18:36:34.453458	PHANTOM_CLEANUP	0.251363500000000017475798586019664071500301361083984375
49	\N	ARIAUSDT	binance	sell	1345.00000000	0.14860000	0.14677000	0.00000000	\N	t	0.15157200	f	\N	f	\N	\N	closed	2025-10-08 21:51:32.721001+00	2025-10-08 22:14:32.450267+00	2025-10-08 22:14:32.450267+00	10.00	\N	\N	0.0000	f	2025-10-08 21:51:32.721001	PHANTOM_CLEANUP	3.2071928500000002060232873191125690937042236328125
75	\N	LQTYUSDT	binance	sell	270.00000000	0.73600000	0.74670000	0.00000000	\N	t	0.75072000	f	\N	t	\N	\N	closed	2025-10-08 23:51:45.44998+00	2025-10-09 00:11:02.057405+00	2025-10-09 00:11:02.057405+00	10.00	\N	\N	0.0000	f	2025-10-08 23:51:45.44998	PHANTOM_CLEANUP	-4.11075000000000034816594052244909107685089111328125
107	\N	ORDERUSDT	binance	sell	610.00000000	0.32754000	0.32406000	0.00000000	\N	t	0.33409080	f	\N	t	\N	\N	closed	2025-10-09 02:36:18.328088+00	2025-10-09 05:40:52.121217+00	2025-10-09 05:40:52.121217+00	10.00	\N	\N	0.0000	f	2025-10-09 02:36:18.328088	PHANTOM_CLEANUP	2.27983840000000004266667019692249596118927001953125
124	\N	ARPAUSDT	binance	sell	9569.00000000	0.02085000	0.02078000	0.00000000	\N	t	0.02126700	f	\N	t	\N	\N	closed	2025-10-09 03:51:33.707568+00	2025-10-09 08:10:17.905128+00	2025-10-09 08:10:17.905128+00	10.00	\N	\N	0.0000	f	2025-10-09 03:51:33.707568	PHANTOM_CLEANUP	0.2468430600000000030291857910924591124057769775390625
111	\N	LTCUSDT	binance	sell	1.00000000	117.16145000	119.17000000	0.00000000	\N	t	119.50467900	f	\N	t	\N	\N	closed	2025-10-09 02:51:11.148917+00	2025-10-09 03:55:27.819936+00	2025-10-09 03:55:27.819936+00	10.00	\N	\N	0.0000	f	2025-10-09 02:51:11.148917	PHANTOM_CLEANUP	-2.4595261900000000565569280297495424747467041015625
17	\N	SUPERUSDT	binance	sell	337.00000000	0.59050000	0.58900000	0.00000000	\N	t	0.60231000	f	\N	f	\N	\N	closed	2025-10-08 18:51:32.13423+00	2025-10-08 22:00:19.170998+00	2025-10-08 22:00:19.170998+00	10.00	\N	\N	0.0000	f	2025-10-08 18:51:32.13423	PHANTOM_AGED	0.257500000000000006661338147750939242541790008544921875
9	\N	HOOKUSDT	binance	sell	1937.00000000	0.10281000	0.10249000	0.00000000	\N	t	0.10486620	f	\N	f	\N	\N	closed	2025-10-08 18:36:20.746763+00	2025-10-08 21:49:36.446486+00	2025-10-08 21:49:36.446486+00	10.00	\N	\N	0.0000	f	2025-10-08 18:36:20.746763	PHANTOM_AGED	0.27669171999999997435537579804076813161373138427734375
202	\N	SLERFUSDT	binance	sell	2497.00000000	0.07965000	0.07809464	\N	\N	t	0.08124300	f	\N	t	\N	\N	closed	2025-10-09 12:51:33.55731+00	\N	2025-10-09 15:59:51.405688+00	10.00	\N	\N	\N	f	2025-10-09 12:51:33.55731	\N	3.88373392000000006163418220239691436290740966796875
108	\N	SUIUSDT	binance	sell	57.00000000	3.46690000	3.46140000	0.00000000	\N	t	3.53623800	f	\N	t	\N	\N	closed	2025-10-09 02:36:25.105328+00	2025-10-09 06:23:33.893258+00	2025-10-09 06:23:33.893258+00	10.00	\N	\N	0.0000	f	2025-10-09 02:36:25.105328	PHANTOM_CLEANUP	0.0260080799999999993932231490134654450230300426483154296875
6	\N	KSMUSDT	binance	sell	13.00000000	15.07500000	15.06300000	0.00000000	\N	t	15.37650000	f	\N	f	\N	\N	closed	2025-10-08 18:21:12.889668+00	2025-10-08 21:28:30.944298+00	2025-10-08 21:28:30.944298+00	10.00	\N	\N	0.0000	f	2025-10-08 18:21:12.889668	PHANTOM_AGED	0.0170315299999999995861355017723326454870402812957763671875
7	\N	ZRCUSDT	binance	sell	9474.00000000	0.02111000	0.02102000	0.00000000	\N	t	0.02153220	f	\N	f	\N	\N	closed	2025-10-08 18:21:19.164601+00	2025-10-08 21:28:31.588182+00	2025-10-08 21:28:31.588182+00	10.00	\N	\N	0.0000	f	2025-10-08 18:21:19.164601	PHANTOM_AGED	0.2174303999999999958969709723533014766871929168701171875
8	\N	XTZUSDT	binance	sell	286.00000000	0.69700000	0.69100000	0.00000000	\N	t	0.71094000	f	\N	f	\N	\N	closed	2025-10-08 18:21:25.382201+00	2025-10-08 21:28:32.574191+00	2025-10-08 21:28:32.574191+00	10.00	\N	\N	0.0000	f	2025-10-08 18:21:25.382201	PHANTOM_AGED	1.8520730800000000382254938813275657594203948974609375
117	\N	KMNOUSDT	binance	sell	2678.00000000	0.07466000	0.07355000	0.00000000	\N	t	0.07615320	f	\N	t	\N	\N	closed	2025-10-09 03:36:21.041889+00	2025-10-09 06:23:34.169341+00	2025-10-09 06:23:34.169341+00	10.00	\N	\N	0.0000	f	2025-10-09 03:36:21.041889	PHANTOM_CLEANUP	2.38342000000000009407585821463726460933685302734375
109	\N	WLDUSDT	binance	sell	161.00000000	1.23690000	1.23110000	0.00000000	\N	t	1.26163800	f	\N	t	\N	\N	closed	2025-10-09 02:36:31.759714+00	2025-10-09 06:12:51.04728+00	2025-10-09 06:12:51.04728+00	10.00	\N	\N	0.0000	f	2025-10-09 02:36:31.759714	PHANTOM_CLEANUP	0.4608727200000000134849642563494853675365447998046875
118	\N	BIOUSDT	binance	sell	1588.00000000	0.12544000	0.12227000	0.00000000	\N	t	0.12794880	f	\N	t	\N	\N	closed	2025-10-09 03:36:28.652247+00	2025-10-09 06:12:51.322173+00	2025-10-09 06:12:51.322173+00	10.00	\N	\N	0.0000	f	2025-10-09 03:36:28.652247	PHANTOM_CLEANUP	5.09748000000000001108446667785756289958953857421875
106	\N	ALTUSDT	binance	sell	7034.00000000	0.02841000	0.02837000	0.00000000	\N	t	0.02897820	f	\N	t	\N	\N	closed	2025-10-09 02:21:42.033982+00	2025-10-09 06:12:51.498435+00	2025-10-09 06:12:51.498435+00	10.00	\N	\N	0.0000	f	2025-10-09 02:21:42.033982	PHANTOM_CLEANUP	0.5312780200000000174753722603782080113887786865234375
143	\N	STEEMUSDT	binance	sell	1658.00000000	0.12039000	0.11875000	0.00000000	\N	t	0.12279780	f	\N	t	\N	\N	closed	2025-10-09 05:51:19.99062+00	2025-10-09 08:59:26.861727+00	2025-10-09 08:59:26.861727+00	10.00	\N	\N	0.0000	f	2025-10-09 05:51:19.99062	PHANTOM_AGED	3.059126060000000091321226136642508208751678466796875
72	\N	REDUSDT	binance	buy	426.00000000	0.46940000	0.47000000	0.00000000	\N	t	0.47878800	f	\N	t	\N	\N	closed	2025-10-08 23:51:12.402987+00	2025-10-09 04:58:03.006228+00	2025-10-09 04:58:03.006228+00	10.00	\N	\N	0.0000	f	2025-10-08 23:51:12.402987	PHANTOM_AGED	0.1620000000000000051070259132757200859487056732177734375
84	\N	TOWNSUSDT	binance	sell	10723.00000000	0.01865000	0.01862716	0.00000000	\N	t	0.01902300	f	\N	t	\N	\N	closed	2025-10-09 00:36:41.212609+00	2025-10-09 01:48:38.771569+00	2025-10-09 01:48:38.771569+00	10.00	\N	\N	0.0000	f	2025-10-09 00:36:41.212609	PHANTOM_CLEANUP	0.003859959999999999953612661585111709428019821643829345703125
2	\N	EIGENUSDT	binance	sell	103.00000000	1.92310000	1.89900000	0.00000000	\N	t	1.96156200	f	\N	f	\N	\N	closed	2025-10-08 18:06:16.280062+00	2025-10-08 20:58:49.900424+00	2025-10-08 20:58:49.900424+00	10.00	\N	\N	0.0000	f	2025-10-08 18:06:16.280062	PHANTOM_CLEANUP	2.3483999999999998209432305884547531604766845703125
57	\N	EPTUSDT	binance	sell	34211.00000000	0.00583150	0.00564800	0.00000000	\N	t	0.00594813	f	\N	t	\N	\N	closed	2025-10-08 22:51:11.761197+00	2025-10-09 00:29:18.039299+00	2025-10-09 00:29:18.039299+00	10.00	\N	\N	0.0000	f	2025-10-08 22:51:11.761197	PHANTOM_CLEANUP	6.31842959000000004010644261143170297145843505859375
51	\N	IDOLUSDT	binance	sell	5305.00000000	0.03758000	0.03833000	0.00000000	\N	t	0.03833160	f	\N	f	\N	\N	closed	2025-10-08 22:21:11.779498+00	2025-10-08 23:45:44.064692+00	2025-10-08 23:45:44.064692+00	10.00	\N	\N	0.0000	f	2025-10-08 22:21:11.779498	PHANTOM_CLEANUP	-3.9787499999999997868371792719699442386627197265625
15	\N	ARBUSDT	binance	sell	459.00000000	0.43420000	0.43280000	0.00000000	\N	t	0.44288400	f	\N	f	\N	\N	closed	2025-10-08 18:51:19.64736+00	2025-10-08 22:00:18.025768+00	2025-10-08 22:00:18.025768+00	10.00	\N	\N	0.0000	f	2025-10-08 18:51:19.64736	PHANTOM_AGED	0.1199800000000000033129055054814671166241168975830078125
16	\N	EDUUSDT	binance	sell	1352.00000000	0.14750000	0.14720000	0.00000000	\N	t	0.15045000	f	\N	f	\N	\N	closed	2025-10-08 18:51:26.096308+00	2025-10-08 22:00:18.635969+00	2025-10-08 22:00:18.635969+00	10.00	\N	\N	0.0000	f	2025-10-08 18:51:26.096308	PHANTOM_AGED	0.509325440000000018159198589273728430271148681640625
45	\N	FISUSDT	binance	sell	2366.00000000	0.08450000	0.08376000	0.00000000	\N	t	0.08619000	f	\N	t	\N	\N	closed	2025-10-08 21:36:24.704112+00	2025-10-09 00:43:41.344913+00	2025-10-09 00:43:41.344913+00	10.00	\N	\N	0.0000	f	2025-10-08 21:36:24.704112	PHANTOM_AGED	1.7509819600000000594519633523304946720600128173828125
44	\N	BIDUSDT	binance	sell	2864.00000000	0.06966531	0.06896000	0.00000000	\N	t	0.07105862	f	\N	t	\N	\N	closed	2025-10-08 21:36:18.844427+00	2025-10-09 00:43:41.959581+00	2025-10-09 00:43:41.959581+00	10.00	\N	\N	0.0000	f	2025-10-08 21:36:18.844427	PHANTOM_AGED	2.46258175999999995298139765509404242038726806640625
47	\N	SFPUSDT	binance	sell	371.00000000	0.53880000	0.53660000	0.00000000	\N	t	0.54957600	f	\N	t	\N	\N	closed	2025-10-08 21:51:19.525621+00	2025-10-09 01:15:54.933243+00	2025-10-09 01:15:54.933243+00	10.00	\N	\N	0.0000	f	2025-10-08 21:51:19.525621	PHANTOM_AGED	0.3127860399999999874154354984057135879993438720703125
35	\N	LPTUSDT	binance	sell	30.00000000	6.43800000	6.41600000	0.00000000	\N	t	6.56676000	f	\N	t	\N	\N	closed	2025-10-08 20:36:43.287567+00	2025-10-09 01:15:57.721535+00	2025-10-09 01:15:57.721535+00	10.00	\N	\N	0.0000	f	2025-10-08 20:36:43.287567	PHANTOM_AGED	0.06489999999999999935607064571740920655429363250732421875
14	\N	TUSDT	binance	sell	13114.00000000	0.01523000	0.01518000	0.00000000	\N	t	0.01553460	f	\N	t	\N	\N	closed	2025-10-08 18:51:13.348185+00	2025-10-09 01:15:58.257657+00	2025-10-09 01:15:58.257657+00	10.00	\N	\N	0.0000	f	2025-10-08 18:51:13.348185	PHANTOM_AGED	0.2288392999999999954940932411773246712982654571533203125
144	\N	1000RATSUSDT	binance	sell	7610.00000000	0.02626000	0.02591000	0.00000000	\N	t	0.02678520	f	\N	t	\N	\N	closed	2025-10-09 05:51:27.687611+00	2025-10-09 07:49:09.234203+00	2025-10-09 07:49:09.234203+00	10.00	\N	\N	0.0000	t	2025-10-09 05:51:27.687611	PHANTOM_CLEANUP	3.349693699999999996208543961984105408191680908203125
174	\N	APTUSDT	binance	sell	40.00000000	4.95000000	4.97110000	0.00000000	\N	t	5.04900000	f	\N	t	\N	\N	closed	2025-10-09 10:21:19.264451+00	2025-10-09 10:45:10.457865+00	2025-10-09 10:45:10.457865+00	10.00	\N	\N	0.0000	t	2025-10-09 10:21:19.264451	PHANTOM_CLEANUP	-0.05079999999999999793498517419720883481204509735107421875
177	\N	FLMUSDT	binance	sell	8032.00000000	0.02480000	0.02465740	0.00000000	\N	t	0.02529600	f	\N	t	\N	\N	closed	2025-10-09 10:36:34.095864+00	2025-10-09 13:44:29.315278+00	2025-10-09 13:44:29.315278+00	10.00	\N	\N	0.0000	f	2025-10-09 10:36:34.095864	PHANTOM_AGED	0.1658438000000000134281918917622533626854419708251953125
183	\N	FLOWUSDT	binance	sell	558.00000000	0.35500000	0.36200000	0.00000000	\N	t	0.36210000	f	\N	t	\N	\N	closed	2025-10-09 11:21:13.817329+00	2025-10-09 12:45:21.491042+00	2025-10-09 12:45:25.397812+00	10.00	\N	\N	0.0000	f	2025-10-09 11:21:13.817329	PHANTOM_CLEANUP	-3.685863420000000001408579919370822608470916748046875
176	\N	IPUSDT	binance	sell	22.00000000	8.93084450	9.11970000	0.00000000	\N	t	9.10946139	f	\N	t	\N	\N	closed	2025-10-09 10:36:20.302062+00	2025-10-09 12:45:21.905023+00	2025-10-09 12:45:27.050397+00	10.00	\N	\N	0.0000	f	2025-10-09 10:36:20.302062	PHANTOM_CLEANUP	-4.59179071999999965925098877050913870334625244140625
65	\N	RVNUSDT	binance	sell	16920.00000000	0.01179000	0.01169000	0.00000000	\N	t	0.01202580	f	\N	t	\N	\N	closed	2025-10-08 23:21:29.631925+00	2025-10-09 02:30:17.490346+00	2025-10-09 02:30:17.490346+00	10.00	\N	\N	0.0000	f	2025-10-08 23:21:29.631925	PHANTOM_AGED	1.6919999999999999484856516573927365243434906005859375
64	\N	COMPUSDT	binance	sell	4.00000000	42.65000000	42.11000000	0.00000000	\N	t	43.50300000	f	\N	t	\N	\N	closed	2025-10-08 23:21:23.384119+00	2025-10-09 02:30:18.13096+00	2025-10-09 02:30:18.13096+00	10.00	\N	\N	0.0000	f	2025-10-08 23:21:23.384119	PHANTOM_AGED	2.160000000000000142108547152020037174224853515625
63	\N	NEOUSDT	binance	sell	31.00000000	6.27039000	6.21145370	0.00000000	\N	t	6.39579780	f	\N	t	\N	\N	closed	2025-10-08 23:21:17.234302+00	2025-10-09 02:30:18.64697+00	2025-10-09 02:30:18.64697+00	10.00	\N	\N	0.0000	f	2025-10-08 23:21:17.234302	PHANTOM_AGED	1.827085129999999946193156574736349284648895263671875
95	\N	CHZUSDT	binance	sell	4765.00000000	0.04192000	0.04148000	0.00000000	\N	t	0.04275840	f	\N	t	\N	\N	closed	2025-10-09 01:36:29.276091+00	2025-10-09 03:03:24.420996+00	2025-10-09 03:03:24.420996+00	10.00	\N	\N	0.0000	f	2025-10-09 01:36:29.276091	PHANTOM_CLEANUP	2.42862519999999992847961038933135569095611572265625
104	\N	MAVUSDT	binance	sell	3857.00000000	0.05176000	0.05077000	0.00000000	\N	t	0.05279520	f	\N	t	\N	\N	closed	2025-10-09 02:21:28.241633+00	2025-10-09 03:03:24.70156+00	2025-10-09 03:03:24.70156+00	10.00	\N	\N	0.0000	f	2025-10-09 02:21:28.241633	PHANTOM_CLEANUP	5.12117032000000005353967935661785304546356201171875
100	\N	LPTUSDT	binance	sell	31.00000000	6.39700000	6.31900000	0.00000000	\N	t	6.52494000	f	\N	t	\N	\N	closed	2025-10-09 01:51:31.38785+00	2025-10-09 03:03:25.254269+00	2025-10-09 03:03:25.254269+00	10.00	\N	\N	0.0000	f	2025-10-09 01:51:31.38785	PHANTOM_CLEANUP	0.08176460000000000671871447366356733255088329315185546875
103	\N	DYDXUSDT	binance	sell	339.00000000	0.58808080	0.58200000	0.00000000	\N	t	0.59984242	f	\N	t	\N	\N	closed	2025-10-09 02:21:21.451573+00	2025-10-09 03:03:25.437811+00	2025-10-09 03:03:25.437811+00	10.00	\N	\N	0.0000	f	2025-10-09 02:21:21.451573	PHANTOM_CLEANUP	2.00465276999999986173861543647944927215576171875
94	\N	IOTAUSDT	binance	sell	1084.00000000	0.18440000	0.18180000	0.00000000	\N	t	0.18808800	f	\N	t	\N	\N	closed	2025-10-09 01:36:22.947541+00	2025-10-09 03:03:25.625476+00	2025-10-09 03:03:25.625476+00	10.00	\N	\N	0.0000	f	2025-10-09 01:36:22.947541	PHANTOM_CLEANUP	3.14360000000000017195134205394424498081207275390625
105	\N	ILVUSDT	binance	sell	13.00000000	14.46300000	14.21800000	0.00000000	\N	t	14.75226000	f	\N	t	\N	\N	closed	2025-10-09 02:21:34.497832+00	2025-10-09 03:03:25.807305+00	2025-10-09 03:03:25.807305+00	10.00	\N	\N	0.0000	f	2025-10-09 02:21:34.497832	PHANTOM_CLEANUP	4.10180550000000021526602722587995231151580810546875
194	\N	YALAUSDT	binance	sell	1943.00000000	0.10270000	0.10490000	0.00000000	\N	t	0.10475400	f	\N	t	\N	\N	closed	2025-10-09 11:51:37.733807+00	2025-10-09 12:45:21.733344+00	2025-10-09 12:45:23.212984+00	10.00	\N	\N	0.0000	f	2025-10-09 11:51:37.733807	PHANTOM_CLEANUP	-4.1405718599999996598626239574514329433441162109375
161	\N	EGLDUSDT	binance	sell	15.00000000	13.15300000	12.94541425	0.00000000	\N	t	13.41606000	f	\N	t	\N	\N	closed	2025-10-09 07:37:16.331764+00	2025-10-09 08:41:49.441445+00	2025-10-09 08:41:49.441445+00	10.00	\N	\N	0.0000	t	2025-10-09 07:37:16.331764	PHANTOM_CLEANUP	0.2075857500000000133155708681442774832248687744140625
130	\N	GMTUSDT	binance	sell	5252.00000000	0.03800000	0.03787000	0.00000000	\N	t	0.03876000	f	\N	t	\N	\N	closed	2025-10-09 04:21:41.208248+00	2025-10-09 07:40:11.614914+00	2025-10-09 07:40:11.614914+00	10.00	\N	\N	0.0000	f	2025-10-09 04:21:41.208248	PHANTOM_AGED	0.389620880000000002763016482276725582778453826904296875
61	\N	GLMUSDT	binance	sell	901.00000000	0.22117000	0.21914000	0.00000000	\N	t	0.22559340	f	\N	t	\N	\N	closed	2025-10-08 22:51:39.071968+00	2025-10-09 01:58:26.408815+00	2025-10-09 01:58:26.408815+00	10.00	\N	\N	0.0000	f	2025-10-08 22:51:39.071968	PHANTOM_AGED	1.829029999999999933635308480006642639636993408203125
145	\N	TNSRUSDT	binance	sell	2012.00000000	0.09940000	0.09820000	0.00000000	\N	t	0.10138800	f	\N	t	\N	\N	closed	2025-10-09 05:51:34.958584+00	2025-10-09 07:49:08.94917+00	2025-10-09 07:49:08.94917+00	10.00	\N	\N	0.0000	f	2025-10-09 05:51:34.958584	PHANTOM_CLEANUP	2.133725999999999789480398248997516930103302001953125
189	\N	BTRUSDT	binance	sell	2538.00000000	0.07880000	0.07760000	0.00000000	\N	t	0.08037600	f	\N	t	\N	\N	closed	2025-10-09 11:36:17.457653+00	2025-10-09 13:19:02.517713+00	2025-10-09 13:19:02.517713+00	10.00	\N	\N	0.0000	f	2025-10-09 11:36:17.457653	PHANTOM_CLEANUP	3.943011419999999933594381218426860868930816650390625
77	\N	XLMUSDT	binance	sell	515.00000000	0.38628000	0.38121000	0.00000000	\N	t	0.39400560	f	\N	t	\N	\N	closed	2025-10-09 00:21:17.698745+00	2025-10-09 03:03:24.900182+00	2025-10-09 03:03:24.900182+00	10.00	\N	\N	0.0000	f	2025-10-09 00:21:17.698745	PHANTOM_CLEANUP	2.53087995000000010037410902441479265689849853515625
85	\N	RSRUSDT	binance	sell	33074.00000000	0.00603200	0.00586300	0.00000000	\N	t	0.00615264	f	\N	t	\N	\N	closed	2025-10-09 00:51:13.662836+00	2025-10-09 03:03:25.059646+00	2025-10-09 03:03:25.059646+00	10.00	\N	\N	0.0000	t	2025-10-09 00:51:13.662836	PHANTOM_CLEANUP	5.9533199999999997231725501478649675846099853515625
86	\N	ARUSDT	binance	sell	33.00000000	5.97100000	5.84700000	0.00000000	\N	t	6.09042000	f	\N	t	\N	\N	closed	2025-10-09 00:51:21.142458+00	2025-10-09 03:03:26.006736+00	2025-10-09 03:03:26.006736+00	10.00	\N	\N	0.0000	f	2025-10-09 00:51:21.142458	PHANTOM_CLEANUP	4.56354459000000023394250092678703367710113525390625
91	\N	STXUSDT	binance	sell	330.00000000	0.60430000	0.59640000	0.00000000	\N	t	0.61638600	f	\N	t	\N	\N	closed	2025-10-09 01:21:25.124257+00	2025-10-09 03:03:26.197112+00	2025-10-09 03:03:26.197112+00	10.00	\N	\N	0.0000	f	2025-10-09 01:21:25.124257	PHANTOM_CLEANUP	3.06899999999999995026200849679298698902130126953125
92	\N	AGLDUSDT	binance	sell	357.00000000	0.55890000	0.54930000	0.00000000	\N	t	0.57007800	f	\N	t	\N	\N	closed	2025-10-09 01:21:32.053566+00	2025-10-09 03:03:26.385315+00	2025-10-09 03:03:26.385315+00	10.00	\N	\N	0.0000	f	2025-10-09 01:21:32.053566	PHANTOM_CLEANUP	3.299751000000000100698116511921398341655731201171875
27	\N	LQTYUSDT	binance	sell	273.00000000	0.72630000	0.74130000	0.00000000	\N	t	0.74082600	f	\N	f	\N	\N	closed	2025-10-08 19:51:18.651138+00	2025-10-08 23:34:07.029956+00	2025-10-08 23:34:18.394751+00	10.00	\N	\N	0.0000	f	2025-10-08 19:51:18.651138	PHANTOM_AGED	-4.02910326000000029722514227614738047122955322265625
56	\N	SPXUSDT	binance	sell	126.00000000	1.58130000	1.55520000	0.00000000	\N	t	1.61292600	f	\N	f	\N	\N	closed	2025-10-08 22:36:38.18528+00	2025-10-08 23:34:19.021699+00	2025-10-08 23:34:19.021699+00	10.00	\N	\N	0.0000	f	2025-10-08 22:36:38.18528	PHANTOM_CLEANUP	3.931200000000000027711166694643907248973846435546875
172	\N	LIGHTUSDT	binance	sell	224.00000000	0.88659130	0.90637000	0.00000000	\N	t	0.90432313	f	\N	t	\N	\N	closed	2025-10-09 09:51:45.97593+00	2025-10-09 10:45:10.715341+00	2025-10-09 10:45:10.715341+00	10.00	\N	\N	0.0000	f	2025-10-09 09:51:45.97593	PHANTOM_CLEANUP	-4.10114207999999980103211782989092171192169189453125
191	\N	BERAUSDT	binance	sell	75.00000000	2.66100000	2.71400000	0.00000000	\N	t	2.71422000	f	\N	t	\N	\N	closed	2025-10-09 11:51:17.79491+00	2025-10-09 12:39:41.036198+00	2025-10-09 12:39:41.036198+00	10.00	\N	\N	0.0000	f	2025-10-09 11:51:17.79491	PHANTOM_CLEANUP	-3.45000000000000017763568394002504646778106689453125
88	\N	SKYUSDT	binance	sell	2907.00000000	0.06855000	0.06745000	\N	\N	t	0.06992100	f	\N	t	\N	\N	closed	2025-10-09 00:51:38.269976+00	\N	2025-10-09 02:30:49.412428+00	10.00	\N	\N	\N	f	2025-10-09 00:51:38.269976	\N	3.19770000000000020889956431346945464611053466796875
29	\N	CYBERUSDT	binance	sell	123.00000000	1.60300000	1.63600000	0.00000000	\N	t	1.63506000	f	\N	f	\N	\N	closed	2025-10-08 19:51:30.80941+00	2025-10-08 20:16:46.759968+00	2025-10-08 20:16:46.759968+00	10.00	\N	\N	0.0000	f	2025-10-08 19:51:30.80941	PHANTOM_CLEANUP	-3.901026180000000120884351417771540582180023193359375
215	\N	ONTUSDT	binance	sell	1633.90000000	0.12220000	0.12060000	0.00000000	\N	t	0.12464400	f	\N	t	\N	\N	closed	2025-10-09 13:51:21.937936+00	2025-10-09 15:49:01.893173+00	2025-10-09 15:49:01.893173+00	10.00	\N	\N	0.0000	f	2025-10-09 13:51:21.937936	PHANTOM_CLEANUP	2.478985750000000098935970527236349880695343017578125
208	\N	OGNUSDT	binance	sell	3436.00000000	0.05800000	0.05730000	0.00000000	\N	t	0.05916000	f	\N	t	\N	\N	closed	2025-10-09 13:21:44.073726+00	2025-10-09 15:49:02.047606+00	2025-10-09 15:49:02.047606+00	10.00	\N	\N	0.0000	f	2025-10-09 13:21:44.073726	PHANTOM_CLEANUP	2.06757863999999980109123498550616204738616943359375
210	\N	1000FLOKIUSDT	binance	sell	2131.00000000	0.09372000	0.09135441	\N	\N	t	0.09559440	f	\N	t	\N	\N	closed	2025-10-09 13:36:11.961387+00	\N	2025-10-09 15:01:16.38415+00	10.00	\N	\N	\N	t	2025-10-09 13:36:11.961387	\N	5.04107228999999978924506649491377174854278564453125
209	\N	1000SHIBUSDT	binance	sell	16561.00000000	0.01205700	0.01186771	\N	\N	t	0.01229814	f	\N	t	\N	\N	closed	2025-10-09 13:21:50.39976+00	\N	2025-10-09 15:01:16.639278+00	10.00	\N	\N	\N	t	2025-10-09 13:21:50.39976	\N	3.134831689999999948526010484783910214900970458984375
184	\N	SKYUSDT	binance	sell	3017.00000000	0.06624000	0.06611554	\N	\N	t	0.06756480	f	\N	t	\N	\N	closed	2025-10-09 11:21:20.543259+00	\N	2025-10-09 15:01:16.802816+00	10.00	\N	\N	\N	f	2025-10-09 11:21:20.543259	\N	0.033230820000000001190887388702321914024651050567626953125
150	\N	PYTHUSDT	binance	sell	1272.00000000	0.15713000	0.15364000	0.00000000	\N	t	0.16027260	f	\N	t	\N	\N	closed	2025-10-09 06:21:32.883219+00	2025-10-09 08:20:47.883895+00	2025-10-09 08:20:47.883895+00	10.00	\N	\N	0.0000	f	2025-10-09 06:21:32.883219	PHANTOM_CLEANUP	4.0068000000000001392663762089796364307403564453125
157	\N	PNUTUSDT	binance	sell	959.00000000	0.20838000	0.20515000	0.00000000	\N	t	0.21254760	f	\N	t	\N	\N	closed	2025-10-09 06:51:20.94344+00	2025-10-09 08:20:48.137111+00	2025-10-09 08:20:48.137111+00	10.00	\N	\N	0.0000	f	2025-10-09 06:51:20.94344	PHANTOM_CLEANUP	2.837038469999999978909954734263010323047637939453125
97	\N	TRXUSDT	binance	sell	586.00000000	0.34019000	0.33934000	0.00000000	\N	t	0.34699380	f	\N	t	\N	\N	closed	2025-10-09 01:51:11.986653+00	2025-10-09 05:19:20.316892+00	2025-10-09 05:19:20.316892+00	10.00	\N	\N	0.0000	f	2025-10-09 01:51:11.986653	PHANTOM_AGED	0.005121180000000000349935636023701590602286159992218017578125
19	\N	IDUSDT	binance	sell	1300.00000000	0.15340000	0.15302704	\N	\N	t	0.15646800	f	\N	f	\N	\N	closed	2025-10-08 19:22:12.138109+00	\N	2025-10-08 22:27:38.589956+00	10.00	\N	\N	\N	f	2025-10-08 19:22:12.138109	\N	0.105174719999999999320294818971888162195682525634765625
21	\N	BSVUSDT	binance	sell	7.00000000	25.82000000	25.71000000	0.00000000	\N	t	26.33640000	f	\N	f	\N	\N	closed	2025-10-08 19:22:24.609956+00	2025-10-08 23:05:29.099325+00	2025-10-08 23:05:29.099325+00	10.00	\N	\N	0.0000	f	2025-10-08 19:22:24.609956	PHANTOM_CLEANUP	0.63000000000000000444089209850062616169452667236328125
28	\N	YGGUSDT	binance	sell	1172.00000000	0.16940000	0.16890000	0.00000000	\N	t	0.17278800	f	\N	f	\N	\N	closed	2025-10-08 19:51:24.66417+00	2025-10-08 23:05:29.523679+00	2025-10-08 23:05:29.523679+00	10.00	\N	\N	0.0000	f	2025-10-08 19:51:24.66417	PHANTOM_CLEANUP	0.48179748000000000018872015061788260936737060546875
213	\N	GRASSUSDT	binance	sell	250.00000000	0.79740000	0.78382788	0.00000000	\N	t	0.81334800	f	\N	t	\N	\N	closed	2025-10-09 13:36:32.747636+00	2025-10-09 14:30:45.540441+00	2025-10-09 14:30:45.540441+00	10.00	\N	\N	0.0000	f	2025-10-09 13:36:32.747636	PHANTOM_CLEANUP	3.393029999999999990478727340814657509326934814453125
135	\N	ERAUSDT	binance	sell	385.00000000	0.51430000	0.50940000	0.00000000	\N	t	0.52458600	f	\N	t	\N	\N	closed	2025-10-09 04:51:12.546013+00	2025-10-09 07:59:44.346495+00	2025-10-09 07:59:44.346495+00	10.00	\N	\N	0.0000	f	2025-10-09 04:51:12.546013	PHANTOM_CLEANUP	1.4408894500000000160611079991213046014308929443359375
140	\N	MANAUSDT	binance	sell	632.00000000	0.31510000	0.31330000	0.00000000	\N	t	0.32140200	f	\N	t	\N	\N	closed	2025-10-09 05:35:13.404092+00	2025-10-09 06:34:13.685172+00	2025-10-09 06:34:13.685172+00	10.00	\N	\N	0.0000	f	2025-10-09 05:35:13.404092	PHANTOM_CLEANUP	0.032412879999999998081872121247215545736253261566162109375
119	\N	NILUSDT	binance	sell	580.00000000	0.34290000	0.33950000	0.00000000	\N	t	0.34975800	f	\N	t	\N	\N	closed	2025-10-09 03:36:35.333118+00	2025-10-09 06:34:13.964028+00	2025-10-09 06:34:13.964028+00	10.00	\N	\N	0.0000	f	2025-10-09 03:36:35.333118	PHANTOM_CLEANUP	1.9920796000000000613994188825017772614955902099609375
127	\N	RLCUSDT	binance	sell	187.00000000	1.05940000	1.05890000	0.00000000	\N	t	1.08058800	f	\N	t	\N	\N	closed	2025-10-09 04:21:20.155928+00	2025-10-09 06:34:14.161142+00	2025-10-09 06:34:14.161142+00	10.00	\N	\N	0.0000	t	2025-10-09 04:21:20.155928	PHANTOM_CLEANUP	-0.00019877999999999999077189560825473790828255005180835723876953125
137	\N	KNCUSDT	binance	sell	600.00000000	0.33230000	0.32950000	0.00000000	\N	t	0.33894600	f	\N	t	\N	\N	closed	2025-10-09 04:51:27.71356+00	2025-10-09 07:59:44.615062+00	2025-10-09 07:59:44.615062+00	10.00	\N	\N	0.0000	f	2025-10-09 04:51:27.71356	PHANTOM_CLEANUP	0.3472389000000000169876557265524752438068389892578125
136	\N	ALGOUSDT	binance	sell	914.90000000	0.21790000	0.21620000	0.00000000	\N	t	0.22225800	f	\N	t	\N	\N	closed	2025-10-09 04:51:20.885113+00	2025-10-09 07:59:44.799324+00	2025-10-09 07:59:44.799324+00	10.00	\N	\N	0.0000	f	2025-10-09 04:51:20.885113	PHANTOM_CLEANUP	1.0063899999999998957633806639933027327060699462890625
126	\N	DAMUSDT	binance	sell	3051.00000000	0.06541270	0.06649000	0.00000000	\N	t	0.06672095	f	\N	t	\N	\N	closed	2025-10-09 04:21:12.524561+00	2025-10-09 05:19:41.009733+00	2025-10-09 05:19:41.009733+00	10.00	\N	\N	0.0000	f	2025-10-09 04:21:12.524561	PHANTOM_CLEANUP	-4.0718951099999998177736415527760982513427734375
81	\N	FUSDT	binance	sell	17911.00000000	0.01115200	0.01141600	0.00000000	\N	t	0.01137504	f	\N	t	\N	\N	closed	2025-10-09 00:36:22.68785+00	2025-10-09 01:06:07.577287+00	2025-10-09 01:06:07.577287+00	10.00	\N	\N	0.0000	f	2025-10-09 00:36:22.68785	PHANTOM_CLEANUP	-4.8180589999999998696011971333064138889312744140625
170	\N	ARKUSDT	binance	sell	466.00000000	0.42650000	0.42580000	0.00000000	\N	t	0.43503000	f	\N	t	\N	\N	closed	2025-10-09 09:51:31.655437+00	2025-10-09 14:00:34.830978+00	2025-10-09 14:00:34.830978+00	10.00	\N	\N	0.0000	f	2025-10-09 09:51:31.655437	PHANTOM_CLEANUP	0.229584220000000005512674761121161282062530517578125
132	\N	JASMYUSDT	binance	sell	15875.00000000	0.01253200	0.01245700	0.00000000	\N	t	0.01278264	f	\N	t	\N	\N	closed	2025-10-09 04:36:22.164277+00	2025-10-09 07:45:39.375713+00	2025-10-09 07:45:39.375713+00	10.00	\N	\N	0.0000	f	2025-10-09 04:36:22.164277	PHANTOM_AGED	1.1966574999999999295852148861740715801715850830078125
133	\N	SKATEUSDT	binance	sell	3804.00000000	0.05257300	0.05224000	0.00000000	\N	t	0.05362446	f	\N	t	\N	\N	closed	2025-10-09 04:36:28.86537+00	2025-10-09 07:45:39.900424+00	2025-10-09 07:45:39.900424+00	10.00	\N	\N	0.0000	f	2025-10-09 04:36:28.86537	PHANTOM_AGED	0.016795999999999998431032821599728777073323726654052734375
134	\N	TAIKOUSDT	binance	sell	552.00000000	0.35990000	0.35900000	0.00000000	\N	t	0.36709800	f	\N	t	\N	\N	closed	2025-10-09 04:36:35.12845+00	2025-10-09 07:45:40.435151+00	2025-10-09 07:45:40.435151+00	10.00	\N	\N	0.0000	f	2025-10-09 04:36:35.12845	PHANTOM_AGED	0.3204000000000000181188397618825547397136688232421875
173	\N	XVSUSDT	binance	sell	28.00000000	6.96900000	6.95500000	0.00000000	\N	t	7.10838000	f	\N	t	\N	\N	closed	2025-10-09 10:21:12.008893+00	2025-10-09 13:39:04.293388+00	2025-10-09 13:39:04.293388+00	10.00	\N	\N	0.0000	f	2025-10-09 10:21:12.008893	PHANTOM_AGED	0.65829999999999999626965063725947402417659759521484375
169	\N	ZEREBROUSDT	binance	sell	11111.00000000	0.01800000	0.01801000	0.00000000	\N	t	0.01836000	f	\N	t	\N	\N	closed	2025-10-09 09:51:14.219831+00	2025-10-09 13:39:06.022902+00	2025-10-09 13:39:06.022902+00	10.00	\N	\N	0.0000	f	2025-10-09 09:51:14.219831	PHANTOM_AGED	0.015777619999999999145234852448993478901684284210205078125
167	\N	VINEUSDT	binance	sell	3192.00000000	0.06220000	0.06179000	0.00000000	\N	t	0.06344400	f	\N	t	\N	\N	closed	2025-10-09 09:36:10.51498+00	2025-10-09 13:39:06.568882+00	2025-10-09 13:39:06.568882+00	10.00	\N	\N	0.0000	f	2025-10-09 09:36:10.51498	PHANTOM_AGED	0.7997875199999999740185785412904806435108184814453125
190	\N	SIRENUSDT	binance	sell	1869.00000000	0.10686000	0.10462000	0.00000000	\N	t	0.10899720	f	\N	t	\N	\N	closed	2025-10-09 11:51:10.862911+00	2025-10-09 13:39:19.960052+00	2025-10-09 13:39:19.960052+00	10.00	\N	\N	0.0000	f	2025-10-09 11:51:10.862911	PHANTOM_CLEANUP	3.802480500000000152027723743231035768985748291015625
185	\N	CTSIUSDT	binance	sell	2751.00000000	0.07240000	0.07140000	0.00000000	\N	t	0.07384800	f	\N	t	\N	\N	closed	2025-10-09 11:21:26.54191+00	2025-10-09 14:30:45.79346+00	2025-10-09 14:30:45.79346+00	10.00	\N	\N	0.0000	f	2025-10-09 11:21:26.54191	PHANTOM_CLEANUP	2.20080000000000008952838470577262341976165771484375
39	\N	RLCUSDT	binance	sell	184.00000000	1.08240000	1.07800000	0.00000000	\N	t	1.10404800	f	\N	t	\N	\N	closed	2025-10-08 20:51:32.655061+00	2025-10-09 00:05:25.026879+00	2025-10-09 00:05:25.026879+00	10.00	\N	\N	0.0000	f	2025-10-08 20:51:32.655061	PHANTOM_AGED	0.09979736999999999635946323905955068767070770263671875
37	\N	COWUSDT	binance	sell	698.00000000	0.28630000	0.28550000	0.00000000	\N	t	0.29202600	f	\N	t	\N	\N	closed	2025-10-08 20:51:19.79237+00	2025-10-09 00:05:26.640573+00	2025-10-09 00:05:26.640573+00	10.00	\N	\N	0.0000	f	2025-10-08 20:51:19.79237	PHANTOM_AGED	0.292972500000000024567015088905463926494121551513671875
112	\N	DOTUSDT	binance	sell	49.00000000	4.07400000	4.06100000	0.00000000	\N	t	4.15548000	f	\N	t	\N	\N	closed	2025-10-09 02:51:18.548681+00	2025-10-09 07:45:34.442793+00	2025-10-09 07:45:34.442793+00	10.00	\N	\N	0.0000	f	2025-10-09 02:51:18.548681	PHANTOM_AGED	0.4868509100000000255903387369471602141857147216796875
115	\N	NMRUSDT	binance	sell	12.00000000	15.93200000	15.89500000	0.00000000	\N	t	16.25064000	f	\N	t	\N	\N	closed	2025-10-09 02:51:37.802294+00	2025-10-09 07:45:36.141437+00	2025-10-09 07:45:36.141437+00	10.00	\N	\N	0.0000	f	2025-10-09 02:51:37.802294	PHANTOM_AGED	0.2403866799999999914749793106238939799368381500244140625
131	\N	GALAUSDT	binance	sell	12828.00000000	0.01555000	0.01536000	0.00000000	\N	t	0.01586100	f	\N	t	\N	\N	closed	2025-10-09 04:36:14.88636+00	2025-10-09 07:45:38.828758+00	2025-10-09 07:45:38.828758+00	10.00	\N	\N	0.0000	f	2025-10-09 04:36:14.88636	PHANTOM_AGED	2.309039999999999981383780323085375130176544189453125
50	\N	FIOUSDT	binance	sell	12084.00000000	0.01655000	0.01651000	0.00000000	\N	t	0.01688100	f	\N	t	\N	\N	closed	2025-10-08 21:51:38.494931+00	2025-10-09 00:55:24.084083+00	2025-10-09 00:55:24.084083+00	10.00	\N	\N	0.0000	f	2025-10-08 21:51:38.494931	PHANTOM_CLEANUP	0.17552000000000000934363697524531744420528411865234375
12	\N	DENTUSDT	binance	sell	313971.00000000	0.00063700	0.00063450	\N	\N	t	0.00064974	f	\N	t	\N	\N	closed	2025-10-08 18:36:45.565351+00	\N	2025-10-09 00:16:31.77274+00	10.00	\N	\N	\N	f	2025-10-08 18:36:45.565351	\N	0.0179099999999999988375964932174611021764576435089111328125
60	\N	ONGUSDT	binance	sell	1318.00000000	0.15120000	0.15017000	0.00000000	\N	t	0.15422400	f	\N	t	\N	\N	closed	2025-10-08 22:51:32.937871+00	2025-10-09 01:58:27.040437+00	2025-10-09 01:58:27.040437+00	10.00	\N	\N	0.0000	f	2025-10-08 22:51:32.937871	PHANTOM_AGED	0.97026000000000001133315663537359796464443206787109375
211	\N	EIGENUSDT	binance	sell	111.00000000	1.78550000	1.75040000	0.00000000	\N	t	1.82121000	f	\N	t	\N	\N	closed	2025-10-09 13:36:18.393713+00	2025-10-09 15:49:01.661261+00	2025-10-09 15:49:01.661261+00	10.00	\N	\N	0.0000	f	2025-10-09 13:36:18.393713	PHANTOM_CLEANUP	3.805225409999999808263737577362917363643646240234375
205	\N	ADAUSDT	binance	sell	245.00000000	0.81420000	0.80000000	0.00000000	\N	t	0.83048400	f	\N	t	\N	\N	closed	2025-10-09 13:21:21.196767+00	2025-10-09 14:36:22.718656+00	2025-10-09 14:36:22.718656+00	10.00	\N	\N	0.0000	f	2025-10-09 13:21:21.196767	PHANTOM_CLEANUP	3.601500000000000145661260830820538103580474853515625
193	\N	PROVEUSDT	binance	sell	262.00000000	0.76320580	0.77910000	0.00000000	\N	t	0.77846992	f	\N	t	\N	\N	closed	2025-10-09 11:51:31.664378+00	2025-10-09 16:05:28.904001+00	2025-10-09 16:05:34.638458+00	10.00	\N	\N	0.0000	f	2025-10-09 11:51:31.664378	PHANTOM_AGED	-3.2403519799999997985651134513318538665771484375
139	\N	C98USDT	binance	sell	3424.00000000	0.05840000	0.05740000	0.00000000	\N	t	0.05956800	f	\N	t	\N	\N	closed	2025-10-09 04:51:41.82821+00	2025-10-09 07:38:30.765125+00	2025-10-09 07:38:30.765125+00	10.00	\N	\N	0.0000	f	2025-10-09 04:51:41.82821	PHANTOM_CLEANUP	2.72550399999999992672883308841846883296966552734375
138	\N	OGNUSDT	binance	sell	3378.00000000	0.05910000	0.05820000	0.00000000	\N	t	0.06028200	f	\N	t	\N	\N	closed	2025-10-09 04:51:35.430537+00	2025-10-09 07:06:20.018578+00	2025-10-09 07:06:20.018578+00	10.00	\N	\N	0.0000	t	2025-10-09 04:51:35.430537	PHANTOM_CLEANUP	2.364599999999999813127260495093651115894317626953125
142	\N	DOODUSDT	binance	sell	18554.00000000	0.01072860	0.01057500	0.00000000	\N	t	0.01094317	f	\N	t	\N	\N	closed	2025-10-09 05:51:12.818665+00	2025-10-09 07:06:19.733468+00	2025-10-09 07:06:19.733468+00	10.00	\N	\N	0.0000	f	2025-10-09 05:51:12.818665	PHANTOM_CLEANUP	2.7020190199999998270641299313865602016448974609375
\.


--
-- Data for Name: processed_signals; Type: TABLE DATA; Schema: monitoring; Owner: elcrypto
--

COPY monitoring.processed_signals (id, signal_id, symbol, action, score_week, score_month, processed_at, result, position_id, error_message, created_at) FROM stdin;
\.


--
-- Data for Name: protection_events; Type: TABLE DATA; Schema: monitoring; Owner: elcrypto
--

COPY monitoring.protection_events (id, position_id, symbol, exchange, event_type, protection_type, price_level, activation_price, callback_rate, success, error_message, created_at) FROM stdin;
\.


--
-- Data for Name: system_health; Type: TABLE DATA; Schema: monitoring; Owner: elcrypto
--

COPY monitoring.system_health (id, service_name, status, binance_connected, bybit_connected, database_connected, last_signal_processed, signals_processed_count, positions_protected_count, error_count, last_error, metadata, created_at) FROM stdin;
1	main_trader	RUNNING	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-13 17:36:48.19145+00
2	main_trader	RUNNING	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-13 17:51:45.486359+00
3	main_trader	RUNNING	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-13 18:27:41.960241+00
4	protection_monitor	RUNNING	t	t	t	\N	0	0	0	\N	{"sl_added": 0, "timeout_closes": 0, "trailing_added": 0, "positions_found": 0, "breakeven_closes": 0, "positions_closed": 0}	2025-09-13 18:33:49.864738+00
5	protection_monitor	RUNNING	t	t	t	\N	0	0	0	\N	{"sl_added": 0, "timeout_closes": 0, "trailing_added": 0, "positions_found": 0, "breakeven_closes": 0, "positions_closed": 0}	2025-09-13 18:42:06.801865+00
6	protection_monitor	RUNNING	t	t	t	\N	0	0	0	\N	{"sl_added": 0, "timeout_closes": 0, "trailing_added": 0, "positions_found": 0, "breakeven_closes": 0, "positions_closed": 0}	2025-09-13 22:00:38.321018+00
7	main_trader	RUNNING	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-13 22:15:12.600482+00
8	protection_monitor	RUNNING	t	t	t	\N	0	0	0	\N	{"sl_added": 0, "timeout_closes": 0, "trailing_added": 0, "positions_found": 0, "breakeven_closes": 0, "positions_closed": 0}	2025-09-13 22:21:39.81107+00
9	protection_monitor	RUNNING	t	t	t	\N	0	0	0	\N	{"sl_added": 0, "timeout_closes": 0, "trailing_added": 0, "positions_found": 0, "breakeven_closes": 0, "positions_closed": 0}	2025-09-13 22:22:55.971869+00
10	main_trader	RUNNING	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-14 07:56:56.696694+00
11	main_trader	RUNNING	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-14 08:01:06.066922+00
12	main_trader	RUNNING	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-14 10:18:07.630258+00
13	main_trader	RUNNING	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-14 11:22:21.098906+00
14	main_trader	RUNNING	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-14 11:28:39.682624+00
15	protection_monitor	RUNNING	t	t	t	\N	0	0	0	\N	{"sl_added": 0, "timeout_closes": 0, "trailing_added": 0, "positions_found": 0, "breakeven_closes": 0, "positions_closed": 0}	2025-09-14 11:28:54.043445+00
16	main_trader	RUNNING	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-14 11:49:41.259402+00
17	main_trader	RUNNING	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-14 13:10:43.103808+00
18	main_trader	STOPPED	t	t	t	\N	8	0	0	\N	{"sl_set": 8, "sl_failed": 0, "positions_failed": 3, "positions_opened": 8}	2025-09-14 13:45:39.831833+00
19	main_trader	RUNNING	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-14 13:45:49.530062+00
20	main_trader	STOPPED	t	t	t	\N	57	0	0	\N	{"sl_set": 57, "sl_failed": 0, "positions_failed": 8, "positions_opened": 57}	2025-09-14 13:56:41.421137+00
21	main_trader	RUNNING	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-14 17:46:29.693027+00
22	main_trader	RUNNING	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-14 17:59:35.67866+00
23	main_trader	RUNNING	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-14 19:12:38.83415+00
24	main_trader	RUNNING	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-14 19:17:31.852715+00
25	main_trader	RUNNING	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-14 19:54:10.109087+00
26	main_trader	RUNNING	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-14 20:56:18.742624+00
27	main_trader	RUNNING	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-14 21:14:32.535977+00
28	main_trader	RUNNING	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-15 14:34:53.271262+00
29	main_trader	HEALTHY	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 0, "positions_opened": 3}	2025-09-15 14:35:54.227811+00
30	main_trader	HEALTHY	t	t	t	\N	5	0	0	\N	{"sl_set": 5, "sl_failed": 0, "positions_failed": 1, "positions_opened": 5}	2025-09-15 14:36:55.665063+00
31	main_trader	HEALTHY	t	t	t	\N	5	0	0	\N	{"sl_set": 5, "sl_failed": 0, "positions_failed": 1, "positions_opened": 5}	2025-09-15 14:37:56.813317+00
32	main_trader	HEALTHY	t	t	t	\N	5	0	0	\N	{"sl_set": 5, "sl_failed": 0, "positions_failed": 1, "positions_opened": 5}	2025-09-15 14:38:57.849636+00
33	main_trader	HEALTHY	t	t	t	\N	5	0	0	\N	{"sl_set": 5, "sl_failed": 0, "positions_failed": 1, "positions_opened": 5}	2025-09-15 14:39:59.186328+00
34	main_trader	HEALTHY	t	t	t	\N	5	0	0	\N	{"sl_set": 5, "sl_failed": 0, "positions_failed": 1, "positions_opened": 5}	2025-09-15 14:41:00.42392+00
35	main_trader	HEALTHY	t	t	t	\N	5	0	0	\N	{"sl_set": 5, "sl_failed": 0, "positions_failed": 1, "positions_opened": 5}	2025-09-15 14:42:01.586762+00
36	main_trader	HEALTHY	t	t	t	\N	5	0	0	\N	{"sl_set": 5, "sl_failed": 0, "positions_failed": 1, "positions_opened": 5}	2025-09-15 14:43:02.634092+00
37	main_trader	HEALTHY	t	t	t	\N	5	0	0	\N	{"sl_set": 5, "sl_failed": 0, "positions_failed": 1, "positions_opened": 5}	2025-09-15 14:44:03.686755+00
38	main_trader	HEALTHY	t	t	t	\N	5	0	0	\N	{"sl_set": 5, "sl_failed": 0, "positions_failed": 1, "positions_opened": 5}	2025-09-15 14:45:05.421014+00
39	main_trader	HEALTHY	t	t	t	\N	5	0	0	\N	{"sl_set": 5, "sl_failed": 0, "positions_failed": 1, "positions_opened": 5}	2025-09-15 14:46:06.644955+00
40	main_trader	HEALTHY	t	t	t	\N	5	0	0	\N	{"sl_set": 5, "sl_failed": 0, "positions_failed": 1, "positions_opened": 5}	2025-09-15 14:47:07.694624+00
41	main_trader	RUNNING	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-15 14:49:01.846864+00
42	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-15 14:50:03.155043+00
43	main_trader	DEGRADED	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 2, "positions_opened": 2}	2025-09-15 14:51:04.283923+00
44	main_trader	DEGRADED	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 2, "positions_opened": 2}	2025-09-15 14:52:05.329636+00
45	main_trader	DEGRADED	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 2, "positions_opened": 2}	2025-09-15 14:53:06.406239+00
46	main_trader	DEGRADED	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 2, "positions_opened": 2}	2025-09-15 14:54:07.603121+00
47	main_trader	DEGRADED	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 2, "positions_opened": 2}	2025-09-15 14:55:09.055934+00
48	main_trader	DEGRADED	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 2, "positions_opened": 2}	2025-09-15 14:56:10.808147+00
49	main_trader	DEGRADED	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 2, "positions_opened": 2}	2025-09-15 14:57:11.931993+00
50	main_trader	DEGRADED	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 2, "positions_opened": 2}	2025-09-15 14:58:13.106318+00
51	main_trader	DEGRADED	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 2, "positions_opened": 2}	2025-09-15 14:59:14.156414+00
52	main_trader	DEGRADED	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 2, "positions_opened": 2}	2025-09-15 15:00:15.325608+00
53	main_trader	DEGRADED	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 2, "positions_opened": 2}	2025-09-15 15:01:16.735059+00
54	main_trader	DEGRADED	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 2, "positions_opened": 2}	2025-09-15 15:02:17.86161+00
55	main_trader	DEGRADED	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 2, "positions_opened": 2}	2025-09-15 15:03:19.049069+00
56	main_trader	DEGRADED	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 2, "positions_opened": 2}	2025-09-15 15:04:20.200658+00
57	main_trader	DEGRADED	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 2, "positions_opened": 2}	2025-09-15 15:05:21.375842+00
58	main_trader	DEGRADED	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 3, "positions_opened": 2}	2025-09-15 15:06:23.149144+00
59	main_trader	DEGRADED	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 3, "positions_opened": 3}	2025-09-15 15:07:24.269782+00
60	main_trader	DEGRADED	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 3, "positions_opened": 3}	2025-09-15 15:08:25.343298+00
61	main_trader	DEGRADED	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 3, "positions_opened": 3}	2025-09-15 15:09:26.421963+00
62	main_trader	DEGRADED	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 3, "positions_opened": 3}	2025-09-15 15:10:27.553175+00
63	main_trader	DEGRADED	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 3, "positions_opened": 3}	2025-09-15 15:11:29.117685+00
64	main_trader	DEGRADED	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 3, "positions_opened": 3}	2025-09-15 15:12:30.233186+00
65	main_trader	DEGRADED	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 3, "positions_opened": 3}	2025-09-15 15:13:31.343406+00
66	main_trader	DEGRADED	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 3, "positions_opened": 3}	2025-09-15 15:14:32.475892+00
67	main_trader	DEGRADED	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 3, "positions_opened": 3}	2025-09-15 15:15:34.048854+00
68	main_trader	DEGRADED	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 3, "positions_opened": 3}	2025-09-15 15:16:35.318545+00
69	main_trader	DEGRADED	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 3, "positions_opened": 3}	2025-09-15 15:17:36.46759+00
70	main_trader	DEGRADED	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 3, "positions_opened": 3}	2025-09-15 15:18:37.557567+00
71	main_trader	DEGRADED	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 3, "positions_opened": 3}	2025-09-15 15:19:38.604665+00
72	main_trader	HEALTHY	t	t	t	\N	5	0	0	\N	{"sl_set": 6, "sl_failed": 0, "positions_failed": 3, "positions_opened": 6}	2025-09-15 15:20:40.573787+00
73	main_trader	HEALTHY	t	t	t	\N	10	0	0	\N	{"sl_set": 10, "sl_failed": 0, "positions_failed": 4, "positions_opened": 10}	2025-09-15 15:21:41.832776+00
74	main_trader	HEALTHY	t	t	t	\N	10	0	0	\N	{"sl_set": 10, "sl_failed": 0, "positions_failed": 4, "positions_opened": 10}	2025-09-15 15:22:42.942434+00
75	main_trader	HEALTHY	t	t	t	\N	10	0	0	\N	{"sl_set": 10, "sl_failed": 0, "positions_failed": 4, "positions_opened": 10}	2025-09-15 15:23:43.976918+00
76	main_trader	HEALTHY	t	t	t	\N	10	0	0	\N	{"sl_set": 10, "sl_failed": 0, "positions_failed": 4, "positions_opened": 10}	2025-09-15 15:24:45.03067+00
77	main_trader	HEALTHY	t	t	t	\N	10	0	0	\N	{"sl_set": 10, "sl_failed": 0, "positions_failed": 4, "positions_opened": 10}	2025-09-15 15:25:46.349032+00
78	main_trader	HEALTHY	t	t	t	\N	10	0	0	\N	{"sl_set": 10, "sl_failed": 0, "positions_failed": 4, "positions_opened": 10}	2025-09-15 15:26:47.982459+00
79	main_trader	HEALTHY	t	t	t	\N	10	0	0	\N	{"sl_set": 10, "sl_failed": 0, "positions_failed": 4, "positions_opened": 10}	2025-09-15 15:27:49.103335+00
80	main_trader	HEALTHY	t	t	t	\N	10	0	0	\N	{"sl_set": 10, "sl_failed": 0, "positions_failed": 4, "positions_opened": 10}	2025-09-15 15:28:50.147081+00
81	main_trader	HEALTHY	t	t	t	\N	10	0	0	\N	{"sl_set": 10, "sl_failed": 0, "positions_failed": 4, "positions_opened": 10}	2025-09-15 15:29:51.223114+00
82	main_trader	HEALTHY	t	t	t	\N	10	0	0	\N	{"sl_set": 10, "sl_failed": 0, "positions_failed": 4, "positions_opened": 10}	2025-09-15 15:30:52.265126+00
83	main_trader	HEALTHY	t	t	t	\N	10	0	0	\N	{"sl_set": 10, "sl_failed": 0, "positions_failed": 4, "positions_opened": 10}	2025-09-15 15:31:53.528412+00
84	main_trader	HEALTHY	t	t	t	\N	10	0	0	\N	{"sl_set": 10, "sl_failed": 0, "positions_failed": 4, "positions_opened": 10}	2025-09-15 15:32:54.736+00
85	main_trader	HEALTHY	t	t	t	\N	10	0	0	\N	{"sl_set": 10, "sl_failed": 0, "positions_failed": 4, "positions_opened": 10}	2025-09-15 15:33:55.778914+00
86	main_trader	HEALTHY	t	t	t	\N	10	0	0	\N	{"sl_set": 10, "sl_failed": 0, "positions_failed": 4, "positions_opened": 10}	2025-09-15 15:34:56.802699+00
87	main_trader	HEALTHY	t	t	t	\N	13	0	0	\N	{"sl_set": 13, "sl_failed": 0, "positions_failed": 4, "positions_opened": 14}	2025-09-15 15:35:57.847854+00
88	main_trader	HEALTHY	t	t	t	\N	14	0	0	\N	{"sl_set": 13, "sl_failed": 1, "positions_failed": 4, "positions_opened": 14}	2025-09-15 15:36:59.510183+00
89	main_trader	HEALTHY	t	t	t	\N	14	0	0	\N	{"sl_set": 13, "sl_failed": 1, "positions_failed": 4, "positions_opened": 14}	2025-09-15 15:38:00.639194+00
90	main_trader	HEALTHY	t	t	t	\N	14	0	0	\N	{"sl_set": 13, "sl_failed": 1, "positions_failed": 4, "positions_opened": 14}	2025-09-15 15:39:01.702288+00
91	main_trader	HEALTHY	t	t	t	\N	14	0	0	\N	{"sl_set": 13, "sl_failed": 1, "positions_failed": 4, "positions_opened": 14}	2025-09-15 15:40:02.800314+00
92	main_trader	HEALTHY	t	t	t	\N	14	0	0	\N	{"sl_set": 13, "sl_failed": 1, "positions_failed": 4, "positions_opened": 14}	2025-09-15 15:41:03.971549+00
93	main_trader	HEALTHY	t	t	t	\N	14	0	0	\N	{"sl_set": 13, "sl_failed": 1, "positions_failed": 4, "positions_opened": 14}	2025-09-15 15:42:05.598407+00
94	main_trader	HEALTHY	t	t	t	\N	14	0	0	\N	{"sl_set": 13, "sl_failed": 1, "positions_failed": 4, "positions_opened": 14}	2025-09-15 15:43:06.745786+00
95	main_trader	HEALTHY	t	t	t	\N	14	0	0	\N	{"sl_set": 13, "sl_failed": 1, "positions_failed": 4, "positions_opened": 14}	2025-09-15 15:44:07.925398+00
96	main_trader	HEALTHY	t	t	t	\N	14	0	0	\N	{"sl_set": 13, "sl_failed": 1, "positions_failed": 4, "positions_opened": 14}	2025-09-15 15:45:08.985223+00
97	main_trader	RUNNING	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-15 16:06:41.080743+00
98	main_trader	RUNNING	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-15 16:22:20.920401+00
99	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-15 16:23:22.016002+00
100	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-15 16:24:23.047986+00
101	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-15 16:25:24.196955+00
102	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-15 16:26:25.267291+00
103	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-15 16:27:26.761574+00
104	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-15 16:28:27.986553+00
105	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-15 16:29:29.049759+00
106	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-15 16:30:30.073636+00
107	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-15 16:31:31.231163+00
108	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-15 16:32:32.514568+00
109	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-15 16:33:33.734073+00
110	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-15 16:34:34.89272+00
111	main_trader	HEALTHY	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 0, "positions_opened": 3}	2025-09-15 16:35:35.756016+00
112	main_trader	HEALTHY	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 0, "positions_opened": 3}	2025-09-15 16:36:36.927783+00
113	main_trader	HEALTHY	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 0, "positions_opened": 3}	2025-09-15 16:37:38.168542+00
114	main_trader	HEALTHY	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 0, "positions_opened": 3}	2025-09-15 16:38:39.411537+00
115	main_trader	HEALTHY	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 0, "positions_opened": 3}	2025-09-15 16:39:40.478412+00
116	main_trader	HEALTHY	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 0, "positions_opened": 3}	2025-09-15 16:40:41.604926+00
117	main_trader	HEALTHY	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 0, "positions_opened": 3}	2025-09-15 16:41:42.725379+00
118	main_trader	HEALTHY	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 0, "positions_opened": 3}	2025-09-15 16:42:44.412488+00
119	main_trader	HEALTHY	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 0, "positions_opened": 3}	2025-09-15 16:43:45.60796+00
120	main_trader	HEALTHY	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 0, "positions_opened": 3}	2025-09-15 16:44:46.751584+00
121	main_trader	HEALTHY	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 0, "positions_opened": 3}	2025-09-15 16:45:47.819836+00
122	main_trader	HEALTHY	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 0, "positions_opened": 3}	2025-09-15 16:46:48.867181+00
123	main_trader	HEALTHY	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 0, "positions_opened": 3}	2025-09-15 16:47:50.11015+00
124	main_trader	HEALTHY	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 0, "positions_opened": 3}	2025-09-15 16:48:51.274952+00
125	main_trader	HEALTHY	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 0, "positions_opened": 3}	2025-09-15 16:49:52.311714+00
126	main_trader	HEALTHY	t	t	t	\N	7	0	0	\N	{"sl_set": 7, "sl_failed": 0, "positions_failed": 0, "positions_opened": 8}	2025-09-15 16:50:53.206673+00
127	main_trader	HEALTHY	t	t	t	\N	8	0	0	\N	{"sl_set": 8, "sl_failed": 0, "positions_failed": 0, "positions_opened": 8}	2025-09-15 16:51:54.328208+00
128	main_trader	HEALTHY	t	t	t	\N	8	0	0	\N	{"sl_set": 8, "sl_failed": 0, "positions_failed": 0, "positions_opened": 8}	2025-09-15 16:52:55.583872+00
129	main_trader	HEALTHY	t	t	t	\N	8	0	0	\N	{"sl_set": 8, "sl_failed": 0, "positions_failed": 0, "positions_opened": 8}	2025-09-15 16:53:56.715934+00
130	main_trader	HEALTHY	t	t	t	\N	8	0	0	\N	{"sl_set": 8, "sl_failed": 0, "positions_failed": 0, "positions_opened": 8}	2025-09-15 16:54:57.772315+00
131	main_trader	HEALTHY	t	t	t	\N	8	0	0	\N	{"sl_set": 8, "sl_failed": 0, "positions_failed": 0, "positions_opened": 8}	2025-09-15 16:55:58.817327+00
132	main_trader	HEALTHY	t	t	t	\N	8	0	0	\N	{"sl_set": 8, "sl_failed": 0, "positions_failed": 0, "positions_opened": 8}	2025-09-15 16:57:00.093484+00
133	main_trader	HEALTHY	t	t	t	\N	8	0	0	\N	{"sl_set": 8, "sl_failed": 0, "positions_failed": 0, "positions_opened": 8}	2025-09-15 16:58:01.220676+00
134	main_trader	HEALTHY	t	t	t	\N	8	0	0	\N	{"sl_set": 8, "sl_failed": 0, "positions_failed": 0, "positions_opened": 8}	2025-09-15 16:59:02.383696+00
135	main_trader	HEALTHY	t	t	t	\N	8	0	0	\N	{"sl_set": 8, "sl_failed": 0, "positions_failed": 0, "positions_opened": 8}	2025-09-15 17:00:03.446645+00
136	main_trader	HEALTHY	t	t	t	\N	8	0	0	\N	{"sl_set": 8, "sl_failed": 0, "positions_failed": 0, "positions_opened": 8}	2025-09-15 17:01:04.49475+00
137	main_trader	HEALTHY	t	t	t	\N	8	0	0	\N	{"sl_set": 8, "sl_failed": 0, "positions_failed": 0, "positions_opened": 8}	2025-09-15 17:02:05.788375+00
138	main_trader	HEALTHY	t	t	t	\N	8	0	0	\N	{"sl_set": 8, "sl_failed": 0, "positions_failed": 0, "positions_opened": 8}	2025-09-15 17:03:06.965598+00
139	main_trader	HEALTHY	t	t	t	\N	8	0	0	\N	{"sl_set": 8, "sl_failed": 0, "positions_failed": 0, "positions_opened": 8}	2025-09-15 17:04:08.094181+00
140	main_trader	HEALTHY	t	t	t	\N	8	0	0	\N	{"sl_set": 8, "sl_failed": 0, "positions_failed": 0, "positions_opened": 8}	2025-09-15 17:05:09.299073+00
141	main_trader	HEALTHY	t	t	t	\N	8	0	0	\N	{"sl_set": 8, "sl_failed": 0, "positions_failed": 0, "positions_opened": 8}	2025-09-15 17:06:10.461261+00
142	main_trader	HEALTHY	t	t	t	\N	10	0	0	\N	{"sl_set": 10, "sl_failed": 0, "positions_failed": 1, "positions_opened": 10}	2025-09-15 17:07:11.563385+00
143	main_trader	HEALTHY	t	t	t	\N	10	0	0	\N	{"sl_set": 10, "sl_failed": 0, "positions_failed": 1, "positions_opened": 10}	2025-09-15 17:08:12.65593+00
144	main_trader	HEALTHY	t	t	t	\N	10	0	0	\N	{"sl_set": 10, "sl_failed": 0, "positions_failed": 1, "positions_opened": 10}	2025-09-15 17:09:13.75427+00
145	main_trader	HEALTHY	t	t	t	\N	10	0	0	\N	{"sl_set": 10, "sl_failed": 0, "positions_failed": 1, "positions_opened": 10}	2025-09-15 17:10:15.184447+00
146	main_trader	HEALTHY	t	t	t	\N	10	0	0	\N	{"sl_set": 10, "sl_failed": 0, "positions_failed": 1, "positions_opened": 10}	2025-09-15 17:11:16.311255+00
147	main_trader	HEALTHY	t	t	t	\N	10	0	0	\N	{"sl_set": 10, "sl_failed": 0, "positions_failed": 1, "positions_opened": 10}	2025-09-15 17:12:17.343016+00
148	main_trader	HEALTHY	t	t	t	\N	10	0	0	\N	{"sl_set": 10, "sl_failed": 0, "positions_failed": 1, "positions_opened": 10}	2025-09-15 17:13:18.436655+00
149	main_trader	HEALTHY	t	t	t	\N	10	0	0	\N	{"sl_set": 10, "sl_failed": 0, "positions_failed": 1, "positions_opened": 10}	2025-09-15 17:14:19.478662+00
150	main_trader	HEALTHY	t	t	t	\N	10	0	0	\N	{"sl_set": 10, "sl_failed": 0, "positions_failed": 1, "positions_opened": 10}	2025-09-15 17:15:20.819786+00
151	main_trader	HEALTHY	t	t	t	\N	10	0	0	\N	{"sl_set": 10, "sl_failed": 0, "positions_failed": 1, "positions_opened": 10}	2025-09-15 17:16:21.92797+00
152	main_trader	HEALTHY	t	t	t	\N	10	0	0	\N	{"sl_set": 10, "sl_failed": 0, "positions_failed": 1, "positions_opened": 10}	2025-09-15 17:17:23.055247+00
153	main_trader	HEALTHY	t	t	t	\N	10	0	0	\N	{"sl_set": 10, "sl_failed": 0, "positions_failed": 1, "positions_opened": 10}	2025-09-15 17:18:24.18313+00
154	main_trader	HEALTHY	t	t	t	\N	10	0	0	\N	{"sl_set": 10, "sl_failed": 0, "positions_failed": 1, "positions_opened": 10}	2025-09-15 17:19:25.216309+00
155	main_trader	HEALTHY	t	t	t	\N	11	0	0	\N	{"sl_set": 11, "sl_failed": 0, "positions_failed": 1, "positions_opened": 11}	2025-09-15 17:20:26.320033+00
156	main_trader	HEALTHY	t	t	t	\N	15	0	0	\N	{"sl_set": 15, "sl_failed": 0, "positions_failed": 3, "positions_opened": 15}	2025-09-15 17:21:27.417968+00
157	main_trader	HEALTHY	t	t	t	\N	15	0	0	\N	{"sl_set": 15, "sl_failed": 0, "positions_failed": 3, "positions_opened": 15}	2025-09-15 17:22:28.542539+00
158	main_trader	HEALTHY	t	t	t	\N	15	0	0	\N	{"sl_set": 15, "sl_failed": 0, "positions_failed": 3, "positions_opened": 15}	2025-09-15 17:23:29.695483+00
159	main_trader	HEALTHY	t	t	t	\N	15	0	0	\N	{"sl_set": 15, "sl_failed": 0, "positions_failed": 3, "positions_opened": 15}	2025-09-15 17:24:30.812013+00
160	main_trader	HEALTHY	t	t	t	\N	15	0	0	\N	{"sl_set": 15, "sl_failed": 0, "positions_failed": 3, "positions_opened": 15}	2025-09-15 17:25:32.62831+00
161	main_trader	HEALTHY	t	t	t	\N	15	0	0	\N	{"sl_set": 15, "sl_failed": 0, "positions_failed": 3, "positions_opened": 15}	2025-09-15 17:26:33.771691+00
162	main_trader	HEALTHY	t	t	t	\N	15	0	0	\N	{"sl_set": 15, "sl_failed": 0, "positions_failed": 3, "positions_opened": 15}	2025-09-15 17:27:34.83904+00
163	main_trader	HEALTHY	t	t	t	\N	15	0	0	\N	{"sl_set": 15, "sl_failed": 0, "positions_failed": 3, "positions_opened": 15}	2025-09-15 17:28:35.898941+00
164	main_trader	HEALTHY	t	t	t	\N	15	0	0	\N	{"sl_set": 15, "sl_failed": 0, "positions_failed": 3, "positions_opened": 15}	2025-09-15 17:29:36.936698+00
165	main_trader	HEALTHY	t	t	t	\N	15	0	0	\N	{"sl_set": 15, "sl_failed": 0, "positions_failed": 3, "positions_opened": 15}	2025-09-15 17:30:38.178313+00
166	main_trader	HEALTHY	t	t	t	\N	15	0	0	\N	{"sl_set": 15, "sl_failed": 0, "positions_failed": 3, "positions_opened": 15}	2025-09-15 17:31:39.281719+00
167	main_trader	HEALTHY	t	t	t	\N	15	0	0	\N	{"sl_set": 15, "sl_failed": 0, "positions_failed": 3, "positions_opened": 15}	2025-09-15 17:32:40.404359+00
168	main_trader	HEALTHY	t	t	t	\N	15	0	0	\N	{"sl_set": 15, "sl_failed": 0, "positions_failed": 3, "positions_opened": 15}	2025-09-15 17:33:41.482066+00
169	main_trader	HEALTHY	t	t	t	\N	15	0	0	\N	{"sl_set": 15, "sl_failed": 0, "positions_failed": 3, "positions_opened": 15}	2025-09-15 17:34:42.505904+00
170	main_trader	HEALTHY	t	t	t	\N	16	0	0	\N	{"sl_set": 17, "sl_failed": 0, "positions_failed": 5, "positions_opened": 17}	2025-09-15 17:35:43.662587+00
171	main_trader	HEALTHY	t	t	t	\N	17	0	0	\N	{"sl_set": 17, "sl_failed": 0, "positions_failed": 5, "positions_opened": 17}	2025-09-15 17:36:44.914955+00
172	main_trader	HEALTHY	t	t	t	\N	17	0	0	\N	{"sl_set": 17, "sl_failed": 0, "positions_failed": 5, "positions_opened": 17}	2025-09-15 17:37:47.409441+00
173	main_trader	HEALTHY	t	t	t	\N	17	0	0	\N	{"sl_set": 17, "sl_failed": 0, "positions_failed": 5, "positions_opened": 17}	2025-09-15 17:38:48.554469+00
174	main_trader	HEALTHY	t	t	t	\N	17	0	0	\N	{"sl_set": 17, "sl_failed": 0, "positions_failed": 5, "positions_opened": 17}	2025-09-15 17:39:50.079258+00
175	main_trader	HEALTHY	t	t	t	\N	17	0	0	\N	{"sl_set": 17, "sl_failed": 0, "positions_failed": 5, "positions_opened": 17}	2025-09-15 17:40:51.368679+00
176	main_trader	HEALTHY	t	t	t	\N	17	0	0	\N	{"sl_set": 17, "sl_failed": 0, "positions_failed": 5, "positions_opened": 17}	2025-09-15 17:41:52.799418+00
177	main_trader	HEALTHY	t	t	t	\N	17	0	0	\N	{"sl_set": 17, "sl_failed": 0, "positions_failed": 5, "positions_opened": 17}	2025-09-15 17:42:54.725555+00
178	main_trader	HEALTHY	t	t	t	\N	17	0	0	\N	{"sl_set": 17, "sl_failed": 0, "positions_failed": 5, "positions_opened": 17}	2025-09-15 17:43:56.203713+00
179	main_trader	HEALTHY	t	t	t	\N	17	0	0	\N	{"sl_set": 17, "sl_failed": 0, "positions_failed": 5, "positions_opened": 17}	2025-09-15 17:44:57.602293+00
180	main_trader	HEALTHY	t	t	t	\N	17	0	0	\N	{"sl_set": 17, "sl_failed": 0, "positions_failed": 5, "positions_opened": 17}	2025-09-15 17:45:58.973265+00
181	main_trader	HEALTHY	t	t	t	\N	17	0	0	\N	{"sl_set": 17, "sl_failed": 0, "positions_failed": 5, "positions_opened": 17}	2025-09-15 17:47:00.316401+00
182	main_trader	HEALTHY	t	t	t	\N	17	0	0	\N	{"sl_set": 17, "sl_failed": 0, "positions_failed": 5, "positions_opened": 17}	2025-09-15 17:48:02.427742+00
183	main_trader	HEALTHY	t	t	t	\N	17	0	0	\N	{"sl_set": 17, "sl_failed": 0, "positions_failed": 5, "positions_opened": 17}	2025-09-15 17:49:03.893741+00
184	main_trader	HEALTHY	t	t	t	\N	17	0	0	\N	{"sl_set": 17, "sl_failed": 0, "positions_failed": 5, "positions_opened": 17}	2025-09-15 17:50:05.343913+00
185	main_trader	HEALTHY	t	t	t	\N	17	0	0	\N	{"sl_set": 17, "sl_failed": 0, "positions_failed": 5, "positions_opened": 17}	2025-09-15 17:51:07.397568+00
186	main_trader	HEALTHY	t	t	t	\N	18	0	0	\N	{"sl_set": 18, "sl_failed": 0, "positions_failed": 5, "positions_opened": 18}	2025-09-15 17:52:08.966381+00
187	main_trader	HEALTHY	t	t	t	\N	18	0	0	\N	{"sl_set": 18, "sl_failed": 0, "positions_failed": 5, "positions_opened": 18}	2025-09-15 17:53:10.833247+00
188	main_trader	HEALTHY	t	t	t	\N	18	0	0	\N	{"sl_set": 18, "sl_failed": 0, "positions_failed": 5, "positions_opened": 18}	2025-09-15 17:54:12.258975+00
189	main_trader	HEALTHY	t	t	t	\N	18	0	0	\N	{"sl_set": 18, "sl_failed": 0, "positions_failed": 5, "positions_opened": 18}	2025-09-15 17:55:13.500573+00
190	main_trader	HEALTHY	t	t	t	\N	18	0	0	\N	{"sl_set": 18, "sl_failed": 0, "positions_failed": 5, "positions_opened": 18}	2025-09-15 17:56:14.619106+00
191	main_trader	HEALTHY	t	t	t	\N	18	0	0	\N	{"sl_set": 18, "sl_failed": 0, "positions_failed": 5, "positions_opened": 18}	2025-09-15 17:57:15.805935+00
192	main_trader	HEALTHY	t	t	t	\N	18	0	0	\N	{"sl_set": 18, "sl_failed": 0, "positions_failed": 5, "positions_opened": 18}	2025-09-15 17:58:17.652604+00
193	main_trader	HEALTHY	t	t	t	\N	18	0	0	\N	{"sl_set": 18, "sl_failed": 0, "positions_failed": 5, "positions_opened": 18}	2025-09-15 17:59:18.830146+00
194	main_trader	HEALTHY	t	t	t	\N	18	0	0	\N	{"sl_set": 18, "sl_failed": 0, "positions_failed": 5, "positions_opened": 18}	2025-09-15 18:00:19.904721+00
195	main_trader	HEALTHY	t	t	t	\N	18	0	0	\N	{"sl_set": 18, "sl_failed": 0, "positions_failed": 5, "positions_opened": 18}	2025-09-15 18:01:21.024379+00
196	main_trader	HEALTHY	t	t	t	\N	18	0	0	\N	{"sl_set": 18, "sl_failed": 0, "positions_failed": 5, "positions_opened": 18}	2025-09-15 18:02:22.152677+00
197	main_trader	HEALTHY	t	t	t	\N	18	0	0	\N	{"sl_set": 18, "sl_failed": 0, "positions_failed": 5, "positions_opened": 18}	2025-09-15 18:03:23.532451+00
198	main_trader	HEALTHY	t	t	t	\N	18	0	0	\N	{"sl_set": 18, "sl_failed": 0, "positions_failed": 5, "positions_opened": 18}	2025-09-15 18:04:24.686337+00
199	main_trader	HEALTHY	t	t	t	\N	18	0	0	\N	{"sl_set": 18, "sl_failed": 0, "positions_failed": 5, "positions_opened": 18}	2025-09-15 18:05:25.765135+00
200	main_trader	HEALTHY	t	t	t	\N	18	0	0	\N	{"sl_set": 18, "sl_failed": 0, "positions_failed": 5, "positions_opened": 18}	2025-09-15 18:06:26.879698+00
201	main_trader	HEALTHY	t	t	t	\N	18	0	0	\N	{"sl_set": 19, "sl_failed": 0, "positions_failed": 5, "positions_opened": 19}	2025-09-15 18:07:27.772434+00
202	main_trader	HEALTHY	t	t	t	\N	20	0	0	\N	{"sl_set": 20, "sl_failed": 0, "positions_failed": 6, "positions_opened": 20}	2025-09-15 18:08:28.961068+00
203	main_trader	HEALTHY	t	t	t	\N	20	0	0	\N	{"sl_set": 20, "sl_failed": 0, "positions_failed": 6, "positions_opened": 20}	2025-09-15 18:09:30.16175+00
204	main_trader	HEALTHY	t	t	t	\N	20	0	0	\N	{"sl_set": 20, "sl_failed": 0, "positions_failed": 6, "positions_opened": 20}	2025-09-15 18:10:31.554026+00
205	main_trader	HEALTHY	t	t	t	\N	20	0	0	\N	{"sl_set": 20, "sl_failed": 0, "positions_failed": 6, "positions_opened": 20}	2025-09-15 18:11:32.704219+00
206	main_trader	HEALTHY	t	t	t	\N	20	0	0	\N	{"sl_set": 20, "sl_failed": 0, "positions_failed": 6, "positions_opened": 20}	2025-09-15 18:12:33.816781+00
207	main_trader	HEALTHY	t	t	t	\N	20	0	0	\N	{"sl_set": 20, "sl_failed": 0, "positions_failed": 6, "positions_opened": 20}	2025-09-15 18:13:35.177355+00
208	main_trader	HEALTHY	t	t	t	\N	20	0	0	\N	{"sl_set": 20, "sl_failed": 0, "positions_failed": 6, "positions_opened": 20}	2025-09-15 18:14:36.405321+00
209	main_trader	HEALTHY	t	t	t	\N	20	0	0	\N	{"sl_set": 20, "sl_failed": 0, "positions_failed": 6, "positions_opened": 20}	2025-09-15 18:15:37.587714+00
210	main_trader	HEALTHY	t	t	t	\N	20	0	0	\N	{"sl_set": 20, "sl_failed": 0, "positions_failed": 6, "positions_opened": 20}	2025-09-15 18:16:38.612247+00
211	main_trader	HEALTHY	t	t	t	\N	20	0	0	\N	{"sl_set": 20, "sl_failed": 0, "positions_failed": 6, "positions_opened": 20}	2025-09-15 18:17:39.649087+00
212	main_trader	HEALTHY	t	t	t	\N	20	0	0	\N	{"sl_set": 20, "sl_failed": 0, "positions_failed": 6, "positions_opened": 20}	2025-09-15 18:18:40.992805+00
213	main_trader	HEALTHY	t	t	t	\N	20	0	0	\N	{"sl_set": 20, "sl_failed": 0, "positions_failed": 6, "positions_opened": 20}	2025-09-15 18:19:42.228926+00
214	main_trader	HEALTHY	t	t	t	\N	20	0	0	\N	{"sl_set": 20, "sl_failed": 0, "positions_failed": 6, "positions_opened": 20}	2025-09-15 18:20:43.286095+00
215	main_trader	HEALTHY	t	t	t	\N	20	0	0	\N	{"sl_set": 20, "sl_failed": 0, "positions_failed": 7, "positions_opened": 20}	2025-09-15 18:21:44.419901+00
216	main_trader	HEALTHY	t	t	t	\N	20	0	0	\N	{"sl_set": 20, "sl_failed": 0, "positions_failed": 7, "positions_opened": 20}	2025-09-15 18:22:45.61364+00
217	main_trader	HEALTHY	t	t	t	\N	20	0	0	\N	{"sl_set": 20, "sl_failed": 0, "positions_failed": 7, "positions_opened": 20}	2025-09-15 18:23:46.88825+00
218	main_trader	HEALTHY	t	t	t	\N	20	0	0	\N	{"sl_set": 20, "sl_failed": 0, "positions_failed": 7, "positions_opened": 20}	2025-09-15 18:24:48.616189+00
219	main_trader	HEALTHY	t	t	t	\N	20	0	0	\N	{"sl_set": 20, "sl_failed": 0, "positions_failed": 7, "positions_opened": 20}	2025-09-15 18:25:49.660191+00
220	main_trader	HEALTHY	t	t	t	\N	20	0	0	\N	{"sl_set": 20, "sl_failed": 0, "positions_failed": 7, "positions_opened": 20}	2025-09-15 18:26:50.723108+00
221	main_trader	HEALTHY	t	t	t	\N	20	0	0	\N	{"sl_set": 20, "sl_failed": 0, "positions_failed": 7, "positions_opened": 20}	2025-09-15 18:27:51.801152+00
222	main_trader	HEALTHY	t	t	t	\N	20	0	0	\N	{"sl_set": 20, "sl_failed": 0, "positions_failed": 7, "positions_opened": 20}	2025-09-15 18:28:53.054656+00
223	main_trader	HEALTHY	t	t	t	\N	20	0	0	\N	{"sl_set": 20, "sl_failed": 0, "positions_failed": 7, "positions_opened": 20}	2025-09-15 18:29:54.174817+00
224	main_trader	HEALTHY	t	t	t	\N	20	0	0	\N	{"sl_set": 20, "sl_failed": 0, "positions_failed": 7, "positions_opened": 20}	2025-09-15 18:30:55.354738+00
225	main_trader	HEALTHY	t	t	t	\N	20	0	0	\N	{"sl_set": 20, "sl_failed": 0, "positions_failed": 7, "positions_opened": 20}	2025-09-15 18:31:56.504688+00
226	main_trader	HEALTHY	t	t	t	\N	20	0	0	\N	{"sl_set": 20, "sl_failed": 0, "positions_failed": 7, "positions_opened": 20}	2025-09-15 18:32:57.63608+00
227	main_trader	HEALTHY	t	t	t	\N	20	0	0	\N	{"sl_set": 20, "sl_failed": 0, "positions_failed": 7, "positions_opened": 20}	2025-09-15 18:33:58.900807+00
228	main_trader	HEALTHY	t	t	t	\N	20	0	0	\N	{"sl_set": 20, "sl_failed": 0, "positions_failed": 7, "positions_opened": 20}	2025-09-15 18:35:00.022077+00
229	main_trader	HEALTHY	t	t	t	\N	20	0	0	\N	{"sl_set": 20, "sl_failed": 0, "positions_failed": 7, "positions_opened": 20}	2025-09-15 18:36:01.230941+00
230	main_trader	HEALTHY	t	t	t	\N	21	0	0	\N	{"sl_set": 21, "sl_failed": 0, "positions_failed": 9, "positions_opened": 21}	2025-09-15 18:37:02.259129+00
231	main_trader	HEALTHY	t	t	t	\N	21	0	0	\N	{"sl_set": 21, "sl_failed": 0, "positions_failed": 9, "positions_opened": 21}	2025-09-15 18:38:03.447534+00
232	main_trader	HEALTHY	t	t	t	\N	21	0	0	\N	{"sl_set": 21, "sl_failed": 0, "positions_failed": 9, "positions_opened": 21}	2025-09-15 18:39:04.704904+00
233	main_trader	HEALTHY	t	t	t	\N	21	0	0	\N	{"sl_set": 21, "sl_failed": 0, "positions_failed": 9, "positions_opened": 21}	2025-09-15 18:40:05.926003+00
234	main_trader	HEALTHY	t	t	t	\N	21	0	0	\N	{"sl_set": 21, "sl_failed": 0, "positions_failed": 9, "positions_opened": 21}	2025-09-15 18:41:06.958648+00
235	main_trader	HEALTHY	t	t	t	\N	21	0	0	\N	{"sl_set": 21, "sl_failed": 0, "positions_failed": 9, "positions_opened": 21}	2025-09-15 18:42:08.03131+00
236	main_trader	HEALTHY	t	t	t	\N	21	0	0	\N	{"sl_set": 21, "sl_failed": 0, "positions_failed": 9, "positions_opened": 21}	2025-09-15 18:43:09.10156+00
237	main_trader	HEALTHY	t	t	t	\N	21	0	0	\N	{"sl_set": 21, "sl_failed": 0, "positions_failed": 9, "positions_opened": 21}	2025-09-15 18:44:10.44993+00
238	main_trader	HEALTHY	t	t	t	\N	21	0	0	\N	{"sl_set": 21, "sl_failed": 0, "positions_failed": 9, "positions_opened": 21}	2025-09-15 18:45:11.804963+00
239	main_trader	HEALTHY	t	t	t	\N	21	0	0	\N	{"sl_set": 21, "sl_failed": 0, "positions_failed": 9, "positions_opened": 21}	2025-09-15 18:46:12.940698+00
240	main_trader	HEALTHY	t	t	t	\N	21	0	0	\N	{"sl_set": 21, "sl_failed": 0, "positions_failed": 9, "positions_opened": 21}	2025-09-15 18:47:14.127542+00
241	main_trader	HEALTHY	t	t	t	\N	21	0	0	\N	{"sl_set": 21, "sl_failed": 0, "positions_failed": 9, "positions_opened": 21}	2025-09-15 18:48:15.219354+00
242	main_trader	HEALTHY	t	t	t	\N	21	0	0	\N	{"sl_set": 21, "sl_failed": 0, "positions_failed": 9, "positions_opened": 21}	2025-09-15 18:49:16.475191+00
243	main_trader	HEALTHY	t	t	t	\N	21	0	0	\N	{"sl_set": 21, "sl_failed": 0, "positions_failed": 9, "positions_opened": 21}	2025-09-15 18:50:17.652418+00
244	main_trader	HEALTHY	t	t	t	\N	23	0	0	\N	{"sl_set": 23, "sl_failed": 0, "positions_failed": 10, "positions_opened": 23}	2025-09-15 18:51:18.823283+00
245	main_trader	HEALTHY	t	t	t	\N	23	0	0	\N	{"sl_set": 23, "sl_failed": 0, "positions_failed": 10, "positions_opened": 23}	2025-09-15 18:52:20.051234+00
246	main_trader	HEALTHY	t	t	t	\N	23	0	0	\N	{"sl_set": 23, "sl_failed": 0, "positions_failed": 10, "positions_opened": 23}	2025-09-15 18:53:21.2528+00
247	main_trader	HEALTHY	t	t	t	\N	23	0	0	\N	{"sl_set": 23, "sl_failed": 0, "positions_failed": 10, "positions_opened": 23}	2025-09-15 18:54:22.415814+00
248	main_trader	HEALTHY	t	t	t	\N	23	0	0	\N	{"sl_set": 23, "sl_failed": 0, "positions_failed": 10, "positions_opened": 23}	2025-09-15 18:55:23.593922+00
249	main_trader	HEALTHY	t	t	t	\N	23	0	0	\N	{"sl_set": 23, "sl_failed": 0, "positions_failed": 10, "positions_opened": 23}	2025-09-15 18:56:24.651909+00
250	main_trader	HEALTHY	t	t	t	\N	23	0	0	\N	{"sl_set": 23, "sl_failed": 0, "positions_failed": 10, "positions_opened": 23}	2025-09-15 18:57:26.639158+00
251	main_trader	HEALTHY	t	t	t	\N	23	0	0	\N	{"sl_set": 23, "sl_failed": 0, "positions_failed": 10, "positions_opened": 23}	2025-09-15 18:58:27.751967+00
252	main_trader	HEALTHY	t	t	t	\N	23	0	0	\N	{"sl_set": 23, "sl_failed": 0, "positions_failed": 10, "positions_opened": 23}	2025-09-15 18:59:28.907524+00
253	main_trader	HEALTHY	t	t	t	\N	23	0	0	\N	{"sl_set": 23, "sl_failed": 0, "positions_failed": 10, "positions_opened": 23}	2025-09-15 19:00:30.086777+00
254	main_trader	HEALTHY	t	t	t	\N	23	0	0	\N	{"sl_set": 23, "sl_failed": 0, "positions_failed": 10, "positions_opened": 23}	2025-09-15 19:01:31.230726+00
255	main_trader	RUNNING	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-15 19:02:01.100192+00
256	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-15 19:03:02.393795+00
257	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-15 19:04:03.601834+00
258	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-15 19:05:04.981307+00
259	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-15 19:06:05.854431+00
260	main_trader	HEALTHY	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 0, "positions_opened": 3}	2025-09-15 19:07:06.98229+00
261	main_trader	HEALTHY	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 0, "positions_opened": 3}	2025-09-15 19:08:08.303847+00
262	main_trader	HEALTHY	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 0, "positions_opened": 3}	2025-09-15 19:09:09.535006+00
263	main_trader	HEALTHY	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 0, "positions_opened": 3}	2025-09-15 19:10:11.158279+00
264	main_trader	HEALTHY	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 0, "positions_opened": 3}	2025-09-15 19:11:12.211098+00
265	main_trader	HEALTHY	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 0, "positions_opened": 3}	2025-09-15 19:12:13.666284+00
266	main_trader	HEALTHY	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 0, "positions_opened": 3}	2025-09-15 19:13:15.489979+00
267	main_trader	HEALTHY	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 0, "positions_opened": 3}	2025-09-15 19:14:16.626679+00
268	main_trader	HEALTHY	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 0, "positions_opened": 3}	2025-09-15 19:15:17.674452+00
269	main_trader	HEALTHY	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 0, "positions_opened": 3}	2025-09-15 19:16:18.861307+00
270	main_trader	HEALTHY	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 0, "positions_opened": 3}	2025-09-15 19:17:20.031594+00
271	main_trader	HEALTHY	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 0, "positions_opened": 3}	2025-09-15 19:18:21.281351+00
272	main_trader	HEALTHY	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 0, "positions_opened": 3}	2025-09-15 19:19:22.51946+00
273	main_trader	HEALTHY	t	t	t	\N	4	0	0	\N	{"sl_set": 4, "sl_failed": 0, "positions_failed": 0, "positions_opened": 4}	2025-09-15 19:20:23.396259+00
274	main_trader	HEALTHY	t	t	t	\N	4	0	0	\N	{"sl_set": 4, "sl_failed": 0, "positions_failed": 0, "positions_opened": 4}	2025-09-15 19:21:24.474064+00
275	main_trader	HEALTHY	t	t	t	\N	4	0	0	\N	{"sl_set": 4, "sl_failed": 0, "positions_failed": 0, "positions_opened": 4}	2025-09-15 19:22:25.522997+00
276	main_trader	HEALTHY	t	t	t	\N	4	0	0	\N	{"sl_set": 4, "sl_failed": 0, "positions_failed": 0, "positions_opened": 4}	2025-09-15 19:23:26.771402+00
277	main_trader	HEALTHY	t	t	t	\N	4	0	0	\N	{"sl_set": 4, "sl_failed": 0, "positions_failed": 0, "positions_opened": 4}	2025-09-15 19:24:27.885864+00
278	main_trader	HEALTHY	t	t	t	\N	4	0	0	\N	{"sl_set": 4, "sl_failed": 0, "positions_failed": 0, "positions_opened": 4}	2025-09-15 19:25:28.93294+00
279	main_trader	HEALTHY	t	t	t	\N	4	0	0	\N	{"sl_set": 4, "sl_failed": 0, "positions_failed": 0, "positions_opened": 4}	2025-09-15 19:26:29.966888+00
280	main_trader	HEALTHY	t	t	t	\N	4	0	0	\N	{"sl_set": 4, "sl_failed": 0, "positions_failed": 0, "positions_opened": 4}	2025-09-15 19:27:31.132173+00
281	main_trader	HEALTHY	t	t	t	\N	4	0	0	\N	{"sl_set": 4, "sl_failed": 0, "positions_failed": 0, "positions_opened": 4}	2025-09-15 19:28:32.854567+00
282	main_trader	HEALTHY	t	t	t	\N	4	0	0	\N	{"sl_set": 4, "sl_failed": 0, "positions_failed": 0, "positions_opened": 4}	2025-09-15 19:29:34.019005+00
283	main_trader	HEALTHY	t	t	t	\N	4	0	0	\N	{"sl_set": 4, "sl_failed": 0, "positions_failed": 0, "positions_opened": 4}	2025-09-15 19:30:35.221973+00
284	main_trader	HEALTHY	t	t	t	\N	4	0	0	\N	{"sl_set": 4, "sl_failed": 0, "positions_failed": 0, "positions_opened": 4}	2025-09-15 19:31:36.281305+00
285	main_trader	HEALTHY	t	t	t	\N	4	0	0	\N	{"sl_set": 4, "sl_failed": 0, "positions_failed": 0, "positions_opened": 4}	2025-09-15 19:32:37.310005+00
286	main_trader	HEALTHY	t	t	t	\N	4	0	0	\N	{"sl_set": 4, "sl_failed": 0, "positions_failed": 0, "positions_opened": 4}	2025-09-15 19:33:38.643999+00
287	main_trader	HEALTHY	t	t	t	\N	4	0	0	\N	{"sl_set": 4, "sl_failed": 0, "positions_failed": 0, "positions_opened": 4}	2025-09-15 19:34:39.853201+00
288	main_trader	HEALTHY	t	t	t	\N	4	0	0	\N	{"sl_set": 4, "sl_failed": 0, "positions_failed": 1, "positions_opened": 4}	2025-09-15 19:35:40.931279+00
289	main_trader	HEALTHY	t	t	t	\N	4	0	0	\N	{"sl_set": 4, "sl_failed": 0, "positions_failed": 1, "positions_opened": 4}	2025-09-15 19:36:42.006421+00
290	main_trader	HEALTHY	t	t	t	\N	4	0	0	\N	{"sl_set": 4, "sl_failed": 0, "positions_failed": 1, "positions_opened": 4}	2025-09-15 19:37:43.480817+00
291	main_trader	HEALTHY	t	t	t	\N	4	0	0	\N	{"sl_set": 4, "sl_failed": 0, "positions_failed": 1, "positions_opened": 4}	2025-09-15 19:38:44.745137+00
292	main_trader	HEALTHY	t	t	t	\N	4	0	0	\N	{"sl_set": 4, "sl_failed": 0, "positions_failed": 1, "positions_opened": 4}	2025-09-15 19:39:45.955779+00
293	main_trader	HEALTHY	t	t	t	\N	4	0	0	\N	{"sl_set": 4, "sl_failed": 0, "positions_failed": 1, "positions_opened": 4}	2025-09-15 19:40:47.114552+00
294	main_trader	HEALTHY	t	t	t	\N	4	0	0	\N	{"sl_set": 4, "sl_failed": 0, "positions_failed": 1, "positions_opened": 4}	2025-09-15 19:41:48.167617+00
295	main_trader	HEALTHY	t	t	t	\N	4	0	0	\N	{"sl_set": 4, "sl_failed": 0, "positions_failed": 1, "positions_opened": 4}	2025-09-15 19:42:49.308131+00
296	main_trader	HEALTHY	t	t	t	\N	4	0	0	\N	{"sl_set": 4, "sl_failed": 0, "positions_failed": 1, "positions_opened": 4}	2025-09-15 19:43:50.802462+00
297	main_trader	HEALTHY	t	t	t	\N	4	0	0	\N	{"sl_set": 4, "sl_failed": 0, "positions_failed": 1, "positions_opened": 4}	2025-09-15 19:44:51.89855+00
298	main_trader	HEALTHY	t	t	t	\N	4	0	0	\N	{"sl_set": 4, "sl_failed": 0, "positions_failed": 1, "positions_opened": 4}	2025-09-15 19:45:53.02629+00
299	main_trader	HEALTHY	t	t	t	\N	4	0	0	\N	{"sl_set": 4, "sl_failed": 0, "positions_failed": 1, "positions_opened": 4}	2025-09-15 19:46:54.159008+00
300	main_trader	HEALTHY	t	t	t	\N	4	0	0	\N	{"sl_set": 4, "sl_failed": 0, "positions_failed": 1, "positions_opened": 4}	2025-09-15 19:47:55.185741+00
301	main_trader	HEALTHY	t	t	t	\N	4	0	0	\N	{"sl_set": 4, "sl_failed": 0, "positions_failed": 1, "positions_opened": 4}	2025-09-15 19:48:56.433184+00
302	main_trader	HEALTHY	t	t	t	\N	4	0	0	\N	{"sl_set": 4, "sl_failed": 0, "positions_failed": 1, "positions_opened": 4}	2025-09-15 19:49:57.526699+00
303	main_trader	HEALTHY	t	t	t	\N	7	0	0	\N	{"sl_set": 8, "sl_failed": 0, "positions_failed": 2, "positions_opened": 8}	2025-09-15 19:50:58.538354+00
304	main_trader	HEALTHY	t	t	t	\N	10	0	0	\N	{"sl_set": 10, "sl_failed": 0, "positions_failed": 2, "positions_opened": 10}	2025-09-15 19:51:59.691211+00
305	main_trader	HEALTHY	t	t	t	\N	10	0	0	\N	{"sl_set": 10, "sl_failed": 0, "positions_failed": 2, "positions_opened": 10}	2025-09-15 19:53:00.858564+00
306	main_trader	HEALTHY	t	t	t	\N	10	0	0	\N	{"sl_set": 10, "sl_failed": 0, "positions_failed": 2, "positions_opened": 10}	2025-09-15 19:54:02.119207+00
307	main_trader	HEALTHY	t	t	t	\N	10	0	0	\N	{"sl_set": 10, "sl_failed": 0, "positions_failed": 2, "positions_opened": 10}	2025-09-15 19:55:03.332773+00
308	main_trader	HEALTHY	t	t	t	\N	10	0	0	\N	{"sl_set": 10, "sl_failed": 0, "positions_failed": 2, "positions_opened": 10}	2025-09-15 19:56:04.467446+00
309	main_trader	HEALTHY	t	t	t	\N	10	0	0	\N	{"sl_set": 10, "sl_failed": 0, "positions_failed": 2, "positions_opened": 10}	2025-09-15 19:57:05.50538+00
310	main_trader	HEALTHY	t	t	t	\N	10	0	0	\N	{"sl_set": 10, "sl_failed": 0, "positions_failed": 2, "positions_opened": 10}	2025-09-15 19:58:06.631+00
311	main_trader	HEALTHY	t	t	t	\N	10	0	0	\N	{"sl_set": 10, "sl_failed": 0, "positions_failed": 2, "positions_opened": 10}	2025-09-15 19:59:08.316486+00
312	main_trader	HEALTHY	t	t	t	\N	10	0	0	\N	{"sl_set": 10, "sl_failed": 0, "positions_failed": 2, "positions_opened": 10}	2025-09-15 20:00:09.421394+00
313	main_trader	HEALTHY	t	t	t	\N	10	0	0	\N	{"sl_set": 10, "sl_failed": 0, "positions_failed": 2, "positions_opened": 10}	2025-09-15 20:01:10.572384+00
314	main_trader	HEALTHY	t	t	t	\N	10	0	0	\N	{"sl_set": 10, "sl_failed": 0, "positions_failed": 2, "positions_opened": 10}	2025-09-15 20:02:11.689331+00
315	main_trader	HEALTHY	t	t	t	\N	10	0	0	\N	{"sl_set": 10, "sl_failed": 0, "positions_failed": 2, "positions_opened": 10}	2025-09-15 20:03:12.817793+00
316	main_trader	HEALTHY	t	t	t	\N	10	0	0	\N	{"sl_set": 10, "sl_failed": 0, "positions_failed": 2, "positions_opened": 10}	2025-09-15 20:04:14.070891+00
317	main_trader	HEALTHY	t	t	t	\N	10	0	0	\N	{"sl_set": 10, "sl_failed": 0, "positions_failed": 2, "positions_opened": 10}	2025-09-15 20:05:15.207806+00
318	main_trader	HEALTHY	t	t	t	\N	10	0	0	\N	{"sl_set": 10, "sl_failed": 0, "positions_failed": 2, "positions_opened": 10}	2025-09-15 20:06:16.320051+00
319	main_trader	HEALTHY	t	t	t	\N	11	0	0	\N	{"sl_set": 11, "sl_failed": 0, "positions_failed": 2, "positions_opened": 11}	2025-09-15 20:07:17.36089+00
320	main_trader	HEALTHY	t	t	t	\N	11	0	0	\N	{"sl_set": 11, "sl_failed": 0, "positions_failed": 2, "positions_opened": 11}	2025-09-15 20:08:18.424426+00
321	main_trader	HEALTHY	t	t	t	\N	11	0	0	\N	{"sl_set": 11, "sl_failed": 0, "positions_failed": 2, "positions_opened": 11}	2025-09-15 20:09:19.70748+00
322	main_trader	HEALTHY	t	t	t	\N	11	0	0	\N	{"sl_set": 11, "sl_failed": 0, "positions_failed": 2, "positions_opened": 11}	2025-09-15 20:10:20.930388+00
323	main_trader	HEALTHY	t	t	t	\N	11	0	0	\N	{"sl_set": 11, "sl_failed": 0, "positions_failed": 2, "positions_opened": 11}	2025-09-15 20:11:22.044614+00
324	main_trader	HEALTHY	t	t	t	\N	11	0	0	\N	{"sl_set": 11, "sl_failed": 0, "positions_failed": 2, "positions_opened": 11}	2025-09-15 20:12:23.199572+00
325	main_trader	HEALTHY	t	t	t	\N	11	0	0	\N	{"sl_set": 11, "sl_failed": 0, "positions_failed": 2, "positions_opened": 11}	2025-09-15 20:13:24.270265+00
326	main_trader	HEALTHY	t	t	t	\N	11	0	0	\N	{"sl_set": 11, "sl_failed": 0, "positions_failed": 2, "positions_opened": 11}	2025-09-15 20:14:26.099631+00
327	main_trader	HEALTHY	t	t	t	\N	11	0	0	\N	{"sl_set": 11, "sl_failed": 0, "positions_failed": 2, "positions_opened": 11}	2025-09-15 20:15:27.251607+00
328	main_trader	HEALTHY	t	t	t	\N	11	0	0	\N	{"sl_set": 11, "sl_failed": 0, "positions_failed": 2, "positions_opened": 11}	2025-09-15 20:16:28.371676+00
329	main_trader	HEALTHY	t	t	t	\N	11	0	0	\N	{"sl_set": 11, "sl_failed": 0, "positions_failed": 2, "positions_opened": 11}	2025-09-15 20:17:29.49834+00
330	main_trader	HEALTHY	t	t	t	\N	11	0	0	\N	{"sl_set": 11, "sl_failed": 0, "positions_failed": 2, "positions_opened": 11}	2025-09-15 20:18:30.574351+00
331	main_trader	HEALTHY	t	t	t	\N	11	0	0	\N	{"sl_set": 11, "sl_failed": 0, "positions_failed": 2, "positions_opened": 11}	2025-09-15 20:19:31.949316+00
332	main_trader	HEALTHY	t	t	t	\N	12	0	0	\N	{"sl_set": 12, "sl_failed": 0, "positions_failed": 2, "positions_opened": 12}	2025-09-15 20:20:32.893911+00
333	main_trader	HEALTHY	t	t	t	\N	12	0	0	\N	{"sl_set": 12, "sl_failed": 0, "positions_failed": 2, "positions_opened": 12}	2025-09-15 20:21:34.018871+00
334	main_trader	HEALTHY	t	t	t	\N	12	0	0	\N	{"sl_set": 12, "sl_failed": 0, "positions_failed": 2, "positions_opened": 12}	2025-09-15 20:22:35.14602+00
335	main_trader	HEALTHY	t	t	t	\N	12	0	0	\N	{"sl_set": 12, "sl_failed": 0, "positions_failed": 2, "positions_opened": 12}	2025-09-15 20:23:36.174939+00
336	main_trader	HEALTHY	t	t	t	\N	12	0	0	\N	{"sl_set": 12, "sl_failed": 0, "positions_failed": 2, "positions_opened": 12}	2025-09-15 20:24:37.556087+00
337	main_trader	HEALTHY	t	t	t	\N	12	0	0	\N	{"sl_set": 12, "sl_failed": 0, "positions_failed": 2, "positions_opened": 12}	2025-09-15 20:25:38.792085+00
338	main_trader	HEALTHY	t	t	t	\N	12	0	0	\N	{"sl_set": 12, "sl_failed": 0, "positions_failed": 2, "positions_opened": 12}	2025-09-15 20:26:39.822187+00
339	main_trader	HEALTHY	t	t	t	\N	12	0	0	\N	{"sl_set": 12, "sl_failed": 0, "positions_failed": 2, "positions_opened": 12}	2025-09-15 20:27:40.954542+00
340	main_trader	HEALTHY	t	t	t	\N	12	0	0	\N	{"sl_set": 12, "sl_failed": 0, "positions_failed": 2, "positions_opened": 12}	2025-09-15 20:28:42.118908+00
341	main_trader	HEALTHY	t	t	t	\N	12	0	0	\N	{"sl_set": 12, "sl_failed": 0, "positions_failed": 2, "positions_opened": 12}	2025-09-15 20:29:43.878552+00
342	main_trader	HEALTHY	t	t	t	\N	12	0	0	\N	{"sl_set": 12, "sl_failed": 0, "positions_failed": 2, "positions_opened": 12}	2025-09-15 20:30:45.067365+00
343	main_trader	HEALTHY	t	t	t	\N	12	0	0	\N	{"sl_set": 12, "sl_failed": 0, "positions_failed": 2, "positions_opened": 12}	2025-09-15 20:31:46.153525+00
344	main_trader	HEALTHY	t	t	t	\N	12	0	0	\N	{"sl_set": 12, "sl_failed": 0, "positions_failed": 2, "positions_opened": 12}	2025-09-15 20:32:47.203816+00
345	main_trader	HEALTHY	t	t	t	\N	12	0	0	\N	{"sl_set": 12, "sl_failed": 0, "positions_failed": 2, "positions_opened": 12}	2025-09-15 20:33:48.288361+00
346	main_trader	HEALTHY	t	t	t	\N	12	0	0	\N	{"sl_set": 12, "sl_failed": 0, "positions_failed": 2, "positions_opened": 12}	2025-09-15 20:34:49.606363+00
347	main_trader	HEALTHY	t	t	t	\N	12	0	0	\N	{"sl_set": 12, "sl_failed": 0, "positions_failed": 2, "positions_opened": 12}	2025-09-15 20:35:50.739415+00
348	main_trader	HEALTHY	t	t	t	\N	12	0	0	\N	{"sl_set": 12, "sl_failed": 0, "positions_failed": 2, "positions_opened": 12}	2025-09-15 20:36:51.887286+00
349	main_trader	HEALTHY	t	t	t	\N	12	0	0	\N	{"sl_set": 12, "sl_failed": 0, "positions_failed": 2, "positions_opened": 12}	2025-09-15 20:37:52.923266+00
350	main_trader	HEALTHY	t	t	t	\N	12	0	0	\N	{"sl_set": 12, "sl_failed": 0, "positions_failed": 2, "positions_opened": 12}	2025-09-15 20:38:54.017643+00
351	main_trader	HEALTHY	t	t	t	\N	12	0	0	\N	{"sl_set": 12, "sl_failed": 0, "positions_failed": 2, "positions_opened": 12}	2025-09-15 20:39:55.4171+00
352	main_trader	HEALTHY	t	t	t	\N	12	0	0	\N	{"sl_set": 12, "sl_failed": 0, "positions_failed": 2, "positions_opened": 12}	2025-09-15 20:40:56.544598+00
353	main_trader	HEALTHY	t	t	t	\N	12	0	0	\N	{"sl_set": 12, "sl_failed": 0, "positions_failed": 2, "positions_opened": 12}	2025-09-15 20:41:57.685399+00
354	main_trader	HEALTHY	t	t	t	\N	12	0	0	\N	{"sl_set": 12, "sl_failed": 0, "positions_failed": 2, "positions_opened": 12}	2025-09-15 20:42:58.783649+00
355	main_trader	HEALTHY	t	t	t	\N	12	0	0	\N	{"sl_set": 12, "sl_failed": 0, "positions_failed": 2, "positions_opened": 12}	2025-09-15 20:43:59.891501+00
356	main_trader	HEALTHY	t	t	t	\N	12	0	0	\N	{"sl_set": 12, "sl_failed": 0, "positions_failed": 2, "positions_opened": 12}	2025-09-15 20:45:01.175964+00
357	main_trader	HEALTHY	t	t	t	\N	12	0	0	\N	{"sl_set": 12, "sl_failed": 0, "positions_failed": 2, "positions_opened": 12}	2025-09-15 20:46:02.309834+00
358	main_trader	HEALTHY	t	t	t	\N	12	0	0	\N	{"sl_set": 12, "sl_failed": 0, "positions_failed": 2, "positions_opened": 12}	2025-09-15 20:47:03.516702+00
359	main_trader	HEALTHY	t	t	t	\N	12	0	0	\N	{"sl_set": 12, "sl_failed": 0, "positions_failed": 2, "positions_opened": 12}	2025-09-15 20:48:04.567802+00
360	main_trader	HEALTHY	t	t	t	\N	12	0	0	\N	{"sl_set": 12, "sl_failed": 0, "positions_failed": 2, "positions_opened": 12}	2025-09-15 20:49:05.619019+00
361	main_trader	HEALTHY	t	t	t	\N	12	0	0	\N	{"sl_set": 12, "sl_failed": 0, "positions_failed": 2, "positions_opened": 12}	2025-09-15 20:50:06.9061+00
362	main_trader	HEALTHY	t	t	t	\N	12	0	0	\N	{"sl_set": 12, "sl_failed": 0, "positions_failed": 2, "positions_opened": 12}	2025-09-15 20:51:08.165017+00
363	main_trader	HEALTHY	t	t	t	\N	12	0	0	\N	{"sl_set": 12, "sl_failed": 0, "positions_failed": 2, "positions_opened": 12}	2025-09-15 20:52:09.216488+00
364	main_trader	HEALTHY	t	t	t	\N	12	0	0	\N	{"sl_set": 12, "sl_failed": 0, "positions_failed": 2, "positions_opened": 12}	2025-09-15 20:53:10.372335+00
365	main_trader	HEALTHY	t	t	t	\N	12	0	0	\N	{"sl_set": 12, "sl_failed": 0, "positions_failed": 2, "positions_opened": 12}	2025-09-15 20:54:11.423636+00
366	main_trader	HEALTHY	t	t	t	\N	12	0	0	\N	{"sl_set": 12, "sl_failed": 0, "positions_failed": 2, "positions_opened": 12}	2025-09-15 20:55:13.141415+00
367	main_trader	HEALTHY	t	t	t	\N	12	0	0	\N	{"sl_set": 12, "sl_failed": 0, "positions_failed": 2, "positions_opened": 12}	2025-09-15 20:56:14.283137+00
368	main_trader	HEALTHY	t	t	t	\N	12	0	0	\N	{"sl_set": 12, "sl_failed": 0, "positions_failed": 2, "positions_opened": 12}	2025-09-15 20:57:15.329661+00
369	main_trader	HEALTHY	t	t	t	\N	12	0	0	\N	{"sl_set": 12, "sl_failed": 0, "positions_failed": 2, "positions_opened": 12}	2025-09-15 20:58:16.46163+00
370	main_trader	HEALTHY	t	t	t	\N	12	0	0	\N	{"sl_set": 12, "sl_failed": 0, "positions_failed": 2, "positions_opened": 12}	2025-09-15 20:59:17.513543+00
371	main_trader	HEALTHY	t	t	t	\N	12	0	0	\N	{"sl_set": 12, "sl_failed": 0, "positions_failed": 2, "positions_opened": 12}	2025-09-15 21:00:18.842419+00
372	main_trader	HEALTHY	t	t	t	\N	12	0	0	\N	{"sl_set": 12, "sl_failed": 0, "positions_failed": 2, "positions_opened": 12}	2025-09-15 21:01:20.070043+00
373	main_trader	HEALTHY	t	t	t	\N	12	0	0	\N	{"sl_set": 12, "sl_failed": 0, "positions_failed": 2, "positions_opened": 12}	2025-09-15 21:02:21.212622+00
374	main_trader	HEALTHY	t	t	t	\N	12	0	0	\N	{"sl_set": 12, "sl_failed": 0, "positions_failed": 2, "positions_opened": 12}	2025-09-15 21:03:22.404423+00
375	main_trader	HEALTHY	t	t	t	\N	12	0	0	\N	{"sl_set": 12, "sl_failed": 0, "positions_failed": 2, "positions_opened": 12}	2025-09-15 21:04:23.487643+00
376	main_trader	HEALTHY	t	t	t	\N	12	0	0	\N	{"sl_set": 12, "sl_failed": 0, "positions_failed": 2, "positions_opened": 12}	2025-09-15 21:05:24.849008+00
377	main_trader	HEALTHY	t	t	t	\N	12	0	0	\N	{"sl_set": 13, "sl_failed": 0, "positions_failed": 2, "positions_opened": 13}	2025-09-15 21:06:25.807968+00
378	main_trader	HEALTHY	t	t	t	\N	13	0	0	\N	{"sl_set": 13, "sl_failed": 0, "positions_failed": 3, "positions_opened": 13}	2025-09-15 21:07:26.89118+00
379	main_trader	HEALTHY	t	t	t	\N	13	0	0	\N	{"sl_set": 13, "sl_failed": 0, "positions_failed": 3, "positions_opened": 13}	2025-09-15 21:08:27.960563+00
380	main_trader	HEALTHY	t	t	t	\N	13	0	0	\N	{"sl_set": 13, "sl_failed": 0, "positions_failed": 3, "positions_opened": 13}	2025-09-15 21:09:29.017802+00
381	main_trader	HEALTHY	t	t	t	\N	13	0	0	\N	{"sl_set": 13, "sl_failed": 0, "positions_failed": 3, "positions_opened": 13}	2025-09-15 21:10:30.327918+00
382	main_trader	HEALTHY	t	t	t	\N	13	0	0	\N	{"sl_set": 13, "sl_failed": 0, "positions_failed": 3, "positions_opened": 13}	2025-09-15 21:11:31.579369+00
383	main_trader	HEALTHY	t	t	t	\N	13	0	0	\N	{"sl_set": 13, "sl_failed": 0, "positions_failed": 3, "positions_opened": 13}	2025-09-15 21:12:32.748687+00
384	main_trader	HEALTHY	t	t	t	\N	13	0	0	\N	{"sl_set": 13, "sl_failed": 0, "positions_failed": 3, "positions_opened": 13}	2025-09-15 21:13:33.932894+00
385	main_trader	HEALTHY	t	t	t	\N	13	0	0	\N	{"sl_set": 13, "sl_failed": 0, "positions_failed": 3, "positions_opened": 13}	2025-09-15 21:14:35.029702+00
386	main_trader	HEALTHY	t	t	t	\N	13	0	0	\N	{"sl_set": 13, "sl_failed": 0, "positions_failed": 3, "positions_opened": 13}	2025-09-15 21:15:36.89088+00
387	main_trader	HEALTHY	t	t	t	\N	13	0	0	\N	{"sl_set": 13, "sl_failed": 0, "positions_failed": 3, "positions_opened": 13}	2025-09-15 21:16:38.121853+00
388	main_trader	HEALTHY	t	t	t	\N	13	0	0	\N	{"sl_set": 13, "sl_failed": 0, "positions_failed": 3, "positions_opened": 13}	2025-09-15 21:17:39.20814+00
389	main_trader	HEALTHY	t	t	t	\N	13	0	0	\N	{"sl_set": 13, "sl_failed": 0, "positions_failed": 3, "positions_opened": 13}	2025-09-15 21:18:40.363927+00
390	main_trader	HEALTHY	t	t	t	\N	13	0	0	\N	{"sl_set": 13, "sl_failed": 0, "positions_failed": 3, "positions_opened": 13}	2025-09-15 21:19:41.439531+00
391	main_trader	HEALTHY	t	t	t	\N	14	0	0	\N	{"sl_set": 14, "sl_failed": 0, "positions_failed": 3, "positions_opened": 14}	2025-09-15 21:20:42.734412+00
392	main_trader	HEALTHY	t	t	t	\N	14	0	0	\N	{"sl_set": 14, "sl_failed": 0, "positions_failed": 3, "positions_opened": 14}	2025-09-15 21:21:43.912846+00
393	main_trader	HEALTHY	t	t	t	\N	14	0	0	\N	{"sl_set": 14, "sl_failed": 0, "positions_failed": 3, "positions_opened": 14}	2025-09-15 21:22:45.105643+00
394	main_trader	HEALTHY	t	t	t	\N	14	0	0	\N	{"sl_set": 14, "sl_failed": 0, "positions_failed": 3, "positions_opened": 14}	2025-09-15 21:23:46.163399+00
395	main_trader	HEALTHY	t	t	t	\N	14	0	0	\N	{"sl_set": 14, "sl_failed": 0, "positions_failed": 3, "positions_opened": 14}	2025-09-15 21:24:47.272465+00
396	main_trader	HEALTHY	t	t	t	\N	14	0	0	\N	{"sl_set": 14, "sl_failed": 0, "positions_failed": 3, "positions_opened": 14}	2025-09-15 21:25:49.051285+00
397	main_trader	HEALTHY	t	t	t	\N	14	0	0	\N	{"sl_set": 14, "sl_failed": 0, "positions_failed": 3, "positions_opened": 14}	2025-09-15 21:26:50.218587+00
398	main_trader	HEALTHY	t	t	t	\N	14	0	0	\N	{"sl_set": 14, "sl_failed": 0, "positions_failed": 3, "positions_opened": 14}	2025-09-15 21:27:51.409134+00
399	main_trader	HEALTHY	t	t	t	\N	14	0	0	\N	{"sl_set": 14, "sl_failed": 0, "positions_failed": 3, "positions_opened": 14}	2025-09-15 21:28:52.469331+00
400	main_trader	HEALTHY	t	t	t	\N	14	0	0	\N	{"sl_set": 14, "sl_failed": 0, "positions_failed": 3, "positions_opened": 14}	2025-09-15 21:29:53.609821+00
401	main_trader	HEALTHY	t	t	t	\N	14	0	0	\N	{"sl_set": 14, "sl_failed": 0, "positions_failed": 3, "positions_opened": 14}	2025-09-15 21:30:54.986811+00
402	main_trader	HEALTHY	t	t	t	\N	14	0	0	\N	{"sl_set": 14, "sl_failed": 0, "positions_failed": 3, "positions_opened": 14}	2025-09-15 21:31:56.291111+00
403	main_trader	HEALTHY	t	t	t	\N	14	0	0	\N	{"sl_set": 14, "sl_failed": 0, "positions_failed": 3, "positions_opened": 14}	2025-09-15 21:32:57.336647+00
404	main_trader	HEALTHY	t	t	t	\N	14	0	0	\N	{"sl_set": 14, "sl_failed": 0, "positions_failed": 3, "positions_opened": 14}	2025-09-15 21:33:58.39306+00
405	main_trader	HEALTHY	t	t	t	\N	14	0	0	\N	{"sl_set": 14, "sl_failed": 0, "positions_failed": 3, "positions_opened": 14}	2025-09-15 21:34:59.538573+00
406	main_trader	HEALTHY	t	t	t	\N	16	0	0	\N	{"sl_set": 16, "sl_failed": 0, "positions_failed": 3, "positions_opened": 16}	2025-09-15 21:36:00.906704+00
407	main_trader	HEALTHY	t	t	t	\N	16	0	0	\N	{"sl_set": 16, "sl_failed": 0, "positions_failed": 3, "positions_opened": 16}	2025-09-15 21:37:02.076256+00
408	main_trader	HEALTHY	t	t	t	\N	16	0	0	\N	{"sl_set": 16, "sl_failed": 0, "positions_failed": 3, "positions_opened": 16}	2025-09-15 21:38:03.186541+00
409	main_trader	HEALTHY	t	t	t	\N	16	0	0	\N	{"sl_set": 16, "sl_failed": 0, "positions_failed": 3, "positions_opened": 16}	2025-09-15 21:39:04.286627+00
410	main_trader	HEALTHY	t	t	t	\N	16	0	0	\N	{"sl_set": 16, "sl_failed": 0, "positions_failed": 3, "positions_opened": 16}	2025-09-15 21:40:05.390096+00
411	main_trader	HEALTHY	t	t	t	\N	16	0	0	\N	{"sl_set": 16, "sl_failed": 0, "positions_failed": 3, "positions_opened": 16}	2025-09-15 21:41:07.142739+00
412	main_trader	HEALTHY	t	t	t	\N	16	0	0	\N	{"sl_set": 16, "sl_failed": 0, "positions_failed": 3, "positions_opened": 16}	2025-09-15 21:42:08.435687+00
413	main_trader	HEALTHY	t	t	t	\N	16	0	0	\N	{"sl_set": 16, "sl_failed": 0, "positions_failed": 3, "positions_opened": 16}	2025-09-15 21:43:09.567687+00
414	main_trader	HEALTHY	t	t	t	\N	16	0	0	\N	{"sl_set": 16, "sl_failed": 0, "positions_failed": 3, "positions_opened": 16}	2025-09-15 21:44:10.730856+00
415	main_trader	HEALTHY	t	t	t	\N	16	0	0	\N	{"sl_set": 16, "sl_failed": 0, "positions_failed": 3, "positions_opened": 16}	2025-09-15 21:45:11.797252+00
416	main_trader	HEALTHY	t	t	t	\N	16	0	0	\N	{"sl_set": 16, "sl_failed": 0, "positions_failed": 3, "positions_opened": 16}	2025-09-15 21:46:13.116642+00
417	main_trader	HEALTHY	t	t	t	\N	16	0	0	\N	{"sl_set": 16, "sl_failed": 0, "positions_failed": 3, "positions_opened": 16}	2025-09-15 21:47:14.297072+00
418	main_trader	HEALTHY	t	t	t	\N	16	0	0	\N	{"sl_set": 16, "sl_failed": 0, "positions_failed": 3, "positions_opened": 16}	2025-09-15 21:48:15.458009+00
419	main_trader	HEALTHY	t	t	t	\N	16	0	0	\N	{"sl_set": 16, "sl_failed": 0, "positions_failed": 3, "positions_opened": 16}	2025-09-15 21:49:16.658179+00
420	main_trader	HEALTHY	t	t	t	\N	17	0	0	\N	{"sl_set": 17, "sl_failed": 0, "positions_failed": 3, "positions_opened": 17}	2025-09-15 21:50:17.566499+00
421	main_trader	HEALTHY	t	t	t	\N	17	0	0	\N	{"sl_set": 17, "sl_failed": 0, "positions_failed": 3, "positions_opened": 17}	2025-09-15 21:51:18.885568+00
422	main_trader	HEALTHY	t	t	t	\N	17	0	0	\N	{"sl_set": 17, "sl_failed": 0, "positions_failed": 3, "positions_opened": 17}	2025-09-15 21:52:20.027114+00
423	main_trader	HEALTHY	t	t	t	\N	17	0	0	\N	{"sl_set": 17, "sl_failed": 0, "positions_failed": 3, "positions_opened": 17}	2025-09-15 21:53:21.123249+00
424	main_trader	HEALTHY	t	t	t	\N	17	0	0	\N	{"sl_set": 17, "sl_failed": 0, "positions_failed": 3, "positions_opened": 17}	2025-09-15 21:54:22.240204+00
425	main_trader	HEALTHY	t	t	t	\N	17	0	0	\N	{"sl_set": 17, "sl_failed": 0, "positions_failed": 3, "positions_opened": 17}	2025-09-15 21:55:23.417843+00
426	main_trader	HEALTHY	t	t	t	\N	17	0	0	\N	{"sl_set": 17, "sl_failed": 0, "positions_failed": 3, "positions_opened": 17}	2025-09-15 21:56:25.17242+00
427	main_trader	HEALTHY	t	t	t	\N	17	0	0	\N	{"sl_set": 17, "sl_failed": 0, "positions_failed": 3, "positions_opened": 17}	2025-09-15 21:57:26.420369+00
428	main_trader	HEALTHY	t	t	t	\N	17	0	0	\N	{"sl_set": 17, "sl_failed": 0, "positions_failed": 3, "positions_opened": 17}	2025-09-15 21:58:27.577128+00
429	main_trader	HEALTHY	t	t	t	\N	17	0	0	\N	{"sl_set": 17, "sl_failed": 0, "positions_failed": 3, "positions_opened": 17}	2025-09-15 21:59:28.641322+00
430	main_trader	HEALTHY	t	t	t	\N	17	0	0	\N	{"sl_set": 17, "sl_failed": 0, "positions_failed": 3, "positions_opened": 17}	2025-09-15 22:00:29.748042+00
431	main_trader	HEALTHY	t	t	t	\N	17	0	0	\N	{"sl_set": 17, "sl_failed": 0, "positions_failed": 3, "positions_opened": 17}	2025-09-15 22:01:31.070538+00
432	main_trader	HEALTHY	t	t	t	\N	17	0	0	\N	{"sl_set": 17, "sl_failed": 0, "positions_failed": 3, "positions_opened": 17}	2025-09-15 22:02:32.240133+00
433	main_trader	HEALTHY	t	t	t	\N	17	0	0	\N	{"sl_set": 17, "sl_failed": 0, "positions_failed": 3, "positions_opened": 17}	2025-09-15 22:03:33.613913+00
434	main_trader	HEALTHY	t	t	t	\N	17	0	0	\N	{"sl_set": 17, "sl_failed": 0, "positions_failed": 3, "positions_opened": 17}	2025-09-15 22:04:35.678119+00
435	main_trader	HEALTHY	t	t	t	\N	17	0	0	\N	{"sl_set": 17, "sl_failed": 0, "positions_failed": 3, "positions_opened": 17}	2025-09-15 22:05:37.472669+00
436	main_trader	HEALTHY	t	t	t	\N	18	0	0	\N	{"sl_set": 18, "sl_failed": 0, "positions_failed": 3, "positions_opened": 18}	2025-09-15 22:06:38.597216+00
437	main_trader	HEALTHY	t	t	t	\N	19	0	0	\N	{"sl_set": 19, "sl_failed": 0, "positions_failed": 3, "positions_opened": 19}	2025-09-15 22:07:39.832655+00
438	main_trader	HEALTHY	t	t	t	\N	19	0	0	\N	{"sl_set": 19, "sl_failed": 0, "positions_failed": 3, "positions_opened": 19}	2025-09-15 22:08:40.894301+00
439	main_trader	HEALTHY	t	t	t	\N	19	0	0	\N	{"sl_set": 19, "sl_failed": 0, "positions_failed": 3, "positions_opened": 19}	2025-09-15 22:09:42.000886+00
440	main_trader	HEALTHY	t	t	t	\N	19	0	0	\N	{"sl_set": 19, "sl_failed": 0, "positions_failed": 3, "positions_opened": 19}	2025-09-15 22:10:43.064855+00
441	main_trader	HEALTHY	t	t	t	\N	19	0	0	\N	{"sl_set": 19, "sl_failed": 0, "positions_failed": 3, "positions_opened": 19}	2025-09-15 22:11:44.850097+00
442	main_trader	HEALTHY	t	t	t	\N	19	0	0	\N	{"sl_set": 19, "sl_failed": 0, "positions_failed": 3, "positions_opened": 19}	2025-09-15 22:12:46.124394+00
443	main_trader	HEALTHY	t	t	t	\N	19	0	0	\N	{"sl_set": 19, "sl_failed": 0, "positions_failed": 3, "positions_opened": 19}	2025-09-15 22:13:47.33262+00
444	main_trader	HEALTHY	t	t	t	\N	19	0	0	\N	{"sl_set": 19, "sl_failed": 0, "positions_failed": 3, "positions_opened": 19}	2025-09-15 22:14:48.404568+00
445	main_trader	HEALTHY	t	t	t	\N	19	0	0	\N	{"sl_set": 19, "sl_failed": 0, "positions_failed": 3, "positions_opened": 19}	2025-09-15 22:15:49.516953+00
446	main_trader	HEALTHY	t	t	t	\N	19	0	0	\N	{"sl_set": 19, "sl_failed": 0, "positions_failed": 3, "positions_opened": 19}	2025-09-15 22:16:50.896971+00
447	main_trader	HEALTHY	t	t	t	\N	19	0	0	\N	{"sl_set": 19, "sl_failed": 0, "positions_failed": 3, "positions_opened": 19}	2025-09-15 22:17:52.179054+00
448	main_trader	HEALTHY	t	t	t	\N	19	0	0	\N	{"sl_set": 19, "sl_failed": 0, "positions_failed": 3, "positions_opened": 19}	2025-09-15 22:18:53.396472+00
449	main_trader	HEALTHY	t	t	t	\N	19	0	0	\N	{"sl_set": 19, "sl_failed": 0, "positions_failed": 3, "positions_opened": 19}	2025-09-15 22:19:54.44708+00
450	main_trader	HEALTHY	t	t	t	\N	22	0	0	\N	{"sl_set": 22, "sl_failed": 0, "positions_failed": 3, "positions_opened": 22}	2025-09-15 22:20:55.419028+00
451	main_trader	HEALTHY	t	t	t	\N	22	0	0	\N	{"sl_set": 22, "sl_failed": 0, "positions_failed": 4, "positions_opened": 22}	2025-09-15 22:21:56.778428+00
452	main_trader	HEALTHY	t	t	t	\N	22	0	0	\N	{"sl_set": 22, "sl_failed": 0, "positions_failed": 4, "positions_opened": 22}	2025-09-15 22:22:57.960712+00
453	main_trader	HEALTHY	t	t	t	\N	22	0	0	\N	{"sl_set": 22, "sl_failed": 0, "positions_failed": 4, "positions_opened": 22}	2025-09-15 22:23:59.012821+00
454	main_trader	HEALTHY	t	t	t	\N	22	0	0	\N	{"sl_set": 22, "sl_failed": 0, "positions_failed": 4, "positions_opened": 22}	2025-09-15 22:25:00.114774+00
455	main_trader	HEALTHY	t	t	t	\N	22	0	0	\N	{"sl_set": 22, "sl_failed": 0, "positions_failed": 4, "positions_opened": 22}	2025-09-15 22:26:01.190633+00
456	main_trader	HEALTHY	t	t	t	\N	22	0	0	\N	{"sl_set": 22, "sl_failed": 0, "positions_failed": 4, "positions_opened": 22}	2025-09-15 22:27:02.712645+00
457	main_trader	HEALTHY	t	t	t	\N	22	0	0	\N	{"sl_set": 22, "sl_failed": 0, "positions_failed": 4, "positions_opened": 22}	2025-09-15 22:28:03.945056+00
458	main_trader	HEALTHY	t	t	t	\N	22	0	0	\N	{"sl_set": 22, "sl_failed": 0, "positions_failed": 4, "positions_opened": 22}	2025-09-15 22:29:05.025008+00
459	main_trader	HEALTHY	t	t	t	\N	22	0	0	\N	{"sl_set": 22, "sl_failed": 0, "positions_failed": 4, "positions_opened": 22}	2025-09-15 22:30:06.120114+00
460	main_trader	HEALTHY	t	t	t	\N	22	0	0	\N	{"sl_set": 22, "sl_failed": 0, "positions_failed": 4, "positions_opened": 22}	2025-09-15 22:31:07.319055+00
461	main_trader	HEALTHY	t	t	t	\N	22	0	0	\N	{"sl_set": 22, "sl_failed": 0, "positions_failed": 4, "positions_opened": 22}	2025-09-15 22:32:08.693693+00
462	main_trader	HEALTHY	t	t	t	\N	22	0	0	\N	{"sl_set": 22, "sl_failed": 0, "positions_failed": 4, "positions_opened": 22}	2025-09-15 22:33:09.914841+00
463	main_trader	HEALTHY	t	t	t	\N	22	0	0	\N	{"sl_set": 22, "sl_failed": 0, "positions_failed": 4, "positions_opened": 22}	2025-09-15 22:34:11.072064+00
464	main_trader	HEALTHY	t	t	t	\N	22	0	0	\N	{"sl_set": 22, "sl_failed": 0, "positions_failed": 4, "positions_opened": 22}	2025-09-15 22:35:12.267823+00
465	main_trader	HEALTHY	t	t	t	\N	24	0	0	\N	{"sl_set": 24, "sl_failed": 0, "positions_failed": 5, "positions_opened": 24}	2025-09-15 22:36:13.387233+00
466	main_trader	HEALTHY	t	t	t	\N	24	0	0	\N	{"sl_set": 24, "sl_failed": 0, "positions_failed": 5, "positions_opened": 24}	2025-09-15 22:37:14.595621+00
467	main_trader	HEALTHY	t	t	t	\N	24	0	0	\N	{"sl_set": 24, "sl_failed": 0, "positions_failed": 5, "positions_opened": 24}	2025-09-15 22:38:15.931321+00
468	main_trader	HEALTHY	t	t	t	\N	24	0	0	\N	{"sl_set": 24, "sl_failed": 0, "positions_failed": 5, "positions_opened": 24}	2025-09-15 22:39:17.069708+00
469	main_trader	HEALTHY	t	t	t	\N	24	0	0	\N	{"sl_set": 24, "sl_failed": 0, "positions_failed": 5, "positions_opened": 24}	2025-09-15 22:40:18.242431+00
470	main_trader	HEALTHY	t	t	t	\N	24	0	0	\N	{"sl_set": 24, "sl_failed": 0, "positions_failed": 5, "positions_opened": 24}	2025-09-15 22:41:19.383012+00
471	main_trader	HEALTHY	t	t	t	\N	24	0	0	\N	{"sl_set": 24, "sl_failed": 0, "positions_failed": 5, "positions_opened": 24}	2025-09-15 22:42:20.562091+00
472	main_trader	HEALTHY	t	t	t	\N	24	0	0	\N	{"sl_set": 24, "sl_failed": 0, "positions_failed": 5, "positions_opened": 24}	2025-09-15 22:43:21.928005+00
473	main_trader	HEALTHY	t	t	t	\N	24	0	0	\N	{"sl_set": 24, "sl_failed": 0, "positions_failed": 5, "positions_opened": 24}	2025-09-15 22:44:23.144987+00
474	main_trader	HEALTHY	t	t	t	\N	24	0	0	\N	{"sl_set": 24, "sl_failed": 0, "positions_failed": 5, "positions_opened": 24}	2025-09-15 22:45:24.348287+00
475	main_trader	HEALTHY	t	t	t	\N	24	0	0	\N	{"sl_set": 24, "sl_failed": 0, "positions_failed": 5, "positions_opened": 24}	2025-09-15 22:46:25.49737+00
476	main_trader	HEALTHY	t	t	t	\N	24	0	0	\N	{"sl_set": 24, "sl_failed": 0, "positions_failed": 5, "positions_opened": 24}	2025-09-15 22:47:26.686645+00
477	main_trader	HEALTHY	t	t	t	\N	24	0	0	\N	{"sl_set": 24, "sl_failed": 0, "positions_failed": 5, "positions_opened": 24}	2025-09-15 22:48:27.995698+00
478	main_trader	HEALTHY	t	t	t	\N	24	0	0	\N	{"sl_set": 24, "sl_failed": 0, "positions_failed": 5, "positions_opened": 24}	2025-09-15 22:49:29.138981+00
479	main_trader	HEALTHY	t	t	t	\N	24	0	0	\N	{"sl_set": 25, "sl_failed": 0, "positions_failed": 5, "positions_opened": 25}	2025-09-15 22:50:30.186359+00
480	main_trader	HEALTHY	t	t	t	\N	26	0	0	\N	{"sl_set": 26, "sl_failed": 0, "positions_failed": 5, "positions_opened": 26}	2025-09-15 22:51:31.353974+00
481	main_trader	HEALTHY	t	t	t	\N	26	0	0	\N	{"sl_set": 26, "sl_failed": 0, "positions_failed": 5, "positions_opened": 26}	2025-09-15 22:52:32.510685+00
482	main_trader	HEALTHY	t	t	t	\N	26	0	0	\N	{"sl_set": 26, "sl_failed": 0, "positions_failed": 5, "positions_opened": 26}	2025-09-15 22:53:33.824108+00
483	main_trader	HEALTHY	t	t	t	\N	26	0	0	\N	{"sl_set": 26, "sl_failed": 0, "positions_failed": 5, "positions_opened": 26}	2025-09-15 22:54:34.986486+00
484	main_trader	HEALTHY	t	t	t	\N	26	0	0	\N	{"sl_set": 26, "sl_failed": 0, "positions_failed": 5, "positions_opened": 26}	2025-09-15 22:55:36.032652+00
485	main_trader	HEALTHY	t	t	t	\N	26	0	0	\N	{"sl_set": 26, "sl_failed": 0, "positions_failed": 5, "positions_opened": 26}	2025-09-15 22:56:37.224055+00
486	main_trader	HEALTHY	t	t	t	\N	26	0	0	\N	{"sl_set": 26, "sl_failed": 0, "positions_failed": 5, "positions_opened": 26}	2025-09-15 22:57:38.36838+00
487	main_trader	HEALTHY	t	t	t	\N	26	0	0	\N	{"sl_set": 26, "sl_failed": 0, "positions_failed": 5, "positions_opened": 26}	2025-09-15 22:58:39.652081+00
488	main_trader	HEALTHY	t	t	t	\N	26	0	0	\N	{"sl_set": 26, "sl_failed": 0, "positions_failed": 5, "positions_opened": 26}	2025-09-15 22:59:40.783415+00
489	main_trader	HEALTHY	t	t	t	\N	26	0	0	\N	{"sl_set": 26, "sl_failed": 0, "positions_failed": 5, "positions_opened": 26}	2025-09-15 23:00:41.961826+00
490	main_trader	HEALTHY	t	t	t	\N	26	0	0	\N	{"sl_set": 26, "sl_failed": 0, "positions_failed": 5, "positions_opened": 26}	2025-09-15 23:01:43.068771+00
491	main_trader	HEALTHY	t	t	t	\N	26	0	0	\N	{"sl_set": 26, "sl_failed": 0, "positions_failed": 5, "positions_opened": 26}	2025-09-15 23:02:44.164314+00
492	main_trader	HEALTHY	t	t	t	\N	26	0	0	\N	{"sl_set": 26, "sl_failed": 0, "positions_failed": 5, "positions_opened": 26}	2025-09-15 23:03:45.778568+00
493	main_trader	HEALTHY	t	t	t	\N	26	0	0	\N	{"sl_set": 26, "sl_failed": 0, "positions_failed": 5, "positions_opened": 26}	2025-09-15 23:04:47.114565+00
494	main_trader	HEALTHY	t	t	t	\N	26	0	0	\N	{"sl_set": 26, "sl_failed": 0, "positions_failed": 5, "positions_opened": 26}	2025-09-15 23:05:48.15526+00
495	main_trader	HEALTHY	t	t	t	\N	27	0	0	\N	{"sl_set": 28, "sl_failed": 0, "positions_failed": 5, "positions_opened": 28}	2025-09-15 23:06:49.049275+00
496	main_trader	HEALTHY	t	t	t	\N	28	0	0	\N	{"sl_set": 28, "sl_failed": 0, "positions_failed": 5, "positions_opened": 28}	2025-09-15 23:07:50.114041+00
497	main_trader	HEALTHY	t	t	t	\N	28	0	0	\N	{"sl_set": 28, "sl_failed": 0, "positions_failed": 5, "positions_opened": 28}	2025-09-15 23:08:51.481391+00
498	main_trader	HEALTHY	t	t	t	\N	28	0	0	\N	{"sl_set": 28, "sl_failed": 0, "positions_failed": 5, "positions_opened": 28}	2025-09-15 23:09:52.712261+00
499	main_trader	HEALTHY	t	t	t	\N	28	0	0	\N	{"sl_set": 28, "sl_failed": 0, "positions_failed": 5, "positions_opened": 28}	2025-09-15 23:10:54.517678+00
500	main_trader	HEALTHY	t	t	t	\N	28	0	0	\N	{"sl_set": 28, "sl_failed": 0, "positions_failed": 5, "positions_opened": 28}	2025-09-15 23:11:55.726042+00
501	main_trader	HEALTHY	t	t	t	\N	28	0	0	\N	{"sl_set": 28, "sl_failed": 0, "positions_failed": 5, "positions_opened": 28}	2025-09-15 23:12:56.860733+00
502	main_trader	HEALTHY	t	t	t	\N	28	0	0	\N	{"sl_set": 28, "sl_failed": 0, "positions_failed": 5, "positions_opened": 28}	2025-09-15 23:13:57.903596+00
503	main_trader	HEALTHY	t	t	t	\N	28	0	0	\N	{"sl_set": 28, "sl_failed": 0, "positions_failed": 5, "positions_opened": 28}	2025-09-15 23:14:58.955631+00
504	main_trader	HEALTHY	t	t	t	\N	28	0	0	\N	{"sl_set": 28, "sl_failed": 0, "positions_failed": 5, "positions_opened": 28}	2025-09-15 23:16:00.234699+00
505	main_trader	HEALTHY	t	t	t	\N	28	0	0	\N	{"sl_set": 28, "sl_failed": 0, "positions_failed": 5, "positions_opened": 28}	2025-09-15 23:17:01.362559+00
506	main_trader	HEALTHY	t	t	t	\N	28	0	0	\N	{"sl_set": 28, "sl_failed": 0, "positions_failed": 5, "positions_opened": 28}	2025-09-15 23:18:02.420331+00
507	main_trader	HEALTHY	t	t	t	\N	28	0	0	\N	{"sl_set": 28, "sl_failed": 0, "positions_failed": 5, "positions_opened": 28}	2025-09-15 23:19:03.466445+00
508	main_trader	HEALTHY	t	t	t	\N	28	0	0	\N	{"sl_set": 28, "sl_failed": 0, "positions_failed": 5, "positions_opened": 28}	2025-09-15 23:20:04.608336+00
509	main_trader	HEALTHY	t	t	t	\N	30	0	0	\N	{"sl_set": 30, "sl_failed": 0, "positions_failed": 5, "positions_opened": 30}	2025-09-15 23:21:05.887239+00
510	main_trader	HEALTHY	t	t	t	\N	30	0	0	\N	{"sl_set": 30, "sl_failed": 0, "positions_failed": 5, "positions_opened": 30}	2025-09-15 23:22:07.028324+00
511	main_trader	HEALTHY	t	t	t	\N	30	0	0	\N	{"sl_set": 30, "sl_failed": 0, "positions_failed": 5, "positions_opened": 30}	2025-09-15 23:23:08.07767+00
512	main_trader	HEALTHY	t	t	t	\N	30	0	0	\N	{"sl_set": 30, "sl_failed": 0, "positions_failed": 5, "positions_opened": 30}	2025-09-15 23:24:09.211673+00
513	main_trader	HEALTHY	t	t	t	\N	30	0	0	\N	{"sl_set": 30, "sl_failed": 0, "positions_failed": 5, "positions_opened": 30}	2025-09-15 23:25:10.25522+00
514	main_trader	HEALTHY	t	t	t	\N	30	0	0	\N	{"sl_set": 30, "sl_failed": 0, "positions_failed": 5, "positions_opened": 30}	2025-09-15 23:26:11.970724+00
515	main_trader	HEALTHY	t	t	t	\N	30	0	0	\N	{"sl_set": 30, "sl_failed": 0, "positions_failed": 5, "positions_opened": 30}	2025-09-15 23:27:13.180094+00
516	main_trader	HEALTHY	t	t	t	\N	30	0	0	\N	{"sl_set": 30, "sl_failed": 0, "positions_failed": 5, "positions_opened": 30}	2025-09-15 23:28:14.320259+00
517	main_trader	HEALTHY	t	t	t	\N	30	0	0	\N	{"sl_set": 30, "sl_failed": 0, "positions_failed": 5, "positions_opened": 30}	2025-09-15 23:29:15.370988+00
518	main_trader	HEALTHY	t	t	t	\N	30	0	0	\N	{"sl_set": 30, "sl_failed": 0, "positions_failed": 5, "positions_opened": 30}	2025-09-15 23:30:16.408025+00
519	main_trader	HEALTHY	t	t	t	\N	30	0	0	\N	{"sl_set": 30, "sl_failed": 0, "positions_failed": 5, "positions_opened": 30}	2025-09-15 23:31:19.040211+00
520	main_trader	HEALTHY	t	t	t	\N	30	0	0	\N	{"sl_set": 30, "sl_failed": 0, "positions_failed": 5, "positions_opened": 30}	2025-09-15 23:32:20.156711+00
521	main_trader	HEALTHY	t	t	t	\N	30	0	0	\N	{"sl_set": 30, "sl_failed": 0, "positions_failed": 5, "positions_opened": 30}	2025-09-15 23:33:21.612867+00
522	main_trader	HEALTHY	t	t	t	\N	30	0	0	\N	{"sl_set": 30, "sl_failed": 0, "positions_failed": 5, "positions_opened": 30}	2025-09-15 23:34:22.652937+00
523	main_trader	HEALTHY	t	t	t	\N	30	0	0	\N	{"sl_set": 30, "sl_failed": 0, "positions_failed": 5, "positions_opened": 30}	2025-09-15 23:35:23.68267+00
524	main_trader	HEALTHY	t	t	t	\N	35	0	0	\N	{"sl_set": 35, "sl_failed": 0, "positions_failed": 6, "positions_opened": 35}	2025-09-15 23:36:24.876045+00
525	main_trader	HEALTHY	t	t	t	\N	35	0	0	\N	{"sl_set": 35, "sl_failed": 0, "positions_failed": 6, "positions_opened": 35}	2025-09-15 23:37:25.991138+00
526	main_trader	HEALTHY	t	t	t	\N	35	0	0	\N	{"sl_set": 35, "sl_failed": 0, "positions_failed": 6, "positions_opened": 35}	2025-09-15 23:38:27.02384+00
527	main_trader	HEALTHY	t	t	t	\N	35	0	0	\N	{"sl_set": 35, "sl_failed": 0, "positions_failed": 6, "positions_opened": 35}	2025-09-15 23:39:28.057153+00
528	main_trader	HEALTHY	t	t	t	\N	35	0	0	\N	{"sl_set": 35, "sl_failed": 0, "positions_failed": 6, "positions_opened": 35}	2025-09-15 23:40:29.102296+00
529	main_trader	HEALTHY	t	t	t	\N	35	0	0	\N	{"sl_set": 35, "sl_failed": 0, "positions_failed": 6, "positions_opened": 35}	2025-09-15 23:41:30.911908+00
530	main_trader	HEALTHY	t	t	t	\N	35	0	0	\N	{"sl_set": 35, "sl_failed": 0, "positions_failed": 6, "positions_opened": 35}	2025-09-15 23:42:32.125862+00
531	main_trader	HEALTHY	t	t	t	\N	35	0	0	\N	{"sl_set": 35, "sl_failed": 0, "positions_failed": 6, "positions_opened": 35}	2025-09-15 23:43:33.17994+00
532	main_trader	HEALTHY	t	t	t	\N	35	0	0	\N	{"sl_set": 35, "sl_failed": 0, "positions_failed": 6, "positions_opened": 35}	2025-09-15 23:44:34.218026+00
533	main_trader	HEALTHY	t	t	t	\N	35	0	0	\N	{"sl_set": 35, "sl_failed": 0, "positions_failed": 6, "positions_opened": 35}	2025-09-15 23:45:35.262632+00
534	main_trader	HEALTHY	t	t	t	\N	35	0	0	\N	{"sl_set": 35, "sl_failed": 0, "positions_failed": 6, "positions_opened": 35}	2025-09-15 23:46:36.525861+00
535	main_trader	HEALTHY	t	t	t	\N	35	0	0	\N	{"sl_set": 35, "sl_failed": 0, "positions_failed": 6, "positions_opened": 35}	2025-09-15 23:47:37.635762+00
536	main_trader	HEALTHY	t	t	t	\N	35	0	0	\N	{"sl_set": 35, "sl_failed": 0, "positions_failed": 6, "positions_opened": 35}	2025-09-15 23:48:38.676623+00
537	main_trader	HEALTHY	t	t	t	\N	35	0	0	\N	{"sl_set": 35, "sl_failed": 0, "positions_failed": 6, "positions_opened": 35}	2025-09-15 23:49:39.807825+00
538	main_trader	HEALTHY	t	t	t	\N	35	0	0	\N	{"sl_set": 35, "sl_failed": 0, "positions_failed": 7, "positions_opened": 35}	2025-09-15 23:50:40.686995+00
539	main_trader	HEALTHY	t	t	t	\N	39	0	0	\N	{"sl_set": 39, "sl_failed": 0, "positions_failed": 7, "positions_opened": 39}	2025-09-15 23:51:42.067979+00
540	main_trader	HEALTHY	t	t	t	\N	39	0	0	\N	{"sl_set": 39, "sl_failed": 0, "positions_failed": 7, "positions_opened": 39}	2025-09-15 23:52:43.297195+00
541	main_trader	HEALTHY	t	t	t	\N	39	0	0	\N	{"sl_set": 39, "sl_failed": 0, "positions_failed": 7, "positions_opened": 39}	2025-09-15 23:53:44.449193+00
542	main_trader	HEALTHY	t	t	t	\N	39	0	0	\N	{"sl_set": 39, "sl_failed": 0, "positions_failed": 7, "positions_opened": 39}	2025-09-15 23:54:45.499164+00
543	main_trader	HEALTHY	t	t	t	\N	39	0	0	\N	{"sl_set": 39, "sl_failed": 0, "positions_failed": 7, "positions_opened": 39}	2025-09-15 23:55:46.681538+00
544	main_trader	HEALTHY	t	t	t	\N	39	0	0	\N	{"sl_set": 39, "sl_failed": 0, "positions_failed": 7, "positions_opened": 39}	2025-09-15 23:56:48.411492+00
545	main_trader	HEALTHY	t	t	t	\N	39	0	0	\N	{"sl_set": 39, "sl_failed": 0, "positions_failed": 7, "positions_opened": 39}	2025-09-15 23:57:49.525644+00
546	main_trader	HEALTHY	t	t	t	\N	39	0	0	\N	{"sl_set": 39, "sl_failed": 0, "positions_failed": 7, "positions_opened": 39}	2025-09-15 23:58:50.680755+00
547	main_trader	HEALTHY	t	t	t	\N	39	0	0	\N	{"sl_set": 39, "sl_failed": 0, "positions_failed": 7, "positions_opened": 39}	2025-09-15 23:59:51.723883+00
548	main_trader	HEALTHY	t	t	t	\N	39	0	0	\N	{"sl_set": 39, "sl_failed": 0, "positions_failed": 7, "positions_opened": 39}	2025-09-16 00:00:52.768693+00
549	main_trader	HEALTHY	t	t	t	\N	39	0	0	\N	{"sl_set": 39, "sl_failed": 0, "positions_failed": 7, "positions_opened": 39}	2025-09-16 00:01:54.549127+00
550	main_trader	HEALTHY	t	t	t	\N	39	0	0	\N	{"sl_set": 39, "sl_failed": 0, "positions_failed": 7, "positions_opened": 39}	2025-09-16 00:02:55.768661+00
551	main_trader	HEALTHY	t	t	t	\N	39	0	0	\N	{"sl_set": 39, "sl_failed": 0, "positions_failed": 7, "positions_opened": 39}	2025-09-16 00:03:56.828477+00
552	main_trader	HEALTHY	t	t	t	\N	39	0	0	\N	{"sl_set": 39, "sl_failed": 0, "positions_failed": 7, "positions_opened": 39}	2025-09-16 00:04:57.95613+00
553	main_trader	HEALTHY	t	t	t	\N	39	0	0	\N	{"sl_set": 39, "sl_failed": 0, "positions_failed": 7, "positions_opened": 39}	2025-09-16 00:05:59.097596+00
554	main_trader	HEALTHY	t	t	t	\N	42	0	0	\N	{"sl_set": 42, "sl_failed": 0, "positions_failed": 7, "positions_opened": 42}	2025-09-16 00:07:00.208891+00
555	main_trader	HEALTHY	t	t	t	\N	48	0	0	\N	{"sl_set": 48, "sl_failed": 0, "positions_failed": 8, "positions_opened": 48}	2025-09-16 00:08:01.331719+00
556	main_trader	HEALTHY	t	t	t	\N	50	0	0	\N	{"sl_set": 50, "sl_failed": 0, "positions_failed": 8, "positions_opened": 50}	2025-09-16 00:09:02.488926+00
557	main_trader	HEALTHY	t	t	t	\N	50	0	0	\N	{"sl_set": 50, "sl_failed": 0, "positions_failed": 8, "positions_opened": 50}	2025-09-16 00:10:03.540824+00
558	main_trader	HEALTHY	t	t	t	\N	50	0	0	\N	{"sl_set": 50, "sl_failed": 0, "positions_failed": 8, "positions_opened": 50}	2025-09-16 00:11:04.59788+00
559	main_trader	HEALTHY	t	t	t	\N	50	0	0	\N	{"sl_set": 50, "sl_failed": 0, "positions_failed": 8, "positions_opened": 50}	2025-09-16 00:12:06.336905+00
560	main_trader	HEALTHY	t	t	t	\N	50	0	0	\N	{"sl_set": 50, "sl_failed": 0, "positions_failed": 8, "positions_opened": 50}	2025-09-16 00:13:07.479322+00
561	main_trader	HEALTHY	t	t	t	\N	50	0	0	\N	{"sl_set": 50, "sl_failed": 0, "positions_failed": 8, "positions_opened": 50}	2025-09-16 00:14:08.612046+00
562	main_trader	HEALTHY	t	t	t	\N	50	0	0	\N	{"sl_set": 50, "sl_failed": 0, "positions_failed": 8, "positions_opened": 50}	2025-09-16 00:15:09.659929+00
563	main_trader	HEALTHY	t	t	t	\N	50	0	0	\N	{"sl_set": 50, "sl_failed": 0, "positions_failed": 8, "positions_opened": 50}	2025-09-16 00:16:10.72595+00
564	main_trader	HEALTHY	t	t	t	\N	50	0	0	\N	{"sl_set": 50, "sl_failed": 0, "positions_failed": 8, "positions_opened": 50}	2025-09-16 00:17:12.107092+00
565	main_trader	HEALTHY	t	t	t	\N	50	0	0	\N	{"sl_set": 50, "sl_failed": 0, "positions_failed": 8, "positions_opened": 50}	2025-09-16 00:18:13.228721+00
566	main_trader	HEALTHY	t	t	t	\N	50	0	0	\N	{"sl_set": 50, "sl_failed": 0, "positions_failed": 8, "positions_opened": 50}	2025-09-16 00:19:14.363794+00
567	main_trader	HEALTHY	t	t	t	\N	51	0	0	\N	{"sl_set": 51, "sl_failed": 0, "positions_failed": 8, "positions_opened": 51}	2025-09-16 00:20:15.886353+00
568	main_trader	HEALTHY	t	t	t	\N	57	0	0	\N	{"sl_set": 57, "sl_failed": 0, "positions_failed": 8, "positions_opened": 57}	2025-09-16 00:21:16.854473+00
569	main_trader	HEALTHY	t	t	t	\N	63	0	0	\N	{"sl_set": 63, "sl_failed": 0, "positions_failed": 8, "positions_opened": 64}	2025-09-16 00:22:17.957143+00
570	main_trader	HEALTHY	t	t	t	\N	69	0	0	\N	{"sl_set": 69, "sl_failed": 0, "positions_failed": 8, "positions_opened": 70}	2025-09-16 00:23:18.912103+00
571	main_trader	HEALTHY	t	t	t	\N	75	0	0	\N	{"sl_set": 76, "sl_failed": 0, "positions_failed": 8, "positions_opened": 76}	2025-09-16 00:24:19.790136+00
572	main_trader	HEALTHY	t	t	t	\N	81	0	0	\N	{"sl_set": 82, "sl_failed": 0, "positions_failed": 8, "positions_opened": 82}	2025-09-16 00:25:20.945421+00
573	main_trader	HEALTHY	t	t	t	\N	87	0	0	\N	{"sl_set": 88, "sl_failed": 0, "positions_failed": 8, "positions_opened": 88}	2025-09-16 00:26:21.841316+00
574	main_trader	HEALTHY	t	t	t	\N	93	0	0	\N	{"sl_set": 93, "sl_failed": 0, "positions_failed": 8, "positions_opened": 93}	2025-09-16 00:27:23.393645+00
575	main_trader	HEALTHY	t	t	t	\N	98	0	0	\N	{"sl_set": 98, "sl_failed": 0, "positions_failed": 8, "positions_opened": 98}	2025-09-16 00:28:24.3525+00
576	main_trader	HEALTHY	t	t	t	\N	98	0	0	\N	{"sl_set": 98, "sl_failed": 0, "positions_failed": 8, "positions_opened": 98}	2025-09-16 00:29:25.501999+00
577	main_trader	HEALTHY	t	t	t	\N	98	0	0	\N	{"sl_set": 98, "sl_failed": 0, "positions_failed": 8, "positions_opened": 98}	2025-09-16 00:30:26.643123+00
578	main_trader	HEALTHY	t	t	t	\N	98	0	0	\N	{"sl_set": 98, "sl_failed": 0, "positions_failed": 8, "positions_opened": 98}	2025-09-16 00:31:27.790032+00
579	main_trader	HEALTHY	t	t	t	\N	98	0	0	\N	{"sl_set": 98, "sl_failed": 0, "positions_failed": 8, "positions_opened": 98}	2025-09-16 00:32:29.534017+00
580	main_trader	HEALTHY	t	t	t	\N	98	0	0	\N	{"sl_set": 98, "sl_failed": 0, "positions_failed": 8, "positions_opened": 98}	2025-09-16 00:33:30.666896+00
581	main_trader	HEALTHY	t	t	t	\N	98	0	0	\N	{"sl_set": 98, "sl_failed": 0, "positions_failed": 8, "positions_opened": 98}	2025-09-16 00:34:31.842288+00
582	main_trader	HEALTHY	t	t	t	\N	99	0	0	\N	{"sl_set": 100, "sl_failed": 0, "positions_failed": 8, "positions_opened": 100}	2025-09-16 00:35:32.721463+00
583	main_trader	HEALTHY	t	t	t	\N	105	0	0	\N	{"sl_set": 106, "sl_failed": 0, "positions_failed": 8, "positions_opened": 106}	2025-09-16 00:36:33.612028+00
584	main_trader	HEALTHY	t	t	t	\N	111	0	0	\N	{"sl_set": 112, "sl_failed": 0, "positions_failed": 8, "positions_opened": 112}	2025-09-16 00:37:34.582357+00
585	main_trader	HEALTHY	t	t	t	\N	117	0	0	\N	{"sl_set": 118, "sl_failed": 0, "positions_failed": 8, "positions_opened": 118}	2025-09-16 00:38:35.545019+00
586	main_trader	HEALTHY	t	t	t	\N	122	0	0	\N	{"sl_set": 123, "sl_failed": 0, "positions_failed": 9, "positions_opened": 123}	2025-09-16 00:39:36.424376+00
587	main_trader	HEALTHY	t	t	t	\N	129	0	0	\N	{"sl_set": 129, "sl_failed": 0, "positions_failed": 9, "positions_opened": 129}	2025-09-16 00:40:37.466338+00
588	main_trader	HEALTHY	t	t	t	\N	135	0	0	\N	{"sl_set": 135, "sl_failed": 0, "positions_failed": 9, "positions_opened": 135}	2025-09-16 00:41:38.352428+00
589	main_trader	HEALTHY	t	t	t	\N	138	0	0	\N	{"sl_set": 138, "sl_failed": 0, "positions_failed": 12, "positions_opened": 138}	2025-09-16 00:42:40.623843+00
590	main_trader	HEALTHY	t	t	t	\N	141	0	0	\N	{"sl_set": 141, "sl_failed": 0, "positions_failed": 13, "positions_opened": 141}	2025-09-16 00:43:41.859721+00
591	main_trader	HEALTHY	t	t	t	\N	144	0	0	\N	{"sl_set": 144, "sl_failed": 0, "positions_failed": 13, "positions_opened": 144}	2025-09-16 00:44:43.013617+00
592	main_trader	HEALTHY	t	t	t	\N	144	0	0	\N	{"sl_set": 144, "sl_failed": 0, "positions_failed": 13, "positions_opened": 144}	2025-09-16 00:45:44.168008+00
593	main_trader	HEALTHY	t	t	t	\N	144	0	0	\N	{"sl_set": 144, "sl_failed": 0, "positions_failed": 13, "positions_opened": 144}	2025-09-16 00:46:45.239795+00
594	main_trader	HEALTHY	t	t	t	\N	144	0	0	\N	{"sl_set": 144, "sl_failed": 0, "positions_failed": 13, "positions_opened": 144}	2025-09-16 00:47:46.700751+00
595	main_trader	HEALTHY	t	t	t	\N	144	0	0	\N	{"sl_set": 144, "sl_failed": 0, "positions_failed": 13, "positions_opened": 144}	2025-09-16 00:48:47.942367+00
596	main_trader	HEALTHY	t	t	t	\N	144	0	0	\N	{"sl_set": 144, "sl_failed": 0, "positions_failed": 13, "positions_opened": 144}	2025-09-16 00:49:49.73303+00
597	main_trader	HEALTHY	t	t	t	\N	146	0	0	\N	{"sl_set": 147, "sl_failed": 0, "positions_failed": 13, "positions_opened": 147}	2025-09-16 00:50:50.632767+00
598	main_trader	HEALTHY	t	t	t	\N	151	0	0	\N	{"sl_set": 152, "sl_failed": 0, "positions_failed": 14, "positions_opened": 152}	2025-09-16 00:51:51.517908+00
599	main_trader	HEALTHY	t	t	t	\N	156	0	0	\N	{"sl_set": 156, "sl_failed": 0, "positions_failed": 15, "positions_opened": 156}	2025-09-16 00:52:53.333105+00
600	main_trader	HEALTHY	t	t	t	\N	158	0	0	\N	{"sl_set": 158, "sl_failed": 0, "positions_failed": 16, "positions_opened": 158}	2025-09-16 00:53:55.07883+00
601	main_trader	HEALTHY	t	t	t	\N	158	0	0	\N	{"sl_set": 158, "sl_failed": 0, "positions_failed": 16, "positions_opened": 158}	2025-09-16 00:54:57.038429+00
602	main_trader	HEALTHY	t	t	t	\N	158	0	0	\N	{"sl_set": 158, "sl_failed": 0, "positions_failed": 16, "positions_opened": 158}	2025-09-16 00:55:58.097567+00
603	main_trader	HEALTHY	t	t	t	\N	158	0	0	\N	{"sl_set": 158, "sl_failed": 0, "positions_failed": 16, "positions_opened": 158}	2025-09-16 00:56:59.965865+00
604	main_trader	HEALTHY	t	t	t	\N	158	0	0	\N	{"sl_set": 158, "sl_failed": 0, "positions_failed": 16, "positions_opened": 158}	2025-09-16 00:58:02.115695+00
605	main_trader	HEALTHY	t	t	t	\N	158	0	0	\N	{"sl_set": 158, "sl_failed": 0, "positions_failed": 16, "positions_opened": 158}	2025-09-16 00:59:04.018584+00
606	main_trader	HEALTHY	t	t	t	\N	158	0	0	\N	{"sl_set": 158, "sl_failed": 0, "positions_failed": 16, "positions_opened": 158}	2025-09-16 01:00:05.772814+00
607	main_trader	HEALTHY	t	t	t	\N	158	0	0	\N	{"sl_set": 158, "sl_failed": 0, "positions_failed": 16, "positions_opened": 158}	2025-09-16 01:01:08.895226+00
608	main_trader	HEALTHY	t	t	t	\N	158	0	0	\N	{"sl_set": 158, "sl_failed": 0, "positions_failed": 16, "positions_opened": 158}	2025-09-16 01:02:10.6647+00
609	main_trader	HEALTHY	t	t	t	\N	158	0	0	\N	{"sl_set": 158, "sl_failed": 0, "positions_failed": 16, "positions_opened": 158}	2025-09-16 01:03:12.0108+00
610	main_trader	HEALTHY	t	t	t	\N	158	0	0	\N	{"sl_set": 158, "sl_failed": 0, "positions_failed": 16, "positions_opened": 158}	2025-09-16 01:04:14.742215+00
611	main_trader	HEALTHY	t	t	t	\N	158	0	0	\N	{"sl_set": 158, "sl_failed": 0, "positions_failed": 16, "positions_opened": 158}	2025-09-16 01:05:16.525427+00
612	main_trader	HEALTHY	t	t	t	\N	159	0	0	\N	{"sl_set": 159, "sl_failed": 0, "positions_failed": 16, "positions_opened": 159}	2025-09-16 01:06:19.276596+00
613	main_trader	HEALTHY	t	t	t	\N	162	0	0	\N	{"sl_set": 162, "sl_failed": 0, "positions_failed": 18, "positions_opened": 162}	2025-09-16 01:07:20.906761+00
614	main_trader	HEALTHY	t	t	t	\N	166	0	0	\N	{"sl_set": 167, "sl_failed": 0, "positions_failed": 18, "positions_opened": 167}	2025-09-16 01:08:22.211755+00
615	main_trader	HEALTHY	t	t	t	\N	170	0	0	\N	{"sl_set": 171, "sl_failed": 0, "positions_failed": 19, "positions_opened": 171}	2025-09-16 01:09:24.395106+00
616	main_trader	HEALTHY	t	t	t	\N	172	0	0	\N	{"sl_set": 172, "sl_failed": 0, "positions_failed": 19, "positions_opened": 172}	2025-09-16 01:10:26.258675+00
617	main_trader	HEALTHY	t	t	t	\N	172	0	0	\N	{"sl_set": 172, "sl_failed": 0, "positions_failed": 19, "positions_opened": 172}	2025-09-16 01:11:28.054203+00
618	main_trader	HEALTHY	t	t	t	\N	172	0	0	\N	{"sl_set": 172, "sl_failed": 0, "positions_failed": 19, "positions_opened": 172}	2025-09-16 01:12:30.009669+00
619	main_trader	HEALTHY	t	t	t	\N	172	0	0	\N	{"sl_set": 172, "sl_failed": 0, "positions_failed": 19, "positions_opened": 172}	2025-09-16 01:13:32.637434+00
620	main_trader	HEALTHY	t	t	t	\N	172	0	0	\N	{"sl_set": 172, "sl_failed": 0, "positions_failed": 19, "positions_opened": 172}	2025-09-16 01:14:33.838191+00
621	main_trader	HEALTHY	t	t	t	\N	172	0	0	\N	{"sl_set": 172, "sl_failed": 0, "positions_failed": 19, "positions_opened": 172}	2025-09-16 01:15:35.696045+00
622	main_trader	HEALTHY	t	t	t	\N	172	0	0	\N	{"sl_set": 172, "sl_failed": 0, "positions_failed": 19, "positions_opened": 172}	2025-09-16 01:16:37.452807+00
623	main_trader	HEALTHY	t	t	t	\N	172	0	0	\N	{"sl_set": 172, "sl_failed": 0, "positions_failed": 19, "positions_opened": 172}	2025-09-16 01:17:38.540488+00
624	main_trader	HEALTHY	t	t	t	\N	172	0	0	\N	{"sl_set": 172, "sl_failed": 0, "positions_failed": 19, "positions_opened": 172}	2025-09-16 01:18:39.841669+00
625	main_trader	HEALTHY	t	t	t	\N	172	0	0	\N	{"sl_set": 172, "sl_failed": 0, "positions_failed": 19, "positions_opened": 172}	2025-09-16 01:19:41.01102+00
626	main_trader	HEALTHY	t	t	t	\N	174	0	0	\N	{"sl_set": 174, "sl_failed": 0, "positions_failed": 19, "positions_opened": 174}	2025-09-16 01:20:41.876379+00
627	main_trader	HEALTHY	t	t	t	\N	180	0	0	\N	{"sl_set": 180, "sl_failed": 0, "positions_failed": 19, "positions_opened": 180}	2025-09-16 01:21:42.989588+00
628	main_trader	HEALTHY	t	t	t	\N	186	0	0	\N	{"sl_set": 186, "sl_failed": 0, "positions_failed": 19, "positions_opened": 186}	2025-09-16 01:22:44.52569+00
629	main_trader	HEALTHY	t	t	t	\N	191	0	0	\N	{"sl_set": 191, "sl_failed": 0, "positions_failed": 21, "positions_opened": 191}	2025-09-16 01:23:46.404254+00
630	main_trader	HEALTHY	t	t	t	\N	193	0	0	\N	{"sl_set": 193, "sl_failed": 0, "positions_failed": 21, "positions_opened": 193}	2025-09-16 01:24:47.593139+00
631	main_trader	HEALTHY	t	t	t	\N	193	0	0	\N	{"sl_set": 193, "sl_failed": 0, "positions_failed": 21, "positions_opened": 193}	2025-09-16 01:25:48.612109+00
632	main_trader	HEALTHY	t	t	t	\N	193	0	0	\N	{"sl_set": 193, "sl_failed": 0, "positions_failed": 21, "positions_opened": 193}	2025-09-16 01:26:49.654353+00
633	main_trader	HEALTHY	t	t	t	\N	193	0	0	\N	{"sl_set": 193, "sl_failed": 0, "positions_failed": 21, "positions_opened": 193}	2025-09-16 01:27:50.757787+00
634	main_trader	HEALTHY	t	t	t	\N	193	0	0	\N	{"sl_set": 193, "sl_failed": 0, "positions_failed": 21, "positions_opened": 193}	2025-09-16 01:28:51.999801+00
635	main_trader	HEALTHY	t	t	t	\N	193	0	0	\N	{"sl_set": 193, "sl_failed": 0, "positions_failed": 21, "positions_opened": 193}	2025-09-16 01:29:53.084739+00
636	main_trader	HEALTHY	t	t	t	\N	193	0	0	\N	{"sl_set": 193, "sl_failed": 0, "positions_failed": 21, "positions_opened": 193}	2025-09-16 01:30:54.229998+00
637	main_trader	HEALTHY	t	t	t	\N	193	0	0	\N	{"sl_set": 193, "sl_failed": 0, "positions_failed": 21, "positions_opened": 193}	2025-09-16 01:31:55.252039+00
638	main_trader	HEALTHY	t	t	t	\N	193	0	0	\N	{"sl_set": 193, "sl_failed": 0, "positions_failed": 21, "positions_opened": 193}	2025-09-16 01:32:56.380256+00
639	main_trader	HEALTHY	t	t	t	\N	193	0	0	\N	{"sl_set": 193, "sl_failed": 0, "positions_failed": 21, "positions_opened": 193}	2025-09-16 01:33:57.619214+00
640	main_trader	HEALTHY	t	t	t	\N	193	0	0	\N	{"sl_set": 193, "sl_failed": 0, "positions_failed": 21, "positions_opened": 193}	2025-09-16 01:34:58.814609+00
641	main_trader	HEALTHY	t	t	t	\N	196	0	0	\N	{"sl_set": 197, "sl_failed": 0, "positions_failed": 22, "positions_opened": 197}	2025-09-16 01:36:00.691436+00
642	main_trader	HEALTHY	t	t	t	\N	201	0	0	\N	{"sl_set": 201, "sl_failed": 0, "positions_failed": 24, "positions_opened": 201}	2025-09-16 01:37:02.206348+00
643	main_trader	HEALTHY	t	t	t	\N	204	0	0	\N	{"sl_set": 204, "sl_failed": 0, "positions_failed": 25, "positions_opened": 204}	2025-09-16 01:38:03.395138+00
644	main_trader	HEALTHY	t	t	t	\N	204	0	0	\N	{"sl_set": 204, "sl_failed": 0, "positions_failed": 25, "positions_opened": 204}	2025-09-16 01:39:04.507385+00
645	main_trader	HEALTHY	t	t	t	\N	204	0	0	\N	{"sl_set": 204, "sl_failed": 0, "positions_failed": 25, "positions_opened": 204}	2025-09-16 01:40:05.61978+00
646	main_trader	HEALTHY	t	t	t	\N	204	0	0	\N	{"sl_set": 204, "sl_failed": 0, "positions_failed": 25, "positions_opened": 204}	2025-09-16 01:41:06.664742+00
647	main_trader	HEALTHY	t	t	t	\N	204	0	0	\N	{"sl_set": 204, "sl_failed": 0, "positions_failed": 25, "positions_opened": 204}	2025-09-16 01:42:08.331274+00
648	main_trader	HEALTHY	t	t	t	\N	204	0	0	\N	{"sl_set": 204, "sl_failed": 0, "positions_failed": 25, "positions_opened": 204}	2025-09-16 01:43:09.564477+00
649	main_trader	HEALTHY	t	t	t	\N	204	0	0	\N	{"sl_set": 204, "sl_failed": 0, "positions_failed": 25, "positions_opened": 204}	2025-09-16 01:44:10.696749+00
650	main_trader	HEALTHY	t	t	t	\N	204	0	0	\N	{"sl_set": 204, "sl_failed": 0, "positions_failed": 25, "positions_opened": 204}	2025-09-16 01:45:11.728129+00
651	main_trader	HEALTHY	t	t	t	\N	204	0	0	\N	{"sl_set": 204, "sl_failed": 0, "positions_failed": 25, "positions_opened": 204}	2025-09-16 01:46:12.842425+00
652	main_trader	HEALTHY	t	t	t	\N	204	0	0	\N	{"sl_set": 204, "sl_failed": 0, "positions_failed": 25, "positions_opened": 204}	2025-09-16 01:47:14.189159+00
653	main_trader	HEALTHY	t	t	t	\N	204	0	0	\N	{"sl_set": 204, "sl_failed": 0, "positions_failed": 25, "positions_opened": 204}	2025-09-16 01:48:15.292849+00
654	main_trader	HEALTHY	t	t	t	\N	204	0	0	\N	{"sl_set": 204, "sl_failed": 0, "positions_failed": 25, "positions_opened": 204}	2025-09-16 01:49:16.444818+00
655	main_trader	HEALTHY	t	t	t	\N	204	0	0	\N	{"sl_set": 204, "sl_failed": 0, "positions_failed": 25, "positions_opened": 204}	2025-09-16 01:50:17.568887+00
656	main_trader	HEALTHY	t	t	t	\N	209	0	0	\N	{"sl_set": 209, "sl_failed": 0, "positions_failed": 25, "positions_opened": 209}	2025-09-16 01:51:18.609164+00
657	main_trader	HEALTHY	t	t	t	\N	215	0	0	\N	{"sl_set": 215, "sl_failed": 0, "positions_failed": 25, "positions_opened": 215}	2025-09-16 01:52:19.720945+00
658	main_trader	HEALTHY	t	t	t	\N	219	0	0	\N	{"sl_set": 220, "sl_failed": 0, "positions_failed": 26, "positions_opened": 220}	2025-09-16 01:53:20.678122+00
659	main_trader	HEALTHY	t	t	t	\N	225	0	0	\N	{"sl_set": 226, "sl_failed": 0, "positions_failed": 26, "positions_opened": 226}	2025-09-16 01:54:21.557668+00
660	main_trader	HEALTHY	t	t	t	\N	226	0	0	\N	{"sl_set": 226, "sl_failed": 0, "positions_failed": 26, "positions_opened": 226}	2025-09-16 01:55:22.744605+00
661	main_trader	HEALTHY	t	t	t	\N	226	0	0	\N	{"sl_set": 226, "sl_failed": 0, "positions_failed": 26, "positions_opened": 226}	2025-09-16 01:56:23.864569+00
662	main_trader	HEALTHY	t	t	t	\N	226	0	0	\N	{"sl_set": 226, "sl_failed": 0, "positions_failed": 26, "positions_opened": 226}	2025-09-16 01:57:24.990632+00
663	main_trader	HEALTHY	t	t	t	\N	226	0	0	\N	{"sl_set": 226, "sl_failed": 0, "positions_failed": 26, "positions_opened": 226}	2025-09-16 01:58:26.060086+00
664	main_trader	HEALTHY	t	t	t	\N	226	0	0	\N	{"sl_set": 226, "sl_failed": 0, "positions_failed": 26, "positions_opened": 226}	2025-09-16 01:59:28.07547+00
665	main_trader	HEALTHY	t	t	t	\N	226	0	0	\N	{"sl_set": 226, "sl_failed": 0, "positions_failed": 26, "positions_opened": 226}	2025-09-16 02:00:29.276656+00
666	main_trader	HEALTHY	t	t	t	\N	226	0	0	\N	{"sl_set": 226, "sl_failed": 0, "positions_failed": 26, "positions_opened": 226}	2025-09-16 02:01:30.392852+00
667	main_trader	HEALTHY	t	t	t	\N	226	0	0	\N	{"sl_set": 226, "sl_failed": 0, "positions_failed": 26, "positions_opened": 226}	2025-09-16 02:02:31.43459+00
668	main_trader	HEALTHY	t	t	t	\N	226	0	0	\N	{"sl_set": 226, "sl_failed": 0, "positions_failed": 26, "positions_opened": 226}	2025-09-16 02:03:32.57216+00
669	main_trader	HEALTHY	t	t	t	\N	226	0	0	\N	{"sl_set": 226, "sl_failed": 0, "positions_failed": 26, "positions_opened": 226}	2025-09-16 02:04:33.834374+00
670	main_trader	HEALTHY	t	t	t	\N	226	0	0	\N	{"sl_set": 226, "sl_failed": 0, "positions_failed": 26, "positions_opened": 226}	2025-09-16 02:05:35.034621+00
671	main_trader	HEALTHY	t	t	t	\N	226	0	0	\N	{"sl_set": 226, "sl_failed": 0, "positions_failed": 26, "positions_opened": 226}	2025-09-16 02:06:35.911949+00
672	main_trader	HEALTHY	t	t	t	\N	232	0	0	\N	{"sl_set": 232, "sl_failed": 0, "positions_failed": 26, "positions_opened": 233}	2025-09-16 02:07:37.031073+00
673	main_trader	HEALTHY	t	t	t	\N	236	0	0	\N	{"sl_set": 236, "sl_failed": 0, "positions_failed": 29, "positions_opened": 237}	2025-09-16 02:08:37.90265+00
674	main_trader	HEALTHY	t	t	t	\N	241	0	0	\N	{"sl_set": 241, "sl_failed": 0, "positions_failed": 30, "positions_opened": 241}	2025-09-16 02:09:39.088264+00
675	main_trader	HEALTHY	t	t	t	\N	245	0	0	\N	{"sl_set": 245, "sl_failed": 0, "positions_failed": 31, "positions_opened": 245}	2025-09-16 02:10:40.306363+00
676	main_trader	HEALTHY	t	t	t	\N	245	0	0	\N	{"sl_set": 245, "sl_failed": 0, "positions_failed": 31, "positions_opened": 245}	2025-09-16 02:11:41.667215+00
677	main_trader	HEALTHY	t	t	t	\N	245	0	0	\N	{"sl_set": 245, "sl_failed": 0, "positions_failed": 31, "positions_opened": 245}	2025-09-16 02:12:42.705698+00
678	main_trader	HEALTHY	t	t	t	\N	245	0	0	\N	{"sl_set": 245, "sl_failed": 0, "positions_failed": 31, "positions_opened": 245}	2025-09-16 02:13:43.80456+00
679	main_trader	HEALTHY	t	t	t	\N	245	0	0	\N	{"sl_set": 245, "sl_failed": 0, "positions_failed": 31, "positions_opened": 245}	2025-09-16 02:14:45.572489+00
680	main_trader	HEALTHY	t	t	t	\N	245	0	0	\N	{"sl_set": 245, "sl_failed": 0, "positions_failed": 31, "positions_opened": 245}	2025-09-16 02:15:46.755029+00
681	main_trader	HEALTHY	t	t	t	\N	245	0	0	\N	{"sl_set": 245, "sl_failed": 0, "positions_failed": 31, "positions_opened": 245}	2025-09-16 02:16:47.802485+00
682	main_trader	HEALTHY	t	t	t	\N	245	0	0	\N	{"sl_set": 245, "sl_failed": 0, "positions_failed": 31, "positions_opened": 245}	2025-09-16 02:17:48.946825+00
683	main_trader	HEALTHY	t	t	t	\N	245	0	0	\N	{"sl_set": 245, "sl_failed": 0, "positions_failed": 31, "positions_opened": 245}	2025-09-16 02:18:50.073169+00
684	main_trader	HEALTHY	t	t	t	\N	245	0	0	\N	{"sl_set": 245, "sl_failed": 0, "positions_failed": 31, "positions_opened": 245}	2025-09-16 02:19:51.446747+00
685	main_trader	HEALTHY	t	t	t	\N	247	0	0	\N	{"sl_set": 247, "sl_failed": 0, "positions_failed": 31, "positions_opened": 248}	2025-09-16 02:20:52.400631+00
686	main_trader	HEALTHY	t	t	t	\N	253	0	0	\N	{"sl_set": 253, "sl_failed": 0, "positions_failed": 31, "positions_opened": 254}	2025-09-16 02:21:53.539193+00
687	main_trader	HEALTHY	t	t	t	\N	259	0	0	\N	{"sl_set": 260, "sl_failed": 0, "positions_failed": 31, "positions_opened": 260}	2025-09-16 02:22:54.641445+00
688	main_trader	HEALTHY	t	t	t	\N	265	0	0	\N	{"sl_set": 265, "sl_failed": 0, "positions_failed": 31, "positions_opened": 265}	2025-09-16 02:23:55.527253+00
689	main_trader	HEALTHY	t	t	t	\N	267	0	0	\N	{"sl_set": 267, "sl_failed": 0, "positions_failed": 32, "positions_opened": 267}	2025-09-16 02:24:56.871204+00
690	main_trader	HEALTHY	t	t	t	\N	267	0	0	\N	{"sl_set": 267, "sl_failed": 0, "positions_failed": 32, "positions_opened": 267}	2025-09-16 02:25:58.087278+00
691	main_trader	HEALTHY	t	t	t	\N	267	0	0	\N	{"sl_set": 267, "sl_failed": 0, "positions_failed": 32, "positions_opened": 267}	2025-09-16 02:26:59.215701+00
692	main_trader	HEALTHY	t	t	t	\N	267	0	0	\N	{"sl_set": 267, "sl_failed": 0, "positions_failed": 32, "positions_opened": 267}	2025-09-16 02:28:00.485232+00
693	main_trader	HEALTHY	t	t	t	\N	267	0	0	\N	{"sl_set": 267, "sl_failed": 0, "positions_failed": 32, "positions_opened": 267}	2025-09-16 02:29:01.686183+00
694	main_trader	HEALTHY	t	t	t	\N	267	0	0	\N	{"sl_set": 267, "sl_failed": 0, "positions_failed": 32, "positions_opened": 267}	2025-09-16 02:30:02.953802+00
695	main_trader	HEALTHY	t	t	t	\N	267	0	0	\N	{"sl_set": 267, "sl_failed": 0, "positions_failed": 32, "positions_opened": 267}	2025-09-16 02:31:04.180323+00
696	main_trader	HEALTHY	t	t	t	\N	267	0	0	\N	{"sl_set": 267, "sl_failed": 0, "positions_failed": 32, "positions_opened": 267}	2025-09-16 02:32:05.322545+00
697	main_trader	HEALTHY	t	t	t	\N	267	0	0	\N	{"sl_set": 267, "sl_failed": 0, "positions_failed": 32, "positions_opened": 267}	2025-09-16 02:33:06.44615+00
698	main_trader	HEALTHY	t	t	t	\N	267	0	0	\N	{"sl_set": 267, "sl_failed": 0, "positions_failed": 32, "positions_opened": 267}	2025-09-16 02:34:07.724915+00
699	main_trader	HEALTHY	t	t	t	\N	267	0	0	\N	{"sl_set": 267, "sl_failed": 0, "positions_failed": 32, "positions_opened": 267}	2025-09-16 02:35:09.065762+00
700	main_trader	HEALTHY	t	t	t	\N	271	0	0	\N	{"sl_set": 272, "sl_failed": 0, "positions_failed": 32, "positions_opened": 272}	2025-09-16 02:36:10.238032+00
701	main_trader	HEALTHY	t	t	t	\N	277	0	0	\N	{"sl_set": 278, "sl_failed": 0, "positions_failed": 32, "positions_opened": 277}	2025-09-16 02:37:11.281823+00
702	main_trader	HEALTHY	t	t	t	\N	277	0	0	\N	{"sl_set": 278, "sl_failed": 0, "positions_failed": 32, "positions_opened": 277}	2025-09-16 02:38:12.411558+00
703	main_trader	HEALTHY	t	t	t	\N	277	0	0	\N	{"sl_set": 278, "sl_failed": 0, "positions_failed": 32, "positions_opened": 277}	2025-09-16 02:39:13.431924+00
704	main_trader	HEALTHY	t	t	t	\N	277	0	0	\N	{"sl_set": 278, "sl_failed": 0, "positions_failed": 32, "positions_opened": 277}	2025-09-16 02:40:14.640005+00
705	main_trader	HEALTHY	t	t	t	\N	277	0	0	\N	{"sl_set": 278, "sl_failed": 0, "positions_failed": 32, "positions_opened": 277}	2025-09-16 02:41:15.735466+00
706	main_trader	HEALTHY	t	t	t	\N	277	0	0	\N	{"sl_set": 278, "sl_failed": 0, "positions_failed": 32, "positions_opened": 277}	2025-09-16 02:42:16.866121+00
707	main_trader	HEALTHY	t	t	t	\N	277	0	0	\N	{"sl_set": 278, "sl_failed": 0, "positions_failed": 32, "positions_opened": 277}	2025-09-16 02:43:17.909881+00
708	main_trader	HEALTHY	t	t	t	\N	277	0	0	\N	{"sl_set": 278, "sl_failed": 0, "positions_failed": 32, "positions_opened": 277}	2025-09-16 02:44:19.027098+00
709	main_trader	HEALTHY	t	t	t	\N	277	0	0	\N	{"sl_set": 278, "sl_failed": 0, "positions_failed": 32, "positions_opened": 277}	2025-09-16 02:45:20.371269+00
710	main_trader	HEALTHY	t	t	t	\N	277	0	0	\N	{"sl_set": 278, "sl_failed": 0, "positions_failed": 32, "positions_opened": 277}	2025-09-16 02:46:21.571704+00
711	main_trader	HEALTHY	t	t	t	\N	277	0	0	\N	{"sl_set": 278, "sl_failed": 0, "positions_failed": 32, "positions_opened": 277}	2025-09-16 02:47:22.59829+00
712	main_trader	HEALTHY	t	t	t	\N	277	0	0	\N	{"sl_set": 278, "sl_failed": 0, "positions_failed": 32, "positions_opened": 277}	2025-09-16 02:48:23.617214+00
713	main_trader	HEALTHY	t	t	t	\N	277	0	0	\N	{"sl_set": 278, "sl_failed": 0, "positions_failed": 32, "positions_opened": 277}	2025-09-16 02:49:24.73192+00
714	main_trader	HEALTHY	t	t	t	\N	277	0	0	\N	{"sl_set": 279, "sl_failed": 0, "positions_failed": 32, "positions_opened": 278}	2025-09-16 02:50:25.691146+00
715	main_trader	HEALTHY	t	t	t	\N	282	0	0	\N	{"sl_set": 283, "sl_failed": 0, "positions_failed": 34, "positions_opened": 282}	2025-09-16 02:51:26.878389+00
716	main_trader	HEALTHY	t	t	t	\N	288	0	0	\N	{"sl_set": 290, "sl_failed": 0, "positions_failed": 34, "positions_opened": 289}	2025-09-16 02:52:28.06261+00
717	main_trader	HEALTHY	t	t	t	\N	292	0	0	\N	{"sl_set": 294, "sl_failed": 0, "positions_failed": 34, "positions_opened": 292}	2025-09-16 02:53:29.186726+00
718	main_trader	HEALTHY	t	t	t	\N	292	0	0	\N	{"sl_set": 294, "sl_failed": 0, "positions_failed": 34, "positions_opened": 292}	2025-09-16 02:54:30.223613+00
719	main_trader	HEALTHY	t	t	t	\N	292	0	0	\N	{"sl_set": 294, "sl_failed": 0, "positions_failed": 34, "positions_opened": 292}	2025-09-16 02:55:31.345431+00
720	main_trader	HEALTHY	t	t	t	\N	292	0	0	\N	{"sl_set": 294, "sl_failed": 0, "positions_failed": 34, "positions_opened": 292}	2025-09-16 02:56:33.137574+00
721	main_trader	HEALTHY	t	t	t	\N	292	0	0	\N	{"sl_set": 294, "sl_failed": 0, "positions_failed": 34, "positions_opened": 292}	2025-09-16 02:57:34.26827+00
722	main_trader	HEALTHY	t	t	t	\N	292	0	0	\N	{"sl_set": 294, "sl_failed": 0, "positions_failed": 34, "positions_opened": 292}	2025-09-16 02:58:35.411689+00
723	main_trader	HEALTHY	t	t	t	\N	292	0	0	\N	{"sl_set": 294, "sl_failed": 0, "positions_failed": 34, "positions_opened": 292}	2025-09-16 02:59:36.544004+00
724	main_trader	HEALTHY	t	t	t	\N	292	0	0	\N	{"sl_set": 294, "sl_failed": 0, "positions_failed": 34, "positions_opened": 292}	2025-09-16 03:00:37.600874+00
725	main_trader	HEALTHY	t	t	t	\N	292	0	0	\N	{"sl_set": 294, "sl_failed": 0, "positions_failed": 34, "positions_opened": 292}	2025-09-16 03:01:38.962098+00
726	main_trader	HEALTHY	t	t	t	\N	292	0	0	\N	{"sl_set": 294, "sl_failed": 0, "positions_failed": 34, "positions_opened": 292}	2025-09-16 03:02:40.091086+00
727	main_trader	HEALTHY	t	t	t	\N	292	0	0	\N	{"sl_set": 294, "sl_failed": 0, "positions_failed": 34, "positions_opened": 292}	2025-09-16 03:03:41.226778+00
728	main_trader	HEALTHY	t	t	t	\N	292	0	0	\N	{"sl_set": 294, "sl_failed": 0, "positions_failed": 34, "positions_opened": 292}	2025-09-16 03:04:42.351935+00
729	main_trader	HEALTHY	t	t	t	\N	294	0	0	\N	{"sl_set": 297, "sl_failed": 0, "positions_failed": 34, "positions_opened": 295}	2025-09-16 03:05:43.457495+00
730	main_trader	HEALTHY	t	t	t	\N	300	0	0	\N	{"sl_set": 302, "sl_failed": 0, "positions_failed": 34, "positions_opened": 301}	2025-09-16 03:06:44.767647+00
731	main_trader	HEALTHY	t	t	t	\N	304	0	0	\N	{"sl_set": 307, "sl_failed": 0, "positions_failed": 36, "positions_opened": 305}	2025-09-16 03:07:46.583267+00
732	main_trader	HEALTHY	t	t	t	\N	308	0	0	\N	{"sl_set": 311, "sl_failed": 0, "positions_failed": 37, "positions_opened": 308}	2025-09-16 03:08:47.770225+00
733	main_trader	HEALTHY	t	t	t	\N	308	0	0	\N	{"sl_set": 311, "sl_failed": 0, "positions_failed": 37, "positions_opened": 308}	2025-09-16 03:09:48.792748+00
734	main_trader	HEALTHY	t	t	t	\N	308	0	0	\N	{"sl_set": 311, "sl_failed": 0, "positions_failed": 37, "positions_opened": 308}	2025-09-16 03:10:50.679775+00
735	main_trader	HEALTHY	t	t	t	\N	308	0	0	\N	{"sl_set": 311, "sl_failed": 0, "positions_failed": 37, "positions_opened": 308}	2025-09-16 03:11:51.704823+00
736	main_trader	HEALTHY	t	t	t	\N	308	0	0	\N	{"sl_set": 311, "sl_failed": 0, "positions_failed": 37, "positions_opened": 308}	2025-09-16 03:12:53.170022+00
737	main_trader	HEALTHY	t	t	t	\N	308	0	0	\N	{"sl_set": 311, "sl_failed": 0, "positions_failed": 37, "positions_opened": 308}	2025-09-16 03:13:54.363542+00
738	main_trader	HEALTHY	t	t	t	\N	308	0	0	\N	{"sl_set": 311, "sl_failed": 0, "positions_failed": 37, "positions_opened": 308}	2025-09-16 03:14:55.468675+00
739	main_trader	HEALTHY	t	t	t	\N	308	0	0	\N	{"sl_set": 311, "sl_failed": 0, "positions_failed": 37, "positions_opened": 308}	2025-09-16 03:15:56.845649+00
740	main_trader	HEALTHY	t	t	t	\N	308	0	0	\N	{"sl_set": 311, "sl_failed": 0, "positions_failed": 37, "positions_opened": 308}	2025-09-16 03:16:57.884462+00
741	main_trader	HEALTHY	t	t	t	\N	308	0	0	\N	{"sl_set": 311, "sl_failed": 0, "positions_failed": 37, "positions_opened": 308}	2025-09-16 03:17:59.230208+00
742	main_trader	HEALTHY	t	t	t	\N	308	0	0	\N	{"sl_set": 311, "sl_failed": 0, "positions_failed": 37, "positions_opened": 308}	2025-09-16 03:19:00.430653+00
743	main_trader	HEALTHY	t	t	t	\N	308	0	0	\N	{"sl_set": 311, "sl_failed": 0, "positions_failed": 37, "positions_opened": 308}	2025-09-16 03:20:01.589296+00
744	main_trader	HEALTHY	t	t	t	\N	313	0	0	\N	{"sl_set": 316, "sl_failed": 0, "positions_failed": 38, "positions_opened": 313}	2025-09-16 03:21:02.748901+00
745	main_trader	HEALTHY	t	t	t	\N	318	0	0	\N	{"sl_set": 321, "sl_failed": 0, "positions_failed": 39, "positions_opened": 319}	2025-09-16 03:22:03.620001+00
746	main_trader	HEALTHY	t	t	t	\N	321	0	0	\N	{"sl_set": 324, "sl_failed": 0, "positions_failed": 42, "positions_opened": 322}	2025-09-16 03:23:04.721461+00
747	main_trader	HEALTHY	t	t	t	\N	322	0	0	\N	{"sl_set": 325, "sl_failed": 0, "positions_failed": 42, "positions_opened": 322}	2025-09-16 03:24:05.886463+00
748	main_trader	HEALTHY	t	t	t	\N	322	0	0	\N	{"sl_set": 325, "sl_failed": 0, "positions_failed": 42, "positions_opened": 322}	2025-09-16 03:25:07.027931+00
749	main_trader	HEALTHY	t	t	t	\N	322	0	0	\N	{"sl_set": 325, "sl_failed": 0, "positions_failed": 42, "positions_opened": 322}	2025-09-16 03:26:08.052409+00
750	main_trader	HEALTHY	t	t	t	\N	322	0	0	\N	{"sl_set": 325, "sl_failed": 0, "positions_failed": 42, "positions_opened": 322}	2025-09-16 03:27:09.131348+00
751	main_trader	HEALTHY	t	t	t	\N	322	0	0	\N	{"sl_set": 325, "sl_failed": 0, "positions_failed": 42, "positions_opened": 322}	2025-09-16 03:28:10.930632+00
752	main_trader	HEALTHY	t	t	t	\N	322	0	0	\N	{"sl_set": 325, "sl_failed": 0, "positions_failed": 42, "positions_opened": 322}	2025-09-16 03:29:12.04462+00
753	main_trader	HEALTHY	t	t	t	\N	322	0	0	\N	{"sl_set": 325, "sl_failed": 0, "positions_failed": 42, "positions_opened": 322}	2025-09-16 03:30:13.08788+00
754	main_trader	HEALTHY	t	t	t	\N	322	0	0	\N	{"sl_set": 325, "sl_failed": 0, "positions_failed": 42, "positions_opened": 322}	2025-09-16 03:31:14.842196+00
755	main_trader	HEALTHY	t	t	t	\N	322	0	0	\N	{"sl_set": 325, "sl_failed": 0, "positions_failed": 42, "positions_opened": 322}	2025-09-16 03:32:15.958821+00
756	main_trader	HEALTHY	t	t	t	\N	322	0	0	\N	{"sl_set": 325, "sl_failed": 0, "positions_failed": 42, "positions_opened": 322}	2025-09-16 03:33:16.987499+00
757	main_trader	HEALTHY	t	t	t	\N	322	0	0	\N	{"sl_set": 325, "sl_failed": 0, "positions_failed": 42, "positions_opened": 322}	2025-09-16 03:34:18.102043+00
758	main_trader	HEALTHY	t	t	t	\N	322	0	0	\N	{"sl_set": 325, "sl_failed": 0, "positions_failed": 42, "positions_opened": 323}	2025-09-16 03:35:19.132717+00
759	main_trader	HEALTHY	t	t	t	\N	327	0	0	\N	{"sl_set": 331, "sl_failed": 0, "positions_failed": 43, "positions_opened": 328}	2025-09-16 03:36:20.09222+00
760	main_trader	HEALTHY	t	t	t	\N	333	0	0	\N	{"sl_set": 336, "sl_failed": 0, "positions_failed": 44, "positions_opened": 333}	2025-09-16 03:37:21.175044+00
761	main_trader	HEALTHY	t	t	t	\N	333	0	0	\N	{"sl_set": 336, "sl_failed": 0, "positions_failed": 44, "positions_opened": 333}	2025-09-16 03:38:22.374882+00
762	main_trader	HEALTHY	t	t	t	\N	333	0	0	\N	{"sl_set": 336, "sl_failed": 0, "positions_failed": 44, "positions_opened": 333}	2025-09-16 03:39:23.399414+00
763	main_trader	HEALTHY	t	t	t	\N	333	0	0	\N	{"sl_set": 336, "sl_failed": 0, "positions_failed": 44, "positions_opened": 333}	2025-09-16 03:40:24.476218+00
764	main_trader	HEALTHY	t	t	t	\N	333	0	0	\N	{"sl_set": 336, "sl_failed": 0, "positions_failed": 44, "positions_opened": 333}	2025-09-16 03:41:25.604484+00
765	main_trader	HEALTHY	t	t	t	\N	333	0	0	\N	{"sl_set": 336, "sl_failed": 0, "positions_failed": 44, "positions_opened": 333}	2025-09-16 03:42:27.39355+00
766	main_trader	HEALTHY	t	t	t	\N	333	0	0	\N	{"sl_set": 336, "sl_failed": 0, "positions_failed": 44, "positions_opened": 333}	2025-09-16 03:43:28.482371+00
767	main_trader	HEALTHY	t	t	t	\N	333	0	0	\N	{"sl_set": 336, "sl_failed": 0, "positions_failed": 44, "positions_opened": 333}	2025-09-16 03:44:29.524402+00
768	main_trader	HEALTHY	t	t	t	\N	333	0	0	\N	{"sl_set": 336, "sl_failed": 0, "positions_failed": 44, "positions_opened": 333}	2025-09-16 03:45:30.629022+00
769	main_trader	HEALTHY	t	t	t	\N	333	0	0	\N	{"sl_set": 336, "sl_failed": 0, "positions_failed": 44, "positions_opened": 333}	2025-09-16 03:46:31.746711+00
770	main_trader	HEALTHY	t	t	t	\N	333	0	0	\N	{"sl_set": 336, "sl_failed": 0, "positions_failed": 44, "positions_opened": 333}	2025-09-16 03:47:33.005607+00
771	main_trader	HEALTHY	t	t	t	\N	333	0	0	\N	{"sl_set": 336, "sl_failed": 0, "positions_failed": 44, "positions_opened": 333}	2025-09-16 03:48:34.134882+00
772	main_trader	HEALTHY	t	t	t	\N	333	0	0	\N	{"sl_set": 336, "sl_failed": 0, "positions_failed": 44, "positions_opened": 333}	2025-09-16 03:49:35.281927+00
773	main_trader	HEALTHY	t	t	t	\N	334	0	0	\N	{"sl_set": 337, "sl_failed": 0, "positions_failed": 44, "positions_opened": 334}	2025-09-16 03:50:36.164884+00
774	main_trader	HEALTHY	t	t	t	\N	339	0	0	\N	{"sl_set": 342, "sl_failed": 0, "positions_failed": 45, "positions_opened": 340}	2025-09-16 03:51:37.032403+00
775	main_trader	HEALTHY	t	t	t	\N	345	0	0	\N	{"sl_set": 348, "sl_failed": 0, "positions_failed": 45, "positions_opened": 345}	2025-09-16 03:52:38.110284+00
776	main_trader	HEALTHY	t	t	t	\N	345	0	0	\N	{"sl_set": 348, "sl_failed": 0, "positions_failed": 45, "positions_opened": 345}	2025-09-16 03:53:39.85069+00
777	main_trader	HEALTHY	t	t	t	\N	345	0	0	\N	{"sl_set": 348, "sl_failed": 0, "positions_failed": 45, "positions_opened": 345}	2025-09-16 03:54:41.097387+00
778	main_trader	HEALTHY	t	t	t	\N	345	0	0	\N	{"sl_set": 348, "sl_failed": 0, "positions_failed": 45, "positions_opened": 345}	2025-09-16 03:55:42.423683+00
779	main_trader	HEALTHY	t	t	t	\N	345	0	0	\N	{"sl_set": 348, "sl_failed": 0, "positions_failed": 45, "positions_opened": 345}	2025-09-16 03:56:43.445431+00
780	main_trader	HEALTHY	t	t	t	\N	345	0	0	\N	{"sl_set": 348, "sl_failed": 0, "positions_failed": 45, "positions_opened": 345}	2025-09-16 03:57:44.578744+00
781	main_trader	HEALTHY	t	t	t	\N	345	0	0	\N	{"sl_set": 348, "sl_failed": 0, "positions_failed": 45, "positions_opened": 345}	2025-09-16 03:58:45.947978+00
782	main_trader	HEALTHY	t	t	t	\N	345	0	0	\N	{"sl_set": 348, "sl_failed": 0, "positions_failed": 45, "positions_opened": 345}	2025-09-16 03:59:47.148416+00
783	main_trader	HEALTHY	t	t	t	\N	345	0	0	\N	{"sl_set": 348, "sl_failed": 0, "positions_failed": 45, "positions_opened": 345}	2025-09-16 04:00:48.26934+00
784	main_trader	HEALTHY	t	t	t	\N	345	0	0	\N	{"sl_set": 348, "sl_failed": 0, "positions_failed": 45, "positions_opened": 345}	2025-09-16 04:01:49.35055+00
785	main_trader	HEALTHY	t	t	t	\N	345	0	0	\N	{"sl_set": 348, "sl_failed": 0, "positions_failed": 45, "positions_opened": 345}	2025-09-16 04:02:50.486565+00
786	main_trader	HEALTHY	t	t	t	\N	345	0	0	\N	{"sl_set": 348, "sl_failed": 0, "positions_failed": 45, "positions_opened": 345}	2025-09-16 04:03:51.76978+00
787	main_trader	HEALTHY	t	t	t	\N	345	0	0	\N	{"sl_set": 348, "sl_failed": 0, "positions_failed": 45, "positions_opened": 345}	2025-09-16 04:04:52.993808+00
788	main_trader	HEALTHY	t	t	t	\N	345	0	0	\N	{"sl_set": 348, "sl_failed": 0, "positions_failed": 45, "positions_opened": 345}	2025-09-16 04:05:54.072182+00
789	main_trader	HEALTHY	t	t	t	\N	345	0	0	\N	{"sl_set": 348, "sl_failed": 0, "positions_failed": 46, "positions_opened": 345}	2025-09-16 04:06:55.359004+00
790	main_trader	HEALTHY	t	t	t	\N	345	0	0	\N	{"sl_set": 348, "sl_failed": 0, "positions_failed": 46, "positions_opened": 345}	2025-09-16 04:07:56.707083+00
791	main_trader	HEALTHY	t	t	t	\N	345	0	0	\N	{"sl_set": 348, "sl_failed": 0, "positions_failed": 46, "positions_opened": 345}	2025-09-16 04:08:58.09454+00
792	main_trader	HEALTHY	t	t	t	\N	345	0	0	\N	{"sl_set": 348, "sl_failed": 0, "positions_failed": 46, "positions_opened": 345}	2025-09-16 04:09:59.253334+00
793	main_trader	HEALTHY	t	t	t	\N	345	0	0	\N	{"sl_set": 348, "sl_failed": 0, "positions_failed": 46, "positions_opened": 345}	2025-09-16 04:11:00.375089+00
794	main_trader	HEALTHY	t	t	t	\N	345	0	0	\N	{"sl_set": 348, "sl_failed": 0, "positions_failed": 46, "positions_opened": 345}	2025-09-16 04:12:01.409768+00
795	main_trader	HEALTHY	t	t	t	\N	345	0	0	\N	{"sl_set": 348, "sl_failed": 0, "positions_failed": 46, "positions_opened": 345}	2025-09-16 04:13:02.452497+00
796	main_trader	HEALTHY	t	t	t	\N	345	0	0	\N	{"sl_set": 348, "sl_failed": 0, "positions_failed": 46, "positions_opened": 345}	2025-09-16 04:14:03.952667+00
797	main_trader	HEALTHY	t	t	t	\N	345	0	0	\N	{"sl_set": 348, "sl_failed": 0, "positions_failed": 46, "positions_opened": 345}	2025-09-16 04:15:05.146054+00
798	main_trader	HEALTHY	t	t	t	\N	345	0	0	\N	{"sl_set": 348, "sl_failed": 0, "positions_failed": 46, "positions_opened": 345}	2025-09-16 04:16:06.186763+00
799	main_trader	HEALTHY	t	t	t	\N	345	0	0	\N	{"sl_set": 348, "sl_failed": 0, "positions_failed": 46, "positions_opened": 345}	2025-09-16 04:17:07.231106+00
800	main_trader	HEALTHY	t	t	t	\N	345	0	0	\N	{"sl_set": 348, "sl_failed": 0, "positions_failed": 46, "positions_opened": 345}	2025-09-16 04:18:08.339582+00
801	main_trader	HEALTHY	t	t	t	\N	345	0	0	\N	{"sl_set": 348, "sl_failed": 0, "positions_failed": 46, "positions_opened": 345}	2025-09-16 04:19:09.575463+00
802	main_trader	HEALTHY	t	t	t	\N	345	0	0	\N	{"sl_set": 348, "sl_failed": 0, "positions_failed": 46, "positions_opened": 345}	2025-09-16 04:20:10.779785+00
803	main_trader	HEALTHY	t	t	t	\N	345	0	0	\N	{"sl_set": 348, "sl_failed": 0, "positions_failed": 46, "positions_opened": 345}	2025-09-16 04:21:11.963701+00
804	main_trader	HEALTHY	t	t	t	\N	345	0	0	\N	{"sl_set": 348, "sl_failed": 0, "positions_failed": 46, "positions_opened": 345}	2025-09-16 04:22:13.020528+00
805	main_trader	HEALTHY	t	t	t	\N	347	0	0	\N	{"sl_set": 350, "sl_failed": 0, "positions_failed": 47, "positions_opened": 347}	2025-09-16 04:23:14.042074+00
806	main_trader	HEALTHY	t	t	t	\N	347	0	0	\N	{"sl_set": 350, "sl_failed": 0, "positions_failed": 47, "positions_opened": 347}	2025-09-16 04:24:15.289647+00
807	main_trader	HEALTHY	t	t	t	\N	347	0	0	\N	{"sl_set": 350, "sl_failed": 0, "positions_failed": 47, "positions_opened": 347}	2025-09-16 04:25:16.393805+00
808	main_trader	HEALTHY	t	t	t	\N	347	0	0	\N	{"sl_set": 350, "sl_failed": 0, "positions_failed": 47, "positions_opened": 347}	2025-09-16 04:26:17.448953+00
809	main_trader	HEALTHY	t	t	t	\N	347	0	0	\N	{"sl_set": 350, "sl_failed": 0, "positions_failed": 47, "positions_opened": 347}	2025-09-16 04:27:18.507552+00
810	main_trader	HEALTHY	t	t	t	\N	347	0	0	\N	{"sl_set": 350, "sl_failed": 0, "positions_failed": 47, "positions_opened": 347}	2025-09-16 04:28:19.638067+00
811	main_trader	HEALTHY	t	t	t	\N	347	0	0	\N	{"sl_set": 350, "sl_failed": 0, "positions_failed": 47, "positions_opened": 347}	2025-09-16 04:29:21.613076+00
812	main_trader	HEALTHY	t	t	t	\N	347	0	0	\N	{"sl_set": 350, "sl_failed": 0, "positions_failed": 47, "positions_opened": 347}	2025-09-16 04:30:22.828555+00
813	main_trader	HEALTHY	t	t	t	\N	347	0	0	\N	{"sl_set": 350, "sl_failed": 0, "positions_failed": 47, "positions_opened": 347}	2025-09-16 04:31:23.864223+00
814	main_trader	HEALTHY	t	t	t	\N	347	0	0	\N	{"sl_set": 350, "sl_failed": 0, "positions_failed": 47, "positions_opened": 347}	2025-09-16 04:32:24.978078+00
815	main_trader	HEALTHY	t	t	t	\N	347	0	0	\N	{"sl_set": 350, "sl_failed": 0, "positions_failed": 47, "positions_opened": 347}	2025-09-16 04:33:26.111237+00
816	main_trader	HEALTHY	t	t	t	\N	347	0	0	\N	{"sl_set": 350, "sl_failed": 0, "positions_failed": 47, "positions_opened": 347}	2025-09-16 04:34:27.468+00
817	main_trader	HEALTHY	t	t	t	\N	348	0	0	\N	{"sl_set": 352, "sl_failed": 0, "positions_failed": 47, "positions_opened": 349}	2025-09-16 04:35:28.400245+00
818	main_trader	HEALTHY	t	t	t	\N	354	0	0	\N	{"sl_set": 356, "sl_failed": 1, "positions_failed": 47, "positions_opened": 354}	2025-09-16 04:36:30.010481+00
819	main_trader	HEALTHY	t	t	t	\N	357	0	0	\N	{"sl_set": 359, "sl_failed": 1, "positions_failed": 50, "positions_opened": 357}	2025-09-16 04:37:31.140779+00
820	main_trader	HEALTHY	t	t	t	\N	357	0	0	\N	{"sl_set": 359, "sl_failed": 1, "positions_failed": 51, "positions_opened": 357}	2025-09-16 04:38:32.266065+00
821	main_trader	HEALTHY	t	t	t	\N	357	0	0	\N	{"sl_set": 359, "sl_failed": 1, "positions_failed": 51, "positions_opened": 357}	2025-09-16 04:39:33.383025+00
822	main_trader	HEALTHY	t	t	t	\N	357	0	0	\N	{"sl_set": 359, "sl_failed": 1, "positions_failed": 51, "positions_opened": 357}	2025-09-16 04:40:34.410255+00
823	main_trader	HEALTHY	t	t	t	\N	357	0	0	\N	{"sl_set": 359, "sl_failed": 1, "positions_failed": 51, "positions_opened": 357}	2025-09-16 04:41:36.238502+00
824	main_trader	HEALTHY	t	t	t	\N	357	0	0	\N	{"sl_set": 359, "sl_failed": 1, "positions_failed": 51, "positions_opened": 357}	2025-09-16 04:42:37.667747+00
825	main_trader	HEALTHY	t	t	t	\N	357	0	0	\N	{"sl_set": 359, "sl_failed": 1, "positions_failed": 51, "positions_opened": 357}	2025-09-16 04:43:38.773704+00
826	main_trader	HEALTHY	t	t	t	\N	357	0	0	\N	{"sl_set": 359, "sl_failed": 1, "positions_failed": 51, "positions_opened": 357}	2025-09-16 04:44:39.926265+00
827	main_trader	HEALTHY	t	t	t	\N	357	0	0	\N	{"sl_set": 359, "sl_failed": 1, "positions_failed": 51, "positions_opened": 357}	2025-09-16 04:45:41.05915+00
828	main_trader	HEALTHY	t	t	t	\N	357	0	0	\N	{"sl_set": 359, "sl_failed": 1, "positions_failed": 51, "positions_opened": 357}	2025-09-16 04:46:42.457336+00
829	main_trader	HEALTHY	t	t	t	\N	357	0	0	\N	{"sl_set": 359, "sl_failed": 1, "positions_failed": 51, "positions_opened": 357}	2025-09-16 04:47:44.036873+00
830	main_trader	HEALTHY	t	t	t	\N	357	0	0	\N	{"sl_set": 359, "sl_failed": 1, "positions_failed": 51, "positions_opened": 357}	2025-09-16 04:48:45.170555+00
831	main_trader	HEALTHY	t	t	t	\N	357	0	0	\N	{"sl_set": 359, "sl_failed": 1, "positions_failed": 51, "positions_opened": 357}	2025-09-16 04:49:46.199222+00
832	main_trader	HEALTHY	t	t	t	\N	357	0	0	\N	{"sl_set": 359, "sl_failed": 1, "positions_failed": 51, "positions_opened": 357}	2025-09-16 04:50:47.57581+00
833	main_trader	HEALTHY	t	t	t	\N	357	0	0	\N	{"sl_set": 359, "sl_failed": 1, "positions_failed": 51, "positions_opened": 357}	2025-09-16 04:51:48.996639+00
834	main_trader	HEALTHY	t	t	t	\N	357	0	0	\N	{"sl_set": 359, "sl_failed": 1, "positions_failed": 51, "positions_opened": 357}	2025-09-16 04:52:50.208076+00
835	main_trader	HEALTHY	t	t	t	\N	357	0	0	\N	{"sl_set": 359, "sl_failed": 1, "positions_failed": 51, "positions_opened": 357}	2025-09-16 04:53:51.385153+00
836	main_trader	HEALTHY	t	t	t	\N	357	0	0	\N	{"sl_set": 359, "sl_failed": 1, "positions_failed": 51, "positions_opened": 357}	2025-09-16 04:54:52.431991+00
837	main_trader	HEALTHY	t	t	t	\N	357	0	0	\N	{"sl_set": 359, "sl_failed": 1, "positions_failed": 51, "positions_opened": 357}	2025-09-16 04:55:53.485821+00
838	main_trader	HEALTHY	t	t	t	\N	357	0	0	\N	{"sl_set": 359, "sl_failed": 1, "positions_failed": 51, "positions_opened": 357}	2025-09-16 04:56:54.76266+00
839	main_trader	HEALTHY	t	t	t	\N	357	0	0	\N	{"sl_set": 359, "sl_failed": 1, "positions_failed": 51, "positions_opened": 357}	2025-09-16 04:57:55.886212+00
840	main_trader	HEALTHY	t	t	t	\N	357	0	0	\N	{"sl_set": 359, "sl_failed": 1, "positions_failed": 51, "positions_opened": 357}	2025-09-16 04:58:57.08676+00
841	main_trader	HEALTHY	t	t	t	\N	357	0	0	\N	{"sl_set": 359, "sl_failed": 1, "positions_failed": 51, "positions_opened": 357}	2025-09-16 04:59:58.134065+00
842	main_trader	HEALTHY	t	t	t	\N	357	0	0	\N	{"sl_set": 359, "sl_failed": 1, "positions_failed": 51, "positions_opened": 357}	2025-09-16 05:00:59.187631+00
843	main_trader	HEALTHY	t	t	t	\N	357	0	0	\N	{"sl_set": 359, "sl_failed": 1, "positions_failed": 51, "positions_opened": 357}	2025-09-16 05:02:00.583649+00
844	main_trader	HEALTHY	t	t	t	\N	357	0	0	\N	{"sl_set": 359, "sl_failed": 1, "positions_failed": 51, "positions_opened": 357}	2025-09-16 05:03:01.793935+00
845	main_trader	HEALTHY	t	t	t	\N	357	0	0	\N	{"sl_set": 359, "sl_failed": 1, "positions_failed": 51, "positions_opened": 357}	2025-09-16 05:04:02.922269+00
846	main_trader	HEALTHY	t	t	t	\N	357	0	0	\N	{"sl_set": 359, "sl_failed": 1, "positions_failed": 51, "positions_opened": 357}	2025-09-16 05:05:04.084788+00
847	main_trader	HEALTHY	t	t	t	\N	357	0	0	\N	{"sl_set": 359, "sl_failed": 1, "positions_failed": 51, "positions_opened": 357}	2025-09-16 05:06:05.168439+00
848	main_trader	HEALTHY	t	t	t	\N	358	0	0	\N	{"sl_set": 360, "sl_failed": 1, "positions_failed": 51, "positions_opened": 358}	2025-09-16 05:07:06.428639+00
849	main_trader	HEALTHY	t	t	t	\N	358	0	0	\N	{"sl_set": 360, "sl_failed": 1, "positions_failed": 51, "positions_opened": 358}	2025-09-16 05:08:07.567851+00
850	main_trader	HEALTHY	t	t	t	\N	358	0	0	\N	{"sl_set": 360, "sl_failed": 1, "positions_failed": 51, "positions_opened": 358}	2025-09-16 05:09:08.609747+00
851	main_trader	HEALTHY	t	t	t	\N	358	0	0	\N	{"sl_set": 360, "sl_failed": 1, "positions_failed": 51, "positions_opened": 358}	2025-09-16 05:10:09.645582+00
852	main_trader	HEALTHY	t	t	t	\N	358	0	0	\N	{"sl_set": 360, "sl_failed": 1, "positions_failed": 51, "positions_opened": 358}	2025-09-16 05:11:10.687341+00
853	main_trader	HEALTHY	t	t	t	\N	358	0	0	\N	{"sl_set": 360, "sl_failed": 1, "positions_failed": 51, "positions_opened": 358}	2025-09-16 05:12:13.482618+00
854	main_trader	HEALTHY	t	t	t	\N	358	0	0	\N	{"sl_set": 360, "sl_failed": 1, "positions_failed": 51, "positions_opened": 358}	2025-09-16 05:13:14.597689+00
855	main_trader	HEALTHY	t	t	t	\N	358	0	0	\N	{"sl_set": 360, "sl_failed": 1, "positions_failed": 51, "positions_opened": 358}	2025-09-16 05:14:15.727625+00
856	main_trader	HEALTHY	t	t	t	\N	358	0	0	\N	{"sl_set": 360, "sl_failed": 1, "positions_failed": 51, "positions_opened": 358}	2025-09-16 05:15:16.781314+00
857	main_trader	HEALTHY	t	t	t	\N	358	0	0	\N	{"sl_set": 360, "sl_failed": 1, "positions_failed": 51, "positions_opened": 358}	2025-09-16 05:16:17.903611+00
858	main_trader	HEALTHY	t	t	t	\N	358	0	0	\N	{"sl_set": 360, "sl_failed": 1, "positions_failed": 51, "positions_opened": 358}	2025-09-16 05:17:19.242225+00
859	main_trader	HEALTHY	t	t	t	\N	358	0	0	\N	{"sl_set": 360, "sl_failed": 1, "positions_failed": 51, "positions_opened": 358}	2025-09-16 05:18:20.447885+00
860	main_trader	HEALTHY	t	t	t	\N	358	0	0	\N	{"sl_set": 360, "sl_failed": 1, "positions_failed": 51, "positions_opened": 358}	2025-09-16 05:19:21.482079+00
861	main_trader	HEALTHY	t	t	t	\N	359	0	0	\N	{"sl_set": 362, "sl_failed": 1, "positions_failed": 51, "positions_opened": 360}	2025-09-16 05:20:22.541221+00
862	main_trader	HEALTHY	t	t	t	\N	365	0	0	\N	{"sl_set": 367, "sl_failed": 1, "positions_failed": 52, "positions_opened": 365}	2025-09-16 05:21:23.442379+00
863	main_trader	HEALTHY	t	t	t	\N	366	0	0	\N	{"sl_set": 368, "sl_failed": 1, "positions_failed": 53, "positions_opened": 366}	2025-09-16 05:22:24.56976+00
864	main_trader	HEALTHY	t	t	t	\N	366	0	0	\N	{"sl_set": 368, "sl_failed": 1, "positions_failed": 53, "positions_opened": 366}	2025-09-16 05:23:25.783379+00
865	main_trader	HEALTHY	t	t	t	\N	366	0	0	\N	{"sl_set": 368, "sl_failed": 1, "positions_failed": 53, "positions_opened": 366}	2025-09-16 05:24:26.89737+00
866	main_trader	HEALTHY	t	t	t	\N	366	0	0	\N	{"sl_set": 368, "sl_failed": 1, "positions_failed": 53, "positions_opened": 366}	2025-09-16 05:25:28.017325+00
867	main_trader	HEALTHY	t	t	t	\N	366	0	0	\N	{"sl_set": 368, "sl_failed": 1, "positions_failed": 53, "positions_opened": 366}	2025-09-16 05:26:29.144278+00
868	main_trader	HEALTHY	t	t	t	\N	366	0	0	\N	{"sl_set": 368, "sl_failed": 1, "positions_failed": 53, "positions_opened": 366}	2025-09-16 05:27:30.413756+00
869	main_trader	HEALTHY	t	t	t	\N	366	0	0	\N	{"sl_set": 368, "sl_failed": 1, "positions_failed": 53, "positions_opened": 366}	2025-09-16 05:28:31.559373+00
870	main_trader	HEALTHY	t	t	t	\N	366	0	0	\N	{"sl_set": 368, "sl_failed": 1, "positions_failed": 53, "positions_opened": 366}	2025-09-16 05:29:32.754259+00
871	main_trader	HEALTHY	t	t	t	\N	366	0	0	\N	{"sl_set": 368, "sl_failed": 1, "positions_failed": 53, "positions_opened": 366}	2025-09-16 05:30:33.953125+00
872	main_trader	HEALTHY	t	t	t	\N	366	0	0	\N	{"sl_set": 368, "sl_failed": 1, "positions_failed": 53, "positions_opened": 366}	2025-09-16 05:31:35.156118+00
873	main_trader	HEALTHY	t	t	t	\N	366	0	0	\N	{"sl_set": 368, "sl_failed": 1, "positions_failed": 53, "positions_opened": 366}	2025-09-16 05:32:36.579669+00
874	main_trader	HEALTHY	t	t	t	\N	366	0	0	\N	{"sl_set": 368, "sl_failed": 1, "positions_failed": 53, "positions_opened": 366}	2025-09-16 05:33:37.721981+00
875	main_trader	HEALTHY	t	t	t	\N	366	0	0	\N	{"sl_set": 368, "sl_failed": 1, "positions_failed": 53, "positions_opened": 366}	2025-09-16 05:34:38.926205+00
876	main_trader	HEALTHY	t	t	t	\N	367	0	0	\N	{"sl_set": 369, "sl_failed": 1, "positions_failed": 53, "positions_opened": 368}	2025-09-16 05:35:39.827579+00
877	main_trader	HEALTHY	t	t	t	\N	368	0	0	\N	{"sl_set": 370, "sl_failed": 1, "positions_failed": 53, "positions_opened": 368}	2025-09-16 05:36:40.989176+00
878	main_trader	HEALTHY	t	t	t	\N	368	0	0	\N	{"sl_set": 370, "sl_failed": 1, "positions_failed": 53, "positions_opened": 368}	2025-09-16 05:37:42.487042+00
879	main_trader	HEALTHY	t	t	t	\N	368	0	0	\N	{"sl_set": 370, "sl_failed": 1, "positions_failed": 53, "positions_opened": 368}	2025-09-16 05:38:43.761647+00
880	main_trader	HEALTHY	t	t	t	\N	368	0	0	\N	{"sl_set": 370, "sl_failed": 1, "positions_failed": 53, "positions_opened": 368}	2025-09-16 05:39:44.840124+00
881	main_trader	HEALTHY	t	t	t	\N	368	0	0	\N	{"sl_set": 370, "sl_failed": 1, "positions_failed": 53, "positions_opened": 368}	2025-09-16 05:40:46.012776+00
882	main_trader	HEALTHY	t	t	t	\N	368	0	0	\N	{"sl_set": 370, "sl_failed": 1, "positions_failed": 53, "positions_opened": 368}	2025-09-16 05:41:47.077104+00
883	main_trader	HEALTHY	t	t	t	\N	368	0	0	\N	{"sl_set": 370, "sl_failed": 1, "positions_failed": 53, "positions_opened": 368}	2025-09-16 05:42:48.964694+00
884	main_trader	HEALTHY	t	t	t	\N	368	0	0	\N	{"sl_set": 370, "sl_failed": 1, "positions_failed": 53, "positions_opened": 368}	2025-09-16 05:43:50.213928+00
885	main_trader	HEALTHY	t	t	t	\N	368	0	0	\N	{"sl_set": 370, "sl_failed": 1, "positions_failed": 53, "positions_opened": 368}	2025-09-16 05:44:51.370533+00
886	main_trader	HEALTHY	t	t	t	\N	368	0	0	\N	{"sl_set": 370, "sl_failed": 1, "positions_failed": 53, "positions_opened": 368}	2025-09-16 05:45:52.46267+00
887	main_trader	HEALTHY	t	t	t	\N	368	0	0	\N	{"sl_set": 370, "sl_failed": 1, "positions_failed": 53, "positions_opened": 368}	2025-09-16 05:46:53.626854+00
888	main_trader	HEALTHY	t	t	t	\N	368	0	0	\N	{"sl_set": 370, "sl_failed": 1, "positions_failed": 53, "positions_opened": 368}	2025-09-16 05:47:54.947795+00
889	main_trader	HEALTHY	t	t	t	\N	368	0	0	\N	{"sl_set": 370, "sl_failed": 1, "positions_failed": 53, "positions_opened": 368}	2025-09-16 05:48:56.084182+00
890	main_trader	HEALTHY	t	t	t	\N	368	0	0	\N	{"sl_set": 370, "sl_failed": 1, "positions_failed": 53, "positions_opened": 368}	2025-09-16 05:49:57.269053+00
891	main_trader	HEALTHY	t	t	t	\N	369	0	0	\N	{"sl_set": 371, "sl_failed": 1, "positions_failed": 54, "positions_opened": 369}	2025-09-16 05:50:58.64935+00
892	main_trader	HEALTHY	t	t	t	\N	369	0	0	\N	{"sl_set": 371, "sl_failed": 1, "positions_failed": 54, "positions_opened": 369}	2025-09-16 05:51:59.745547+00
893	main_trader	HEALTHY	t	t	t	\N	369	0	0	\N	{"sl_set": 371, "sl_failed": 1, "positions_failed": 54, "positions_opened": 369}	2025-09-16 05:53:01.049337+00
894	main_trader	HEALTHY	t	t	t	\N	369	0	0	\N	{"sl_set": 371, "sl_failed": 1, "positions_failed": 54, "positions_opened": 369}	2025-09-16 05:54:02.239382+00
895	main_trader	HEALTHY	t	t	t	\N	369	0	0	\N	{"sl_set": 371, "sl_failed": 1, "positions_failed": 54, "positions_opened": 369}	2025-09-16 05:55:03.439022+00
896	main_trader	HEALTHY	t	t	t	\N	369	0	0	\N	{"sl_set": 371, "sl_failed": 1, "positions_failed": 54, "positions_opened": 369}	2025-09-16 05:56:04.640286+00
897	main_trader	HEALTHY	t	t	t	\N	369	0	0	\N	{"sl_set": 371, "sl_failed": 1, "positions_failed": 54, "positions_opened": 369}	2025-09-16 05:57:05.718582+00
898	main_trader	HEALTHY	t	t	t	\N	369	0	0	\N	{"sl_set": 371, "sl_failed": 1, "positions_failed": 54, "positions_opened": 369}	2025-09-16 05:58:07.578242+00
899	main_trader	HEALTHY	t	t	t	\N	369	0	0	\N	{"sl_set": 371, "sl_failed": 1, "positions_failed": 54, "positions_opened": 369}	2025-09-16 05:59:08.724372+00
900	main_trader	HEALTHY	t	t	t	\N	369	0	0	\N	{"sl_set": 371, "sl_failed": 1, "positions_failed": 54, "positions_opened": 369}	2025-09-16 06:00:09.89367+00
901	main_trader	HEALTHY	t	t	t	\N	369	0	0	\N	{"sl_set": 371, "sl_failed": 1, "positions_failed": 54, "positions_opened": 369}	2025-09-16 06:01:11.01461+00
902	main_trader	HEALTHY	t	t	t	\N	369	0	0	\N	{"sl_set": 371, "sl_failed": 1, "positions_failed": 54, "positions_opened": 369}	2025-09-16 06:02:12.203147+00
903	main_trader	HEALTHY	t	t	t	\N	369	0	0	\N	{"sl_set": 371, "sl_failed": 1, "positions_failed": 54, "positions_opened": 369}	2025-09-16 06:03:13.677045+00
904	main_trader	HEALTHY	t	t	t	\N	369	0	0	\N	{"sl_set": 371, "sl_failed": 1, "positions_failed": 54, "positions_opened": 369}	2025-09-16 06:04:14.906448+00
905	main_trader	HEALTHY	t	t	t	\N	369	0	0	\N	{"sl_set": 371, "sl_failed": 1, "positions_failed": 54, "positions_opened": 369}	2025-09-16 06:05:15.977876+00
906	main_trader	HEALTHY	t	t	t	\N	369	0	0	\N	{"sl_set": 371, "sl_failed": 1, "positions_failed": 54, "positions_opened": 369}	2025-09-16 06:06:17.156814+00
907	main_trader	HEALTHY	t	t	t	\N	370	0	0	\N	{"sl_set": 372, "sl_failed": 1, "positions_failed": 55, "positions_opened": 370}	2025-09-16 06:07:18.2304+00
908	main_trader	HEALTHY	t	t	t	\N	370	0	0	\N	{"sl_set": 372, "sl_failed": 1, "positions_failed": 55, "positions_opened": 370}	2025-09-16 06:08:19.633919+00
909	main_trader	HEALTHY	t	t	t	\N	370	0	0	\N	{"sl_set": 372, "sl_failed": 1, "positions_failed": 55, "positions_opened": 370}	2025-09-16 06:09:20.855214+00
910	main_trader	HEALTHY	t	t	t	\N	370	0	0	\N	{"sl_set": 372, "sl_failed": 1, "positions_failed": 55, "positions_opened": 370}	2025-09-16 06:10:21.940263+00
911	main_trader	HEALTHY	t	t	t	\N	370	0	0	\N	{"sl_set": 372, "sl_failed": 1, "positions_failed": 55, "positions_opened": 370}	2025-09-16 06:11:23.141491+00
912	main_trader	HEALTHY	t	t	t	\N	370	0	0	\N	{"sl_set": 372, "sl_failed": 1, "positions_failed": 55, "positions_opened": 370}	2025-09-16 06:12:24.351758+00
913	main_trader	HEALTHY	t	t	t	\N	370	0	0	\N	{"sl_set": 372, "sl_failed": 1, "positions_failed": 55, "positions_opened": 370}	2025-09-16 06:13:26.221664+00
914	main_trader	HEALTHY	t	t	t	\N	370	0	0	\N	{"sl_set": 372, "sl_failed": 1, "positions_failed": 55, "positions_opened": 370}	2025-09-16 06:14:27.409893+00
915	main_trader	HEALTHY	t	t	t	\N	370	0	0	\N	{"sl_set": 372, "sl_failed": 1, "positions_failed": 55, "positions_opened": 370}	2025-09-16 06:15:28.618856+00
916	main_trader	HEALTHY	t	t	t	\N	370	0	0	\N	{"sl_set": 372, "sl_failed": 1, "positions_failed": 55, "positions_opened": 370}	2025-09-16 06:16:29.783142+00
917	main_trader	HEALTHY	t	t	t	\N	370	0	0	\N	{"sl_set": 372, "sl_failed": 1, "positions_failed": 55, "positions_opened": 370}	2025-09-16 06:17:30.962087+00
918	main_trader	HEALTHY	t	t	t	\N	370	0	0	\N	{"sl_set": 372, "sl_failed": 1, "positions_failed": 55, "positions_opened": 370}	2025-09-16 06:18:32.306789+00
919	main_trader	HEALTHY	t	t	t	\N	370	0	0	\N	{"sl_set": 372, "sl_failed": 1, "positions_failed": 55, "positions_opened": 370}	2025-09-16 06:19:33.612631+00
920	main_trader	HEALTHY	t	t	t	\N	371	0	0	\N	{"sl_set": 373, "sl_failed": 1, "positions_failed": 55, "positions_opened": 371}	2025-09-16 06:20:34.721826+00
921	main_trader	HEALTHY	t	t	t	\N	375	0	0	\N	{"sl_set": 377, "sl_failed": 1, "positions_failed": 55, "positions_opened": 375}	2025-09-16 06:21:35.842312+00
922	main_trader	HEALTHY	t	t	t	\N	375	0	0	\N	{"sl_set": 377, "sl_failed": 1, "positions_failed": 55, "positions_opened": 375}	2025-09-16 06:22:37.290105+00
923	main_trader	HEALTHY	t	t	t	\N	375	0	0	\N	{"sl_set": 377, "sl_failed": 1, "positions_failed": 55, "positions_opened": 375}	2025-09-16 06:23:38.807605+00
924	main_trader	HEALTHY	t	t	t	\N	375	0	0	\N	{"sl_set": 377, "sl_failed": 1, "positions_failed": 55, "positions_opened": 375}	2025-09-16 06:24:40.047845+00
925	main_trader	HEALTHY	t	t	t	\N	375	0	0	\N	{"sl_set": 377, "sl_failed": 1, "positions_failed": 55, "positions_opened": 375}	2025-09-16 06:25:41.132736+00
926	main_trader	HEALTHY	t	t	t	\N	375	0	0	\N	{"sl_set": 377, "sl_failed": 1, "positions_failed": 55, "positions_opened": 375}	2025-09-16 06:26:42.336745+00
927	main_trader	HEALTHY	t	t	t	\N	375	0	0	\N	{"sl_set": 377, "sl_failed": 1, "positions_failed": 55, "positions_opened": 375}	2025-09-16 06:27:43.531083+00
928	main_trader	HEALTHY	t	t	t	\N	375	0	0	\N	{"sl_set": 377, "sl_failed": 1, "positions_failed": 55, "positions_opened": 375}	2025-09-16 06:28:44.967644+00
929	main_trader	HEALTHY	t	t	t	\N	375	0	0	\N	{"sl_set": 377, "sl_failed": 1, "positions_failed": 55, "positions_opened": 375}	2025-09-16 06:29:46.101821+00
930	main_trader	HEALTHY	t	t	t	\N	375	0	0	\N	{"sl_set": 377, "sl_failed": 1, "positions_failed": 55, "positions_opened": 375}	2025-09-16 06:30:47.282341+00
931	main_trader	HEALTHY	t	t	t	\N	375	0	0	\N	{"sl_set": 377, "sl_failed": 1, "positions_failed": 55, "positions_opened": 375}	2025-09-16 06:31:48.441684+00
932	main_trader	HEALTHY	t	t	t	\N	375	0	0	\N	{"sl_set": 377, "sl_failed": 1, "positions_failed": 55, "positions_opened": 375}	2025-09-16 06:32:49.685327+00
933	main_trader	HEALTHY	t	t	t	\N	375	0	0	\N	{"sl_set": 377, "sl_failed": 1, "positions_failed": 55, "positions_opened": 375}	2025-09-16 06:33:50.914752+00
934	main_trader	HEALTHY	t	t	t	\N	375	0	0	\N	{"sl_set": 377, "sl_failed": 1, "positions_failed": 55, "positions_opened": 375}	2025-09-16 06:34:52.083146+00
935	main_trader	HEALTHY	t	t	t	\N	377	0	0	\N	{"sl_set": 380, "sl_failed": 1, "positions_failed": 55, "positions_opened": 378}	2025-09-16 06:35:52.984626+00
936	main_trader	HEALTHY	t	t	t	\N	380	0	0	\N	{"sl_set": 382, "sl_failed": 1, "positions_failed": 56, "positions_opened": 380}	2025-09-16 06:36:54.145725+00
937	main_trader	HEALTHY	t	t	t	\N	380	0	0	\N	{"sl_set": 382, "sl_failed": 1, "positions_failed": 56, "positions_opened": 380}	2025-09-16 06:37:55.566445+00
938	main_trader	HEALTHY	t	t	t	\N	380	0	0	\N	{"sl_set": 382, "sl_failed": 1, "positions_failed": 56, "positions_opened": 380}	2025-09-16 06:38:56.715056+00
939	main_trader	HEALTHY	t	t	t	\N	380	0	0	\N	{"sl_set": 382, "sl_failed": 1, "positions_failed": 56, "positions_opened": 380}	2025-09-16 06:39:57.871851+00
940	main_trader	HEALTHY	t	t	t	\N	380	0	0	\N	{"sl_set": 382, "sl_failed": 1, "positions_failed": 56, "positions_opened": 380}	2025-09-16 06:40:58.963141+00
941	main_trader	HEALTHY	t	t	t	\N	380	0	0	\N	{"sl_set": 382, "sl_failed": 1, "positions_failed": 56, "positions_opened": 380}	2025-09-16 06:42:00.157898+00
942	main_trader	HEALTHY	t	t	t	\N	380	0	0	\N	{"sl_set": 382, "sl_failed": 1, "positions_failed": 56, "positions_opened": 380}	2025-09-16 06:43:01.548259+00
943	main_trader	HEALTHY	t	t	t	\N	380	0	0	\N	{"sl_set": 382, "sl_failed": 1, "positions_failed": 56, "positions_opened": 380}	2025-09-16 06:44:03.347623+00
944	main_trader	HEALTHY	t	t	t	\N	380	0	0	\N	{"sl_set": 382, "sl_failed": 1, "positions_failed": 56, "positions_opened": 380}	2025-09-16 06:45:04.536843+00
945	main_trader	HEALTHY	t	t	t	\N	380	0	0	\N	{"sl_set": 382, "sl_failed": 1, "positions_failed": 56, "positions_opened": 380}	2025-09-16 06:46:05.679921+00
946	main_trader	HEALTHY	t	t	t	\N	380	0	0	\N	{"sl_set": 382, "sl_failed": 1, "positions_failed": 56, "positions_opened": 380}	2025-09-16 06:47:06.760902+00
947	main_trader	HEALTHY	t	t	t	\N	380	0	0	\N	{"sl_set": 382, "sl_failed": 1, "positions_failed": 56, "positions_opened": 380}	2025-09-16 06:48:07.924634+00
948	main_trader	HEALTHY	t	t	t	\N	380	0	0	\N	{"sl_set": 382, "sl_failed": 1, "positions_failed": 56, "positions_opened": 380}	2025-09-16 06:49:09.262687+00
949	main_trader	HEALTHY	t	t	t	\N	380	0	0	\N	{"sl_set": 382, "sl_failed": 1, "positions_failed": 56, "positions_opened": 381}	2025-09-16 06:50:10.236497+00
950	main_trader	HEALTHY	t	t	t	\N	383	0	0	\N	{"sl_set": 385, "sl_failed": 1, "positions_failed": 57, "positions_opened": 383}	2025-09-16 06:51:11.341306+00
951	main_trader	HEALTHY	t	t	t	\N	383	0	0	\N	{"sl_set": 385, "sl_failed": 1, "positions_failed": 57, "positions_opened": 383}	2025-09-16 06:52:12.397707+00
952	main_trader	HEALTHY	t	t	t	\N	383	0	0	\N	{"sl_set": 385, "sl_failed": 1, "positions_failed": 57, "positions_opened": 383}	2025-09-16 06:53:13.459118+00
953	main_trader	HEALTHY	t	t	t	\N	383	0	0	\N	{"sl_set": 385, "sl_failed": 1, "positions_failed": 57, "positions_opened": 383}	2025-09-16 06:54:14.874552+00
954	main_trader	HEALTHY	t	t	t	\N	383	0	0	\N	{"sl_set": 385, "sl_failed": 1, "positions_failed": 57, "positions_opened": 383}	2025-09-16 06:55:16.043565+00
955	main_trader	HEALTHY	t	t	t	\N	383	0	0	\N	{"sl_set": 385, "sl_failed": 1, "positions_failed": 57, "positions_opened": 383}	2025-09-16 06:56:17.20755+00
956	main_trader	HEALTHY	t	t	t	\N	383	0	0	\N	{"sl_set": 385, "sl_failed": 1, "positions_failed": 57, "positions_opened": 383}	2025-09-16 06:57:18.40196+00
957	main_trader	HEALTHY	t	t	t	\N	383	0	0	\N	{"sl_set": 385, "sl_failed": 1, "positions_failed": 57, "positions_opened": 383}	2025-09-16 06:58:19.466397+00
958	main_trader	HEALTHY	t	t	t	\N	383	0	0	\N	{"sl_set": 385, "sl_failed": 1, "positions_failed": 57, "positions_opened": 383}	2025-09-16 06:59:21.339689+00
959	main_trader	HEALTHY	t	t	t	\N	383	0	0	\N	{"sl_set": 385, "sl_failed": 1, "positions_failed": 57, "positions_opened": 383}	2025-09-16 07:00:22.553649+00
960	main_trader	HEALTHY	t	t	t	\N	383	0	0	\N	{"sl_set": 385, "sl_failed": 1, "positions_failed": 57, "positions_opened": 383}	2025-09-16 07:01:23.939642+00
961	main_trader	HEALTHY	t	t	t	\N	383	0	0	\N	{"sl_set": 385, "sl_failed": 1, "positions_failed": 57, "positions_opened": 383}	2025-09-16 07:02:25.021844+00
962	main_trader	HEALTHY	t	t	t	\N	383	0	0	\N	{"sl_set": 385, "sl_failed": 1, "positions_failed": 57, "positions_opened": 383}	2025-09-16 07:03:26.139387+00
963	main_trader	HEALTHY	t	t	t	\N	383	0	0	\N	{"sl_set": 385, "sl_failed": 1, "positions_failed": 57, "positions_opened": 383}	2025-09-16 07:04:27.553573+00
964	main_trader	HEALTHY	t	t	t	\N	383	0	0	\N	{"sl_set": 385, "sl_failed": 1, "positions_failed": 57, "positions_opened": 383}	2025-09-16 07:05:28.701171+00
965	main_trader	HEALTHY	t	t	t	\N	383	0	0	\N	{"sl_set": 385, "sl_failed": 1, "positions_failed": 57, "positions_opened": 383}	2025-09-16 07:06:29.765489+00
966	main_trader	HEALTHY	t	t	t	\N	386	0	0	\N	{"sl_set": 388, "sl_failed": 1, "positions_failed": 57, "positions_opened": 386}	2025-09-16 07:07:30.947442+00
967	main_trader	HEALTHY	t	t	t	\N	386	0	0	\N	{"sl_set": 388, "sl_failed": 1, "positions_failed": 57, "positions_opened": 386}	2025-09-16 07:08:32.005157+00
968	main_trader	HEALTHY	t	t	t	\N	386	0	0	\N	{"sl_set": 388, "sl_failed": 1, "positions_failed": 57, "positions_opened": 386}	2025-09-16 07:09:33.409747+00
969	main_trader	HEALTHY	t	t	t	\N	386	0	0	\N	{"sl_set": 388, "sl_failed": 1, "positions_failed": 57, "positions_opened": 386}	2025-09-16 07:10:34.648936+00
970	main_trader	HEALTHY	t	t	t	\N	386	0	0	\N	{"sl_set": 388, "sl_failed": 1, "positions_failed": 57, "positions_opened": 386}	2025-09-16 07:11:35.702422+00
971	main_trader	HEALTHY	t	t	t	\N	386	0	0	\N	{"sl_set": 388, "sl_failed": 1, "positions_failed": 57, "positions_opened": 386}	2025-09-16 07:12:36.808625+00
972	main_trader	HEALTHY	t	t	t	\N	386	0	0	\N	{"sl_set": 388, "sl_failed": 1, "positions_failed": 57, "positions_opened": 386}	2025-09-16 07:13:38.006371+00
973	main_trader	HEALTHY	t	t	t	\N	386	0	0	\N	{"sl_set": 388, "sl_failed": 1, "positions_failed": 57, "positions_opened": 386}	2025-09-16 07:14:39.773276+00
974	main_trader	HEALTHY	t	t	t	\N	386	0	0	\N	{"sl_set": 388, "sl_failed": 1, "positions_failed": 57, "positions_opened": 386}	2025-09-16 07:15:41.029885+00
975	main_trader	HEALTHY	t	t	t	\N	386	0	0	\N	{"sl_set": 388, "sl_failed": 1, "positions_failed": 57, "positions_opened": 386}	2025-09-16 07:16:42.185895+00
976	main_trader	HEALTHY	t	t	t	\N	386	0	0	\N	{"sl_set": 388, "sl_failed": 1, "positions_failed": 57, "positions_opened": 386}	2025-09-16 07:17:43.35354+00
977	main_trader	HEALTHY	t	t	t	\N	386	0	0	\N	{"sl_set": 388, "sl_failed": 1, "positions_failed": 57, "positions_opened": 386}	2025-09-16 07:18:44.529494+00
978	main_trader	HEALTHY	t	t	t	\N	386	0	0	\N	{"sl_set": 388, "sl_failed": 1, "positions_failed": 57, "positions_opened": 386}	2025-09-16 07:19:45.82044+00
979	main_trader	HEALTHY	t	t	t	\N	389	0	0	\N	{"sl_set": 391, "sl_failed": 1, "positions_failed": 57, "positions_opened": 389}	2025-09-16 07:20:46.962559+00
980	main_trader	HEALTHY	t	t	t	\N	389	0	0	\N	{"sl_set": 391, "sl_failed": 1, "positions_failed": 57, "positions_opened": 389}	2025-09-16 07:21:48.126469+00
981	main_trader	HEALTHY	t	t	t	\N	389	0	0	\N	{"sl_set": 391, "sl_failed": 1, "positions_failed": 57, "positions_opened": 389}	2025-09-16 07:22:49.544384+00
982	main_trader	HEALTHY	t	t	t	\N	389	0	0	\N	{"sl_set": 391, "sl_failed": 1, "positions_failed": 57, "positions_opened": 389}	2025-09-16 07:23:50.712026+00
983	main_trader	HEALTHY	t	t	t	\N	389	0	0	\N	{"sl_set": 391, "sl_failed": 1, "positions_failed": 57, "positions_opened": 389}	2025-09-16 07:24:52.025614+00
984	main_trader	HEALTHY	t	t	t	\N	389	0	0	\N	{"sl_set": 391, "sl_failed": 1, "positions_failed": 57, "positions_opened": 389}	2025-09-16 07:25:53.182084+00
985	main_trader	HEALTHY	t	t	t	\N	389	0	0	\N	{"sl_set": 391, "sl_failed": 1, "positions_failed": 57, "positions_opened": 389}	2025-09-16 07:26:54.286337+00
986	main_trader	HEALTHY	t	t	t	\N	389	0	0	\N	{"sl_set": 391, "sl_failed": 1, "positions_failed": 57, "positions_opened": 389}	2025-09-16 07:27:55.447295+00
987	main_trader	HEALTHY	t	t	t	\N	389	0	0	\N	{"sl_set": 391, "sl_failed": 1, "positions_failed": 57, "positions_opened": 389}	2025-09-16 07:28:56.671589+00
988	main_trader	HEALTHY	t	t	t	\N	389	0	0	\N	{"sl_set": 391, "sl_failed": 1, "positions_failed": 57, "positions_opened": 389}	2025-09-16 07:29:58.069158+00
989	main_trader	HEALTHY	t	t	t	\N	389	0	0	\N	{"sl_set": 391, "sl_failed": 1, "positions_failed": 57, "positions_opened": 389}	2025-09-16 07:30:59.361257+00
990	main_trader	HEALTHY	t	t	t	\N	389	0	0	\N	{"sl_set": 391, "sl_failed": 1, "positions_failed": 57, "positions_opened": 389}	2025-09-16 07:32:00.436119+00
991	main_trader	HEALTHY	t	t	t	\N	389	0	0	\N	{"sl_set": 391, "sl_failed": 1, "positions_failed": 57, "positions_opened": 389}	2025-09-16 07:33:01.604763+00
992	main_trader	HEALTHY	t	t	t	\N	389	0	0	\N	{"sl_set": 391, "sl_failed": 1, "positions_failed": 57, "positions_opened": 389}	2025-09-16 07:34:02.814588+00
993	main_trader	HEALTHY	t	t	t	\N	389	0	0	\N	{"sl_set": 391, "sl_failed": 1, "positions_failed": 57, "positions_opened": 389}	2025-09-16 07:35:04.19831+00
994	main_trader	HEALTHY	t	t	t	\N	392	0	0	\N	{"sl_set": 394, "sl_failed": 2, "positions_failed": 57, "positions_opened": 393}	2025-09-16 07:36:05.175729+00
995	main_trader	HEALTHY	t	t	t	\N	394	0	0	\N	{"sl_set": 395, "sl_failed": 2, "positions_failed": 57, "positions_opened": 394}	2025-09-16 07:37:06.283611+00
996	main_trader	HEALTHY	t	t	t	\N	394	0	0	\N	{"sl_set": 395, "sl_failed": 2, "positions_failed": 57, "positions_opened": 394}	2025-09-16 07:38:07.524574+00
997	main_trader	HEALTHY	t	t	t	\N	394	0	0	\N	{"sl_set": 395, "sl_failed": 2, "positions_failed": 57, "positions_opened": 394}	2025-09-16 07:39:08.708776+00
998	main_trader	HEALTHY	t	t	t	\N	394	0	0	\N	{"sl_set": 395, "sl_failed": 2, "positions_failed": 57, "positions_opened": 394}	2025-09-16 07:40:10.050853+00
999	main_trader	HEALTHY	t	t	t	\N	394	0	0	\N	{"sl_set": 395, "sl_failed": 2, "positions_failed": 57, "positions_opened": 394}	2025-09-16 07:41:11.304954+00
1000	main_trader	HEALTHY	t	t	t	\N	394	0	0	\N	{"sl_set": 395, "sl_failed": 2, "positions_failed": 57, "positions_opened": 394}	2025-09-16 07:42:12.451954+00
1001	main_trader	HEALTHY	t	t	t	\N	394	0	0	\N	{"sl_set": 395, "sl_failed": 2, "positions_failed": 57, "positions_opened": 394}	2025-09-16 07:43:13.626989+00
1002	main_trader	HEALTHY	t	t	t	\N	394	0	0	\N	{"sl_set": 395, "sl_failed": 2, "positions_failed": 57, "positions_opened": 394}	2025-09-16 07:44:14.74231+00
1003	main_trader	HEALTHY	t	t	t	\N	394	0	0	\N	{"sl_set": 395, "sl_failed": 2, "positions_failed": 57, "positions_opened": 394}	2025-09-16 07:45:16.528811+00
1004	main_trader	HEALTHY	t	t	t	\N	394	0	0	\N	{"sl_set": 395, "sl_failed": 2, "positions_failed": 57, "positions_opened": 394}	2025-09-16 07:46:17.70443+00
1005	main_trader	HEALTHY	t	t	t	\N	394	0	0	\N	{"sl_set": 395, "sl_failed": 2, "positions_failed": 57, "positions_opened": 394}	2025-09-16 07:47:18.80427+00
1006	main_trader	HEALTHY	t	t	t	\N	394	0	0	\N	{"sl_set": 395, "sl_failed": 2, "positions_failed": 57, "positions_opened": 394}	2025-09-16 07:48:19.907006+00
1007	main_trader	HEALTHY	t	t	t	\N	394	0	0	\N	{"sl_set": 395, "sl_failed": 2, "positions_failed": 57, "positions_opened": 394}	2025-09-16 07:49:21.320959+00
1008	main_trader	HEALTHY	t	t	t	\N	394	0	0	\N	{"sl_set": 395, "sl_failed": 2, "positions_failed": 57, "positions_opened": 394}	2025-09-16 07:50:22.608613+00
1009	main_trader	HEALTHY	t	t	t	\N	397	0	0	\N	{"sl_set": 397, "sl_failed": 3, "positions_failed": 58, "positions_opened": 397}	2025-09-16 07:51:23.5881+00
1010	main_trader	HEALTHY	t	t	t	\N	397	0	0	\N	{"sl_set": 397, "sl_failed": 3, "positions_failed": 58, "positions_opened": 397}	2025-09-16 07:52:24.700617+00
1011	main_trader	HEALTHY	t	t	t	\N	397	0	0	\N	{"sl_set": 397, "sl_failed": 3, "positions_failed": 58, "positions_opened": 397}	2025-09-16 07:53:25.905185+00
1012	main_trader	HEALTHY	t	t	t	\N	397	0	0	\N	{"sl_set": 397, "sl_failed": 3, "positions_failed": 58, "positions_opened": 397}	2025-09-16 07:54:27.54464+00
1013	main_trader	HEALTHY	t	t	t	\N	397	0	0	\N	{"sl_set": 397, "sl_failed": 3, "positions_failed": 58, "positions_opened": 397}	2025-09-16 07:55:29.327064+00
1014	main_trader	HEALTHY	t	t	t	\N	397	0	0	\N	{"sl_set": 397, "sl_failed": 3, "positions_failed": 58, "positions_opened": 397}	2025-09-16 07:56:30.39793+00
1015	main_trader	HEALTHY	t	t	t	\N	397	0	0	\N	{"sl_set": 397, "sl_failed": 3, "positions_failed": 58, "positions_opened": 397}	2025-09-16 07:57:31.492077+00
1016	main_trader	HEALTHY	t	t	t	\N	397	0	0	\N	{"sl_set": 397, "sl_failed": 3, "positions_failed": 58, "positions_opened": 397}	2025-09-16 07:58:32.64826+00
1017	main_trader	HEALTHY	t	t	t	\N	397	0	0	\N	{"sl_set": 397, "sl_failed": 3, "positions_failed": 58, "positions_opened": 397}	2025-09-16 07:59:33.807311+00
1018	main_trader	HEALTHY	t	t	t	\N	397	0	0	\N	{"sl_set": 397, "sl_failed": 3, "positions_failed": 58, "positions_opened": 397}	2025-09-16 08:00:35.206819+00
1019	main_trader	HEALTHY	t	t	t	\N	397	0	0	\N	{"sl_set": 397, "sl_failed": 3, "positions_failed": 58, "positions_opened": 397}	2025-09-16 08:01:37.675604+00
1020	main_trader	HEALTHY	t	t	t	\N	397	0	0	\N	{"sl_set": 397, "sl_failed": 3, "positions_failed": 58, "positions_opened": 397}	2025-09-16 08:02:38.833726+00
1021	main_trader	HEALTHY	t	t	t	\N	397	0	0	\N	{"sl_set": 397, "sl_failed": 3, "positions_failed": 58, "positions_opened": 397}	2025-09-16 08:03:39.989808+00
1022	main_trader	HEALTHY	t	t	t	\N	397	0	0	\N	{"sl_set": 397, "sl_failed": 3, "positions_failed": 58, "positions_opened": 397}	2025-09-16 08:04:41.07974+00
1023	main_trader	HEALTHY	t	t	t	\N	397	0	0	\N	{"sl_set": 397, "sl_failed": 3, "positions_failed": 58, "positions_opened": 397}	2025-09-16 08:05:42.469632+00
1024	main_trader	HEALTHY	t	t	t	\N	398	0	0	\N	{"sl_set": 399, "sl_failed": 3, "positions_failed": 58, "positions_opened": 399}	2025-09-16 08:06:43.434273+00
1025	main_trader	HEALTHY	t	t	t	\N	401	0	0	\N	{"sl_set": 401, "sl_failed": 3, "positions_failed": 58, "positions_opened": 401}	2025-09-16 08:07:44.509389+00
1026	main_trader	HEALTHY	t	t	t	\N	401	0	0	\N	{"sl_set": 401, "sl_failed": 3, "positions_failed": 58, "positions_opened": 401}	2025-09-16 08:08:45.665404+00
1027	main_trader	HEALTHY	t	t	t	\N	401	0	0	\N	{"sl_set": 401, "sl_failed": 3, "positions_failed": 58, "positions_opened": 401}	2025-09-16 08:09:46.829192+00
1028	main_trader	HEALTHY	t	t	t	\N	401	0	0	\N	{"sl_set": 401, "sl_failed": 3, "positions_failed": 58, "positions_opened": 401}	2025-09-16 08:10:48.142323+00
1029	main_trader	HEALTHY	t	t	t	\N	401	0	0	\N	{"sl_set": 401, "sl_failed": 3, "positions_failed": 58, "positions_opened": 401}	2025-09-16 08:11:49.381326+00
1030	main_trader	HEALTHY	t	t	t	\N	401	0	0	\N	{"sl_set": 401, "sl_failed": 3, "positions_failed": 58, "positions_opened": 401}	2025-09-16 08:12:50.553728+00
1031	main_trader	HEALTHY	t	t	t	\N	401	0	0	\N	{"sl_set": 401, "sl_failed": 3, "positions_failed": 58, "positions_opened": 401}	2025-09-16 08:13:51.763095+00
1032	main_trader	HEALTHY	t	t	t	\N	401	0	0	\N	{"sl_set": 401, "sl_failed": 3, "positions_failed": 58, "positions_opened": 401}	2025-09-16 08:14:52.935477+00
1033	main_trader	HEALTHY	t	t	t	\N	401	0	0	\N	{"sl_set": 401, "sl_failed": 3, "positions_failed": 58, "positions_opened": 401}	2025-09-16 08:15:54.709303+00
1034	main_trader	HEALTHY	t	t	t	\N	401	0	0	\N	{"sl_set": 401, "sl_failed": 3, "positions_failed": 58, "positions_opened": 401}	2025-09-16 08:16:55.944483+00
1035	main_trader	HEALTHY	t	t	t	\N	401	0	0	\N	{"sl_set": 401, "sl_failed": 3, "positions_failed": 58, "positions_opened": 401}	2025-09-16 08:17:57.102973+00
1036	main_trader	HEALTHY	t	t	t	\N	401	0	0	\N	{"sl_set": 401, "sl_failed": 3, "positions_failed": 58, "positions_opened": 401}	2025-09-16 08:18:58.279633+00
1037	main_trader	HEALTHY	t	t	t	\N	401	0	0	\N	{"sl_set": 401, "sl_failed": 3, "positions_failed": 58, "positions_opened": 401}	2025-09-16 08:19:59.445553+00
1038	main_trader	HEALTHY	t	t	t	\N	405	0	0	\N	{"sl_set": 406, "sl_failed": 3, "positions_failed": 58, "positions_opened": 406}	2025-09-16 08:21:00.879891+00
1039	main_trader	HEALTHY	t	t	t	\N	411	0	0	\N	{"sl_set": 412, "sl_failed": 3, "positions_failed": 58, "positions_opened": 412}	2025-09-16 08:22:01.849557+00
1040	main_trader	HEALTHY	t	t	t	\N	413	0	0	\N	{"sl_set": 413, "sl_failed": 3, "positions_failed": 58, "positions_opened": 413}	2025-09-16 08:23:03.121192+00
1041	main_trader	HEALTHY	t	t	t	\N	413	0	0	\N	{"sl_set": 413, "sl_failed": 3, "positions_failed": 58, "positions_opened": 413}	2025-09-16 08:24:04.399155+00
1042	main_trader	HEALTHY	t	t	t	\N	413	0	0	\N	{"sl_set": 413, "sl_failed": 3, "positions_failed": 58, "positions_opened": 413}	2025-09-16 08:25:05.781211+00
1043	main_trader	HEALTHY	t	t	t	\N	413	0	0	\N	{"sl_set": 413, "sl_failed": 3, "positions_failed": 58, "positions_opened": 413}	2025-09-16 08:26:06.944945+00
1044	main_trader	HEALTHY	t	t	t	\N	413	0	0	\N	{"sl_set": 413, "sl_failed": 3, "positions_failed": 58, "positions_opened": 413}	2025-09-16 08:27:08.027358+00
1045	main_trader	HEALTHY	t	t	t	\N	413	0	0	\N	{"sl_set": 413, "sl_failed": 3, "positions_failed": 58, "positions_opened": 413}	2025-09-16 08:28:09.430669+00
1046	main_trader	HEALTHY	t	t	t	\N	413	0	0	\N	{"sl_set": 413, "sl_failed": 3, "positions_failed": 58, "positions_opened": 413}	2025-09-16 08:29:10.696559+00
1047	main_trader	HEALTHY	t	t	t	\N	413	0	0	\N	{"sl_set": 413, "sl_failed": 3, "positions_failed": 58, "positions_opened": 413}	2025-09-16 08:30:11.782558+00
1048	main_trader	HEALTHY	t	t	t	\N	413	0	0	\N	{"sl_set": 413, "sl_failed": 3, "positions_failed": 58, "positions_opened": 413}	2025-09-16 08:31:12.941439+00
1049	main_trader	HEALTHY	t	t	t	\N	413	0	0	\N	{"sl_set": 413, "sl_failed": 3, "positions_failed": 58, "positions_opened": 413}	2025-09-16 08:32:14.004999+00
1050	main_trader	HEALTHY	t	t	t	\N	413	0	0	\N	{"sl_set": 413, "sl_failed": 3, "positions_failed": 58, "positions_opened": 413}	2025-09-16 08:33:15.397001+00
1051	main_trader	HEALTHY	t	t	t	\N	413	0	0	\N	{"sl_set": 413, "sl_failed": 3, "positions_failed": 58, "positions_opened": 413}	2025-09-16 08:34:16.595124+00
1052	main_trader	HEALTHY	t	t	t	\N	413	0	0	\N	{"sl_set": 413, "sl_failed": 3, "positions_failed": 58, "positions_opened": 413}	2025-09-16 08:35:17.646886+00
1053	main_trader	HEALTHY	t	t	t	\N	417	0	0	\N	{"sl_set": 417, "sl_failed": 3, "positions_failed": 59, "positions_opened": 417}	2025-09-16 08:36:18.807064+00
1054	main_trader	HEALTHY	t	t	t	\N	417	0	0	\N	{"sl_set": 417, "sl_failed": 3, "positions_failed": 61, "positions_opened": 417}	2025-09-16 08:37:19.98981+00
1055	main_trader	HEALTHY	t	t	t	\N	417	0	0	\N	{"sl_set": 417, "sl_failed": 3, "positions_failed": 61, "positions_opened": 417}	2025-09-16 08:38:21.395069+00
1056	main_trader	HEALTHY	t	t	t	\N	417	0	0	\N	{"sl_set": 417, "sl_failed": 3, "positions_failed": 61, "positions_opened": 417}	2025-09-16 08:39:22.662071+00
1057	main_trader	HEALTHY	t	t	t	\N	417	0	0	\N	{"sl_set": 417, "sl_failed": 3, "positions_failed": 61, "positions_opened": 417}	2025-09-16 08:40:23.774022+00
1058	main_trader	HEALTHY	t	t	t	\N	417	0	0	\N	{"sl_set": 417, "sl_failed": 3, "positions_failed": 61, "positions_opened": 417}	2025-09-16 08:41:24.958381+00
1059	main_trader	HEALTHY	t	t	t	\N	417	0	0	\N	{"sl_set": 417, "sl_failed": 3, "positions_failed": 61, "positions_opened": 417}	2025-09-16 08:42:26.389248+00
1060	main_trader	HEALTHY	t	t	t	\N	417	0	0	\N	{"sl_set": 417, "sl_failed": 3, "positions_failed": 61, "positions_opened": 417}	2025-09-16 08:43:27.687321+00
1061	main_trader	HEALTHY	t	t	t	\N	417	0	0	\N	{"sl_set": 417, "sl_failed": 3, "positions_failed": 61, "positions_opened": 417}	2025-09-16 08:44:29.127067+00
1062	main_trader	HEALTHY	t	t	t	\N	417	0	0	\N	{"sl_set": 417, "sl_failed": 3, "positions_failed": 61, "positions_opened": 417}	2025-09-16 08:45:30.28114+00
1063	main_trader	HEALTHY	t	t	t	\N	417	0	0	\N	{"sl_set": 417, "sl_failed": 3, "positions_failed": 61, "positions_opened": 417}	2025-09-16 08:46:31.343048+00
1064	main_trader	HEALTHY	t	t	t	\N	417	0	0	\N	{"sl_set": 417, "sl_failed": 3, "positions_failed": 61, "positions_opened": 417}	2025-09-16 08:47:32.528194+00
1065	main_trader	HEALTHY	t	t	t	\N	417	0	0	\N	{"sl_set": 417, "sl_failed": 3, "positions_failed": 61, "positions_opened": 417}	2025-09-16 08:48:33.822503+00
1066	main_trader	HEALTHY	t	t	t	\N	417	0	0	\N	{"sl_set": 417, "sl_failed": 3, "positions_failed": 61, "positions_opened": 417}	2025-09-16 08:49:35.098832+00
1067	main_trader	HEALTHY	t	t	t	\N	417	0	0	\N	{"sl_set": 417, "sl_failed": 3, "positions_failed": 61, "positions_opened": 417}	2025-09-16 08:50:36.274005+00
1068	main_trader	HEALTHY	t	t	t	\N	419	0	0	\N	{"sl_set": 419, "sl_failed": 3, "positions_failed": 62, "positions_opened": 419}	2025-09-16 08:51:37.339337+00
1069	main_trader	HEALTHY	t	t	t	\N	421	0	0	\N	{"sl_set": 421, "sl_failed": 3, "positions_failed": 64, "positions_opened": 421}	2025-09-16 08:52:38.519749+00
1070	main_trader	HEALTHY	t	t	t	\N	421	0	0	\N	{"sl_set": 421, "sl_failed": 3, "positions_failed": 64, "positions_opened": 421}	2025-09-16 08:53:39.938163+00
1071	main_trader	HEALTHY	t	t	t	\N	421	0	0	\N	{"sl_set": 421, "sl_failed": 3, "positions_failed": 64, "positions_opened": 421}	2025-09-16 08:54:41.089482+00
1072	main_trader	HEALTHY	t	t	t	\N	421	0	0	\N	{"sl_set": 421, "sl_failed": 3, "positions_failed": 64, "positions_opened": 421}	2025-09-16 08:55:42.956928+00
1073	main_trader	HEALTHY	t	t	t	\N	421	0	0	\N	{"sl_set": 421, "sl_failed": 3, "positions_failed": 64, "positions_opened": 421}	2025-09-16 08:56:44.11317+00
1074	main_trader	HEALTHY	t	t	t	\N	421	0	0	\N	{"sl_set": 421, "sl_failed": 3, "positions_failed": 64, "positions_opened": 421}	2025-09-16 08:57:45.634398+00
1075	main_trader	HEALTHY	t	t	t	\N	421	0	0	\N	{"sl_set": 421, "sl_failed": 3, "positions_failed": 64, "positions_opened": 421}	2025-09-16 08:58:46.803731+00
1076	main_trader	HEALTHY	t	t	t	\N	421	0	0	\N	{"sl_set": 421, "sl_failed": 3, "positions_failed": 64, "positions_opened": 421}	2025-09-16 08:59:47.961138+00
1077	main_trader	HEALTHY	t	t	t	\N	421	0	0	\N	{"sl_set": 421, "sl_failed": 3, "positions_failed": 64, "positions_opened": 421}	2025-09-16 09:00:49.390689+00
1078	main_trader	HEALTHY	t	t	t	\N	421	0	0	\N	{"sl_set": 421, "sl_failed": 3, "positions_failed": 64, "positions_opened": 421}	2025-09-16 09:01:50.689583+00
1079	main_trader	HEALTHY	t	t	t	\N	421	0	0	\N	{"sl_set": 421, "sl_failed": 3, "positions_failed": 64, "positions_opened": 421}	2025-09-16 09:02:51.746313+00
1080	main_trader	HEALTHY	t	t	t	\N	421	0	0	\N	{"sl_set": 421, "sl_failed": 3, "positions_failed": 64, "positions_opened": 421}	2025-09-16 09:03:52.922801+00
1081	main_trader	HEALTHY	t	t	t	\N	421	0	0	\N	{"sl_set": 421, "sl_failed": 3, "positions_failed": 64, "positions_opened": 421}	2025-09-16 09:04:53.992687+00
1082	main_trader	HEALTHY	t	t	t	\N	421	0	0	\N	{"sl_set": 421, "sl_failed": 3, "positions_failed": 64, "positions_opened": 421}	2025-09-16 09:05:55.401327+00
1083	main_trader	HEALTHY	t	t	t	\N	425	0	0	\N	{"sl_set": 425, "sl_failed": 3, "positions_failed": 64, "positions_opened": 425}	2025-09-16 09:06:57.043596+00
1084	main_trader	HEALTHY	t	t	t	\N	426	0	0	\N	{"sl_set": 426, "sl_failed": 3, "positions_failed": 64, "positions_opened": 426}	2025-09-16 09:07:58.21595+00
1085	main_trader	HEALTHY	t	t	t	\N	426	0	0	\N	{"sl_set": 426, "sl_failed": 3, "positions_failed": 64, "positions_opened": 426}	2025-09-16 09:08:59.33242+00
1086	main_trader	HEALTHY	t	t	t	\N	426	0	0	\N	{"sl_set": 426, "sl_failed": 3, "positions_failed": 64, "positions_opened": 426}	2025-09-16 09:10:00.822667+00
1087	main_trader	HEALTHY	t	t	t	\N	426	0	0	\N	{"sl_set": 426, "sl_failed": 3, "positions_failed": 64, "positions_opened": 426}	2025-09-16 09:11:02.215377+00
1088	main_trader	HEALTHY	t	t	t	\N	426	0	0	\N	{"sl_set": 426, "sl_failed": 3, "positions_failed": 64, "positions_opened": 426}	2025-09-16 09:12:03.480009+00
1089	main_trader	HEALTHY	t	t	t	\N	426	0	0	\N	{"sl_set": 426, "sl_failed": 3, "positions_failed": 64, "positions_opened": 426}	2025-09-16 09:13:04.550557+00
1090	main_trader	HEALTHY	t	t	t	\N	426	0	0	\N	{"sl_set": 426, "sl_failed": 3, "positions_failed": 64, "positions_opened": 426}	2025-09-16 09:14:05.709656+00
1091	main_trader	HEALTHY	t	t	t	\N	426	0	0	\N	{"sl_set": 426, "sl_failed": 3, "positions_failed": 64, "positions_opened": 426}	2025-09-16 09:15:06.865174+00
1092	main_trader	HEALTHY	t	t	t	\N	426	0	0	\N	{"sl_set": 426, "sl_failed": 3, "positions_failed": 64, "positions_opened": 426}	2025-09-16 09:16:08.254901+00
1093	main_trader	HEALTHY	t	t	t	\N	426	0	0	\N	{"sl_set": 426, "sl_failed": 3, "positions_failed": 64, "positions_opened": 426}	2025-09-16 09:17:09.500457+00
1094	main_trader	HEALTHY	t	t	t	\N	426	0	0	\N	{"sl_set": 426, "sl_failed": 3, "positions_failed": 64, "positions_opened": 426}	2025-09-16 09:18:10.674668+00
1095	main_trader	HEALTHY	t	t	t	\N	426	0	0	\N	{"sl_set": 426, "sl_failed": 3, "positions_failed": 64, "positions_opened": 426}	2025-09-16 09:19:11.749885+00
1096	main_trader	HEALTHY	t	t	t	\N	426	0	0	\N	{"sl_set": 426, "sl_failed": 3, "positions_failed": 64, "positions_opened": 426}	2025-09-16 09:20:12.909566+00
1097	main_trader	HEALTHY	t	t	t	\N	429	0	0	\N	{"sl_set": 429, "sl_failed": 3, "positions_failed": 65, "positions_opened": 429}	2025-09-16 09:21:14.213413+00
1098	main_trader	HEALTHY	t	t	t	\N	429	0	0	\N	{"sl_set": 429, "sl_failed": 3, "positions_failed": 65, "positions_opened": 429}	2025-09-16 09:22:15.368735+00
1099	main_trader	HEALTHY	t	t	t	\N	429	0	0	\N	{"sl_set": 429, "sl_failed": 3, "positions_failed": 65, "positions_opened": 429}	2025-09-16 09:23:16.426395+00
1100	main_trader	HEALTHY	t	t	t	\N	429	0	0	\N	{"sl_set": 429, "sl_failed": 3, "positions_failed": 65, "positions_opened": 429}	2025-09-16 09:24:17.592179+00
1101	main_trader	HEALTHY	t	t	t	\N	429	0	0	\N	{"sl_set": 429, "sl_failed": 3, "positions_failed": 65, "positions_opened": 429}	2025-09-16 09:25:18.662379+00
1102	main_trader	HEALTHY	t	t	t	\N	429	0	0	\N	{"sl_set": 429, "sl_failed": 3, "positions_failed": 65, "positions_opened": 429}	2025-09-16 09:26:20.539814+00
1103	main_trader	HEALTHY	t	t	t	\N	429	0	0	\N	{"sl_set": 429, "sl_failed": 3, "positions_failed": 65, "positions_opened": 429}	2025-09-16 09:27:21.696034+00
1104	main_trader	HEALTHY	t	t	t	\N	429	0	0	\N	{"sl_set": 429, "sl_failed": 3, "positions_failed": 65, "positions_opened": 429}	2025-09-16 09:28:22.868597+00
1105	main_trader	HEALTHY	t	t	t	\N	429	0	0	\N	{"sl_set": 429, "sl_failed": 3, "positions_failed": 65, "positions_opened": 429}	2025-09-16 09:29:24.037126+00
1106	main_trader	HEALTHY	t	t	t	\N	429	0	0	\N	{"sl_set": 429, "sl_failed": 3, "positions_failed": 65, "positions_opened": 429}	2025-09-16 09:30:25.192935+00
1107	main_trader	HEALTHY	t	t	t	\N	429	0	0	\N	{"sl_set": 429, "sl_failed": 3, "positions_failed": 65, "positions_opened": 429}	2025-09-16 09:31:26.606849+00
1108	main_trader	HEALTHY	t	t	t	\N	429	0	0	\N	{"sl_set": 429, "sl_failed": 3, "positions_failed": 65, "positions_opened": 429}	2025-09-16 09:32:27.880954+00
1109	main_trader	HEALTHY	t	t	t	\N	429	0	0	\N	{"sl_set": 429, "sl_failed": 3, "positions_failed": 65, "positions_opened": 429}	2025-09-16 09:33:29.131569+00
1110	main_trader	HEALTHY	t	t	t	\N	429	0	0	\N	{"sl_set": 429, "sl_failed": 3, "positions_failed": 65, "positions_opened": 429}	2025-09-16 09:34:30.382794+00
1111	main_trader	HEALTHY	t	t	t	\N	429	0	0	\N	{"sl_set": 429, "sl_failed": 3, "positions_failed": 65, "positions_opened": 429}	2025-09-16 09:35:31.567959+00
1112	main_trader	HEALTHY	t	t	t	\N	433	0	0	\N	{"sl_set": 433, "sl_failed": 3, "positions_failed": 65, "positions_opened": 433}	2025-09-16 09:36:32.633796+00
1113	main_trader	HEALTHY	t	t	t	\N	433	0	0	\N	{"sl_set": 433, "sl_failed": 3, "positions_failed": 65, "positions_opened": 433}	2025-09-16 09:37:33.692089+00
1114	main_trader	HEALTHY	t	t	t	\N	433	0	0	\N	{"sl_set": 433, "sl_failed": 3, "positions_failed": 65, "positions_opened": 433}	2025-09-16 09:38:35.09939+00
1115	main_trader	HEALTHY	t	t	t	\N	433	0	0	\N	{"sl_set": 433, "sl_failed": 3, "positions_failed": 65, "positions_opened": 433}	2025-09-16 09:39:36.359956+00
1116	main_trader	HEALTHY	t	t	t	\N	433	0	0	\N	{"sl_set": 433, "sl_failed": 3, "positions_failed": 65, "positions_opened": 433}	2025-09-16 09:40:37.530544+00
1117	main_trader	HEALTHY	t	t	t	\N	433	0	0	\N	{"sl_set": 433, "sl_failed": 3, "positions_failed": 65, "positions_opened": 433}	2025-09-16 09:41:38.701572+00
1118	main_trader	HEALTHY	t	t	t	\N	433	0	0	\N	{"sl_set": 433, "sl_failed": 3, "positions_failed": 65, "positions_opened": 433}	2025-09-16 09:42:40.406587+00
1119	main_trader	HEALTHY	t	t	t	\N	433	0	0	\N	{"sl_set": 433, "sl_failed": 3, "positions_failed": 65, "positions_opened": 433}	2025-09-16 09:43:41.717334+00
1120	main_trader	HEALTHY	t	t	t	\N	433	0	0	\N	{"sl_set": 433, "sl_failed": 3, "positions_failed": 65, "positions_opened": 433}	2025-09-16 09:44:43.002284+00
1121	main_trader	HEALTHY	t	t	t	\N	433	0	0	\N	{"sl_set": 433, "sl_failed": 3, "positions_failed": 65, "positions_opened": 433}	2025-09-16 09:45:44.086375+00
1122	main_trader	HEALTHY	t	t	t	\N	433	0	0	\N	{"sl_set": 433, "sl_failed": 3, "positions_failed": 65, "positions_opened": 433}	2025-09-16 09:46:45.18608+00
1123	main_trader	HEALTHY	t	t	t	\N	433	0	0	\N	{"sl_set": 433, "sl_failed": 3, "positions_failed": 65, "positions_opened": 433}	2025-09-16 09:47:46.255343+00
1124	main_trader	HEALTHY	t	t	t	\N	433	0	0	\N	{"sl_set": 433, "sl_failed": 3, "positions_failed": 65, "positions_opened": 433}	2025-09-16 09:48:47.642962+00
1125	main_trader	HEALTHY	t	t	t	\N	433	0	0	\N	{"sl_set": 433, "sl_failed": 3, "positions_failed": 65, "positions_opened": 433}	2025-09-16 09:49:48.869788+00
1126	main_trader	HEALTHY	t	t	t	\N	435	0	0	\N	{"sl_set": 435, "sl_failed": 3, "positions_failed": 65, "positions_opened": 435}	2025-09-16 09:50:49.774948+00
1127	main_trader	HEALTHY	t	t	t	\N	438	0	0	\N	{"sl_set": 438, "sl_failed": 3, "positions_failed": 67, "positions_opened": 438}	2025-09-16 09:51:50.890264+00
1128	main_trader	HEALTHY	t	t	t	\N	438	0	0	\N	{"sl_set": 438, "sl_failed": 3, "positions_failed": 67, "positions_opened": 438}	2025-09-16 09:52:52.099247+00
1129	main_trader	HEALTHY	t	t	t	\N	438	0	0	\N	{"sl_set": 438, "sl_failed": 3, "positions_failed": 67, "positions_opened": 438}	2025-09-16 09:53:53.485463+00
1130	main_trader	HEALTHY	t	t	t	\N	438	0	0	\N	{"sl_set": 438, "sl_failed": 3, "positions_failed": 67, "positions_opened": 438}	2025-09-16 09:54:54.671603+00
1131	main_trader	HEALTHY	t	t	t	\N	438	0	0	\N	{"sl_set": 438, "sl_failed": 3, "positions_failed": 67, "positions_opened": 438}	2025-09-16 09:55:55.910932+00
1132	main_trader	HEALTHY	t	t	t	\N	438	0	0	\N	{"sl_set": 438, "sl_failed": 3, "positions_failed": 67, "positions_opened": 438}	2025-09-16 09:56:56.991765+00
1133	main_trader	HEALTHY	t	t	t	\N	438	0	0	\N	{"sl_set": 438, "sl_failed": 3, "positions_failed": 67, "positions_opened": 438}	2025-09-16 09:57:58.06694+00
1134	main_trader	HEALTHY	t	t	t	\N	438	0	0	\N	{"sl_set": 438, "sl_failed": 3, "positions_failed": 67, "positions_opened": 438}	2025-09-16 09:58:59.467625+00
1135	main_trader	HEALTHY	t	t	t	\N	438	0	0	\N	{"sl_set": 438, "sl_failed": 3, "positions_failed": 67, "positions_opened": 438}	2025-09-16 10:00:00.713421+00
1136	main_trader	HEALTHY	t	t	t	\N	438	0	0	\N	{"sl_set": 438, "sl_failed": 3, "positions_failed": 67, "positions_opened": 438}	2025-09-16 10:01:01.846534+00
1137	main_trader	HEALTHY	t	t	t	\N	438	0	0	\N	{"sl_set": 438, "sl_failed": 3, "positions_failed": 67, "positions_opened": 438}	2025-09-16 10:02:03.035307+00
1138	main_trader	HEALTHY	t	t	t	\N	438	0	0	\N	{"sl_set": 438, "sl_failed": 3, "positions_failed": 67, "positions_opened": 438}	2025-09-16 10:03:04.128949+00
1139	main_trader	HEALTHY	t	t	t	\N	438	0	0	\N	{"sl_set": 438, "sl_failed": 3, "positions_failed": 67, "positions_opened": 438}	2025-09-16 10:04:05.803272+00
1140	main_trader	HEALTHY	t	t	t	\N	438	0	0	\N	{"sl_set": 438, "sl_failed": 3, "positions_failed": 67, "positions_opened": 438}	2025-09-16 10:05:06.943624+00
1141	main_trader	HEALTHY	t	t	t	\N	438	0	0	\N	{"sl_set": 438, "sl_failed": 3, "positions_failed": 67, "positions_opened": 438}	2025-09-16 10:06:08.005304+00
1142	main_trader	HEALTHY	t	t	t	\N	438	0	0	\N	{"sl_set": 438, "sl_failed": 3, "positions_failed": 67, "positions_opened": 438}	2025-09-16 10:07:09.18006+00
1143	main_trader	HEALTHY	t	t	t	\N	438	0	0	\N	{"sl_set": 438, "sl_failed": 3, "positions_failed": 67, "positions_opened": 438}	2025-09-16 10:08:10.388443+00
1144	main_trader	HEALTHY	t	t	t	\N	438	0	0	\N	{"sl_set": 438, "sl_failed": 3, "positions_failed": 67, "positions_opened": 438}	2025-09-16 10:09:11.679885+00
1145	main_trader	HEALTHY	t	t	t	\N	438	0	0	\N	{"sl_set": 438, "sl_failed": 3, "positions_failed": 67, "positions_opened": 438}	2025-09-16 10:10:12.921178+00
1146	main_trader	HEALTHY	t	t	t	\N	438	0	0	\N	{"sl_set": 438, "sl_failed": 3, "positions_failed": 67, "positions_opened": 438}	2025-09-16 10:11:13.98669+00
1147	main_trader	HEALTHY	t	t	t	\N	438	0	0	\N	{"sl_set": 438, "sl_failed": 3, "positions_failed": 67, "positions_opened": 438}	2025-09-16 10:12:15.107775+00
1148	main_trader	HEALTHY	t	t	t	\N	438	0	0	\N	{"sl_set": 438, "sl_failed": 3, "positions_failed": 67, "positions_opened": 438}	2025-09-16 10:13:16.326773+00
1149	main_trader	HEALTHY	t	t	t	\N	438	0	0	\N	{"sl_set": 438, "sl_failed": 3, "positions_failed": 67, "positions_opened": 438}	2025-09-16 10:14:17.64211+00
1150	main_trader	HEALTHY	t	t	t	\N	438	0	0	\N	{"sl_set": 438, "sl_failed": 3, "positions_failed": 67, "positions_opened": 438}	2025-09-16 10:15:18.787102+00
1151	main_trader	HEALTHY	t	t	t	\N	438	0	0	\N	{"sl_set": 438, "sl_failed": 3, "positions_failed": 67, "positions_opened": 438}	2025-09-16 10:16:19.974758+00
1152	main_trader	HEALTHY	t	t	t	\N	438	0	0	\N	{"sl_set": 438, "sl_failed": 3, "positions_failed": 67, "positions_opened": 438}	2025-09-16 10:17:21.14301+00
1153	main_trader	HEALTHY	t	t	t	\N	438	0	0	\N	{"sl_set": 438, "sl_failed": 3, "positions_failed": 67, "positions_opened": 438}	2025-09-16 10:18:22.302252+00
1154	main_trader	HEALTHY	t	t	t	\N	438	0	0	\N	{"sl_set": 438, "sl_failed": 3, "positions_failed": 67, "positions_opened": 438}	2025-09-16 10:19:23.707161+00
1155	main_trader	HEALTHY	t	t	t	\N	438	0	0	\N	{"sl_set": 439, "sl_failed": 3, "positions_failed": 67, "positions_opened": 439}	2025-09-16 10:20:25.515077+00
1156	main_trader	HEALTHY	t	t	t	\N	439	0	0	\N	{"sl_set": 439, "sl_failed": 3, "positions_failed": 69, "positions_opened": 439}	2025-09-16 10:21:26.797908+00
1157	main_trader	HEALTHY	t	t	t	\N	439	0	0	\N	{"sl_set": 439, "sl_failed": 3, "positions_failed": 69, "positions_opened": 439}	2025-09-16 10:22:27.908257+00
1158	main_trader	HEALTHY	t	t	t	\N	439	0	0	\N	{"sl_set": 439, "sl_failed": 3, "positions_failed": 69, "positions_opened": 439}	2025-09-16 10:23:29.155817+00
1159	main_trader	HEALTHY	t	t	t	\N	439	0	0	\N	{"sl_set": 439, "sl_failed": 3, "positions_failed": 69, "positions_opened": 439}	2025-09-16 10:24:30.352597+00
1160	main_trader	HEALTHY	t	t	t	\N	439	0	0	\N	{"sl_set": 439, "sl_failed": 3, "positions_failed": 69, "positions_opened": 439}	2025-09-16 10:25:31.974641+00
1161	main_trader	HEALTHY	t	t	t	\N	439	0	0	\N	{"sl_set": 439, "sl_failed": 3, "positions_failed": 69, "positions_opened": 439}	2025-09-16 10:26:33.238341+00
1162	main_trader	HEALTHY	t	t	t	\N	439	0	0	\N	{"sl_set": 439, "sl_failed": 3, "positions_failed": 69, "positions_opened": 439}	2025-09-16 10:27:34.308126+00
1163	main_trader	HEALTHY	t	t	t	\N	439	0	0	\N	{"sl_set": 439, "sl_failed": 3, "positions_failed": 69, "positions_opened": 439}	2025-09-16 10:28:35.500888+00
1164	main_trader	HEALTHY	t	t	t	\N	439	0	0	\N	{"sl_set": 439, "sl_failed": 3, "positions_failed": 69, "positions_opened": 439}	2025-09-16 10:29:36.699543+00
1165	main_trader	HEALTHY	t	t	t	\N	439	0	0	\N	{"sl_set": 439, "sl_failed": 3, "positions_failed": 69, "positions_opened": 439}	2025-09-16 10:30:38.038615+00
1166	main_trader	HEALTHY	t	t	t	\N	439	0	0	\N	{"sl_set": 439, "sl_failed": 3, "positions_failed": 69, "positions_opened": 439}	2025-09-16 10:31:39.305316+00
1167	main_trader	HEALTHY	t	t	t	\N	439	0	0	\N	{"sl_set": 439, "sl_failed": 3, "positions_failed": 69, "positions_opened": 439}	2025-09-16 10:32:40.50355+00
1168	main_trader	HEALTHY	t	t	t	\N	439	0	0	\N	{"sl_set": 439, "sl_failed": 3, "positions_failed": 69, "positions_opened": 439}	2025-09-16 10:33:41.66956+00
1169	main_trader	HEALTHY	t	t	t	\N	439	0	0	\N	{"sl_set": 439, "sl_failed": 3, "positions_failed": 69, "positions_opened": 439}	2025-09-16 10:34:42.836191+00
1170	main_trader	HEALTHY	t	t	t	\N	440	0	0	\N	{"sl_set": 440, "sl_failed": 3, "positions_failed": 69, "positions_opened": 440}	2025-09-16 10:35:43.966962+00
1171	main_trader	HEALTHY	t	t	t	\N	440	0	0	\N	{"sl_set": 440, "sl_failed": 3, "positions_failed": 69, "positions_opened": 440}	2025-09-16 10:36:45.119742+00
1172	main_trader	HEALTHY	t	t	t	\N	440	0	0	\N	{"sl_set": 440, "sl_failed": 3, "positions_failed": 69, "positions_opened": 440}	2025-09-16 10:37:46.201811+00
1173	main_trader	HEALTHY	t	t	t	\N	440	0	0	\N	{"sl_set": 440, "sl_failed": 3, "positions_failed": 69, "positions_opened": 440}	2025-09-16 10:38:47.594991+00
1174	main_trader	HEALTHY	t	t	t	\N	440	0	0	\N	{"sl_set": 440, "sl_failed": 3, "positions_failed": 69, "positions_opened": 440}	2025-09-16 10:39:48.788115+00
1175	main_trader	HEALTHY	t	t	t	\N	440	0	0	\N	{"sl_set": 440, "sl_failed": 3, "positions_failed": 69, "positions_opened": 440}	2025-09-16 10:40:50.584016+00
1176	main_trader	HEALTHY	t	t	t	\N	440	0	0	\N	{"sl_set": 440, "sl_failed": 3, "positions_failed": 69, "positions_opened": 440}	2025-09-16 10:41:51.731078+00
1177	main_trader	HEALTHY	t	t	t	\N	440	0	0	\N	{"sl_set": 440, "sl_failed": 3, "positions_failed": 69, "positions_opened": 440}	2025-09-16 10:42:53.222771+00
1178	main_trader	HEALTHY	t	t	t	\N	440	0	0	\N	{"sl_set": 440, "sl_failed": 3, "positions_failed": 69, "positions_opened": 440}	2025-09-16 10:43:54.297818+00
1179	main_trader	HEALTHY	t	t	t	\N	440	0	0	\N	{"sl_set": 440, "sl_failed": 3, "positions_failed": 69, "positions_opened": 440}	2025-09-16 10:44:55.471589+00
1180	main_trader	HEALTHY	t	t	t	\N	440	0	0	\N	{"sl_set": 440, "sl_failed": 3, "positions_failed": 69, "positions_opened": 440}	2025-09-16 10:45:56.772107+00
1181	main_trader	HEALTHY	t	t	t	\N	440	0	0	\N	{"sl_set": 440, "sl_failed": 3, "positions_failed": 69, "positions_opened": 440}	2025-09-16 10:46:57.952408+00
1182	main_trader	HEALTHY	t	t	t	\N	440	0	0	\N	{"sl_set": 440, "sl_failed": 3, "positions_failed": 69, "positions_opened": 440}	2025-09-16 10:47:59.106071+00
1183	main_trader	HEALTHY	t	t	t	\N	440	0	0	\N	{"sl_set": 440, "sl_failed": 3, "positions_failed": 69, "positions_opened": 440}	2025-09-16 10:49:00.312056+00
1184	main_trader	HEALTHY	t	t	t	\N	440	0	0	\N	{"sl_set": 440, "sl_failed": 3, "positions_failed": 69, "positions_opened": 440}	2025-09-16 10:50:01.411842+00
1185	main_trader	HEALTHY	t	t	t	\N	443	0	0	\N	{"sl_set": 443, "sl_failed": 3, "positions_failed": 69, "positions_opened": 443}	2025-09-16 10:51:02.786163+00
1186	main_trader	HEALTHY	t	t	t	\N	443	0	0	\N	{"sl_set": 443, "sl_failed": 3, "positions_failed": 69, "positions_opened": 443}	2025-09-16 10:52:03.952049+00
1187	main_trader	HEALTHY	t	t	t	\N	443	0	0	\N	{"sl_set": 443, "sl_failed": 3, "positions_failed": 69, "positions_opened": 443}	2025-09-16 10:53:05.027206+00
1188	main_trader	HEALTHY	t	t	t	\N	443	0	0	\N	{"sl_set": 443, "sl_failed": 3, "positions_failed": 69, "positions_opened": 443}	2025-09-16 10:54:06.199455+00
1189	main_trader	HEALTHY	t	t	t	\N	443	0	0	\N	{"sl_set": 443, "sl_failed": 3, "positions_failed": 69, "positions_opened": 443}	2025-09-16 10:55:07.548394+00
1190	main_trader	HEALTHY	t	t	t	\N	443	0	0	\N	{"sl_set": 443, "sl_failed": 3, "positions_failed": 69, "positions_opened": 443}	2025-09-16 10:56:09.442946+00
1191	main_trader	HEALTHY	t	t	t	\N	443	0	0	\N	{"sl_set": 443, "sl_failed": 3, "positions_failed": 69, "positions_opened": 443}	2025-09-16 10:57:10.623558+00
1192	main_trader	HEALTHY	t	t	t	\N	443	0	0	\N	{"sl_set": 443, "sl_failed": 3, "positions_failed": 69, "positions_opened": 443}	2025-09-16 10:58:11.714755+00
1193	main_trader	HEALTHY	t	t	t	\N	443	0	0	\N	{"sl_set": 443, "sl_failed": 3, "positions_failed": 69, "positions_opened": 443}	2025-09-16 10:59:12.914175+00
1194	main_trader	HEALTHY	t	t	t	\N	443	0	0	\N	{"sl_set": 443, "sl_failed": 3, "positions_failed": 69, "positions_opened": 443}	2025-09-16 11:00:13.988908+00
1195	main_trader	HEALTHY	t	t	t	\N	443	0	0	\N	{"sl_set": 443, "sl_failed": 3, "positions_failed": 69, "positions_opened": 443}	2025-09-16 11:01:15.403581+00
1196	main_trader	HEALTHY	t	t	t	\N	443	0	0	\N	{"sl_set": 443, "sl_failed": 3, "positions_failed": 69, "positions_opened": 443}	2025-09-16 11:02:16.668159+00
1197	main_trader	HEALTHY	t	t	t	\N	443	0	0	\N	{"sl_set": 443, "sl_failed": 3, "positions_failed": 69, "positions_opened": 443}	2025-09-16 11:03:17.745434+00
1198	main_trader	HEALTHY	t	t	t	\N	443	0	0	\N	{"sl_set": 443, "sl_failed": 3, "positions_failed": 69, "positions_opened": 443}	2025-09-16 11:04:18.914619+00
1199	main_trader	HEALTHY	t	t	t	\N	443	0	0	\N	{"sl_set": 443, "sl_failed": 3, "positions_failed": 69, "positions_opened": 443}	2025-09-16 11:05:20.065817+00
1200	main_trader	HEALTHY	t	t	t	\N	443	0	0	\N	{"sl_set": 443, "sl_failed": 3, "positions_failed": 69, "positions_opened": 443}	2025-09-16 11:06:21.466885+00
1201	main_trader	HEALTHY	t	t	t	\N	443	0	0	\N	{"sl_set": 443, "sl_failed": 3, "positions_failed": 70, "positions_opened": 443}	2025-09-16 11:07:22.695248+00
1202	main_trader	HEALTHY	t	t	t	\N	443	0	0	\N	{"sl_set": 443, "sl_failed": 3, "positions_failed": 70, "positions_opened": 443}	2025-09-16 11:08:23.869246+00
1203	main_trader	HEALTHY	t	t	t	\N	443	0	0	\N	{"sl_set": 443, "sl_failed": 3, "positions_failed": 70, "positions_opened": 443}	2025-09-16 11:09:25.067368+00
1204	main_trader	HEALTHY	t	t	t	\N	443	0	0	\N	{"sl_set": 443, "sl_failed": 3, "positions_failed": 70, "positions_opened": 443}	2025-09-16 11:10:26.140482+00
1205	main_trader	HEALTHY	t	t	t	\N	443	0	0	\N	{"sl_set": 443, "sl_failed": 3, "positions_failed": 70, "positions_opened": 443}	2025-09-16 11:11:27.310173+00
1206	main_trader	HEALTHY	t	t	t	\N	443	0	0	\N	{"sl_set": 443, "sl_failed": 3, "positions_failed": 70, "positions_opened": 443}	2025-09-16 11:12:28.609773+00
1207	main_trader	HEALTHY	t	t	t	\N	443	0	0	\N	{"sl_set": 443, "sl_failed": 3, "positions_failed": 70, "positions_opened": 443}	2025-09-16 11:13:29.760759+00
1208	main_trader	HEALTHY	t	t	t	\N	443	0	0	\N	{"sl_set": 443, "sl_failed": 3, "positions_failed": 70, "positions_opened": 443}	2025-09-16 11:14:30.91707+00
1209	main_trader	HEALTHY	t	t	t	\N	443	0	0	\N	{"sl_set": 443, "sl_failed": 3, "positions_failed": 70, "positions_opened": 443}	2025-09-16 11:15:32.105091+00
1210	main_trader	HEALTHY	t	t	t	\N	443	0	0	\N	{"sl_set": 443, "sl_failed": 3, "positions_failed": 70, "positions_opened": 443}	2025-09-16 11:16:33.298058+00
1211	main_trader	HEALTHY	t	t	t	\N	443	0	0	\N	{"sl_set": 443, "sl_failed": 3, "positions_failed": 70, "positions_opened": 443}	2025-09-16 11:17:34.558343+00
1212	main_trader	HEALTHY	t	t	t	\N	443	0	0	\N	{"sl_set": 443, "sl_failed": 3, "positions_failed": 70, "positions_opened": 443}	2025-09-16 11:18:35.729553+00
1213	main_trader	HEALTHY	t	t	t	\N	443	0	0	\N	{"sl_set": 443, "sl_failed": 3, "positions_failed": 70, "positions_opened": 443}	2025-09-16 11:19:36.899026+00
1214	main_trader	HEALTHY	t	t	t	\N	445	0	0	\N	{"sl_set": 445, "sl_failed": 3, "positions_failed": 71, "positions_opened": 445}	2025-09-16 11:20:37.792215+00
1215	main_trader	HEALTHY	t	t	t	\N	446	0	0	\N	{"sl_set": 446, "sl_failed": 3, "positions_failed": 72, "positions_opened": 446}	2025-09-16 11:21:38.850259+00
1216	main_trader	HEALTHY	t	t	t	\N	446	0	0	\N	{"sl_set": 446, "sl_failed": 3, "positions_failed": 72, "positions_opened": 446}	2025-09-16 11:22:40.256581+00
1217	main_trader	HEALTHY	t	t	t	\N	446	0	0	\N	{"sl_set": 446, "sl_failed": 3, "positions_failed": 72, "positions_opened": 446}	2025-09-16 11:23:41.507605+00
1218	main_trader	HEALTHY	t	t	t	\N	446	0	0	\N	{"sl_set": 446, "sl_failed": 3, "positions_failed": 72, "positions_opened": 446}	2025-09-16 11:24:42.590474+00
1219	main_trader	HEALTHY	t	t	t	\N	446	0	0	\N	{"sl_set": 446, "sl_failed": 3, "positions_failed": 72, "positions_opened": 446}	2025-09-16 11:25:43.743046+00
1220	main_trader	HEALTHY	t	t	t	\N	446	0	0	\N	{"sl_set": 446, "sl_failed": 3, "positions_failed": 72, "positions_opened": 446}	2025-09-16 11:26:44.922833+00
1221	main_trader	HEALTHY	t	t	t	\N	446	0	0	\N	{"sl_set": 446, "sl_failed": 3, "positions_failed": 72, "positions_opened": 446}	2025-09-16 11:27:46.343762+00
1222	main_trader	HEALTHY	t	t	t	\N	446	0	0	\N	{"sl_set": 446, "sl_failed": 3, "positions_failed": 72, "positions_opened": 446}	2025-09-16 11:28:47.596687+00
1223	main_trader	HEALTHY	t	t	t	\N	446	0	0	\N	{"sl_set": 446, "sl_failed": 3, "positions_failed": 72, "positions_opened": 446}	2025-09-16 11:29:48.679974+00
1224	main_trader	HEALTHY	t	t	t	\N	446	0	0	\N	{"sl_set": 446, "sl_failed": 3, "positions_failed": 72, "positions_opened": 446}	2025-09-16 11:30:49.853834+00
1225	main_trader	HEALTHY	t	t	t	\N	446	0	0	\N	{"sl_set": 446, "sl_failed": 3, "positions_failed": 72, "positions_opened": 446}	2025-09-16 11:31:50.927724+00
1226	main_trader	HEALTHY	t	t	t	\N	446	0	0	\N	{"sl_set": 446, "sl_failed": 3, "positions_failed": 72, "positions_opened": 446}	2025-09-16 11:32:52.26595+00
1227	main_trader	HEALTHY	t	t	t	\N	446	0	0	\N	{"sl_set": 446, "sl_failed": 3, "positions_failed": 72, "positions_opened": 446}	2025-09-16 11:33:53.560145+00
1228	main_trader	HEALTHY	t	t	t	\N	446	0	0	\N	{"sl_set": 446, "sl_failed": 3, "positions_failed": 72, "positions_opened": 446}	2025-09-16 11:34:54.630665+00
1229	main_trader	HEALTHY	t	t	t	\N	448	0	0	\N	{"sl_set": 448, "sl_failed": 3, "positions_failed": 72, "positions_opened": 448}	2025-09-16 11:35:55.691247+00
1230	main_trader	HEALTHY	t	t	t	\N	450	0	0	\N	{"sl_set": 450, "sl_failed": 3, "positions_failed": 75, "positions_opened": 450}	2025-09-16 11:36:56.832559+00
1231	main_trader	HEALTHY	t	t	t	\N	450	0	0	\N	{"sl_set": 450, "sl_failed": 3, "positions_failed": 75, "positions_opened": 450}	2025-09-16 11:37:58.085727+00
1232	main_trader	HEALTHY	t	t	t	\N	450	0	0	\N	{"sl_set": 450, "sl_failed": 3, "positions_failed": 75, "positions_opened": 450}	2025-09-16 11:38:59.260424+00
1233	main_trader	HEALTHY	t	t	t	\N	450	0	0	\N	{"sl_set": 450, "sl_failed": 3, "positions_failed": 75, "positions_opened": 450}	2025-09-16 11:40:00.325042+00
1234	main_trader	HEALTHY	t	t	t	\N	450	0	0	\N	{"sl_set": 450, "sl_failed": 3, "positions_failed": 75, "positions_opened": 450}	2025-09-16 11:41:01.503371+00
1235	main_trader	HEALTHY	t	t	t	\N	450	0	0	\N	{"sl_set": 450, "sl_failed": 3, "positions_failed": 75, "positions_opened": 450}	2025-09-16 11:42:03.380097+00
1236	main_trader	HEALTHY	t	t	t	\N	450	0	0	\N	{"sl_set": 450, "sl_failed": 3, "positions_failed": 75, "positions_opened": 450}	2025-09-16 11:43:04.669237+00
1237	main_trader	HEALTHY	t	t	t	\N	450	0	0	\N	{"sl_set": 450, "sl_failed": 3, "positions_failed": 75, "positions_opened": 450}	2025-09-16 11:44:05.857445+00
1238	main_trader	HEALTHY	t	t	t	\N	450	0	0	\N	{"sl_set": 450, "sl_failed": 3, "positions_failed": 75, "positions_opened": 450}	2025-09-16 11:45:07.013262+00
1239	main_trader	HEALTHY	t	t	t	\N	450	0	0	\N	{"sl_set": 450, "sl_failed": 3, "positions_failed": 75, "positions_opened": 450}	2025-09-16 11:46:08.101614+00
1240	main_trader	HEALTHY	t	t	t	\N	450	0	0	\N	{"sl_set": 450, "sl_failed": 3, "positions_failed": 75, "positions_opened": 450}	2025-09-16 11:47:09.533558+00
1241	main_trader	HEALTHY	t	t	t	\N	450	0	0	\N	{"sl_set": 450, "sl_failed": 3, "positions_failed": 75, "positions_opened": 450}	2025-09-16 11:48:10.774843+00
1242	main_trader	HEALTHY	t	t	t	\N	450	0	0	\N	{"sl_set": 450, "sl_failed": 3, "positions_failed": 75, "positions_opened": 450}	2025-09-16 11:49:11.85519+00
1243	main_trader	HEALTHY	t	t	t	\N	450	0	0	\N	{"sl_set": 450, "sl_failed": 3, "positions_failed": 75, "positions_opened": 450}	2025-09-16 11:50:13.025291+00
1244	main_trader	HEALTHY	t	t	t	\N	453	0	0	\N	{"sl_set": 453, "sl_failed": 3, "positions_failed": 78, "positions_opened": 453}	2025-09-16 11:51:14.219998+00
1245	main_trader	HEALTHY	t	t	t	\N	453	0	0	\N	{"sl_set": 453, "sl_failed": 3, "positions_failed": 78, "positions_opened": 453}	2025-09-16 11:52:15.600503+00
1246	main_trader	HEALTHY	t	t	t	\N	453	0	0	\N	{"sl_set": 453, "sl_failed": 3, "positions_failed": 78, "positions_opened": 453}	2025-09-16 11:53:16.843188+00
1247	main_trader	HEALTHY	t	t	t	\N	453	0	0	\N	{"sl_set": 453, "sl_failed": 3, "positions_failed": 78, "positions_opened": 453}	2025-09-16 11:54:17.922929+00
1248	main_trader	HEALTHY	t	t	t	\N	453	0	0	\N	{"sl_set": 453, "sl_failed": 3, "positions_failed": 78, "positions_opened": 453}	2025-09-16 11:55:19.06816+00
1249	main_trader	HEALTHY	t	t	t	\N	453	0	0	\N	{"sl_set": 453, "sl_failed": 3, "positions_failed": 78, "positions_opened": 453}	2025-09-16 11:56:20.140623+00
1250	main_trader	HEALTHY	t	t	t	\N	453	0	0	\N	{"sl_set": 453, "sl_failed": 3, "positions_failed": 78, "positions_opened": 453}	2025-09-16 11:57:22.333849+00
1251	main_trader	HEALTHY	t	t	t	\N	453	0	0	\N	{"sl_set": 453, "sl_failed": 3, "positions_failed": 78, "positions_opened": 453}	2025-09-16 11:58:23.59501+00
1252	main_trader	HEALTHY	t	t	t	\N	453	0	0	\N	{"sl_set": 453, "sl_failed": 3, "positions_failed": 78, "positions_opened": 453}	2025-09-16 11:59:24.794176+00
1253	main_trader	HEALTHY	t	t	t	\N	453	0	0	\N	{"sl_set": 453, "sl_failed": 3, "positions_failed": 78, "positions_opened": 453}	2025-09-16 12:00:25.994548+00
1254	main_trader	HEALTHY	t	t	t	\N	453	0	0	\N	{"sl_set": 453, "sl_failed": 3, "positions_failed": 78, "positions_opened": 453}	2025-09-16 12:01:27.19427+00
1255	main_trader	HEALTHY	t	t	t	\N	453	0	0	\N	{"sl_set": 453, "sl_failed": 3, "positions_failed": 78, "positions_opened": 453}	2025-09-16 12:02:28.634565+00
1256	main_trader	HEALTHY	t	t	t	\N	453	0	0	\N	{"sl_set": 453, "sl_failed": 3, "positions_failed": 78, "positions_opened": 453}	2025-09-16 12:03:29.916625+00
1257	main_trader	HEALTHY	t	t	t	\N	453	0	0	\N	{"sl_set": 453, "sl_failed": 3, "positions_failed": 78, "positions_opened": 453}	2025-09-16 12:04:31.009668+00
1258	main_trader	HEALTHY	t	t	t	\N	453	0	0	\N	{"sl_set": 453, "sl_failed": 3, "positions_failed": 78, "positions_opened": 453}	2025-09-16 12:05:32.508863+00
1259	main_trader	HEALTHY	t	t	t	\N	454	0	0	\N	{"sl_set": 455, "sl_failed": 3, "positions_failed": 78, "positions_opened": 455}	2025-09-16 12:06:33.700115+00
1260	main_trader	HEALTHY	t	t	t	\N	455	0	0	\N	{"sl_set": 455, "sl_failed": 3, "positions_failed": 78, "positions_opened": 455}	2025-09-16 12:07:35.015926+00
1261	main_trader	HEALTHY	t	t	t	\N	455	0	0	\N	{"sl_set": 455, "sl_failed": 3, "positions_failed": 78, "positions_opened": 455}	2025-09-16 12:08:36.214069+00
1262	main_trader	HEALTHY	t	t	t	\N	455	0	0	\N	{"sl_set": 455, "sl_failed": 3, "positions_failed": 78, "positions_opened": 455}	2025-09-16 12:09:37.389361+00
1263	main_trader	HEALTHY	t	t	t	\N	455	0	0	\N	{"sl_set": 455, "sl_failed": 3, "positions_failed": 78, "positions_opened": 455}	2025-09-16 12:10:38.484447+00
1264	main_trader	HEALTHY	t	t	t	\N	455	0	0	\N	{"sl_set": 455, "sl_failed": 3, "positions_failed": 78, "positions_opened": 455}	2025-09-16 12:11:39.639267+00
1265	main_trader	HEALTHY	t	t	t	\N	455	0	0	\N	{"sl_set": 455, "sl_failed": 3, "positions_failed": 78, "positions_opened": 455}	2025-09-16 12:12:41.447084+00
1266	main_trader	HEALTHY	t	t	t	\N	455	0	0	\N	{"sl_set": 455, "sl_failed": 3, "positions_failed": 78, "positions_opened": 455}	2025-09-16 12:13:42.698414+00
1267	main_trader	HEALTHY	t	t	t	\N	455	0	0	\N	{"sl_set": 455, "sl_failed": 3, "positions_failed": 78, "positions_opened": 455}	2025-09-16 12:14:43.976003+00
1268	main_trader	HEALTHY	t	t	t	\N	455	0	0	\N	{"sl_set": 455, "sl_failed": 3, "positions_failed": 78, "positions_opened": 455}	2025-09-16 12:15:45.037285+00
1269	main_trader	HEALTHY	t	t	t	\N	455	0	0	\N	{"sl_set": 455, "sl_failed": 3, "positions_failed": 78, "positions_opened": 455}	2025-09-16 12:16:46.213389+00
1270	main_trader	HEALTHY	t	t	t	\N	455	0	0	\N	{"sl_set": 455, "sl_failed": 3, "positions_failed": 78, "positions_opened": 455}	2025-09-16 12:17:47.410095+00
1271	main_trader	HEALTHY	t	t	t	\N	455	0	0	\N	{"sl_set": 455, "sl_failed": 3, "positions_failed": 78, "positions_opened": 455}	2025-09-16 12:18:48.940145+00
1272	main_trader	HEALTHY	t	t	t	\N	455	0	0	\N	{"sl_set": 455, "sl_failed": 3, "positions_failed": 78, "positions_opened": 455}	2025-09-16 12:19:50.199367+00
1273	main_trader	HEALTHY	t	t	t	\N	456	0	0	\N	{"sl_set": 456, "sl_failed": 4, "positions_failed": 79, "positions_opened": 457}	2025-09-16 12:20:51.496627+00
1274	main_trader	HEALTHY	t	t	t	\N	460	0	0	\N	{"sl_set": 459, "sl_failed": 4, "positions_failed": 79, "positions_opened": 460}	2025-09-16 12:21:52.567813+00
1275	main_trader	HEALTHY	t	t	t	\N	460	0	0	\N	{"sl_set": 459, "sl_failed": 4, "positions_failed": 79, "positions_opened": 460}	2025-09-16 12:22:53.74329+00
1276	main_trader	HEALTHY	t	t	t	\N	460	0	0	\N	{"sl_set": 459, "sl_failed": 4, "positions_failed": 79, "positions_opened": 460}	2025-09-16 12:23:55.172465+00
1277	main_trader	HEALTHY	t	t	t	\N	460	0	0	\N	{"sl_set": 459, "sl_failed": 4, "positions_failed": 79, "positions_opened": 460}	2025-09-16 12:24:56.443397+00
1278	main_trader	HEALTHY	t	t	t	\N	460	0	0	\N	{"sl_set": 459, "sl_failed": 4, "positions_failed": 79, "positions_opened": 460}	2025-09-16 12:25:57.5271+00
1279	main_trader	HEALTHY	t	t	t	\N	460	0	0	\N	{"sl_set": 459, "sl_failed": 4, "positions_failed": 79, "positions_opened": 460}	2025-09-16 12:26:58.785089+00
1280	main_trader	HEALTHY	t	t	t	\N	460	0	0	\N	{"sl_set": 459, "sl_failed": 4, "positions_failed": 79, "positions_opened": 460}	2025-09-16 12:28:00.042138+00
1281	main_trader	HEALTHY	t	t	t	\N	460	0	0	\N	{"sl_set": 459, "sl_failed": 4, "positions_failed": 79, "positions_opened": 460}	2025-09-16 12:29:01.126769+00
1282	main_trader	HEALTHY	t	t	t	\N	460	0	0	\N	{"sl_set": 459, "sl_failed": 4, "positions_failed": 79, "positions_opened": 460}	2025-09-16 12:30:02.368433+00
1283	main_trader	HEALTHY	t	t	t	\N	460	0	0	\N	{"sl_set": 459, "sl_failed": 4, "positions_failed": 79, "positions_opened": 460}	2025-09-16 12:31:03.602944+00
1284	main_trader	HEALTHY	t	t	t	\N	460	0	0	\N	{"sl_set": 459, "sl_failed": 4, "positions_failed": 79, "positions_opened": 460}	2025-09-16 12:32:05.149024+00
1285	main_trader	HEALTHY	t	t	t	\N	460	0	0	\N	{"sl_set": 459, "sl_failed": 4, "positions_failed": 79, "positions_opened": 460}	2025-09-16 12:33:06.344151+00
1286	main_trader	HEALTHY	t	t	t	\N	460	0	0	\N	{"sl_set": 459, "sl_failed": 4, "positions_failed": 79, "positions_opened": 460}	2025-09-16 12:34:07.546682+00
1287	main_trader	HEALTHY	t	t	t	\N	460	0	0	\N	{"sl_set": 459, "sl_failed": 4, "positions_failed": 79, "positions_opened": 460}	2025-09-16 12:35:08.621143+00
1288	main_trader	HEALTHY	t	t	t	\N	463	0	0	\N	{"sl_set": 462, "sl_failed": 4, "positions_failed": 79, "positions_opened": 463}	2025-09-16 12:36:09.798426+00
1289	main_trader	HEALTHY	t	t	t	\N	463	0	0	\N	{"sl_set": 462, "sl_failed": 4, "positions_failed": 79, "positions_opened": 463}	2025-09-16 12:37:11.20654+00
1290	main_trader	HEALTHY	t	t	t	\N	463	0	0	\N	{"sl_set": 462, "sl_failed": 4, "positions_failed": 79, "positions_opened": 463}	2025-09-16 12:38:12.474692+00
1291	main_trader	HEALTHY	t	t	t	\N	463	0	0	\N	{"sl_set": 462, "sl_failed": 4, "positions_failed": 79, "positions_opened": 463}	2025-09-16 12:39:13.668205+00
1292	main_trader	HEALTHY	t	t	t	\N	463	0	0	\N	{"sl_set": 462, "sl_failed": 4, "positions_failed": 79, "positions_opened": 463}	2025-09-16 12:40:14.871632+00
1293	main_trader	HEALTHY	t	t	t	\N	463	0	0	\N	{"sl_set": 462, "sl_failed": 4, "positions_failed": 79, "positions_opened": 463}	2025-09-16 12:41:15.960597+00
1294	main_trader	HEALTHY	t	t	t	\N	463	0	0	\N	{"sl_set": 462, "sl_failed": 4, "positions_failed": 79, "positions_opened": 463}	2025-09-16 12:42:17.286086+00
1295	main_trader	HEALTHY	t	t	t	\N	463	0	0	\N	{"sl_set": 462, "sl_failed": 4, "positions_failed": 79, "positions_opened": 463}	2025-09-16 12:43:18.768088+00
1296	main_trader	HEALTHY	t	t	t	\N	463	0	0	\N	{"sl_set": 462, "sl_failed": 4, "positions_failed": 79, "positions_opened": 463}	2025-09-16 12:44:19.968736+00
1297	main_trader	HEALTHY	t	t	t	\N	463	0	0	\N	{"sl_set": 462, "sl_failed": 4, "positions_failed": 79, "positions_opened": 463}	2025-09-16 12:45:21.09646+00
1298	main_trader	HEALTHY	t	t	t	\N	463	0	0	\N	{"sl_set": 462, "sl_failed": 4, "positions_failed": 79, "positions_opened": 463}	2025-09-16 12:46:22.292649+00
1299	main_trader	HEALTHY	t	t	t	\N	463	0	0	\N	{"sl_set": 462, "sl_failed": 4, "positions_failed": 79, "positions_opened": 463}	2025-09-16 12:47:23.60215+00
1300	main_trader	HEALTHY	t	t	t	\N	463	0	0	\N	{"sl_set": 462, "sl_failed": 4, "positions_failed": 79, "positions_opened": 463}	2025-09-16 12:48:24.861769+00
1301	main_trader	HEALTHY	t	t	t	\N	463	0	0	\N	{"sl_set": 462, "sl_failed": 4, "positions_failed": 79, "positions_opened": 463}	2025-09-16 12:49:26.066705+00
1302	main_trader	HEALTHY	t	t	t	\N	464	0	0	\N	{"sl_set": 463, "sl_failed": 4, "positions_failed": 79, "positions_opened": 464}	2025-09-16 12:50:27.167555+00
1303	main_trader	HEALTHY	t	t	t	\N	467	0	0	\N	{"sl_set": 466, "sl_failed": 4, "positions_failed": 79, "positions_opened": 467}	2025-09-16 12:51:28.256055+00
1304	main_trader	HEALTHY	t	t	t	\N	467	0	0	\N	{"sl_set": 466, "sl_failed": 4, "positions_failed": 79, "positions_opened": 467}	2025-09-16 12:52:29.591199+00
1305	main_trader	HEALTHY	t	t	t	\N	467	0	0	\N	{"sl_set": 466, "sl_failed": 4, "positions_failed": 79, "positions_opened": 467}	2025-09-16 12:53:30.863595+00
1306	main_trader	HEALTHY	t	t	t	\N	467	0	0	\N	{"sl_set": 466, "sl_failed": 4, "positions_failed": 79, "positions_opened": 467}	2025-09-16 12:54:32.06013+00
1307	main_trader	HEALTHY	t	t	t	\N	467	0	0	\N	{"sl_set": 466, "sl_failed": 4, "positions_failed": 79, "positions_opened": 467}	2025-09-16 12:55:33.267381+00
1308	main_trader	HEALTHY	t	t	t	\N	467	0	0	\N	{"sl_set": 466, "sl_failed": 4, "positions_failed": 79, "positions_opened": 467}	2025-09-16 12:56:34.466048+00
1309	main_trader	HEALTHY	t	t	t	\N	467	0	0	\N	{"sl_set": 466, "sl_failed": 4, "positions_failed": 79, "positions_opened": 467}	2025-09-16 12:57:35.895897+00
1310	main_trader	HEALTHY	t	t	t	\N	467	0	0	\N	{"sl_set": 466, "sl_failed": 4, "positions_failed": 79, "positions_opened": 467}	2025-09-16 12:58:37.083901+00
1311	main_trader	HEALTHY	t	t	t	\N	467	0	0	\N	{"sl_set": 466, "sl_failed": 4, "positions_failed": 79, "positions_opened": 467}	2025-09-16 12:59:38.273243+00
1312	main_trader	HEALTHY	t	t	t	\N	467	0	0	\N	{"sl_set": 466, "sl_failed": 4, "positions_failed": 79, "positions_opened": 467}	2025-09-16 13:00:39.36388+00
1313	main_trader	HEALTHY	t	t	t	\N	467	0	0	\N	{"sl_set": 466, "sl_failed": 4, "positions_failed": 79, "positions_opened": 467}	2025-09-16 13:01:40.561869+00
1314	main_trader	HEALTHY	t	t	t	\N	467	0	0	\N	{"sl_set": 466, "sl_failed": 4, "positions_failed": 79, "positions_opened": 467}	2025-09-16 13:02:41.896962+00
1315	main_trader	HEALTHY	t	t	t	\N	467	0	0	\N	{"sl_set": 466, "sl_failed": 4, "positions_failed": 79, "positions_opened": 467}	2025-09-16 13:03:43.088753+00
1316	main_trader	HEALTHY	t	t	t	\N	467	0	0	\N	{"sl_set": 466, "sl_failed": 4, "positions_failed": 79, "positions_opened": 467}	2025-09-16 13:04:44.274902+00
1317	main_trader	HEALTHY	t	t	t	\N	467	0	0	\N	{"sl_set": 466, "sl_failed": 4, "positions_failed": 79, "positions_opened": 467}	2025-09-16 13:05:45.434958+00
1318	main_trader	HEALTHY	t	t	t	\N	470	0	0	\N	{"sl_set": 468, "sl_failed": 5, "positions_failed": 79, "positions_opened": 470}	2025-09-16 13:06:46.32894+00
1319	main_trader	HEALTHY	t	t	t	\N	471	0	0	\N	{"sl_set": 469, "sl_failed": 5, "positions_failed": 79, "positions_opened": 471}	2025-09-16 13:07:47.569835+00
1320	main_trader	HEALTHY	t	t	t	\N	471	0	0	\N	{"sl_set": 469, "sl_failed": 5, "positions_failed": 79, "positions_opened": 471}	2025-09-16 13:08:48.833373+00
1321	main_trader	HEALTHY	t	t	t	\N	471	0	0	\N	{"sl_set": 469, "sl_failed": 5, "positions_failed": 79, "positions_opened": 471}	2025-09-16 13:09:49.897989+00
1322	main_trader	HEALTHY	t	t	t	\N	471	0	0	\N	{"sl_set": 469, "sl_failed": 5, "positions_failed": 79, "positions_opened": 471}	2025-09-16 13:10:51.062023+00
1323	main_trader	HEALTHY	t	t	t	\N	471	0	0	\N	{"sl_set": 469, "sl_failed": 5, "positions_failed": 79, "positions_opened": 471}	2025-09-16 13:11:52.212692+00
1324	main_trader	HEALTHY	t	t	t	\N	471	0	0	\N	{"sl_set": 469, "sl_failed": 5, "positions_failed": 79, "positions_opened": 471}	2025-09-16 13:12:53.624361+00
1325	main_trader	HEALTHY	t	t	t	\N	471	0	0	\N	{"sl_set": 469, "sl_failed": 5, "positions_failed": 79, "positions_opened": 471}	2025-09-16 13:13:54.771686+00
1326	main_trader	HEALTHY	t	t	t	\N	471	0	0	\N	{"sl_set": 469, "sl_failed": 5, "positions_failed": 79, "positions_opened": 471}	2025-09-16 13:14:55.844997+00
1327	main_trader	HEALTHY	t	t	t	\N	471	0	0	\N	{"sl_set": 469, "sl_failed": 5, "positions_failed": 79, "positions_opened": 471}	2025-09-16 13:15:57.009689+00
1328	main_trader	HEALTHY	t	t	t	\N	471	0	0	\N	{"sl_set": 469, "sl_failed": 5, "positions_failed": 79, "positions_opened": 471}	2025-09-16 13:16:58.075177+00
1329	main_trader	HEALTHY	t	t	t	\N	471	0	0	\N	{"sl_set": 469, "sl_failed": 5, "positions_failed": 79, "positions_opened": 471}	2025-09-16 13:17:59.480707+00
1330	main_trader	HEALTHY	t	t	t	\N	471	0	0	\N	{"sl_set": 469, "sl_failed": 5, "positions_failed": 79, "positions_opened": 471}	2025-09-16 13:19:00.667588+00
1331	main_trader	HEALTHY	t	t	t	\N	471	0	0	\N	{"sl_set": 469, "sl_failed": 5, "positions_failed": 79, "positions_opened": 471}	2025-09-16 13:20:02.467757+00
1332	main_trader	HEALTHY	t	t	t	\N	471	0	0	\N	{"sl_set": 469, "sl_failed": 5, "positions_failed": 79, "positions_opened": 471}	2025-09-16 13:21:03.688039+00
1333	main_trader	HEALTHY	t	t	t	\N	476	0	0	\N	{"sl_set": 474, "sl_failed": 5, "positions_failed": 80, "positions_opened": 476}	2025-09-16 13:22:04.590081+00
1334	main_trader	HEALTHY	t	t	t	\N	476	0	0	\N	{"sl_set": 474, "sl_failed": 5, "positions_failed": 82, "positions_opened": 476}	2025-09-16 13:23:05.890998+00
1335	main_trader	HEALTHY	t	t	t	\N	476	0	0	\N	{"sl_set": 474, "sl_failed": 5, "positions_failed": 82, "positions_opened": 476}	2025-09-16 13:24:07.031441+00
1336	main_trader	HEALTHY	t	t	t	\N	476	0	0	\N	{"sl_set": 474, "sl_failed": 5, "positions_failed": 82, "positions_opened": 476}	2025-09-16 13:25:08.108959+00
1337	main_trader	HEALTHY	t	t	t	\N	476	0	0	\N	{"sl_set": 474, "sl_failed": 5, "positions_failed": 82, "positions_opened": 476}	2025-09-16 13:26:09.275204+00
1338	main_trader	HEALTHY	t	t	t	\N	476	0	0	\N	{"sl_set": 474, "sl_failed": 5, "positions_failed": 82, "positions_opened": 476}	2025-09-16 13:27:10.449568+00
1339	main_trader	HEALTHY	t	t	t	\N	476	0	0	\N	{"sl_set": 474, "sl_failed": 5, "positions_failed": 82, "positions_opened": 476}	2025-09-16 13:28:11.868645+00
1340	main_trader	HEALTHY	t	t	t	\N	476	0	0	\N	{"sl_set": 474, "sl_failed": 5, "positions_failed": 82, "positions_opened": 476}	2025-09-16 13:29:13.135541+00
1341	main_trader	HEALTHY	t	t	t	\N	476	0	0	\N	{"sl_set": 474, "sl_failed": 5, "positions_failed": 82, "positions_opened": 476}	2025-09-16 13:30:14.21291+00
1342	main_trader	HEALTHY	t	t	t	\N	476	0	0	\N	{"sl_set": 474, "sl_failed": 5, "positions_failed": 82, "positions_opened": 476}	2025-09-16 13:31:15.300849+00
1343	main_trader	HEALTHY	t	t	t	\N	476	0	0	\N	{"sl_set": 474, "sl_failed": 5, "positions_failed": 82, "positions_opened": 476}	2025-09-16 13:32:16.412278+00
1344	main_trader	HEALTHY	t	t	t	\N	476	0	0	\N	{"sl_set": 474, "sl_failed": 5, "positions_failed": 82, "positions_opened": 476}	2025-09-16 13:33:17.853216+00
1345	main_trader	HEALTHY	t	t	t	\N	476	0	0	\N	{"sl_set": 474, "sl_failed": 5, "positions_failed": 82, "positions_opened": 476}	2025-09-16 13:34:19.121804+00
1346	main_trader	HEALTHY	t	t	t	\N	476	0	0	\N	{"sl_set": 474, "sl_failed": 5, "positions_failed": 82, "positions_opened": 476}	2025-09-16 13:35:20.452565+00
1347	main_trader	HEALTHY	t	t	t	\N	476	0	0	\N	{"sl_set": 474, "sl_failed": 5, "positions_failed": 82, "positions_opened": 476}	2025-09-16 13:36:21.543335+00
1348	main_trader	HEALTHY	t	t	t	\N	480	0	0	\N	{"sl_set": 480, "sl_failed": 5, "positions_failed": 82, "positions_opened": 481}	2025-09-16 13:37:22.62036+00
1349	main_trader	HEALTHY	t	t	t	\N	486	0	0	\N	{"sl_set": 486, "sl_failed": 5, "positions_failed": 82, "positions_opened": 487}	2025-09-16 13:38:23.834054+00
1350	main_trader	HEALTHY	t	t	t	\N	489	0	0	\N	{"sl_set": 488, "sl_failed": 5, "positions_failed": 82, "positions_opened": 489}	2025-09-16 13:39:24.973131+00
1351	main_trader	HEALTHY	t	t	t	\N	489	0	0	\N	{"sl_set": 488, "sl_failed": 5, "positions_failed": 82, "positions_opened": 489}	2025-09-16 13:40:26.135576+00
1352	main_trader	HEALTHY	t	t	t	\N	489	0	0	\N	{"sl_set": 488, "sl_failed": 5, "positions_failed": 82, "positions_opened": 489}	2025-09-16 13:41:27.288602+00
1353	main_trader	HEALTHY	t	t	t	\N	489	0	0	\N	{"sl_set": 488, "sl_failed": 5, "positions_failed": 82, "positions_opened": 489}	2025-09-16 13:42:28.468543+00
1354	main_trader	HEALTHY	t	t	t	\N	489	0	0	\N	{"sl_set": 488, "sl_failed": 5, "positions_failed": 82, "positions_opened": 489}	2025-09-16 13:43:30.35863+00
1355	main_trader	HEALTHY	t	t	t	\N	489	0	0	\N	{"sl_set": 488, "sl_failed": 5, "positions_failed": 82, "positions_opened": 489}	2025-09-16 13:44:31.597719+00
1356	main_trader	HEALTHY	t	t	t	\N	489	0	0	\N	{"sl_set": 488, "sl_failed": 5, "positions_failed": 82, "positions_opened": 489}	2025-09-16 13:45:32.680203+00
1357	main_trader	HEALTHY	t	t	t	\N	489	0	0	\N	{"sl_set": 488, "sl_failed": 5, "positions_failed": 82, "positions_opened": 489}	2025-09-16 13:46:33.852469+00
1358	main_trader	HEALTHY	t	t	t	\N	489	0	0	\N	{"sl_set": 488, "sl_failed": 5, "positions_failed": 82, "positions_opened": 489}	2025-09-16 13:47:35.023349+00
1359	main_trader	HEALTHY	t	t	t	\N	489	0	0	\N	{"sl_set": 488, "sl_failed": 5, "positions_failed": 82, "positions_opened": 489}	2025-09-16 13:48:36.326954+00
1360	main_trader	HEALTHY	t	t	t	\N	489	0	0	\N	{"sl_set": 488, "sl_failed": 5, "positions_failed": 82, "positions_opened": 489}	2025-09-16 13:49:37.561091+00
1361	main_trader	HEALTHY	t	t	t	\N	489	0	0	\N	{"sl_set": 488, "sl_failed": 5, "positions_failed": 82, "positions_opened": 489}	2025-09-16 13:50:38.722567+00
1362	main_trader	HEALTHY	t	t	t	\N	490	0	0	\N	{"sl_set": 489, "sl_failed": 5, "positions_failed": 82, "positions_opened": 490}	2025-09-16 13:51:39.841797+00
1363	main_trader	HEALTHY	t	t	t	\N	492	0	0	\N	{"sl_set": 491, "sl_failed": 5, "positions_failed": 82, "positions_opened": 492}	2025-09-16 13:52:41.016995+00
1364	main_trader	HEALTHY	t	t	t	\N	492	0	0	\N	{"sl_set": 491, "sl_failed": 5, "positions_failed": 82, "positions_opened": 492}	2025-09-16 13:53:42.407044+00
1365	main_trader	HEALTHY	t	t	t	\N	492	0	0	\N	{"sl_set": 491, "sl_failed": 5, "positions_failed": 82, "positions_opened": 492}	2025-09-16 13:54:43.558612+00
1366	main_trader	HEALTHY	t	t	t	\N	492	0	0	\N	{"sl_set": 491, "sl_failed": 5, "positions_failed": 82, "positions_opened": 492}	2025-09-16 13:55:44.754313+00
1367	main_trader	HEALTHY	t	t	t	\N	492	0	0	\N	{"sl_set": 491, "sl_failed": 5, "positions_failed": 82, "positions_opened": 492}	2025-09-16 13:56:45.961406+00
1368	main_trader	HEALTHY	t	t	t	\N	492	0	0	\N	{"sl_set": 491, "sl_failed": 5, "positions_failed": 82, "positions_opened": 492}	2025-09-16 13:57:47.141708+00
1369	main_trader	HEALTHY	t	t	t	\N	492	0	0	\N	{"sl_set": 491, "sl_failed": 5, "positions_failed": 82, "positions_opened": 492}	2025-09-16 13:58:48.911034+00
1370	main_trader	HEALTHY	t	t	t	\N	492	0	0	\N	{"sl_set": 491, "sl_failed": 5, "positions_failed": 82, "positions_opened": 492}	2025-09-16 13:59:50.161793+00
1371	main_trader	HEALTHY	t	t	t	\N	492	0	0	\N	{"sl_set": 491, "sl_failed": 5, "positions_failed": 82, "positions_opened": 492}	2025-09-16 14:00:51.234179+00
1372	main_trader	HEALTHY	t	t	t	\N	492	0	0	\N	{"sl_set": 491, "sl_failed": 5, "positions_failed": 82, "positions_opened": 492}	2025-09-16 14:01:52.400757+00
1373	main_trader	HEALTHY	t	t	t	\N	492	0	0	\N	{"sl_set": 491, "sl_failed": 5, "positions_failed": 82, "positions_opened": 492}	2025-09-16 14:02:53.46994+00
1374	main_trader	HEALTHY	t	t	t	\N	492	0	0	\N	{"sl_set": 491, "sl_failed": 5, "positions_failed": 82, "positions_opened": 492}	2025-09-16 14:03:54.864134+00
1375	main_trader	HEALTHY	t	t	t	\N	492	0	0	\N	{"sl_set": 491, "sl_failed": 5, "positions_failed": 82, "positions_opened": 492}	2025-09-16 14:04:56.10291+00
1376	main_trader	HEALTHY	t	t	t	\N	492	0	0	\N	{"sl_set": 491, "sl_failed": 5, "positions_failed": 82, "positions_opened": 492}	2025-09-16 14:05:57.280248+00
1377	main_trader	HEALTHY	t	t	t	\N	496	0	0	\N	{"sl_set": 495, "sl_failed": 5, "positions_failed": 82, "positions_opened": 497}	2025-09-16 14:06:58.902437+00
1378	main_trader	HEALTHY	t	t	t	\N	502	0	0	\N	{"sl_set": 501, "sl_failed": 5, "positions_failed": 82, "positions_opened": 502}	2025-09-16 14:08:00.051715+00
1379	main_trader	HEALTHY	t	t	t	\N	503	0	0	\N	{"sl_set": 502, "sl_failed": 5, "positions_failed": 82, "positions_opened": 503}	2025-09-16 14:09:01.23338+00
1380	main_trader	HEALTHY	t	t	t	\N	503	0	0	\N	{"sl_set": 502, "sl_failed": 5, "positions_failed": 82, "positions_opened": 503}	2025-09-16 14:10:02.444074+00
1381	main_trader	HEALTHY	t	t	t	\N	503	0	0	\N	{"sl_set": 502, "sl_failed": 5, "positions_failed": 82, "positions_opened": 503}	2025-09-16 14:11:03.532913+00
1382	main_trader	HEALTHY	t	t	t	\N	503	0	0	\N	{"sl_set": 502, "sl_failed": 5, "positions_failed": 82, "positions_opened": 503}	2025-09-16 14:12:05.33454+00
1383	main_trader	HEALTHY	t	t	t	\N	503	0	0	\N	{"sl_set": 502, "sl_failed": 5, "positions_failed": 82, "positions_opened": 503}	2025-09-16 14:13:06.513903+00
1384	main_trader	HEALTHY	t	t	t	\N	503	0	0	\N	{"sl_set": 502, "sl_failed": 5, "positions_failed": 82, "positions_opened": 503}	2025-09-16 14:14:07.882011+00
1385	main_trader	HEALTHY	t	t	t	\N	503	0	0	\N	{"sl_set": 502, "sl_failed": 5, "positions_failed": 82, "positions_opened": 503}	2025-09-16 14:15:09.049567+00
1386	main_trader	HEALTHY	t	t	t	\N	503	0	0	\N	{"sl_set": 502, "sl_failed": 5, "positions_failed": 82, "positions_opened": 503}	2025-09-16 14:16:10.221923+00
1387	main_trader	HEALTHY	t	t	t	\N	503	0	0	\N	{"sl_set": 502, "sl_failed": 5, "positions_failed": 82, "positions_opened": 503}	2025-09-16 14:17:11.523532+00
1388	main_trader	HEALTHY	t	t	t	\N	503	0	0	\N	{"sl_set": 502, "sl_failed": 5, "positions_failed": 82, "positions_opened": 503}	2025-09-16 14:18:12.817355+00
1389	main_trader	HEALTHY	t	t	t	\N	503	0	0	\N	{"sl_set": 502, "sl_failed": 5, "positions_failed": 82, "positions_opened": 503}	2025-09-16 14:19:13.933833+00
1390	main_trader	HEALTHY	t	t	t	\N	503	0	0	\N	{"sl_set": 502, "sl_failed": 5, "positions_failed": 82, "positions_opened": 503}	2025-09-16 14:20:15.119716+00
1391	main_trader	HEALTHY	t	t	t	\N	503	0	0	\N	{"sl_set": 502, "sl_failed": 5, "positions_failed": 82, "positions_opened": 503}	2025-09-16 14:21:16.232417+00
1392	main_trader	HEALTHY	t	t	t	\N	503	0	0	\N	{"sl_set": 502, "sl_failed": 5, "positions_failed": 82, "positions_opened": 503}	2025-09-16 14:22:17.633359+00
1393	main_trader	HEALTHY	t	t	t	\N	503	0	0	\N	{"sl_set": 502, "sl_failed": 5, "positions_failed": 82, "positions_opened": 503}	2025-09-16 14:23:18.858798+00
1394	main_trader	HEALTHY	t	t	t	\N	503	0	0	\N	{"sl_set": 502, "sl_failed": 5, "positions_failed": 82, "positions_opened": 503}	2025-09-16 14:24:20.148502+00
1395	main_trader	HEALTHY	t	t	t	\N	503	0	0	\N	{"sl_set": 502, "sl_failed": 5, "positions_failed": 82, "positions_opened": 503}	2025-09-16 14:25:21.223338+00
1396	main_trader	HEALTHY	t	t	t	\N	503	0	0	\N	{"sl_set": 502, "sl_failed": 5, "positions_failed": 82, "positions_opened": 503}	2025-09-16 14:26:22.321703+00
1397	main_trader	HEALTHY	t	t	t	\N	503	0	0	\N	{"sl_set": 502, "sl_failed": 5, "positions_failed": 82, "positions_opened": 503}	2025-09-16 14:27:23.727137+00
1398	main_trader	HEALTHY	t	t	t	\N	503	0	0	\N	{"sl_set": 502, "sl_failed": 5, "positions_failed": 82, "positions_opened": 503}	2025-09-16 14:28:24.980898+00
1399	main_trader	HEALTHY	t	t	t	\N	503	0	0	\N	{"sl_set": 502, "sl_failed": 5, "positions_failed": 82, "positions_opened": 503}	2025-09-16 14:29:26.219201+00
1400	main_trader	HEALTHY	t	t	t	\N	503	0	0	\N	{"sl_set": 502, "sl_failed": 5, "positions_failed": 82, "positions_opened": 503}	2025-09-16 14:30:27.427555+00
1401	main_trader	HEALTHY	t	t	t	\N	503	0	0	\N	{"sl_set": 502, "sl_failed": 5, "positions_failed": 82, "positions_opened": 503}	2025-09-16 14:31:28.542785+00
1402	main_trader	HEALTHY	t	t	t	\N	503	0	0	\N	{"sl_set": 502, "sl_failed": 5, "positions_failed": 82, "positions_opened": 503}	2025-09-16 14:32:29.951249+00
1403	main_trader	HEALTHY	t	t	t	\N	503	0	0	\N	{"sl_set": 502, "sl_failed": 5, "positions_failed": 82, "positions_opened": 503}	2025-09-16 14:33:31.201145+00
1404	main_trader	HEALTHY	t	t	t	\N	503	0	0	\N	{"sl_set": 502, "sl_failed": 5, "positions_failed": 82, "positions_opened": 503}	2025-09-16 14:34:32.360144+00
1405	main_trader	HEALTHY	t	t	t	\N	503	0	0	\N	{"sl_set": 503, "sl_failed": 5, "positions_failed": 82, "positions_opened": 504}	2025-09-16 14:35:33.272652+00
1406	main_trader	HEALTHY	t	t	t	\N	509	0	0	\N	{"sl_set": 509, "sl_failed": 5, "positions_failed": 82, "positions_opened": 510}	2025-09-16 14:36:34.182347+00
1407	main_trader	HEALTHY	t	t	t	\N	514	0	0	\N	{"sl_set": 513, "sl_failed": 5, "positions_failed": 83, "positions_opened": 515}	2025-09-16 14:37:35.152586+00
1408	main_trader	HEALTHY	t	t	t	\N	520	0	0	\N	{"sl_set": 519, "sl_failed": 5, "positions_failed": 83, "positions_opened": 520}	2025-09-16 14:38:36.130626+00
1409	main_trader	HEALTHY	t	t	t	\N	520	0	0	\N	{"sl_set": 519, "sl_failed": 5, "positions_failed": 83, "positions_opened": 520}	2025-09-16 14:39:37.293553+00
1410	main_trader	HEALTHY	t	t	t	\N	520	0	0	\N	{"sl_set": 519, "sl_failed": 5, "positions_failed": 83, "positions_opened": 520}	2025-09-16 14:40:38.468944+00
1411	main_trader	HEALTHY	t	t	t	\N	520	0	0	\N	{"sl_set": 519, "sl_failed": 5, "positions_failed": 83, "positions_opened": 520}	2025-09-16 14:41:39.531466+00
1412	main_trader	HEALTHY	t	t	t	\N	520	0	0	\N	{"sl_set": 519, "sl_failed": 5, "positions_failed": 83, "positions_opened": 520}	2025-09-16 14:42:41.361488+00
1413	main_trader	HEALTHY	t	t	t	\N	520	0	0	\N	{"sl_set": 519, "sl_failed": 5, "positions_failed": 83, "positions_opened": 520}	2025-09-16 14:43:42.527358+00
1414	main_trader	HEALTHY	t	t	t	\N	520	0	0	\N	{"sl_set": 519, "sl_failed": 5, "positions_failed": 83, "positions_opened": 520}	2025-09-16 14:44:43.676871+00
1415	main_trader	HEALTHY	t	t	t	\N	520	0	0	\N	{"sl_set": 519, "sl_failed": 5, "positions_failed": 83, "positions_opened": 520}	2025-09-16 14:45:45.151426+00
1416	main_trader	HEALTHY	t	t	t	\N	520	0	0	\N	{"sl_set": 519, "sl_failed": 5, "positions_failed": 83, "positions_opened": 520}	2025-09-16 14:46:46.318054+00
1417	main_trader	HEALTHY	t	t	t	\N	520	0	0	\N	{"sl_set": 519, "sl_failed": 5, "positions_failed": 83, "positions_opened": 520}	2025-09-16 14:47:47.769873+00
1418	main_trader	HEALTHY	t	t	t	\N	520	0	0	\N	{"sl_set": 519, "sl_failed": 5, "positions_failed": 83, "positions_opened": 520}	2025-09-16 14:48:48.921692+00
1419	main_trader	HEALTHY	t	t	t	\N	520	0	0	\N	{"sl_set": 519, "sl_failed": 5, "positions_failed": 83, "positions_opened": 520}	2025-09-16 14:49:50.04315+00
1420	main_trader	HEALTHY	t	t	t	\N	520	0	0	\N	{"sl_set": 519, "sl_failed": 5, "positions_failed": 83, "positions_opened": 520}	2025-09-16 14:50:51.217228+00
1421	main_trader	HEALTHY	t	t	t	\N	523	0	0	\N	{"sl_set": 523, "sl_failed": 5, "positions_failed": 84, "positions_opened": 524}	2025-09-16 14:51:52.112736+00
1422	main_trader	HEALTHY	t	t	t	\N	530	0	0	\N	{"sl_set": 529, "sl_failed": 5, "positions_failed": 84, "positions_opened": 530}	2025-09-16 14:52:53.419071+00
1423	main_trader	HEALTHY	t	t	t	\N	534	0	0	\N	{"sl_set": 533, "sl_failed": 5, "positions_failed": 85, "positions_opened": 534}	2025-09-16 14:53:54.409148+00
1424	main_trader	HEALTHY	t	t	t	\N	535	0	0	\N	{"sl_set": 534, "sl_failed": 5, "positions_failed": 85, "positions_opened": 535}	2025-09-16 14:54:55.493267+00
1425	main_trader	HEALTHY	t	t	t	\N	535	0	0	\N	{"sl_set": 534, "sl_failed": 5, "positions_failed": 85, "positions_opened": 535}	2025-09-16 14:55:56.648214+00
1426	main_trader	HEALTHY	t	t	t	\N	535	0	0	\N	{"sl_set": 534, "sl_failed": 5, "positions_failed": 85, "positions_opened": 535}	2025-09-16 14:56:57.807987+00
1427	main_trader	HEALTHY	t	t	t	\N	535	0	0	\N	{"sl_set": 534, "sl_failed": 5, "positions_failed": 85, "positions_opened": 535}	2025-09-16 14:58:00.296154+00
1428	main_trader	HEALTHY	t	t	t	\N	535	0	0	\N	{"sl_set": 534, "sl_failed": 5, "positions_failed": 85, "positions_opened": 535}	2025-09-16 14:59:01.585887+00
1429	main_trader	HEALTHY	t	t	t	\N	535	0	0	\N	{"sl_set": 534, "sl_failed": 5, "positions_failed": 85, "positions_opened": 535}	2025-09-16 15:00:03.345406+00
1430	main_trader	HEALTHY	t	t	t	\N	535	0	0	\N	{"sl_set": 534, "sl_failed": 5, "positions_failed": 85, "positions_opened": 535}	2025-09-16 15:01:04.43611+00
1431	main_trader	HEALTHY	t	t	t	\N	535	0	0	\N	{"sl_set": 534, "sl_failed": 5, "positions_failed": 85, "positions_opened": 535}	2025-09-16 15:02:05.639233+00
1432	main_trader	HEALTHY	t	t	t	\N	535	0	0	\N	{"sl_set": 534, "sl_failed": 5, "positions_failed": 85, "positions_opened": 535}	2025-09-16 15:03:06.941219+00
1433	main_trader	HEALTHY	t	t	t	\N	535	0	0	\N	{"sl_set": 534, "sl_failed": 5, "positions_failed": 85, "positions_opened": 535}	2025-09-16 15:04:08.88234+00
1434	main_trader	HEALTHY	t	t	t	\N	535	0	0	\N	{"sl_set": 534, "sl_failed": 5, "positions_failed": 85, "positions_opened": 535}	2025-09-16 15:05:10.178096+00
1435	main_trader	HEALTHY	t	t	t	\N	535	0	0	\N	{"sl_set": 534, "sl_failed": 5, "positions_failed": 85, "positions_opened": 535}	2025-09-16 15:06:11.284709+00
1436	main_trader	HEALTHY	t	t	t	\N	540	0	0	\N	{"sl_set": 539, "sl_failed": 5, "positions_failed": 86, "positions_opened": 540}	2025-09-16 15:07:12.184129+00
1437	main_trader	HEALTHY	t	t	t	\N	541	0	0	\N	{"sl_set": 540, "sl_failed": 5, "positions_failed": 86, "positions_opened": 541}	2025-09-16 15:08:13.628433+00
1438	main_trader	HEALTHY	t	t	t	\N	541	0	0	\N	{"sl_set": 540, "sl_failed": 5, "positions_failed": 86, "positions_opened": 541}	2025-09-16 15:09:14.829778+00
1439	main_trader	HEALTHY	t	t	t	\N	541	0	0	\N	{"sl_set": 540, "sl_failed": 5, "positions_failed": 86, "positions_opened": 541}	2025-09-16 15:10:16.027879+00
1440	main_trader	HEALTHY	t	t	t	\N	541	0	0	\N	{"sl_set": 540, "sl_failed": 5, "positions_failed": 86, "positions_opened": 541}	2025-09-16 15:11:17.091691+00
1441	main_trader	HEALTHY	t	t	t	\N	541	0	0	\N	{"sl_set": 540, "sl_failed": 5, "positions_failed": 86, "positions_opened": 541}	2025-09-16 15:12:18.160596+00
1442	main_trader	HEALTHY	t	t	t	\N	541	0	0	\N	{"sl_set": 540, "sl_failed": 5, "positions_failed": 86, "positions_opened": 541}	2025-09-16 15:13:19.467579+00
1443	main_trader	HEALTHY	t	t	t	\N	541	0	0	\N	{"sl_set": 540, "sl_failed": 5, "positions_failed": 86, "positions_opened": 541}	2025-09-16 15:14:20.726305+00
1444	main_trader	HEALTHY	t	t	t	\N	541	0	0	\N	{"sl_set": 540, "sl_failed": 5, "positions_failed": 86, "positions_opened": 541}	2025-09-16 15:15:21.936453+00
1445	main_trader	HEALTHY	t	t	t	\N	541	0	0	\N	{"sl_set": 540, "sl_failed": 5, "positions_failed": 86, "positions_opened": 541}	2025-09-16 15:16:23.133805+00
1446	main_trader	HEALTHY	t	t	t	\N	541	0	0	\N	{"sl_set": 540, "sl_failed": 5, "positions_failed": 86, "positions_opened": 541}	2025-09-16 15:17:24.235737+00
1447	main_trader	HEALTHY	t	t	t	\N	541	0	0	\N	{"sl_set": 540, "sl_failed": 5, "positions_failed": 86, "positions_opened": 541}	2025-09-16 15:18:25.890155+00
1448	main_trader	HEALTHY	t	t	t	\N	541	0	0	\N	{"sl_set": 540, "sl_failed": 5, "positions_failed": 86, "positions_opened": 541}	2025-09-16 15:19:27.104264+00
1449	main_trader	HEALTHY	t	t	t	\N	541	0	0	\N	{"sl_set": 540, "sl_failed": 5, "positions_failed": 86, "positions_opened": 541}	2025-09-16 15:20:28.392687+00
1450	main_trader	HEALTHY	t	t	t	\N	544	0	0	\N	{"sl_set": 543, "sl_failed": 5, "positions_failed": 86, "positions_opened": 544}	2025-09-16 15:21:29.540311+00
1451	main_trader	HEALTHY	t	t	t	\N	544	0	0	\N	{"sl_set": 543, "sl_failed": 5, "positions_failed": 86, "positions_opened": 544}	2025-09-16 15:22:30.69591+00
1452	main_trader	HEALTHY	t	t	t	\N	544	0	0	\N	{"sl_set": 543, "sl_failed": 5, "positions_failed": 86, "positions_opened": 544}	2025-09-16 15:23:31.906777+00
1453	main_trader	HEALTHY	t	t	t	\N	544	0	0	\N	{"sl_set": 543, "sl_failed": 5, "positions_failed": 86, "positions_opened": 544}	2025-09-16 15:24:33.203833+00
1454	main_trader	HEALTHY	t	t	t	\N	544	0	0	\N	{"sl_set": 543, "sl_failed": 5, "positions_failed": 86, "positions_opened": 544}	2025-09-16 15:25:34.518343+00
1455	main_trader	HEALTHY	t	t	t	\N	544	0	0	\N	{"sl_set": 543, "sl_failed": 5, "positions_failed": 86, "positions_opened": 544}	2025-09-16 15:26:36.698253+00
1456	main_trader	HEALTHY	t	t	t	\N	544	0	0	\N	{"sl_set": 543, "sl_failed": 5, "positions_failed": 86, "positions_opened": 544}	2025-09-16 15:27:38.083427+00
1457	main_trader	HEALTHY	t	t	t	\N	544	0	0	\N	{"sl_set": 543, "sl_failed": 5, "positions_failed": 86, "positions_opened": 544}	2025-09-16 15:28:39.141893+00
1458	main_trader	HEALTHY	t	t	t	\N	544	0	0	\N	{"sl_set": 543, "sl_failed": 5, "positions_failed": 86, "positions_opened": 544}	2025-09-16 15:29:40.595886+00
1459	main_trader	HEALTHY	t	t	t	\N	544	0	0	\N	{"sl_set": 543, "sl_failed": 5, "positions_failed": 86, "positions_opened": 544}	2025-09-16 15:30:41.839468+00
1460	main_trader	HEALTHY	t	t	t	\N	544	0	0	\N	{"sl_set": 543, "sl_failed": 5, "positions_failed": 86, "positions_opened": 544}	2025-09-16 15:31:42.9128+00
1461	main_trader	HEALTHY	t	t	t	\N	544	0	0	\N	{"sl_set": 543, "sl_failed": 5, "positions_failed": 86, "positions_opened": 544}	2025-09-16 15:32:44.087013+00
1462	main_trader	HEALTHY	t	t	t	\N	544	0	0	\N	{"sl_set": 543, "sl_failed": 5, "positions_failed": 86, "positions_opened": 544}	2025-09-16 15:33:45.310309+00
1463	main_trader	HEALTHY	t	t	t	\N	544	0	0	\N	{"sl_set": 543, "sl_failed": 5, "positions_failed": 86, "positions_opened": 544}	2025-09-16 15:34:46.60812+00
1464	main_trader	HEALTHY	t	t	t	\N	547	0	0	\N	{"sl_set": 546, "sl_failed": 5, "positions_failed": 87, "positions_opened": 547}	2025-09-16 15:35:47.609142+00
1465	main_trader	HEALTHY	t	t	t	\N	548	0	0	\N	{"sl_set": 547, "sl_failed": 5, "positions_failed": 87, "positions_opened": 548}	2025-09-16 15:36:48.716285+00
1466	main_trader	HEALTHY	t	t	t	\N	548	0	0	\N	{"sl_set": 547, "sl_failed": 5, "positions_failed": 87, "positions_opened": 548}	2025-09-16 15:37:49.877431+00
1467	main_trader	HEALTHY	t	t	t	\N	548	0	0	\N	{"sl_set": 547, "sl_failed": 5, "positions_failed": 87, "positions_opened": 548}	2025-09-16 15:38:51.066138+00
1468	main_trader	HEALTHY	t	t	t	\N	548	0	0	\N	{"sl_set": 547, "sl_failed": 5, "positions_failed": 87, "positions_opened": 548}	2025-09-16 15:39:52.365196+00
1469	main_trader	HEALTHY	t	t	t	\N	548	0	0	\N	{"sl_set": 547, "sl_failed": 5, "positions_failed": 87, "positions_opened": 548}	2025-09-16 15:40:53.524818+00
1470	main_trader	HEALTHY	t	t	t	\N	548	0	0	\N	{"sl_set": 547, "sl_failed": 5, "positions_failed": 87, "positions_opened": 548}	2025-09-16 15:41:54.759748+00
1471	main_trader	HEALTHY	t	t	t	\N	548	0	0	\N	{"sl_set": 547, "sl_failed": 5, "positions_failed": 87, "positions_opened": 548}	2025-09-16 15:42:55.869677+00
1472	main_trader	HEALTHY	t	t	t	\N	548	0	0	\N	{"sl_set": 547, "sl_failed": 5, "positions_failed": 87, "positions_opened": 548}	2025-09-16 15:43:56.986955+00
1473	main_trader	HEALTHY	t	t	t	\N	548	0	0	\N	{"sl_set": 547, "sl_failed": 5, "positions_failed": 87, "positions_opened": 548}	2025-09-16 15:44:58.405943+00
1474	main_trader	HEALTHY	t	t	t	\N	548	0	0	\N	{"sl_set": 547, "sl_failed": 5, "positions_failed": 87, "positions_opened": 548}	2025-09-16 15:45:59.727998+00
1475	main_trader	HEALTHY	t	t	t	\N	548	0	0	\N	{"sl_set": 547, "sl_failed": 5, "positions_failed": 87, "positions_opened": 548}	2025-09-16 15:47:00.796947+00
1476	main_trader	HEALTHY	t	t	t	\N	548	0	0	\N	{"sl_set": 547, "sl_failed": 5, "positions_failed": 87, "positions_opened": 548}	2025-09-16 15:48:01.979554+00
1477	main_trader	HEALTHY	t	t	t	\N	548	0	0	\N	{"sl_set": 547, "sl_failed": 5, "positions_failed": 87, "positions_opened": 548}	2025-09-16 15:49:03.772128+00
1478	main_trader	HEALTHY	t	t	t	\N	548	0	0	\N	{"sl_set": 547, "sl_failed": 5, "positions_failed": 87, "positions_opened": 548}	2025-09-16 15:50:05.127944+00
1479	main_trader	HEALTHY	t	t	t	\N	553	0	0	\N	{"sl_set": 551, "sl_failed": 6, "positions_failed": 87, "positions_opened": 553}	2025-09-16 15:51:06.365777+00
1480	main_trader	HEALTHY	t	t	t	\N	556	0	0	\N	{"sl_set": 554, "sl_failed": 6, "positions_failed": 87, "positions_opened": 556}	2025-09-16 15:52:07.477538+00
1481	main_trader	HEALTHY	t	t	t	\N	556	0	0	\N	{"sl_set": 554, "sl_failed": 6, "positions_failed": 87, "positions_opened": 556}	2025-09-16 15:53:08.672337+00
1482	main_trader	HEALTHY	t	t	t	\N	556	0	0	\N	{"sl_set": 554, "sl_failed": 6, "positions_failed": 87, "positions_opened": 556}	2025-09-16 15:54:09.821328+00
1483	main_trader	HEALTHY	t	t	t	\N	556	0	0	\N	{"sl_set": 554, "sl_failed": 6, "positions_failed": 87, "positions_opened": 556}	2025-09-16 15:55:11.60601+00
1484	main_trader	HEALTHY	t	t	t	\N	556	0	0	\N	{"sl_set": 554, "sl_failed": 6, "positions_failed": 87, "positions_opened": 556}	2025-09-16 15:56:12.720735+00
1485	main_trader	HEALTHY	t	t	t	\N	556	0	0	\N	{"sl_set": 554, "sl_failed": 6, "positions_failed": 87, "positions_opened": 556}	2025-09-16 15:57:13.891664+00
1486	main_trader	HEALTHY	t	t	t	\N	556	0	0	\N	{"sl_set": 554, "sl_failed": 6, "positions_failed": 87, "positions_opened": 556}	2025-09-16 15:58:15.026239+00
1487	main_trader	HEALTHY	t	t	t	\N	556	0	0	\N	{"sl_set": 554, "sl_failed": 6, "positions_failed": 87, "positions_opened": 556}	2025-09-16 15:59:16.232483+00
1488	main_trader	HEALTHY	t	t	t	\N	556	0	0	\N	{"sl_set": 554, "sl_failed": 6, "positions_failed": 87, "positions_opened": 556}	2025-09-16 16:00:17.656261+00
1489	main_trader	HEALTHY	t	t	t	\N	556	0	0	\N	{"sl_set": 554, "sl_failed": 6, "positions_failed": 87, "positions_opened": 556}	2025-09-16 16:01:18.981715+00
1490	main_trader	HEALTHY	t	t	t	\N	556	0	0	\N	{"sl_set": 554, "sl_failed": 6, "positions_failed": 87, "positions_opened": 556}	2025-09-16 16:02:20.096369+00
1491	main_trader	HEALTHY	t	t	t	\N	556	0	0	\N	{"sl_set": 554, "sl_failed": 6, "positions_failed": 87, "positions_opened": 556}	2025-09-16 16:03:21.184672+00
1492	main_trader	HEALTHY	t	t	t	\N	556	0	0	\N	{"sl_set": 554, "sl_failed": 6, "positions_failed": 87, "positions_opened": 556}	2025-09-16 16:04:22.25159+00
1493	main_trader	HEALTHY	t	t	t	\N	556	0	0	\N	{"sl_set": 554, "sl_failed": 6, "positions_failed": 87, "positions_opened": 556}	2025-09-16 16:05:23.566664+00
1494	main_trader	HEALTHY	t	t	t	\N	557	0	0	\N	{"sl_set": 555, "sl_failed": 6, "positions_failed": 87, "positions_opened": 557}	2025-09-16 16:06:24.554368+00
1495	main_trader	HEALTHY	t	t	t	\N	558	0	0	\N	{"sl_set": 556, "sl_failed": 6, "positions_failed": 87, "positions_opened": 558}	2025-09-16 16:07:25.844033+00
1496	main_trader	HEALTHY	t	t	t	\N	558	0	0	\N	{"sl_set": 556, "sl_failed": 6, "positions_failed": 87, "positions_opened": 558}	2025-09-16 16:08:27.029658+00
1497	main_trader	HEALTHY	t	t	t	\N	558	0	0	\N	{"sl_set": 556, "sl_failed": 6, "positions_failed": 87, "positions_opened": 558}	2025-09-16 16:09:28.196163+00
1498	main_trader	HEALTHY	t	t	t	\N	558	0	0	\N	{"sl_set": 556, "sl_failed": 6, "positions_failed": 87, "positions_opened": 558}	2025-09-16 16:10:29.289487+00
1499	main_trader	HEALTHY	t	t	t	\N	558	0	0	\N	{"sl_set": 556, "sl_failed": 6, "positions_failed": 87, "positions_opened": 558}	2025-09-16 16:11:30.480504+00
1500	main_trader	HEALTHY	t	t	t	\N	558	0	0	\N	{"sl_set": 556, "sl_failed": 6, "positions_failed": 87, "positions_opened": 558}	2025-09-16 16:12:31.880265+00
1501	main_trader	HEALTHY	t	t	t	\N	558	0	0	\N	{"sl_set": 556, "sl_failed": 6, "positions_failed": 87, "positions_opened": 558}	2025-09-16 16:13:33.07965+00
1502	main_trader	HEALTHY	t	t	t	\N	558	0	0	\N	{"sl_set": 556, "sl_failed": 6, "positions_failed": 87, "positions_opened": 558}	2025-09-16 16:14:34.297476+00
1503	main_trader	HEALTHY	t	t	t	\N	558	0	0	\N	{"sl_set": 556, "sl_failed": 6, "positions_failed": 87, "positions_opened": 558}	2025-09-16 16:15:35.624353+00
1504	main_trader	HEALTHY	t	t	t	\N	558	0	0	\N	{"sl_set": 556, "sl_failed": 6, "positions_failed": 87, "positions_opened": 558}	2025-09-16 16:16:36.784861+00
1505	main_trader	HEALTHY	t	t	t	\N	558	0	0	\N	{"sl_set": 556, "sl_failed": 6, "positions_failed": 87, "positions_opened": 558}	2025-09-16 16:17:38.411975+00
1506	main_trader	HEALTHY	t	t	t	\N	558	0	0	\N	{"sl_set": 556, "sl_failed": 6, "positions_failed": 87, "positions_opened": 558}	2025-09-16 16:18:39.575166+00
1507	main_trader	HEALTHY	t	t	t	\N	558	0	0	\N	{"sl_set": 556, "sl_failed": 6, "positions_failed": 87, "positions_opened": 558}	2025-09-16 16:19:40.800593+00
1508	main_trader	HEALTHY	t	t	t	\N	560	0	0	\N	{"sl_set": 559, "sl_failed": 6, "positions_failed": 87, "positions_opened": 561}	2025-09-16 16:20:42.35715+00
1509	main_trader	HEALTHY	t	t	t	\N	561	0	0	\N	{"sl_set": 559, "sl_failed": 6, "positions_failed": 87, "positions_opened": 561}	2025-09-16 16:21:43.578195+00
1510	main_trader	HEALTHY	t	t	t	\N	561	0	0	\N	{"sl_set": 559, "sl_failed": 6, "positions_failed": 87, "positions_opened": 561}	2025-09-16 16:22:44.879132+00
1511	main_trader	HEALTHY	t	t	t	\N	561	0	0	\N	{"sl_set": 559, "sl_failed": 6, "positions_failed": 87, "positions_opened": 561}	2025-09-16 16:23:46.129935+00
1512	main_trader	HEALTHY	t	t	t	\N	561	0	0	\N	{"sl_set": 559, "sl_failed": 6, "positions_failed": 87, "positions_opened": 561}	2025-09-16 16:24:47.290273+00
1513	main_trader	HEALTHY	t	t	t	\N	561	0	0	\N	{"sl_set": 559, "sl_failed": 6, "positions_failed": 87, "positions_opened": 561}	2025-09-16 16:25:48.522221+00
1514	main_trader	HEALTHY	t	t	t	\N	561	0	0	\N	{"sl_set": 559, "sl_failed": 6, "positions_failed": 87, "positions_opened": 561}	2025-09-16 16:26:49.596855+00
1515	main_trader	HEALTHY	t	t	t	\N	561	0	0	\N	{"sl_set": 559, "sl_failed": 6, "positions_failed": 87, "positions_opened": 561}	2025-09-16 16:27:51.010478+00
1516	main_trader	HEALTHY	t	t	t	\N	561	0	0	\N	{"sl_set": 559, "sl_failed": 6, "positions_failed": 87, "positions_opened": 561}	2025-09-16 16:28:52.164123+00
1517	main_trader	HEALTHY	t	t	t	\N	561	0	0	\N	{"sl_set": 559, "sl_failed": 6, "positions_failed": 87, "positions_opened": 561}	2025-09-16 16:29:53.242435+00
1518	main_trader	HEALTHY	t	t	t	\N	561	0	0	\N	{"sl_set": 559, "sl_failed": 6, "positions_failed": 87, "positions_opened": 561}	2025-09-16 16:30:54.458403+00
1519	main_trader	HEALTHY	t	t	t	\N	561	0	0	\N	{"sl_set": 559, "sl_failed": 6, "positions_failed": 87, "positions_opened": 561}	2025-09-16 16:31:56.208471+00
1520	main_trader	HEALTHY	t	t	t	\N	561	0	0	\N	{"sl_set": 559, "sl_failed": 6, "positions_failed": 87, "positions_opened": 561}	2025-09-16 16:32:57.683302+00
1521	main_trader	HEALTHY	t	t	t	\N	561	0	0	\N	{"sl_set": 559, "sl_failed": 6, "positions_failed": 87, "positions_opened": 561}	2025-09-16 16:33:58.959746+00
1522	main_trader	HEALTHY	t	t	t	\N	561	0	0	\N	{"sl_set": 559, "sl_failed": 6, "positions_failed": 87, "positions_opened": 561}	2025-09-16 16:35:00.02402+00
1523	main_trader	HEALTHY	t	t	t	\N	561	0	0	\N	{"sl_set": 559, "sl_failed": 6, "positions_failed": 87, "positions_opened": 561}	2025-09-16 16:36:01.258615+00
1524	main_trader	HEALTHY	t	t	t	\N	562	0	0	\N	{"sl_set": 560, "sl_failed": 6, "positions_failed": 87, "positions_opened": 562}	2025-09-16 16:37:02.374044+00
1525	main_trader	HEALTHY	t	t	t	\N	562	0	0	\N	{"sl_set": 560, "sl_failed": 6, "positions_failed": 87, "positions_opened": 562}	2025-09-16 16:38:03.95787+00
1526	main_trader	HEALTHY	t	t	t	\N	562	0	0	\N	{"sl_set": 560, "sl_failed": 6, "positions_failed": 87, "positions_opened": 562}	2025-09-16 16:39:05.110767+00
1527	main_trader	HEALTHY	t	t	t	\N	562	0	0	\N	{"sl_set": 560, "sl_failed": 6, "positions_failed": 87, "positions_opened": 562}	2025-09-16 16:40:06.183675+00
1528	main_trader	HEALTHY	t	t	t	\N	562	0	0	\N	{"sl_set": 560, "sl_failed": 6, "positions_failed": 87, "positions_opened": 562}	2025-09-16 16:41:07.401435+00
1529	main_trader	HEALTHY	t	t	t	\N	562	0	0	\N	{"sl_set": 560, "sl_failed": 6, "positions_failed": 87, "positions_opened": 562}	2025-09-16 16:42:08.786801+00
1530	main_trader	HEALTHY	t	t	t	\N	562	0	0	\N	{"sl_set": 560, "sl_failed": 6, "positions_failed": 87, "positions_opened": 562}	2025-09-16 16:43:10.20382+00
1531	main_trader	HEALTHY	t	t	t	\N	562	0	0	\N	{"sl_set": 560, "sl_failed": 6, "positions_failed": 87, "positions_opened": 562}	2025-09-16 16:44:12.069553+00
1532	main_trader	HEALTHY	t	t	t	\N	562	0	0	\N	{"sl_set": 560, "sl_failed": 6, "positions_failed": 87, "positions_opened": 562}	2025-09-16 16:45:13.317331+00
1533	main_trader	HEALTHY	t	t	t	\N	562	0	0	\N	{"sl_set": 560, "sl_failed": 6, "positions_failed": 87, "positions_opened": 562}	2025-09-16 16:46:14.375081+00
1534	main_trader	HEALTHY	t	t	t	\N	562	0	0	\N	{"sl_set": 560, "sl_failed": 6, "positions_failed": 87, "positions_opened": 562}	2025-09-16 16:47:15.575737+00
1535	main_trader	HEALTHY	t	t	t	\N	562	0	0	\N	{"sl_set": 560, "sl_failed": 6, "positions_failed": 87, "positions_opened": 562}	2025-09-16 16:48:16.679321+00
1536	main_trader	HEALTHY	t	t	t	\N	562	0	0	\N	{"sl_set": 560, "sl_failed": 6, "positions_failed": 87, "positions_opened": 562}	2025-09-16 16:49:17.96361+00
1537	main_trader	HEALTHY	t	t	t	\N	562	0	0	\N	{"sl_set": 560, "sl_failed": 6, "positions_failed": 87, "positions_opened": 562}	2025-09-16 16:50:19.214148+00
1538	main_trader	HEALTHY	t	t	t	\N	562	0	0	\N	{"sl_set": 560, "sl_failed": 6, "positions_failed": 87, "positions_opened": 562}	2025-09-16 16:51:20.302127+00
1539	main_trader	HEALTHY	t	t	t	\N	564	0	0	\N	{"sl_set": 562, "sl_failed": 6, "positions_failed": 88, "positions_opened": 564}	2025-09-16 16:52:21.451354+00
1540	main_trader	HEALTHY	t	t	t	\N	564	0	0	\N	{"sl_set": 562, "sl_failed": 6, "positions_failed": 88, "positions_opened": 564}	2025-09-16 16:53:22.611238+00
1541	main_trader	HEALTHY	t	t	t	\N	564	0	0	\N	{"sl_set": 562, "sl_failed": 6, "positions_failed": 88, "positions_opened": 564}	2025-09-16 16:54:24.03629+00
1542	main_trader	HEALTHY	t	t	t	\N	564	0	0	\N	{"sl_set": 562, "sl_failed": 6, "positions_failed": 88, "positions_opened": 564}	2025-09-16 16:55:25.355994+00
1543	main_trader	HEALTHY	t	t	t	\N	564	0	0	\N	{"sl_set": 562, "sl_failed": 6, "positions_failed": 88, "positions_opened": 564}	2025-09-16 16:56:26.576206+00
1544	main_trader	HEALTHY	t	t	t	\N	564	0	0	\N	{"sl_set": 562, "sl_failed": 6, "positions_failed": 88, "positions_opened": 564}	2025-09-16 16:57:27.640597+00
1545	main_trader	HEALTHY	t	t	t	\N	564	0	0	\N	{"sl_set": 562, "sl_failed": 6, "positions_failed": 88, "positions_opened": 564}	2025-09-16 16:58:28.786504+00
1546	main_trader	HEALTHY	t	t	t	\N	564	0	0	\N	{"sl_set": 562, "sl_failed": 6, "positions_failed": 88, "positions_opened": 564}	2025-09-16 16:59:30.642634+00
1547	main_trader	HEALTHY	t	t	t	\N	564	0	0	\N	{"sl_set": 562, "sl_failed": 6, "positions_failed": 88, "positions_opened": 564}	2025-09-16 17:00:31.885804+00
1548	main_trader	HEALTHY	t	t	t	\N	564	0	0	\N	{"sl_set": 562, "sl_failed": 6, "positions_failed": 88, "positions_opened": 564}	2025-09-16 17:01:33.296718+00
1549	main_trader	HEALTHY	t	t	t	\N	564	0	0	\N	{"sl_set": 562, "sl_failed": 6, "positions_failed": 88, "positions_opened": 564}	2025-09-16 17:02:34.466571+00
1550	main_trader	HEALTHY	t	t	t	\N	564	0	0	\N	{"sl_set": 562, "sl_failed": 6, "positions_failed": 88, "positions_opened": 564}	2025-09-16 17:03:35.530843+00
1551	main_trader	HEALTHY	t	t	t	\N	564	0	0	\N	{"sl_set": 562, "sl_failed": 6, "positions_failed": 88, "positions_opened": 564}	2025-09-16 17:04:37.12471+00
1552	main_trader	HEALTHY	t	t	t	\N	564	0	0	\N	{"sl_set": 562, "sl_failed": 6, "positions_failed": 88, "positions_opened": 564}	2025-09-16 17:05:38.395037+00
1553	main_trader	HEALTHY	t	t	t	\N	565	0	0	\N	{"sl_set": 563, "sl_failed": 6, "positions_failed": 88, "positions_opened": 565}	2025-09-16 17:06:40.608263+00
1554	main_trader	HEALTHY	t	t	t	\N	569	0	0	\N	{"sl_set": 567, "sl_failed": 6, "positions_failed": 88, "positions_opened": 569}	2025-09-16 17:07:41.890026+00
1555	main_trader	HEALTHY	t	t	t	\N	569	0	0	\N	{"sl_set": 567, "sl_failed": 6, "positions_failed": 88, "positions_opened": 569}	2025-09-16 17:08:42.992572+00
1556	main_trader	HEALTHY	t	t	t	\N	569	0	0	\N	{"sl_set": 567, "sl_failed": 6, "positions_failed": 88, "positions_opened": 569}	2025-09-16 17:09:44.047019+00
1557	main_trader	HEALTHY	t	t	t	\N	569	0	0	\N	{"sl_set": 567, "sl_failed": 6, "positions_failed": 88, "positions_opened": 569}	2025-09-16 17:10:45.212696+00
1558	main_trader	HEALTHY	t	t	t	\N	569	0	0	\N	{"sl_set": 567, "sl_failed": 6, "positions_failed": 88, "positions_opened": 569}	2025-09-16 17:11:46.741997+00
1559	main_trader	HEALTHY	t	t	t	\N	569	0	0	\N	{"sl_set": 567, "sl_failed": 6, "positions_failed": 88, "positions_opened": 569}	2025-09-16 17:12:48.011754+00
1560	main_trader	HEALTHY	t	t	t	\N	569	0	0	\N	{"sl_set": 567, "sl_failed": 6, "positions_failed": 88, "positions_opened": 569}	2025-09-16 17:13:49.196097+00
1561	main_trader	HEALTHY	t	t	t	\N	569	0	0	\N	{"sl_set": 567, "sl_failed": 6, "positions_failed": 88, "positions_opened": 569}	2025-09-16 17:14:50.348357+00
1562	main_trader	HEALTHY	t	t	t	\N	569	0	0	\N	{"sl_set": 567, "sl_failed": 6, "positions_failed": 88, "positions_opened": 569}	2025-09-16 17:15:51.410272+00
1563	main_trader	HEALTHY	t	t	t	\N	569	0	0	\N	{"sl_set": 567, "sl_failed": 6, "positions_failed": 88, "positions_opened": 569}	2025-09-16 17:16:52.746804+00
1564	main_trader	HEALTHY	t	t	t	\N	569	0	0	\N	{"sl_set": 567, "sl_failed": 6, "positions_failed": 88, "positions_opened": 569}	2025-09-16 17:17:53.92178+00
1565	main_trader	HEALTHY	t	t	t	\N	569	0	0	\N	{"sl_set": 567, "sl_failed": 6, "positions_failed": 88, "positions_opened": 569}	2025-09-16 17:18:55.117417+00
1566	main_trader	HEALTHY	t	t	t	\N	569	0	0	\N	{"sl_set": 567, "sl_failed": 6, "positions_failed": 88, "positions_opened": 569}	2025-09-16 17:19:56.312048+00
1567	main_trader	HEALTHY	t	t	t	\N	569	0	0	\N	{"sl_set": 567, "sl_failed": 6, "positions_failed": 88, "positions_opened": 569}	2025-09-16 17:20:57.377952+00
1568	main_trader	HEALTHY	t	t	t	\N	572	0	0	\N	{"sl_set": 570, "sl_failed": 6, "positions_failed": 88, "positions_opened": 572}	2025-09-16 17:21:58.705584+00
1569	main_trader	HEALTHY	t	t	t	\N	572	0	0	\N	{"sl_set": 570, "sl_failed": 6, "positions_failed": 88, "positions_opened": 572}	2025-09-16 17:22:59.884993+00
1570	main_trader	HEALTHY	t	t	t	\N	572	0	0	\N	{"sl_set": 570, "sl_failed": 6, "positions_failed": 88, "positions_opened": 572}	2025-09-16 17:24:01.059148+00
1571	main_trader	HEALTHY	t	t	t	\N	572	0	0	\N	{"sl_set": 570, "sl_failed": 6, "positions_failed": 88, "positions_opened": 572}	2025-09-16 17:25:02.188356+00
1572	main_trader	HEALTHY	t	t	t	\N	572	0	0	\N	{"sl_set": 570, "sl_failed": 6, "positions_failed": 88, "positions_opened": 572}	2025-09-16 17:26:03.270631+00
1573	main_trader	HEALTHY	t	t	t	\N	572	0	0	\N	{"sl_set": 570, "sl_failed": 6, "positions_failed": 88, "positions_opened": 572}	2025-09-16 17:27:05.156371+00
1574	main_trader	HEALTHY	t	t	t	\N	572	0	0	\N	{"sl_set": 570, "sl_failed": 6, "positions_failed": 88, "positions_opened": 572}	2025-09-16 17:28:06.443063+00
1575	main_trader	HEALTHY	t	t	t	\N	572	0	0	\N	{"sl_set": 570, "sl_failed": 6, "positions_failed": 88, "positions_opened": 572}	2025-09-16 17:29:07.641137+00
1576	main_trader	HEALTHY	t	t	t	\N	572	0	0	\N	{"sl_set": 570, "sl_failed": 6, "positions_failed": 88, "positions_opened": 572}	2025-09-16 17:30:08.73323+00
1577	main_trader	HEALTHY	t	t	t	\N	572	0	0	\N	{"sl_set": 570, "sl_failed": 6, "positions_failed": 88, "positions_opened": 572}	2025-09-16 17:31:09.806959+00
1578	main_trader	HEALTHY	t	t	t	\N	572	0	0	\N	{"sl_set": 570, "sl_failed": 6, "positions_failed": 88, "positions_opened": 572}	2025-09-16 17:32:11.489714+00
1579	main_trader	HEALTHY	t	t	t	\N	572	0	0	\N	{"sl_set": 570, "sl_failed": 6, "positions_failed": 88, "positions_opened": 572}	2025-09-16 17:33:12.748894+00
1580	main_trader	HEALTHY	t	t	t	\N	572	0	0	\N	{"sl_set": 570, "sl_failed": 6, "positions_failed": 88, "positions_opened": 572}	2025-09-16 17:34:13.90534+00
1581	main_trader	HEALTHY	t	t	t	\N	572	0	0	\N	{"sl_set": 570, "sl_failed": 6, "positions_failed": 88, "positions_opened": 572}	2025-09-16 17:35:15.015552+00
1582	main_trader	HEALTHY	t	t	t	\N	572	0	0	\N	{"sl_set": 570, "sl_failed": 6, "positions_failed": 88, "positions_opened": 572}	2025-09-16 17:36:16.144356+00
1583	main_trader	HEALTHY	t	t	t	\N	574	0	0	\N	{"sl_set": 572, "sl_failed": 6, "positions_failed": 88, "positions_opened": 574}	2025-09-16 17:37:17.33661+00
1584	main_trader	HEALTHY	t	t	t	\N	574	0	0	\N	{"sl_set": 572, "sl_failed": 6, "positions_failed": 88, "positions_opened": 574}	2025-09-16 17:38:18.532139+00
1585	main_trader	HEALTHY	t	t	t	\N	574	0	0	\N	{"sl_set": 572, "sl_failed": 6, "positions_failed": 88, "positions_opened": 574}	2025-09-16 17:39:19.637619+00
1586	main_trader	HEALTHY	t	t	t	\N	574	0	0	\N	{"sl_set": 572, "sl_failed": 6, "positions_failed": 88, "positions_opened": 574}	2025-09-16 17:40:20.806426+00
1587	main_trader	HEALTHY	t	t	t	\N	574	0	0	\N	{"sl_set": 572, "sl_failed": 6, "positions_failed": 88, "positions_opened": 574}	2025-09-16 17:41:21.889168+00
1588	main_trader	HEALTHY	t	t	t	\N	574	0	0	\N	{"sl_set": 572, "sl_failed": 6, "positions_failed": 88, "positions_opened": 574}	2025-09-16 17:42:23.201799+00
1589	main_trader	HEALTHY	t	t	t	\N	574	0	0	\N	{"sl_set": 572, "sl_failed": 6, "positions_failed": 88, "positions_opened": 574}	2025-09-16 17:43:24.44+00
1590	main_trader	HEALTHY	t	t	t	\N	574	0	0	\N	{"sl_set": 572, "sl_failed": 6, "positions_failed": 88, "positions_opened": 574}	2025-09-16 17:44:25.623662+00
1591	main_trader	HEALTHY	t	t	t	\N	574	0	0	\N	{"sl_set": 572, "sl_failed": 6, "positions_failed": 88, "positions_opened": 574}	2025-09-16 17:45:26.782661+00
1592	main_trader	HEALTHY	t	t	t	\N	574	0	0	\N	{"sl_set": 572, "sl_failed": 6, "positions_failed": 88, "positions_opened": 574}	2025-09-16 17:46:27.936273+00
1593	main_trader	HEALTHY	t	t	t	\N	574	0	0	\N	{"sl_set": 572, "sl_failed": 6, "positions_failed": 88, "positions_opened": 574}	2025-09-16 17:47:29.234126+00
1594	main_trader	HEALTHY	t	t	t	\N	574	0	0	\N	{"sl_set": 572, "sl_failed": 6, "positions_failed": 88, "positions_opened": 574}	2025-09-16 17:48:30.782981+00
1595	main_trader	HEALTHY	t	t	t	\N	574	0	0	\N	{"sl_set": 572, "sl_failed": 6, "positions_failed": 88, "positions_opened": 574}	2025-09-16 17:49:31.976598+00
1596	main_trader	HEALTHY	t	t	t	\N	574	0	0	\N	{"sl_set": 572, "sl_failed": 6, "positions_failed": 88, "positions_opened": 574}	2025-09-16 17:50:33.115471+00
1597	main_trader	HEALTHY	t	t	t	\N	576	0	0	\N	{"sl_set": 574, "sl_failed": 6, "positions_failed": 88, "positions_opened": 576}	2025-09-16 17:51:34.302588+00
1598	main_trader	HEALTHY	t	t	t	\N	577	0	0	\N	{"sl_set": 575, "sl_failed": 6, "positions_failed": 89, "positions_opened": 577}	2025-09-16 17:52:35.586243+00
1599	main_trader	HEALTHY	t	t	t	\N	577	0	0	\N	{"sl_set": 575, "sl_failed": 6, "positions_failed": 89, "positions_opened": 577}	2025-09-16 17:53:36.718543+00
1600	main_trader	HEALTHY	t	t	t	\N	577	0	0	\N	{"sl_set": 575, "sl_failed": 6, "positions_failed": 89, "positions_opened": 577}	2025-09-16 17:54:38.37937+00
1601	main_trader	HEALTHY	t	t	t	\N	577	0	0	\N	{"sl_set": 575, "sl_failed": 6, "positions_failed": 89, "positions_opened": 577}	2025-09-16 17:55:39.572256+00
1602	main_trader	HEALTHY	t	t	t	\N	577	0	0	\N	{"sl_set": 575, "sl_failed": 6, "positions_failed": 89, "positions_opened": 577}	2025-09-16 17:56:40.73114+00
1603	main_trader	HEALTHY	t	t	t	\N	577	0	0	\N	{"sl_set": 575, "sl_failed": 6, "positions_failed": 89, "positions_opened": 577}	2025-09-16 17:57:42.054742+00
1604	main_trader	HEALTHY	t	t	t	\N	577	0	0	\N	{"sl_set": 575, "sl_failed": 6, "positions_failed": 89, "positions_opened": 577}	2025-09-16 17:58:43.221351+00
1605	main_trader	HEALTHY	t	t	t	\N	577	0	0	\N	{"sl_set": 575, "sl_failed": 6, "positions_failed": 89, "positions_opened": 577}	2025-09-16 17:59:44.37715+00
1606	main_trader	HEALTHY	t	t	t	\N	577	0	0	\N	{"sl_set": 575, "sl_failed": 6, "positions_failed": 89, "positions_opened": 577}	2025-09-16 18:00:45.508555+00
1607	main_trader	HEALTHY	t	t	t	\N	577	0	0	\N	{"sl_set": 575, "sl_failed": 6, "positions_failed": 89, "positions_opened": 577}	2025-09-16 18:01:46.665053+00
1608	main_trader	HEALTHY	t	t	t	\N	577	0	0	\N	{"sl_set": 575, "sl_failed": 6, "positions_failed": 89, "positions_opened": 577}	2025-09-16 18:02:48.125965+00
1609	main_trader	HEALTHY	t	t	t	\N	577	0	0	\N	{"sl_set": 575, "sl_failed": 6, "positions_failed": 89, "positions_opened": 577}	2025-09-16 18:03:49.292956+00
1610	main_trader	HEALTHY	t	t	t	\N	577	0	0	\N	{"sl_set": 575, "sl_failed": 6, "positions_failed": 89, "positions_opened": 577}	2025-09-16 18:04:50.441307+00
1611	main_trader	HEALTHY	t	t	t	\N	577	0	0	\N	{"sl_set": 575, "sl_failed": 6, "positions_failed": 89, "positions_opened": 577}	2025-09-16 18:05:51.545947+00
1612	main_trader	HEALTHY	t	t	t	\N	579	0	0	\N	{"sl_set": 577, "sl_failed": 6, "positions_failed": 89, "positions_opened": 579}	2025-09-16 18:06:52.594418+00
1613	main_trader	HEALTHY	t	t	t	\N	582	0	0	\N	{"sl_set": 580, "sl_failed": 6, "positions_failed": 90, "positions_opened": 582}	2025-09-16 18:07:54.094408+00
1614	main_trader	HEALTHY	t	t	t	\N	582	0	0	\N	{"sl_set": 580, "sl_failed": 6, "positions_failed": 90, "positions_opened": 582}	2025-09-16 18:08:55.258819+00
1615	main_trader	HEALTHY	t	t	t	\N	582	0	0	\N	{"sl_set": 580, "sl_failed": 6, "positions_failed": 90, "positions_opened": 582}	2025-09-16 18:09:56.404235+00
1616	main_trader	HEALTHY	t	t	t	\N	582	0	0	\N	{"sl_set": 580, "sl_failed": 6, "positions_failed": 90, "positions_opened": 582}	2025-09-16 18:10:57.475278+00
1617	main_trader	HEALTHY	t	t	t	\N	582	0	0	\N	{"sl_set": 580, "sl_failed": 6, "positions_failed": 90, "positions_opened": 582}	2025-09-16 18:11:58.615367+00
1618	main_trader	HEALTHY	t	t	t	\N	582	0	0	\N	{"sl_set": 580, "sl_failed": 6, "positions_failed": 90, "positions_opened": 582}	2025-09-16 18:13:00.46455+00
1619	main_trader	HEALTHY	t	t	t	\N	582	0	0	\N	{"sl_set": 580, "sl_failed": 6, "positions_failed": 90, "positions_opened": 582}	2025-09-16 18:14:01.648694+00
1620	main_trader	HEALTHY	t	t	t	\N	582	0	0	\N	{"sl_set": 580, "sl_failed": 6, "positions_failed": 90, "positions_opened": 582}	2025-09-16 18:15:02.788937+00
1621	main_trader	HEALTHY	t	t	t	\N	582	0	0	\N	{"sl_set": 580, "sl_failed": 6, "positions_failed": 90, "positions_opened": 582}	2025-09-16 18:16:03.937809+00
1622	main_trader	HEALTHY	t	t	t	\N	582	0	0	\N	{"sl_set": 580, "sl_failed": 6, "positions_failed": 90, "positions_opened": 582}	2025-09-16 18:17:05.092806+00
1623	main_trader	HEALTHY	t	t	t	\N	582	0	0	\N	{"sl_set": 580, "sl_failed": 6, "positions_failed": 90, "positions_opened": 582}	2025-09-16 18:18:06.49965+00
1624	main_trader	HEALTHY	t	t	t	\N	582	0	0	\N	{"sl_set": 580, "sl_failed": 6, "positions_failed": 90, "positions_opened": 582}	2025-09-16 18:19:07.623855+00
1625	main_trader	HEALTHY	t	t	t	\N	582	0	0	\N	{"sl_set": 580, "sl_failed": 6, "positions_failed": 90, "positions_opened": 583}	2025-09-16 18:20:08.514043+00
1626	main_trader	HEALTHY	t	t	t	\N	588	0	0	\N	{"sl_set": 587, "sl_failed": 6, "positions_failed": 90, "positions_opened": 589}	2025-09-16 18:21:09.405973+00
1627	main_trader	HEALTHY	t	t	t	\N	589	0	0	\N	{"sl_set": 587, "sl_failed": 6, "positions_failed": 90, "positions_opened": 589}	2025-09-16 18:22:10.455131+00
1628	main_trader	HEALTHY	t	t	t	\N	589	0	0	\N	{"sl_set": 587, "sl_failed": 6, "positions_failed": 90, "positions_opened": 589}	2025-09-16 18:23:11.746198+00
1629	main_trader	HEALTHY	t	t	t	\N	589	0	0	\N	{"sl_set": 587, "sl_failed": 6, "positions_failed": 90, "positions_opened": 589}	2025-09-16 18:24:13.195626+00
1630	main_trader	HEALTHY	t	t	t	\N	589	0	0	\N	{"sl_set": 587, "sl_failed": 6, "positions_failed": 90, "positions_opened": 589}	2025-09-16 18:25:14.371645+00
1631	main_trader	HEALTHY	t	t	t	\N	589	0	0	\N	{"sl_set": 587, "sl_failed": 6, "positions_failed": 90, "positions_opened": 589}	2025-09-16 18:26:15.430111+00
1632	main_trader	HEALTHY	t	t	t	\N	589	0	0	\N	{"sl_set": 587, "sl_failed": 6, "positions_failed": 90, "positions_opened": 589}	2025-09-16 18:27:17.119788+00
1633	main_trader	HEALTHY	t	t	t	\N	589	0	0	\N	{"sl_set": 587, "sl_failed": 6, "positions_failed": 90, "positions_opened": 589}	2025-09-16 18:28:18.355943+00
1634	main_trader	HEALTHY	t	t	t	\N	589	0	0	\N	{"sl_set": 587, "sl_failed": 6, "positions_failed": 90, "positions_opened": 589}	2025-09-16 18:29:19.405944+00
1635	main_trader	HEALTHY	t	t	t	\N	589	0	0	\N	{"sl_set": 587, "sl_failed": 6, "positions_failed": 90, "positions_opened": 589}	2025-09-16 18:30:20.858504+00
1636	main_trader	HEALTHY	t	t	t	\N	589	0	0	\N	{"sl_set": 587, "sl_failed": 6, "positions_failed": 90, "positions_opened": 589}	2025-09-16 18:31:22.031367+00
1637	main_trader	HEALTHY	t	t	t	\N	589	0	0	\N	{"sl_set": 587, "sl_failed": 6, "positions_failed": 90, "positions_opened": 589}	2025-09-16 18:32:23.324475+00
1638	main_trader	HEALTHY	t	t	t	\N	589	0	0	\N	{"sl_set": 587, "sl_failed": 6, "positions_failed": 90, "positions_opened": 589}	2025-09-16 18:33:24.946869+00
1639	main_trader	HEALTHY	t	t	t	\N	589	0	0	\N	{"sl_set": 587, "sl_failed": 6, "positions_failed": 90, "positions_opened": 589}	2025-09-16 18:34:26.60704+00
1640	main_trader	HEALTHY	t	t	t	\N	589	0	0	\N	{"sl_set": 587, "sl_failed": 6, "positions_failed": 90, "positions_opened": 589}	2025-09-16 18:35:28.159449+00
1641	main_trader	HEALTHY	t	t	t	\N	589	0	0	\N	{"sl_set": 588, "sl_failed": 6, "positions_failed": 90, "positions_opened": 590}	2025-09-16 18:36:29.712106+00
1642	main_trader	HEALTHY	t	t	t	\N	591	0	0	\N	{"sl_set": 589, "sl_failed": 6, "positions_failed": 90, "positions_opened": 591}	2025-09-16 18:37:31.3619+00
1643	main_trader	HEALTHY	t	t	t	\N	591	0	0	\N	{"sl_set": 589, "sl_failed": 6, "positions_failed": 90, "positions_opened": 591}	2025-09-16 18:38:33.201964+00
1644	main_trader	HEALTHY	t	t	t	\N	591	0	0	\N	{"sl_set": 589, "sl_failed": 6, "positions_failed": 90, "positions_opened": 591}	2025-09-16 18:39:34.86154+00
1645	main_trader	HEALTHY	t	t	t	\N	591	0	0	\N	{"sl_set": 589, "sl_failed": 6, "positions_failed": 90, "positions_opened": 591}	2025-09-16 18:40:36.557952+00
1646	main_trader	HEALTHY	t	t	t	\N	591	0	0	\N	{"sl_set": 589, "sl_failed": 6, "positions_failed": 90, "positions_opened": 591}	2025-09-16 18:41:38.207614+00
1647	main_trader	HEALTHY	t	t	t	\N	591	0	0	\N	{"sl_set": 589, "sl_failed": 6, "positions_failed": 90, "positions_opened": 591}	2025-09-16 18:42:40.008031+00
1648	main_trader	HEALTHY	t	t	t	\N	591	0	0	\N	{"sl_set": 589, "sl_failed": 6, "positions_failed": 90, "positions_opened": 591}	2025-09-16 18:43:41.720223+00
1649	main_trader	HEALTHY	t	t	t	\N	591	0	0	\N	{"sl_set": 589, "sl_failed": 6, "positions_failed": 90, "positions_opened": 591}	2025-09-16 18:44:42.830079+00
1650	main_trader	HEALTHY	t	t	t	\N	591	0	0	\N	{"sl_set": 589, "sl_failed": 6, "positions_failed": 90, "positions_opened": 591}	2025-09-16 18:45:44.397777+00
1651	main_trader	HEALTHY	t	t	t	\N	591	0	0	\N	{"sl_set": 589, "sl_failed": 6, "positions_failed": 90, "positions_opened": 591}	2025-09-16 18:46:46.988354+00
1652	main_trader	HEALTHY	t	t	t	\N	591	0	0	\N	{"sl_set": 589, "sl_failed": 6, "positions_failed": 90, "positions_opened": 591}	2025-09-16 18:47:49.392885+00
1653	main_trader	HEALTHY	t	t	t	\N	591	0	0	\N	{"sl_set": 589, "sl_failed": 6, "positions_failed": 90, "positions_opened": 591}	2025-09-16 18:48:50.789572+00
1654	main_trader	HEALTHY	t	t	t	\N	591	0	0	\N	{"sl_set": 589, "sl_failed": 6, "positions_failed": 90, "positions_opened": 591}	2025-09-16 18:49:53.234084+00
1655	main_trader	HEALTHY	t	t	t	\N	591	0	0	\N	{"sl_set": 589, "sl_failed": 6, "positions_failed": 90, "positions_opened": 591}	2025-09-16 18:50:54.84933+00
1656	main_trader	HEALTHY	t	t	t	\N	593	0	0	\N	{"sl_set": 591, "sl_failed": 6, "positions_failed": 90, "positions_opened": 593}	2025-09-16 18:51:56.346176+00
1657	main_trader	HEALTHY	t	t	t	\N	595	0	0	\N	{"sl_set": 593, "sl_failed": 6, "positions_failed": 92, "positions_opened": 595}	2025-09-16 18:52:57.666903+00
1658	main_trader	HEALTHY	t	t	t	\N	595	0	0	\N	{"sl_set": 593, "sl_failed": 6, "positions_failed": 92, "positions_opened": 595}	2025-09-16 18:53:59.459747+00
1659	main_trader	HEALTHY	t	t	t	\N	595	0	0	\N	{"sl_set": 593, "sl_failed": 6, "positions_failed": 92, "positions_opened": 595}	2025-09-16 18:55:00.638001+00
1660	main_trader	HEALTHY	t	t	t	\N	595	0	0	\N	{"sl_set": 593, "sl_failed": 6, "positions_failed": 92, "positions_opened": 595}	2025-09-16 18:56:02.37217+00
1661	main_trader	HEALTHY	t	t	t	\N	595	0	0	\N	{"sl_set": 593, "sl_failed": 6, "positions_failed": 92, "positions_opened": 595}	2025-09-16 18:57:04.07961+00
1662	main_trader	HEALTHY	t	t	t	\N	595	0	0	\N	{"sl_set": 593, "sl_failed": 6, "positions_failed": 92, "positions_opened": 595}	2025-09-16 18:58:06.398609+00
1663	main_trader	HEALTHY	t	t	t	\N	595	0	0	\N	{"sl_set": 593, "sl_failed": 6, "positions_failed": 92, "positions_opened": 595}	2025-09-16 18:59:08.125568+00
1664	main_trader	HEALTHY	t	t	t	\N	595	0	0	\N	{"sl_set": 593, "sl_failed": 6, "positions_failed": 92, "positions_opened": 595}	2025-09-16 19:00:09.690152+00
1665	main_trader	HEALTHY	t	t	t	\N	595	0	0	\N	{"sl_set": 593, "sl_failed": 6, "positions_failed": 92, "positions_opened": 595}	2025-09-16 19:01:11.359815+00
1666	main_trader	HEALTHY	t	t	t	\N	595	0	0	\N	{"sl_set": 593, "sl_failed": 6, "positions_failed": 92, "positions_opened": 595}	2025-09-16 19:02:13.016055+00
1667	main_trader	HEALTHY	t	t	t	\N	595	0	0	\N	{"sl_set": 593, "sl_failed": 6, "positions_failed": 92, "positions_opened": 595}	2025-09-16 19:03:14.924585+00
1668	main_trader	HEALTHY	t	t	t	\N	595	0	0	\N	{"sl_set": 593, "sl_failed": 6, "positions_failed": 92, "positions_opened": 595}	2025-09-16 19:04:16.584863+00
1669	main_trader	HEALTHY	t	t	t	\N	595	0	0	\N	{"sl_set": 593, "sl_failed": 6, "positions_failed": 92, "positions_opened": 595}	2025-09-16 19:05:18.143496+00
1670	main_trader	HEALTHY	t	t	t	\N	595	0	0	\N	{"sl_set": 593, "sl_failed": 6, "positions_failed": 92, "positions_opened": 595}	2025-09-16 19:06:19.707751+00
1671	main_trader	HEALTHY	t	t	t	\N	597	0	0	\N	{"sl_set": 595, "sl_failed": 6, "positions_failed": 94, "positions_opened": 597}	2025-09-16 19:07:21.093283+00
1672	main_trader	HEALTHY	t	t	t	\N	597	0	0	\N	{"sl_set": 595, "sl_failed": 6, "positions_failed": 94, "positions_opened": 597}	2025-09-16 19:08:22.947044+00
1673	main_trader	HEALTHY	t	t	t	\N	597	0	0	\N	{"sl_set": 595, "sl_failed": 6, "positions_failed": 94, "positions_opened": 597}	2025-09-16 19:09:24.219335+00
1674	main_trader	HEALTHY	t	t	t	\N	597	0	0	\N	{"sl_set": 595, "sl_failed": 6, "positions_failed": 94, "positions_opened": 597}	2025-09-16 19:10:25.885976+00
1675	main_trader	HEALTHY	t	t	t	\N	597	0	0	\N	{"sl_set": 595, "sl_failed": 6, "positions_failed": 94, "positions_opened": 597}	2025-09-16 19:11:27.584915+00
1676	main_trader	HEALTHY	t	t	t	\N	597	0	0	\N	{"sl_set": 595, "sl_failed": 6, "positions_failed": 94, "positions_opened": 597}	2025-09-16 19:12:28.685311+00
1677	main_trader	HEALTHY	t	t	t	\N	597	0	0	\N	{"sl_set": 595, "sl_failed": 6, "positions_failed": 94, "positions_opened": 597}	2025-09-16 19:13:31.367312+00
1678	main_trader	HEALTHY	t	t	t	\N	597	0	0	\N	{"sl_set": 595, "sl_failed": 6, "positions_failed": 94, "positions_opened": 597}	2025-09-16 19:14:33.115803+00
1679	main_trader	HEALTHY	t	t	t	\N	597	0	0	\N	{"sl_set": 595, "sl_failed": 6, "positions_failed": 94, "positions_opened": 597}	2025-09-16 19:15:34.748683+00
1680	main_trader	HEALTHY	t	t	t	\N	597	0	0	\N	{"sl_set": 595, "sl_failed": 6, "positions_failed": 94, "positions_opened": 597}	2025-09-16 19:16:35.929674+00
1681	main_trader	HEALTHY	t	t	t	\N	597	0	0	\N	{"sl_set": 595, "sl_failed": 6, "positions_failed": 94, "positions_opened": 597}	2025-09-16 19:17:37.57931+00
1682	main_trader	HEALTHY	t	t	t	\N	597	0	0	\N	{"sl_set": 595, "sl_failed": 6, "positions_failed": 94, "positions_opened": 597}	2025-09-16 19:18:39.455648+00
1683	main_trader	HEALTHY	t	t	t	\N	597	0	0	\N	{"sl_set": 595, "sl_failed": 6, "positions_failed": 94, "positions_opened": 597}	2025-09-16 19:19:40.590421+00
1684	main_trader	HEALTHY	t	t	t	\N	597	0	0	\N	{"sl_set": 595, "sl_failed": 6, "positions_failed": 94, "positions_opened": 597}	2025-09-16 19:20:41.748663+00
1685	main_trader	HEALTHY	t	t	t	\N	597	0	0	\N	{"sl_set": 595, "sl_failed": 6, "positions_failed": 94, "positions_opened": 597}	2025-09-16 19:21:42.819617+00
1686	main_trader	HEALTHY	t	t	t	\N	597	0	0	\N	{"sl_set": 595, "sl_failed": 6, "positions_failed": 94, "positions_opened": 597}	2025-09-16 19:22:43.973978+00
1687	main_trader	HEALTHY	t	t	t	\N	597	0	0	\N	{"sl_set": 595, "sl_failed": 6, "positions_failed": 94, "positions_opened": 597}	2025-09-16 19:23:45.416449+00
1688	main_trader	HEALTHY	t	t	t	\N	597	0	0	\N	{"sl_set": 595, "sl_failed": 6, "positions_failed": 94, "positions_opened": 597}	2025-09-16 19:24:47.189127+00
1689	main_trader	HEALTHY	t	t	t	\N	597	0	0	\N	{"sl_set": 595, "sl_failed": 6, "positions_failed": 94, "positions_opened": 597}	2025-09-16 19:25:48.409837+00
1690	main_trader	HEALTHY	t	t	t	\N	597	0	0	\N	{"sl_set": 595, "sl_failed": 6, "positions_failed": 94, "positions_opened": 597}	2025-09-16 19:26:49.478094+00
1691	main_trader	HEALTHY	t	t	t	\N	597	0	0	\N	{"sl_set": 595, "sl_failed": 6, "positions_failed": 94, "positions_opened": 597}	2025-09-16 19:27:50.633464+00
1692	main_trader	HEALTHY	t	t	t	\N	597	0	0	\N	{"sl_set": 595, "sl_failed": 6, "positions_failed": 94, "positions_opened": 597}	2025-09-16 19:28:51.790072+00
1693	main_trader	HEALTHY	t	t	t	\N	597	0	0	\N	{"sl_set": 595, "sl_failed": 6, "positions_failed": 94, "positions_opened": 597}	2025-09-16 19:29:53.072498+00
1694	main_trader	HEALTHY	t	t	t	\N	597	0	0	\N	{"sl_set": 595, "sl_failed": 6, "positions_failed": 94, "positions_opened": 597}	2025-09-16 19:30:54.486026+00
1695	main_trader	HEALTHY	t	t	t	\N	597	0	0	\N	{"sl_set": 595, "sl_failed": 6, "positions_failed": 94, "positions_opened": 597}	2025-09-16 19:31:55.543586+00
1696	main_trader	HEALTHY	t	t	t	\N	597	0	0	\N	{"sl_set": 595, "sl_failed": 6, "positions_failed": 94, "positions_opened": 597}	2025-09-16 19:32:56.691014+00
1697	main_trader	HEALTHY	t	t	t	\N	597	0	0	\N	{"sl_set": 595, "sl_failed": 6, "positions_failed": 94, "positions_opened": 597}	2025-09-16 19:33:57.755888+00
1698	main_trader	HEALTHY	t	t	t	\N	597	0	0	\N	{"sl_set": 595, "sl_failed": 6, "positions_failed": 94, "positions_opened": 597}	2025-09-16 19:34:59.0482+00
1699	main_trader	HEALTHY	t	t	t	\N	597	0	0	\N	{"sl_set": 595, "sl_failed": 6, "positions_failed": 94, "positions_opened": 597}	2025-09-16 19:36:00.291041+00
1700	main_trader	HEALTHY	t	t	t	\N	601	0	0	\N	{"sl_set": 599, "sl_failed": 6, "positions_failed": 94, "positions_opened": 601}	2025-09-16 19:37:01.823536+00
1701	main_trader	HEALTHY	t	t	t	\N	602	0	0	\N	{"sl_set": 601, "sl_failed": 6, "positions_failed": 94, "positions_opened": 602}	2025-09-16 19:38:03.084337+00
1702	main_trader	HEALTHY	t	t	t	\N	602	0	0	\N	{"sl_set": 601, "sl_failed": 6, "positions_failed": 94, "positions_opened": 602}	2025-09-16 19:39:04.155898+00
1703	main_trader	HEALTHY	t	t	t	\N	602	0	0	\N	{"sl_set": 601, "sl_failed": 6, "positions_failed": 94, "positions_opened": 602}	2025-09-16 19:40:05.211179+00
1704	main_trader	HEALTHY	t	t	t	\N	602	0	0	\N	{"sl_set": 601, "sl_failed": 6, "positions_failed": 94, "positions_opened": 602}	2025-09-16 19:41:06.356768+00
1705	main_trader	HEALTHY	t	t	t	\N	602	0	0	\N	{"sl_set": 601, "sl_failed": 6, "positions_failed": 94, "positions_opened": 602}	2025-09-16 19:42:07.97381+00
1706	main_trader	HEALTHY	t	t	t	\N	602	0	0	\N	{"sl_set": 601, "sl_failed": 6, "positions_failed": 94, "positions_opened": 602}	2025-09-16 19:43:09.122251+00
1707	main_trader	HEALTHY	t	t	t	\N	602	0	0	\N	{"sl_set": 601, "sl_failed": 6, "positions_failed": 94, "positions_opened": 602}	2025-09-16 19:44:10.269078+00
1708	main_trader	HEALTHY	t	t	t	\N	602	0	0	\N	{"sl_set": 601, "sl_failed": 6, "positions_failed": 94, "positions_opened": 602}	2025-09-16 19:45:11.328079+00
1709	main_trader	HEALTHY	t	t	t	\N	602	0	0	\N	{"sl_set": 601, "sl_failed": 6, "positions_failed": 94, "positions_opened": 602}	2025-09-16 19:46:12.381925+00
1710	main_trader	HEALTHY	t	t	t	\N	602	0	0	\N	{"sl_set": 601, "sl_failed": 6, "positions_failed": 94, "positions_opened": 602}	2025-09-16 19:47:13.66344+00
1711	main_trader	HEALTHY	t	t	t	\N	602	0	0	\N	{"sl_set": 601, "sl_failed": 6, "positions_failed": 94, "positions_opened": 602}	2025-09-16 19:48:14.924637+00
1712	main_trader	HEALTHY	t	t	t	\N	602	0	0	\N	{"sl_set": 601, "sl_failed": 6, "positions_failed": 94, "positions_opened": 602}	2025-09-16 19:49:15.982753+00
1713	main_trader	HEALTHY	t	t	t	\N	602	0	0	\N	{"sl_set": 601, "sl_failed": 6, "positions_failed": 94, "positions_opened": 602}	2025-09-16 19:50:17.054142+00
1714	main_trader	HEALTHY	t	t	t	\N	606	0	0	\N	{"sl_set": 605, "sl_failed": 6, "positions_failed": 94, "positions_opened": 606}	2025-09-16 19:51:18.202462+00
1715	main_trader	HEALTHY	t	t	t	\N	606	0	0	\N	{"sl_set": 605, "sl_failed": 6, "positions_failed": 94, "positions_opened": 606}	2025-09-16 19:52:19.512619+00
1716	main_trader	HEALTHY	t	t	t	\N	606	0	0	\N	{"sl_set": 605, "sl_failed": 6, "positions_failed": 94, "positions_opened": 606}	2025-09-16 19:53:20.661777+00
1717	main_trader	HEALTHY	t	t	t	\N	606	0	0	\N	{"sl_set": 605, "sl_failed": 6, "positions_failed": 94, "positions_opened": 606}	2025-09-16 19:54:21.742166+00
1718	main_trader	HEALTHY	t	t	t	\N	606	0	0	\N	{"sl_set": 605, "sl_failed": 6, "positions_failed": 94, "positions_opened": 606}	2025-09-16 19:55:22.895556+00
1719	main_trader	HEALTHY	t	t	t	\N	606	0	0	\N	{"sl_set": 605, "sl_failed": 6, "positions_failed": 94, "positions_opened": 606}	2025-09-16 19:56:23.968123+00
1720	main_trader	HEALTHY	t	t	t	\N	606	0	0	\N	{"sl_set": 605, "sl_failed": 6, "positions_failed": 94, "positions_opened": 606}	2025-09-16 19:57:25.817204+00
1721	main_trader	HEALTHY	t	t	t	\N	606	0	0	\N	{"sl_set": 605, "sl_failed": 6, "positions_failed": 94, "positions_opened": 606}	2025-09-16 19:58:27.045404+00
1722	main_trader	HEALTHY	t	t	t	\N	606	0	0	\N	{"sl_set": 605, "sl_failed": 6, "positions_failed": 94, "positions_opened": 606}	2025-09-16 19:59:28.186847+00
1723	main_trader	HEALTHY	t	t	t	\N	606	0	0	\N	{"sl_set": 605, "sl_failed": 6, "positions_failed": 94, "positions_opened": 606}	2025-09-16 20:00:29.245019+00
1724	main_trader	HEALTHY	t	t	t	\N	606	0	0	\N	{"sl_set": 605, "sl_failed": 6, "positions_failed": 94, "positions_opened": 606}	2025-09-16 20:01:30.303727+00
1725	main_trader	RUNNING	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-16 22:03:12.252862+00
1726	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-16 22:04:13.568987+00
1727	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-16 22:05:14.718592+00
1728	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-16 22:06:16.429321+00
1729	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-16 22:07:18.156394+00
1730	main_trader	HEALTHY	t	t	t	\N	7	0	0	\N	{"sl_set": 7, "sl_failed": 0, "positions_failed": 0, "positions_opened": 7}	2025-09-16 22:08:20.421907+00
1731	main_trader	HEALTHY	t	t	t	\N	10	0	0	\N	{"sl_set": 9, "sl_failed": 1, "positions_failed": 0, "positions_opened": 10}	2025-09-16 22:09:22.594741+00
1732	main_trader	HEALTHY	t	t	t	\N	10	0	0	\N	{"sl_set": 9, "sl_failed": 1, "positions_failed": 0, "positions_opened": 10}	2025-09-16 22:10:24.590423+00
1733	main_trader	HEALTHY	t	t	t	\N	10	0	0	\N	{"sl_set": 9, "sl_failed": 1, "positions_failed": 0, "positions_opened": 10}	2025-09-16 22:11:26.622335+00
1734	main_trader	HEALTHY	t	t	t	\N	10	0	0	\N	{"sl_set": 9, "sl_failed": 1, "positions_failed": 0, "positions_opened": 10}	2025-09-16 22:12:28.221736+00
1735	main_trader	HEALTHY	t	t	t	\N	10	0	0	\N	{"sl_set": 9, "sl_failed": 1, "positions_failed": 0, "positions_opened": 10}	2025-09-16 22:13:29.949154+00
1736	main_trader	HEALTHY	t	t	t	\N	10	0	0	\N	{"sl_set": 9, "sl_failed": 1, "positions_failed": 0, "positions_opened": 10}	2025-09-16 22:14:32.651377+00
1737	main_trader	HEALTHY	t	t	t	\N	10	0	0	\N	{"sl_set": 9, "sl_failed": 1, "positions_failed": 0, "positions_opened": 10}	2025-09-16 22:15:34.749871+00
1738	main_trader	HEALTHY	t	t	t	\N	10	0	0	\N	{"sl_set": 9, "sl_failed": 1, "positions_failed": 0, "positions_opened": 10}	2025-09-16 22:16:36.762922+00
1739	main_trader	HEALTHY	t	t	t	\N	10	0	0	\N	{"sl_set": 9, "sl_failed": 1, "positions_failed": 0, "positions_opened": 10}	2025-09-16 22:17:38.687805+00
1740	main_trader	HEALTHY	t	t	t	\N	10	0	0	\N	{"sl_set": 9, "sl_failed": 1, "positions_failed": 0, "positions_opened": 10}	2025-09-16 22:18:40.725393+00
1741	main_trader	HEALTHY	t	t	t	\N	10	0	0	\N	{"sl_set": 9, "sl_failed": 1, "positions_failed": 0, "positions_opened": 10}	2025-09-16 22:19:42.895245+00
1742	main_trader	HEALTHY	t	t	t	\N	10	0	0	\N	{"sl_set": 9, "sl_failed": 1, "positions_failed": 0, "positions_opened": 10}	2025-09-16 22:20:44.875558+00
1743	main_trader	HEALTHY	t	t	t	\N	11	0	0	\N	{"sl_set": 10, "sl_failed": 1, "positions_failed": 0, "positions_opened": 11}	2025-09-16 22:21:45.80525+00
1744	main_trader	HEALTHY	t	t	t	\N	12	0	0	\N	{"sl_set": 11, "sl_failed": 1, "positions_failed": 0, "positions_opened": 12}	2025-09-16 22:22:47.786857+00
1745	main_trader	HEALTHY	t	t	t	\N	12	0	0	\N	{"sl_set": 11, "sl_failed": 1, "positions_failed": 0, "positions_opened": 12}	2025-09-16 22:23:49.672303+00
1746	main_trader	HEALTHY	t	t	t	\N	12	0	0	\N	{"sl_set": 11, "sl_failed": 1, "positions_failed": 0, "positions_opened": 12}	2025-09-16 22:24:51.921714+00
1747	main_trader	HEALTHY	t	t	t	\N	12	0	0	\N	{"sl_set": 11, "sl_failed": 1, "positions_failed": 0, "positions_opened": 12}	2025-09-16 22:25:53.88469+00
1748	main_trader	HEALTHY	t	t	t	\N	12	0	0	\N	{"sl_set": 11, "sl_failed": 1, "positions_failed": 0, "positions_opened": 12}	2025-09-16 22:26:55.783909+00
1749	main_trader	HEALTHY	t	t	t	\N	12	0	0	\N	{"sl_set": 11, "sl_failed": 1, "positions_failed": 0, "positions_opened": 12}	2025-09-16 22:27:57.42863+00
1750	main_trader	HEALTHY	t	t	t	\N	12	0	0	\N	{"sl_set": 11, "sl_failed": 1, "positions_failed": 0, "positions_opened": 12}	2025-09-16 22:28:59.112207+00
1751	main_trader	HEALTHY	t	t	t	\N	12	0	0	\N	{"sl_set": 11, "sl_failed": 1, "positions_failed": 0, "positions_opened": 12}	2025-09-16 22:30:01.739775+00
1752	main_trader	HEALTHY	t	t	t	\N	12	0	0	\N	{"sl_set": 11, "sl_failed": 1, "positions_failed": 0, "positions_opened": 12}	2025-09-16 22:31:03.713028+00
1753	main_trader	HEALTHY	t	t	t	\N	12	0	0	\N	{"sl_set": 11, "sl_failed": 1, "positions_failed": 0, "positions_opened": 12}	2025-09-16 22:32:05.600859+00
1754	main_trader	HEALTHY	t	t	t	\N	12	0	0	\N	{"sl_set": 11, "sl_failed": 1, "positions_failed": 0, "positions_opened": 12}	2025-09-16 22:33:07.486162+00
1755	main_trader	HEALTHY	t	t	t	\N	12	0	0	\N	{"sl_set": 11, "sl_failed": 1, "positions_failed": 0, "positions_opened": 12}	2025-09-16 22:34:09.469742+00
1756	main_trader	HEALTHY	t	t	t	\N	12	0	0	\N	{"sl_set": 11, "sl_failed": 1, "positions_failed": 0, "positions_opened": 12}	2025-09-16 22:35:11.283347+00
1757	main_trader	HEALTHY	t	t	t	\N	12	0	0	\N	{"sl_set": 12, "sl_failed": 1, "positions_failed": 0, "positions_opened": 13}	2025-09-16 22:36:12.470181+00
1758	main_trader	HEALTHY	t	t	t	\N	14	0	0	\N	{"sl_set": 13, "sl_failed": 1, "positions_failed": 0, "positions_opened": 14}	2025-09-16 22:37:14.453289+00
1759	main_trader	HEALTHY	t	t	t	\N	14	0	0	\N	{"sl_set": 13, "sl_failed": 1, "positions_failed": 0, "positions_opened": 14}	2025-09-16 22:38:16.425689+00
1760	main_trader	HEALTHY	t	t	t	\N	14	0	0	\N	{"sl_set": 13, "sl_failed": 1, "positions_failed": 0, "positions_opened": 14}	2025-09-16 22:39:18.316188+00
1761	main_trader	HEALTHY	t	t	t	\N	14	0	0	\N	{"sl_set": 13, "sl_failed": 1, "positions_failed": 0, "positions_opened": 14}	2025-09-16 22:40:20.438226+00
1762	main_trader	HEALTHY	t	t	t	\N	14	0	0	\N	{"sl_set": 13, "sl_failed": 1, "positions_failed": 0, "positions_opened": 14}	2025-09-16 22:41:22.177039+00
1763	main_trader	HEALTHY	t	t	t	\N	14	0	0	\N	{"sl_set": 13, "sl_failed": 1, "positions_failed": 0, "positions_opened": 14}	2025-09-16 22:42:24.06183+00
1764	main_trader	HEALTHY	t	t	t	\N	14	0	0	\N	{"sl_set": 13, "sl_failed": 1, "positions_failed": 0, "positions_opened": 14}	2025-09-16 22:43:25.953669+00
1765	main_trader	HEALTHY	t	t	t	\N	14	0	0	\N	{"sl_set": 13, "sl_failed": 1, "positions_failed": 0, "positions_opened": 14}	2025-09-16 22:44:27.844495+00
1766	main_trader	HEALTHY	t	t	t	\N	14	0	0	\N	{"sl_set": 13, "sl_failed": 1, "positions_failed": 0, "positions_opened": 14}	2025-09-16 22:45:30.417035+00
1767	main_trader	HEALTHY	t	t	t	\N	14	0	0	\N	{"sl_set": 13, "sl_failed": 1, "positions_failed": 0, "positions_opened": 14}	2025-09-16 22:46:32.493403+00
1768	main_trader	HEALTHY	t	t	t	\N	14	0	0	\N	{"sl_set": 13, "sl_failed": 1, "positions_failed": 0, "positions_opened": 14}	2025-09-16 22:47:34.46294+00
1769	main_trader	HEALTHY	t	t	t	\N	14	0	0	\N	{"sl_set": 13, "sl_failed": 1, "positions_failed": 0, "positions_opened": 14}	2025-09-16 22:48:36.002588+00
1770	main_trader	HEALTHY	t	t	t	\N	14	0	0	\N	{"sl_set": 13, "sl_failed": 1, "positions_failed": 0, "positions_opened": 14}	2025-09-16 22:49:37.865843+00
1771	main_trader	HEALTHY	t	t	t	\N	14	0	0	\N	{"sl_set": 13, "sl_failed": 1, "positions_failed": 0, "positions_opened": 14}	2025-09-16 22:50:40.039486+00
1772	main_trader	HEALTHY	t	t	t	\N	16	0	0	\N	{"sl_set": 16, "sl_failed": 1, "positions_failed": 0, "positions_opened": 16}	2025-09-16 22:51:41.46782+00
1773	main_trader	HEALTHY	t	t	t	\N	16	0	0	\N	{"sl_set": 16, "sl_failed": 1, "positions_failed": 0, "positions_opened": 16}	2025-09-16 22:52:43.331486+00
1774	main_trader	HEALTHY	t	t	t	\N	16	0	0	\N	{"sl_set": 16, "sl_failed": 1, "positions_failed": 0, "positions_opened": 16}	2025-09-16 22:53:44.845762+00
1775	main_trader	HEALTHY	t	t	t	\N	16	0	0	\N	{"sl_set": 16, "sl_failed": 1, "positions_failed": 0, "positions_opened": 16}	2025-09-16 22:54:46.698698+00
1776	main_trader	HEALTHY	t	t	t	\N	16	0	0	\N	{"sl_set": 16, "sl_failed": 1, "positions_failed": 0, "positions_opened": 16}	2025-09-16 22:55:48.985363+00
1777	main_trader	HEALTHY	t	t	t	\N	16	0	0	\N	{"sl_set": 16, "sl_failed": 1, "positions_failed": 0, "positions_opened": 16}	2025-09-16 22:56:50.64022+00
1778	main_trader	HEALTHY	t	t	t	\N	16	0	0	\N	{"sl_set": 16, "sl_failed": 1, "positions_failed": 0, "positions_opened": 16}	2025-09-16 22:57:52.600549+00
1779	main_trader	HEALTHY	t	t	t	\N	16	0	0	\N	{"sl_set": 16, "sl_failed": 1, "positions_failed": 0, "positions_opened": 16}	2025-09-16 22:58:54.512552+00
1780	main_trader	HEALTHY	t	t	t	\N	16	0	0	\N	{"sl_set": 16, "sl_failed": 1, "positions_failed": 0, "positions_opened": 16}	2025-09-16 22:59:56.48113+00
1781	main_trader	HEALTHY	t	t	t	\N	16	0	0	\N	{"sl_set": 16, "sl_failed": 1, "positions_failed": 0, "positions_opened": 16}	2025-09-16 23:00:59.017834+00
1782	main_trader	HEALTHY	t	t	t	\N	16	0	0	\N	{"sl_set": 16, "sl_failed": 1, "positions_failed": 0, "positions_opened": 16}	2025-09-16 23:02:01.015554+00
1783	main_trader	HEALTHY	t	t	t	\N	16	0	0	\N	{"sl_set": 16, "sl_failed": 1, "positions_failed": 0, "positions_opened": 16}	2025-09-16 23:03:02.91118+00
1784	main_trader	HEALTHY	t	t	t	\N	16	0	0	\N	{"sl_set": 16, "sl_failed": 1, "positions_failed": 0, "positions_opened": 16}	2025-09-16 23:04:04.029579+00
1785	main_trader	HEALTHY	t	t	t	\N	16	0	0	\N	{"sl_set": 16, "sl_failed": 1, "positions_failed": 0, "positions_opened": 16}	2025-09-16 23:05:05.914594+00
1786	main_trader	HEALTHY	t	t	t	\N	16	0	0	\N	{"sl_set": 16, "sl_failed": 1, "positions_failed": 0, "positions_opened": 16}	2025-09-16 23:06:07.686997+00
1787	main_trader	HEALTHY	t	t	t	\N	16	0	0	\N	{"sl_set": 16, "sl_failed": 1, "positions_failed": 0, "positions_opened": 16}	2025-09-16 23:07:09.332573+00
1788	main_trader	HEALTHY	t	t	t	\N	19	0	0	\N	{"sl_set": 19, "sl_failed": 1, "positions_failed": 1, "positions_opened": 19}	2025-09-16 23:08:10.878401+00
1789	main_trader	HEALTHY	t	t	t	\N	22	0	0	\N	{"sl_set": 22, "sl_failed": 1, "positions_failed": 1, "positions_opened": 22}	2025-09-16 23:09:12.298712+00
1790	main_trader	HEALTHY	t	t	t	\N	22	0	0	\N	{"sl_set": 22, "sl_failed": 1, "positions_failed": 1, "positions_opened": 22}	2025-09-16 23:10:14.197231+00
1791	main_trader	HEALTHY	t	t	t	\N	22	0	0	\N	{"sl_set": 22, "sl_failed": 1, "positions_failed": 1, "positions_opened": 22}	2025-09-16 23:11:16.384591+00
1792	main_trader	HEALTHY	t	t	t	\N	22	0	0	\N	{"sl_set": 22, "sl_failed": 1, "positions_failed": 1, "positions_opened": 22}	2025-09-16 23:12:17.881955+00
1793	main_trader	HEALTHY	t	t	t	\N	22	0	0	\N	{"sl_set": 22, "sl_failed": 1, "positions_failed": 1, "positions_opened": 22}	2025-09-16 23:13:19.849628+00
1794	main_trader	HEALTHY	t	t	t	\N	22	0	0	\N	{"sl_set": 22, "sl_failed": 1, "positions_failed": 1, "positions_opened": 22}	2025-09-16 23:14:21.728642+00
1795	main_trader	HEALTHY	t	t	t	\N	22	0	0	\N	{"sl_set": 22, "sl_failed": 1, "positions_failed": 1, "positions_opened": 22}	2025-09-16 23:15:22.858585+00
1796	main_trader	HEALTHY	t	t	t	\N	22	0	0	\N	{"sl_set": 22, "sl_failed": 1, "positions_failed": 1, "positions_opened": 22}	2025-09-16 23:16:24.705349+00
1797	main_trader	HEALTHY	t	t	t	\N	22	0	0	\N	{"sl_set": 22, "sl_failed": 1, "positions_failed": 1, "positions_opened": 22}	2025-09-16 23:17:26.805238+00
1798	main_trader	HEALTHY	t	t	t	\N	22	0	0	\N	{"sl_set": 22, "sl_failed": 1, "positions_failed": 1, "positions_opened": 22}	2025-09-16 23:18:28.320888+00
1799	main_trader	HEALTHY	t	t	t	\N	22	0	0	\N	{"sl_set": 22, "sl_failed": 1, "positions_failed": 1, "positions_opened": 22}	2025-09-16 23:19:30.356991+00
1800	main_trader	HEALTHY	t	t	t	\N	22	0	0	\N	{"sl_set": 22, "sl_failed": 1, "positions_failed": 1, "positions_opened": 22}	2025-09-16 23:20:32.231289+00
1801	main_trader	HEALTHY	t	t	t	\N	22	0	0	\N	{"sl_set": 22, "sl_failed": 1, "positions_failed": 1, "positions_opened": 23}	2025-09-16 23:21:34.099063+00
1802	main_trader	HEALTHY	t	t	t	\N	27	0	0	\N	{"sl_set": 28, "sl_failed": 1, "positions_failed": 1, "positions_opened": 27}	2025-09-16 23:22:36.07174+00
1803	main_trader	HEALTHY	t	t	t	\N	28	0	0	\N	{"sl_set": 29, "sl_failed": 1, "positions_failed": 1, "positions_opened": 28}	2025-09-16 23:23:38.076986+00
1804	main_trader	HEALTHY	t	t	t	\N	28	0	0	\N	{"sl_set": 29, "sl_failed": 1, "positions_failed": 1, "positions_opened": 28}	2025-09-16 23:24:40.077421+00
1805	main_trader	HEALTHY	t	t	t	\N	28	0	0	\N	{"sl_set": 29, "sl_failed": 1, "positions_failed": 1, "positions_opened": 28}	2025-09-16 23:25:41.636858+00
1806	main_trader	HEALTHY	t	t	t	\N	28	0	0	\N	{"sl_set": 29, "sl_failed": 1, "positions_failed": 1, "positions_opened": 28}	2025-09-16 23:26:44.071229+00
1807	main_trader	HEALTHY	t	t	t	\N	28	0	0	\N	{"sl_set": 29, "sl_failed": 1, "positions_failed": 1, "positions_opened": 28}	2025-09-16 23:27:45.837896+00
1808	main_trader	HEALTHY	t	t	t	\N	28	0	0	\N	{"sl_set": 29, "sl_failed": 1, "positions_failed": 1, "positions_opened": 28}	2025-09-16 23:28:47.431657+00
1809	main_trader	HEALTHY	t	t	t	\N	28	0	0	\N	{"sl_set": 29, "sl_failed": 1, "positions_failed": 1, "positions_opened": 28}	2025-09-16 23:29:49.418652+00
1810	main_trader	HEALTHY	t	t	t	\N	28	0	0	\N	{"sl_set": 29, "sl_failed": 1, "positions_failed": 1, "positions_opened": 28}	2025-09-16 23:30:51.427864+00
1811	main_trader	HEALTHY	t	t	t	\N	28	0	0	\N	{"sl_set": 29, "sl_failed": 1, "positions_failed": 1, "positions_opened": 28}	2025-09-16 23:31:53.094208+00
1812	main_trader	HEALTHY	t	t	t	\N	28	0	0	\N	{"sl_set": 29, "sl_failed": 1, "positions_failed": 1, "positions_opened": 28}	2025-09-16 23:32:54.713556+00
1813	main_trader	HEALTHY	t	t	t	\N	28	0	0	\N	{"sl_set": 29, "sl_failed": 1, "positions_failed": 1, "positions_opened": 28}	2025-09-16 23:33:56.6128+00
1814	main_trader	HEALTHY	t	t	t	\N	28	0	0	\N	{"sl_set": 29, "sl_failed": 1, "positions_failed": 1, "positions_opened": 28}	2025-09-16 23:34:58.055028+00
1815	main_trader	HEALTHY	t	t	t	\N	28	0	0	\N	{"sl_set": 29, "sl_failed": 1, "positions_failed": 1, "positions_opened": 28}	2025-09-16 23:35:59.590355+00
1816	main_trader	HEALTHY	t	t	t	\N	30	0	0	\N	{"sl_set": 31, "sl_failed": 1, "positions_failed": 1, "positions_opened": 30}	2025-09-16 23:37:01.541826+00
1817	main_trader	HEALTHY	t	t	t	\N	30	0	0	\N	{"sl_set": 31, "sl_failed": 1, "positions_failed": 1, "positions_opened": 30}	2025-09-16 23:38:03.640806+00
1818	main_trader	HEALTHY	t	t	t	\N	30	0	0	\N	{"sl_set": 31, "sl_failed": 1, "positions_failed": 1, "positions_opened": 30}	2025-09-16 23:39:05.195176+00
1819	main_trader	HEALTHY	t	t	t	\N	30	0	0	\N	{"sl_set": 31, "sl_failed": 1, "positions_failed": 1, "positions_opened": 30}	2025-09-16 23:40:07.085495+00
1820	main_trader	HEALTHY	t	t	t	\N	30	0	0	\N	{"sl_set": 31, "sl_failed": 1, "positions_failed": 1, "positions_opened": 30}	2025-09-16 23:41:09.004135+00
1821	main_trader	HEALTHY	t	t	t	\N	30	0	0	\N	{"sl_set": 31, "sl_failed": 1, "positions_failed": 1, "positions_opened": 30}	2025-09-16 23:42:11.697312+00
1822	main_trader	HEALTHY	t	t	t	\N	30	0	0	\N	{"sl_set": 31, "sl_failed": 1, "positions_failed": 1, "positions_opened": 30}	2025-09-16 23:43:13.764891+00
1823	main_trader	HEALTHY	t	t	t	\N	30	0	0	\N	{"sl_set": 31, "sl_failed": 1, "positions_failed": 1, "positions_opened": 30}	2025-09-16 23:44:15.68509+00
1824	main_trader	HEALTHY	t	t	t	\N	30	0	0	\N	{"sl_set": 31, "sl_failed": 1, "positions_failed": 1, "positions_opened": 30}	2025-09-16 23:45:17.683835+00
1825	main_trader	HEALTHY	t	t	t	\N	30	0	0	\N	{"sl_set": 31, "sl_failed": 1, "positions_failed": 1, "positions_opened": 30}	2025-09-16 23:46:19.586118+00
1826	main_trader	HEALTHY	t	t	t	\N	30	0	0	\N	{"sl_set": 31, "sl_failed": 1, "positions_failed": 1, "positions_opened": 30}	2025-09-16 23:47:21.821368+00
1827	main_trader	HEALTHY	t	t	t	\N	30	0	0	\N	{"sl_set": 31, "sl_failed": 1, "positions_failed": 1, "positions_opened": 30}	2025-09-16 23:48:23.48627+00
1828	main_trader	HEALTHY	t	t	t	\N	30	0	0	\N	{"sl_set": 31, "sl_failed": 1, "positions_failed": 1, "positions_opened": 30}	2025-09-16 23:49:25.540396+00
1829	main_trader	HEALTHY	t	t	t	\N	30	0	0	\N	{"sl_set": 31, "sl_failed": 1, "positions_failed": 1, "positions_opened": 30}	2025-09-16 23:50:27.546446+00
1830	main_trader	HEALTHY	t	t	t	\N	30	0	0	\N	{"sl_set": 31, "sl_failed": 1, "positions_failed": 1, "positions_opened": 30}	2025-09-16 23:51:30.199864+00
1831	main_trader	HEALTHY	t	t	t	\N	32	0	0	\N	{"sl_set": 34, "sl_failed": 1, "positions_failed": 4, "positions_opened": 33}	2025-09-16 23:52:31.992454+00
1832	main_trader	HEALTHY	t	t	t	\N	34	0	0	\N	{"sl_set": 35, "sl_failed": 1, "positions_failed": 5, "positions_opened": 34}	2025-09-16 23:53:33.905609+00
1833	main_trader	HEALTHY	t	t	t	\N	34	0	0	\N	{"sl_set": 35, "sl_failed": 1, "positions_failed": 5, "positions_opened": 34}	2025-09-16 23:54:35.930926+00
1834	main_trader	HEALTHY	t	t	t	\N	34	0	0	\N	{"sl_set": 35, "sl_failed": 1, "positions_failed": 5, "positions_opened": 34}	2025-09-16 23:55:37.940648+00
1835	main_trader	HEALTHY	t	t	t	\N	34	0	0	\N	{"sl_set": 35, "sl_failed": 1, "positions_failed": 5, "positions_opened": 34}	2025-09-16 23:56:40.466166+00
1836	main_trader	HEALTHY	t	t	t	\N	34	0	0	\N	{"sl_set": 35, "sl_failed": 1, "positions_failed": 5, "positions_opened": 34}	2025-09-16 23:57:42.506055+00
1837	main_trader	HEALTHY	t	t	t	\N	34	0	0	\N	{"sl_set": 35, "sl_failed": 1, "positions_failed": 5, "positions_opened": 34}	2025-09-16 23:58:44.434288+00
1838	main_trader	HEALTHY	t	t	t	\N	34	0	0	\N	{"sl_set": 35, "sl_failed": 1, "positions_failed": 5, "positions_opened": 34}	2025-09-16 23:59:46.11971+00
1839	main_trader	HEALTHY	t	t	t	\N	34	0	0	\N	{"sl_set": 35, "sl_failed": 1, "positions_failed": 5, "positions_opened": 34}	2025-09-17 00:00:48.143795+00
1840	main_trader	HEALTHY	t	t	t	\N	34	0	0	\N	{"sl_set": 35, "sl_failed": 1, "positions_failed": 5, "positions_opened": 34}	2025-09-17 00:01:50.287039+00
1841	main_trader	HEALTHY	t	t	t	\N	34	0	0	\N	{"sl_set": 35, "sl_failed": 1, "positions_failed": 5, "positions_opened": 34}	2025-09-17 00:02:52.384098+00
1842	main_trader	HEALTHY	t	t	t	\N	34	0	0	\N	{"sl_set": 35, "sl_failed": 1, "positions_failed": 5, "positions_opened": 34}	2025-09-17 00:03:54.312911+00
1843	main_trader	HEALTHY	t	t	t	\N	34	0	0	\N	{"sl_set": 35, "sl_failed": 1, "positions_failed": 5, "positions_opened": 34}	2025-09-17 00:04:55.541473+00
1844	main_trader	HEALTHY	t	t	t	\N	34	0	0	\N	{"sl_set": 35, "sl_failed": 1, "positions_failed": 5, "positions_opened": 34}	2025-09-17 00:05:57.46886+00
1845	main_trader	HEALTHY	t	t	t	\N	34	0	0	\N	{"sl_set": 35, "sl_failed": 1, "positions_failed": 5, "positions_opened": 34}	2025-09-17 00:06:59.623276+00
1846	main_trader	HEALTHY	t	t	t	\N	34	0	0	\N	{"sl_set": 35, "sl_failed": 1, "positions_failed": 5, "positions_opened": 34}	2025-09-17 00:08:01.588633+00
1847	main_trader	HEALTHY	t	t	t	\N	34	0	0	\N	{"sl_set": 35, "sl_failed": 1, "positions_failed": 5, "positions_opened": 34}	2025-09-17 00:09:03.044173+00
1848	main_trader	HEALTHY	t	t	t	\N	34	0	0	\N	{"sl_set": 35, "sl_failed": 1, "positions_failed": 5, "positions_opened": 34}	2025-09-17 00:10:05.132471+00
1849	main_trader	HEALTHY	t	t	t	\N	34	0	0	\N	{"sl_set": 35, "sl_failed": 1, "positions_failed": 5, "positions_opened": 34}	2025-09-17 00:11:07.026911+00
1850	main_trader	HEALTHY	t	t	t	\N	34	0	0	\N	{"sl_set": 35, "sl_failed": 1, "positions_failed": 5, "positions_opened": 34}	2025-09-17 00:12:09.17149+00
1851	main_trader	HEALTHY	t	t	t	\N	34	0	0	\N	{"sl_set": 35, "sl_failed": 1, "positions_failed": 5, "positions_opened": 34}	2025-09-17 00:13:11.242919+00
1852	main_trader	HEALTHY	t	t	t	\N	34	0	0	\N	{"sl_set": 35, "sl_failed": 1, "positions_failed": 5, "positions_opened": 34}	2025-09-17 00:14:13.133655+00
1853	main_trader	HEALTHY	t	t	t	\N	34	0	0	\N	{"sl_set": 35, "sl_failed": 1, "positions_failed": 5, "positions_opened": 34}	2025-09-17 00:15:15.793216+00
1854	main_trader	HEALTHY	t	t	t	\N	34	0	0	\N	{"sl_set": 35, "sl_failed": 1, "positions_failed": 5, "positions_opened": 34}	2025-09-17 00:16:17.771697+00
1855	main_trader	HEALTHY	t	t	t	\N	34	0	0	\N	{"sl_set": 35, "sl_failed": 1, "positions_failed": 5, "positions_opened": 34}	2025-09-17 00:17:19.352024+00
1856	main_trader	HEALTHY	t	t	t	\N	34	0	0	\N	{"sl_set": 35, "sl_failed": 1, "positions_failed": 5, "positions_opened": 34}	2025-09-17 00:18:20.531203+00
1857	main_trader	HEALTHY	t	t	t	\N	34	0	0	\N	{"sl_set": 35, "sl_failed": 1, "positions_failed": 5, "positions_opened": 34}	2025-09-17 00:19:21.947115+00
1858	main_trader	HEALTHY	t	t	t	\N	34	0	0	\N	{"sl_set": 35, "sl_failed": 1, "positions_failed": 5, "positions_opened": 34}	2025-09-17 00:20:23.70161+00
1859	main_trader	HEALTHY	t	t	t	\N	34	0	0	\N	{"sl_set": 36, "sl_failed": 1, "positions_failed": 5, "positions_opened": 35}	2025-09-17 00:21:25.19411+00
1860	main_trader	HEALTHY	t	t	t	\N	40	0	0	\N	{"sl_set": 42, "sl_failed": 1, "positions_failed": 5, "positions_opened": 40}	2025-09-17 00:22:26.278207+00
1861	main_trader	HEALTHY	t	t	t	\N	44	0	0	\N	{"sl_set": 46, "sl_failed": 1, "positions_failed": 6, "positions_opened": 44}	2025-09-17 00:23:27.771454+00
1862	main_trader	HEALTHY	t	t	t	\N	44	0	0	\N	{"sl_set": 46, "sl_failed": 1, "positions_failed": 6, "positions_opened": 44}	2025-09-17 00:24:29.247921+00
1863	main_trader	HEALTHY	t	t	t	\N	44	0	0	\N	{"sl_set": 46, "sl_failed": 1, "positions_failed": 6, "positions_opened": 44}	2025-09-17 00:25:30.976279+00
1864	main_trader	HEALTHY	t	t	t	\N	44	0	0	\N	{"sl_set": 46, "sl_failed": 1, "positions_failed": 6, "positions_opened": 44}	2025-09-17 00:26:32.715809+00
1865	main_trader	HEALTHY	t	t	t	\N	44	0	0	\N	{"sl_set": 46, "sl_failed": 1, "positions_failed": 6, "positions_opened": 44}	2025-09-17 00:27:34.108332+00
1866	main_trader	HEALTHY	t	t	t	\N	44	0	0	\N	{"sl_set": 46, "sl_failed": 1, "positions_failed": 6, "positions_opened": 44}	2025-09-17 00:28:35.612336+00
1867	main_trader	HEALTHY	t	t	t	\N	44	0	0	\N	{"sl_set": 46, "sl_failed": 1, "positions_failed": 6, "positions_opened": 44}	2025-09-17 00:29:37.009494+00
1868	main_trader	HEALTHY	t	t	t	\N	44	0	0	\N	{"sl_set": 46, "sl_failed": 1, "positions_failed": 6, "positions_opened": 44}	2025-09-17 00:30:39.203564+00
1869	main_trader	HEALTHY	t	t	t	\N	44	0	0	\N	{"sl_set": 46, "sl_failed": 1, "positions_failed": 6, "positions_opened": 44}	2025-09-17 00:31:40.884609+00
1870	main_trader	HEALTHY	t	t	t	\N	44	0	0	\N	{"sl_set": 46, "sl_failed": 1, "positions_failed": 6, "positions_opened": 44}	2025-09-17 00:32:42.293537+00
1871	main_trader	HEALTHY	t	t	t	\N	44	0	0	\N	{"sl_set": 46, "sl_failed": 1, "positions_failed": 6, "positions_opened": 44}	2025-09-17 00:33:43.720761+00
1872	main_trader	HEALTHY	t	t	t	\N	44	0	0	\N	{"sl_set": 46, "sl_failed": 1, "positions_failed": 6, "positions_opened": 44}	2025-09-17 00:34:45.729029+00
1873	main_trader	HEALTHY	t	t	t	\N	44	0	0	\N	{"sl_set": 46, "sl_failed": 1, "positions_failed": 6, "positions_opened": 44}	2025-09-17 00:35:47.486975+00
1874	main_trader	HEALTHY	t	t	t	\N	46	0	0	\N	{"sl_set": 48, "sl_failed": 1, "positions_failed": 6, "positions_opened": 46}	2025-09-17 00:36:48.881024+00
1875	main_trader	HEALTHY	t	t	t	\N	49	0	0	\N	{"sl_set": 51, "sl_failed": 1, "positions_failed": 7, "positions_opened": 49}	2025-09-17 00:37:50.738279+00
1876	main_trader	HEALTHY	t	t	t	\N	49	0	0	\N	{"sl_set": 51, "sl_failed": 1, "positions_failed": 7, "positions_opened": 49}	2025-09-17 00:38:52.16707+00
1877	main_trader	HEALTHY	t	t	t	\N	49	0	0	\N	{"sl_set": 51, "sl_failed": 1, "positions_failed": 7, "positions_opened": 49}	2025-09-17 00:39:53.342277+00
1878	main_trader	HEALTHY	t	t	t	\N	49	0	0	\N	{"sl_set": 51, "sl_failed": 1, "positions_failed": 7, "positions_opened": 49}	2025-09-17 00:40:54.965682+00
1879	main_trader	HEALTHY	t	t	t	\N	49	0	0	\N	{"sl_set": 51, "sl_failed": 1, "positions_failed": 7, "positions_opened": 49}	2025-09-17 00:41:56.553779+00
1880	main_trader	HEALTHY	t	t	t	\N	49	0	0	\N	{"sl_set": 51, "sl_failed": 1, "positions_failed": 7, "positions_opened": 49}	2025-09-17 00:42:57.959245+00
1881	main_trader	HEALTHY	t	t	t	\N	49	0	0	\N	{"sl_set": 51, "sl_failed": 1, "positions_failed": 7, "positions_opened": 49}	2025-09-17 00:43:59.460135+00
1882	main_trader	HEALTHY	t	t	t	\N	49	0	0	\N	{"sl_set": 51, "sl_failed": 1, "positions_failed": 7, "positions_opened": 49}	2025-09-17 00:45:00.85917+00
1883	main_trader	HEALTHY	t	t	t	\N	49	0	0	\N	{"sl_set": 51, "sl_failed": 1, "positions_failed": 7, "positions_opened": 49}	2025-09-17 00:46:02.252844+00
1884	main_trader	HEALTHY	t	t	t	\N	49	0	0	\N	{"sl_set": 51, "sl_failed": 1, "positions_failed": 7, "positions_opened": 49}	2025-09-17 00:47:03.839291+00
1885	main_trader	HEALTHY	t	t	t	\N	49	0	0	\N	{"sl_set": 51, "sl_failed": 1, "positions_failed": 7, "positions_opened": 49}	2025-09-17 00:48:05.238032+00
1886	main_trader	HEALTHY	t	t	t	\N	49	0	0	\N	{"sl_set": 51, "sl_failed": 1, "positions_failed": 7, "positions_opened": 49}	2025-09-17 00:49:06.659569+00
1887	main_trader	HEALTHY	t	t	t	\N	49	0	0	\N	{"sl_set": 51, "sl_failed": 1, "positions_failed": 7, "positions_opened": 49}	2025-09-17 00:50:07.744222+00
1888	main_trader	HEALTHY	t	t	t	\N	49	0	0	\N	{"sl_set": 51, "sl_failed": 1, "positions_failed": 7, "positions_opened": 50}	2025-09-17 00:51:09.636023+00
1889	main_trader	HEALTHY	t	t	t	\N	53	0	0	\N	{"sl_set": 57, "sl_failed": 1, "positions_failed": 8, "positions_opened": 54}	2025-09-17 00:52:10.948669+00
1890	main_trader	HEALTHY	t	t	t	\N	56	0	0	\N	{"sl_set": 59, "sl_failed": 1, "positions_failed": 10, "positions_opened": 56}	2025-09-17 00:53:12.343254+00
1891	main_trader	HEALTHY	t	t	t	\N	56	0	0	\N	{"sl_set": 59, "sl_failed": 1, "positions_failed": 10, "positions_opened": 56}	2025-09-17 00:54:13.903052+00
1892	main_trader	HEALTHY	t	t	t	\N	56	0	0	\N	{"sl_set": 59, "sl_failed": 1, "positions_failed": 10, "positions_opened": 56}	2025-09-17 00:55:15.00106+00
1893	main_trader	HEALTHY	t	t	t	\N	56	0	0	\N	{"sl_set": 59, "sl_failed": 1, "positions_failed": 10, "positions_opened": 56}	2025-09-17 00:56:16.691957+00
1894	main_trader	HEALTHY	t	t	t	\N	56	0	0	\N	{"sl_set": 59, "sl_failed": 1, "positions_failed": 10, "positions_opened": 56}	2025-09-17 00:57:18.323172+00
1895	main_trader	HEALTHY	t	t	t	\N	56	0	0	\N	{"sl_set": 59, "sl_failed": 1, "positions_failed": 10, "positions_opened": 56}	2025-09-17 00:58:19.880241+00
1896	main_trader	HEALTHY	t	t	t	\N	56	0	0	\N	{"sl_set": 59, "sl_failed": 1, "positions_failed": 10, "positions_opened": 56}	2025-09-17 00:59:21.377431+00
1897	main_trader	HEALTHY	t	t	t	\N	56	0	0	\N	{"sl_set": 59, "sl_failed": 1, "positions_failed": 10, "positions_opened": 56}	2025-09-17 01:00:22.777591+00
1898	main_trader	HEALTHY	t	t	t	\N	56	0	0	\N	{"sl_set": 59, "sl_failed": 1, "positions_failed": 10, "positions_opened": 56}	2025-09-17 01:01:24.545343+00
1899	main_trader	HEALTHY	t	t	t	\N	56	0	0	\N	{"sl_set": 59, "sl_failed": 1, "positions_failed": 10, "positions_opened": 56}	2025-09-17 01:02:26.048938+00
1900	main_trader	HEALTHY	t	t	t	\N	56	0	0	\N	{"sl_set": 59, "sl_failed": 1, "positions_failed": 10, "positions_opened": 56}	2025-09-17 01:03:27.578239+00
1901	main_trader	HEALTHY	t	t	t	\N	56	0	0	\N	{"sl_set": 59, "sl_failed": 1, "positions_failed": 10, "positions_opened": 56}	2025-09-17 01:04:28.823832+00
1902	main_trader	HEALTHY	t	t	t	\N	56	0	0	\N	{"sl_set": 59, "sl_failed": 1, "positions_failed": 10, "positions_opened": 56}	2025-09-17 01:05:30.012952+00
1903	main_trader	HEALTHY	t	t	t	\N	56	0	0	\N	{"sl_set": 59, "sl_failed": 1, "positions_failed": 10, "positions_opened": 56}	2025-09-17 01:06:31.296332+00
1904	main_trader	HEALTHY	t	t	t	\N	60	0	0	\N	{"sl_set": 64, "sl_failed": 1, "positions_failed": 12, "positions_opened": 60}	2025-09-17 01:07:32.3258+00
1905	main_trader	HEALTHY	t	t	t	\N	61	0	0	\N	{"sl_set": 64, "sl_failed": 2, "positions_failed": 13, "positions_opened": 61}	2025-09-17 01:08:33.538277+00
1906	main_trader	HEALTHY	t	t	t	\N	61	0	0	\N	{"sl_set": 64, "sl_failed": 2, "positions_failed": 13, "positions_opened": 61}	2025-09-17 01:09:34.623782+00
1907	main_trader	HEALTHY	t	t	t	\N	61	0	0	\N	{"sl_set": 64, "sl_failed": 2, "positions_failed": 13, "positions_opened": 61}	2025-09-17 01:10:35.819351+00
1908	main_trader	HEALTHY	t	t	t	\N	61	0	0	\N	{"sl_set": 64, "sl_failed": 2, "positions_failed": 13, "positions_opened": 61}	2025-09-17 01:11:36.862256+00
1909	main_trader	HEALTHY	t	t	t	\N	61	0	0	\N	{"sl_set": 64, "sl_failed": 2, "positions_failed": 13, "positions_opened": 61}	2025-09-17 01:12:38.509354+00
1910	main_trader	HEALTHY	t	t	t	\N	61	0	0	\N	{"sl_set": 64, "sl_failed": 2, "positions_failed": 13, "positions_opened": 61}	2025-09-17 01:13:39.723027+00
1911	main_trader	HEALTHY	t	t	t	\N	61	0	0	\N	{"sl_set": 64, "sl_failed": 2, "positions_failed": 13, "positions_opened": 61}	2025-09-17 01:14:40.769462+00
1912	main_trader	HEALTHY	t	t	t	\N	61	0	0	\N	{"sl_set": 64, "sl_failed": 2, "positions_failed": 13, "positions_opened": 61}	2025-09-17 01:15:41.94556+00
1913	main_trader	HEALTHY	t	t	t	\N	61	0	0	\N	{"sl_set": 64, "sl_failed": 2, "positions_failed": 13, "positions_opened": 61}	2025-09-17 01:16:43.093097+00
1914	main_trader	HEALTHY	t	t	t	\N	61	0	0	\N	{"sl_set": 64, "sl_failed": 2, "positions_failed": 13, "positions_opened": 61}	2025-09-17 01:17:44.469424+00
1915	main_trader	HEALTHY	t	t	t	\N	61	0	0	\N	{"sl_set": 64, "sl_failed": 2, "positions_failed": 13, "positions_opened": 61}	2025-09-17 01:18:46.215253+00
1916	main_trader	HEALTHY	t	t	t	\N	61	0	0	\N	{"sl_set": 64, "sl_failed": 2, "positions_failed": 13, "positions_opened": 61}	2025-09-17 01:19:47.415406+00
1917	main_trader	HEALTHY	t	t	t	\N	63	0	0	\N	{"sl_set": 66, "sl_failed": 2, "positions_failed": 14, "positions_opened": 63}	2025-09-17 01:20:48.46039+00
1918	main_trader	HEALTHY	t	t	t	\N	63	0	0	\N	{"sl_set": 66, "sl_failed": 2, "positions_failed": 14, "positions_opened": 63}	2025-09-17 01:21:49.512426+00
1919	main_trader	HEALTHY	t	t	t	\N	63	0	0	\N	{"sl_set": 66, "sl_failed": 2, "positions_failed": 14, "positions_opened": 63}	2025-09-17 01:22:50.783384+00
1920	main_trader	HEALTHY	t	t	t	\N	63	0	0	\N	{"sl_set": 66, "sl_failed": 2, "positions_failed": 14, "positions_opened": 63}	2025-09-17 01:23:52.045916+00
1921	main_trader	HEALTHY	t	t	t	\N	63	0	0	\N	{"sl_set": 66, "sl_failed": 2, "positions_failed": 14, "positions_opened": 63}	2025-09-17 01:24:53.097618+00
1922	main_trader	HEALTHY	t	t	t	\N	63	0	0	\N	{"sl_set": 66, "sl_failed": 2, "positions_failed": 14, "positions_opened": 63}	2025-09-17 01:25:54.295351+00
1923	main_trader	HEALTHY	t	t	t	\N	63	0	0	\N	{"sl_set": 66, "sl_failed": 2, "positions_failed": 14, "positions_opened": 63}	2025-09-17 01:26:55.380963+00
1924	main_trader	HEALTHY	t	t	t	\N	63	0	0	\N	{"sl_set": 66, "sl_failed": 2, "positions_failed": 14, "positions_opened": 63}	2025-09-17 01:27:56.798309+00
1925	main_trader	HEALTHY	t	t	t	\N	63	0	0	\N	{"sl_set": 66, "sl_failed": 2, "positions_failed": 14, "positions_opened": 63}	2025-09-17 01:28:58.234067+00
1926	main_trader	HEALTHY	t	t	t	\N	63	0	0	\N	{"sl_set": 66, "sl_failed": 2, "positions_failed": 14, "positions_opened": 63}	2025-09-17 01:29:59.367856+00
1927	main_trader	HEALTHY	t	t	t	\N	63	0	0	\N	{"sl_set": 66, "sl_failed": 2, "positions_failed": 14, "positions_opened": 63}	2025-09-17 01:31:00.42555+00
1928	main_trader	HEALTHY	t	t	t	\N	63	0	0	\N	{"sl_set": 66, "sl_failed": 2, "positions_failed": 14, "positions_opened": 63}	2025-09-17 01:32:01.628871+00
1929	main_trader	HEALTHY	t	t	t	\N	63	0	0	\N	{"sl_set": 66, "sl_failed": 2, "positions_failed": 14, "positions_opened": 63}	2025-09-17 01:33:03.020503+00
1930	main_trader	HEALTHY	t	t	t	\N	63	0	0	\N	{"sl_set": 66, "sl_failed": 2, "positions_failed": 14, "positions_opened": 63}	2025-09-17 01:34:04.139494+00
1931	main_trader	HEALTHY	t	t	t	\N	63	0	0	\N	{"sl_set": 66, "sl_failed": 2, "positions_failed": 14, "positions_opened": 63}	2025-09-17 01:35:05.22608+00
1932	main_trader	HEALTHY	t	t	t	\N	66	0	0	\N	{"sl_set": 70, "sl_failed": 2, "positions_failed": 15, "positions_opened": 66}	2025-09-17 01:36:06.144418+00
1933	main_trader	HEALTHY	t	t	t	\N	66	0	0	\N	{"sl_set": 70, "sl_failed": 2, "positions_failed": 15, "positions_opened": 66}	2025-09-17 01:37:07.30035+00
1934	main_trader	HEALTHY	t	t	t	\N	66	0	0	\N	{"sl_set": 70, "sl_failed": 2, "positions_failed": 15, "positions_opened": 66}	2025-09-17 01:38:09.022008+00
1935	main_trader	HEALTHY	t	t	t	\N	66	0	0	\N	{"sl_set": 70, "sl_failed": 2, "positions_failed": 15, "positions_opened": 66}	2025-09-17 01:39:10.154598+00
1936	main_trader	HEALTHY	t	t	t	\N	66	0	0	\N	{"sl_set": 70, "sl_failed": 2, "positions_failed": 15, "positions_opened": 66}	2025-09-17 01:40:11.669667+00
1937	main_trader	HEALTHY	t	t	t	\N	66	0	0	\N	{"sl_set": 70, "sl_failed": 2, "positions_failed": 15, "positions_opened": 66}	2025-09-17 01:41:13.070984+00
1938	main_trader	HEALTHY	t	t	t	\N	66	0	0	\N	{"sl_set": 70, "sl_failed": 2, "positions_failed": 15, "positions_opened": 66}	2025-09-17 01:42:14.270629+00
1939	main_trader	HEALTHY	t	t	t	\N	66	0	0	\N	{"sl_set": 70, "sl_failed": 2, "positions_failed": 15, "positions_opened": 66}	2025-09-17 01:43:15.938254+00
1940	main_trader	HEALTHY	t	t	t	\N	66	0	0	\N	{"sl_set": 70, "sl_failed": 2, "positions_failed": 15, "positions_opened": 66}	2025-09-17 01:44:17.379791+00
1941	main_trader	HEALTHY	t	t	t	\N	66	0	0	\N	{"sl_set": 70, "sl_failed": 2, "positions_failed": 15, "positions_opened": 66}	2025-09-17 01:45:18.772628+00
1942	main_trader	HEALTHY	t	t	t	\N	66	0	0	\N	{"sl_set": 70, "sl_failed": 2, "positions_failed": 15, "positions_opened": 66}	2025-09-17 01:46:19.905659+00
1943	main_trader	HEALTHY	t	t	t	\N	66	0	0	\N	{"sl_set": 70, "sl_failed": 2, "positions_failed": 15, "positions_opened": 66}	2025-09-17 01:47:20.986562+00
1944	main_trader	HEALTHY	t	t	t	\N	66	0	0	\N	{"sl_set": 70, "sl_failed": 2, "positions_failed": 15, "positions_opened": 66}	2025-09-17 01:48:22.390388+00
1945	main_trader	HEALTHY	t	t	t	\N	66	0	0	\N	{"sl_set": 70, "sl_failed": 2, "positions_failed": 15, "positions_opened": 66}	2025-09-17 01:49:23.639739+00
1946	main_trader	HEALTHY	t	t	t	\N	67	0	0	\N	{"sl_set": 71, "sl_failed": 3, "positions_failed": 15, "positions_opened": 68}	2025-09-17 01:50:24.832522+00
1947	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 73, "sl_failed": 3, "positions_failed": 17, "positions_opened": 70}	2025-09-17 01:51:25.730357+00
1948	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 73, "sl_failed": 3, "positions_failed": 17, "positions_opened": 70}	2025-09-17 01:52:26.867395+00
1949	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 73, "sl_failed": 3, "positions_failed": 17, "positions_opened": 70}	2025-09-17 01:53:28.46209+00
1950	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 73, "sl_failed": 3, "positions_failed": 17, "positions_opened": 70}	2025-09-17 01:54:29.676125+00
1951	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 73, "sl_failed": 3, "positions_failed": 17, "positions_opened": 70}	2025-09-17 01:55:31.072577+00
1952	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 73, "sl_failed": 3, "positions_failed": 17, "positions_opened": 70}	2025-09-17 01:56:32.263421+00
1953	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 73, "sl_failed": 3, "positions_failed": 17, "positions_opened": 70}	2025-09-17 01:57:33.418298+00
1954	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 73, "sl_failed": 3, "positions_failed": 17, "positions_opened": 70}	2025-09-17 01:58:34.798047+00
1955	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 73, "sl_failed": 3, "positions_failed": 17, "positions_opened": 70}	2025-09-17 01:59:36.255946+00
1956	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 73, "sl_failed": 3, "positions_failed": 17, "positions_opened": 70}	2025-09-17 02:00:37.626133+00
1957	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 73, "sl_failed": 3, "positions_failed": 17, "positions_opened": 70}	2025-09-17 02:01:39.083754+00
1958	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 73, "sl_failed": 3, "positions_failed": 17, "positions_opened": 70}	2025-09-17 02:02:40.589808+00
1959	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 73, "sl_failed": 3, "positions_failed": 17, "positions_opened": 70}	2025-09-17 02:03:42.192294+00
1960	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 73, "sl_failed": 3, "positions_failed": 17, "positions_opened": 70}	2025-09-17 02:04:43.439595+00
1961	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 73, "sl_failed": 3, "positions_failed": 17, "positions_opened": 70}	2025-09-17 02:05:44.561407+00
1962	main_trader	HEALTHY	t	t	t	\N	71	0	0	\N	{"sl_set": 74, "sl_failed": 3, "positions_failed": 18, "positions_opened": 71}	2025-09-17 02:06:46.140208+00
1963	main_trader	HEALTHY	t	t	t	\N	71	0	0	\N	{"sl_set": 74, "sl_failed": 3, "positions_failed": 19, "positions_opened": 71}	2025-09-17 02:07:47.598773+00
1964	main_trader	HEALTHY	t	t	t	\N	71	0	0	\N	{"sl_set": 74, "sl_failed": 3, "positions_failed": 19, "positions_opened": 71}	2025-09-17 02:08:48.663275+00
1965	main_trader	HEALTHY	t	t	t	\N	71	0	0	\N	{"sl_set": 74, "sl_failed": 3, "positions_failed": 19, "positions_opened": 71}	2025-09-17 02:09:49.73543+00
1966	main_trader	HEALTHY	t	t	t	\N	71	0	0	\N	{"sl_set": 74, "sl_failed": 3, "positions_failed": 19, "positions_opened": 71}	2025-09-17 02:10:50.937384+00
1967	main_trader	HEALTHY	t	t	t	\N	71	0	0	\N	{"sl_set": 74, "sl_failed": 3, "positions_failed": 19, "positions_opened": 71}	2025-09-17 02:11:52.249942+00
1968	main_trader	HEALTHY	t	t	t	\N	71	0	0	\N	{"sl_set": 74, "sl_failed": 3, "positions_failed": 19, "positions_opened": 71}	2025-09-17 02:12:53.461624+00
1969	main_trader	HEALTHY	t	t	t	\N	71	0	0	\N	{"sl_set": 74, "sl_failed": 3, "positions_failed": 19, "positions_opened": 71}	2025-09-17 02:13:54.534619+00
1970	main_trader	HEALTHY	t	t	t	\N	71	0	0	\N	{"sl_set": 74, "sl_failed": 3, "positions_failed": 19, "positions_opened": 71}	2025-09-17 02:14:55.673411+00
1971	main_trader	HEALTHY	t	t	t	\N	71	0	0	\N	{"sl_set": 74, "sl_failed": 3, "positions_failed": 19, "positions_opened": 71}	2025-09-17 02:15:56.734937+00
1972	main_trader	HEALTHY	t	t	t	\N	71	0	0	\N	{"sl_set": 74, "sl_failed": 3, "positions_failed": 19, "positions_opened": 71}	2025-09-17 02:16:58.083561+00
1973	main_trader	HEALTHY	t	t	t	\N	71	0	0	\N	{"sl_set": 74, "sl_failed": 3, "positions_failed": 19, "positions_opened": 71}	2025-09-17 02:17:59.578195+00
1974	main_trader	HEALTHY	t	t	t	\N	71	0	0	\N	{"sl_set": 74, "sl_failed": 3, "positions_failed": 19, "positions_opened": 71}	2025-09-17 02:19:00.71701+00
1975	main_trader	HEALTHY	t	t	t	\N	71	0	0	\N	{"sl_set": 74, "sl_failed": 3, "positions_failed": 19, "positions_opened": 71}	2025-09-17 02:20:01.884307+00
1976	main_trader	HEALTHY	t	t	t	\N	71	0	0	\N	{"sl_set": 74, "sl_failed": 3, "positions_failed": 19, "positions_opened": 71}	2025-09-17 02:21:03.091953+00
1977	main_trader	HEALTHY	t	t	t	\N	73	0	0	\N	{"sl_set": 76, "sl_failed": 3, "positions_failed": 20, "positions_opened": 73}	2025-09-17 02:22:04.507384+00
1978	main_trader	HEALTHY	t	t	t	\N	73	0	0	\N	{"sl_set": 76, "sl_failed": 3, "positions_failed": 20, "positions_opened": 73}	2025-09-17 02:23:05.63132+00
1979	main_trader	HEALTHY	t	t	t	\N	73	0	0	\N	{"sl_set": 76, "sl_failed": 3, "positions_failed": 20, "positions_opened": 73}	2025-09-17 02:24:06.72157+00
1980	main_trader	HEALTHY	t	t	t	\N	73	0	0	\N	{"sl_set": 76, "sl_failed": 3, "positions_failed": 20, "positions_opened": 73}	2025-09-17 02:25:07.902293+00
1981	main_trader	HEALTHY	t	t	t	\N	73	0	0	\N	{"sl_set": 76, "sl_failed": 3, "positions_failed": 20, "positions_opened": 73}	2025-09-17 02:26:09.304673+00
1982	main_trader	HEALTHY	t	t	t	\N	73	0	0	\N	{"sl_set": 76, "sl_failed": 3, "positions_failed": 20, "positions_opened": 73}	2025-09-17 02:27:11.371051+00
1983	main_trader	HEALTHY	t	t	t	\N	73	0	0	\N	{"sl_set": 76, "sl_failed": 3, "positions_failed": 20, "positions_opened": 73}	2025-09-17 02:28:12.80244+00
1984	main_trader	HEALTHY	t	t	t	\N	73	0	0	\N	{"sl_set": 76, "sl_failed": 3, "positions_failed": 20, "positions_opened": 73}	2025-09-17 02:29:13.993004+00
1985	main_trader	HEALTHY	t	t	t	\N	73	0	0	\N	{"sl_set": 76, "sl_failed": 3, "positions_failed": 20, "positions_opened": 73}	2025-09-17 02:30:15.0468+00
1986	main_trader	HEALTHY	t	t	t	\N	73	0	0	\N	{"sl_set": 76, "sl_failed": 3, "positions_failed": 20, "positions_opened": 73}	2025-09-17 02:31:16.258238+00
1987	main_trader	HEALTHY	t	t	t	\N	73	0	0	\N	{"sl_set": 76, "sl_failed": 3, "positions_failed": 20, "positions_opened": 73}	2025-09-17 02:32:17.593707+00
1988	main_trader	HEALTHY	t	t	t	\N	73	0	0	\N	{"sl_set": 76, "sl_failed": 3, "positions_failed": 20, "positions_opened": 73}	2025-09-17 02:33:18.86316+00
1989	main_trader	HEALTHY	t	t	t	\N	73	0	0	\N	{"sl_set": 76, "sl_failed": 3, "positions_failed": 20, "positions_opened": 73}	2025-09-17 02:34:20.325404+00
1990	main_trader	HEALTHY	t	t	t	\N	73	0	0	\N	{"sl_set": 76, "sl_failed": 3, "positions_failed": 20, "positions_opened": 73}	2025-09-17 02:35:21.821327+00
1991	main_trader	HEALTHY	t	t	t	\N	74	0	0	\N	{"sl_set": 77, "sl_failed": 3, "positions_failed": 20, "positions_opened": 74}	2025-09-17 02:36:23.517877+00
1992	main_trader	HEALTHY	t	t	t	\N	79	0	0	\N	{"sl_set": 82, "sl_failed": 3, "positions_failed": 20, "positions_opened": 79}	2025-09-17 02:37:25.055755+00
1993	main_trader	HEALTHY	t	t	t	\N	80	0	0	\N	{"sl_set": 83, "sl_failed": 3, "positions_failed": 21, "positions_opened": 80}	2025-09-17 02:38:26.115161+00
1994	main_trader	HEALTHY	t	t	t	\N	80	0	0	\N	{"sl_set": 83, "sl_failed": 3, "positions_failed": 21, "positions_opened": 80}	2025-09-17 02:39:27.319949+00
1995	main_trader	HEALTHY	t	t	t	\N	80	0	0	\N	{"sl_set": 83, "sl_failed": 3, "positions_failed": 21, "positions_opened": 80}	2025-09-17 02:40:28.552569+00
1996	main_trader	HEALTHY	t	t	t	\N	80	0	0	\N	{"sl_set": 83, "sl_failed": 3, "positions_failed": 21, "positions_opened": 80}	2025-09-17 02:41:30.347868+00
1997	main_trader	HEALTHY	t	t	t	\N	80	0	0	\N	{"sl_set": 83, "sl_failed": 3, "positions_failed": 21, "positions_opened": 80}	2025-09-17 02:42:31.407864+00
1998	main_trader	HEALTHY	t	t	t	\N	80	0	0	\N	{"sl_set": 83, "sl_failed": 3, "positions_failed": 21, "positions_opened": 80}	2025-09-17 02:43:32.611676+00
1999	main_trader	HEALTHY	t	t	t	\N	80	0	0	\N	{"sl_set": 83, "sl_failed": 3, "positions_failed": 21, "positions_opened": 80}	2025-09-17 02:44:33.771477+00
2000	main_trader	HEALTHY	t	t	t	\N	80	0	0	\N	{"sl_set": 83, "sl_failed": 3, "positions_failed": 21, "positions_opened": 80}	2025-09-17 02:45:34.908251+00
2001	main_trader	HEALTHY	t	t	t	\N	80	0	0	\N	{"sl_set": 83, "sl_failed": 3, "positions_failed": 21, "positions_opened": 80}	2025-09-17 02:46:36.178703+00
2002	main_trader	HEALTHY	t	t	t	\N	80	0	0	\N	{"sl_set": 83, "sl_failed": 3, "positions_failed": 21, "positions_opened": 80}	2025-09-17 02:47:37.399747+00
2003	main_trader	HEALTHY	t	t	t	\N	80	0	0	\N	{"sl_set": 83, "sl_failed": 3, "positions_failed": 21, "positions_opened": 80}	2025-09-17 02:48:38.792993+00
2004	main_trader	HEALTHY	t	t	t	\N	80	0	0	\N	{"sl_set": 83, "sl_failed": 3, "positions_failed": 21, "positions_opened": 80}	2025-09-17 02:49:39.977438+00
2005	main_trader	HEALTHY	t	t	t	\N	80	0	0	\N	{"sl_set": 83, "sl_failed": 3, "positions_failed": 21, "positions_opened": 80}	2025-09-17 02:50:41.172672+00
2006	main_trader	HEALTHY	t	t	t	\N	82	0	0	\N	{"sl_set": 85, "sl_failed": 3, "positions_failed": 21, "positions_opened": 82}	2025-09-17 02:51:42.314085+00
2007	main_trader	HEALTHY	t	t	t	\N	87	0	0	\N	{"sl_set": 90, "sl_failed": 3, "positions_failed": 22, "positions_opened": 87}	2025-09-17 02:52:43.962603+00
2008	main_trader	HEALTHY	t	t	t	\N	93	0	0	\N	{"sl_set": 96, "sl_failed": 3, "positions_failed": 22, "positions_opened": 93}	2025-09-17 02:53:44.933157+00
2009	main_trader	HEALTHY	t	t	t	\N	94	0	0	\N	{"sl_set": 97, "sl_failed": 3, "positions_failed": 22, "positions_opened": 94}	2025-09-17 02:54:46.146545+00
2010	main_trader	HEALTHY	t	t	t	\N	94	0	0	\N	{"sl_set": 97, "sl_failed": 3, "positions_failed": 22, "positions_opened": 94}	2025-09-17 02:55:47.40401+00
2011	main_trader	HEALTHY	t	t	t	\N	94	0	0	\N	{"sl_set": 97, "sl_failed": 3, "positions_failed": 22, "positions_opened": 94}	2025-09-17 02:56:48.527056+00
2012	main_trader	HEALTHY	t	t	t	\N	94	0	0	\N	{"sl_set": 97, "sl_failed": 3, "positions_failed": 22, "positions_opened": 94}	2025-09-17 02:57:50.483913+00
2013	main_trader	HEALTHY	t	t	t	\N	94	0	0	\N	{"sl_set": 97, "sl_failed": 3, "positions_failed": 22, "positions_opened": 94}	2025-09-17 02:58:51.680702+00
2014	main_trader	HEALTHY	t	t	t	\N	94	0	0	\N	{"sl_set": 97, "sl_failed": 3, "positions_failed": 22, "positions_opened": 94}	2025-09-17 02:59:52.880879+00
2015	main_trader	HEALTHY	t	t	t	\N	94	0	0	\N	{"sl_set": 97, "sl_failed": 3, "positions_failed": 22, "positions_opened": 94}	2025-09-17 03:00:53.951549+00
2016	main_trader	HEALTHY	t	t	t	\N	94	0	0	\N	{"sl_set": 97, "sl_failed": 3, "positions_failed": 22, "positions_opened": 94}	2025-09-17 03:01:55.126286+00
2017	main_trader	HEALTHY	t	t	t	\N	94	0	0	\N	{"sl_set": 97, "sl_failed": 3, "positions_failed": 22, "positions_opened": 94}	2025-09-17 03:02:56.556292+00
2018	main_trader	HEALTHY	t	t	t	\N	94	0	0	\N	{"sl_set": 97, "sl_failed": 3, "positions_failed": 22, "positions_opened": 94}	2025-09-17 03:03:57.786264+00
2019	main_trader	HEALTHY	t	t	t	\N	94	0	0	\N	{"sl_set": 97, "sl_failed": 3, "positions_failed": 22, "positions_opened": 94}	2025-09-17 03:04:58.856186+00
2020	main_trader	HEALTHY	t	t	t	\N	94	0	0	\N	{"sl_set": 97, "sl_failed": 3, "positions_failed": 22, "positions_opened": 94}	2025-09-17 03:06:00.029163+00
2021	main_trader	HEALTHY	t	t	t	\N	99	0	0	\N	{"sl_set": 102, "sl_failed": 3, "positions_failed": 22, "positions_opened": 99}	2025-09-17 03:07:00.926306+00
2022	main_trader	HEALTHY	t	t	t	\N	100	0	0	\N	{"sl_set": 103, "sl_failed": 3, "positions_failed": 23, "positions_opened": 100}	2025-09-17 03:08:02.361977+00
2023	main_trader	HEALTHY	t	t	t	\N	100	0	0	\N	{"sl_set": 103, "sl_failed": 3, "positions_failed": 23, "positions_opened": 100}	2025-09-17 03:09:03.496472+00
2024	main_trader	HEALTHY	t	t	t	\N	100	0	0	\N	{"sl_set": 103, "sl_failed": 3, "positions_failed": 23, "positions_opened": 100}	2025-09-17 03:10:04.660088+00
2025	main_trader	HEALTHY	t	t	t	\N	100	0	0	\N	{"sl_set": 103, "sl_failed": 3, "positions_failed": 23, "positions_opened": 100}	2025-09-17 03:11:05.729578+00
2026	main_trader	HEALTHY	t	t	t	\N	100	0	0	\N	{"sl_set": 103, "sl_failed": 3, "positions_failed": 23, "positions_opened": 100}	2025-09-17 03:12:06.803835+00
2027	main_trader	HEALTHY	t	t	t	\N	100	0	0	\N	{"sl_set": 103, "sl_failed": 3, "positions_failed": 23, "positions_opened": 100}	2025-09-17 03:13:08.671546+00
2028	main_trader	HEALTHY	t	t	t	\N	100	0	0	\N	{"sl_set": 103, "sl_failed": 3, "positions_failed": 23, "positions_opened": 100}	2025-09-17 03:14:09.826912+00
2029	main_trader	HEALTHY	t	t	t	\N	100	0	0	\N	{"sl_set": 103, "sl_failed": 3, "positions_failed": 23, "positions_opened": 100}	2025-09-17 03:15:10.998948+00
2030	main_trader	HEALTHY	t	t	t	\N	100	0	0	\N	{"sl_set": 103, "sl_failed": 3, "positions_failed": 23, "positions_opened": 100}	2025-09-17 03:16:12.175633+00
2031	main_trader	HEALTHY	t	t	t	\N	100	0	0	\N	{"sl_set": 103, "sl_failed": 3, "positions_failed": 23, "positions_opened": 100}	2025-09-17 03:17:13.232164+00
2032	main_trader	HEALTHY	t	t	t	\N	100	0	0	\N	{"sl_set": 103, "sl_failed": 3, "positions_failed": 23, "positions_opened": 100}	2025-09-17 03:18:14.534333+00
2033	main_trader	HEALTHY	t	t	t	\N	100	0	0	\N	{"sl_set": 103, "sl_failed": 3, "positions_failed": 23, "positions_opened": 100}	2025-09-17 03:19:15.803416+00
2034	main_trader	HEALTHY	t	t	t	\N	100	0	0	\N	{"sl_set": 103, "sl_failed": 3, "positions_failed": 23, "positions_opened": 100}	2025-09-17 03:20:16.870824+00
2035	main_trader	HEALTHY	t	t	t	\N	101	0	0	\N	{"sl_set": 104, "sl_failed": 3, "positions_failed": 24, "positions_opened": 101}	2025-09-17 03:21:18.045533+00
2036	main_trader	HEALTHY	t	t	t	\N	101	0	0	\N	{"sl_set": 104, "sl_failed": 3, "positions_failed": 24, "positions_opened": 101}	2025-09-17 03:22:19.211178+00
2037	main_trader	HEALTHY	t	t	t	\N	101	0	0	\N	{"sl_set": 104, "sl_failed": 3, "positions_failed": 24, "positions_opened": 101}	2025-09-17 03:23:20.653294+00
2038	main_trader	HEALTHY	t	t	t	\N	101	0	0	\N	{"sl_set": 104, "sl_failed": 3, "positions_failed": 24, "positions_opened": 101}	2025-09-17 03:24:21.807608+00
2039	main_trader	HEALTHY	t	t	t	\N	101	0	0	\N	{"sl_set": 104, "sl_failed": 3, "positions_failed": 24, "positions_opened": 101}	2025-09-17 03:25:22.872582+00
2040	main_trader	HEALTHY	t	t	t	\N	101	0	0	\N	{"sl_set": 104, "sl_failed": 3, "positions_failed": 24, "positions_opened": 101}	2025-09-17 03:26:24.362653+00
2041	main_trader	HEALTHY	t	t	t	\N	101	0	0	\N	{"sl_set": 104, "sl_failed": 3, "positions_failed": 24, "positions_opened": 101}	2025-09-17 03:27:25.514861+00
2042	main_trader	HEALTHY	t	t	t	\N	101	0	0	\N	{"sl_set": 104, "sl_failed": 3, "positions_failed": 24, "positions_opened": 101}	2025-09-17 03:28:27.455021+00
2043	main_trader	HEALTHY	t	t	t	\N	101	0	0	\N	{"sl_set": 104, "sl_failed": 3, "positions_failed": 24, "positions_opened": 101}	2025-09-17 03:29:28.619263+00
2044	main_trader	HEALTHY	t	t	t	\N	101	0	0	\N	{"sl_set": 104, "sl_failed": 3, "positions_failed": 24, "positions_opened": 101}	2025-09-17 03:30:29.776093+00
2045	main_trader	HEALTHY	t	t	t	\N	101	0	0	\N	{"sl_set": 104, "sl_failed": 3, "positions_failed": 24, "positions_opened": 101}	2025-09-17 03:31:30.940493+00
2046	main_trader	HEALTHY	t	t	t	\N	101	0	0	\N	{"sl_set": 104, "sl_failed": 3, "positions_failed": 24, "positions_opened": 101}	2025-09-17 03:32:32.104586+00
2047	main_trader	HEALTHY	t	t	t	\N	101	0	0	\N	{"sl_set": 104, "sl_failed": 3, "positions_failed": 24, "positions_opened": 101}	2025-09-17 03:33:33.502108+00
2048	main_trader	HEALTHY	t	t	t	\N	101	0	0	\N	{"sl_set": 104, "sl_failed": 3, "positions_failed": 24, "positions_opened": 101}	2025-09-17 03:34:34.735397+00
2049	main_trader	HEALTHY	t	t	t	\N	102	0	0	\N	{"sl_set": 105, "sl_failed": 3, "positions_failed": 24, "positions_opened": 103}	2025-09-17 03:35:35.803012+00
2050	main_trader	HEALTHY	t	t	t	\N	104	0	0	\N	{"sl_set": 107, "sl_failed": 3, "positions_failed": 24, "positions_opened": 104}	2025-09-17 03:36:36.884589+00
2051	main_trader	HEALTHY	t	t	t	\N	104	0	0	\N	{"sl_set": 107, "sl_failed": 3, "positions_failed": 24, "positions_opened": 104}	2025-09-17 03:37:38.082967+00
2052	main_trader	HEALTHY	t	t	t	\N	104	0	0	\N	{"sl_set": 107, "sl_failed": 3, "positions_failed": 24, "positions_opened": 104}	2025-09-17 03:38:39.421249+00
2053	main_trader	HEALTHY	t	t	t	\N	104	0	0	\N	{"sl_set": 107, "sl_failed": 3, "positions_failed": 24, "positions_opened": 104}	2025-09-17 03:39:40.610687+00
2054	main_trader	HEALTHY	t	t	t	\N	104	0	0	\N	{"sl_set": 107, "sl_failed": 3, "positions_failed": 24, "positions_opened": 104}	2025-09-17 03:40:41.816365+00
2055	main_trader	HEALTHY	t	t	t	\N	104	0	0	\N	{"sl_set": 107, "sl_failed": 3, "positions_failed": 24, "positions_opened": 104}	2025-09-17 03:41:42.936568+00
2056	main_trader	HEALTHY	t	t	t	\N	104	0	0	\N	{"sl_set": 107, "sl_failed": 3, "positions_failed": 24, "positions_opened": 104}	2025-09-17 03:42:44.112127+00
2057	main_trader	HEALTHY	t	t	t	\N	104	0	0	\N	{"sl_set": 107, "sl_failed": 3, "positions_failed": 24, "positions_opened": 104}	2025-09-17 03:43:46.139965+00
2058	main_trader	HEALTHY	t	t	t	\N	104	0	0	\N	{"sl_set": 107, "sl_failed": 3, "positions_failed": 24, "positions_opened": 104}	2025-09-17 03:44:47.375276+00
2059	main_trader	HEALTHY	t	t	t	\N	104	0	0	\N	{"sl_set": 107, "sl_failed": 3, "positions_failed": 24, "positions_opened": 104}	2025-09-17 03:45:48.445448+00
2060	main_trader	HEALTHY	t	t	t	\N	104	0	0	\N	{"sl_set": 107, "sl_failed": 3, "positions_failed": 24, "positions_opened": 104}	2025-09-17 03:46:49.638243+00
2061	main_trader	HEALTHY	t	t	t	\N	104	0	0	\N	{"sl_set": 107, "sl_failed": 3, "positions_failed": 24, "positions_opened": 104}	2025-09-17 03:47:50.725782+00
2062	main_trader	HEALTHY	t	t	t	\N	104	0	0	\N	{"sl_set": 107, "sl_failed": 3, "positions_failed": 24, "positions_opened": 104}	2025-09-17 03:48:52.166198+00
2063	main_trader	HEALTHY	t	t	t	\N	104	0	0	\N	{"sl_set": 107, "sl_failed": 3, "positions_failed": 24, "positions_opened": 104}	2025-09-17 03:49:53.550031+00
2064	main_trader	HEALTHY	t	t	t	\N	104	0	0	\N	{"sl_set": 107, "sl_failed": 3, "positions_failed": 24, "positions_opened": 104}	2025-09-17 03:50:54.704722+00
2065	main_trader	HEALTHY	t	t	t	\N	106	0	0	\N	{"sl_set": 109, "sl_failed": 3, "positions_failed": 24, "positions_opened": 107}	2025-09-17 03:51:55.593779+00
2066	main_trader	HEALTHY	t	t	t	\N	110	0	0	\N	{"sl_set": 112, "sl_failed": 4, "positions_failed": 24, "positions_opened": 110}	2025-09-17 03:52:56.661749+00
2067	main_trader	HEALTHY	t	t	t	\N	110	0	0	\N	{"sl_set": 112, "sl_failed": 4, "positions_failed": 24, "positions_opened": 110}	2025-09-17 03:53:58.082976+00
2068	main_trader	HEALTHY	t	t	t	\N	110	0	0	\N	{"sl_set": 112, "sl_failed": 4, "positions_failed": 24, "positions_opened": 110}	2025-09-17 03:54:59.344658+00
2069	main_trader	HEALTHY	t	t	t	\N	110	0	0	\N	{"sl_set": 112, "sl_failed": 4, "positions_failed": 24, "positions_opened": 110}	2025-09-17 03:56:00.417358+00
2070	main_trader	HEALTHY	t	t	t	\N	110	0	0	\N	{"sl_set": 112, "sl_failed": 4, "positions_failed": 24, "positions_opened": 110}	2025-09-17 03:57:01.489701+00
2071	main_trader	HEALTHY	t	t	t	\N	110	0	0	\N	{"sl_set": 112, "sl_failed": 4, "positions_failed": 24, "positions_opened": 110}	2025-09-17 03:58:02.643569+00
2072	main_trader	HEALTHY	t	t	t	\N	110	0	0	\N	{"sl_set": 112, "sl_failed": 4, "positions_failed": 24, "positions_opened": 110}	2025-09-17 03:59:04.421039+00
2073	main_trader	HEALTHY	t	t	t	\N	110	0	0	\N	{"sl_set": 112, "sl_failed": 4, "positions_failed": 24, "positions_opened": 110}	2025-09-17 04:00:05.652317+00
2074	main_trader	HEALTHY	t	t	t	\N	110	0	0	\N	{"sl_set": 112, "sl_failed": 4, "positions_failed": 24, "positions_opened": 110}	2025-09-17 04:01:06.727081+00
2075	main_trader	HEALTHY	t	t	t	\N	110	0	0	\N	{"sl_set": 112, "sl_failed": 4, "positions_failed": 24, "positions_opened": 110}	2025-09-17 04:02:07.902069+00
2076	main_trader	HEALTHY	t	t	t	\N	110	0	0	\N	{"sl_set": 112, "sl_failed": 4, "positions_failed": 24, "positions_opened": 110}	2025-09-17 04:03:08.977038+00
2077	main_trader	HEALTHY	t	t	t	\N	110	0	0	\N	{"sl_set": 112, "sl_failed": 4, "positions_failed": 24, "positions_opened": 110}	2025-09-17 04:04:10.386261+00
2078	main_trader	HEALTHY	t	t	t	\N	110	0	0	\N	{"sl_set": 112, "sl_failed": 4, "positions_failed": 24, "positions_opened": 110}	2025-09-17 04:05:11.653935+00
2079	main_trader	HEALTHY	t	t	t	\N	110	0	0	\N	{"sl_set": 112, "sl_failed": 4, "positions_failed": 24, "positions_opened": 110}	2025-09-17 04:06:12.729317+00
2080	main_trader	HEALTHY	t	t	t	\N	113	0	0	\N	{"sl_set": 115, "sl_failed": 4, "positions_failed": 24, "positions_opened": 113}	2025-09-17 04:07:13.906169+00
2081	main_trader	HEALTHY	t	t	t	\N	113	0	0	\N	{"sl_set": 115, "sl_failed": 4, "positions_failed": 24, "positions_opened": 113}	2025-09-17 04:08:15.059223+00
2082	main_trader	HEALTHY	t	t	t	\N	113	0	0	\N	{"sl_set": 115, "sl_failed": 4, "positions_failed": 24, "positions_opened": 113}	2025-09-17 04:09:16.395208+00
2083	main_trader	HEALTHY	t	t	t	\N	113	0	0	\N	{"sl_set": 115, "sl_failed": 4, "positions_failed": 24, "positions_opened": 113}	2025-09-17 04:10:17.635985+00
2084	main_trader	HEALTHY	t	t	t	\N	113	0	0	\N	{"sl_set": 115, "sl_failed": 4, "positions_failed": 24, "positions_opened": 113}	2025-09-17 04:11:19.080144+00
2085	main_trader	HEALTHY	t	t	t	\N	113	0	0	\N	{"sl_set": 115, "sl_failed": 4, "positions_failed": 24, "positions_opened": 113}	2025-09-17 04:12:20.134451+00
2086	main_trader	HEALTHY	t	t	t	\N	113	0	0	\N	{"sl_set": 115, "sl_failed": 4, "positions_failed": 24, "positions_opened": 113}	2025-09-17 04:13:21.607042+00
2087	main_trader	HEALTHY	t	t	t	\N	113	0	0	\N	{"sl_set": 115, "sl_failed": 4, "positions_failed": 24, "positions_opened": 113}	2025-09-17 04:14:23.935432+00
2088	main_trader	HEALTHY	t	t	t	\N	113	0	0	\N	{"sl_set": 115, "sl_failed": 4, "positions_failed": 24, "positions_opened": 113}	2025-09-17 04:15:25.984859+00
2089	main_trader	HEALTHY	t	t	t	\N	113	0	0	\N	{"sl_set": 115, "sl_failed": 4, "positions_failed": 24, "positions_opened": 113}	2025-09-17 04:16:28.003845+00
2090	main_trader	HEALTHY	t	t	t	\N	113	0	0	\N	{"sl_set": 115, "sl_failed": 4, "positions_failed": 24, "positions_opened": 113}	2025-09-17 04:17:29.999492+00
2091	main_trader	HEALTHY	t	t	t	\N	113	0	0	\N	{"sl_set": 115, "sl_failed": 4, "positions_failed": 24, "positions_opened": 113}	2025-09-17 04:18:32.082053+00
2092	main_trader	HEALTHY	t	t	t	\N	113	0	0	\N	{"sl_set": 115, "sl_failed": 4, "positions_failed": 24, "positions_opened": 113}	2025-09-17 04:19:34.279162+00
2093	main_trader	HEALTHY	t	t	t	\N	113	0	0	\N	{"sl_set": 115, "sl_failed": 4, "positions_failed": 24, "positions_opened": 113}	2025-09-17 04:20:36.258684+00
2094	main_trader	HEALTHY	t	t	t	\N	113	0	0	\N	{"sl_set": 115, "sl_failed": 4, "positions_failed": 24, "positions_opened": 113}	2025-09-17 04:21:38.269119+00
2095	main_trader	HEALTHY	t	t	t	\N	113	0	0	\N	{"sl_set": 116, "sl_failed": 4, "positions_failed": 24, "positions_opened": 114}	2025-09-17 04:22:40.361714+00
2096	main_trader	HEALTHY	t	t	t	\N	114	0	0	\N	{"sl_set": 116, "sl_failed": 4, "positions_failed": 25, "positions_opened": 114}	2025-09-17 04:23:42.786829+00
2097	main_trader	HEALTHY	t	t	t	\N	114	0	0	\N	{"sl_set": 116, "sl_failed": 4, "positions_failed": 25, "positions_opened": 114}	2025-09-17 04:24:44.811588+00
2098	main_trader	HEALTHY	t	t	t	\N	114	0	0	\N	{"sl_set": 116, "sl_failed": 4, "positions_failed": 25, "positions_opened": 114}	2025-09-17 04:25:46.313803+00
2099	main_trader	HEALTHY	t	t	t	\N	114	0	0	\N	{"sl_set": 116, "sl_failed": 4, "positions_failed": 25, "positions_opened": 114}	2025-09-17 04:26:48.303156+00
2100	main_trader	HEALTHY	t	t	t	\N	114	0	0	\N	{"sl_set": 116, "sl_failed": 4, "positions_failed": 25, "positions_opened": 114}	2025-09-17 04:27:50.697156+00
2101	main_trader	HEALTHY	t	t	t	\N	114	0	0	\N	{"sl_set": 116, "sl_failed": 4, "positions_failed": 25, "positions_opened": 114}	2025-09-17 04:28:52.038224+00
2102	main_trader	HEALTHY	t	t	t	\N	114	0	0	\N	{"sl_set": 116, "sl_failed": 4, "positions_failed": 25, "positions_opened": 114}	2025-09-17 04:29:53.461299+00
2103	main_trader	HEALTHY	t	t	t	\N	114	0	0	\N	{"sl_set": 116, "sl_failed": 4, "positions_failed": 25, "positions_opened": 114}	2025-09-17 04:30:55.47206+00
2104	main_trader	HEALTHY	t	t	t	\N	114	0	0	\N	{"sl_set": 116, "sl_failed": 4, "positions_failed": 25, "positions_opened": 114}	2025-09-17 04:31:57.117964+00
2105	main_trader	HEALTHY	t	t	t	\N	114	0	0	\N	{"sl_set": 116, "sl_failed": 4, "positions_failed": 25, "positions_opened": 114}	2025-09-17 04:32:59.002567+00
2106	main_trader	HEALTHY	t	t	t	\N	114	0	0	\N	{"sl_set": 116, "sl_failed": 4, "positions_failed": 25, "positions_opened": 114}	2025-09-17 04:34:00.633222+00
2107	main_trader	HEALTHY	t	t	t	\N	114	0	0	\N	{"sl_set": 116, "sl_failed": 4, "positions_failed": 25, "positions_opened": 114}	2025-09-17 04:35:02.621961+00
2108	main_trader	HEALTHY	t	t	t	\N	114	0	0	\N	{"sl_set": 116, "sl_failed": 4, "positions_failed": 25, "positions_opened": 114}	2025-09-17 04:36:04.113883+00
2109	main_trader	HEALTHY	t	t	t	\N	114	0	0	\N	{"sl_set": 116, "sl_failed": 4, "positions_failed": 25, "positions_opened": 114}	2025-09-17 04:37:05.99362+00
2110	main_trader	HEALTHY	t	t	t	\N	114	0	0	\N	{"sl_set": 116, "sl_failed": 4, "positions_failed": 25, "positions_opened": 114}	2025-09-17 04:38:07.805449+00
2111	main_trader	HEALTHY	t	t	t	\N	114	0	0	\N	{"sl_set": 116, "sl_failed": 4, "positions_failed": 25, "positions_opened": 114}	2025-09-17 04:39:09.865998+00
2112	main_trader	HEALTHY	t	t	t	\N	114	0	0	\N	{"sl_set": 116, "sl_failed": 4, "positions_failed": 25, "positions_opened": 114}	2025-09-17 04:40:11.520677+00
2113	main_trader	HEALTHY	t	t	t	\N	114	0	0	\N	{"sl_set": 116, "sl_failed": 4, "positions_failed": 25, "positions_opened": 114}	2025-09-17 04:41:12.698002+00
2114	main_trader	HEALTHY	t	t	t	\N	114	0	0	\N	{"sl_set": 116, "sl_failed": 4, "positions_failed": 25, "positions_opened": 114}	2025-09-17 04:42:14.097567+00
2115	main_trader	HEALTHY	t	t	t	\N	114	0	0	\N	{"sl_set": 116, "sl_failed": 4, "positions_failed": 25, "positions_opened": 114}	2025-09-17 04:43:15.492764+00
2116	main_trader	HEALTHY	t	t	t	\N	114	0	0	\N	{"sl_set": 116, "sl_failed": 4, "positions_failed": 25, "positions_opened": 114}	2025-09-17 04:44:16.644977+00
2117	main_trader	HEALTHY	t	t	t	\N	114	0	0	\N	{"sl_set": 116, "sl_failed": 4, "positions_failed": 25, "positions_opened": 114}	2025-09-17 04:45:18.150342+00
2118	main_trader	HEALTHY	t	t	t	\N	114	0	0	\N	{"sl_set": 116, "sl_failed": 4, "positions_failed": 25, "positions_opened": 114}	2025-09-17 04:46:19.557629+00
2119	main_trader	HEALTHY	t	t	t	\N	114	0	0	\N	{"sl_set": 116, "sl_failed": 4, "positions_failed": 25, "positions_opened": 114}	2025-09-17 04:47:21.071053+00
2120	main_trader	HEALTHY	t	t	t	\N	114	0	0	\N	{"sl_set": 116, "sl_failed": 4, "positions_failed": 25, "positions_opened": 114}	2025-09-17 04:48:22.803618+00
2121	main_trader	HEALTHY	t	t	t	\N	114	0	0	\N	{"sl_set": 116, "sl_failed": 4, "positions_failed": 25, "positions_opened": 114}	2025-09-17 04:49:24.278436+00
2122	main_trader	HEALTHY	t	t	t	\N	114	0	0	\N	{"sl_set": 116, "sl_failed": 4, "positions_failed": 25, "positions_opened": 114}	2025-09-17 04:50:25.69539+00
2123	main_trader	HEALTHY	t	t	t	\N	115	0	0	\N	{"sl_set": 117, "sl_failed": 4, "positions_failed": 25, "positions_opened": 115}	2025-09-17 04:51:26.938961+00
2124	main_trader	HEALTHY	t	t	t	\N	117	0	0	\N	{"sl_set": 119, "sl_failed": 4, "positions_failed": 26, "positions_opened": 117}	2025-09-17 04:52:28.121438+00
2125	main_trader	HEALTHY	t	t	t	\N	117	0	0	\N	{"sl_set": 119, "sl_failed": 4, "positions_failed": 26, "positions_opened": 117}	2025-09-17 04:53:29.428341+00
2126	main_trader	HEALTHY	t	t	t	\N	117	0	0	\N	{"sl_set": 119, "sl_failed": 4, "positions_failed": 26, "positions_opened": 117}	2025-09-17 04:54:30.964446+00
2127	main_trader	HEALTHY	t	t	t	\N	117	0	0	\N	{"sl_set": 119, "sl_failed": 4, "positions_failed": 26, "positions_opened": 117}	2025-09-17 04:55:32.055538+00
2128	main_trader	HEALTHY	t	t	t	\N	117	0	0	\N	{"sl_set": 119, "sl_failed": 4, "positions_failed": 26, "positions_opened": 117}	2025-09-17 04:56:33.237827+00
2129	main_trader	HEALTHY	t	t	t	\N	117	0	0	\N	{"sl_set": 119, "sl_failed": 4, "positions_failed": 26, "positions_opened": 117}	2025-09-17 04:57:34.308655+00
2130	main_trader	HEALTHY	t	t	t	\N	117	0	0	\N	{"sl_set": 119, "sl_failed": 4, "positions_failed": 26, "positions_opened": 117}	2025-09-17 04:58:36.186924+00
2131	main_trader	HEALTHY	t	t	t	\N	117	0	0	\N	{"sl_set": 119, "sl_failed": 4, "positions_failed": 26, "positions_opened": 117}	2025-09-17 04:59:37.444382+00
2132	main_trader	HEALTHY	t	t	t	\N	117	0	0	\N	{"sl_set": 119, "sl_failed": 4, "positions_failed": 26, "positions_opened": 117}	2025-09-17 05:00:38.618111+00
2133	main_trader	HEALTHY	t	t	t	\N	117	0	0	\N	{"sl_set": 119, "sl_failed": 4, "positions_failed": 26, "positions_opened": 117}	2025-09-17 05:01:39.689768+00
2134	main_trader	HEALTHY	t	t	t	\N	117	0	0	\N	{"sl_set": 119, "sl_failed": 4, "positions_failed": 26, "positions_opened": 117}	2025-09-17 05:02:40.87085+00
2135	main_trader	HEALTHY	t	t	t	\N	117	0	0	\N	{"sl_set": 119, "sl_failed": 4, "positions_failed": 26, "positions_opened": 117}	2025-09-17 05:03:42.324333+00
2136	main_trader	HEALTHY	t	t	t	\N	117	0	0	\N	{"sl_set": 119, "sl_failed": 4, "positions_failed": 26, "positions_opened": 117}	2025-09-17 05:04:43.472938+00
2137	main_trader	HEALTHY	t	t	t	\N	117	0	0	\N	{"sl_set": 119, "sl_failed": 4, "positions_failed": 26, "positions_opened": 117}	2025-09-17 05:05:44.65664+00
2138	main_trader	HEALTHY	t	t	t	\N	118	0	0	\N	{"sl_set": 120, "sl_failed": 4, "positions_failed": 26, "positions_opened": 118}	2025-09-17 05:06:45.574941+00
2139	main_trader	HEALTHY	t	t	t	\N	118	0	0	\N	{"sl_set": 120, "sl_failed": 4, "positions_failed": 26, "positions_opened": 118}	2025-09-17 05:07:46.777875+00
2140	main_trader	HEALTHY	t	t	t	\N	118	0	0	\N	{"sl_set": 120, "sl_failed": 4, "positions_failed": 26, "positions_opened": 118}	2025-09-17 05:08:48.2036+00
2141	main_trader	HEALTHY	t	t	t	\N	118	0	0	\N	{"sl_set": 120, "sl_failed": 4, "positions_failed": 26, "positions_opened": 118}	2025-09-17 05:09:49.468876+00
2142	main_trader	HEALTHY	t	t	t	\N	118	0	0	\N	{"sl_set": 120, "sl_failed": 4, "positions_failed": 26, "positions_opened": 118}	2025-09-17 05:10:50.535378+00
2143	main_trader	HEALTHY	t	t	t	\N	118	0	0	\N	{"sl_set": 120, "sl_failed": 4, "positions_failed": 26, "positions_opened": 118}	2025-09-17 05:11:51.618664+00
2144	main_trader	HEALTHY	t	t	t	\N	118	0	0	\N	{"sl_set": 120, "sl_failed": 4, "positions_failed": 26, "positions_opened": 118}	2025-09-17 05:12:52.803365+00
2145	main_trader	HEALTHY	t	t	t	\N	118	0	0	\N	{"sl_set": 120, "sl_failed": 4, "positions_failed": 26, "positions_opened": 118}	2025-09-17 05:13:54.56861+00
2146	main_trader	HEALTHY	t	t	t	\N	118	0	0	\N	{"sl_set": 120, "sl_failed": 4, "positions_failed": 26, "positions_opened": 118}	2025-09-17 05:14:55.884198+00
2147	main_trader	HEALTHY	t	t	t	\N	118	0	0	\N	{"sl_set": 120, "sl_failed": 4, "positions_failed": 26, "positions_opened": 118}	2025-09-17 05:15:57.089861+00
2148	main_trader	HEALTHY	t	t	t	\N	118	0	0	\N	{"sl_set": 120, "sl_failed": 4, "positions_failed": 26, "positions_opened": 118}	2025-09-17 05:16:58.285179+00
2149	main_trader	HEALTHY	t	t	t	\N	118	0	0	\N	{"sl_set": 120, "sl_failed": 4, "positions_failed": 26, "positions_opened": 118}	2025-09-17 05:17:59.362069+00
2150	main_trader	HEALTHY	t	t	t	\N	118	0	0	\N	{"sl_set": 120, "sl_failed": 4, "positions_failed": 26, "positions_opened": 118}	2025-09-17 05:19:01.089214+00
2151	main_trader	HEALTHY	t	t	t	\N	118	0	0	\N	{"sl_set": 120, "sl_failed": 4, "positions_failed": 26, "positions_opened": 118}	2025-09-17 05:20:02.366958+00
2152	main_trader	HEALTHY	t	t	t	\N	118	0	0	\N	{"sl_set": 120, "sl_failed": 4, "positions_failed": 26, "positions_opened": 118}	2025-09-17 05:21:03.858647+00
2153	main_trader	HEALTHY	t	t	t	\N	119	0	0	\N	{"sl_set": 121, "sl_failed": 4, "positions_failed": 26, "positions_opened": 119}	2025-09-17 05:22:05.049289+00
2154	main_trader	HEALTHY	t	t	t	\N	119	0	0	\N	{"sl_set": 121, "sl_failed": 4, "positions_failed": 26, "positions_opened": 119}	2025-09-17 05:23:06.176186+00
2155	main_trader	HEALTHY	t	t	t	\N	119	0	0	\N	{"sl_set": 121, "sl_failed": 4, "positions_failed": 26, "positions_opened": 119}	2025-09-17 05:24:07.516628+00
2156	main_trader	HEALTHY	t	t	t	\N	119	0	0	\N	{"sl_set": 121, "sl_failed": 4, "positions_failed": 26, "positions_opened": 119}	2025-09-17 05:25:09.02681+00
2157	main_trader	HEALTHY	t	t	t	\N	119	0	0	\N	{"sl_set": 121, "sl_failed": 4, "positions_failed": 26, "positions_opened": 119}	2025-09-17 05:26:10.223012+00
2158	main_trader	HEALTHY	t	t	t	\N	119	0	0	\N	{"sl_set": 121, "sl_failed": 4, "positions_failed": 26, "positions_opened": 119}	2025-09-17 05:27:11.297735+00
2159	main_trader	HEALTHY	t	t	t	\N	119	0	0	\N	{"sl_set": 121, "sl_failed": 4, "positions_failed": 26, "positions_opened": 119}	2025-09-17 05:28:12.384575+00
2160	main_trader	HEALTHY	t	t	t	\N	119	0	0	\N	{"sl_set": 121, "sl_failed": 4, "positions_failed": 26, "positions_opened": 119}	2025-09-17 05:29:14.309783+00
2161	main_trader	HEALTHY	t	t	t	\N	119	0	0	\N	{"sl_set": 121, "sl_failed": 4, "positions_failed": 26, "positions_opened": 119}	2025-09-17 05:30:15.475581+00
2162	main_trader	HEALTHY	t	t	t	\N	119	0	0	\N	{"sl_set": 121, "sl_failed": 4, "positions_failed": 26, "positions_opened": 119}	2025-09-17 05:31:16.632466+00
2163	main_trader	HEALTHY	t	t	t	\N	119	0	0	\N	{"sl_set": 121, "sl_failed": 4, "positions_failed": 26, "positions_opened": 119}	2025-09-17 05:32:17.795698+00
2164	main_trader	HEALTHY	t	t	t	\N	119	0	0	\N	{"sl_set": 121, "sl_failed": 4, "positions_failed": 26, "positions_opened": 119}	2025-09-17 05:33:18.888554+00
2165	main_trader	HEALTHY	t	t	t	\N	119	0	0	\N	{"sl_set": 121, "sl_failed": 4, "positions_failed": 26, "positions_opened": 119}	2025-09-17 05:34:20.323191+00
2166	main_trader	HEALTHY	t	t	t	\N	119	0	0	\N	{"sl_set": 121, "sl_failed": 4, "positions_failed": 26, "positions_opened": 119}	2025-09-17 05:35:21.633383+00
2167	main_trader	HEALTHY	t	t	t	\N	119	0	0	\N	{"sl_set": 121, "sl_failed": 4, "positions_failed": 26, "positions_opened": 119}	2025-09-17 05:36:22.704847+00
2168	main_trader	HEALTHY	t	t	t	\N	119	0	0	\N	{"sl_set": 121, "sl_failed": 4, "positions_failed": 26, "positions_opened": 119}	2025-09-17 05:37:23.807428+00
2169	main_trader	HEALTHY	t	t	t	\N	119	0	0	\N	{"sl_set": 121, "sl_failed": 4, "positions_failed": 26, "positions_opened": 119}	2025-09-17 05:38:26.006793+00
2170	main_trader	HEALTHY	t	t	t	\N	119	0	0	\N	{"sl_set": 121, "sl_failed": 4, "positions_failed": 26, "positions_opened": 119}	2025-09-17 05:39:27.311863+00
2171	main_trader	HEALTHY	t	t	t	\N	119	0	0	\N	{"sl_set": 121, "sl_failed": 4, "positions_failed": 26, "positions_opened": 119}	2025-09-17 05:40:28.559359+00
2172	main_trader	HEALTHY	t	t	t	\N	119	0	0	\N	{"sl_set": 121, "sl_failed": 4, "positions_failed": 26, "positions_opened": 119}	2025-09-17 05:41:29.761147+00
2173	main_trader	HEALTHY	t	t	t	\N	119	0	0	\N	{"sl_set": 121, "sl_failed": 4, "positions_failed": 26, "positions_opened": 119}	2025-09-17 05:42:30.83397+00
2174	main_trader	HEALTHY	t	t	t	\N	119	0	0	\N	{"sl_set": 121, "sl_failed": 4, "positions_failed": 26, "positions_opened": 119}	2025-09-17 05:43:32.038602+00
2175	main_trader	HEALTHY	t	t	t	\N	119	0	0	\N	{"sl_set": 121, "sl_failed": 4, "positions_failed": 26, "positions_opened": 119}	2025-09-17 05:44:33.47125+00
2176	main_trader	HEALTHY	t	t	t	\N	119	0	0	\N	{"sl_set": 121, "sl_failed": 4, "positions_failed": 26, "positions_opened": 119}	2025-09-17 05:45:34.738497+00
2177	main_trader	HEALTHY	t	t	t	\N	119	0	0	\N	{"sl_set": 121, "sl_failed": 4, "positions_failed": 26, "positions_opened": 119}	2025-09-17 05:46:35.819332+00
2178	main_trader	HEALTHY	t	t	t	\N	119	0	0	\N	{"sl_set": 121, "sl_failed": 4, "positions_failed": 26, "positions_opened": 119}	2025-09-17 05:47:36.984367+00
2179	main_trader	HEALTHY	t	t	t	\N	119	0	0	\N	{"sl_set": 121, "sl_failed": 4, "positions_failed": 26, "positions_opened": 119}	2025-09-17 05:48:38.1875+00
2180	main_trader	HEALTHY	t	t	t	\N	119	0	0	\N	{"sl_set": 121, "sl_failed": 4, "positions_failed": 26, "positions_opened": 119}	2025-09-17 05:49:39.489939+00
2181	main_trader	HEALTHY	t	t	t	\N	119	0	0	\N	{"sl_set": 121, "sl_failed": 4, "positions_failed": 26, "positions_opened": 119}	2025-09-17 05:50:40.7445+00
2182	main_trader	HEALTHY	t	t	t	\N	121	0	0	\N	{"sl_set": 123, "sl_failed": 4, "positions_failed": 27, "positions_opened": 121}	2025-09-17 05:51:41.649257+00
2183	main_trader	HEALTHY	t	t	t	\N	121	0	0	\N	{"sl_set": 123, "sl_failed": 4, "positions_failed": 27, "positions_opened": 121}	2025-09-17 05:52:42.726613+00
2184	main_trader	HEALTHY	t	t	t	\N	121	0	0	\N	{"sl_set": 123, "sl_failed": 4, "positions_failed": 27, "positions_opened": 121}	2025-09-17 05:53:43.844107+00
2185	main_trader	HEALTHY	t	t	t	\N	121	0	0	\N	{"sl_set": 123, "sl_failed": 4, "positions_failed": 27, "positions_opened": 121}	2025-09-17 05:54:44.99888+00
2186	main_trader	HEALTHY	t	t	t	\N	121	0	0	\N	{"sl_set": 123, "sl_failed": 4, "positions_failed": 27, "positions_opened": 121}	2025-09-17 05:55:46.150476+00
2187	main_trader	HEALTHY	t	t	t	\N	121	0	0	\N	{"sl_set": 123, "sl_failed": 4, "positions_failed": 27, "positions_opened": 121}	2025-09-17 05:56:47.633573+00
2188	main_trader	HEALTHY	t	t	t	\N	121	0	0	\N	{"sl_set": 123, "sl_failed": 4, "positions_failed": 27, "positions_opened": 121}	2025-09-17 05:57:48.810661+00
2189	main_trader	HEALTHY	t	t	t	\N	121	0	0	\N	{"sl_set": 123, "sl_failed": 4, "positions_failed": 27, "positions_opened": 121}	2025-09-17 05:58:49.894197+00
2190	main_trader	HEALTHY	t	t	t	\N	121	0	0	\N	{"sl_set": 123, "sl_failed": 4, "positions_failed": 27, "positions_opened": 121}	2025-09-17 05:59:51.057731+00
2191	main_trader	HEALTHY	t	t	t	\N	121	0	0	\N	{"sl_set": 123, "sl_failed": 4, "positions_failed": 27, "positions_opened": 121}	2025-09-17 06:00:52.21184+00
2192	main_trader	HEALTHY	t	t	t	\N	121	0	0	\N	{"sl_set": 123, "sl_failed": 4, "positions_failed": 27, "positions_opened": 121}	2025-09-17 06:01:53.391894+00
2193	main_trader	HEALTHY	t	t	t	\N	121	0	0	\N	{"sl_set": 123, "sl_failed": 4, "positions_failed": 27, "positions_opened": 121}	2025-09-17 06:02:54.455255+00
2194	main_trader	HEALTHY	t	t	t	\N	121	0	0	\N	{"sl_set": 123, "sl_failed": 4, "positions_failed": 27, "positions_opened": 121}	2025-09-17 06:03:55.91461+00
2195	main_trader	HEALTHY	t	t	t	\N	121	0	0	\N	{"sl_set": 123, "sl_failed": 4, "positions_failed": 27, "positions_opened": 121}	2025-09-17 06:04:57.23744+00
2196	main_trader	HEALTHY	t	t	t	\N	121	0	0	\N	{"sl_set": 123, "sl_failed": 4, "positions_failed": 27, "positions_opened": 121}	2025-09-17 06:05:58.486122+00
2197	main_trader	HEALTHY	t	t	t	\N	125	0	0	\N	{"sl_set": 127, "sl_failed": 4, "positions_failed": 27, "positions_opened": 125}	2025-09-17 06:06:59.396111+00
2198	main_trader	HEALTHY	t	t	t	\N	130	0	0	\N	{"sl_set": 132, "sl_failed": 4, "positions_failed": 27, "positions_opened": 130}	2025-09-17 06:08:00.301233+00
2199	main_trader	HEALTHY	t	t	t	\N	130	0	0	\N	{"sl_set": 132, "sl_failed": 4, "positions_failed": 27, "positions_opened": 130}	2025-09-17 06:09:01.389038+00
2200	main_trader	HEALTHY	t	t	t	\N	130	0	0	\N	{"sl_set": 132, "sl_failed": 4, "positions_failed": 27, "positions_opened": 130}	2025-09-17 06:10:02.661153+00
2201	main_trader	HEALTHY	t	t	t	\N	130	0	0	\N	{"sl_set": 132, "sl_failed": 4, "positions_failed": 27, "positions_opened": 130}	2025-09-17 06:11:03.938265+00
2202	main_trader	HEALTHY	t	t	t	\N	130	0	0	\N	{"sl_set": 132, "sl_failed": 4, "positions_failed": 27, "positions_opened": 130}	2025-09-17 06:12:05.011458+00
2203	main_trader	HEALTHY	t	t	t	\N	130	0	0	\N	{"sl_set": 132, "sl_failed": 4, "positions_failed": 27, "positions_opened": 130}	2025-09-17 06:13:06.204675+00
2204	main_trader	HEALTHY	t	t	t	\N	130	0	0	\N	{"sl_set": 132, "sl_failed": 4, "positions_failed": 27, "positions_opened": 130}	2025-09-17 06:14:07.268588+00
2205	main_trader	HEALTHY	t	t	t	\N	130	0	0	\N	{"sl_set": 132, "sl_failed": 4, "positions_failed": 27, "positions_opened": 130}	2025-09-17 06:15:08.435785+00
2206	main_trader	HEALTHY	t	t	t	\N	130	0	0	\N	{"sl_set": 132, "sl_failed": 4, "positions_failed": 27, "positions_opened": 130}	2025-09-17 06:16:09.71028+00
2207	main_trader	HEALTHY	t	t	t	\N	130	0	0	\N	{"sl_set": 132, "sl_failed": 4, "positions_failed": 27, "positions_opened": 130}	2025-09-17 06:17:10.795679+00
2208	main_trader	HEALTHY	t	t	t	\N	130	0	0	\N	{"sl_set": 132, "sl_failed": 4, "positions_failed": 27, "positions_opened": 130}	2025-09-17 06:18:11.999051+00
2209	main_trader	HEALTHY	t	t	t	\N	130	0	0	\N	{"sl_set": 132, "sl_failed": 4, "positions_failed": 27, "positions_opened": 130}	2025-09-17 06:19:13.192682+00
2210	main_trader	HEALTHY	t	t	t	\N	130	0	0	\N	{"sl_set": 132, "sl_failed": 4, "positions_failed": 27, "positions_opened": 130}	2025-09-17 06:20:14.626547+00
2211	main_trader	HEALTHY	t	t	t	\N	130	0	0	\N	{"sl_set": 133, "sl_failed": 4, "positions_failed": 27, "positions_opened": 131}	2025-09-17 06:21:15.63675+00
2212	main_trader	HEALTHY	t	t	t	\N	134	0	0	\N	{"sl_set": 136, "sl_failed": 4, "positions_failed": 27, "positions_opened": 134}	2025-09-17 06:22:17.828084+00
2213	main_trader	HEALTHY	t	t	t	\N	134	0	0	\N	{"sl_set": 136, "sl_failed": 4, "positions_failed": 27, "positions_opened": 134}	2025-09-17 06:23:19.837463+00
2214	main_trader	HEALTHY	t	t	t	\N	134	0	0	\N	{"sl_set": 136, "sl_failed": 4, "positions_failed": 27, "positions_opened": 134}	2025-09-17 06:24:21.730621+00
2215	main_trader	HEALTHY	t	t	t	\N	134	0	0	\N	{"sl_set": 136, "sl_failed": 4, "positions_failed": 27, "positions_opened": 134}	2025-09-17 06:25:23.087746+00
2216	main_trader	HEALTHY	t	t	t	\N	134	0	0	\N	{"sl_set": 136, "sl_failed": 4, "positions_failed": 27, "positions_opened": 134}	2025-09-17 06:26:25.001684+00
2217	main_trader	HEALTHY	t	t	t	\N	134	0	0	\N	{"sl_set": 136, "sl_failed": 4, "positions_failed": 27, "positions_opened": 134}	2025-09-17 06:27:27.80366+00
2218	main_trader	HEALTHY	t	t	t	\N	134	0	0	\N	{"sl_set": 136, "sl_failed": 4, "positions_failed": 27, "positions_opened": 134}	2025-09-17 06:28:29.83889+00
2219	main_trader	HEALTHY	t	t	t	\N	134	0	0	\N	{"sl_set": 136, "sl_failed": 4, "positions_failed": 27, "positions_opened": 134}	2025-09-17 06:29:32.298396+00
2220	main_trader	HEALTHY	t	t	t	\N	134	0	0	\N	{"sl_set": 136, "sl_failed": 4, "positions_failed": 27, "positions_opened": 134}	2025-09-17 06:30:34.278527+00
2221	main_trader	HEALTHY	t	t	t	\N	134	0	0	\N	{"sl_set": 136, "sl_failed": 4, "positions_failed": 27, "positions_opened": 134}	2025-09-17 06:31:36.091033+00
2222	main_trader	HEALTHY	t	t	t	\N	134	0	0	\N	{"sl_set": 136, "sl_failed": 4, "positions_failed": 27, "positions_opened": 134}	2025-09-17 06:32:38.055792+00
2223	main_trader	HEALTHY	t	t	t	\N	134	0	0	\N	{"sl_set": 136, "sl_failed": 4, "positions_failed": 27, "positions_opened": 134}	2025-09-17 06:33:39.945488+00
2224	main_trader	HEALTHY	t	t	t	\N	134	0	0	\N	{"sl_set": 136, "sl_failed": 4, "positions_failed": 27, "positions_opened": 134}	2025-09-17 06:34:41.968627+00
2225	main_trader	HEALTHY	t	t	t	\N	134	0	0	\N	{"sl_set": 136, "sl_failed": 4, "positions_failed": 27, "positions_opened": 134}	2025-09-17 06:35:43.939053+00
2226	main_trader	HEALTHY	t	t	t	\N	137	0	0	\N	{"sl_set": 139, "sl_failed": 4, "positions_failed": 27, "positions_opened": 137}	2025-09-17 06:36:45.560189+00
2227	main_trader	HEALTHY	t	t	t	\N	138	0	0	\N	{"sl_set": 140, "sl_failed": 4, "positions_failed": 27, "positions_opened": 138}	2025-09-17 06:37:47.47366+00
2228	main_trader	HEALTHY	t	t	t	\N	138	0	0	\N	{"sl_set": 140, "sl_failed": 4, "positions_failed": 27, "positions_opened": 138}	2025-09-17 06:38:49.387947+00
2229	main_trader	HEALTHY	t	t	t	\N	138	0	0	\N	{"sl_set": 140, "sl_failed": 4, "positions_failed": 27, "positions_opened": 138}	2025-09-17 06:39:51.828807+00
2230	main_trader	HEALTHY	t	t	t	\N	138	0	0	\N	{"sl_set": 140, "sl_failed": 4, "positions_failed": 27, "positions_opened": 138}	2025-09-17 06:40:53.84638+00
2231	main_trader	HEALTHY	t	t	t	\N	138	0	0	\N	{"sl_set": 140, "sl_failed": 4, "positions_failed": 27, "positions_opened": 138}	2025-09-17 06:41:55.650286+00
2232	main_trader	HEALTHY	t	t	t	\N	138	0	0	\N	{"sl_set": 140, "sl_failed": 4, "positions_failed": 27, "positions_opened": 138}	2025-09-17 06:42:57.539158+00
2233	main_trader	HEALTHY	t	t	t	\N	138	0	0	\N	{"sl_set": 140, "sl_failed": 4, "positions_failed": 27, "positions_opened": 138}	2025-09-17 06:43:59.342217+00
2234	main_trader	HEALTHY	t	t	t	\N	138	0	0	\N	{"sl_set": 140, "sl_failed": 4, "positions_failed": 27, "positions_opened": 138}	2025-09-17 06:45:01.963643+00
2235	main_trader	HEALTHY	t	t	t	\N	138	0	0	\N	{"sl_set": 140, "sl_failed": 4, "positions_failed": 27, "positions_opened": 138}	2025-09-17 06:46:03.972187+00
2236	main_trader	HEALTHY	t	t	t	\N	138	0	0	\N	{"sl_set": 140, "sl_failed": 4, "positions_failed": 27, "positions_opened": 138}	2025-09-17 06:47:05.875951+00
2237	main_trader	HEALTHY	t	t	t	\N	138	0	0	\N	{"sl_set": 140, "sl_failed": 4, "positions_failed": 27, "positions_opened": 138}	2025-09-17 06:48:07.69762+00
2238	main_trader	HEALTHY	t	t	t	\N	138	0	0	\N	{"sl_set": 140, "sl_failed": 4, "positions_failed": 27, "positions_opened": 138}	2025-09-17 06:49:09.639026+00
2239	main_trader	HEALTHY	t	t	t	\N	138	0	0	\N	{"sl_set": 140, "sl_failed": 4, "positions_failed": 27, "positions_opened": 138}	2025-09-17 06:50:11.700221+00
2240	main_trader	HEALTHY	t	t	t	\N	138	0	0	\N	{"sl_set": 140, "sl_failed": 4, "positions_failed": 27, "positions_opened": 139}	2025-09-17 06:51:13.594553+00
2241	main_trader	HEALTHY	t	t	t	\N	140	0	0	\N	{"sl_set": 142, "sl_failed": 4, "positions_failed": 27, "positions_opened": 140}	2025-09-17 06:52:15.403775+00
2242	main_trader	HEALTHY	t	t	t	\N	140	0	0	\N	{"sl_set": 142, "sl_failed": 4, "positions_failed": 27, "positions_opened": 140}	2025-09-17 06:53:17.343551+00
2243	main_trader	HEALTHY	t	t	t	\N	140	0	0	\N	{"sl_set": 142, "sl_failed": 4, "positions_failed": 27, "positions_opened": 140}	2025-09-17 06:54:19.259594+00
2244	main_trader	HEALTHY	t	t	t	\N	140	0	0	\N	{"sl_set": 142, "sl_failed": 4, "positions_failed": 27, "positions_opened": 140}	2025-09-17 06:55:21.386196+00
2245	main_trader	HEALTHY	t	t	t	\N	140	0	0	\N	{"sl_set": 142, "sl_failed": 4, "positions_failed": 27, "positions_opened": 140}	2025-09-17 06:56:23.387723+00
2246	main_trader	HEALTHY	t	t	t	\N	140	0	0	\N	{"sl_set": 142, "sl_failed": 4, "positions_failed": 27, "positions_opened": 140}	2025-09-17 06:57:24.96014+00
2247	main_trader	HEALTHY	t	t	t	\N	140	0	0	\N	{"sl_set": 142, "sl_failed": 4, "positions_failed": 27, "positions_opened": 140}	2025-09-17 06:58:26.855939+00
2248	main_trader	HEALTHY	t	t	t	\N	140	0	0	\N	{"sl_set": 142, "sl_failed": 4, "positions_failed": 27, "positions_opened": 140}	2025-09-17 06:59:28.934111+00
2249	main_trader	HEALTHY	t	t	t	\N	140	0	0	\N	{"sl_set": 142, "sl_failed": 4, "positions_failed": 27, "positions_opened": 140}	2025-09-17 07:00:30.843303+00
2250	main_trader	HEALTHY	t	t	t	\N	140	0	0	\N	{"sl_set": 142, "sl_failed": 4, "positions_failed": 27, "positions_opened": 140}	2025-09-17 07:01:32.162757+00
2251	main_trader	HEALTHY	t	t	t	\N	140	0	0	\N	{"sl_set": 142, "sl_failed": 4, "positions_failed": 27, "positions_opened": 140}	2025-09-17 07:02:33.966049+00
2252	main_trader	HEALTHY	t	t	t	\N	140	0	0	\N	{"sl_set": 142, "sl_failed": 4, "positions_failed": 27, "positions_opened": 140}	2025-09-17 07:03:35.163407+00
2253	main_trader	HEALTHY	t	t	t	\N	140	0	0	\N	{"sl_set": 142, "sl_failed": 4, "positions_failed": 27, "positions_opened": 140}	2025-09-17 07:04:37.056054+00
2254	main_trader	HEALTHY	t	t	t	\N	140	0	0	\N	{"sl_set": 142, "sl_failed": 4, "positions_failed": 27, "positions_opened": 140}	2025-09-17 07:05:38.480843+00
2255	main_trader	HEALTHY	t	t	t	\N	140	0	0	\N	{"sl_set": 142, "sl_failed": 4, "positions_failed": 28, "positions_opened": 140}	2025-09-17 07:06:40.348701+00
2256	main_trader	HEALTHY	t	t	t	\N	140	0	0	\N	{"sl_set": 142, "sl_failed": 4, "positions_failed": 28, "positions_opened": 140}	2025-09-17 07:07:42.159799+00
2257	main_trader	HEALTHY	t	t	t	\N	140	0	0	\N	{"sl_set": 142, "sl_failed": 4, "positions_failed": 28, "positions_opened": 140}	2025-09-17 07:08:44.08746+00
2258	main_trader	HEALTHY	t	t	t	\N	140	0	0	\N	{"sl_set": 142, "sl_failed": 4, "positions_failed": 28, "positions_opened": 140}	2025-09-17 07:09:45.980627+00
2259	main_trader	HEALTHY	t	t	t	\N	140	0	0	\N	{"sl_set": 142, "sl_failed": 4, "positions_failed": 28, "positions_opened": 140}	2025-09-17 07:10:48.102081+00
2260	main_trader	HEALTHY	t	t	t	\N	140	0	0	\N	{"sl_set": 142, "sl_failed": 4, "positions_failed": 28, "positions_opened": 140}	2025-09-17 07:11:50.085738+00
2261	main_trader	HEALTHY	t	t	t	\N	140	0	0	\N	{"sl_set": 142, "sl_failed": 4, "positions_failed": 28, "positions_opened": 140}	2025-09-17 07:12:51.979674+00
2262	main_trader	HEALTHY	t	t	t	\N	140	0	0	\N	{"sl_set": 142, "sl_failed": 4, "positions_failed": 28, "positions_opened": 140}	2025-09-17 07:13:53.876645+00
2263	main_trader	HEALTHY	t	t	t	\N	140	0	0	\N	{"sl_set": 142, "sl_failed": 4, "positions_failed": 28, "positions_opened": 140}	2025-09-17 07:14:55.677039+00
2264	main_trader	HEALTHY	t	t	t	\N	140	0	0	\N	{"sl_set": 142, "sl_failed": 4, "positions_failed": 28, "positions_opened": 140}	2025-09-17 07:15:57.819646+00
2265	main_trader	HEALTHY	t	t	t	\N	140	0	0	\N	{"sl_set": 142, "sl_failed": 4, "positions_failed": 28, "positions_opened": 140}	2025-09-17 07:16:59.785695+00
2266	main_trader	HEALTHY	t	t	t	\N	140	0	0	\N	{"sl_set": 142, "sl_failed": 4, "positions_failed": 28, "positions_opened": 140}	2025-09-17 07:18:01.893383+00
2267	main_trader	HEALTHY	t	t	t	\N	140	0	0	\N	{"sl_set": 142, "sl_failed": 4, "positions_failed": 28, "positions_opened": 140}	2025-09-17 07:19:03.813079+00
2268	main_trader	HEALTHY	t	t	t	\N	140	0	0	\N	{"sl_set": 142, "sl_failed": 4, "positions_failed": 28, "positions_opened": 140}	2025-09-17 07:20:05.147584+00
2269	main_trader	HEALTHY	t	t	t	\N	140	0	0	\N	{"sl_set": 142, "sl_failed": 4, "positions_failed": 28, "positions_opened": 140}	2025-09-17 07:21:06.568216+00
2270	main_trader	HEALTHY	t	t	t	\N	143	0	0	\N	{"sl_set": 146, "sl_failed": 4, "positions_failed": 29, "positions_opened": 144}	2025-09-17 07:22:08.457441+00
2271	main_trader	HEALTHY	t	t	t	\N	144	0	0	\N	{"sl_set": 146, "sl_failed": 4, "positions_failed": 29, "positions_opened": 144}	2025-09-17 07:23:10.366965+00
2272	main_trader	HEALTHY	t	t	t	\N	144	0	0	\N	{"sl_set": 146, "sl_failed": 4, "positions_failed": 29, "positions_opened": 144}	2025-09-17 07:24:12.167593+00
2273	main_trader	HEALTHY	t	t	t	\N	144	0	0	\N	{"sl_set": 146, "sl_failed": 4, "positions_failed": 29, "positions_opened": 144}	2025-09-17 07:25:13.968156+00
2274	main_trader	HEALTHY	t	t	t	\N	144	0	0	\N	{"sl_set": 146, "sl_failed": 4, "positions_failed": 29, "positions_opened": 144}	2025-09-17 07:26:15.923611+00
2275	main_trader	HEALTHY	t	t	t	\N	144	0	0	\N	{"sl_set": 146, "sl_failed": 4, "positions_failed": 29, "positions_opened": 144}	2025-09-17 07:27:17.005312+00
2276	main_trader	HEALTHY	t	t	t	\N	144	0	0	\N	{"sl_set": 146, "sl_failed": 4, "positions_failed": 29, "positions_opened": 144}	2025-09-17 07:28:18.169648+00
2277	main_trader	HEALTHY	t	t	t	\N	144	0	0	\N	{"sl_set": 146, "sl_failed": 4, "positions_failed": 29, "positions_opened": 144}	2025-09-17 07:29:19.230961+00
2278	main_trader	HEALTHY	t	t	t	\N	144	0	0	\N	{"sl_set": 146, "sl_failed": 4, "positions_failed": 29, "positions_opened": 144}	2025-09-17 07:30:20.379589+00
2279	main_trader	HEALTHY	t	t	t	\N	144	0	0	\N	{"sl_set": 146, "sl_failed": 4, "positions_failed": 29, "positions_opened": 144}	2025-09-17 07:31:21.774282+00
2280	main_trader	HEALTHY	t	t	t	\N	144	0	0	\N	{"sl_set": 146, "sl_failed": 4, "positions_failed": 29, "positions_opened": 144}	2025-09-17 07:32:23.000024+00
2281	main_trader	HEALTHY	t	t	t	\N	144	0	0	\N	{"sl_set": 146, "sl_failed": 4, "positions_failed": 29, "positions_opened": 144}	2025-09-17 07:33:24.42158+00
2282	main_trader	HEALTHY	t	t	t	\N	144	0	0	\N	{"sl_set": 146, "sl_failed": 4, "positions_failed": 29, "positions_opened": 144}	2025-09-17 07:34:25.615776+00
2283	main_trader	HEALTHY	t	t	t	\N	144	0	0	\N	{"sl_set": 146, "sl_failed": 4, "positions_failed": 29, "positions_opened": 144}	2025-09-17 07:35:26.914701+00
2284	main_trader	HEALTHY	t	t	t	\N	144	0	0	\N	{"sl_set": 146, "sl_failed": 4, "positions_failed": 29, "positions_opened": 145}	2025-09-17 07:36:28.094228+00
2285	main_trader	HEALTHY	t	t	t	\N	147	0	0	\N	{"sl_set": 148, "sl_failed": 5, "positions_failed": 29, "positions_opened": 147}	2025-09-17 07:37:29.406913+00
2286	main_trader	HEALTHY	t	t	t	\N	147	0	0	\N	{"sl_set": 148, "sl_failed": 5, "positions_failed": 29, "positions_opened": 147}	2025-09-17 07:38:30.614212+00
2287	main_trader	HEALTHY	t	t	t	\N	147	0	0	\N	{"sl_set": 148, "sl_failed": 5, "positions_failed": 29, "positions_opened": 147}	2025-09-17 07:39:31.698086+00
2288	main_trader	HEALTHY	t	t	t	\N	147	0	0	\N	{"sl_set": 148, "sl_failed": 5, "positions_failed": 29, "positions_opened": 147}	2025-09-17 07:40:32.882551+00
2289	main_trader	HEALTHY	t	t	t	\N	147	0	0	\N	{"sl_set": 148, "sl_failed": 5, "positions_failed": 29, "positions_opened": 147}	2025-09-17 07:41:34.438317+00
2290	main_trader	HEALTHY	t	t	t	\N	147	0	0	\N	{"sl_set": 148, "sl_failed": 5, "positions_failed": 29, "positions_opened": 147}	2025-09-17 07:42:35.691019+00
2291	main_trader	HEALTHY	t	t	t	\N	147	0	0	\N	{"sl_set": 148, "sl_failed": 5, "positions_failed": 29, "positions_opened": 147}	2025-09-17 07:43:36.754772+00
2292	main_trader	HEALTHY	t	t	t	\N	147	0	0	\N	{"sl_set": 148, "sl_failed": 5, "positions_failed": 29, "positions_opened": 147}	2025-09-17 07:44:37.879141+00
2293	main_trader	HEALTHY	t	t	t	\N	147	0	0	\N	{"sl_set": 148, "sl_failed": 5, "positions_failed": 29, "positions_opened": 147}	2025-09-17 07:45:39.048723+00
2294	main_trader	HEALTHY	t	t	t	\N	147	0	0	\N	{"sl_set": 148, "sl_failed": 5, "positions_failed": 29, "positions_opened": 147}	2025-09-17 07:46:40.483884+00
2295	main_trader	HEALTHY	t	t	t	\N	147	0	0	\N	{"sl_set": 148, "sl_failed": 5, "positions_failed": 29, "positions_opened": 147}	2025-09-17 07:47:41.785759+00
2296	main_trader	HEALTHY	t	t	t	\N	147	0	0	\N	{"sl_set": 148, "sl_failed": 5, "positions_failed": 29, "positions_opened": 147}	2025-09-17 07:48:42.875425+00
2297	main_trader	HEALTHY	t	t	t	\N	147	0	0	\N	{"sl_set": 148, "sl_failed": 5, "positions_failed": 29, "positions_opened": 147}	2025-09-17 07:49:43.937992+00
2298	main_trader	HEALTHY	t	t	t	\N	147	0	0	\N	{"sl_set": 148, "sl_failed": 5, "positions_failed": 29, "positions_opened": 147}	2025-09-17 07:50:46.23456+00
2299	main_trader	HEALTHY	t	t	t	\N	149	0	0	\N	{"sl_set": 150, "sl_failed": 5, "positions_failed": 29, "positions_opened": 149}	2025-09-17 07:51:47.378179+00
2300	main_trader	HEALTHY	t	t	t	\N	149	0	0	\N	{"sl_set": 150, "sl_failed": 5, "positions_failed": 29, "positions_opened": 149}	2025-09-17 07:52:48.644301+00
2301	main_trader	HEALTHY	t	t	t	\N	149	0	0	\N	{"sl_set": 150, "sl_failed": 5, "positions_failed": 29, "positions_opened": 149}	2025-09-17 07:53:49.921985+00
2302	main_trader	HEALTHY	t	t	t	\N	149	0	0	\N	{"sl_set": 150, "sl_failed": 5, "positions_failed": 29, "positions_opened": 149}	2025-09-17 07:54:51.08449+00
2303	main_trader	HEALTHY	t	t	t	\N	149	0	0	\N	{"sl_set": 150, "sl_failed": 5, "positions_failed": 29, "positions_opened": 149}	2025-09-17 07:55:52.177328+00
2304	main_trader	HEALTHY	t	t	t	\N	149	0	0	\N	{"sl_set": 150, "sl_failed": 5, "positions_failed": 29, "positions_opened": 149}	2025-09-17 07:56:53.945397+00
2305	main_trader	HEALTHY	t	t	t	\N	149	0	0	\N	{"sl_set": 150, "sl_failed": 5, "positions_failed": 29, "positions_opened": 149}	2025-09-17 07:57:55.129861+00
2306	main_trader	HEALTHY	t	t	t	\N	149	0	0	\N	{"sl_set": 150, "sl_failed": 5, "positions_failed": 29, "positions_opened": 149}	2025-09-17 07:58:56.227426+00
2307	main_trader	HEALTHY	t	t	t	\N	149	0	0	\N	{"sl_set": 150, "sl_failed": 5, "positions_failed": 29, "positions_opened": 149}	2025-09-17 07:59:57.299915+00
2308	main_trader	HEALTHY	t	t	t	\N	149	0	0	\N	{"sl_set": 150, "sl_failed": 5, "positions_failed": 29, "positions_opened": 149}	2025-09-17 08:00:58.466553+00
2309	main_trader	HEALTHY	t	t	t	\N	149	0	0	\N	{"sl_set": 150, "sl_failed": 5, "positions_failed": 29, "positions_opened": 149}	2025-09-17 08:01:59.77212+00
2310	main_trader	HEALTHY	t	t	t	\N	149	0	0	\N	{"sl_set": 150, "sl_failed": 5, "positions_failed": 29, "positions_opened": 149}	2025-09-17 08:03:01.014189+00
2311	main_trader	HEALTHY	t	t	t	\N	149	0	0	\N	{"sl_set": 150, "sl_failed": 5, "positions_failed": 29, "positions_opened": 149}	2025-09-17 08:04:02.082712+00
2312	main_trader	HEALTHY	t	t	t	\N	149	0	0	\N	{"sl_set": 150, "sl_failed": 5, "positions_failed": 29, "positions_opened": 149}	2025-09-17 08:05:03.259699+00
2313	main_trader	HEALTHY	t	t	t	\N	149	0	0	\N	{"sl_set": 150, "sl_failed": 5, "positions_failed": 29, "positions_opened": 149}	2025-09-17 08:06:04.331753+00
2314	main_trader	HEALTHY	t	t	t	\N	151	0	0	\N	{"sl_set": 152, "sl_failed": 5, "positions_failed": 30, "positions_opened": 151}	2025-09-17 08:07:05.733833+00
2315	main_trader	HEALTHY	t	t	t	\N	151	0	0	\N	{"sl_set": 152, "sl_failed": 5, "positions_failed": 30, "positions_opened": 151}	2025-09-17 08:08:06.99728+00
2316	main_trader	HEALTHY	t	t	t	\N	151	0	0	\N	{"sl_set": 152, "sl_failed": 5, "positions_failed": 30, "positions_opened": 151}	2025-09-17 08:09:08.091939+00
2317	main_trader	HEALTHY	t	t	t	\N	151	0	0	\N	{"sl_set": 152, "sl_failed": 5, "positions_failed": 30, "positions_opened": 151}	2025-09-17 08:10:09.264299+00
2318	main_trader	HEALTHY	t	t	t	\N	151	0	0	\N	{"sl_set": 152, "sl_failed": 5, "positions_failed": 30, "positions_opened": 151}	2025-09-17 08:11:10.330821+00
2319	main_trader	HEALTHY	t	t	t	\N	151	0	0	\N	{"sl_set": 152, "sl_failed": 5, "positions_failed": 30, "positions_opened": 151}	2025-09-17 08:12:12.190573+00
2320	main_trader	HEALTHY	t	t	t	\N	151	0	0	\N	{"sl_set": 152, "sl_failed": 5, "positions_failed": 30, "positions_opened": 151}	2025-09-17 08:13:13.336524+00
2321	main_trader	HEALTHY	t	t	t	\N	151	0	0	\N	{"sl_set": 152, "sl_failed": 5, "positions_failed": 30, "positions_opened": 151}	2025-09-17 08:14:14.508201+00
2322	main_trader	HEALTHY	t	t	t	\N	151	0	0	\N	{"sl_set": 152, "sl_failed": 5, "positions_failed": 30, "positions_opened": 151}	2025-09-17 08:15:15.573029+00
2323	main_trader	HEALTHY	t	t	t	\N	151	0	0	\N	{"sl_set": 152, "sl_failed": 5, "positions_failed": 30, "positions_opened": 151}	2025-09-17 08:16:16.630927+00
2324	main_trader	HEALTHY	t	t	t	\N	151	0	0	\N	{"sl_set": 152, "sl_failed": 5, "positions_failed": 30, "positions_opened": 151}	2025-09-17 08:17:18.029675+00
2325	main_trader	HEALTHY	t	t	t	\N	151	0	0	\N	{"sl_set": 152, "sl_failed": 5, "positions_failed": 30, "positions_opened": 151}	2025-09-17 08:18:19.304116+00
2326	main_trader	HEALTHY	t	t	t	\N	151	0	0	\N	{"sl_set": 152, "sl_failed": 5, "positions_failed": 30, "positions_opened": 151}	2025-09-17 08:19:20.552471+00
2327	main_trader	HEALTHY	t	t	t	\N	151	0	0	\N	{"sl_set": 152, "sl_failed": 5, "positions_failed": 30, "positions_opened": 151}	2025-09-17 08:20:21.674032+00
2328	main_trader	HEALTHY	t	t	t	\N	151	0	0	\N	{"sl_set": 152, "sl_failed": 5, "positions_failed": 30, "positions_opened": 151}	2025-09-17 08:21:23.500773+00
2329	main_trader	HEALTHY	t	t	t	\N	153	0	0	\N	{"sl_set": 155, "sl_failed": 5, "positions_failed": 31, "positions_opened": 153}	2025-09-17 08:22:25.534559+00
2330	main_trader	HEALTHY	t	t	t	\N	153	0	0	\N	{"sl_set": 155, "sl_failed": 5, "positions_failed": 31, "positions_opened": 153}	2025-09-17 08:23:27.548044+00
2331	main_trader	HEALTHY	t	t	t	\N	153	0	0	\N	{"sl_set": 155, "sl_failed": 5, "positions_failed": 31, "positions_opened": 153}	2025-09-17 08:24:28.83102+00
2332	main_trader	HEALTHY	t	t	t	\N	153	0	0	\N	{"sl_set": 155, "sl_failed": 5, "positions_failed": 31, "positions_opened": 153}	2025-09-17 08:25:30.298277+00
2333	main_trader	HEALTHY	t	t	t	\N	153	0	0	\N	{"sl_set": 155, "sl_failed": 5, "positions_failed": 31, "positions_opened": 153}	2025-09-17 08:26:32.202429+00
2334	main_trader	HEALTHY	t	t	t	\N	153	0	0	\N	{"sl_set": 155, "sl_failed": 5, "positions_failed": 31, "positions_opened": 153}	2025-09-17 08:27:34.344093+00
2335	main_trader	HEALTHY	t	t	t	\N	153	0	0	\N	{"sl_set": 155, "sl_failed": 5, "positions_failed": 31, "positions_opened": 153}	2025-09-17 08:28:36.232077+00
2336	main_trader	HEALTHY	t	t	t	\N	153	0	0	\N	{"sl_set": 155, "sl_failed": 5, "positions_failed": 31, "positions_opened": 153}	2025-09-17 08:29:38.118019+00
2337	main_trader	HEALTHY	t	t	t	\N	153	0	0	\N	{"sl_set": 155, "sl_failed": 5, "positions_failed": 31, "positions_opened": 153}	2025-09-17 08:30:40.019164+00
2338	main_trader	HEALTHY	t	t	t	\N	153	0	0	\N	{"sl_set": 155, "sl_failed": 5, "positions_failed": 31, "positions_opened": 153}	2025-09-17 08:31:41.827855+00
2339	main_trader	HEALTHY	t	t	t	\N	153	0	0	\N	{"sl_set": 155, "sl_failed": 5, "positions_failed": 31, "positions_opened": 153}	2025-09-17 08:32:43.987998+00
2340	main_trader	HEALTHY	t	t	t	\N	153	0	0	\N	{"sl_set": 155, "sl_failed": 5, "positions_failed": 31, "positions_opened": 153}	2025-09-17 08:33:45.855997+00
2341	main_trader	HEALTHY	t	t	t	\N	153	0	0	\N	{"sl_set": 155, "sl_failed": 5, "positions_failed": 31, "positions_opened": 153}	2025-09-17 08:34:47.75437+00
2342	main_trader	HEALTHY	t	t	t	\N	153	0	0	\N	{"sl_set": 155, "sl_failed": 5, "positions_failed": 31, "positions_opened": 153}	2025-09-17 08:35:48.853082+00
2343	main_trader	HEALTHY	t	t	t	\N	154	0	0	\N	{"sl_set": 157, "sl_failed": 5, "positions_failed": 31, "positions_opened": 154}	2025-09-17 08:36:50.744594+00
2344	main_trader	HEALTHY	t	t	t	\N	154	0	0	\N	{"sl_set": 157, "sl_failed": 5, "positions_failed": 31, "positions_opened": 154}	2025-09-17 08:37:52.892979+00
2345	main_trader	HEALTHY	t	t	t	\N	154	0	0	\N	{"sl_set": 157, "sl_failed": 5, "positions_failed": 31, "positions_opened": 154}	2025-09-17 08:38:54.895356+00
2346	main_trader	HEALTHY	t	t	t	\N	154	0	0	\N	{"sl_set": 157, "sl_failed": 5, "positions_failed": 31, "positions_opened": 154}	2025-09-17 08:39:56.781584+00
2347	main_trader	HEALTHY	t	t	t	\N	154	0	0	\N	{"sl_set": 157, "sl_failed": 5, "positions_failed": 31, "positions_opened": 154}	2025-09-17 08:40:57.887144+00
2348	main_trader	HEALTHY	t	t	t	\N	154	0	0	\N	{"sl_set": 157, "sl_failed": 5, "positions_failed": 31, "positions_opened": 154}	2025-09-17 08:41:59.813769+00
2349	main_trader	HEALTHY	t	t	t	\N	154	0	0	\N	{"sl_set": 157, "sl_failed": 5, "positions_failed": 31, "positions_opened": 154}	2025-09-17 08:43:02.304785+00
2350	main_trader	HEALTHY	t	t	t	\N	154	0	0	\N	{"sl_set": 157, "sl_failed": 5, "positions_failed": 31, "positions_opened": 154}	2025-09-17 08:44:04.314234+00
2351	main_trader	HEALTHY	t	t	t	\N	154	0	0	\N	{"sl_set": 157, "sl_failed": 5, "positions_failed": 31, "positions_opened": 154}	2025-09-17 08:45:05.519322+00
2352	main_trader	HEALTHY	t	t	t	\N	154	0	0	\N	{"sl_set": 157, "sl_failed": 5, "positions_failed": 31, "positions_opened": 154}	2025-09-17 08:46:07.414765+00
2353	main_trader	HEALTHY	t	t	t	\N	154	0	0	\N	{"sl_set": 157, "sl_failed": 5, "positions_failed": 31, "positions_opened": 154}	2025-09-17 08:47:09.315886+00
2354	main_trader	HEALTHY	t	t	t	\N	154	0	0	\N	{"sl_set": 157, "sl_failed": 5, "positions_failed": 31, "positions_opened": 154}	2025-09-17 08:48:11.446876+00
2355	main_trader	RUNNING	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-17 08:48:26.245785+00
2356	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-17 08:49:28.580218+00
2357	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-17 08:50:29.800927+00
2358	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-17 08:51:31.95785+00
2359	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-17 08:52:34.217908+00
2360	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-17 08:53:36.466203+00
2361	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-17 08:54:38.788927+00
2362	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-17 08:55:41.058447+00
2363	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-17 08:56:43.308071+00
2364	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-17 08:57:45.536964+00
2365	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-17 08:58:47.692475+00
2366	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-17 08:59:49.938352+00
2367	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-17 09:00:52.560815+00
2368	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-17 09:01:54.839818+00
2369	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-17 09:02:56.363551+00
2370	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-17 09:03:58.107191+00
2371	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-17 09:04:59.709962+00
2372	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-17 09:06:00.929475+00
2373	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-17 09:07:02.463673+00
2374	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-17 09:08:03.912061+00
2375	main_trader	RUNNING	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-17 09:08:56.895749+00
2376	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-17 09:09:58.16241+00
2377	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-17 09:10:59.399193+00
2378	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-17 09:12:00.470709+00
2379	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-17 09:13:01.628932+00
2380	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-17 09:14:02.828568+00
2381	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-17 09:15:04.212548+00
2382	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-17 09:16:05.458396+00
2383	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-17 09:17:06.521818+00
2384	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-17 09:18:07.706265+00
2385	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-17 09:19:08.813968+00
2386	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-17 09:20:11.661035+00
2387	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-17 09:21:12.807086+00
2388	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 1, "positions_opened": 0}	2025-09-17 09:22:14.637226+00
2389	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 1, "positions_opened": 0}	2025-09-17 09:23:15.82391+00
2390	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 1, "positions_opened": 0}	2025-09-17 09:24:16.987441+00
2391	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 1, "positions_opened": 0}	2025-09-17 09:25:18.058558+00
2392	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 1, "positions_opened": 0}	2025-09-17 09:26:19.223351+00
2393	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 1, "positions_opened": 0}	2025-09-17 09:27:20.651854+00
2394	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 1, "positions_opened": 0}	2025-09-17 09:28:21.841857+00
2395	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 1, "positions_opened": 0}	2025-09-17 09:29:22.997761+00
2396	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 1, "positions_opened": 0}	2025-09-17 09:30:24.171763+00
2397	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 1, "positions_opened": 0}	2025-09-17 09:31:25.331347+00
2398	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 1, "positions_opened": 0}	2025-09-17 09:32:26.726372+00
2399	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 1, "positions_opened": 0}	2025-09-17 09:33:27.978636+00
2400	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 1, "positions_opened": 0}	2025-09-17 09:34:29.135793+00
2401	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 1, "positions_opened": 0}	2025-09-17 09:35:30.252733+00
2402	main_trader	DEGRADED	t	t	t	\N	1	0	0	\N	{"sl_set": 1, "sl_failed": 0, "positions_failed": 1, "positions_opened": 1}	2025-09-17 09:36:31.146083+00
2403	main_trader	HEALTHY	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 1, "positions_opened": 3}	2025-09-17 09:37:32.544298+00
2404	main_trader	HEALTHY	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 1, "positions_opened": 3}	2025-09-17 09:38:33.853037+00
2405	main_trader	HEALTHY	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 1, "positions_opened": 3}	2025-09-17 09:39:35.048885+00
2406	main_trader	HEALTHY	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 1, "positions_opened": 3}	2025-09-17 09:40:36.508862+00
2407	main_trader	HEALTHY	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 1, "positions_opened": 3}	2025-09-17 09:41:37.674997+00
2408	main_trader	HEALTHY	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 1, "positions_opened": 3}	2025-09-17 09:42:39.542956+00
2409	main_trader	HEALTHY	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 1, "positions_opened": 3}	2025-09-17 09:43:40.828768+00
2410	main_trader	HEALTHY	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 1, "positions_opened": 3}	2025-09-17 09:44:41.99486+00
2411	main_trader	HEALTHY	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 1, "positions_opened": 3}	2025-09-17 09:45:43.097142+00
2412	main_trader	HEALTHY	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 1, "positions_opened": 3}	2025-09-17 09:46:44.313291+00
2413	main_trader	HEALTHY	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 1, "positions_opened": 3}	2025-09-17 09:47:45.618774+00
2414	main_trader	HEALTHY	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 1, "positions_opened": 3}	2025-09-17 09:48:46.883636+00
2415	main_trader	HEALTHY	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 1, "positions_opened": 3}	2025-09-17 09:49:47.958322+00
2416	main_trader	RUNNING	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-17 09:50:34.527119+00
2417	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-17 09:51:35.511031+00
2418	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-17 09:52:36.707692+00
2419	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-17 09:53:37.877754+00
2420	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-17 09:54:39.043122+00
2421	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-17 09:55:40.506931+00
2422	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-17 09:56:41.737677+00
2423	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-17 09:57:42.904173+00
2424	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-17 09:58:43.96958+00
2425	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-17 09:59:45.132777+00
2426	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-17 10:00:47.010835+00
2427	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-17 10:01:48.180959+00
2428	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-17 10:02:49.256224+00
2429	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-17 10:03:50.418071+00
2430	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-17 10:04:51.481644+00
2431	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-17 10:05:52.773352+00
2432	main_trader	DEGRADED	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 2, "positions_opened": 2}	2025-09-17 10:06:54.013064+00
2433	main_trader	DEGRADED	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 2, "positions_opened": 2}	2025-09-17 10:07:55.396156+00
2434	main_trader	DEGRADED	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 2, "positions_opened": 2}	2025-09-17 10:08:56.56146+00
2435	main_trader	DEGRADED	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 2, "positions_opened": 2}	2025-09-17 10:09:57.609125+00
2436	main_trader	DEGRADED	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 2, "positions_opened": 2}	2025-09-17 10:10:58.910576+00
2437	main_trader	DEGRADED	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 2, "positions_opened": 2}	2025-09-17 10:12:00.15825+00
2438	main_trader	DEGRADED	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 2, "positions_opened": 2}	2025-09-17 10:13:01.242821+00
2439	main_trader	DEGRADED	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 2, "positions_opened": 2}	2025-09-17 10:14:02.458393+00
2440	main_trader	DEGRADED	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 2, "positions_opened": 2}	2025-09-17 10:15:03.631937+00
2441	main_trader	DEGRADED	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 2, "positions_opened": 2}	2025-09-17 10:16:05.025787+00
2442	main_trader	DEGRADED	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 2, "positions_opened": 2}	2025-09-17 10:17:06.175564+00
2443	main_trader	DEGRADED	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 2, "positions_opened": 2}	2025-09-17 10:18:07.249325+00
2444	main_trader	DEGRADED	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 2, "positions_opened": 2}	2025-09-17 10:19:08.411063+00
2445	main_trader	DEGRADED	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 2, "positions_opened": 2}	2025-09-17 10:20:09.47982+00
2446	main_trader	DEGRADED	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 2, "positions_opened": 2}	2025-09-17 10:21:10.879249+00
2447	main_trader	HEALTHY	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 2, "positions_opened": 3}	2025-09-17 10:22:12.032174+00
2448	main_trader	HEALTHY	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 2, "positions_opened": 3}	2025-09-17 10:23:13.121552+00
2449	main_trader	HEALTHY	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 2, "positions_opened": 3}	2025-09-17 10:24:14.30247+00
2450	main_trader	HEALTHY	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 2, "positions_opened": 3}	2025-09-17 10:25:15.471099+00
2451	main_trader	HEALTHY	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 2, "positions_opened": 3}	2025-09-17 10:26:16.771335+00
2452	main_trader	HEALTHY	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 2, "positions_opened": 3}	2025-09-17 10:27:18.014065+00
2453	main_trader	HEALTHY	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 2, "positions_opened": 3}	2025-09-17 10:28:19.182584+00
2454	main_trader	HEALTHY	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 2, "positions_opened": 3}	2025-09-17 10:29:20.246868+00
2455	main_trader	HEALTHY	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 2, "positions_opened": 3}	2025-09-17 10:30:21.406494+00
2456	main_trader	HEALTHY	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 2, "positions_opened": 3}	2025-09-17 10:31:22.826409+00
2457	main_trader	HEALTHY	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 2, "positions_opened": 3}	2025-09-17 10:32:24.061749+00
2458	main_trader	HEALTHY	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 2, "positions_opened": 3}	2025-09-17 10:33:25.134671+00
2459	main_trader	HEALTHY	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 2, "positions_opened": 3}	2025-09-17 10:34:26.296228+00
2460	main_trader	HEALTHY	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 2, "positions_opened": 3}	2025-09-17 10:35:27.459766+00
2461	main_trader	HEALTHY	t	t	t	\N	4	0	0	\N	{"sl_set": 4, "sl_failed": 0, "positions_failed": 2, "positions_opened": 4}	2025-09-17 10:36:28.441192+00
2462	main_trader	HEALTHY	t	t	t	\N	5	0	0	\N	{"sl_set": 6, "sl_failed": 0, "positions_failed": 4, "positions_opened": 6}	2025-09-17 10:37:29.418709+00
2463	main_trader	HEALTHY	t	t	t	\N	6	0	0	\N	{"sl_set": 6, "sl_failed": 0, "positions_failed": 4, "positions_opened": 6}	2025-09-17 10:38:30.59674+00
2464	main_trader	HEALTHY	t	t	t	\N	6	0	0	\N	{"sl_set": 6, "sl_failed": 0, "positions_failed": 4, "positions_opened": 6}	2025-09-17 10:39:31.659302+00
2465	main_trader	HEALTHY	t	t	t	\N	6	0	0	\N	{"sl_set": 6, "sl_failed": 0, "positions_failed": 4, "positions_opened": 6}	2025-09-17 10:40:32.827461+00
2466	main_trader	HEALTHY	t	t	t	\N	6	0	0	\N	{"sl_set": 6, "sl_failed": 0, "positions_failed": 4, "positions_opened": 6}	2025-09-17 10:41:34.693599+00
2467	main_trader	HEALTHY	t	t	t	\N	6	0	0	\N	{"sl_set": 6, "sl_failed": 0, "positions_failed": 4, "positions_opened": 6}	2025-09-17 10:42:35.850811+00
2468	main_trader	HEALTHY	t	t	t	\N	6	0	0	\N	{"sl_set": 6, "sl_failed": 0, "positions_failed": 4, "positions_opened": 6}	2025-09-17 10:43:37.025618+00
2469	main_trader	HEALTHY	t	t	t	\N	6	0	0	\N	{"sl_set": 6, "sl_failed": 0, "positions_failed": 4, "positions_opened": 6}	2025-09-17 10:44:38.202674+00
2470	main_trader	HEALTHY	t	t	t	\N	6	0	0	\N	{"sl_set": 6, "sl_failed": 0, "positions_failed": 4, "positions_opened": 6}	2025-09-17 10:45:39.393112+00
2471	main_trader	HEALTHY	t	t	t	\N	6	0	0	\N	{"sl_set": 6, "sl_failed": 0, "positions_failed": 4, "positions_opened": 6}	2025-09-17 10:46:41.529091+00
2472	main_trader	HEALTHY	t	t	t	\N	6	0	0	\N	{"sl_set": 6, "sl_failed": 0, "positions_failed": 4, "positions_opened": 6}	2025-09-17 10:47:42.780013+00
2473	main_trader	HEALTHY	t	t	t	\N	6	0	0	\N	{"sl_set": 6, "sl_failed": 0, "positions_failed": 4, "positions_opened": 6}	2025-09-17 10:48:43.931923+00
2474	main_trader	HEALTHY	t	t	t	\N	6	0	0	\N	{"sl_set": 6, "sl_failed": 0, "positions_failed": 4, "positions_opened": 6}	2025-09-17 10:49:45.127916+00
2475	main_trader	HEALTHY	t	t	t	\N	6	0	0	\N	{"sl_set": 6, "sl_failed": 0, "positions_failed": 4, "positions_opened": 6}	2025-09-17 10:50:46.20022+00
2476	main_trader	DEGRADED	t	t	t	\N	6	0	0	\N	{"sl_set": 6, "sl_failed": 0, "positions_failed": 7, "positions_opened": 6}	2025-09-17 10:51:47.591551+00
2477	main_trader	DEGRADED	t	t	t	\N	6	0	0	\N	{"sl_set": 6, "sl_failed": 0, "positions_failed": 7, "positions_opened": 6}	2025-09-17 10:52:48.742112+00
2478	main_trader	DEGRADED	t	t	t	\N	6	0	0	\N	{"sl_set": 6, "sl_failed": 0, "positions_failed": 7, "positions_opened": 6}	2025-09-17 10:53:49.917135+00
2479	main_trader	DEGRADED	t	t	t	\N	6	0	0	\N	{"sl_set": 6, "sl_failed": 0, "positions_failed": 7, "positions_opened": 6}	2025-09-17 10:54:51.10833+00
2480	main_trader	DEGRADED	t	t	t	\N	6	0	0	\N	{"sl_set": 6, "sl_failed": 0, "positions_failed": 7, "positions_opened": 6}	2025-09-17 10:55:52.182651+00
2481	main_trader	DEGRADED	t	t	t	\N	6	0	0	\N	{"sl_set": 6, "sl_failed": 0, "positions_failed": 7, "positions_opened": 6}	2025-09-17 10:56:53.711354+00
2482	main_trader	DEGRADED	t	t	t	\N	6	0	0	\N	{"sl_set": 6, "sl_failed": 0, "positions_failed": 7, "positions_opened": 6}	2025-09-17 10:57:54.957857+00
2483	main_trader	DEGRADED	t	t	t	\N	6	0	0	\N	{"sl_set": 6, "sl_failed": 0, "positions_failed": 7, "positions_opened": 6}	2025-09-17 10:58:56.029658+00
2484	main_trader	DEGRADED	t	t	t	\N	6	0	0	\N	{"sl_set": 6, "sl_failed": 0, "positions_failed": 7, "positions_opened": 6}	2025-09-17 10:59:57.105131+00
2485	main_trader	DEGRADED	t	t	t	\N	6	0	0	\N	{"sl_set": 6, "sl_failed": 0, "positions_failed": 7, "positions_opened": 6}	2025-09-17 11:00:58.172174+00
2486	main_trader	DEGRADED	t	t	t	\N	6	0	0	\N	{"sl_set": 6, "sl_failed": 0, "positions_failed": 7, "positions_opened": 6}	2025-09-17 11:01:59.562492+00
2487	main_trader	DEGRADED	t	t	t	\N	6	0	0	\N	{"sl_set": 6, "sl_failed": 0, "positions_failed": 7, "positions_opened": 6}	2025-09-17 11:03:00.805407+00
2488	main_trader	RUNNING	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-17 11:03:39.436897+00
2489	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-17 11:04:40.717567+00
2490	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-17 11:05:41.78379+00
2491	main_trader	DEGRADED	t	t	t	\N	1	0	0	\N	{"sl_set": 1, "sl_failed": 0, "positions_failed": 1, "positions_opened": 1}	2025-09-17 11:06:42.685836+00
2492	main_trader	DEGRADED	t	t	t	\N	1	0	0	\N	{"sl_set": 1, "sl_failed": 0, "positions_failed": 1, "positions_opened": 1}	2025-09-17 11:07:43.847995+00
2493	main_trader	DEGRADED	t	t	t	\N	1	0	0	\N	{"sl_set": 1, "sl_failed": 0, "positions_failed": 1, "positions_opened": 1}	2025-09-17 11:08:45.22934+00
2494	main_trader	DEGRADED	t	t	t	\N	1	0	0	\N	{"sl_set": 1, "sl_failed": 0, "positions_failed": 1, "positions_opened": 1}	2025-09-17 11:09:46.480409+00
2495	main_trader	DEGRADED	t	t	t	\N	1	0	0	\N	{"sl_set": 1, "sl_failed": 0, "positions_failed": 1, "positions_opened": 1}	2025-09-17 11:10:47.644733+00
2496	main_trader	DEGRADED	t	t	t	\N	1	0	0	\N	{"sl_set": 1, "sl_failed": 0, "positions_failed": 1, "positions_opened": 1}	2025-09-17 11:11:48.81694+00
2497	main_trader	DEGRADED	t	t	t	\N	1	0	0	\N	{"sl_set": 1, "sl_failed": 0, "positions_failed": 1, "positions_opened": 1}	2025-09-17 11:12:49.974922+00
2498	main_trader	DEGRADED	t	t	t	\N	1	0	0	\N	{"sl_set": 1, "sl_failed": 0, "positions_failed": 1, "positions_opened": 1}	2025-09-17 11:13:51.75552+00
2499	main_trader	DEGRADED	t	t	t	\N	1	0	0	\N	{"sl_set": 1, "sl_failed": 0, "positions_failed": 1, "positions_opened": 1}	2025-09-17 11:14:52.895033+00
2500	main_trader	DEGRADED	t	t	t	\N	1	0	0	\N	{"sl_set": 1, "sl_failed": 0, "positions_failed": 1, "positions_opened": 1}	2025-09-17 11:15:54.057304+00
2501	main_trader	DEGRADED	t	t	t	\N	1	0	0	\N	{"sl_set": 1, "sl_failed": 0, "positions_failed": 1, "positions_opened": 1}	2025-09-17 11:16:55.219986+00
2502	main_trader	DEGRADED	t	t	t	\N	1	0	0	\N	{"sl_set": 1, "sl_failed": 0, "positions_failed": 1, "positions_opened": 1}	2025-09-17 11:17:56.28807+00
2503	main_trader	DEGRADED	t	t	t	\N	1	0	0	\N	{"sl_set": 1, "sl_failed": 0, "positions_failed": 1, "positions_opened": 1}	2025-09-17 11:18:57.682847+00
2504	main_trader	DEGRADED	t	t	t	\N	1	0	0	\N	{"sl_set": 1, "sl_failed": 0, "positions_failed": 1, "positions_opened": 1}	2025-09-17 11:19:58.913589+00
2505	main_trader	DEGRADED	t	t	t	\N	1	0	0	\N	{"sl_set": 1, "sl_failed": 0, "positions_failed": 1, "positions_opened": 1}	2025-09-17 11:21:00.088768+00
2506	main_trader	RUNNING	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-17 11:28:02.241297+00
2507	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-17 11:29:03.460974+00
2508	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-17 11:30:04.504823+00
2509	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-17 11:31:05.638063+00
2510	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-17 11:32:06.693791+00
2511	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-17 11:33:08.381168+00
2512	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-17 11:34:09.568315+00
2513	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-17 11:35:10.614379+00
2514	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-17 11:36:11.650128+00
2515	main_trader	HEALTHY	t	t	t	\N	4	0	0	\N	{"sl_set": 4, "sl_failed": 0, "positions_failed": 0, "positions_opened": 4}	2025-09-17 11:37:12.766349+00
2516	main_trader	HEALTHY	t	t	t	\N	4	0	0	\N	{"sl_set": 4, "sl_failed": 0, "positions_failed": 0, "positions_opened": 4}	2025-09-17 11:38:14.295193+00
2517	main_trader	HEALTHY	t	t	t	\N	4	0	0	\N	{"sl_set": 4, "sl_failed": 0, "positions_failed": 0, "positions_opened": 4}	2025-09-17 11:39:15.523039+00
2518	main_trader	HEALTHY	t	t	t	\N	4	0	0	\N	{"sl_set": 4, "sl_failed": 0, "positions_failed": 0, "positions_opened": 4}	2025-09-17 11:40:16.561932+00
2519	main_trader	HEALTHY	t	t	t	\N	4	0	0	\N	{"sl_set": 4, "sl_failed": 0, "positions_failed": 0, "positions_opened": 4}	2025-09-17 11:41:17.678167+00
2520	main_trader	HEALTHY	t	t	t	\N	4	0	0	\N	{"sl_set": 4, "sl_failed": 0, "positions_failed": 0, "positions_opened": 4}	2025-09-17 11:42:18.977958+00
2521	main_trader	HEALTHY	t	t	t	\N	4	0	0	\N	{"sl_set": 4, "sl_failed": 0, "positions_failed": 0, "positions_opened": 4}	2025-09-17 11:43:20.779462+00
2522	main_trader	HEALTHY	t	t	t	\N	4	0	0	\N	{"sl_set": 4, "sl_failed": 0, "positions_failed": 0, "positions_opened": 4}	2025-09-17 11:44:22.027601+00
2523	main_trader	HEALTHY	t	t	t	\N	4	0	0	\N	{"sl_set": 4, "sl_failed": 0, "positions_failed": 0, "positions_opened": 4}	2025-09-17 11:45:23.092822+00
2524	main_trader	HEALTHY	t	t	t	\N	4	0	0	\N	{"sl_set": 4, "sl_failed": 0, "positions_failed": 0, "positions_opened": 4}	2025-09-17 11:46:24.209457+00
2525	main_trader	HEALTHY	t	t	t	\N	4	0	0	\N	{"sl_set": 4, "sl_failed": 0, "positions_failed": 0, "positions_opened": 4}	2025-09-17 11:47:25.37014+00
2526	main_trader	HEALTHY	t	t	t	\N	4	0	0	\N	{"sl_set": 4, "sl_failed": 0, "positions_failed": 0, "positions_opened": 4}	2025-09-17 11:48:26.759274+00
2527	main_trader	HEALTHY	t	t	t	\N	4	0	0	\N	{"sl_set": 4, "sl_failed": 0, "positions_failed": 0, "positions_opened": 4}	2025-09-17 11:49:27.99898+00
2528	main_trader	HEALTHY	t	t	t	\N	4	0	0	\N	{"sl_set": 4, "sl_failed": 0, "positions_failed": 0, "positions_opened": 4}	2025-09-17 11:50:30.322641+00
2529	main_trader	HEALTHY	t	t	t	\N	4	0	0	\N	{"sl_set": 5, "sl_failed": 0, "positions_failed": 0, "positions_opened": 5}	2025-09-17 11:51:31.975624+00
2530	main_trader	HEALTHY	t	t	t	\N	6	0	0	\N	{"sl_set": 7, "sl_failed": 0, "positions_failed": 1, "positions_opened": 7}	2025-09-17 11:52:33.086666+00
2531	main_trader	HEALTHY	t	t	t	\N	8	0	0	\N	{"sl_set": 8, "sl_failed": 0, "positions_failed": 1, "positions_opened": 8}	2025-09-17 11:53:34.228437+00
2532	main_trader	HEALTHY	t	t	t	\N	8	0	0	\N	{"sl_set": 8, "sl_failed": 0, "positions_failed": 1, "positions_opened": 8}	2025-09-17 11:54:35.265561+00
2533	main_trader	HEALTHY	t	t	t	\N	8	0	0	\N	{"sl_set": 8, "sl_failed": 0, "positions_failed": 1, "positions_opened": 8}	2025-09-17 11:55:36.308979+00
2534	main_trader	HEALTHY	t	t	t	\N	8	0	0	\N	{"sl_set": 8, "sl_failed": 0, "positions_failed": 1, "positions_opened": 8}	2025-09-17 11:56:37.892922+00
2535	main_trader	HEALTHY	t	t	t	\N	8	0	0	\N	{"sl_set": 8, "sl_failed": 0, "positions_failed": 1, "positions_opened": 8}	2025-09-17 11:57:39.729468+00
2536	main_trader	HEALTHY	t	t	t	\N	8	0	0	\N	{"sl_set": 8, "sl_failed": 0, "positions_failed": 1, "positions_opened": 8}	2025-09-17 11:58:41.627012+00
2537	main_trader	HEALTHY	t	t	t	\N	8	0	0	\N	{"sl_set": 8, "sl_failed": 0, "positions_failed": 1, "positions_opened": 8}	2025-09-17 11:59:43.527131+00
2538	main_trader	HEALTHY	t	t	t	\N	8	0	0	\N	{"sl_set": 8, "sl_failed": 0, "positions_failed": 1, "positions_opened": 8}	2025-09-17 12:00:45.45464+00
2539	main_trader	HEALTHY	t	t	t	\N	8	0	0	\N	{"sl_set": 8, "sl_failed": 0, "positions_failed": 1, "positions_opened": 8}	2025-09-17 12:01:47.570855+00
2540	main_trader	HEALTHY	t	t	t	\N	8	0	0	\N	{"sl_set": 8, "sl_failed": 0, "positions_failed": 1, "positions_opened": 8}	2025-09-17 12:02:49.430424+00
2541	main_trader	HEALTHY	t	t	t	\N	8	0	0	\N	{"sl_set": 8, "sl_failed": 0, "positions_failed": 1, "positions_opened": 8}	2025-09-17 12:03:51.277967+00
2542	main_trader	HEALTHY	t	t	t	\N	8	0	0	\N	{"sl_set": 8, "sl_failed": 0, "positions_failed": 1, "positions_opened": 8}	2025-09-17 12:04:53.132264+00
2543	main_trader	HEALTHY	t	t	t	\N	8	0	0	\N	{"sl_set": 8, "sl_failed": 0, "positions_failed": 1, "positions_opened": 8}	2025-09-17 12:05:55.012663+00
2544	main_trader	HEALTHY	t	t	t	\N	8	0	0	\N	{"sl_set": 8, "sl_failed": 0, "positions_failed": 1, "positions_opened": 8}	2025-09-17 12:06:56.989626+00
2545	main_trader	HEALTHY	t	t	t	\N	9	0	0	\N	{"sl_set": 10, "sl_failed": 0, "positions_failed": 2, "positions_opened": 10}	2025-09-17 12:07:58.838109+00
2546	main_trader	HEALTHY	t	t	t	\N	11	0	0	\N	{"sl_set": 11, "sl_failed": 0, "positions_failed": 4, "positions_opened": 11}	2025-09-17 12:09:00.604544+00
2547	main_trader	HEALTHY	t	t	t	\N	13	0	0	\N	{"sl_set": 13, "sl_failed": 0, "positions_failed": 4, "positions_opened": 13}	2025-09-17 12:10:02.191938+00
2548	main_trader	HEALTHY	t	t	t	\N	13	0	0	\N	{"sl_set": 13, "sl_failed": 0, "positions_failed": 7, "positions_opened": 14}	2025-09-17 12:11:03.95227+00
2549	main_trader	HEALTHY	t	t	t	\N	15	0	0	\N	{"sl_set": 15, "sl_failed": 0, "positions_failed": 8, "positions_opened": 15}	2025-09-17 12:12:05.773128+00
2550	main_trader	HEALTHY	t	t	t	\N	17	0	0	\N	{"sl_set": 17, "sl_failed": 0, "positions_failed": 8, "positions_opened": 18}	2025-09-17 12:13:06.916181+00
2551	main_trader	HEALTHY	t	t	t	\N	19	0	0	\N	{"sl_set": 19, "sl_failed": 0, "positions_failed": 8, "positions_opened": 19}	2025-09-17 12:14:08.774478+00
2552	main_trader	HEALTHY	t	t	t	\N	19	0	0	\N	{"sl_set": 19, "sl_failed": 0, "positions_failed": 8, "positions_opened": 19}	2025-09-17 12:15:10.555535+00
2553	main_trader	HEALTHY	t	t	t	\N	19	0	0	\N	{"sl_set": 19, "sl_failed": 0, "positions_failed": 8, "positions_opened": 19}	2025-09-17 12:16:11.735239+00
2554	main_trader	HEALTHY	t	t	t	\N	19	0	0	\N	{"sl_set": 19, "sl_failed": 0, "positions_failed": 8, "positions_opened": 19}	2025-09-17 12:17:14.05807+00
2555	main_trader	HEALTHY	t	t	t	\N	19	0	0	\N	{"sl_set": 19, "sl_failed": 0, "positions_failed": 8, "positions_opened": 19}	2025-09-17 12:18:15.934757+00
2556	main_trader	HEALTHY	t	t	t	\N	19	0	0	\N	{"sl_set": 19, "sl_failed": 0, "positions_failed": 8, "positions_opened": 19}	2025-09-17 12:19:17.812885+00
2557	main_trader	HEALTHY	t	t	t	\N	19	0	0	\N	{"sl_set": 19, "sl_failed": 0, "positions_failed": 8, "positions_opened": 19}	2025-09-17 12:20:19.671087+00
2558	main_trader	HEALTHY	t	t	t	\N	19	0	0	\N	{"sl_set": 19, "sl_failed": 0, "positions_failed": 8, "positions_opened": 19}	2025-09-17 12:21:21.55701+00
2559	main_trader	HEALTHY	t	t	t	\N	20	0	0	\N	{"sl_set": 20, "sl_failed": 0, "positions_failed": 10, "positions_opened": 20}	2025-09-17 12:22:22.920484+00
2560	main_trader	HEALTHY	t	t	t	\N	22	0	0	\N	{"sl_set": 22, "sl_failed": 0, "positions_failed": 11, "positions_opened": 22}	2025-09-17 12:23:25.101987+00
2561	main_trader	HEALTHY	t	t	t	\N	25	0	0	\N	{"sl_set": 25, "sl_failed": 0, "positions_failed": 11, "positions_opened": 25}	2025-09-17 12:24:26.70343+00
2562	main_trader	HEALTHY	t	t	t	\N	27	0	0	\N	{"sl_set": 27, "sl_failed": 0, "positions_failed": 12, "positions_opened": 27}	2025-09-17 12:25:27.864307+00
2563	main_trader	HEALTHY	t	t	t	\N	28	0	0	\N	{"sl_set": 28, "sl_failed": 0, "positions_failed": 13, "positions_opened": 28}	2025-09-17 12:26:29.713456+00
2564	main_trader	HEALTHY	t	t	t	\N	28	0	0	\N	{"sl_set": 28, "sl_failed": 0, "positions_failed": 13, "positions_opened": 28}	2025-09-17 12:27:32.325792+00
2565	main_trader	HEALTHY	t	t	t	\N	28	0	0	\N	{"sl_set": 28, "sl_failed": 0, "positions_failed": 13, "positions_opened": 28}	2025-09-17 12:28:34.174471+00
2566	main_trader	HEALTHY	t	t	t	\N	28	0	0	\N	{"sl_set": 28, "sl_failed": 0, "positions_failed": 13, "positions_opened": 28}	2025-09-17 12:29:36.037301+00
2567	main_trader	HEALTHY	t	t	t	\N	28	0	0	\N	{"sl_set": 28, "sl_failed": 0, "positions_failed": 13, "positions_opened": 28}	2025-09-17 12:30:37.354615+00
2568	main_trader	HEALTHY	t	t	t	\N	28	0	0	\N	{"sl_set": 28, "sl_failed": 0, "positions_failed": 13, "positions_opened": 28}	2025-09-17 12:31:39.155828+00
2569	main_trader	HEALTHY	t	t	t	\N	28	0	0	\N	{"sl_set": 28, "sl_failed": 0, "positions_failed": 13, "positions_opened": 28}	2025-09-17 12:32:41.346557+00
2570	main_trader	HEALTHY	t	t	t	\N	28	0	0	\N	{"sl_set": 28, "sl_failed": 0, "positions_failed": 13, "positions_opened": 28}	2025-09-17 12:33:42.758105+00
2571	main_trader	HEALTHY	t	t	t	\N	28	0	0	\N	{"sl_set": 28, "sl_failed": 0, "positions_failed": 13, "positions_opened": 28}	2025-09-17 12:34:44.973784+00
2572	main_trader	HEALTHY	t	t	t	\N	28	0	0	\N	{"sl_set": 28, "sl_failed": 0, "positions_failed": 13, "positions_opened": 28}	2025-09-17 12:35:46.385961+00
2573	main_trader	HEALTHY	t	t	t	\N	30	0	0	\N	{"sl_set": 30, "sl_failed": 0, "positions_failed": 13, "positions_opened": 31}	2025-09-17 12:36:48.161012+00
2574	main_trader	HEALTHY	t	t	t	\N	31	0	0	\N	{"sl_set": 32, "sl_failed": 0, "positions_failed": 15, "positions_opened": 32}	2025-09-17 12:37:50.045554+00
2575	main_trader	HEALTHY	t	t	t	\N	32	0	0	\N	{"sl_set": 33, "sl_failed": 0, "positions_failed": 17, "positions_opened": 33}	2025-09-17 12:38:51.792915+00
2576	main_trader	HEALTHY	t	t	t	\N	35	0	0	\N	{"sl_set": 35, "sl_failed": 0, "positions_failed": 17, "positions_opened": 35}	2025-09-17 12:39:53.637404+00
2577	main_trader	HEALTHY	t	t	t	\N	37	0	0	\N	{"sl_set": 38, "sl_failed": 0, "positions_failed": 17, "positions_opened": 38}	2025-09-17 12:40:55.224162+00
2578	main_trader	HEALTHY	t	t	t	\N	39	0	0	\N	{"sl_set": 40, "sl_failed": 0, "positions_failed": 18, "positions_opened": 40}	2025-09-17 12:41:57.091011+00
2579	main_trader	HEALTHY	t	t	t	\N	40	0	0	\N	{"sl_set": 40, "sl_failed": 0, "positions_failed": 18, "positions_opened": 40}	2025-09-17 12:42:58.175264+00
2580	main_trader	HEALTHY	t	t	t	\N	40	0	0	\N	{"sl_set": 40, "sl_failed": 0, "positions_failed": 18, "positions_opened": 40}	2025-09-17 12:44:00.481203+00
2581	main_trader	HEALTHY	t	t	t	\N	40	0	0	\N	{"sl_set": 40, "sl_failed": 0, "positions_failed": 18, "positions_opened": 40}	2025-09-17 12:45:02.431385+00
2582	main_trader	HEALTHY	t	t	t	\N	40	0	0	\N	{"sl_set": 40, "sl_failed": 0, "positions_failed": 18, "positions_opened": 40}	2025-09-17 12:46:04.202002+00
2583	main_trader	HEALTHY	t	t	t	\N	40	0	0	\N	{"sl_set": 40, "sl_failed": 0, "positions_failed": 18, "positions_opened": 40}	2025-09-17 12:47:06.137475+00
2584	main_trader	HEALTHY	t	t	t	\N	40	0	0	\N	{"sl_set": 40, "sl_failed": 0, "positions_failed": 18, "positions_opened": 40}	2025-09-17 12:48:07.971463+00
2585	main_trader	HEALTHY	t	t	t	\N	40	0	0	\N	{"sl_set": 40, "sl_failed": 0, "positions_failed": 18, "positions_opened": 40}	2025-09-17 12:49:09.738277+00
2586	main_trader	HEALTHY	t	t	t	\N	40	0	0	\N	{"sl_set": 40, "sl_failed": 0, "positions_failed": 18, "positions_opened": 40}	2025-09-17 12:50:11.589189+00
2587	main_trader	HEALTHY	t	t	t	\N	40	0	0	\N	{"sl_set": 40, "sl_failed": 0, "positions_failed": 18, "positions_opened": 41}	2025-09-17 12:51:13.187243+00
2588	main_trader	HEALTHY	t	t	t	\N	43	0	0	\N	{"sl_set": 43, "sl_failed": 0, "positions_failed": 18, "positions_opened": 43}	2025-09-17 12:52:15.174038+00
2589	main_trader	HEALTHY	t	t	t	\N	44	0	0	\N	{"sl_set": 44, "sl_failed": 0, "positions_failed": 20, "positions_opened": 44}	2025-09-17 12:53:16.835568+00
2590	main_trader	HEALTHY	t	t	t	\N	47	0	0	\N	{"sl_set": 47, "sl_failed": 0, "positions_failed": 20, "positions_opened": 47}	2025-09-17 12:54:18.900264+00
2591	main_trader	HEALTHY	t	t	t	\N	49	0	0	\N	{"sl_set": 49, "sl_failed": 0, "positions_failed": 21, "positions_opened": 49}	2025-09-17 12:55:19.964985+00
2592	main_trader	HEALTHY	t	t	t	\N	52	0	0	\N	{"sl_set": 52, "sl_failed": 0, "positions_failed": 21, "positions_opened": 52}	2025-09-17 12:56:21.85109+00
2593	main_trader	HEALTHY	t	t	t	\N	54	0	0	\N	{"sl_set": 54, "sl_failed": 0, "positions_failed": 22, "positions_opened": 54}	2025-09-17 12:57:23.389872+00
2594	main_trader	HEALTHY	t	t	t	\N	57	0	0	\N	{"sl_set": 57, "sl_failed": 0, "positions_failed": 22, "positions_opened": 57}	2025-09-17 12:58:24.578537+00
2595	main_trader	HEALTHY	t	t	t	\N	60	0	0	\N	{"sl_set": 60, "sl_failed": 0, "positions_failed": 22, "positions_opened": 60}	2025-09-17 12:59:25.479931+00
2596	main_trader	HEALTHY	t	t	t	\N	61	0	0	\N	{"sl_set": 61, "sl_failed": 0, "positions_failed": 23, "positions_opened": 61}	2025-09-17 13:00:27.225828+00
2597	main_trader	HEALTHY	t	t	t	\N	61	0	0	\N	{"sl_set": 61, "sl_failed": 0, "positions_failed": 23, "positions_opened": 61}	2025-09-17 13:01:29.078814+00
2598	main_trader	HEALTHY	t	t	t	\N	61	0	0	\N	{"sl_set": 61, "sl_failed": 0, "positions_failed": 23, "positions_opened": 61}	2025-09-17 13:02:31.226363+00
2599	main_trader	HEALTHY	t	t	t	\N	61	0	0	\N	{"sl_set": 61, "sl_failed": 0, "positions_failed": 23, "positions_opened": 61}	2025-09-17 13:03:32.706641+00
2600	main_trader	HEALTHY	t	t	t	\N	61	0	0	\N	{"sl_set": 61, "sl_failed": 0, "positions_failed": 23, "positions_opened": 61}	2025-09-17 13:04:34.486856+00
2601	main_trader	HEALTHY	t	t	t	\N	61	0	0	\N	{"sl_set": 61, "sl_failed": 0, "positions_failed": 23, "positions_opened": 61}	2025-09-17 13:05:36.256658+00
2602	main_trader	HEALTHY	t	t	t	\N	61	0	0	\N	{"sl_set": 61, "sl_failed": 0, "positions_failed": 25, "positions_opened": 61}	2025-09-17 13:06:37.413842+00
2603	main_trader	HEALTHY	t	t	t	\N	62	0	0	\N	{"sl_set": 63, "sl_failed": 0, "positions_failed": 27, "positions_opened": 63}	2025-09-17 13:07:39.171179+00
2604	main_trader	HEALTHY	t	t	t	\N	65	0	0	\N	{"sl_set": 66, "sl_failed": 0, "positions_failed": 27, "positions_opened": 66}	2025-09-17 13:08:40.358743+00
2605	main_trader	HEALTHY	t	t	t	\N	68	0	0	\N	{"sl_set": 68, "sl_failed": 0, "positions_failed": 28, "positions_opened": 68}	2025-09-17 13:09:41.31745+00
2606	main_trader	HEALTHY	t	t	t	\N	71	0	0	\N	{"sl_set": 71, "sl_failed": 0, "positions_failed": 28, "positions_opened": 71}	2025-09-17 13:10:42.200733+00
2607	main_trader	HEALTHY	t	t	t	\N	74	0	0	\N	{"sl_set": 74, "sl_failed": 0, "positions_failed": 28, "positions_opened": 74}	2025-09-17 13:11:43.091999+00
2608	main_trader	HEALTHY	t	t	t	\N	74	0	0	\N	{"sl_set": 74, "sl_failed": 0, "positions_failed": 28, "positions_opened": 74}	2025-09-17 13:12:44.216766+00
2609	main_trader	HEALTHY	t	t	t	\N	74	0	0	\N	{"sl_set": 74, "sl_failed": 0, "positions_failed": 28, "positions_opened": 74}	2025-09-17 13:13:45.931666+00
2610	main_trader	HEALTHY	t	t	t	\N	74	0	0	\N	{"sl_set": 74, "sl_failed": 0, "positions_failed": 28, "positions_opened": 74}	2025-09-17 13:14:47.366306+00
2611	main_trader	HEALTHY	t	t	t	\N	74	0	0	\N	{"sl_set": 74, "sl_failed": 0, "positions_failed": 28, "positions_opened": 74}	2025-09-17 13:15:48.410136+00
2612	main_trader	HEALTHY	t	t	t	\N	74	0	0	\N	{"sl_set": 74, "sl_failed": 0, "positions_failed": 28, "positions_opened": 74}	2025-09-17 13:16:49.563244+00
2613	main_trader	HEALTHY	t	t	t	\N	74	0	0	\N	{"sl_set": 74, "sl_failed": 0, "positions_failed": 28, "positions_opened": 74}	2025-09-17 13:17:50.693825+00
2614	main_trader	HEALTHY	t	t	t	\N	74	0	0	\N	{"sl_set": 74, "sl_failed": 0, "positions_failed": 28, "positions_opened": 74}	2025-09-17 13:18:51.961352+00
2615	main_trader	HEALTHY	t	t	t	\N	74	0	0	\N	{"sl_set": 74, "sl_failed": 0, "positions_failed": 28, "positions_opened": 74}	2025-09-17 13:19:53.16162+00
2616	main_trader	HEALTHY	t	t	t	\N	74	0	0	\N	{"sl_set": 74, "sl_failed": 0, "positions_failed": 28, "positions_opened": 74}	2025-09-17 13:20:54.299869+00
2617	main_trader	HEALTHY	t	t	t	\N	76	0	0	\N	{"sl_set": 76, "sl_failed": 0, "positions_failed": 29, "positions_opened": 76}	2025-09-17 13:21:55.418641+00
2618	main_trader	HEALTHY	t	t	t	\N	79	0	0	\N	{"sl_set": 78, "sl_failed": 1, "positions_failed": 29, "positions_opened": 79}	2025-09-17 13:22:56.29326+00
2619	main_trader	HEALTHY	t	t	t	\N	82	0	0	\N	{"sl_set": 81, "sl_failed": 1, "positions_failed": 29, "positions_opened": 82}	2025-09-17 13:23:57.558217+00
2620	main_trader	HEALTHY	t	t	t	\N	83	0	0	\N	{"sl_set": 82, "sl_failed": 1, "positions_failed": 29, "positions_opened": 83}	2025-09-17 13:24:58.772046+00
2621	main_trader	HEALTHY	t	t	t	\N	83	0	0	\N	{"sl_set": 82, "sl_failed": 1, "positions_failed": 29, "positions_opened": 83}	2025-09-17 13:25:59.814943+00
2622	main_trader	HEALTHY	t	t	t	\N	83	0	0	\N	{"sl_set": 82, "sl_failed": 1, "positions_failed": 29, "positions_opened": 83}	2025-09-17 13:27:00.946247+00
2623	main_trader	HEALTHY	t	t	t	\N	83	0	0	\N	{"sl_set": 82, "sl_failed": 1, "positions_failed": 29, "positions_opened": 83}	2025-09-17 13:28:02.202562+00
2624	main_trader	HEALTHY	t	t	t	\N	83	0	0	\N	{"sl_set": 82, "sl_failed": 1, "positions_failed": 29, "positions_opened": 83}	2025-09-17 13:29:03.4874+00
2625	main_trader	HEALTHY	t	t	t	\N	83	0	0	\N	{"sl_set": 82, "sl_failed": 1, "positions_failed": 29, "positions_opened": 83}	2025-09-17 13:30:05.445402+00
2626	main_trader	HEALTHY	t	t	t	\N	83	0	0	\N	{"sl_set": 82, "sl_failed": 1, "positions_failed": 29, "positions_opened": 83}	2025-09-17 13:31:06.597158+00
2627	main_trader	HEALTHY	t	t	t	\N	83	0	0	\N	{"sl_set": 82, "sl_failed": 1, "positions_failed": 29, "positions_opened": 83}	2025-09-17 13:32:07.639534+00
2628	main_trader	HEALTHY	t	t	t	\N	83	0	0	\N	{"sl_set": 82, "sl_failed": 1, "positions_failed": 29, "positions_opened": 83}	2025-09-17 13:33:08.90398+00
2629	main_trader	HEALTHY	t	t	t	\N	83	0	0	\N	{"sl_set": 82, "sl_failed": 1, "positions_failed": 29, "positions_opened": 83}	2025-09-17 13:34:10.114311+00
2630	main_trader	RUNNING	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-17 13:48:07.269428+00
2631	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 1, "positions_opened": 2}	2025-09-17 13:49:08.463173+00
2632	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 1, "positions_opened": 2}	2025-09-17 13:50:09.627282+00
2633	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 1, "positions_opened": 3}	2025-09-17 13:51:11.163133+00
2634	main_trader	HEALTHY	t	t	t	\N	5	0	0	\N	{"sl_set": 6, "sl_failed": 0, "positions_failed": 1, "positions_opened": 6}	2025-09-17 13:52:12.273681+00
2635	main_trader	HEALTHY	t	t	t	\N	8	0	0	\N	{"sl_set": 9, "sl_failed": 0, "positions_failed": 1, "positions_opened": 9}	2025-09-17 13:53:13.446675+00
2636	main_trader	HEALTHY	t	t	t	\N	11	0	0	\N	{"sl_set": 12, "sl_failed": 0, "positions_failed": 1, "positions_opened": 12}	2025-09-17 13:54:14.558695+00
2637	main_trader	HEALTHY	t	t	t	\N	14	0	0	\N	{"sl_set": 14, "sl_failed": 0, "positions_failed": 1, "positions_opened": 14}	2025-09-17 13:55:15.959613+00
2638	main_trader	HEALTHY	t	t	t	\N	15	0	0	\N	{"sl_set": 16, "sl_failed": 0, "positions_failed": 3, "positions_opened": 16}	2025-09-17 13:56:16.849461+00
2639	main_trader	HEALTHY	t	t	t	\N	18	0	0	\N	{"sl_set": 18, "sl_failed": 0, "positions_failed": 4, "positions_opened": 18}	2025-09-17 13:57:17.870855+00
2640	main_trader	HEALTHY	t	t	t	\N	21	0	0	\N	{"sl_set": 21, "sl_failed": 0, "positions_failed": 4, "positions_opened": 21}	2025-09-17 13:58:18.830936+00
2641	main_trader	HEALTHY	t	t	t	\N	22	0	0	\N	{"sl_set": 22, "sl_failed": 0, "positions_failed": 6, "positions_opened": 22}	2025-09-17 13:59:19.879803+00
2642	main_trader	HEALTHY	t	t	t	\N	23	0	0	\N	{"sl_set": 23, "sl_failed": 0, "positions_failed": 6, "positions_opened": 23}	2025-09-17 14:00:21.130726+00
2643	main_trader	HEALTHY	t	t	t	\N	23	0	0	\N	{"sl_set": 23, "sl_failed": 0, "positions_failed": 6, "positions_opened": 23}	2025-09-17 14:01:22.237302+00
2644	main_trader	HEALTHY	t	t	t	\N	23	0	0	\N	{"sl_set": 23, "sl_failed": 0, "positions_failed": 6, "positions_opened": 23}	2025-09-17 14:02:24.097588+00
2645	main_trader	HEALTHY	t	t	t	\N	23	0	0	\N	{"sl_set": 23, "sl_failed": 0, "positions_failed": 6, "positions_opened": 23}	2025-09-17 14:03:25.129697+00
2646	main_trader	HEALTHY	t	t	t	\N	23	0	0	\N	{"sl_set": 23, "sl_failed": 0, "positions_failed": 6, "positions_opened": 23}	2025-09-17 14:04:26.286092+00
2647	main_trader	HEALTHY	t	t	t	\N	23	0	0	\N	{"sl_set": 23, "sl_failed": 0, "positions_failed": 6, "positions_opened": 23}	2025-09-17 14:05:27.361775+00
2648	main_trader	HEALTHY	t	t	t	\N	23	0	0	\N	{"sl_set": 23, "sl_failed": 0, "positions_failed": 6, "positions_opened": 23}	2025-09-17 14:06:28.523861+00
2649	main_trader	HEALTHY	t	t	t	\N	26	0	0	\N	{"sl_set": 26, "sl_failed": 0, "positions_failed": 6, "positions_opened": 26}	2025-09-17 14:07:29.881443+00
2650	main_trader	HEALTHY	t	t	t	\N	29	0	0	\N	{"sl_set": 29, "sl_failed": 0, "positions_failed": 6, "positions_opened": 29}	2025-09-17 14:08:31.125467+00
2651	main_trader	HEALTHY	t	t	t	\N	32	0	0	\N	{"sl_set": 32, "sl_failed": 0, "positions_failed": 6, "positions_opened": 32}	2025-09-17 14:09:32.270058+00
2652	main_trader	HEALTHY	t	t	t	\N	35	0	0	\N	{"sl_set": 35, "sl_failed": 0, "positions_failed": 6, "positions_opened": 35}	2025-09-17 14:10:33.388254+00
2653	main_trader	HEALTHY	t	t	t	\N	37	0	0	\N	{"sl_set": 37, "sl_failed": 0, "positions_failed": 7, "positions_opened": 37}	2025-09-17 14:11:34.63363+00
2654	main_trader	HEALTHY	t	t	t	\N	40	0	0	\N	{"sl_set": 40, "sl_failed": 0, "positions_failed": 7, "positions_opened": 40}	2025-09-17 14:12:36.493819+00
2655	main_trader	HEALTHY	t	t	t	\N	41	0	0	\N	{"sl_set": 41, "sl_failed": 0, "positions_failed": 9, "positions_opened": 41}	2025-09-17 14:13:37.745308+00
2656	main_trader	HEALTHY	t	t	t	\N	41	0	0	\N	{"sl_set": 41, "sl_failed": 0, "positions_failed": 9, "positions_opened": 41}	2025-09-17 14:14:38.889105+00
2657	main_trader	HEALTHY	t	t	t	\N	41	0	0	\N	{"sl_set": 41, "sl_failed": 0, "positions_failed": 9, "positions_opened": 41}	2025-09-17 14:15:40.06688+00
2658	main_trader	HEALTHY	t	t	t	\N	41	0	0	\N	{"sl_set": 41, "sl_failed": 0, "positions_failed": 9, "positions_opened": 41}	2025-09-17 14:16:41.105867+00
2659	main_trader	HEALTHY	t	t	t	\N	41	0	0	\N	{"sl_set": 41, "sl_failed": 0, "positions_failed": 9, "positions_opened": 41}	2025-09-17 14:17:42.503771+00
2660	main_trader	HEALTHY	t	t	t	\N	41	0	0	\N	{"sl_set": 41, "sl_failed": 0, "positions_failed": 9, "positions_opened": 41}	2025-09-17 14:18:43.710384+00
2661	main_trader	HEALTHY	t	t	t	\N	41	0	0	\N	{"sl_set": 41, "sl_failed": 0, "positions_failed": 9, "positions_opened": 41}	2025-09-17 14:19:44.889793+00
2662	main_trader	HEALTHY	t	t	t	\N	41	0	0	\N	{"sl_set": 41, "sl_failed": 0, "positions_failed": 9, "positions_opened": 41}	2025-09-17 14:20:46.061535+00
2663	main_trader	HEALTHY	t	t	t	\N	43	0	0	\N	{"sl_set": 43, "sl_failed": 0, "positions_failed": 10, "positions_opened": 43}	2025-09-17 14:21:46.94617+00
2664	main_trader	HEALTHY	t	t	t	\N	45	0	0	\N	{"sl_set": 45, "sl_failed": 0, "positions_failed": 11, "positions_opened": 45}	2025-09-17 14:22:48.460789+00
2665	main_trader	HEALTHY	t	t	t	\N	48	0	0	\N	{"sl_set": 47, "sl_failed": 1, "positions_failed": 11, "positions_opened": 48}	2025-09-17 14:23:49.435272+00
2666	main_trader	HEALTHY	t	t	t	\N	51	0	0	\N	{"sl_set": 50, "sl_failed": 1, "positions_failed": 11, "positions_opened": 51}	2025-09-17 14:24:50.327157+00
2667	main_trader	HEALTHY	t	t	t	\N	52	0	0	\N	{"sl_set": 51, "sl_failed": 1, "positions_failed": 12, "positions_opened": 52}	2025-09-17 14:25:51.451402+00
2668	main_trader	HEALTHY	t	t	t	\N	55	0	0	\N	{"sl_set": 54, "sl_failed": 1, "positions_failed": 12, "positions_opened": 55}	2025-09-17 14:26:52.327738+00
2669	main_trader	HEALTHY	t	t	t	\N	56	0	0	\N	{"sl_set": 55, "sl_failed": 1, "positions_failed": 13, "positions_opened": 56}	2025-09-17 14:27:53.727048+00
2670	main_trader	HEALTHY	t	t	t	\N	57	0	0	\N	{"sl_set": 56, "sl_failed": 1, "positions_failed": 13, "positions_opened": 57}	2025-09-17 14:28:54.883232+00
2671	main_trader	HEALTHY	t	t	t	\N	57	0	0	\N	{"sl_set": 56, "sl_failed": 1, "positions_failed": 13, "positions_opened": 57}	2025-09-17 14:29:56.010972+00
2672	main_trader	HEALTHY	t	t	t	\N	57	0	0	\N	{"sl_set": 56, "sl_failed": 1, "positions_failed": 13, "positions_opened": 57}	2025-09-17 14:30:57.366242+00
2673	main_trader	HEALTHY	t	t	t	\N	57	0	0	\N	{"sl_set": 56, "sl_failed": 1, "positions_failed": 13, "positions_opened": 57}	2025-09-17 14:31:58.517183+00
2674	main_trader	HEALTHY	t	t	t	\N	57	0	0	\N	{"sl_set": 56, "sl_failed": 1, "positions_failed": 13, "positions_opened": 57}	2025-09-17 14:33:00.325925+00
2675	main_trader	HEALTHY	t	t	t	\N	57	0	0	\N	{"sl_set": 56, "sl_failed": 1, "positions_failed": 13, "positions_opened": 57}	2025-09-17 14:34:01.538664+00
2676	main_trader	HEALTHY	t	t	t	\N	57	0	0	\N	{"sl_set": 56, "sl_failed": 1, "positions_failed": 13, "positions_opened": 57}	2025-09-17 14:35:02.685797+00
2677	main_trader	HEALTHY	t	t	t	\N	57	0	0	\N	{"sl_set": 56, "sl_failed": 1, "positions_failed": 13, "positions_opened": 57}	2025-09-17 14:36:03.822541+00
2678	main_trader	HEALTHY	t	t	t	\N	60	0	0	\N	{"sl_set": 59, "sl_failed": 1, "positions_failed": 13, "positions_opened": 60}	2025-09-17 14:37:04.952255+00
2679	main_trader	HEALTHY	t	t	t	\N	63	0	0	\N	{"sl_set": 62, "sl_failed": 1, "positions_failed": 13, "positions_opened": 63}	2025-09-17 14:38:06.307392+00
2680	main_trader	HEALTHY	t	t	t	\N	66	0	0	\N	{"sl_set": 65, "sl_failed": 1, "positions_failed": 13, "positions_opened": 66}	2025-09-17 14:39:07.640401+00
2681	main_trader	HEALTHY	t	t	t	\N	69	0	0	\N	{"sl_set": 68, "sl_failed": 1, "positions_failed": 13, "positions_opened": 69}	2025-09-17 14:40:08.771763+00
2682	main_trader	HEALTHY	t	t	t	\N	72	0	0	\N	{"sl_set": 71, "sl_failed": 1, "positions_failed": 13, "positions_opened": 72}	2025-09-17 14:41:09.856268+00
2683	main_trader	HEALTHY	t	t	t	\N	75	0	0	\N	{"sl_set": 74, "sl_failed": 1, "positions_failed": 13, "positions_opened": 75}	2025-09-17 14:42:11.019803+00
2684	main_trader	HEALTHY	t	t	t	\N	77	0	0	\N	{"sl_set": 76, "sl_failed": 1, "positions_failed": 14, "positions_opened": 77}	2025-09-17 14:43:12.138029+00
2685	main_trader	HEALTHY	t	t	t	\N	79	0	0	\N	{"sl_set": 78, "sl_failed": 1, "positions_failed": 15, "positions_opened": 79}	2025-09-17 14:44:13.089235+00
2686	main_trader	HEALTHY	t	t	t	\N	79	0	0	\N	{"sl_set": 78, "sl_failed": 1, "positions_failed": 15, "positions_opened": 79}	2025-09-17 14:45:14.236568+00
2687	main_trader	HEALTHY	t	t	t	\N	79	0	0	\N	{"sl_set": 78, "sl_failed": 1, "positions_failed": 15, "positions_opened": 79}	2025-09-17 14:46:15.366991+00
2688	main_trader	HEALTHY	t	t	t	\N	79	0	0	\N	{"sl_set": 78, "sl_failed": 1, "positions_failed": 15, "positions_opened": 79}	2025-09-17 14:47:16.499712+00
2689	main_trader	HEALTHY	t	t	t	\N	79	0	0	\N	{"sl_set": 78, "sl_failed": 1, "positions_failed": 15, "positions_opened": 79}	2025-09-17 14:48:18.282822+00
2690	main_trader	HEALTHY	t	t	t	\N	79	0	0	\N	{"sl_set": 78, "sl_failed": 1, "positions_failed": 15, "positions_opened": 79}	2025-09-17 14:49:19.517957+00
2691	main_trader	HEALTHY	t	t	t	\N	79	0	0	\N	{"sl_set": 78, "sl_failed": 1, "positions_failed": 15, "positions_opened": 79}	2025-09-17 14:50:20.662278+00
2692	main_trader	HEALTHY	t	t	t	\N	79	0	0	\N	{"sl_set": 78, "sl_failed": 1, "positions_failed": 16, "positions_opened": 79}	2025-09-17 14:51:21.849979+00
2693	main_trader	HEALTHY	t	t	t	\N	79	0	0	\N	{"sl_set": 78, "sl_failed": 1, "positions_failed": 19, "positions_opened": 79}	2025-09-17 14:52:22.731338+00
2694	main_trader	HEALTHY	t	t	t	\N	79	0	0	\N	{"sl_set": 78, "sl_failed": 1, "positions_failed": 23, "positions_opened": 79}	2025-09-17 14:53:24.016566+00
2695	main_trader	HEALTHY	t	t	t	\N	79	0	0	\N	{"sl_set": 78, "sl_failed": 1, "positions_failed": 27, "positions_opened": 79}	2025-09-17 14:54:25.008649+00
2696	main_trader	HEALTHY	t	t	t	\N	80	0	0	\N	{"sl_set": 79, "sl_failed": 1, "positions_failed": 28, "positions_opened": 80}	2025-09-17 14:55:26.089882+00
2697	main_trader	HEALTHY	t	t	t	\N	80	0	0	\N	{"sl_set": 79, "sl_failed": 1, "positions_failed": 28, "positions_opened": 80}	2025-09-17 14:56:27.219006+00
2698	main_trader	HEALTHY	t	t	t	\N	80	0	0	\N	{"sl_set": 79, "sl_failed": 1, "positions_failed": 28, "positions_opened": 80}	2025-09-17 14:57:28.416548+00
2699	main_trader	HEALTHY	t	t	t	\N	80	0	0	\N	{"sl_set": 79, "sl_failed": 1, "positions_failed": 28, "positions_opened": 80}	2025-09-17 14:58:29.940731+00
2700	main_trader	HEALTHY	t	t	t	\N	80	0	0	\N	{"sl_set": 79, "sl_failed": 1, "positions_failed": 28, "positions_opened": 80}	2025-09-17 14:59:31.732839+00
2701	main_trader	HEALTHY	t	t	t	\N	80	0	0	\N	{"sl_set": 79, "sl_failed": 1, "positions_failed": 28, "positions_opened": 80}	2025-09-17 15:00:32.849032+00
2702	main_trader	HEALTHY	t	t	t	\N	80	0	0	\N	{"sl_set": 79, "sl_failed": 1, "positions_failed": 28, "positions_opened": 80}	2025-09-17 15:01:34.030213+00
2703	main_trader	HEALTHY	t	t	t	\N	80	0	0	\N	{"sl_set": 79, "sl_failed": 1, "positions_failed": 28, "positions_opened": 80}	2025-09-17 15:02:35.168815+00
2704	main_trader	HEALTHY	t	t	t	\N	80	0	0	\N	{"sl_set": 79, "sl_failed": 1, "positions_failed": 28, "positions_opened": 80}	2025-09-17 15:03:36.549365+00
2705	main_trader	HEALTHY	t	t	t	\N	80	0	0	\N	{"sl_set": 79, "sl_failed": 1, "positions_failed": 28, "positions_opened": 80}	2025-09-17 15:04:37.752458+00
2706	main_trader	HEALTHY	t	t	t	\N	80	0	0	\N	{"sl_set": 79, "sl_failed": 1, "positions_failed": 28, "positions_opened": 80}	2025-09-17 15:05:38.883633+00
2707	main_trader	HEALTHY	t	t	t	\N	80	0	0	\N	{"sl_set": 79, "sl_failed": 1, "positions_failed": 30, "positions_opened": 81}	2025-09-17 15:06:39.756773+00
2708	main_trader	HEALTHY	t	t	t	\N	81	0	0	\N	{"sl_set": 80, "sl_failed": 1, "positions_failed": 33, "positions_opened": 81}	2025-09-17 15:07:40.630887+00
2709	main_trader	HEALTHY	t	t	t	\N	81	0	0	\N	{"sl_set": 80, "sl_failed": 1, "positions_failed": 36, "positions_opened": 81}	2025-09-17 15:08:41.745463+00
2710	main_trader	HEALTHY	t	t	t	\N	81	0	0	\N	{"sl_set": 80, "sl_failed": 1, "positions_failed": 38, "positions_opened": 81}	2025-09-17 15:09:42.939308+00
2711	main_trader	HEALTHY	t	t	t	\N	81	0	0	\N	{"sl_set": 80, "sl_failed": 1, "positions_failed": 40, "positions_opened": 81}	2025-09-17 15:10:43.832561+00
2712	main_trader	HEALTHY	t	t	t	\N	82	0	0	\N	{"sl_set": 81, "sl_failed": 1, "positions_failed": 42, "positions_opened": 82}	2025-09-17 15:11:45.018619+00
2713	main_trader	HEALTHY	t	t	t	\N	82	0	0	\N	{"sl_set": 81, "sl_failed": 1, "positions_failed": 42, "positions_opened": 82}	2025-09-17 15:12:46.144785+00
2714	main_trader	HEALTHY	t	t	t	\N	82	0	0	\N	{"sl_set": 81, "sl_failed": 1, "positions_failed": 42, "positions_opened": 82}	2025-09-17 15:13:47.681308+00
2715	main_trader	HEALTHY	t	t	t	\N	82	0	0	\N	{"sl_set": 81, "sl_failed": 1, "positions_failed": 42, "positions_opened": 82}	2025-09-17 15:14:48.789497+00
2716	main_trader	HEALTHY	t	t	t	\N	82	0	0	\N	{"sl_set": 81, "sl_failed": 1, "positions_failed": 42, "positions_opened": 82}	2025-09-17 15:15:49.844271+00
2717	main_trader	HEALTHY	t	t	t	\N	82	0	0	\N	{"sl_set": 81, "sl_failed": 1, "positions_failed": 42, "positions_opened": 82}	2025-09-17 15:16:51.198273+00
2718	main_trader	HEALTHY	t	t	t	\N	82	0	0	\N	{"sl_set": 81, "sl_failed": 1, "positions_failed": 42, "positions_opened": 82}	2025-09-17 15:17:52.249246+00
2719	main_trader	HEALTHY	t	t	t	\N	82	0	0	\N	{"sl_set": 81, "sl_failed": 1, "positions_failed": 42, "positions_opened": 82}	2025-09-17 15:18:53.634143+00
2720	main_trader	HEALTHY	t	t	t	\N	82	0	0	\N	{"sl_set": 81, "sl_failed": 1, "positions_failed": 42, "positions_opened": 82}	2025-09-17 15:19:54.868044+00
2721	main_trader	HEALTHY	t	t	t	\N	82	0	0	\N	{"sl_set": 81, "sl_failed": 1, "positions_failed": 42, "positions_opened": 82}	2025-09-17 15:20:56.531142+00
2722	main_trader	HEALTHY	t	t	t	\N	82	0	0	\N	{"sl_set": 81, "sl_failed": 1, "positions_failed": 45, "positions_opened": 82}	2025-09-17 15:21:57.642602+00
2723	main_trader	HEALTHY	t	t	t	\N	82	0	0	\N	{"sl_set": 81, "sl_failed": 1, "positions_failed": 47, "positions_opened": 82}	2025-09-17 15:22:58.674799+00
2724	main_trader	HEALTHY	t	t	t	\N	82	0	0	\N	{"sl_set": 81, "sl_failed": 1, "positions_failed": 51, "positions_opened": 82}	2025-09-17 15:23:59.78872+00
2725	main_trader	HEALTHY	t	t	t	\N	82	0	0	\N	{"sl_set": 81, "sl_failed": 1, "positions_failed": 53, "positions_opened": 82}	2025-09-17 15:25:00.908052+00
2726	main_trader	HEALTHY	t	t	t	\N	82	0	0	\N	{"sl_set": 81, "sl_failed": 1, "positions_failed": 55, "positions_opened": 82}	2025-09-17 15:26:02.092496+00
2727	main_trader	HEALTHY	t	t	t	\N	82	0	0	\N	{"sl_set": 81, "sl_failed": 1, "positions_failed": 58, "positions_opened": 82}	2025-09-17 15:27:03.178254+00
2728	main_trader	HEALTHY	t	t	t	\N	82	0	0	\N	{"sl_set": 81, "sl_failed": 1, "positions_failed": 61, "positions_opened": 82}	2025-09-17 15:28:04.317333+00
2729	main_trader	HEALTHY	t	t	t	\N	82	0	0	\N	{"sl_set": 81, "sl_failed": 1, "positions_failed": 62, "positions_opened": 82}	2025-09-17 15:29:05.71903+00
2730	main_trader	HEALTHY	t	t	t	\N	82	0	0	\N	{"sl_set": 81, "sl_failed": 1, "positions_failed": 63, "positions_opened": 82}	2025-09-17 15:30:06.931+00
2731	main_trader	HEALTHY	t	t	t	\N	82	0	0	\N	{"sl_set": 81, "sl_failed": 1, "positions_failed": 63, "positions_opened": 82}	2025-09-17 15:31:07.974244+00
2732	main_trader	HEALTHY	t	t	t	\N	82	0	0	\N	{"sl_set": 81, "sl_failed": 1, "positions_failed": 63, "positions_opened": 82}	2025-09-17 15:32:09.374243+00
2733	main_trader	HEALTHY	t	t	t	\N	82	0	0	\N	{"sl_set": 81, "sl_failed": 1, "positions_failed": 63, "positions_opened": 82}	2025-09-17 15:33:10.49229+00
2734	main_trader	HEALTHY	t	t	t	\N	82	0	0	\N	{"sl_set": 81, "sl_failed": 1, "positions_failed": 63, "positions_opened": 82}	2025-09-17 15:34:11.805974+00
2735	main_trader	HEALTHY	t	t	t	\N	82	0	0	\N	{"sl_set": 81, "sl_failed": 1, "positions_failed": 63, "positions_opened": 82}	2025-09-17 15:35:13.037574+00
2736	main_trader	HEALTHY	t	t	t	\N	82	0	0	\N	{"sl_set": 81, "sl_failed": 1, "positions_failed": 63, "positions_opened": 82}	2025-09-17 15:36:14.073326+00
2737	main_trader	HEALTHY	t	t	t	\N	83	0	0	\N	{"sl_set": 82, "sl_failed": 1, "positions_failed": 65, "positions_opened": 83}	2025-09-17 15:37:14.942577+00
2738	main_trader	HEALTHY	t	t	t	\N	83	0	0	\N	{"sl_set": 82, "sl_failed": 1, "positions_failed": 68, "positions_opened": 83}	2025-09-17 15:38:16.069816+00
2739	main_trader	HEALTHY	t	t	t	\N	84	0	0	\N	{"sl_set": 83, "sl_failed": 1, "positions_failed": 70, "positions_opened": 84}	2025-09-17 15:39:17.153813+00
2740	main_trader	HEALTHY	t	t	t	\N	84	0	0	\N	{"sl_set": 83, "sl_failed": 1, "positions_failed": 72, "positions_opened": 84}	2025-09-17 15:40:18.260933+00
2741	main_trader	HEALTHY	t	t	t	\N	84	0	0	\N	{"sl_set": 83, "sl_failed": 1, "positions_failed": 74, "positions_opened": 84}	2025-09-17 15:41:19.363558+00
2742	main_trader	RUNNING	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-17 15:55:56.58954+00
2743	main_trader	HEALTHY	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 0, "positions_opened": 3}	2025-09-17 15:56:57.788431+00
2744	main_trader	HEALTHY	t	t	t	\N	6	0	0	\N	{"sl_set": 6, "sl_failed": 0, "positions_failed": 0, "positions_opened": 6}	2025-09-17 15:57:59.35765+00
2745	main_trader	HEALTHY	t	t	t	\N	9	0	0	\N	{"sl_set": 8, "sl_failed": 1, "positions_failed": 0, "positions_opened": 9}	2025-09-17 15:59:00.413757+00
2746	main_trader	HEALTHY	t	t	t	\N	12	0	0	\N	{"sl_set": 11, "sl_failed": 1, "positions_failed": 0, "positions_opened": 12}	2025-09-17 16:00:01.450046+00
2747	main_trader	HEALTHY	t	t	t	\N	13	0	0	\N	{"sl_set": 12, "sl_failed": 1, "positions_failed": 2, "positions_opened": 13}	2025-09-17 16:01:02.475297+00
2748	main_trader	HEALTHY	t	t	t	\N	15	0	0	\N	{"sl_set": 14, "sl_failed": 1, "positions_failed": 3, "positions_opened": 15}	2025-09-17 16:02:03.897793+00
2749	main_trader	HEALTHY	t	t	t	\N	16	0	0	\N	{"sl_set": 15, "sl_failed": 1, "positions_failed": 3, "positions_opened": 16}	2025-09-17 16:03:05.01227+00
2750	main_trader	HEALTHY	t	t	t	\N	16	0	0	\N	{"sl_set": 15, "sl_failed": 1, "positions_failed": 3, "positions_opened": 16}	2025-09-17 16:04:06.186017+00
2751	main_trader	HEALTHY	t	t	t	\N	16	0	0	\N	{"sl_set": 15, "sl_failed": 1, "positions_failed": 3, "positions_opened": 16}	2025-09-17 16:05:07.309858+00
2752	main_trader	HEALTHY	t	t	t	\N	16	0	0	\N	{"sl_set": 15, "sl_failed": 1, "positions_failed": 3, "positions_opened": 16}	2025-09-17 16:06:08.346623+00
2753	main_trader	HEALTHY	t	t	t	\N	16	0	0	\N	{"sl_set": 15, "sl_failed": 1, "positions_failed": 3, "positions_opened": 16}	2025-09-17 16:07:09.697343+00
2754	main_trader	HEALTHY	t	t	t	\N	16	0	0	\N	{"sl_set": 15, "sl_failed": 1, "positions_failed": 5, "positions_opened": 16}	2025-09-17 16:08:10.829678+00
2755	main_trader	HEALTHY	t	t	t	\N	18	0	0	\N	{"sl_set": 17, "sl_failed": 1, "positions_failed": 5, "positions_opened": 18}	2025-09-17 16:09:11.70787+00
2756	main_trader	HEALTHY	t	t	t	\N	18	0	0	\N	{"sl_set": 17, "sl_failed": 1, "positions_failed": 5, "positions_opened": 18}	2025-09-17 16:10:12.835671+00
2757	main_trader	HEALTHY	t	t	t	\N	18	0	0	\N	{"sl_set": 17, "sl_failed": 1, "positions_failed": 5, "positions_opened": 18}	2025-09-17 16:11:13.881969+00
2758	main_trader	HEALTHY	t	t	t	\N	18	0	0	\N	{"sl_set": 17, "sl_failed": 1, "positions_failed": 5, "positions_opened": 18}	2025-09-17 16:12:15.308981+00
2759	main_trader	HEALTHY	t	t	t	\N	18	0	0	\N	{"sl_set": 17, "sl_failed": 1, "positions_failed": 5, "positions_opened": 18}	2025-09-17 16:13:16.437833+00
2760	main_trader	HEALTHY	t	t	t	\N	18	0	0	\N	{"sl_set": 17, "sl_failed": 1, "positions_failed": 5, "positions_opened": 18}	2025-09-17 16:14:17.471189+00
2761	main_trader	HEALTHY	t	t	t	\N	18	0	0	\N	{"sl_set": 17, "sl_failed": 1, "positions_failed": 5, "positions_opened": 18}	2025-09-17 16:15:18.904731+00
2762	main_trader	HEALTHY	t	t	t	\N	18	0	0	\N	{"sl_set": 17, "sl_failed": 1, "positions_failed": 5, "positions_opened": 18}	2025-09-17 16:16:20.036076+00
2763	main_trader	HEALTHY	t	t	t	\N	18	0	0	\N	{"sl_set": 17, "sl_failed": 1, "positions_failed": 5, "positions_opened": 18}	2025-09-17 16:17:21.385485+00
2764	main_trader	HEALTHY	t	t	t	\N	18	0	0	\N	{"sl_set": 17, "sl_failed": 1, "positions_failed": 5, "positions_opened": 18}	2025-09-17 16:18:23.230887+00
2765	main_trader	HEALTHY	t	t	t	\N	18	0	0	\N	{"sl_set": 17, "sl_failed": 1, "positions_failed": 5, "positions_opened": 18}	2025-09-17 16:19:24.357059+00
2766	main_trader	HEALTHY	t	t	t	\N	18	0	0	\N	{"sl_set": 17, "sl_failed": 1, "positions_failed": 5, "positions_opened": 18}	2025-09-17 16:20:25.499857+00
2767	main_trader	HEALTHY	t	t	t	\N	19	0	0	\N	{"sl_set": 18, "sl_failed": 1, "positions_failed": 5, "positions_opened": 19}	2025-09-17 16:21:26.65506+00
2768	main_trader	HEALTHY	t	t	t	\N	22	0	0	\N	{"sl_set": 21, "sl_failed": 1, "positions_failed": 5, "positions_opened": 22}	2025-09-17 16:22:27.907142+00
2769	main_trader	HEALTHY	t	t	t	\N	25	0	0	\N	{"sl_set": 24, "sl_failed": 1, "positions_failed": 5, "positions_opened": 26}	2025-09-17 16:23:29.140376+00
2770	main_trader	HEALTHY	t	t	t	\N	26	0	0	\N	{"sl_set": 25, "sl_failed": 1, "positions_failed": 5, "positions_opened": 26}	2025-09-17 16:24:30.273357+00
2771	main_trader	HEALTHY	t	t	t	\N	26	0	0	\N	{"sl_set": 25, "sl_failed": 1, "positions_failed": 5, "positions_opened": 26}	2025-09-17 16:25:31.392149+00
2772	main_trader	HEALTHY	t	t	t	\N	26	0	0	\N	{"sl_set": 25, "sl_failed": 1, "positions_failed": 5, "positions_opened": 26}	2025-09-17 16:26:32.547718+00
2773	main_trader	HEALTHY	t	t	t	\N	26	0	0	\N	{"sl_set": 25, "sl_failed": 1, "positions_failed": 5, "positions_opened": 26}	2025-09-17 16:27:34.271238+00
2774	main_trader	HEALTHY	t	t	t	\N	26	0	0	\N	{"sl_set": 25, "sl_failed": 1, "positions_failed": 5, "positions_opened": 26}	2025-09-17 16:28:35.478422+00
2775	main_trader	HEALTHY	t	t	t	\N	26	0	0	\N	{"sl_set": 25, "sl_failed": 1, "positions_failed": 5, "positions_opened": 26}	2025-09-17 16:29:36.593282+00
2776	main_trader	HEALTHY	t	t	t	\N	26	0	0	\N	{"sl_set": 25, "sl_failed": 1, "positions_failed": 5, "positions_opened": 26}	2025-09-17 16:30:37.752857+00
2777	main_trader	HEALTHY	t	t	t	\N	26	0	0	\N	{"sl_set": 25, "sl_failed": 1, "positions_failed": 5, "positions_opened": 26}	2025-09-17 16:31:38.89649+00
2778	main_trader	HEALTHY	t	t	t	\N	26	0	0	\N	{"sl_set": 25, "sl_failed": 1, "positions_failed": 5, "positions_opened": 26}	2025-09-17 16:32:40.258261+00
2779	main_trader	HEALTHY	t	t	t	\N	26	0	0	\N	{"sl_set": 25, "sl_failed": 1, "positions_failed": 5, "positions_opened": 26}	2025-09-17 16:33:41.471797+00
2780	main_trader	HEALTHY	t	t	t	\N	26	0	0	\N	{"sl_set": 25, "sl_failed": 1, "positions_failed": 5, "positions_opened": 26}	2025-09-17 16:34:42.600226+00
2781	main_trader	HEALTHY	t	t	t	\N	26	0	0	\N	{"sl_set": 25, "sl_failed": 1, "positions_failed": 5, "positions_opened": 26}	2025-09-17 16:35:43.722859+00
2782	main_trader	HEALTHY	t	t	t	\N	27	0	0	\N	{"sl_set": 26, "sl_failed": 1, "positions_failed": 6, "positions_opened": 27}	2025-09-17 16:36:44.8405+00
2783	main_trader	HEALTHY	t	t	t	\N	27	0	0	\N	{"sl_set": 26, "sl_failed": 1, "positions_failed": 6, "positions_opened": 27}	2025-09-17 16:37:46.197402+00
2784	main_trader	HEALTHY	t	t	t	\N	27	0	0	\N	{"sl_set": 26, "sl_failed": 1, "positions_failed": 6, "positions_opened": 27}	2025-09-17 16:38:47.317118+00
2785	main_trader	HEALTHY	t	t	t	\N	27	0	0	\N	{"sl_set": 26, "sl_failed": 1, "positions_failed": 6, "positions_opened": 27}	2025-09-17 16:39:48.482404+00
2786	main_trader	HEALTHY	t	t	t	\N	27	0	0	\N	{"sl_set": 26, "sl_failed": 1, "positions_failed": 6, "positions_opened": 27}	2025-09-17 16:40:49.607415+00
2787	main_trader	HEALTHY	t	t	t	\N	27	0	0	\N	{"sl_set": 26, "sl_failed": 1, "positions_failed": 6, "positions_opened": 27}	2025-09-17 16:41:50.769543+00
2788	main_trader	HEALTHY	t	t	t	\N	27	0	0	\N	{"sl_set": 26, "sl_failed": 1, "positions_failed": 6, "positions_opened": 27}	2025-09-17 16:42:52.466923+00
2789	main_trader	HEALTHY	t	t	t	\N	27	0	0	\N	{"sl_set": 26, "sl_failed": 1, "positions_failed": 6, "positions_opened": 27}	2025-09-17 16:43:53.686922+00
2790	main_trader	HEALTHY	t	t	t	\N	27	0	0	\N	{"sl_set": 26, "sl_failed": 1, "positions_failed": 6, "positions_opened": 27}	2025-09-17 16:44:54.729481+00
2791	main_trader	HEALTHY	t	t	t	\N	27	0	0	\N	{"sl_set": 26, "sl_failed": 1, "positions_failed": 6, "positions_opened": 27}	2025-09-17 16:45:55.851877+00
2792	main_trader	HEALTHY	t	t	t	\N	27	0	0	\N	{"sl_set": 26, "sl_failed": 1, "positions_failed": 6, "positions_opened": 27}	2025-09-17 16:46:57.034135+00
2793	main_trader	HEALTHY	t	t	t	\N	27	0	0	\N	{"sl_set": 26, "sl_failed": 1, "positions_failed": 6, "positions_opened": 27}	2025-09-17 16:47:58.389753+00
2794	main_trader	HEALTHY	t	t	t	\N	27	0	0	\N	{"sl_set": 26, "sl_failed": 1, "positions_failed": 6, "positions_opened": 27}	2025-09-17 16:48:59.599554+00
2795	main_trader	HEALTHY	t	t	t	\N	27	0	0	\N	{"sl_set": 26, "sl_failed": 1, "positions_failed": 6, "positions_opened": 27}	2025-09-17 16:50:00.731346+00
2796	main_trader	HEALTHY	t	t	t	\N	27	0	0	\N	{"sl_set": 26, "sl_failed": 1, "positions_failed": 6, "positions_opened": 27}	2025-09-17 16:51:01.861082+00
2797	main_trader	HEALTHY	t	t	t	\N	30	0	0	\N	{"sl_set": 29, "sl_failed": 1, "positions_failed": 6, "positions_opened": 30}	2025-09-17 16:52:02.992284+00
2798	main_trader	HEALTHY	t	t	t	\N	32	0	0	\N	{"sl_set": 31, "sl_failed": 1, "positions_failed": 6, "positions_opened": 32}	2025-09-17 16:53:04.322752+00
2799	main_trader	HEALTHY	t	t	t	\N	32	0	0	\N	{"sl_set": 31, "sl_failed": 1, "positions_failed": 6, "positions_opened": 32}	2025-09-17 16:54:05.520687+00
2800	main_trader	HEALTHY	t	t	t	\N	32	0	0	\N	{"sl_set": 31, "sl_failed": 1, "positions_failed": 6, "positions_opened": 32}	2025-09-17 16:55:06.664975+00
2801	main_trader	HEALTHY	t	t	t	\N	32	0	0	\N	{"sl_set": 31, "sl_failed": 1, "positions_failed": 6, "positions_opened": 32}	2025-09-17 16:56:07.870549+00
2802	main_trader	HEALTHY	t	t	t	\N	32	0	0	\N	{"sl_set": 31, "sl_failed": 1, "positions_failed": 6, "positions_opened": 32}	2025-09-17 16:57:08.914269+00
2803	main_trader	HEALTHY	t	t	t	\N	32	0	0	\N	{"sl_set": 31, "sl_failed": 1, "positions_failed": 6, "positions_opened": 32}	2025-09-17 16:58:10.723096+00
2804	main_trader	HEALTHY	t	t	t	\N	32	0	0	\N	{"sl_set": 31, "sl_failed": 1, "positions_failed": 6, "positions_opened": 32}	2025-09-17 16:59:11.833869+00
2805	main_trader	HEALTHY	t	t	t	\N	32	0	0	\N	{"sl_set": 31, "sl_failed": 1, "positions_failed": 6, "positions_opened": 32}	2025-09-17 17:00:13.006131+00
2806	main_trader	HEALTHY	t	t	t	\N	32	0	0	\N	{"sl_set": 31, "sl_failed": 1, "positions_failed": 6, "positions_opened": 32}	2025-09-17 17:01:14.157317+00
2807	main_trader	HEALTHY	t	t	t	\N	32	0	0	\N	{"sl_set": 31, "sl_failed": 1, "positions_failed": 6, "positions_opened": 32}	2025-09-17 17:02:15.280417+00
2808	main_trader	HEALTHY	t	t	t	\N	32	0	0	\N	{"sl_set": 31, "sl_failed": 1, "positions_failed": 6, "positions_opened": 32}	2025-09-17 17:03:16.547813+00
2809	main_trader	HEALTHY	t	t	t	\N	32	0	0	\N	{"sl_set": 31, "sl_failed": 1, "positions_failed": 6, "positions_opened": 32}	2025-09-17 17:04:18.07185+00
2810	main_trader	HEALTHY	t	t	t	\N	32	0	0	\N	{"sl_set": 31, "sl_failed": 1, "positions_failed": 6, "positions_opened": 32}	2025-09-17 17:05:19.116624+00
2811	main_trader	HEALTHY	t	t	t	\N	32	0	0	\N	{"sl_set": 31, "sl_failed": 1, "positions_failed": 6, "positions_opened": 32}	2025-09-17 17:06:20.257364+00
2812	main_trader	HEALTHY	t	t	t	\N	33	0	0	\N	{"sl_set": 32, "sl_failed": 1, "positions_failed": 6, "positions_opened": 33}	2025-09-17 17:07:22.444759+00
2813	main_trader	HEALTHY	t	t	t	\N	35	0	0	\N	{"sl_set": 34, "sl_failed": 1, "positions_failed": 7, "positions_opened": 35}	2025-09-17 17:08:23.561591+00
2814	main_trader	HEALTHY	t	t	t	\N	38	0	0	\N	{"sl_set": 37, "sl_failed": 1, "positions_failed": 7, "positions_opened": 39}	2025-09-17 17:09:24.605453+00
2815	main_trader	HEALTHY	t	t	t	\N	39	0	0	\N	{"sl_set": 38, "sl_failed": 1, "positions_failed": 9, "positions_opened": 39}	2025-09-17 17:10:25.493491+00
2816	main_trader	HEALTHY	t	t	t	\N	39	0	0	\N	{"sl_set": 38, "sl_failed": 1, "positions_failed": 9, "positions_opened": 39}	2025-09-17 17:11:26.637818+00
2817	main_trader	HEALTHY	t	t	t	\N	39	0	0	\N	{"sl_set": 38, "sl_failed": 1, "positions_failed": 9, "positions_opened": 39}	2025-09-17 17:12:28.229015+00
2818	main_trader	HEALTHY	t	t	t	\N	39	0	0	\N	{"sl_set": 38, "sl_failed": 1, "positions_failed": 9, "positions_opened": 39}	2025-09-17 17:13:29.669926+00
2819	main_trader	HEALTHY	t	t	t	\N	39	0	0	\N	{"sl_set": 38, "sl_failed": 1, "positions_failed": 9, "positions_opened": 39}	2025-09-17 17:14:30.810913+00
2820	main_trader	HEALTHY	t	t	t	\N	39	0	0	\N	{"sl_set": 38, "sl_failed": 1, "positions_failed": 9, "positions_opened": 39}	2025-09-17 17:15:31.84232+00
2821	main_trader	HEALTHY	t	t	t	\N	39	0	0	\N	{"sl_set": 38, "sl_failed": 1, "positions_failed": 9, "positions_opened": 39}	2025-09-17 17:16:32.968001+00
2822	main_trader	HEALTHY	t	t	t	\N	39	0	0	\N	{"sl_set": 38, "sl_failed": 1, "positions_failed": 9, "positions_opened": 39}	2025-09-17 17:17:34.319729+00
2823	main_trader	HEALTHY	t	t	t	\N	39	0	0	\N	{"sl_set": 38, "sl_failed": 1, "positions_failed": 9, "positions_opened": 39}	2025-09-17 17:18:35.527197+00
2824	main_trader	HEALTHY	t	t	t	\N	39	0	0	\N	{"sl_set": 38, "sl_failed": 1, "positions_failed": 9, "positions_opened": 39}	2025-09-17 17:19:36.648303+00
2825	main_trader	HEALTHY	t	t	t	\N	39	0	0	\N	{"sl_set": 38, "sl_failed": 1, "positions_failed": 9, "positions_opened": 39}	2025-09-17 17:20:37.738732+00
2826	main_trader	HEALTHY	t	t	t	\N	40	0	0	\N	{"sl_set": 39, "sl_failed": 1, "positions_failed": 9, "positions_opened": 40}	2025-09-17 17:21:39.278888+00
2827	main_trader	HEALTHY	t	t	t	\N	43	0	0	\N	{"sl_set": 42, "sl_failed": 1, "positions_failed": 9, "positions_opened": 43}	2025-09-17 17:22:40.437017+00
2828	main_trader	HEALTHY	t	t	t	\N	44	0	0	\N	{"sl_set": 43, "sl_failed": 1, "positions_failed": 11, "positions_opened": 44}	2025-09-17 17:23:41.67838+00
2829	main_trader	HEALTHY	t	t	t	\N	45	0	0	\N	{"sl_set": 44, "sl_failed": 1, "positions_failed": 11, "positions_opened": 45}	2025-09-17 17:24:42.864093+00
2830	main_trader	HEALTHY	t	t	t	\N	45	0	0	\N	{"sl_set": 44, "sl_failed": 1, "positions_failed": 11, "positions_opened": 45}	2025-09-17 17:25:43.903377+00
2831	main_trader	HEALTHY	t	t	t	\N	45	0	0	\N	{"sl_set": 44, "sl_failed": 1, "positions_failed": 11, "positions_opened": 45}	2025-09-17 17:26:45.48934+00
2832	main_trader	HEALTHY	t	t	t	\N	45	0	0	\N	{"sl_set": 44, "sl_failed": 1, "positions_failed": 11, "positions_opened": 45}	2025-09-17 17:27:46.620442+00
2833	main_trader	HEALTHY	t	t	t	\N	45	0	0	\N	{"sl_set": 44, "sl_failed": 1, "positions_failed": 11, "positions_opened": 45}	2025-09-17 17:28:47.742646+00
2834	main_trader	HEALTHY	t	t	t	\N	45	0	0	\N	{"sl_set": 44, "sl_failed": 1, "positions_failed": 11, "positions_opened": 45}	2025-09-17 17:29:48.865356+00
2835	main_trader	HEALTHY	t	t	t	\N	45	0	0	\N	{"sl_set": 44, "sl_failed": 1, "positions_failed": 11, "positions_opened": 45}	2025-09-17 17:30:50.02279+00
2836	main_trader	HEALTHY	t	t	t	\N	45	0	0	\N	{"sl_set": 44, "sl_failed": 1, "positions_failed": 11, "positions_opened": 45}	2025-09-17 17:31:51.359842+00
2837	main_trader	HEALTHY	t	t	t	\N	45	0	0	\N	{"sl_set": 44, "sl_failed": 1, "positions_failed": 11, "positions_opened": 45}	2025-09-17 17:32:52.578589+00
2838	main_trader	HEALTHY	t	t	t	\N	45	0	0	\N	{"sl_set": 44, "sl_failed": 1, "positions_failed": 11, "positions_opened": 45}	2025-09-17 17:33:53.698246+00
2839	main_trader	HEALTHY	t	t	t	\N	45	0	0	\N	{"sl_set": 44, "sl_failed": 1, "positions_failed": 11, "positions_opened": 45}	2025-09-17 17:34:54.836883+00
2840	main_trader	HEALTHY	t	t	t	\N	45	0	0	\N	{"sl_set": 44, "sl_failed": 1, "positions_failed": 11, "positions_opened": 45}	2025-09-17 17:35:55.971637+00
2841	main_trader	HEALTHY	t	t	t	\N	48	0	0	\N	{"sl_set": 47, "sl_failed": 1, "positions_failed": 11, "positions_opened": 48}	2025-09-17 17:36:57.469662+00
2842	main_trader	HEALTHY	t	t	t	\N	51	0	0	\N	{"sl_set": 50, "sl_failed": 1, "positions_failed": 11, "positions_opened": 51}	2025-09-17 17:37:58.42321+00
2843	main_trader	HEALTHY	t	t	t	\N	52	0	0	\N	{"sl_set": 50, "sl_failed": 2, "positions_failed": 12, "positions_opened": 52}	2025-09-17 17:38:59.470296+00
2844	main_trader	HEALTHY	t	t	t	\N	53	0	0	\N	{"sl_set": 51, "sl_failed": 2, "positions_failed": 12, "positions_opened": 53}	2025-09-17 17:40:00.538358+00
2845	main_trader	HEALTHY	t	t	t	\N	53	0	0	\N	{"sl_set": 51, "sl_failed": 2, "positions_failed": 12, "positions_opened": 53}	2025-09-17 17:41:01.679724+00
2846	main_trader	HEALTHY	t	t	t	\N	53	0	0	\N	{"sl_set": 51, "sl_failed": 2, "positions_failed": 12, "positions_opened": 53}	2025-09-17 17:42:03.575738+00
2847	main_trader	HEALTHY	t	t	t	\N	53	0	0	\N	{"sl_set": 51, "sl_failed": 2, "positions_failed": 12, "positions_opened": 53}	2025-09-17 17:43:04.777057+00
2848	main_trader	HEALTHY	t	t	t	\N	53	0	0	\N	{"sl_set": 51, "sl_failed": 2, "positions_failed": 12, "positions_opened": 53}	2025-09-17 17:44:05.911618+00
2849	main_trader	HEALTHY	t	t	t	\N	53	0	0	\N	{"sl_set": 51, "sl_failed": 2, "positions_failed": 12, "positions_opened": 53}	2025-09-17 17:45:06.975755+00
2850	main_trader	HEALTHY	t	t	t	\N	53	0	0	\N	{"sl_set": 51, "sl_failed": 2, "positions_failed": 12, "positions_opened": 53}	2025-09-17 17:46:09.227225+00
2851	main_trader	HEALTHY	t	t	t	\N	53	0	0	\N	{"sl_set": 51, "sl_failed": 2, "positions_failed": 12, "positions_opened": 53}	2025-09-17 17:47:10.629742+00
2852	main_trader	HEALTHY	t	t	t	\N	53	0	0	\N	{"sl_set": 51, "sl_failed": 2, "positions_failed": 12, "positions_opened": 53}	2025-09-17 17:48:11.836401+00
2853	main_trader	HEALTHY	t	t	t	\N	53	0	0	\N	{"sl_set": 51, "sl_failed": 2, "positions_failed": 12, "positions_opened": 53}	2025-09-17 17:49:12.973029+00
2854	main_trader	HEALTHY	t	t	t	\N	53	0	0	\N	{"sl_set": 51, "sl_failed": 2, "positions_failed": 12, "positions_opened": 53}	2025-09-17 17:50:14.55226+00
2855	main_trader	HEALTHY	t	t	t	\N	53	0	0	\N	{"sl_set": 51, "sl_failed": 2, "positions_failed": 12, "positions_opened": 54}	2025-09-17 17:51:15.751267+00
2856	main_trader	HEALTHY	t	t	t	\N	55	0	0	\N	{"sl_set": 53, "sl_failed": 2, "positions_failed": 13, "positions_opened": 56}	2025-09-17 17:52:16.86313+00
2857	main_trader	HEALTHY	t	t	t	\N	58	0	0	\N	{"sl_set": 56, "sl_failed": 2, "positions_failed": 13, "positions_opened": 59}	2025-09-17 17:53:17.891605+00
2858	main_trader	HEALTHY	t	t	t	\N	60	0	0	\N	{"sl_set": 58, "sl_failed": 2, "positions_failed": 13, "positions_opened": 60}	2025-09-17 17:54:19.115917+00
2859	main_trader	HEALTHY	t	t	t	\N	60	0	0	\N	{"sl_set": 58, "sl_failed": 2, "positions_failed": 13, "positions_opened": 60}	2025-09-17 17:55:20.505919+00
2860	main_trader	HEALTHY	t	t	t	\N	60	0	0	\N	{"sl_set": 58, "sl_failed": 2, "positions_failed": 13, "positions_opened": 60}	2025-09-17 17:56:21.640478+00
2861	main_trader	HEALTHY	t	t	t	\N	60	0	0	\N	{"sl_set": 58, "sl_failed": 2, "positions_failed": 13, "positions_opened": 60}	2025-09-17 17:57:22.765138+00
2862	main_trader	HEALTHY	t	t	t	\N	60	0	0	\N	{"sl_set": 58, "sl_failed": 2, "positions_failed": 13, "positions_opened": 60}	2025-09-17 17:58:24.803453+00
2863	main_trader	HEALTHY	t	t	t	\N	60	0	0	\N	{"sl_set": 58, "sl_failed": 2, "positions_failed": 13, "positions_opened": 60}	2025-09-17 17:59:26.024786+00
2864	main_trader	HEALTHY	t	t	t	\N	60	0	0	\N	{"sl_set": 58, "sl_failed": 2, "positions_failed": 13, "positions_opened": 60}	2025-09-17 18:00:27.166572+00
2865	main_trader	HEALTHY	t	t	t	\N	60	0	0	\N	{"sl_set": 58, "sl_failed": 2, "positions_failed": 13, "positions_opened": 60}	2025-09-17 18:01:28.549696+00
2866	main_trader	HEALTHY	t	t	t	\N	60	0	0	\N	{"sl_set": 58, "sl_failed": 2, "positions_failed": 13, "positions_opened": 60}	2025-09-17 18:02:29.591449+00
2867	main_trader	HEALTHY	t	t	t	\N	60	0	0	\N	{"sl_set": 58, "sl_failed": 2, "positions_failed": 13, "positions_opened": 60}	2025-09-17 18:03:30.945896+00
2868	main_trader	HEALTHY	t	t	t	\N	60	0	0	\N	{"sl_set": 58, "sl_failed": 2, "positions_failed": 13, "positions_opened": 60}	2025-09-17 18:04:32.15258+00
2869	main_trader	HEALTHY	t	t	t	\N	60	0	0	\N	{"sl_set": 58, "sl_failed": 2, "positions_failed": 13, "positions_opened": 60}	2025-09-17 18:05:34.538598+00
2870	main_trader	HEALTHY	t	t	t	\N	60	0	0	\N	{"sl_set": 58, "sl_failed": 2, "positions_failed": 13, "positions_opened": 60}	2025-09-17 18:06:36.250283+00
2871	main_trader	HEALTHY	t	t	t	\N	62	0	0	\N	{"sl_set": 60, "sl_failed": 2, "positions_failed": 13, "positions_opened": 62}	2025-09-17 18:07:37.347873+00
2872	main_trader	HEALTHY	t	t	t	\N	62	0	0	\N	{"sl_set": 60, "sl_failed": 2, "positions_failed": 13, "positions_opened": 62}	2025-09-17 18:08:38.63616+00
2873	main_trader	HEALTHY	t	t	t	\N	62	0	0	\N	{"sl_set": 60, "sl_failed": 2, "positions_failed": 13, "positions_opened": 62}	2025-09-17 18:09:39.837159+00
2874	main_trader	HEALTHY	t	t	t	\N	62	0	0	\N	{"sl_set": 60, "sl_failed": 2, "positions_failed": 13, "positions_opened": 62}	2025-09-17 18:10:40.968382+00
2875	main_trader	HEALTHY	t	t	t	\N	62	0	0	\N	{"sl_set": 60, "sl_failed": 2, "positions_failed": 13, "positions_opened": 62}	2025-09-17 18:11:42.740684+00
2876	main_trader	HEALTHY	t	t	t	\N	62	0	0	\N	{"sl_set": 60, "sl_failed": 2, "positions_failed": 13, "positions_opened": 62}	2025-09-17 18:12:44.468791+00
2877	main_trader	HEALTHY	t	t	t	\N	62	0	0	\N	{"sl_set": 60, "sl_failed": 2, "positions_failed": 13, "positions_opened": 62}	2025-09-17 18:13:45.591014+00
2878	main_trader	HEALTHY	t	t	t	\N	62	0	0	\N	{"sl_set": 60, "sl_failed": 2, "positions_failed": 13, "positions_opened": 62}	2025-09-17 18:14:46.723016+00
2879	main_trader	HEALTHY	t	t	t	\N	62	0	0	\N	{"sl_set": 60, "sl_failed": 2, "positions_failed": 13, "positions_opened": 62}	2025-09-17 18:15:47.7643+00
2880	main_trader	HEALTHY	t	t	t	\N	62	0	0	\N	{"sl_set": 60, "sl_failed": 2, "positions_failed": 13, "positions_opened": 62}	2025-09-17 18:16:49.126074+00
2881	main_trader	HEALTHY	t	t	t	\N	62	0	0	\N	{"sl_set": 60, "sl_failed": 2, "positions_failed": 13, "positions_opened": 62}	2025-09-17 18:17:50.23509+00
2882	main_trader	HEALTHY	t	t	t	\N	62	0	0	\N	{"sl_set": 60, "sl_failed": 2, "positions_failed": 13, "positions_opened": 62}	2025-09-17 18:18:51.37317+00
2883	main_trader	HEALTHY	t	t	t	\N	62	0	0	\N	{"sl_set": 60, "sl_failed": 2, "positions_failed": 13, "positions_opened": 62}	2025-09-17 18:19:52.507361+00
2884	main_trader	HEALTHY	t	t	t	\N	62	0	0	\N	{"sl_set": 60, "sl_failed": 2, "positions_failed": 13, "positions_opened": 62}	2025-09-17 18:20:53.642399+00
2885	main_trader	HEALTHY	t	t	t	\N	65	0	0	\N	{"sl_set": 63, "sl_failed": 2, "positions_failed": 13, "positions_opened": 65}	2025-09-17 18:21:54.739528+00
2886	main_trader	HEALTHY	t	t	t	\N	66	0	0	\N	{"sl_set": 64, "sl_failed": 2, "positions_failed": 14, "positions_opened": 66}	2025-09-17 18:22:55.947454+00
2887	main_trader	HEALTHY	t	t	t	\N	67	0	0	\N	{"sl_set": 65, "sl_failed": 2, "positions_failed": 15, "positions_opened": 67}	2025-09-17 18:23:58.091414+00
2888	main_trader	HEALTHY	t	t	t	\N	67	0	0	\N	{"sl_set": 65, "sl_failed": 2, "positions_failed": 16, "positions_opened": 67}	2025-09-17 18:25:00.183574+00
2889	main_trader	HEALTHY	t	t	t	\N	67	0	0	\N	{"sl_set": 65, "sl_failed": 2, "positions_failed": 16, "positions_opened": 67}	2025-09-17 18:26:01.240165+00
2890	main_trader	HEALTHY	t	t	t	\N	67	0	0	\N	{"sl_set": 65, "sl_failed": 2, "positions_failed": 16, "positions_opened": 67}	2025-09-17 18:27:02.959031+00
2891	main_trader	HEALTHY	t	t	t	\N	67	0	0	\N	{"sl_set": 65, "sl_failed": 2, "positions_failed": 16, "positions_opened": 67}	2025-09-17 18:28:04.173983+00
2892	main_trader	HEALTHY	t	t	t	\N	67	0	0	\N	{"sl_set": 65, "sl_failed": 2, "positions_failed": 16, "positions_opened": 67}	2025-09-17 18:29:05.330413+00
2893	main_trader	HEALTHY	t	t	t	\N	67	0	0	\N	{"sl_set": 65, "sl_failed": 2, "positions_failed": 16, "positions_opened": 67}	2025-09-17 18:30:06.372661+00
2894	main_trader	HEALTHY	t	t	t	\N	67	0	0	\N	{"sl_set": 65, "sl_failed": 2, "positions_failed": 16, "positions_opened": 67}	2025-09-17 18:31:07.521308+00
2895	main_trader	HEALTHY	t	t	t	\N	67	0	0	\N	{"sl_set": 65, "sl_failed": 2, "positions_failed": 16, "positions_opened": 67}	2025-09-17 18:32:08.874352+00
2896	main_trader	HEALTHY	t	t	t	\N	67	0	0	\N	{"sl_set": 65, "sl_failed": 2, "positions_failed": 16, "positions_opened": 67}	2025-09-17 18:33:09.98216+00
2897	main_trader	HEALTHY	t	t	t	\N	67	0	0	\N	{"sl_set": 65, "sl_failed": 2, "positions_failed": 16, "positions_opened": 67}	2025-09-17 18:34:11.124591+00
2898	main_trader	HEALTHY	t	t	t	\N	67	0	0	\N	{"sl_set": 65, "sl_failed": 2, "positions_failed": 16, "positions_opened": 67}	2025-09-17 18:35:12.198712+00
2899	main_trader	HEALTHY	t	t	t	\N	67	0	0	\N	{"sl_set": 65, "sl_failed": 2, "positions_failed": 16, "positions_opened": 67}	2025-09-17 18:36:13.364991+00
2900	main_trader	HEALTHY	t	t	t	\N	68	0	0	\N	{"sl_set": 67, "sl_failed": 2, "positions_failed": 17, "positions_opened": 69}	2025-09-17 18:37:14.469414+00
2901	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 17, "positions_opened": 70}	2025-09-17 18:38:15.745278+00
2902	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 18:39:16.863638+00
2903	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 18:40:18.013966+00
2904	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 18:41:19.653472+00
2905	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 18:42:20.775902+00
2906	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 18:43:22.035956+00
2907	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 18:44:23.250326+00
2908	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 18:45:24.373723+00
2909	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 18:46:25.426076+00
2910	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 18:47:26.547545+00
2911	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 18:48:27.894868+00
2912	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 18:49:29.09797+00
2913	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 18:50:30.238477+00
2914	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 18:51:31.374714+00
2915	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 18:52:32.420624+00
2916	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 18:53:33.685857+00
2917	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 18:54:35.190966+00
2918	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 18:55:36.236898+00
2919	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 18:56:37.386693+00
2920	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 18:57:38.534691+00
2921	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 18:58:40.77662+00
2922	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 18:59:42.460482+00
2923	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 19:00:43.55481+00
2924	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 19:01:45.41944+00
2925	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 19:02:46.731896+00
2926	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 19:03:49.23782+00
2927	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 19:04:50.504059+00
2928	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 19:05:51.938716+00
2929	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 19:06:53.150832+00
2930	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 19:07:54.437707+00
2931	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 19:08:55.773935+00
2932	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 19:09:56.996473+00
2933	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 19:10:58.182677+00
2934	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 19:11:59.383221+00
2935	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 19:13:00.673782+00
2936	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 19:14:01.875111+00
2937	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 19:15:03.059998+00
2938	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 19:16:04.242278+00
2939	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 19:17:05.307933+00
2940	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 19:18:06.661384+00
2941	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 19:19:07.769865+00
2942	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 19:20:08.917146+00
2943	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 19:21:10.057388+00
2944	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 19:22:11.181527+00
2945	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 19:23:12.559702+00
2946	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 19:24:13.7753+00
2947	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 19:25:15.210326+00
2948	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 19:26:17.333913+00
2949	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 19:27:18.361832+00
2950	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 19:28:19.992789+00
2951	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 19:29:21.225447+00
2952	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 19:30:22.263174+00
2953	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 19:31:23.396871+00
2954	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 19:32:24.584062+00
2955	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 19:33:25.947905+00
2956	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 19:34:27.198372+00
2957	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 19:35:28.339607+00
2958	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 19:36:29.385686+00
2959	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 19:37:30.582094+00
2960	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 19:38:31.932435+00
2961	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 19:39:33.163971+00
2962	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 19:40:34.248359+00
2963	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 19:41:35.384431+00
2964	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 19:42:37.38298+00
2965	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 19:43:38.769645+00
2966	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 19:44:39.874653+00
2967	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 19:45:41.04459+00
2968	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 19:46:42.255327+00
2969	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 19:47:43.292199+00
2970	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 19:48:44.588777+00
2971	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 19:49:45.796017+00
2972	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 19:50:46.984297+00
2973	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 19:51:48.187301+00
2974	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 19:52:49.339426+00
2975	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 19:53:50.422465+00
2976	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 19:54:51.592106+00
2977	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 19:55:52.774066+00
2978	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 19:56:54.178861+00
2979	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 19:57:55.393674+00
2980	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 19:58:56.947236+00
2981	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 19:59:58.119939+00
2982	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 20:00:59.171441+00
2983	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 20:02:00.531692+00
2984	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 20:03:01.768968+00
2985	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 20:04:02.861666+00
2986	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 20:05:04.050197+00
2987	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 20:06:05.10731+00
2988	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 20:07:06.458905+00
2989	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 20:08:07.597228+00
2990	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 20:09:08.996745+00
2991	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 20:10:10.09381+00
2992	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 20:11:11.263326+00
2993	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 20:12:12.601417+00
2994	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 20:13:13.707593+00
2995	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 20:14:14.864338+00
2996	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 20:15:15.993418+00
2997	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 20:16:17.038132+00
2998	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 20:17:18.329186+00
2999	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 20:18:19.447377+00
3000	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 20:19:20.61313+00
3001	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 20:20:21.730267+00
3002	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 20:21:22.793366+00
3003	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 20:22:24.042452+00
3004	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 20:23:25.23056+00
3005	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 20:24:26.258526+00
3006	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 20:25:27.423646+00
3007	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 20:26:28.603331+00
3008	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 20:27:29.995448+00
3009	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 20:28:31.532381+00
3010	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 20:29:32.712435+00
3011	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 20:30:33.877959+00
3012	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 20:31:34.998482+00
3013	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 20:32:36.578469+00
3014	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 20:33:37.677704+00
3015	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 20:34:38.802316+00
3016	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 20:35:39.93148+00
3017	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 20:36:41.095441+00
3018	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 20:37:42.399985+00
3019	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 20:38:43.635207+00
3020	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 20:39:45.160279+00
3021	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 20:40:46.229864+00
3022	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 20:41:47.36975+00
3023	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 20:42:48.613402+00
3024	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 20:43:49.715954+00
3025	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 20:44:50.784046+00
3026	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 20:45:51.93947+00
3027	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 20:46:52.978268+00
3028	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 20:47:54.248241+00
3029	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 20:48:55.34185+00
3030	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 20:49:56.470598+00
3031	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 20:50:57.577074+00
3032	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 20:51:58.6212+00
3033	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 20:52:59.883349+00
3034	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 20:54:01.52326+00
3035	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 20:55:02.567415+00
3036	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 20:56:03.714585+00
3037	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 20:57:04.85533+00
3038	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 20:58:06.242016+00
3039	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 20:59:07.351065+00
3040	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 21:00:08.363721+00
3041	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 21:01:09.461625+00
3042	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 21:02:10.532456+00
3043	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 21:03:11.800261+00
3044	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 21:04:12.978963+00
3045	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 21:05:14.13245+00
3046	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 21:06:15.188093+00
3047	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 21:07:16.23355+00
3048	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 21:08:17.625948+00
3049	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 21:09:18.755381+00
3050	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 21:10:19.814035+00
3051	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 21:11:20.944364+00
3052	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 21:12:22.095819+00
3053	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 21:13:23.467214+00
3054	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 21:14:24.960698+00
3055	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 21:15:26.11077+00
3056	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 21:16:27.161443+00
3057	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 21:17:28.225557+00
3058	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 21:18:29.729564+00
3059	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 21:19:30.82959+00
3060	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 21:20:31.934352+00
3061	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 21:21:32.996255+00
3062	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 21:22:34.044554+00
3063	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 21:23:35.422987+00
3064	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 21:24:36.593841+00
3065	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 21:25:38.131171+00
3066	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 21:26:39.25822+00
3067	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 21:27:40.419637+00
3068	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 21:28:41.453423+00
3069	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 21:29:42.789646+00
3070	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 21:30:43.976589+00
3071	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 21:31:45.017179+00
3072	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 21:32:46.04667+00
3073	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 21:33:47.074922+00
3074	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 21:34:48.44228+00
3075	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 21:35:49.533552+00
3076	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 21:36:50.601949+00
3077	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 21:37:51.718561+00
3078	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 21:38:52.791203+00
3079	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 21:39:54.082782+00
3080	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 21:40:55.185263+00
3081	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 21:41:56.244895+00
3082	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 21:42:57.268546+00
3083	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 21:43:58.288624+00
3084	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 21:44:59.566365+00
3085	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 21:46:00.796633+00
3086	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 21:47:02.668538+00
3087	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 21:48:04.009561+00
3088	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 21:49:05.136002+00
3089	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 21:50:06.500579+00
3090	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 21:51:07.634864+00
3091	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 21:52:08.706215+00
3092	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 21:53:09.836344+00
3093	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 21:54:10.962301+00
3094	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 21:55:12.28775+00
3095	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 21:56:13.382648+00
3096	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 21:57:14.453884+00
3097	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 21:58:15.705755+00
3098	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 21:59:16.730045+00
3099	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 22:00:18.020023+00
3100	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 22:01:19.251771+00
3101	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 22:02:20.405567+00
3102	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 22:03:21.573753+00
3103	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 22:04:22.644124+00
3104	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 22:05:24.027117+00
3105	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 22:06:25.213372+00
3106	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 22:07:26.564948+00
3107	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 22:08:27.630185+00
3108	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 22:09:28.79596+00
3109	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 22:10:30.047377+00
3110	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 22:11:31.862769+00
3111	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 22:12:33.006211+00
3112	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 22:13:34.047795+00
3113	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 22:14:35.174821+00
3114	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 22:15:36.303978+00
3115	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 22:16:37.581879+00
3116	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 22:17:38.766774+00
3117	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 22:18:39.922739+00
3118	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 22:19:41.045912+00
3119	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 22:20:42.174476+00
3120	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 22:21:43.569021+00
3121	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 22:22:44.828374+00
3122	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 22:23:45.889985+00
3123	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 22:24:47.0452+00
3124	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 22:25:48.087741+00
3125	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 22:26:50.461011+00
3126	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 22:27:52.369704+00
3127	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 22:28:53.745109+00
3128	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 22:29:55.601561+00
3129	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 22:30:57.436439+00
3130	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 22:31:59.61528+00
3131	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 22:33:01.074166+00
3132	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 22:34:02.483573+00
3133	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 22:35:03.858253+00
3134	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 22:36:04.96579+00
3135	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 22:37:07.088864+00
3136	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 22:38:08.9833+00
3137	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 22:39:10.585498+00
3138	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 22:40:12.191886+00
3139	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 22:41:13.257253+00
3140	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 22:42:15.077586+00
3141	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 22:43:16.702157+00
3142	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 22:44:18.305777+00
3143	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 22:45:19.43285+00
3144	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 22:46:20.945056+00
3145	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 22:47:22.611605+00
3146	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 22:48:24.565433+00
3147	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 22:49:26.48714+00
3148	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 22:50:28.359233+00
3149	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 22:51:29.874156+00
3150	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 22:52:31.708041+00
3151	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 22:53:33.377426+00
3152	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 22:54:34.884416+00
3153	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 22:55:36.486964+00
3154	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 22:56:37.986833+00
3155	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 22:57:39.718774+00
3156	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 22:58:41.407686+00
3157	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 22:59:43.240561+00
3158	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 23:00:44.751536+00
3159	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 23:01:46.66982+00
3160	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 23:02:48.398768+00
3161	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 23:03:50.007851+00
3162	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 23:04:51.65154+00
3163	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 23:05:53.035857+00
3164	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 23:06:54.645264+00
3165	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 23:07:56.469549+00
3166	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 23:08:58.101007+00
3167	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 23:09:59.605632+00
3168	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 23:11:00.975648+00
3169	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 23:12:03.107752+00
3170	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 23:13:04.324227+00
3171	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 23:14:05.706369+00
3172	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 23:15:06.756984+00
3173	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 23:16:08.124213+00
3174	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 23:17:09.752329+00
3175	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 23:18:10.910395+00
3176	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 23:19:12.360074+00
3177	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 23:20:13.529327+00
3178	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 23:21:14.994286+00
3179	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 23:22:16.56984+00
3180	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 23:23:18.003287+00
3181	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 23:24:19.370594+00
3182	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 23:25:20.882489+00
3183	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 23:26:22.016297+00
3184	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 23:27:23.70816+00
3185	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 23:28:25.149178+00
3186	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 23:29:26.607078+00
3187	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 23:30:27.968446+00
3188	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 23:31:29.438032+00
3189	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 23:32:31.151316+00
3190	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 23:33:32.632418+00
3191	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 23:34:34.096735+00
3192	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 23:35:35.558163+00
3193	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 23:36:36.696974+00
3194	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 23:37:38.321566+00
3195	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 23:38:39.839037+00
3196	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 23:39:41.27795+00
3197	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 23:40:42.637429+00
3198	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 23:41:44.003984+00
3199	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 23:42:45.300693+00
3200	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 23:43:46.745298+00
3201	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 23:44:48.089807+00
3202	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 23:45:49.467023+00
3203	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 23:46:50.920338+00
3204	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 23:47:52.394809+00
3205	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 23:48:53.839378+00
3206	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 23:49:55.243729+00
3207	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 23:50:56.699952+00
3208	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 23:51:58.101529+00
3209	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 23:52:59.539475+00
3210	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 23:54:01.072651+00
3211	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 23:55:02.587791+00
3212	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 23:56:04.094679+00
3213	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 23:57:05.199718+00
3214	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 23:58:06.826285+00
3215	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-17 23:59:08.257862+00
3216	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 00:00:09.673048+00
3217	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 00:01:11.20486+00
3218	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 00:02:12.378768+00
3219	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 00:03:14.462448+00
3220	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 00:04:15.902569+00
3221	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 00:05:17.352024+00
3222	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 00:06:18.39183+00
3223	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 00:07:19.529181+00
3224	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 00:08:21.12178+00
3225	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 00:09:22.281327+00
3226	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 00:10:23.354207+00
3227	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 00:11:24.394789+00
3228	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 00:12:25.435725+00
3229	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 00:13:27.027265+00
3230	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 00:14:28.137468+00
3231	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 00:15:29.169791+00
3232	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 00:16:30.261803+00
3233	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 00:17:31.36767+00
3234	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 00:18:32.987378+00
3235	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 00:19:34.240887+00
3236	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 00:20:35.281474+00
3237	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 00:21:36.448677+00
3238	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 00:22:37.6234+00
3239	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 00:23:39.213613+00
3240	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 00:24:40.42715+00
3241	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 00:25:41.686831+00
3242	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 00:26:42.887946+00
3243	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 00:27:45.009716+00
3244	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 00:28:46.086941+00
3245	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 00:29:47.112238+00
3246	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 00:30:48.400196+00
3247	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 00:31:49.500129+00
3248	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 00:32:50.60235+00
3249	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 00:33:52.004988+00
3250	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 00:34:53.440541+00
3251	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 00:35:54.734619+00
3252	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 00:36:55.833969+00
3253	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 00:37:56.915027+00
3254	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 00:38:58.397744+00
3255	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 00:39:59.429478+00
3256	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 00:41:00.735814+00
3257	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 00:42:02.250471+00
3258	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 00:43:03.414651+00
3259	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 00:44:04.459577+00
3260	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 00:45:05.610023+00
3261	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 00:46:07.219567+00
3262	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 00:47:08.327546+00
3263	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 00:48:09.731697+00
3264	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 00:49:10.892957+00
3265	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 00:50:11.949918+00
3266	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 00:51:13.277908+00
3267	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 00:52:14.697311+00
3268	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 00:53:15.736689+00
3269	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 00:54:17.129806+00
3270	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 00:55:18.467635+00
3271	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 00:56:19.728466+00
3272	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 00:57:20.92871+00
3273	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 00:58:21.97002+00
3274	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 00:59:23.027802+00
3275	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 01:00:24.069092+00
3276	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 01:01:25.648431+00
3277	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 01:02:26.857912+00
3278	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 01:03:28.211392+00
3279	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 01:04:29.253434+00
3280	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 01:05:30.622784+00
3281	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 01:06:32.22555+00
3282	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 01:07:33.669636+00
3283	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 01:08:35.030794+00
3284	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 01:09:36.48512+00
3285	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 01:10:37.803008+00
3286	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 01:11:39.121692+00
3287	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 01:12:40.220656+00
3288	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 01:13:41.683674+00
3289	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 01:14:42.711155+00
3290	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 01:15:43.72081+00
3291	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 01:16:44.965856+00
3292	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 01:17:46.159401+00
3293	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 01:18:47.199823+00
3294	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 01:19:48.306363+00
3295	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 01:20:49.43255+00
3296	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 01:21:51.808593+00
3297	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 01:22:53.553859+00
3298	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 01:23:54.585627+00
3299	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 01:24:55.619457+00
3300	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 01:25:56.667147+00
3301	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 01:26:58.02253+00
3302	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 01:27:59.122777+00
3303	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 01:29:00.274335+00
3304	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 01:30:01.315581+00
3305	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 01:31:02.354686+00
3306	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 01:32:04.003207+00
3307	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 01:33:05.134196+00
3308	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 01:34:06.280201+00
3309	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 01:35:07.316941+00
3310	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 01:36:08.350204+00
3311	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 01:37:09.596005+00
3312	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 01:38:10.815017+00
3313	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 01:39:11.938302+00
3314	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 01:40:12.975557+00
3315	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 01:41:14.012414+00
3316	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 01:42:15.262484+00
3317	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 01:43:16.353935+00
3318	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 01:44:17.381543+00
3319	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 01:45:18.407161+00
3320	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 01:46:19.548645+00
3321	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 01:47:20.808075+00
3322	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 01:48:21.921477+00
3323	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 01:49:22.967661+00
3324	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 01:50:24.008453+00
3325	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 01:51:25.032063+00
3326	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 01:52:26.38968+00
3327	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 01:53:27.554941+00
3328	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 01:54:28.771889+00
3329	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 01:55:30.101621+00
3330	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 01:56:31.13159+00
3331	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 01:57:32.509087+00
3332	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 01:58:33.615666+00
3333	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 01:59:34.635645+00
3334	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 02:00:35.671719+00
3335	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 02:01:36.714013+00
3336	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 02:02:37.973143+00
3337	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 02:03:39.082359+00
3338	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 02:04:40.210597+00
3339	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 02:05:41.336596+00
3340	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 02:06:42.382936+00
3341	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 02:07:43.630342+00
3342	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 02:08:44.881321+00
3343	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 02:09:45.912668+00
3344	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 02:10:47.267669+00
3345	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 02:11:48.381564+00
3346	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 02:12:49.740239+00
3347	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 02:13:50.949486+00
3348	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 02:14:51.998963+00
3349	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 02:15:53.100067+00
3350	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 02:16:54.221994+00
3351	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 02:17:55.490659+00
3352	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 02:18:56.622595+00
3353	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 02:19:57.671929+00
3354	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 02:20:58.717727+00
3355	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 02:21:59.845911+00
3356	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 02:23:01.555945+00
3357	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 02:24:02.678359+00
3358	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 02:25:03.71154+00
3359	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 02:26:04.838139+00
3360	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 02:27:05.889438+00
3361	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 02:28:07.157817+00
3362	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 02:29:08.366463+00
3363	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 02:30:09.49021+00
3364	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 02:31:10.545976+00
3365	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 02:32:11.66425+00
3366	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 02:33:13.020807+00
3367	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 02:34:14.695731+00
3368	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 02:35:16.007797+00
3369	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 02:36:17.064375+00
3370	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 02:37:18.107617+00
3371	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 02:38:19.347552+00
3372	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 02:39:20.457346+00
3373	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 02:40:22.105789+00
3374	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 02:41:23.219093+00
3375	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 02:42:24.357712+00
3376	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 02:43:25.469093+00
3377	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 02:44:26.572455+00
3378	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 02:45:27.876857+00
3379	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 02:46:29.288803+00
3380	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 02:47:30.341178+00
3381	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 02:48:31.365957+00
3382	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 02:49:32.51303+00
3383	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 02:50:33.89825+00
3384	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 02:51:35.022833+00
3385	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 02:52:36.16479+00
3386	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 02:53:37.192613+00
3387	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 02:54:38.267335+00
3388	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 02:55:39.527384+00
3389	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 02:56:40.653447+00
3390	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 02:57:41.686253+00
3391	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 02:58:43.08065+00
3392	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 02:59:44.222393+00
3393	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 03:00:45.618305+00
3394	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 03:01:46.824659+00
3395	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 03:02:47.879949+00
3396	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 03:03:49.868576+00
3397	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 03:04:50.927169+00
3398	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 03:05:52.235011+00
3399	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 03:06:53.35767+00
3400	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 03:07:54.490389+00
3401	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 03:08:55.544495+00
3402	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 03:09:56.692289+00
3403	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 03:10:58.071768+00
3404	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 03:11:59.335141+00
3405	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 03:13:00.481674+00
3406	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 03:14:01.52418+00
3407	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 03:15:02.583862+00
3408	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 03:16:03.858925+00
3409	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 03:17:05.038229+00
3410	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 03:18:06.185199+00
3411	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 03:19:07.323977+00
3412	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 03:20:08.394546+00
3413	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 03:21:09.765723+00
3414	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 03:22:10.994825+00
3415	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 03:23:12.089861+00
3416	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 03:24:13.229972+00
3417	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 03:25:14.365948+00
3418	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 03:26:15.748938+00
3419	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 03:27:16.979232+00
3420	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 03:28:18.280931+00
3421	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 03:29:19.321583+00
3422	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 03:30:20.436336+00
3423	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 03:31:21.722313+00
3424	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 03:32:22.814562+00
3425	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 03:33:23.968301+00
3426	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 03:34:25.022823+00
3427	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 03:35:26.378269+00
3428	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 03:36:27.640432+00
3429	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 03:37:28.770208+00
3430	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 03:38:29.82656+00
3431	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 03:39:30.870559+00
3432	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 03:40:31.972424+00
3433	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 03:41:33.271598+00
3434	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 03:42:34.772066+00
3435	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 03:43:35.832053+00
3436	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 03:44:36.895647+00
3437	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 03:45:37.922721+00
3438	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 03:46:39.1768+00
3439	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 03:47:40.388854+00
3440	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 03:48:41.581501+00
3441	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 03:49:42.603464+00
3442	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 03:50:43.73688+00
3443	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 03:51:45.164749+00
3444	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 03:52:46.592657+00
3445	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 03:53:47.727262+00
3446	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 03:54:48.838064+00
3447	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 03:55:50.672446+00
3448	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 03:56:51.966076+00
3449	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 03:57:53.187437+00
3450	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 03:58:54.208991+00
3451	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 03:59:55.407679+00
3452	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 04:00:56.462147+00
3453	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 04:01:57.735881+00
3454	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 04:02:59.008434+00
3455	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 04:04:00.091411+00
3456	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 04:05:01.24947+00
3457	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 04:06:02.374499+00
3458	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 04:07:03.65801+00
3459	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 04:08:04.806474+00
3460	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 04:09:05.928392+00
3461	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 04:10:06.962624+00
3462	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 04:11:08.086884+00
3463	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 04:12:09.661281+00
3464	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 04:13:11.41131+00
3465	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 04:14:12.575557+00
3466	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 04:15:13.640551+00
3467	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 04:16:14.705987+00
3468	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 04:17:15.731029+00
3469	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 04:18:17.005267+00
3470	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 04:19:18.096573+00
3471	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 04:20:19.246994+00
3472	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 04:21:20.31591+00
3473	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 04:22:21.353578+00
3474	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 04:23:22.615885+00
3475	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 04:24:23.743099+00
3476	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 04:25:24.945018+00
3477	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 04:26:26.268311+00
3478	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 04:27:27.314233+00
3479	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 04:28:28.61774+00
3480	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 04:29:29.82958+00
3481	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 04:30:30.945115+00
3482	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 04:31:32.080081+00
3483	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 04:32:33.136402+00
3484	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 04:33:34.406335+00
3485	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 04:34:35.509562+00
3486	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 04:35:36.558851+00
3487	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 04:36:37.697212+00
3488	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 04:37:38.861638+00
3489	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 04:38:40.165333+00
3490	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 04:39:41.292924+00
3491	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 04:40:42.443767+00
3492	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 04:41:43.613271+00
3493	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 04:42:44.795826+00
3494	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 04:43:46.173027+00
3495	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 04:44:47.295268+00
3496	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 04:45:48.343596+00
3497	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 04:46:49.424717+00
3498	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 04:47:50.471261+00
3499	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 04:48:51.868948+00
3500	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 04:49:53.101446+00
3501	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 04:50:54.267503+00
3502	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 04:51:55.330468+00
3503	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 04:52:56.379728+00
3504	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 04:53:57.675437+00
3505	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 04:54:58.79044+00
3506	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 04:55:59.827204+00
3507	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 04:57:00.978947+00
3508	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 04:58:02.085132+00
3509	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 04:59:03.526547+00
3510	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 05:00:04.632955+00
3511	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 05:01:05.694362+00
3512	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 05:02:06.726842+00
3513	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 05:03:07.831715+00
3514	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 05:04:09.211231+00
3515	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 05:05:10.355035+00
3516	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 05:06:11.49928+00
3517	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 05:07:12.567572+00
3518	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 05:08:13.628534+00
3519	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 05:09:14.895973+00
3520	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 05:10:16.476545+00
3521	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 05:11:17.523076+00
3522	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 05:12:18.568168+00
3523	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 05:13:19.650988+00
3524	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 05:14:20.910271+00
3525	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 05:15:22.024301+00
3526	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 05:16:23.464443+00
3527	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 05:17:24.670954+00
3528	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 05:18:25.736993+00
3529	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 05:19:26.98444+00
3530	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 05:20:28.109059+00
3531	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 05:21:29.276235+00
3532	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 05:22:30.355141+00
3533	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 05:23:31.547427+00
3534	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 05:24:32.909654+00
3535	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 05:25:34.05626+00
3536	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 05:26:35.186997+00
3537	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 05:27:36.335542+00
3538	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 05:28:37.457011+00
3539	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 05:29:38.730133+00
3540	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 05:30:40.012134+00
3541	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 05:31:41.440715+00
3542	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 05:32:42.486325+00
3543	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 05:33:43.523781+00
3544	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 05:34:44.827091+00
3545	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 05:35:46.527726+00
3546	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 05:36:47.579094+00
3547	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 05:37:48.626118+00
3548	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 05:38:49.649942+00
3549	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 05:39:51.017302+00
3550	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 05:40:52.158795+00
3551	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 05:41:53.724196+00
3552	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 05:42:54.840003+00
3553	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 05:43:55.991649+00
3554	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 05:44:57.301715+00
3555	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 05:45:58.444975+00
3556	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 05:46:59.62614+00
3557	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 05:48:01.140184+00
3558	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 05:49:02.360097+00
3559	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 05:50:03.575442+00
3560	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 05:51:04.738+00
3561	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 05:52:05.816455+00
3562	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 05:53:06.856309+00
3563	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 05:54:08.109683+00
3564	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 05:55:09.236714+00
3565	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 05:56:10.268328+00
3566	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 05:57:11.337654+00
3567	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 05:58:12.374925+00
3568	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 05:59:13.734586+00
3569	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 06:00:14.863929+00
3570	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 06:01:15.917189+00
3571	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 06:02:17.066627+00
3572	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 06:03:18.120599+00
3573	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 06:04:19.493058+00
3574	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 06:05:20.698363+00
3575	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 06:06:21.741378+00
3576	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 06:07:22.866753+00
3577	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 06:08:24.007238+00
3578	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 06:09:25.28387+00
3579	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 06:10:26.499018+00
3580	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 06:11:27.627362+00
3581	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 06:12:28.680437+00
3582	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 06:13:30.311499+00
3583	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 06:14:32.099058+00
3584	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 06:15:33.741457+00
3585	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 06:16:35.296653+00
3586	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 06:17:36.894971+00
3587	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 06:18:38.468594+00
3588	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 06:19:40.226633+00
3589	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 06:20:41.840891+00
3590	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 06:21:43.378753+00
3591	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 06:22:45.068469+00
3592	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 06:23:47.011485+00
3593	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 06:24:48.811333+00
3594	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 06:25:50.444716+00
3595	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 06:26:52.730466+00
3596	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 06:27:54.374687+00
3597	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 06:28:56.141966+00
3598	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 06:29:57.779845+00
3599	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 06:30:59.421949+00
3600	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 06:32:01.641015+00
3601	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 06:33:02.809982+00
3602	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 06:34:04.46604+00
3603	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 06:35:06.068754+00
3604	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 06:36:07.64232+00
3605	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 06:37:09.52755+00
3606	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 06:38:11.26728+00
3607	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 06:39:12.942227+00
3608	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 06:40:14.524631+00
3609	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 06:41:16.393851+00
3610	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 06:42:18.458495+00
3611	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 06:43:20.17667+00
3612	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 06:44:21.736492+00
3613	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 06:45:22.842721+00
3614	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 06:46:24.468388+00
3615	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 06:47:26.370361+00
3616	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 06:48:28.108752+00
3617	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 06:49:29.682565+00
3618	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 06:50:31.243526+00
3619	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 06:51:32.787346+00
3620	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 06:52:34.563576+00
3621	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 06:53:36.181004+00
3622	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 06:54:37.768757+00
3623	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 06:55:39.325748+00
3624	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 06:56:40.873459+00
3625	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 06:57:42.50648+00
3626	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 06:58:44.160809+00
3627	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 06:59:45.701896+00
3628	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 07:00:46.819651+00
3629	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 07:01:48.367322+00
3630	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 07:02:50.080792+00
3631	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 07:03:51.72536+00
3632	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 07:04:53.284907+00
3633	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 07:05:54.954477+00
3634	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 07:06:55.987748+00
3635	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 07:07:57.352892+00
3636	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 07:08:58.481886+00
3637	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 07:09:59.660903+00
3638	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 07:11:00.715159+00
3639	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 07:12:01.768375+00
3640	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 07:13:03.040845+00
3641	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 07:14:04.447336+00
3642	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 07:15:05.498086+00
3643	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 07:16:06.624114+00
3644	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 07:17:07.689612+00
3645	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 07:18:08.962773+00
3646	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 07:19:10.226653+00
3647	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 07:20:11.308426+00
3648	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 07:21:12.343744+00
3649	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 07:22:13.393639+00
3650	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 07:23:14.646552+00
3651	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 07:24:15.778051+00
3652	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 07:25:17.648724+00
3653	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 07:26:18.774832+00
3654	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 07:27:19.915796+00
3655	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 07:28:21.321423+00
3656	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 07:29:22.427645+00
3657	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 07:30:23.535235+00
3658	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 07:31:24.662417+00
3659	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 07:32:25.789861+00
3660	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 07:33:27.142011+00
3661	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 07:34:28.339719+00
3662	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 07:35:29.401291+00
3663	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 07:36:30.551758+00
3664	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 07:37:31.639633+00
3665	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 07:38:32.814901+00
3666	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 07:39:34.108288+00
3667	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 07:40:35.22982+00
3668	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 07:41:36.64657+00
3669	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 07:42:37.710043+00
3670	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 07:43:39.058238+00
3671	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 07:44:40.306347+00
3672	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 07:45:41.420392+00
3673	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 07:46:42.448983+00
3674	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 07:47:43.477916+00
3675	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 07:48:44.581209+00
3676	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 07:49:45.921451+00
3677	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 07:50:47.425789+00
3678	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 07:51:49.14964+00
3679	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 07:52:50.231965+00
3680	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 07:53:51.265132+00
3681	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 07:54:52.676432+00
3682	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 07:55:53.800889+00
3683	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 07:56:55.777712+00
3684	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 07:57:56.95168+00
3685	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 07:58:58.005913+00
3686	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 07:59:59.35655+00
3687	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 08:01:00.48485+00
3688	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 08:02:02.001564+00
3689	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 08:03:03.073478+00
3690	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 08:04:04.6079+00
3691	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 08:05:06.354981+00
3692	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 08:06:07.990136+00
3693	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 08:07:09.662914+00
3694	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 08:08:10.814728+00
3695	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 08:09:12.372357+00
3696	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 08:10:14.12839+00
3697	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 08:11:15.807565+00
3698	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 08:12:16.912846+00
3699	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 08:13:18.438892+00
3700	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 08:14:20.062235+00
3701	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 08:15:21.864418+00
3702	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 08:16:23.07085+00
3703	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 08:17:24.758471+00
3704	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 08:18:25.94486+00
3705	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 08:19:27.47915+00
3706	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 08:20:29.345728+00
3707	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 08:21:31.016568+00
3708	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 08:22:32.646731+00
3709	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 08:23:34.252777+00
3710	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 08:24:35.859227+00
3711	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 08:25:37.747318+00
3712	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 08:26:39.348154+00
3713	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 08:27:40.965023+00
3714	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 08:28:42.108097+00
3715	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 08:29:46.901018+00
3716	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 08:30:48.254542+00
3717	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 08:31:49.36286+00
3718	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 08:32:52.961826+00
3719	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 08:33:54.405562+00
3720	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 08:34:55.42976+00
3721	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 08:35:56.732598+00
3722	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 08:36:57.84112+00
3723	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 08:37:58.859637+00
3724	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 08:39:00.403998+00
3725	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 08:40:01.99724+00
3726	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 08:41:03.870102+00
3727	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 08:42:05.490152+00
3728	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 08:43:07.011233+00
3729	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 08:44:08.555457+00
3730	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 08:45:10.096146+00
3731	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 08:46:11.230026+00
3732	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 08:47:12.837587+00
3733	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 08:48:14.464465+00
3734	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 08:49:15.523258+00
3735	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 08:50:16.603693+00
3736	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 08:51:18.373396+00
3737	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 08:52:20.092578+00
3738	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 08:53:21.645207+00
3739	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 08:54:22.708337+00
3740	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 08:55:24.351725+00
3741	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 08:56:25.765769+00
3742	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 08:57:27.383572+00
3743	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 08:58:29.039439+00
3744	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 08:59:30.555746+00
3745	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 09:00:32.220007+00
3746	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 09:01:33.987068+00
3747	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 09:02:35.623296+00
3748	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 09:03:36.776544+00
3749	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 09:04:37.972661+00
3750	main_trader	HEALTHY	t	t	t	\N	70	0	0	\N	{"sl_set": 69, "sl_failed": 2, "positions_failed": 18, "positions_opened": 70}	2025-09-18 09:05:39.612056+00
3751	main_trader	HEALTHY	t	t	t	\N	71	0	0	\N	{"sl_set": 70, "sl_failed": 2, "positions_failed": 19, "positions_opened": 71}	2025-09-18 09:06:41.20889+00
3752	main_trader	HEALTHY	t	t	t	\N	72	0	0	\N	{"sl_set": 71, "sl_failed": 2, "positions_failed": 20, "positions_opened": 72}	2025-09-18 09:07:42.62312+00
3753	main_trader	HEALTHY	t	t	t	\N	74	0	0	\N	{"sl_set": 73, "sl_failed": 2, "positions_failed": 21, "positions_opened": 74}	2025-09-18 09:08:43.774626+00
3754	main_trader	HEALTHY	t	t	t	\N	75	0	0	\N	{"sl_set": 74, "sl_failed": 2, "positions_failed": 23, "positions_opened": 75}	2025-09-18 09:09:45.403632+00
3755	main_trader	HEALTHY	t	t	t	\N	77	0	0	\N	{"sl_set": 76, "sl_failed": 2, "positions_failed": 23, "positions_opened": 77}	2025-09-18 09:10:46.308999+00
3756	main_trader	HEALTHY	t	t	t	\N	79	0	0	\N	{"sl_set": 78, "sl_failed": 2, "positions_failed": 23, "positions_opened": 79}	2025-09-18 09:11:48.300343+00
3757	main_trader	HEALTHY	t	t	t	\N	80	0	0	\N	{"sl_set": 79, "sl_failed": 2, "positions_failed": 24, "positions_opened": 80}	2025-09-18 09:12:49.786342+00
3758	main_trader	HEALTHY	t	t	t	\N	82	0	0	\N	{"sl_set": 81, "sl_failed": 2, "positions_failed": 24, "positions_opened": 82}	2025-09-18 09:13:51.337802+00
3759	main_trader	HEALTHY	t	t	t	\N	83	0	0	\N	{"sl_set": 82, "sl_failed": 2, "positions_failed": 24, "positions_opened": 83}	2025-09-18 09:14:53.222617+00
3760	main_trader	HEALTHY	t	t	t	\N	83	0	0	\N	{"sl_set": 82, "sl_failed": 2, "positions_failed": 24, "positions_opened": 83}	2025-09-18 09:15:55.210964+00
3761	main_trader	HEALTHY	t	t	t	\N	83	0	0	\N	{"sl_set": 82, "sl_failed": 2, "positions_failed": 24, "positions_opened": 83}	2025-09-18 09:16:57.419845+00
3762	main_trader	HEALTHY	t	t	t	\N	83	0	0	\N	{"sl_set": 82, "sl_failed": 2, "positions_failed": 24, "positions_opened": 83}	2025-09-18 09:17:59.378575+00
3763	main_trader	HEALTHY	t	t	t	\N	83	0	0	\N	{"sl_set": 82, "sl_failed": 2, "positions_failed": 24, "positions_opened": 83}	2025-09-18 09:19:00.917847+00
3764	main_trader	HEALTHY	t	t	t	\N	83	0	0	\N	{"sl_set": 82, "sl_failed": 2, "positions_failed": 24, "positions_opened": 83}	2025-09-18 09:20:01.99529+00
3765	main_trader	HEALTHY	t	t	t	\N	83	0	0	\N	{"sl_set": 82, "sl_failed": 2, "positions_failed": 24, "positions_opened": 83}	2025-09-18 09:21:03.388462+00
3766	main_trader	HEALTHY	t	t	t	\N	86	0	0	\N	{"sl_set": 85, "sl_failed": 2, "positions_failed": 24, "positions_opened": 86}	2025-09-18 09:22:05.09057+00
3767	main_trader	HEALTHY	t	t	t	\N	89	0	0	\N	{"sl_set": 88, "sl_failed": 2, "positions_failed": 24, "positions_opened": 89}	2025-09-18 09:23:06.311731+00
3768	main_trader	HEALTHY	t	t	t	\N	92	0	0	\N	{"sl_set": 91, "sl_failed": 2, "positions_failed": 24, "positions_opened": 92}	2025-09-18 09:24:07.694401+00
3769	main_trader	HEALTHY	t	t	t	\N	95	0	0	\N	{"sl_set": 94, "sl_failed": 2, "positions_failed": 24, "positions_opened": 95}	2025-09-18 09:25:09.927011+00
3770	main_trader	HEALTHY	t	t	t	\N	97	0	0	\N	{"sl_set": 96, "sl_failed": 2, "positions_failed": 25, "positions_opened": 97}	2025-09-18 09:26:11.08569+00
3771	main_trader	HEALTHY	t	t	t	\N	97	0	0	\N	{"sl_set": 96, "sl_failed": 2, "positions_failed": 27, "positions_opened": 97}	2025-09-18 09:27:12.723089+00
3772	main_trader	HEALTHY	t	t	t	\N	100	0	0	\N	{"sl_set": 99, "sl_failed": 2, "positions_failed": 27, "positions_opened": 100}	2025-09-18 09:28:14.29899+00
3773	main_trader	HEALTHY	t	t	t	\N	102	0	0	\N	{"sl_set": 101, "sl_failed": 2, "positions_failed": 27, "positions_opened": 102}	2025-09-18 09:29:15.785341+00
3774	main_trader	HEALTHY	t	t	t	\N	102	0	0	\N	{"sl_set": 101, "sl_failed": 2, "positions_failed": 30, "positions_opened": 102}	2025-09-18 09:30:17.098871+00
3775	main_trader	HEALTHY	t	t	t	\N	105	0	0	\N	{"sl_set": 104, "sl_failed": 2, "positions_failed": 30, "positions_opened": 105}	2025-09-18 09:31:17.970169+00
3776	main_trader	HEALTHY	t	t	t	\N	106	0	0	\N	{"sl_set": 105, "sl_failed": 2, "positions_failed": 30, "positions_opened": 106}	2025-09-18 09:32:19.431211+00
3777	main_trader	HEALTHY	t	t	t	\N	107	0	0	\N	{"sl_set": 106, "sl_failed": 2, "positions_failed": 30, "positions_opened": 107}	2025-09-18 09:33:20.628578+00
3778	main_trader	HEALTHY	t	t	t	\N	108	0	0	\N	{"sl_set": 107, "sl_failed": 2, "positions_failed": 31, "positions_opened": 108}	2025-09-18 09:34:21.743458+00
3779	main_trader	HEALTHY	t	t	t	\N	108	0	0	\N	{"sl_set": 107, "sl_failed": 2, "positions_failed": 31, "positions_opened": 108}	2025-09-18 09:35:22.875471+00
3780	main_trader	HEALTHY	t	t	t	\N	109	0	0	\N	{"sl_set": 108, "sl_failed": 2, "positions_failed": 31, "positions_opened": 110}	2025-09-18 09:36:24.00596+00
3781	main_trader	HEALTHY	t	t	t	\N	112	0	0	\N	{"sl_set": 112, "sl_failed": 2, "positions_failed": 31, "positions_opened": 113}	2025-09-18 09:37:25.347915+00
3782	main_trader	HEALTHY	t	t	t	\N	114	0	0	\N	{"sl_set": 113, "sl_failed": 2, "positions_failed": 33, "positions_opened": 114}	2025-09-18 09:38:26.455074+00
3783	main_trader	HEALTHY	t	t	t	\N	115	0	0	\N	{"sl_set": 114, "sl_failed": 2, "positions_failed": 34, "positions_opened": 115}	2025-09-18 09:39:27.59388+00
3784	main_trader	HEALTHY	t	t	t	\N	117	0	0	\N	{"sl_set": 116, "sl_failed": 2, "positions_failed": 35, "positions_opened": 117}	2025-09-18 09:40:28.488776+00
3785	main_trader	HEALTHY	t	t	t	\N	119	0	0	\N	{"sl_set": 118, "sl_failed": 2, "positions_failed": 35, "positions_opened": 119}	2025-09-18 09:41:29.544959+00
3786	main_trader	HEALTHY	t	t	t	\N	119	0	0	\N	{"sl_set": 118, "sl_failed": 2, "positions_failed": 37, "positions_opened": 119}	2025-09-18 09:42:31.288409+00
3787	main_trader	HEALTHY	t	t	t	\N	122	0	0	\N	{"sl_set": 121, "sl_failed": 2, "positions_failed": 37, "positions_opened": 122}	2025-09-18 09:43:32.247316+00
3788	main_trader	HEALTHY	t	t	t	\N	124	0	0	\N	{"sl_set": 123, "sl_failed": 2, "positions_failed": 37, "positions_opened": 124}	2025-09-18 09:44:33.457572+00
3789	main_trader	HEALTHY	t	t	t	\N	124	0	0	\N	{"sl_set": 123, "sl_failed": 2, "positions_failed": 37, "positions_opened": 124}	2025-09-18 09:45:34.570548+00
3790	main_trader	HEALTHY	t	t	t	\N	124	0	0	\N	{"sl_set": 123, "sl_failed": 2, "positions_failed": 37, "positions_opened": 124}	2025-09-18 09:46:35.70141+00
3791	main_trader	HEALTHY	t	t	t	\N	124	0	0	\N	{"sl_set": 123, "sl_failed": 2, "positions_failed": 37, "positions_opened": 124}	2025-09-18 09:47:37.281546+00
3792	main_trader	HEALTHY	t	t	t	\N	124	0	0	\N	{"sl_set": 123, "sl_failed": 2, "positions_failed": 37, "positions_opened": 124}	2025-09-18 09:48:38.394628+00
3793	main_trader	HEALTHY	t	t	t	\N	124	0	0	\N	{"sl_set": 123, "sl_failed": 2, "positions_failed": 37, "positions_opened": 124}	2025-09-18 09:49:39.446992+00
3794	main_trader	HEALTHY	t	t	t	\N	124	0	0	\N	{"sl_set": 123, "sl_failed": 2, "positions_failed": 37, "positions_opened": 124}	2025-09-18 09:50:40.571308+00
3795	main_trader	HEALTHY	t	t	t	\N	125	0	0	\N	{"sl_set": 124, "sl_failed": 2, "positions_failed": 38, "positions_opened": 125}	2025-09-18 09:51:41.440944+00
3796	main_trader	HEALTHY	t	t	t	\N	127	0	0	\N	{"sl_set": 126, "sl_failed": 2, "positions_failed": 39, "positions_opened": 127}	2025-09-18 09:52:42.541411+00
3797	main_trader	HEALTHY	t	t	t	\N	130	0	0	\N	{"sl_set": 129, "sl_failed": 2, "positions_failed": 39, "positions_opened": 130}	2025-09-18 09:53:43.653733+00
3798	main_trader	HEALTHY	t	t	t	\N	133	0	0	\N	{"sl_set": 132, "sl_failed": 2, "positions_failed": 39, "positions_opened": 133}	2025-09-18 09:54:44.778133+00
3799	main_trader	HEALTHY	t	t	t	\N	135	0	0	\N	{"sl_set": 134, "sl_failed": 3, "positions_failed": 39, "positions_opened": 135}	2025-09-18 09:55:45.660841+00
3800	main_trader	HEALTHY	t	t	t	\N	136	0	0	\N	{"sl_set": 135, "sl_failed": 3, "positions_failed": 40, "positions_opened": 136}	2025-09-18 09:56:46.522052+00
3801	main_trader	HEALTHY	t	t	t	\N	137	0	0	\N	{"sl_set": 136, "sl_failed": 3, "positions_failed": 42, "positions_opened": 137}	2025-09-18 09:57:47.620802+00
3802	main_trader	HEALTHY	t	t	t	\N	139	0	0	\N	{"sl_set": 138, "sl_failed": 3, "positions_failed": 42, "positions_opened": 139}	2025-09-18 09:58:48.719094+00
3803	main_trader	HEALTHY	t	t	t	\N	141	0	0	\N	{"sl_set": 140, "sl_failed": 3, "positions_failed": 42, "positions_opened": 141}	2025-09-18 09:59:49.737582+00
3804	main_trader	HEALTHY	t	t	t	\N	143	0	0	\N	{"sl_set": 142, "sl_failed": 3, "positions_failed": 42, "positions_opened": 143}	2025-09-18 10:00:50.772499+00
3805	main_trader	HEALTHY	t	t	t	\N	143	0	0	\N	{"sl_set": 142, "sl_failed": 3, "positions_failed": 42, "positions_opened": 143}	2025-09-18 10:01:51.931651+00
3806	main_trader	HEALTHY	t	t	t	\N	143	0	0	\N	{"sl_set": 142, "sl_failed": 3, "positions_failed": 42, "positions_opened": 143}	2025-09-18 10:02:53.759296+00
3807	main_trader	HEALTHY	t	t	t	\N	143	0	0	\N	{"sl_set": 142, "sl_failed": 3, "positions_failed": 42, "positions_opened": 143}	2025-09-18 10:03:54.962482+00
3808	main_trader	HEALTHY	t	t	t	\N	143	0	0	\N	{"sl_set": 142, "sl_failed": 3, "positions_failed": 42, "positions_opened": 143}	2025-09-18 10:04:56.10217+00
3809	main_trader	RUNNING	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-18 10:05:20.012633+00
3810	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-18 10:06:21.536768+00
3811	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-18 10:07:22.932997+00
3812	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 1, "sl_failed": 0, "positions_failed": 3, "positions_opened": 1}	2025-09-18 10:08:23.810449+00
3813	main_trader	DEGRADED	t	t	t	\N	1	0	0	\N	{"sl_set": 1, "sl_failed": 0, "positions_failed": 6, "positions_opened": 1}	2025-09-18 10:09:24.927796+00
3814	main_trader	DEGRADED	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 6, "positions_opened": 2}	2025-09-18 10:10:26.292297+00
3815	main_trader	DEGRADED	t	t	t	\N	4	0	0	\N	{"sl_set": 4, "sl_failed": 0, "positions_failed": 6, "positions_opened": 4}	2025-09-18 10:11:27.268252+00
3816	main_trader	DEGRADED	t	t	t	\N	5	0	0	\N	{"sl_set": 5, "sl_failed": 0, "positions_failed": 6, "positions_opened": 5}	2025-09-18 10:12:28.464386+00
3817	main_trader	DEGRADED	t	t	t	\N	6	0	0	\N	{"sl_set": 6, "sl_failed": 0, "positions_failed": 7, "positions_opened": 6}	2025-09-18 10:13:29.34298+00
3818	main_trader	DEGRADED	t	t	t	\N	7	0	0	\N	{"sl_set": 6, "sl_failed": 1, "positions_failed": 7, "positions_opened": 7}	2025-09-18 10:14:30.23223+00
3819	main_trader	DEGRADED	t	t	t	\N	8	0	0	\N	{"sl_set": 7, "sl_failed": 1, "positions_failed": 8, "positions_opened": 8}	2025-09-18 10:15:31.521171+00
3820	main_trader	HEALTHY	t	t	t	\N	9	0	0	\N	{"sl_set": 9, "sl_failed": 1, "positions_failed": 8, "positions_opened": 10}	2025-09-18 10:16:32.573332+00
3821	main_trader	RUNNING	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-18 11:07:08.228725+00
3822	main_trader	RUNNING	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-18 13:51:29.013664+00
3823	main_trader	RUNNING	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-20 10:49:01.954667+00
3824	main_trader	RUNNING	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 20:23:07.082556+00
3825	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 20:24:08.301763+00
3826	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 20:25:10.016266+00
3827	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 20:26:11.310215+00
3828	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 20:27:12.56043+00
3829	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 20:28:13.963644+00
3830	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 20:29:15.378234+00
3831	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 20:30:17.397793+00
3832	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 20:31:18.576912+00
3833	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 20:32:19.782779+00
3834	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 20:33:20.983617+00
3835	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 20:34:22.109906+00
3836	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 20:35:23.585851+00
3837	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 20:36:24.844926+00
3838	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 20:37:25.948027+00
3839	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 20:38:28.162846+00
3840	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 20:39:30.229437+00
3841	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 20:40:31.820704+00
3842	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 20:41:33.015298+00
3843	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 20:42:34.217136+00
3844	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 20:43:36.10888+00
3845	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 20:44:37.880591+00
3846	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 20:45:39.356329+00
3847	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 20:46:40.816358+00
3848	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 20:47:41.860919+00
3849	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 20:48:43.103763+00
3850	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 20:49:44.318127+00
3851	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 20:50:45.911438+00
3852	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 20:51:47.393118+00
3853	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 20:52:48.566176+00
3854	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 20:53:50.072665+00
3855	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 20:54:51.210266+00
3856	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 20:55:52.820223+00
3857	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 20:56:54.259973+00
3858	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 20:57:55.589569+00
3859	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 20:58:56.695787+00
3860	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 20:59:58.010208+00
3861	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 21:00:59.617967+00
3862	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 21:02:00.995679+00
3863	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 21:03:02.284343+00
3864	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 21:04:03.372556+00
3865	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 21:05:04.749665+00
3866	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 21:06:06.242225+00
3867	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 21:07:07.497851+00
3868	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 21:08:08.706043+00
3869	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 21:09:09.956873+00
3870	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 21:10:11.71805+00
3871	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 21:11:13.45429+00
3872	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 21:12:14.963361+00
3873	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 21:13:16.106075+00
3874	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 21:14:17.290484+00
3875	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 21:15:18.394604+00
3876	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 21:16:19.950913+00
3877	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 21:17:21.249992+00
3878	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 21:18:22.641983+00
3879	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 21:19:23.760872+00
3880	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 21:20:24.867475+00
3881	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 21:21:26.189601+00
3882	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 21:22:27.442242+00
3883	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 21:23:28.690711+00
3884	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 21:24:29.946154+00
3885	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 21:25:31.117858+00
3886	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 21:26:32.628546+00
3887	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 21:27:33.928923+00
3888	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 21:28:35.063891+00
3889	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 21:29:36.553733+00
3890	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 21:30:37.855333+00
3891	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 21:31:39.484559+00
3892	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 21:32:40.699491+00
3893	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 21:33:41.769057+00
3894	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 21:34:43.368747+00
3895	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 21:35:44.646973+00
3896	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 21:36:46.412167+00
3897	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 21:37:47.815274+00
3898	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 21:38:49.122684+00
3899	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 21:39:50.294299+00
3900	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 21:40:51.417944+00
3901	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 21:41:53.306334+00
3902	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 21:42:54.557291+00
3903	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 21:43:55.70888+00
3904	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 21:44:57.013774+00
3905	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 21:45:58.291642+00
3906	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 21:46:59.666831+00
3907	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 21:48:00.928809+00
3908	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 21:49:02.040072+00
3909	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 21:50:03.296723+00
3910	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 21:51:04.48526+00
3911	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 21:52:05.937833+00
3912	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 21:53:07.230989+00
3913	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 21:54:09.615202+00
3914	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 21:55:10.865049+00
3915	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 21:56:12.103435+00
3916	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 21:57:13.4086+00
3917	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 21:58:14.650878+00
3918	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 21:59:16.030083+00
3919	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 22:00:17.284927+00
3920	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 22:01:18.851281+00
3921	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 22:02:20.409046+00
3922	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 22:03:21.589386+00
3923	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 22:04:23.470073+00
3924	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 22:05:24.786592+00
3925	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 22:06:25.894573+00
3926	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 22:07:27.256983+00
3927	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 22:08:28.450715+00
3928	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 22:09:29.748003+00
3929	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 22:10:31.286835+00
3930	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 22:11:32.619772+00
3931	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 22:12:33.709074+00
3932	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 22:13:34.842123+00
3933	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 22:14:36.305695+00
3934	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 22:15:37.651474+00
3935	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 22:16:39.006976+00
3936	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 22:17:40.239237+00
3937	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 22:18:41.466016+00
3938	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 22:19:42.989297+00
3939	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 22:20:44.089387+00
3940	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 22:21:45.422273+00
3941	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 22:22:46.825019+00
3942	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 22:23:48.009464+00
3943	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 22:24:49.429804+00
3944	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 22:25:50.684665+00
3945	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 22:26:51.803221+00
3946	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 22:27:52.98398+00
3947	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 22:28:54.136103+00
3948	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 22:29:55.672577+00
3949	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 22:30:56.919292+00
3950	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 22:31:58.256373+00
3951	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 22:32:59.561658+00
3952	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 22:34:00.598651+00
3953	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 22:35:02.017692+00
3954	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 22:36:03.282714+00
3955	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 22:37:04.534012+00
3956	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 22:38:05.915162+00
3957	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 22:39:07.184656+00
3958	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 22:40:08.8417+00
3959	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 22:41:10.732675+00
3960	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 22:42:12.317976+00
3961	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 22:43:13.808723+00
3962	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 22:44:15.057416+00
3963	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 22:45:16.565689+00
3964	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 22:46:18.37303+00
3965	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 22:47:19.717181+00
3966	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 22:48:21.044316+00
3967	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 22:49:22.307246+00
3968	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 22:50:23.554995+00
3969	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 22:51:25.012178+00
3970	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 22:52:26.263842+00
3971	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 22:53:27.68478+00
3972	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 22:54:28.938198+00
3973	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 22:55:30.630061+00
3974	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 22:56:32.262923+00
3975	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 22:57:33.921724+00
3976	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 22:58:35.331482+00
3977	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 22:59:36.593588+00
3978	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 23:00:37.731011+00
3979	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 23:01:39.265317+00
3980	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 23:02:40.957987+00
3981	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 23:03:42.149384+00
3982	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 23:04:43.326492+00
3983	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 23:05:44.542038+00
3984	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 23:06:46.250116+00
3985	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 23:07:47.822655+00
3986	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 23:08:48.93196+00
3987	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 23:09:50.019278+00
3988	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 23:10:51.348109+00
3989	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 23:11:52.902655+00
3990	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 23:12:54.300086+00
3991	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 23:13:55.643761+00
3992	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 23:14:57.158999+00
3993	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 23:15:58.557974+00
3994	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 23:17:00.385069+00
3995	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 23:18:01.611915+00
3996	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 23:19:02.935655+00
3997	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 23:20:04.065809+00
3998	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 23:21:05.216763+00
3999	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 23:22:06.488435+00
4000	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 23:23:08.846676+00
4001	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 23:24:10.395747+00
4002	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 23:25:11.653641+00
4003	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 23:26:12.761195+00
4004	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 23:27:13.883449+00
4005	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 23:28:15.268945+00
4006	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 23:29:16.395252+00
4007	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 23:30:17.458179+00
4008	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 23:31:18.925124+00
4009	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 23:32:20.133457+00
4010	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 23:33:21.738128+00
4011	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 23:34:23.005805+00
4012	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 23:35:24.220597+00
4013	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 23:36:25.394175+00
4014	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 23:37:26.653419+00
4015	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 23:38:28.445962+00
4016	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 23:39:30.073035+00
4017	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 23:40:31.244767+00
4018	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 23:41:32.278153+00
4019	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 23:42:33.430378+00
4020	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 23:43:34.78148+00
4021	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 23:44:35.988646+00
4022	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 23:45:37.104752+00
4023	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 23:46:38.294216+00
4024	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 23:47:39.405931+00
4025	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 23:48:40.824054+00
4026	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 23:49:42.05443+00
4027	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 23:50:43.248638+00
4028	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 23:51:44.407751+00
4029	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 23:52:45.482666+00
4030	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 23:53:47.152112+00
4031	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 23:54:48.280822+00
4032	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 23:55:49.614531+00
4033	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 23:56:50.698225+00
4034	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 23:57:51.829104+00
4035	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 23:58:53.190562+00
4036	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-21 23:59:55.05305+00
4037	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 00:00:56.406394+00
4038	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 00:01:57.666189+00
4039	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 00:02:58.78572+00
4040	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 00:04:00.081484+00
4041	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 00:05:01.419279+00
4042	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 00:06:02.450046+00
4043	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 00:07:03.693656+00
4044	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 00:08:04.863002+00
4045	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 00:09:06.258901+00
4046	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 00:10:07.611567+00
4047	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 00:11:08.651627+00
4048	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 00:12:10.921692+00
4049	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 00:13:12.46834+00
4050	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 00:14:13.919428+00
4051	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 00:15:16.028713+00
4052	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 00:16:17.305364+00
4053	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 00:17:18.729108+00
4054	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 00:18:20.062605+00
4055	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 00:19:21.217731+00
4056	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 00:20:22.42955+00
4057	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 00:21:23.68415+00
4058	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 00:22:25.214931+00
4059	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 00:23:26.453097+00
4060	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 00:24:27.598943+00
4061	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 00:25:28.80436+00
4062	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 00:26:30.059125+00
4063	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 00:27:31.484554+00
4064	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 00:28:32.770452+00
4065	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 00:29:33.836231+00
4066	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 00:30:34.93684+00
4067	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 00:31:36.222088+00
4068	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 00:32:37.762559+00
4069	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 00:33:39.2401+00
4070	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 00:34:40.41807+00
4071	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 00:35:41.583634+00
4072	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 00:36:42.649418+00
4073	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 00:37:44.114827+00
4074	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 00:38:45.508793+00
4075	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 00:39:46.867468+00
4076	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 00:40:48.033725+00
4077	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 00:41:49.144057+00
4078	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 00:42:50.911217+00
4079	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 00:43:52.494644+00
4080	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 00:44:54.030502+00
4081	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 00:45:55.41249+00
4082	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 00:46:56.519394+00
4083	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 00:47:58.11966+00
4084	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 00:48:59.271021+00
4085	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 00:50:00.425026+00
4086	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 00:51:01.671099+00
4087	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 00:52:02.764069+00
4088	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 00:53:04.363703+00
4089	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 00:54:05.898161+00
4090	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 00:55:07.011211+00
4091	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 00:56:08.27283+00
4092	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 00:57:09.643662+00
4093	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 00:58:11.273231+00
4094	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 00:59:12.624819+00
4095	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 01:00:13.871838+00
4096	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 01:01:14.927392+00
4097	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 01:02:16.075224+00
4098	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 01:03:17.317127+00
4099	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 01:04:18.731907+00
4100	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 01:05:19.977161+00
4101	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 01:06:21.067294+00
4102	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 01:07:22.247779+00
4103	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 01:08:23.474862+00
4104	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 01:09:24.831766+00
4105	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 01:10:26.467675+00
4106	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 01:11:27.543786+00
4107	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 01:12:28.605494+00
4108	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 01:13:29.685393+00
4109	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 01:14:31.082454+00
4110	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 01:15:32.352614+00
4111	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 01:16:33.542318+00
4112	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 01:17:34.762994+00
4113	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 01:18:35.939926+00
4114	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 01:19:37.369768+00
4115	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 01:20:38.854267+00
4116	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 01:21:40.11828+00
4117	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 01:22:41.380641+00
4118	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 01:23:43.074248+00
4119	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 01:24:44.790579+00
4120	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 01:25:46.214259+00
4121	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 01:26:47.377423+00
4122	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 01:27:48.575932+00
4123	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 01:28:49.702258+00
4124	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 01:29:51.134279+00
4125	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 01:30:52.503888+00
4126	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 01:31:53.707958+00
4127	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 01:32:54.879206+00
4128	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 01:33:55.963469+00
4129	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 01:34:57.315746+00
4130	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 01:35:58.481233+00
4131	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 01:36:59.633717+00
4132	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 01:38:00.885744+00
4133	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 01:39:01.969178+00
4134	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 01:40:03.827023+00
4135	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 01:41:05.057676+00
4136	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 01:42:06.189956+00
4137	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 01:43:07.357547+00
4138	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 01:44:08.71574+00
4139	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 01:45:10.169356+00
4140	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 01:46:11.245865+00
4141	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 01:47:13.74631+00
4142	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 01:48:14.92023+00
4143	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 01:49:16.158066+00
4144	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 01:50:17.376801+00
4145	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 01:51:18.46097+00
4146	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 01:52:19.867654+00
4147	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 01:53:21.11601+00
4148	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 01:54:22.582383+00
4149	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 01:55:23.827373+00
4150	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 01:56:24.992123+00
4151	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 01:57:26.696046+00
4152	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 01:58:28.175423+00
4153	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 01:59:29.635714+00
4154	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 02:00:30.761852+00
4155	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 02:01:31.941151+00
4156	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 02:02:33.367794+00
4157	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 02:03:34.54574+00
4158	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 02:04:35.726428+00
4159	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 02:05:37.055663+00
4160	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 02:06:38.250709+00
4161	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 02:07:39.682554+00
4162	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 02:08:40.932497+00
4163	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 02:09:41.995373+00
4164	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 02:10:43.043133+00
4165	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 02:11:44.305327+00
4166	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 02:12:45.886474+00
4167	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 02:13:47.273167+00
4168	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 02:14:48.369821+00
4169	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 02:15:49.624914+00
4170	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 02:16:50.770695+00
4171	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 02:17:52.337166+00
4172	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 02:18:53.538+00
4173	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 02:19:54.650685+00
4174	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 02:20:55.741941+00
4175	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 02:21:57.253544+00
4176	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 02:22:58.827841+00
4177	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 02:24:00.027646+00
4178	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 02:25:01.355098+00
4179	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 02:26:02.661289+00
4180	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 02:27:03.930504+00
4181	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 02:28:05.678799+00
4182	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 02:29:07.359255+00
4183	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 02:30:08.670741+00
4184	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 02:31:09.817019+00
4185	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 02:32:10.865159+00
4186	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 02:33:12.56878+00
4187	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 02:34:14.043964+00
4188	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 02:35:15.545701+00
4189	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 02:36:16.852667+00
4190	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 02:37:18.008777+00
4191	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 02:38:19.342871+00
4192	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 02:39:20.592201+00
4193	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 02:40:21.725969+00
4194	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 02:41:23.043317+00
4195	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 02:42:24.145+00
4196	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 02:43:25.612981+00
4197	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 02:44:26.768562+00
4198	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 02:45:27.891049+00
4199	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 02:46:29.017614+00
4200	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 02:47:30.325222+00
4201	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 02:48:31.702368+00
4202	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 02:49:32.924822+00
4203	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 02:50:34.085711+00
4204	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 02:51:35.201223+00
4205	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 02:52:36.361123+00
4206	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 02:53:39.17341+00
4207	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 02:54:40.555317+00
4208	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 02:55:42.035138+00
4209	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 02:56:43.15892+00
4210	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 02:57:44.40482+00
4211	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 02:58:46.036881+00
4212	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 02:59:47.772407+00
4213	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 03:00:49.021294+00
4214	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 03:01:50.115118+00
4215	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 03:02:51.379403+00
4216	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 03:03:52.839401+00
4217	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 03:04:54.498753+00
4218	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 03:05:56.197574+00
4219	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 03:06:57.604037+00
4220	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 03:07:58.846699+00
4221	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 03:09:00.225916+00
4222	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 03:10:01.547882+00
4223	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 03:11:02.834295+00
4224	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 03:12:03.978684+00
4225	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 03:13:05.35158+00
4226	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 03:14:06.824324+00
4227	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 03:15:08.433589+00
4228	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 03:16:09.966933+00
4229	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 03:17:11.183449+00
4230	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 03:18:12.501238+00
4231	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 03:19:13.890942+00
4232	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 03:20:15.157788+00
4233	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 03:21:16.377178+00
4234	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 03:22:17.706341+00
4235	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 03:23:19.257627+00
4236	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 03:24:20.968276+00
4237	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 03:25:22.139784+00
4238	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 03:26:23.365649+00
4239	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 03:27:24.52356+00
4240	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 03:28:26.078603+00
4241	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 03:29:27.497379+00
4242	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 03:30:28.691269+00
4243	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 03:31:29.990949+00
4244	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 03:32:31.245138+00
4245	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 03:33:32.573779+00
4246	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 03:34:34.184258+00
4247	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 03:35:35.532797+00
4248	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 03:36:36.81482+00
4249	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 03:37:38.784275+00
4250	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 03:38:40.157194+00
4251	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 03:39:41.491431+00
4252	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 03:40:42.647763+00
4253	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 03:41:44.277423+00
4254	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 03:42:45.532281+00
4255	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 03:43:47.523701+00
4256	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 03:44:48.679352+00
4257	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 03:45:49.817468+00
4258	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 03:46:50.997541+00
4259	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 03:47:52.192736+00
4260	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 03:48:54.238715+00
4261	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 03:49:55.519444+00
4262	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 03:50:56.693211+00
4263	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 03:51:57.829456+00
4264	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 03:52:59.612556+00
4265	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 03:54:02.169386+00
4266	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 03:55:03.517916+00
4267	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 03:56:04.98574+00
4268	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 03:57:06.233075+00
4269	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 03:58:07.302492+00
4270	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 03:59:08.726931+00
4271	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 04:00:10.115044+00
4272	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 04:01:11.4423+00
4273	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 04:02:12.702793+00
4274	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 04:03:13.845504+00
4275	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 04:04:15.409655+00
4276	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 04:05:17.221832+00
4277	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 04:06:18.451738+00
4278	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 04:07:19.754591+00
4279	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 04:08:21.056265+00
4280	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 04:09:22.522332+00
4281	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 04:10:23.676072+00
4282	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 04:11:24.818195+00
4283	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 04:12:26.068472+00
4284	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 04:13:27.525732+00
4285	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 04:14:29.084899+00
4286	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 04:15:30.719198+00
4287	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 04:16:31.823179+00
4288	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 04:17:33.027962+00
4289	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 04:18:34.403917+00
4290	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 04:19:36.065277+00
4291	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 04:20:37.473839+00
4292	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 04:21:38.693179+00
4293	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 04:22:39.798874+00
4294	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 04:23:41.05683+00
4295	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 04:24:42.556794+00
4296	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 04:25:44.124298+00
4297	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 04:26:45.261576+00
4298	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 04:27:46.740263+00
4299	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 04:28:47.860245+00
4300	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 04:29:49.51915+00
4301	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 04:30:50.94743+00
4302	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 04:31:52.3325+00
4303	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 04:32:53.583858+00
4304	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 04:33:54.798685+00
4305	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 04:34:56.238058+00
4306	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 04:35:57.529895+00
4307	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 04:36:58.693398+00
4308	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 04:38:00.01528+00
4309	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 04:39:01.276637+00
4310	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 04:40:02.776362+00
4311	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 04:41:04.717766+00
4312	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 04:42:05.79429+00
4313	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 04:43:07.058118+00
4314	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 04:44:08.278747+00
4315	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 04:45:10.144317+00
4316	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 04:46:11.546085+00
4317	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 04:47:12.616576+00
4318	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 04:48:13.703581+00
4319	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 04:49:14.848246+00
4320	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 04:50:16.943783+00
4321	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 04:51:18.237652+00
4322	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 04:52:19.561779+00
4323	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 04:53:20.753546+00
4324	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 04:54:22.149299+00
4325	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 04:55:23.663382+00
4326	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 04:56:25.528275+00
4327	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 04:57:26.882408+00
4328	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 04:58:28.075599+00
4329	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 04:59:29.163322+00
4330	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 05:00:30.664865+00
4331	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 05:01:32.049927+00
4332	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 05:02:33.172401+00
4333	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 05:03:34.322469+00
4334	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 05:04:35.641472+00
4335	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 05:05:36.962949+00
4336	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 05:06:38.538444+00
4337	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 05:07:39.616728+00
4338	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 05:08:40.745201+00
4339	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 05:09:41.807167+00
4340	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 05:10:43.287+00
4341	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 05:11:44.593166+00
4342	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 05:12:45.911312+00
4343	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 05:13:47.062784+00
4344	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 05:14:48.332597+00
4345	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 05:15:49.955743+00
4346	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 05:16:51.244804+00
4347	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 05:17:52.64004+00
4348	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 05:18:53.773419+00
4349	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 05:19:55.284662+00
4350	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 05:20:56.85943+00
4351	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 05:21:58.249724+00
4352	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 05:22:59.446558+00
4353	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 05:24:00.932692+00
4354	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 05:25:02.449869+00
4355	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 05:26:04.546555+00
4356	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 05:27:06.311063+00
4357	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 05:28:07.757759+00
4358	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 05:29:08.993612+00
4359	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 05:30:10.192015+00
4360	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 05:31:11.900777+00
4361	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 05:32:13.148956+00
4362	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 05:33:14.41216+00
4363	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 05:34:15.663971+00
4364	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 05:35:16.82407+00
4365	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 05:36:18.639387+00
4366	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 05:37:20.500176+00
4367	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 05:38:21.899793+00
4368	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 05:39:23.280185+00
4369	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 05:40:24.497681+00
4370	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 05:41:25.660777+00
4371	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 05:42:27.040049+00
4372	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 05:43:28.59567+00
4373	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 05:44:29.736238+00
4374	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 05:45:31.15076+00
4375	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 05:46:32.436881+00
4376	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 05:47:34.195927+00
4377	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 05:48:35.544208+00
4378	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 05:49:36.798536+00
4379	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 05:50:37.925034+00
4380	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 05:51:39.038495+00
4381	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 05:52:40.358347+00
4382	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 05:53:41.664231+00
4383	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 05:54:42.791051+00
4384	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 05:55:43.92841+00
4385	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 05:56:45.222368+00
4386	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 05:57:46.587174+00
4387	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 05:58:47.881494+00
4388	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 05:59:49.280814+00
4389	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 06:00:50.497798+00
4390	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 06:01:51.662321+00
4391	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 06:02:53.060155+00
4392	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 06:03:54.232887+00
4393	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 06:04:55.402177+00
4394	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 06:05:56.663941+00
4395	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 06:06:58.013246+00
4396	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 06:07:59.541447+00
4397	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 06:09:00.875802+00
4398	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 06:10:02.083003+00
4399	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 06:11:03.196222+00
4400	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 06:12:04.751067+00
4401	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 06:13:06.716995+00
4402	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 06:14:08.088315+00
4403	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 06:15:09.259469+00
4404	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 06:16:10.39581+00
4405	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 06:17:11.556629+00
4406	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 06:18:13.07264+00
4407	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 06:19:14.353236+00
4408	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 06:20:15.577062+00
4409	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 06:21:16.704438+00
4410	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 06:22:18.157941+00
4411	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 06:23:19.533542+00
4412	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 06:24:21.405671+00
4413	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 06:25:22.511173+00
4414	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 06:26:23.826473+00
4415	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 06:27:26.480778+00
4416	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 06:28:28.108045+00
4417	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 06:29:29.183338+00
4418	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 06:30:30.293077+00
4419	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 06:31:31.623683+00
4420	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 06:32:33.08654+00
4421	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 06:33:34.52472+00
4422	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 06:34:35.781078+00
4423	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 06:35:37.05468+00
4424	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 06:36:38.29291+00
4425	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 06:37:39.737171+00
4426	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 06:38:41.085328+00
4427	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 06:39:42.221993+00
4428	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 06:40:43.468847+00
4429	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 06:41:44.815977+00
4430	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 06:42:46.26108+00
4431	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 06:43:47.473924+00
4432	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 06:44:48.89694+00
4433	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 06:45:50.220808+00
4434	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 06:46:51.49909+00
4435	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 06:47:52.810263+00
4436	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 06:48:54.063817+00
4437	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 06:49:55.129074+00
4438	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 06:50:56.204728+00
4439	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 06:51:57.403682+00
4440	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 06:52:59.042945+00
4441	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 06:54:00.241239+00
4442	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 06:55:01.323705+00
4443	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 06:56:02.470191+00
4444	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 06:57:03.982555+00
4445	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 06:58:06.020742+00
4446	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 06:59:07.727713+00
4447	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 07:00:08.79922+00
4448	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 07:01:09.890556+00
4449	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 07:02:11.505904+00
4450	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 07:03:12.957205+00
4451	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 07:04:14.134892+00
4452	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 07:05:15.370232+00
4453	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 07:06:16.7158+00
4454	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 07:07:18.402109+00
4455	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 07:08:19.709082+00
4456	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 07:09:20.982376+00
4457	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 07:10:22.047643+00
4458	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 07:11:23.312019+00
4459	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 07:12:24.485362+00
4460	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 07:13:26.104635+00
4461	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 07:14:27.528168+00
4462	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 07:15:28.792183+00
4463	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 07:16:30.655949+00
4464	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 07:17:31.822647+00
4465	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 07:18:33.088871+00
4466	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 07:19:34.574603+00
4467	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 07:20:35.811953+00
4468	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 07:21:36.91379+00
4469	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 07:22:39.026048+00
4470	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 07:23:40.402652+00
4471	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 07:24:42.751604+00
4472	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 07:25:44.310798+00
4473	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 07:26:45.37719+00
4474	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 07:27:46.738654+00
4475	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 07:28:47.968319+00
4476	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 07:29:49.686235+00
4477	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 07:30:50.932637+00
4478	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 07:31:52.197005+00
4479	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 07:32:53.330118+00
4480	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 07:33:54.408285+00
4481	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 07:34:56.018591+00
4482	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 07:35:57.141753+00
4483	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 07:36:58.396622+00
4484	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 07:37:59.721878+00
4485	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 07:39:01.226599+00
4486	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 07:40:02.529357+00
4487	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 07:41:03.718844+00
4488	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 07:42:05.167879+00
4489	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 07:43:06.416332+00
4490	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 07:44:07.563731+00
4491	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 07:45:09.612296+00
4492	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 07:46:10.899863+00
4493	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 07:47:12.236649+00
4494	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 07:48:13.710993+00
4495	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 07:49:15.030148+00
4496	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 07:50:16.753114+00
4497	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 07:51:18.114005+00
4498	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 07:52:19.804382+00
4499	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 07:53:20.951083+00
4500	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 07:54:22.106404+00
4501	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 07:55:23.500463+00
4502	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 07:56:25.088042+00
4503	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 07:57:26.50504+00
4504	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 07:58:28.147184+00
4505	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 07:59:29.425806+00
4506	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 08:00:30.504276+00
4507	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 08:01:31.960871+00
4508	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 08:02:33.46656+00
4509	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 08:03:34.651701+00
4510	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 08:04:35.772823+00
4511	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 08:05:36.969154+00
4512	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 08:06:38.428156+00
4513	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 08:07:39.856551+00
4514	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 08:08:40.985079+00
4515	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 08:09:42.371847+00
4516	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 08:10:43.874114+00
4517	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 08:11:45.577693+00
4518	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 08:12:46.826298+00
4519	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 08:13:47.911054+00
4520	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 08:14:48.966925+00
4521	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 08:15:50.157811+00
4522	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 08:16:51.900568+00
4523	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 08:17:53.889003+00
4524	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 08:18:55.464783+00
4525	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 08:19:56.497453+00
4526	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 08:20:57.720279+00
4527	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 08:21:59.381603+00
4528	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 08:23:00.945201+00
4529	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 08:24:02.452258+00
4530	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 08:25:03.670602+00
4531	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 08:26:04.830821+00
4532	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 08:27:06.6684+00
4533	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 08:28:08.15216+00
4534	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 08:29:09.379079+00
4535	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 08:30:10.727949+00
4536	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 08:31:12.133282+00
4537	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 08:32:13.684028+00
4538	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 08:33:15.13994+00
4539	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 08:34:16.238382+00
4540	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 08:35:17.436109+00
4541	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 08:36:19.535024+00
4542	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 08:37:20.92467+00
4543	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 08:38:22.239502+00
4544	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 08:39:23.554708+00
4545	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 08:40:25.705878+00
4546	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 08:41:26.979183+00
4547	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 08:42:28.230365+00
4548	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 08:43:29.453443+00
4549	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 08:44:30.664188+00
4550	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 08:45:32.036802+00
4551	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 08:46:33.14171+00
4552	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 08:47:34.374832+00
4553	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 08:48:35.742443+00
4554	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 08:49:37.022644+00
4555	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 08:50:38.463786+00
4556	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 08:51:39.787243+00
4557	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 08:52:42.053488+00
4558	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 08:53:43.189694+00
4559	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 08:54:44.352828+00
4560	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 08:55:45.914714+00
4561	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 08:56:47.495354+00
4562	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 08:57:48.805655+00
4563	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 08:58:50.106148+00
4564	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 08:59:51.358215+00
4565	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 09:00:53.093212+00
4566	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 09:01:56.323462+00
4567	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 09:02:57.459304+00
4568	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 09:03:58.611076+00
4569	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 09:05:00.031545+00
4570	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 09:06:01.467079+00
4571	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 09:07:02.683218+00
4572	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 09:08:04.027028+00
4573	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 09:09:05.2857+00
4574	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 09:10:06.439369+00
4575	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 09:11:07.919056+00
4576	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 09:12:09.276539+00
4577	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 09:13:10.570735+00
4578	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 09:14:11.809413+00
4579	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 09:15:12.870473+00
4580	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 09:16:14.49345+00
4581	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 09:17:15.616736+00
4582	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 09:18:16.758865+00
4583	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 09:19:17.99812+00
4584	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 09:20:19.214661+00
4585	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 09:21:21.057048+00
4586	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 09:22:22.390163+00
4587	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 09:23:23.56779+00
4588	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 09:24:24.867723+00
4589	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 09:25:26.049646+00
4590	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 09:26:27.510694+00
4591	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 09:27:29.031845+00
4592	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 09:28:30.307363+00
4593	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 09:29:31.599702+00
4594	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 09:30:32.968839+00
4595	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 09:31:34.267768+00
4596	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 09:32:35.522589+00
4597	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 09:33:36.976257+00
4598	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 09:34:38.079131+00
4599	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 09:35:39.207265+00
4600	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 09:36:40.596955+00
4601	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 09:37:42.156625+00
4602	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 09:38:43.412259+00
4603	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 09:39:44.578071+00
4604	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 09:40:46.147147+00
4605	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 09:41:47.693738+00
4606	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 09:42:48.893992+00
4607	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 09:43:50.098897+00
4608	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 09:44:51.560881+00
4609	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 09:45:52.888621+00
4610	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 09:46:54.415143+00
4611	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 09:47:55.753401+00
4612	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 09:48:57.180039+00
4613	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 09:49:58.430637+00
4614	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 09:50:59.479012+00
4615	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 09:52:01.377659+00
4616	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 09:53:02.957309+00
4617	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 09:54:04.245712+00
4618	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 09:55:05.957192+00
4619	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 09:56:07.234549+00
4620	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 09:57:08.73433+00
4621	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 09:58:10.039368+00
4622	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 09:59:11.153492+00
4623	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 10:00:12.264457+00
4624	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 10:01:13.418174+00
4625	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 10:02:14.872034+00
4626	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 10:03:16.228689+00
4627	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 10:04:17.88635+00
4628	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 10:05:19.127776+00
4629	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 10:06:20.252017+00
4630	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 10:07:21.77169+00
4631	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 10:08:23.096256+00
4632	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 10:09:24.355967+00
4633	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 10:10:25.582917+00
4634	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 10:11:26.852335+00
4635	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 10:12:28.427848+00
4636	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 10:13:29.861934+00
4637	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 10:14:30.919684+00
4638	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 10:15:32.168862+00
4639	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 10:16:33.34058+00
4640	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 10:17:34.654038+00
4641	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 10:18:35.911428+00
4642	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 10:19:37.587425+00
4643	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 10:20:38.818034+00
4644	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 10:21:40.058419+00
4645	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 10:22:41.759123+00
4646	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 10:23:43.59862+00
4647	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 10:24:45.094339+00
4648	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 10:25:46.178927+00
4649	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 10:26:48.397563+00
4650	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 10:27:50.363069+00
4651	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 10:28:51.771336+00
4652	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 10:29:52.887391+00
4653	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 10:30:54.033535+00
4654	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 10:31:55.284122+00
4655	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 10:32:57.641744+00
4656	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 10:33:59.058167+00
4657	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 10:35:00.453366+00
4658	main_trader	HEALTHY	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 0, "positions_opened": 3}	2025-09-22 10:36:01.969279+00
4659	main_trader	HEALTHY	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 0, "positions_opened": 3}	2025-09-22 10:37:03.13818+00
4660	main_trader	HEALTHY	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 0, "positions_opened": 3}	2025-09-22 10:38:04.555+00
4661	main_trader	HEALTHY	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 0, "positions_opened": 3}	2025-09-22 10:39:05.89339+00
4662	main_trader	HEALTHY	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 0, "positions_opened": 3}	2025-09-22 10:40:07.339126+00
4663	main_trader	HEALTHY	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 0, "positions_opened": 3}	2025-09-22 10:41:08.692324+00
4664	main_trader	HEALTHY	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 0, "positions_opened": 3}	2025-09-22 10:42:09.854864+00
4665	main_trader	HEALTHY	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 0, "positions_opened": 3}	2025-09-22 10:43:11.565266+00
4666	main_trader	HEALTHY	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 0, "positions_opened": 3}	2025-09-22 10:44:12.828843+00
4667	main_trader	HEALTHY	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 0, "positions_opened": 3}	2025-09-22 10:45:14.048646+00
4668	main_trader	HEALTHY	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 0, "positions_opened": 3}	2025-09-22 10:46:15.157985+00
4669	main_trader	HEALTHY	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 0, "positions_opened": 3}	2025-09-22 10:47:16.414593+00
4670	main_trader	HEALTHY	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 0, "positions_opened": 3}	2025-09-22 10:48:17.80634+00
4671	main_trader	HEALTHY	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 0, "positions_opened": 3}	2025-09-22 10:49:19.036571+00
4672	main_trader	HEALTHY	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 0, "positions_opened": 3}	2025-09-22 10:50:20.242687+00
4673	main_trader	HEALTHY	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 0, "positions_opened": 3}	2025-09-22 10:51:21.424702+00
4674	main_trader	HEALTHY	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 0, "positions_opened": 3}	2025-09-22 10:52:22.812615+00
4675	main_trader	HEALTHY	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 0, "positions_opened": 3}	2025-09-22 10:53:24.613876+00
4676	main_trader	HEALTHY	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 0, "positions_opened": 3}	2025-09-22 10:54:25.974406+00
4677	main_trader	HEALTHY	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 0, "positions_opened": 3}	2025-09-22 10:55:27.162379+00
4678	main_trader	HEALTHY	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 0, "positions_opened": 3}	2025-09-22 10:56:28.294484+00
4679	main_trader	HEALTHY	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 0, "positions_opened": 3}	2025-09-22 10:57:29.454619+00
4680	main_trader	HEALTHY	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 0, "positions_opened": 3}	2025-09-22 10:58:30.874268+00
4681	main_trader	HEALTHY	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 0, "positions_opened": 3}	2025-09-22 10:59:32.17028+00
4682	main_trader	HEALTHY	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 0, "positions_opened": 3}	2025-09-22 11:00:33.482762+00
4683	main_trader	HEALTHY	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 0, "positions_opened": 3}	2025-09-22 11:01:34.75418+00
4684	main_trader	HEALTHY	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 0, "positions_opened": 3}	2025-09-22 11:02:35.915995+00
4685	main_trader	HEALTHY	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 0, "positions_opened": 3}	2025-09-22 11:03:37.159139+00
4686	main_trader	HEALTHY	t	t	t	\N	3	0	0	\N	{"sl_set": 3, "sl_failed": 0, "positions_failed": 0, "positions_opened": 3}	2025-09-22 11:04:38.265362+00
4687	main_trader	HEALTHY	t	t	t	\N	5	0	0	\N	{"sl_set": 5, "sl_failed": 0, "positions_failed": 0, "positions_opened": 5}	2025-09-22 11:05:39.77062+00
4688	main_trader	HEALTHY	t	t	t	\N	5	0	0	\N	{"sl_set": 5, "sl_failed": 0, "positions_failed": 0, "positions_opened": 5}	2025-09-22 11:06:40.934375+00
4689	main_trader	HEALTHY	t	t	t	\N	5	0	0	\N	{"sl_set": 5, "sl_failed": 0, "positions_failed": 0, "positions_opened": 5}	2025-09-22 11:07:42.135722+00
4690	main_trader	HEALTHY	t	t	t	\N	5	0	0	\N	{"sl_set": 5, "sl_failed": 0, "positions_failed": 0, "positions_opened": 5}	2025-09-22 11:08:43.503954+00
4691	main_trader	HEALTHY	t	t	t	\N	5	0	0	\N	{"sl_set": 5, "sl_failed": 0, "positions_failed": 0, "positions_opened": 5}	2025-09-22 11:09:44.779249+00
4692	main_trader	HEALTHY	t	t	t	\N	5	0	0	\N	{"sl_set": 5, "sl_failed": 0, "positions_failed": 0, "positions_opened": 5}	2025-09-22 11:10:47.53606+00
4693	main_trader	HEALTHY	t	t	t	\N	5	0	0	\N	{"sl_set": 5, "sl_failed": 0, "positions_failed": 0, "positions_opened": 5}	2025-09-22 11:11:48.843247+00
4694	main_trader	HEALTHY	t	t	t	\N	5	0	0	\N	{"sl_set": 5, "sl_failed": 0, "positions_failed": 0, "positions_opened": 5}	2025-09-22 11:12:50.072997+00
4695	main_trader	HEALTHY	t	t	t	\N	5	0	0	\N	{"sl_set": 5, "sl_failed": 0, "positions_failed": 0, "positions_opened": 5}	2025-09-22 11:13:51.222765+00
4696	main_trader	HEALTHY	t	t	t	\N	5	0	0	\N	{"sl_set": 5, "sl_failed": 0, "positions_failed": 0, "positions_opened": 5}	2025-09-22 11:14:52.425602+00
4697	main_trader	HEALTHY	t	t	t	\N	5	0	0	\N	{"sl_set": 5, "sl_failed": 0, "positions_failed": 0, "positions_opened": 5}	2025-09-22 11:15:53.898354+00
4698	main_trader	HEALTHY	t	t	t	\N	5	0	0	\N	{"sl_set": 5, "sl_failed": 0, "positions_failed": 0, "positions_opened": 5}	2025-09-22 11:16:55.184369+00
4699	main_trader	HEALTHY	t	t	t	\N	5	0	0	\N	{"sl_set": 5, "sl_failed": 0, "positions_failed": 0, "positions_opened": 5}	2025-09-22 11:17:56.540754+00
4700	main_trader	HEALTHY	t	t	t	\N	5	0	0	\N	{"sl_set": 5, "sl_failed": 0, "positions_failed": 0, "positions_opened": 5}	2025-09-22 11:18:58.1015+00
4701	main_trader	HEALTHY	t	t	t	\N	6	0	0	\N	{"sl_set": 6, "sl_failed": 0, "positions_failed": 0, "positions_opened": 6}	2025-09-22 11:19:59.310111+00
4702	main_trader	HEALTHY	t	t	t	\N	6	0	0	\N	{"sl_set": 6, "sl_failed": 0, "positions_failed": 0, "positions_opened": 6}	2025-09-22 11:21:00.730927+00
4703	main_trader	HEALTHY	t	t	t	\N	6	0	0	\N	{"sl_set": 6, "sl_failed": 0, "positions_failed": 0, "positions_opened": 6}	2025-09-22 11:22:02.018789+00
4704	main_trader	HEALTHY	t	t	t	\N	6	0	0	\N	{"sl_set": 6, "sl_failed": 0, "positions_failed": 0, "positions_opened": 6}	2025-09-22 11:23:03.207673+00
4705	main_trader	HEALTHY	t	t	t	\N	6	0	0	\N	{"sl_set": 6, "sl_failed": 0, "positions_failed": 0, "positions_opened": 6}	2025-09-22 11:24:04.679473+00
4706	main_trader	HEALTHY	t	t	t	\N	6	0	0	\N	{"sl_set": 6, "sl_failed": 0, "positions_failed": 0, "positions_opened": 6}	2025-09-22 11:25:05.845754+00
4707	main_trader	HEALTHY	t	t	t	\N	6	0	0	\N	{"sl_set": 6, "sl_failed": 0, "positions_failed": 0, "positions_opened": 6}	2025-09-22 11:26:07.16137+00
4708	main_trader	HEALTHY	t	t	t	\N	6	0	0	\N	{"sl_set": 6, "sl_failed": 0, "positions_failed": 0, "positions_opened": 6}	2025-09-22 11:27:08.543062+00
4709	main_trader	HEALTHY	t	t	t	\N	6	0	0	\N	{"sl_set": 6, "sl_failed": 0, "positions_failed": 0, "positions_opened": 6}	2025-09-22 11:28:09.668635+00
4710	main_trader	HEALTHY	t	t	t	\N	6	0	0	\N	{"sl_set": 6, "sl_failed": 0, "positions_failed": 0, "positions_opened": 6}	2025-09-22 11:29:11.214097+00
4711	main_trader	HEALTHY	t	t	t	\N	6	0	0	\N	{"sl_set": 6, "sl_failed": 0, "positions_failed": 0, "positions_opened": 6}	2025-09-22 11:30:12.501788+00
4712	main_trader	HEALTHY	t	t	t	\N	6	0	0	\N	{"sl_set": 6, "sl_failed": 0, "positions_failed": 0, "positions_opened": 6}	2025-09-22 11:31:14.399022+00
4713	main_trader	HEALTHY	t	t	t	\N	6	0	0	\N	{"sl_set": 6, "sl_failed": 0, "positions_failed": 0, "positions_opened": 6}	2025-09-22 11:32:15.787794+00
4714	main_trader	HEALTHY	t	t	t	\N	6	0	0	\N	{"sl_set": 6, "sl_failed": 0, "positions_failed": 0, "positions_opened": 6}	2025-09-22 11:33:16.838501+00
4715	main_trader	HEALTHY	t	t	t	\N	6	0	0	\N	{"sl_set": 6, "sl_failed": 0, "positions_failed": 0, "positions_opened": 6}	2025-09-22 11:34:18.13101+00
4716	main_trader	HEALTHY	t	t	t	\N	6	0	0	\N	{"sl_set": 6, "sl_failed": 0, "positions_failed": 0, "positions_opened": 6}	2025-09-22 11:35:19.583266+00
4717	main_trader	HEALTHY	t	t	t	\N	6	0	0	\N	{"sl_set": 6, "sl_failed": 0, "positions_failed": 0, "positions_opened": 6}	2025-09-22 11:36:21.245565+00
4718	main_trader	HEALTHY	t	t	t	\N	6	0	0	\N	{"sl_set": 6, "sl_failed": 0, "positions_failed": 0, "positions_opened": 6}	2025-09-22 11:37:22.550044+00
4719	main_trader	HEALTHY	t	t	t	\N	6	0	0	\N	{"sl_set": 6, "sl_failed": 0, "positions_failed": 0, "positions_opened": 6}	2025-09-22 11:38:23.822798+00
4720	main_trader	HEALTHY	t	t	t	\N	6	0	0	\N	{"sl_set": 6, "sl_failed": 0, "positions_failed": 0, "positions_opened": 6}	2025-09-22 11:39:24.990123+00
4721	main_trader	HEALTHY	t	t	t	\N	6	0	0	\N	{"sl_set": 6, "sl_failed": 0, "positions_failed": 0, "positions_opened": 6}	2025-09-22 11:40:26.166989+00
4722	main_trader	HEALTHY	t	t	t	\N	6	0	0	\N	{"sl_set": 6, "sl_failed": 0, "positions_failed": 0, "positions_opened": 6}	2025-09-22 11:41:27.815546+00
4723	main_trader	HEALTHY	t	t	t	\N	6	0	0	\N	{"sl_set": 6, "sl_failed": 0, "positions_failed": 0, "positions_opened": 6}	2025-09-22 11:42:29.671114+00
4724	main_trader	HEALTHY	t	t	t	\N	6	0	0	\N	{"sl_set": 6, "sl_failed": 0, "positions_failed": 0, "positions_opened": 6}	2025-09-22 11:43:30.974249+00
4725	main_trader	HEALTHY	t	t	t	\N	6	0	0	\N	{"sl_set": 6, "sl_failed": 0, "positions_failed": 0, "positions_opened": 6}	2025-09-22 11:44:32.024556+00
4726	main_trader	HEALTHY	t	t	t	\N	6	0	0	\N	{"sl_set": 6, "sl_failed": 0, "positions_failed": 0, "positions_opened": 6}	2025-09-22 11:45:33.225202+00
4727	main_trader	HEALTHY	t	t	t	\N	6	0	0	\N	{"sl_set": 6, "sl_failed": 0, "positions_failed": 0, "positions_opened": 6}	2025-09-22 11:46:34.563417+00
4728	main_trader	HEALTHY	t	t	t	\N	6	0	0	\N	{"sl_set": 6, "sl_failed": 0, "positions_failed": 0, "positions_opened": 6}	2025-09-22 11:47:35.996474+00
4729	main_trader	HEALTHY	t	t	t	\N	6	0	0	\N	{"sl_set": 6, "sl_failed": 0, "positions_failed": 0, "positions_opened": 6}	2025-09-22 11:48:37.811066+00
4730	main_trader	HEALTHY	t	t	t	\N	6	0	0	\N	{"sl_set": 6, "sl_failed": 0, "positions_failed": 0, "positions_opened": 6}	2025-09-22 11:49:39.031579+00
4731	main_trader	HEALTHY	t	t	t	\N	7	0	0	\N	{"sl_set": 7, "sl_failed": 0, "positions_failed": 0, "positions_opened": 7}	2025-09-22 11:50:40.303648+00
4732	main_trader	HEALTHY	t	t	t	\N	7	0	0	\N	{"sl_set": 7, "sl_failed": 0, "positions_failed": 0, "positions_opened": 7}	2025-09-22 11:51:41.788384+00
4733	main_trader	HEALTHY	t	t	t	\N	7	0	0	\N	{"sl_set": 7, "sl_failed": 0, "positions_failed": 0, "positions_opened": 7}	2025-09-22 11:52:43.001345+00
4734	main_trader	HEALTHY	t	t	t	\N	7	0	0	\N	{"sl_set": 7, "sl_failed": 0, "positions_failed": 0, "positions_opened": 7}	2025-09-22 11:53:44.050694+00
4735	main_trader	HEALTHY	t	t	t	\N	7	0	0	\N	{"sl_set": 7, "sl_failed": 0, "positions_failed": 0, "positions_opened": 7}	2025-09-22 11:54:45.297132+00
4736	main_trader	HEALTHY	t	t	t	\N	7	0	0	\N	{"sl_set": 7, "sl_failed": 0, "positions_failed": 0, "positions_opened": 7}	2025-09-22 11:55:46.483375+00
4737	main_trader	HEALTHY	t	t	t	\N	7	0	0	\N	{"sl_set": 7, "sl_failed": 0, "positions_failed": 0, "positions_opened": 7}	2025-09-22 11:56:48.601865+00
4738	main_trader	HEALTHY	t	t	t	\N	7	0	0	\N	{"sl_set": 7, "sl_failed": 0, "positions_failed": 0, "positions_opened": 7}	2025-09-22 11:57:50.04426+00
4739	main_trader	HEALTHY	t	t	t	\N	7	0	0	\N	{"sl_set": 7, "sl_failed": 0, "positions_failed": 0, "positions_opened": 7}	2025-09-22 11:58:51.274261+00
4740	main_trader	HEALTHY	t	t	t	\N	7	0	0	\N	{"sl_set": 7, "sl_failed": 0, "positions_failed": 0, "positions_opened": 7}	2025-09-22 11:59:52.369819+00
4741	main_trader	HEALTHY	t	t	t	\N	7	0	0	\N	{"sl_set": 7, "sl_failed": 0, "positions_failed": 0, "positions_opened": 7}	2025-09-22 12:00:53.417378+00
4742	main_trader	HEALTHY	t	t	t	\N	7	0	0	\N	{"sl_set": 7, "sl_failed": 0, "positions_failed": 0, "positions_opened": 7}	2025-09-22 12:01:54.870488+00
4743	main_trader	HEALTHY	t	t	t	\N	7	0	0	\N	{"sl_set": 7, "sl_failed": 0, "positions_failed": 0, "positions_opened": 7}	2025-09-22 12:02:56.027177+00
4744	main_trader	HEALTHY	t	t	t	\N	7	0	0	\N	{"sl_set": 7, "sl_failed": 0, "positions_failed": 0, "positions_opened": 7}	2025-09-22 12:03:57.27508+00
4745	main_trader	HEALTHY	t	t	t	\N	7	0	0	\N	{"sl_set": 7, "sl_failed": 0, "positions_failed": 0, "positions_opened": 7}	2025-09-22 12:04:58.552055+00
4746	main_trader	HEALTHY	t	t	t	\N	7	0	0	\N	{"sl_set": 7, "sl_failed": 0, "positions_failed": 0, "positions_opened": 7}	2025-09-22 12:05:59.744568+00
4747	main_trader	HEALTHY	t	t	t	\N	9	0	0	\N	{"sl_set": 9, "sl_failed": 0, "positions_failed": 1, "positions_opened": 9}	2025-09-22 12:07:00.921585+00
4748	main_trader	HEALTHY	t	t	t	\N	11	0	0	\N	{"sl_set": 12, "sl_failed": 0, "positions_failed": 1, "positions_opened": 12}	2025-09-22 12:08:02.062571+00
4749	main_trader	HEALTHY	t	t	t	\N	14	0	0	\N	{"sl_set": 14, "sl_failed": 0, "positions_failed": 1, "positions_opened": 15}	2025-09-22 12:09:03.20541+00
4750	main_trader	HEALTHY	t	t	t	\N	15	0	0	\N	{"sl_set": 15, "sl_failed": 0, "positions_failed": 3, "positions_opened": 15}	2025-09-22 12:10:04.96614+00
4751	main_trader	HEALTHY	t	t	t	\N	15	0	0	\N	{"sl_set": 15, "sl_failed": 0, "positions_failed": 3, "positions_opened": 15}	2025-09-22 12:11:07.135891+00
4752	main_trader	HEALTHY	t	t	t	\N	15	0	0	\N	{"sl_set": 15, "sl_failed": 0, "positions_failed": 3, "positions_opened": 15}	2025-09-22 12:12:09.739357+00
4753	main_trader	HEALTHY	t	t	t	\N	15	0	0	\N	{"sl_set": 15, "sl_failed": 0, "positions_failed": 3, "positions_opened": 15}	2025-09-22 12:13:11.199396+00
4754	main_trader	HEALTHY	t	t	t	\N	15	0	0	\N	{"sl_set": 15, "sl_failed": 0, "positions_failed": 3, "positions_opened": 15}	2025-09-22 12:14:12.358905+00
4755	main_trader	HEALTHY	t	t	t	\N	15	0	0	\N	{"sl_set": 15, "sl_failed": 0, "positions_failed": 3, "positions_opened": 15}	2025-09-22 12:15:13.470001+00
4756	main_trader	HEALTHY	t	t	t	\N	15	0	0	\N	{"sl_set": 15, "sl_failed": 0, "positions_failed": 3, "positions_opened": 15}	2025-09-22 12:16:14.963602+00
4757	main_trader	HEALTHY	t	t	t	\N	15	0	0	\N	{"sl_set": 15, "sl_failed": 0, "positions_failed": 3, "positions_opened": 15}	2025-09-22 12:17:16.513334+00
4758	main_trader	HEALTHY	t	t	t	\N	15	0	0	\N	{"sl_set": 15, "sl_failed": 0, "positions_failed": 3, "positions_opened": 15}	2025-09-22 12:18:17.734184+00
4759	main_trader	HEALTHY	t	t	t	\N	15	0	0	\N	{"sl_set": 15, "sl_failed": 0, "positions_failed": 3, "positions_opened": 15}	2025-09-22 12:19:19.015929+00
4760	main_trader	HEALTHY	t	t	t	\N	16	0	0	\N	{"sl_set": 16, "sl_failed": 0, "positions_failed": 3, "positions_opened": 17}	2025-09-22 12:20:19.956814+00
4761	main_trader	HEALTHY	t	t	t	\N	19	0	0	\N	{"sl_set": 19, "sl_failed": 0, "positions_failed": 3, "positions_opened": 19}	2025-09-22 12:21:21.422051+00
4762	main_trader	HEALTHY	t	t	t	\N	22	0	0	\N	{"sl_set": 22, "sl_failed": 0, "positions_failed": 3, "positions_opened": 22}	2025-09-22 12:22:23.459635+00
4763	main_trader	HEALTHY	t	t	t	\N	24	0	0	\N	{"sl_set": 24, "sl_failed": 0, "positions_failed": 3, "positions_opened": 24}	2025-09-22 12:23:25.472563+00
4764	main_trader	HEALTHY	t	t	t	\N	25	0	0	\N	{"sl_set": 26, "sl_failed": 0, "positions_failed": 5, "positions_opened": 26}	2025-09-22 12:24:26.911572+00
4765	main_trader	HEALTHY	t	t	t	\N	26	0	0	\N	{"sl_set": 26, "sl_failed": 0, "positions_failed": 5, "positions_opened": 26}	2025-09-22 12:25:28.13208+00
4766	main_trader	HEALTHY	t	t	t	\N	26	0	0	\N	{"sl_set": 26, "sl_failed": 0, "positions_failed": 5, "positions_opened": 26}	2025-09-22 12:26:29.195008+00
4767	main_trader	HEALTHY	t	t	t	\N	26	0	0	\N	{"sl_set": 26, "sl_failed": 0, "positions_failed": 5, "positions_opened": 26}	2025-09-22 12:27:30.358561+00
4768	main_trader	HEALTHY	t	t	t	\N	26	0	0	\N	{"sl_set": 26, "sl_failed": 0, "positions_failed": 5, "positions_opened": 26}	2025-09-22 12:28:33.451706+00
4769	main_trader	HEALTHY	t	t	t	\N	26	0	0	\N	{"sl_set": 26, "sl_failed": 0, "positions_failed": 5, "positions_opened": 26}	2025-09-22 12:29:35.211023+00
4770	main_trader	HEALTHY	t	t	t	\N	26	0	0	\N	{"sl_set": 26, "sl_failed": 0, "positions_failed": 5, "positions_opened": 26}	2025-09-22 12:30:36.537394+00
4771	main_trader	HEALTHY	t	t	t	\N	26	0	0	\N	{"sl_set": 26, "sl_failed": 0, "positions_failed": 5, "positions_opened": 26}	2025-09-22 12:31:37.790448+00
4772	main_trader	HEALTHY	t	t	t	\N	26	0	0	\N	{"sl_set": 26, "sl_failed": 0, "positions_failed": 5, "positions_opened": 26}	2025-09-22 12:32:38.916684+00
4773	main_trader	HEALTHY	t	t	t	\N	26	0	0	\N	{"sl_set": 26, "sl_failed": 0, "positions_failed": 5, "positions_opened": 26}	2025-09-22 12:33:40.323988+00
4774	main_trader	HEALTHY	t	t	t	\N	26	0	0	\N	{"sl_set": 26, "sl_failed": 0, "positions_failed": 5, "positions_opened": 26}	2025-09-22 12:34:41.697274+00
4775	main_trader	HEALTHY	t	t	t	\N	29	0	0	\N	{"sl_set": 29, "sl_failed": 0, "positions_failed": 5, "positions_opened": 29}	2025-09-22 12:35:43.01081+00
4776	main_trader	HEALTHY	t	t	t	\N	32	0	0	\N	{"sl_set": 32, "sl_failed": 0, "positions_failed": 5, "positions_opened": 32}	2025-09-22 12:36:44.067673+00
4777	main_trader	HEALTHY	t	t	t	\N	34	0	0	\N	{"sl_set": 34, "sl_failed": 0, "positions_failed": 5, "positions_opened": 34}	2025-09-22 12:37:45.049174+00
4778	main_trader	HEALTHY	t	t	t	\N	35	0	0	\N	{"sl_set": 35, "sl_failed": 0, "positions_failed": 6, "positions_opened": 35}	2025-09-22 12:38:46.506627+00
4779	main_trader	HEALTHY	t	t	t	\N	35	0	0	\N	{"sl_set": 35, "sl_failed": 0, "positions_failed": 6, "positions_opened": 35}	2025-09-22 12:39:47.731823+00
4780	main_trader	HEALTHY	t	t	t	\N	35	0	0	\N	{"sl_set": 35, "sl_failed": 0, "positions_failed": 6, "positions_opened": 35}	2025-09-22 12:40:48.990718+00
4781	main_trader	HEALTHY	t	t	t	\N	35	0	0	\N	{"sl_set": 35, "sl_failed": 0, "positions_failed": 6, "positions_opened": 35}	2025-09-22 12:41:50.161073+00
4782	main_trader	HEALTHY	t	t	t	\N	35	0	0	\N	{"sl_set": 35, "sl_failed": 0, "positions_failed": 6, "positions_opened": 35}	2025-09-22 12:42:51.28877+00
4783	main_trader	HEALTHY	t	t	t	\N	35	0	0	\N	{"sl_set": 35, "sl_failed": 0, "positions_failed": 6, "positions_opened": 35}	2025-09-22 12:43:54.05139+00
4784	main_trader	HEALTHY	t	t	t	\N	35	0	0	\N	{"sl_set": 35, "sl_failed": 0, "positions_failed": 6, "positions_opened": 35}	2025-09-22 12:44:55.417372+00
4785	main_trader	HEALTHY	t	t	t	\N	35	0	0	\N	{"sl_set": 35, "sl_failed": 0, "positions_failed": 6, "positions_opened": 35}	2025-09-22 12:45:56.671102+00
4786	main_trader	HEALTHY	t	t	t	\N	35	0	0	\N	{"sl_set": 35, "sl_failed": 0, "positions_failed": 6, "positions_opened": 35}	2025-09-22 12:46:57.731465+00
4787	main_trader	HEALTHY	t	t	t	\N	35	0	0	\N	{"sl_set": 35, "sl_failed": 0, "positions_failed": 6, "positions_opened": 35}	2025-09-22 12:47:58.987467+00
4788	main_trader	HEALTHY	t	t	t	\N	35	0	0	\N	{"sl_set": 35, "sl_failed": 0, "positions_failed": 6, "positions_opened": 35}	2025-09-22 12:49:00.706248+00
4789	main_trader	HEALTHY	t	t	t	\N	35	0	0	\N	{"sl_set": 35, "sl_failed": 0, "positions_failed": 6, "positions_opened": 35}	2025-09-22 12:50:03.207365+00
4790	main_trader	HEALTHY	t	t	t	\N	38	0	0	\N	{"sl_set": 38, "sl_failed": 0, "positions_failed": 6, "positions_opened": 38}	2025-09-22 12:51:04.711634+00
4791	main_trader	HEALTHY	t	t	t	\N	41	0	0	\N	{"sl_set": 41, "sl_failed": 0, "positions_failed": 6, "positions_opened": 41}	2025-09-22 12:52:06.314141+00
4792	main_trader	HEALTHY	t	t	t	\N	42	0	0	\N	{"sl_set": 42, "sl_failed": 0, "positions_failed": 8, "positions_opened": 42}	2025-09-22 12:53:07.770231+00
4793	main_trader	HEALTHY	t	t	t	\N	45	0	0	\N	{"sl_set": 45, "sl_failed": 0, "positions_failed": 8, "positions_opened": 45}	2025-09-22 12:54:09.406631+00
4794	main_trader	HEALTHY	t	t	t	\N	47	0	0	\N	{"sl_set": 47, "sl_failed": 0, "positions_failed": 8, "positions_opened": 47}	2025-09-22 12:55:10.58421+00
4795	main_trader	HEALTHY	t	t	t	\N	47	0	0	\N	{"sl_set": 47, "sl_failed": 0, "positions_failed": 8, "positions_opened": 47}	2025-09-22 12:56:11.833156+00
4796	main_trader	HEALTHY	t	t	t	\N	47	0	0	\N	{"sl_set": 47, "sl_failed": 0, "positions_failed": 8, "positions_opened": 47}	2025-09-22 12:57:12.96157+00
4797	main_trader	HEALTHY	t	t	t	\N	47	0	0	\N	{"sl_set": 47, "sl_failed": 0, "positions_failed": 8, "positions_opened": 47}	2025-09-22 12:58:14.134429+00
4798	main_trader	HEALTHY	t	t	t	\N	47	0	0	\N	{"sl_set": 47, "sl_failed": 0, "positions_failed": 8, "positions_opened": 47}	2025-09-22 12:59:15.904239+00
4799	main_trader	HEALTHY	t	t	t	\N	47	0	0	\N	{"sl_set": 47, "sl_failed": 0, "positions_failed": 8, "positions_opened": 47}	2025-09-22 13:00:17.457929+00
4800	main_trader	HEALTHY	t	t	t	\N	47	0	0	\N	{"sl_set": 47, "sl_failed": 0, "positions_failed": 8, "positions_opened": 47}	2025-09-22 13:01:18.78228+00
4801	main_trader	HEALTHY	t	t	t	\N	47	0	0	\N	{"sl_set": 47, "sl_failed": 0, "positions_failed": 8, "positions_opened": 47}	2025-09-22 13:02:20.073842+00
4802	main_trader	HEALTHY	t	t	t	\N	47	0	0	\N	{"sl_set": 47, "sl_failed": 0, "positions_failed": 8, "positions_opened": 47}	2025-09-22 13:03:21.527978+00
4803	main_trader	HEALTHY	t	t	t	\N	47	0	0	\N	{"sl_set": 47, "sl_failed": 0, "positions_failed": 8, "positions_opened": 47}	2025-09-22 13:04:22.920983+00
4804	main_trader	HEALTHY	t	t	t	\N	47	0	0	\N	{"sl_set": 47, "sl_failed": 0, "positions_failed": 8, "positions_opened": 47}	2025-09-22 13:05:24.168138+00
4805	main_trader	HEALTHY	t	t	t	\N	50	0	0	\N	{"sl_set": 50, "sl_failed": 0, "positions_failed": 8, "positions_opened": 50}	2025-09-22 13:06:25.825343+00
4806	main_trader	HEALTHY	t	t	t	\N	52	0	0	\N	{"sl_set": 52, "sl_failed": 0, "positions_failed": 9, "positions_opened": 52}	2025-09-22 13:07:27.258202+00
4807	main_trader	HEALTHY	t	t	t	\N	52	0	0	\N	{"sl_set": 52, "sl_failed": 0, "positions_failed": 10, "positions_opened": 52}	2025-09-22 13:08:28.813976+00
4808	main_trader	HEALTHY	t	t	t	\N	52	0	0	\N	{"sl_set": 52, "sl_failed": 0, "positions_failed": 10, "positions_opened": 52}	2025-09-22 13:09:30.538989+00
4809	main_trader	HEALTHY	t	t	t	\N	52	0	0	\N	{"sl_set": 52, "sl_failed": 0, "positions_failed": 10, "positions_opened": 52}	2025-09-22 13:10:32.192308+00
4810	main_trader	HEALTHY	t	t	t	\N	52	0	0	\N	{"sl_set": 52, "sl_failed": 0, "positions_failed": 10, "positions_opened": 52}	2025-09-22 13:11:33.340622+00
4811	main_trader	HEALTHY	t	t	t	\N	52	0	0	\N	{"sl_set": 52, "sl_failed": 0, "positions_failed": 10, "positions_opened": 52}	2025-09-22 13:12:34.69885+00
4812	main_trader	HEALTHY	t	t	t	\N	52	0	0	\N	{"sl_set": 52, "sl_failed": 0, "positions_failed": 10, "positions_opened": 52}	2025-09-22 13:13:35.908666+00
4813	main_trader	HEALTHY	t	t	t	\N	52	0	0	\N	{"sl_set": 52, "sl_failed": 0, "positions_failed": 10, "positions_opened": 52}	2025-09-22 13:14:37.756038+00
4814	main_trader	HEALTHY	t	t	t	\N	52	0	0	\N	{"sl_set": 52, "sl_failed": 0, "positions_failed": 10, "positions_opened": 52}	2025-09-22 13:15:39.40254+00
4815	main_trader	HEALTHY	t	t	t	\N	52	0	0	\N	{"sl_set": 52, "sl_failed": 0, "positions_failed": 10, "positions_opened": 52}	2025-09-22 13:16:40.959889+00
4816	main_trader	HEALTHY	t	t	t	\N	52	0	0	\N	{"sl_set": 52, "sl_failed": 0, "positions_failed": 10, "positions_opened": 52}	2025-09-22 13:17:42.128743+00
4817	main_trader	HEALTHY	t	t	t	\N	52	0	0	\N	{"sl_set": 52, "sl_failed": 0, "positions_failed": 10, "positions_opened": 52}	2025-09-22 13:18:43.262657+00
4818	main_trader	HEALTHY	t	t	t	\N	52	0	0	\N	{"sl_set": 52, "sl_failed": 0, "positions_failed": 10, "positions_opened": 52}	2025-09-22 13:19:45.026316+00
4819	main_trader	HEALTHY	t	t	t	\N	54	0	0	\N	{"sl_set": 55, "sl_failed": 0, "positions_failed": 10, "positions_opened": 55}	2025-09-22 13:20:46.490223+00
4820	main_trader	HEALTHY	t	t	t	\N	56	0	0	\N	{"sl_set": 57, "sl_failed": 0, "positions_failed": 11, "positions_opened": 57}	2025-09-22 13:21:47.871429+00
4821	main_trader	HEALTHY	t	t	t	\N	59	0	0	\N	{"sl_set": 59, "sl_failed": 0, "positions_failed": 11, "positions_opened": 60}	2025-09-22 13:22:49.101292+00
4822	main_trader	HEALTHY	t	t	t	\N	61	0	0	\N	{"sl_set": 61, "sl_failed": 0, "positions_failed": 11, "positions_opened": 61}	2025-09-22 13:23:50.463562+00
4823	main_trader	HEALTHY	t	t	t	\N	61	0	0	\N	{"sl_set": 61, "sl_failed": 0, "positions_failed": 11, "positions_opened": 61}	2025-09-22 13:24:51.842037+00
4824	main_trader	HEALTHY	t	t	t	\N	61	0	0	\N	{"sl_set": 61, "sl_failed": 0, "positions_failed": 11, "positions_opened": 61}	2025-09-22 13:25:54.269158+00
4825	main_trader	HEALTHY	t	t	t	\N	61	0	0	\N	{"sl_set": 61, "sl_failed": 0, "positions_failed": 11, "positions_opened": 61}	2025-09-22 13:26:55.548927+00
4826	main_trader	HEALTHY	t	t	t	\N	61	0	0	\N	{"sl_set": 61, "sl_failed": 0, "positions_failed": 11, "positions_opened": 61}	2025-09-22 13:27:56.707696+00
4827	main_trader	HEALTHY	t	t	t	\N	61	0	0	\N	{"sl_set": 61, "sl_failed": 0, "positions_failed": 11, "positions_opened": 61}	2025-09-22 13:28:58.10919+00
4828	main_trader	HEALTHY	t	t	t	\N	61	0	0	\N	{"sl_set": 61, "sl_failed": 0, "positions_failed": 11, "positions_opened": 61}	2025-09-22 13:29:59.282398+00
4829	main_trader	HEALTHY	t	t	t	\N	61	0	0	\N	{"sl_set": 61, "sl_failed": 0, "positions_failed": 11, "positions_opened": 61}	2025-09-22 13:31:00.872682+00
4830	main_trader	HEALTHY	t	t	t	\N	61	0	0	\N	{"sl_set": 61, "sl_failed": 0, "positions_failed": 11, "positions_opened": 61}	2025-09-22 13:32:02.112659+00
4831	main_trader	HEALTHY	t	t	t	\N	61	0	0	\N	{"sl_set": 61, "sl_failed": 0, "positions_failed": 11, "positions_opened": 61}	2025-09-22 13:33:03.238668+00
4832	main_trader	HEALTHY	t	t	t	\N	61	0	0	\N	{"sl_set": 61, "sl_failed": 0, "positions_failed": 11, "positions_opened": 61}	2025-09-22 13:34:04.492186+00
4833	main_trader	HEALTHY	t	t	t	\N	61	0	0	\N	{"sl_set": 61, "sl_failed": 0, "positions_failed": 11, "positions_opened": 61}	2025-09-22 13:35:05.647474+00
4834	main_trader	HEALTHY	t	t	t	\N	63	0	0	\N	{"sl_set": 63, "sl_failed": 0, "positions_failed": 12, "positions_opened": 63}	2025-09-22 13:36:07.399755+00
4835	main_trader	HEALTHY	t	t	t	\N	66	0	0	\N	{"sl_set": 66, "sl_failed": 0, "positions_failed": 12, "positions_opened": 66}	2025-09-22 13:37:08.644447+00
4836	main_trader	HEALTHY	t	t	t	\N	68	0	0	\N	{"sl_set": 68, "sl_failed": 0, "positions_failed": 13, "positions_opened": 68}	2025-09-22 13:38:10.134241+00
4837	main_trader	HEALTHY	t	t	t	\N	68	0	0	\N	{"sl_set": 68, "sl_failed": 0, "positions_failed": 13, "positions_opened": 68}	2025-09-22 13:39:11.256132+00
4838	main_trader	HEALTHY	t	t	t	\N	68	0	0	\N	{"sl_set": 68, "sl_failed": 0, "positions_failed": 13, "positions_opened": 68}	2025-09-22 13:40:12.688947+00
4839	main_trader	HEALTHY	t	t	t	\N	68	0	0	\N	{"sl_set": 68, "sl_failed": 0, "positions_failed": 13, "positions_opened": 68}	2025-09-22 13:41:14.338663+00
4840	main_trader	HEALTHY	t	t	t	\N	68	0	0	\N	{"sl_set": 68, "sl_failed": 0, "positions_failed": 13, "positions_opened": 68}	2025-09-22 13:42:15.525617+00
4841	main_trader	HEALTHY	t	t	t	\N	68	0	0	\N	{"sl_set": 68, "sl_failed": 0, "positions_failed": 13, "positions_opened": 68}	2025-09-22 13:43:17.008082+00
4842	main_trader	HEALTHY	t	t	t	\N	68	0	0	\N	{"sl_set": 68, "sl_failed": 0, "positions_failed": 13, "positions_opened": 68}	2025-09-22 13:44:18.248088+00
4843	main_trader	HEALTHY	t	t	t	\N	68	0	0	\N	{"sl_set": 68, "sl_failed": 0, "positions_failed": 13, "positions_opened": 68}	2025-09-22 13:45:19.40013+00
4844	main_trader	HEALTHY	t	t	t	\N	68	0	0	\N	{"sl_set": 68, "sl_failed": 0, "positions_failed": 13, "positions_opened": 68}	2025-09-22 13:46:21.262669+00
4845	main_trader	HEALTHY	t	t	t	\N	68	0	0	\N	{"sl_set": 68, "sl_failed": 0, "positions_failed": 13, "positions_opened": 68}	2025-09-22 13:47:22.522336+00
4846	main_trader	HEALTHY	t	t	t	\N	68	0	0	\N	{"sl_set": 68, "sl_failed": 0, "positions_failed": 13, "positions_opened": 68}	2025-09-22 13:48:23.854483+00
4847	main_trader	HEALTHY	t	t	t	\N	68	0	0	\N	{"sl_set": 68, "sl_failed": 0, "positions_failed": 13, "positions_opened": 68}	2025-09-22 13:49:25.103004+00
4848	main_trader	HEALTHY	t	t	t	\N	68	0	0	\N	{"sl_set": 68, "sl_failed": 0, "positions_failed": 13, "positions_opened": 68}	2025-09-22 13:50:26.31782+00
4849	main_trader	HEALTHY	t	t	t	\N	71	0	0	\N	{"sl_set": 71, "sl_failed": 0, "positions_failed": 13, "positions_opened": 71}	2025-09-22 13:51:27.927316+00
4850	main_trader	HEALTHY	t	t	t	\N	72	0	0	\N	{"sl_set": 72, "sl_failed": 0, "positions_failed": 14, "positions_opened": 72}	2025-09-22 13:52:29.254463+00
4851	main_trader	HEALTHY	t	t	t	\N	75	0	0	\N	{"sl_set": 75, "sl_failed": 0, "positions_failed": 14, "positions_opened": 75}	2025-09-22 13:53:30.431983+00
4852	main_trader	HEALTHY	t	t	t	\N	77	0	0	\N	{"sl_set": 77, "sl_failed": 0, "positions_failed": 14, "positions_opened": 77}	2025-09-22 13:54:31.659992+00
4853	main_trader	HEALTHY	t	t	t	\N	77	0	0	\N	{"sl_set": 77, "sl_failed": 0, "positions_failed": 14, "positions_opened": 77}	2025-09-22 13:55:33.32884+00
4854	main_trader	HEALTHY	t	t	t	\N	77	0	0	\N	{"sl_set": 77, "sl_failed": 0, "positions_failed": 14, "positions_opened": 77}	2025-09-22 13:56:34.812327+00
4855	main_trader	HEALTHY	t	t	t	\N	77	0	0	\N	{"sl_set": 77, "sl_failed": 0, "positions_failed": 14, "positions_opened": 77}	2025-09-22 13:57:36.352108+00
4856	main_trader	HEALTHY	t	t	t	\N	77	0	0	\N	{"sl_set": 77, "sl_failed": 0, "positions_failed": 14, "positions_opened": 77}	2025-09-22 13:58:37.721344+00
4857	main_trader	HEALTHY	t	t	t	\N	77	0	0	\N	{"sl_set": 77, "sl_failed": 0, "positions_failed": 14, "positions_opened": 77}	2025-09-22 13:59:39.039549+00
4858	main_trader	HEALTHY	t	t	t	\N	77	0	0	\N	{"sl_set": 77, "sl_failed": 0, "positions_failed": 14, "positions_opened": 77}	2025-09-22 14:00:40.736735+00
4859	main_trader	HEALTHY	t	t	t	\N	77	0	0	\N	{"sl_set": 77, "sl_failed": 0, "positions_failed": 14, "positions_opened": 77}	2025-09-22 14:01:42.277543+00
4860	main_trader	HEALTHY	t	t	t	\N	77	0	0	\N	{"sl_set": 77, "sl_failed": 0, "positions_failed": 14, "positions_opened": 77}	2025-09-22 14:02:43.733922+00
4861	main_trader	HEALTHY	t	t	t	\N	77	0	0	\N	{"sl_set": 77, "sl_failed": 0, "positions_failed": 14, "positions_opened": 77}	2025-09-22 14:03:44.990364+00
4862	main_trader	HEALTHY	t	t	t	\N	77	0	0	\N	{"sl_set": 77, "sl_failed": 0, "positions_failed": 14, "positions_opened": 77}	2025-09-22 14:04:46.658346+00
4863	main_trader	HEALTHY	t	t	t	\N	79	0	0	\N	{"sl_set": 79, "sl_failed": 0, "positions_failed": 15, "positions_opened": 79}	2025-09-22 14:05:47.853298+00
4864	main_trader	HEALTHY	t	t	t	\N	81	0	0	\N	{"sl_set": 81, "sl_failed": 0, "positions_failed": 16, "positions_opened": 81}	2025-09-22 14:06:49.886997+00
4865	main_trader	HEALTHY	t	t	t	\N	84	0	0	\N	{"sl_set": 84, "sl_failed": 0, "positions_failed": 16, "positions_opened": 84}	2025-09-22 14:07:50.995645+00
4866	main_trader	HEALTHY	t	t	t	\N	86	0	0	\N	{"sl_set": 86, "sl_failed": 0, "positions_failed": 17, "positions_opened": 86}	2025-09-22 14:08:52.189141+00
4867	main_trader	HEALTHY	t	t	t	\N	88	0	0	\N	{"sl_set": 88, "sl_failed": 0, "positions_failed": 18, "positions_opened": 88}	2025-09-22 14:09:53.198944+00
4868	main_trader	HEALTHY	t	t	t	\N	91	0	0	\N	{"sl_set": 91, "sl_failed": 0, "positions_failed": 18, "positions_opened": 91}	2025-09-22 14:10:54.630423+00
4869	main_trader	HEALTHY	t	t	t	\N	92	0	0	\N	{"sl_set": 92, "sl_failed": 0, "positions_failed": 18, "positions_opened": 92}	2025-09-22 14:11:56.268491+00
4870	main_trader	HEALTHY	t	t	t	\N	92	0	0	\N	{"sl_set": 92, "sl_failed": 0, "positions_failed": 18, "positions_opened": 92}	2025-09-22 14:12:57.864547+00
4871	main_trader	HEALTHY	t	t	t	\N	92	0	0	\N	{"sl_set": 92, "sl_failed": 0, "positions_failed": 18, "positions_opened": 92}	2025-09-22 14:13:59.526895+00
4872	main_trader	HEALTHY	t	t	t	\N	92	0	0	\N	{"sl_set": 92, "sl_failed": 0, "positions_failed": 18, "positions_opened": 92}	2025-09-22 14:15:01.230774+00
4873	main_trader	HEALTHY	t	t	t	\N	92	0	0	\N	{"sl_set": 92, "sl_failed": 0, "positions_failed": 18, "positions_opened": 92}	2025-09-22 14:16:02.670748+00
4874	main_trader	HEALTHY	t	t	t	\N	92	0	0	\N	{"sl_set": 92, "sl_failed": 0, "positions_failed": 18, "positions_opened": 92}	2025-09-22 14:17:04.930895+00
4875	main_trader	HEALTHY	t	t	t	\N	92	0	0	\N	{"sl_set": 92, "sl_failed": 0, "positions_failed": 18, "positions_opened": 92}	2025-09-22 14:18:06.413705+00
4876	main_trader	HEALTHY	t	t	t	\N	92	0	0	\N	{"sl_set": 92, "sl_failed": 0, "positions_failed": 18, "positions_opened": 92}	2025-09-22 14:19:07.763151+00
4877	main_trader	HEALTHY	t	t	t	\N	92	0	0	\N	{"sl_set": 92, "sl_failed": 0, "positions_failed": 18, "positions_opened": 92}	2025-09-22 14:20:09.484862+00
4878	main_trader	HEALTHY	t	t	t	\N	95	0	0	\N	{"sl_set": 95, "sl_failed": 0, "positions_failed": 18, "positions_opened": 95}	2025-09-22 14:21:10.696767+00
4879	main_trader	HEALTHY	t	t	t	\N	98	0	0	\N	{"sl_set": 98, "sl_failed": 0, "positions_failed": 18, "positions_opened": 98}	2025-09-22 14:22:12.243581+00
4880	main_trader	HEALTHY	t	t	t	\N	101	0	0	\N	{"sl_set": 101, "sl_failed": 0, "positions_failed": 18, "positions_opened": 101}	2025-09-22 14:23:13.671164+00
4881	main_trader	HEALTHY	t	t	t	\N	104	0	0	\N	{"sl_set": 104, "sl_failed": 0, "positions_failed": 18, "positions_opened": 104}	2025-09-22 14:24:14.770796+00
4882	main_trader	HEALTHY	t	t	t	\N	107	0	0	\N	{"sl_set": 107, "sl_failed": 0, "positions_failed": 18, "positions_opened": 107}	2025-09-22 14:25:15.952275+00
4883	main_trader	HEALTHY	t	t	t	\N	109	0	0	\N	{"sl_set": 109, "sl_failed": 0, "positions_failed": 18, "positions_opened": 109}	2025-09-22 14:26:17.540193+00
4884	main_trader	HEALTHY	t	t	t	\N	112	0	0	\N	{"sl_set": 112, "sl_failed": 0, "positions_failed": 18, "positions_opened": 112}	2025-09-22 14:27:18.893585+00
4885	main_trader	HEALTHY	t	t	t	\N	114	0	0	\N	{"sl_set": 114, "sl_failed": 0, "positions_failed": 18, "positions_opened": 114}	2025-09-22 14:28:20.145226+00
4886	main_trader	HEALTHY	t	t	t	\N	117	0	0	\N	{"sl_set": 117, "sl_failed": 0, "positions_failed": 18, "positions_opened": 117}	2025-09-22 14:29:21.568686+00
4887	main_trader	HEALTHY	t	t	t	\N	118	0	0	\N	{"sl_set": 118, "sl_failed": 0, "positions_failed": 18, "positions_opened": 118}	2025-09-22 14:30:23.099897+00
4888	main_trader	HEALTHY	t	t	t	\N	118	0	0	\N	{"sl_set": 118, "sl_failed": 0, "positions_failed": 18, "positions_opened": 118}	2025-09-22 14:31:24.786293+00
4889	main_trader	HEALTHY	t	t	t	\N	118	0	0	\N	{"sl_set": 118, "sl_failed": 0, "positions_failed": 18, "positions_opened": 118}	2025-09-22 14:32:27.312288+00
4890	main_trader	HEALTHY	t	t	t	\N	118	0	0	\N	{"sl_set": 118, "sl_failed": 0, "positions_failed": 18, "positions_opened": 118}	2025-09-22 14:33:29.063136+00
4891	main_trader	HEALTHY	t	t	t	\N	118	0	0	\N	{"sl_set": 118, "sl_failed": 0, "positions_failed": 18, "positions_opened": 118}	2025-09-22 14:34:30.598666+00
4892	main_trader	HEALTHY	t	t	t	\N	119	0	0	\N	{"sl_set": 119, "sl_failed": 0, "positions_failed": 18, "positions_opened": 120}	2025-09-22 14:35:33.656536+00
4893	main_trader	HEALTHY	t	t	t	\N	121	0	0	\N	{"sl_set": 121, "sl_failed": 0, "positions_failed": 19, "positions_opened": 121}	2025-09-22 14:36:35.07367+00
4894	main_trader	HEALTHY	t	t	t	\N	123	0	0	\N	{"sl_set": 124, "sl_failed": 0, "positions_failed": 19, "positions_opened": 124}	2025-09-22 14:37:36.303189+00
4895	main_trader	HEALTHY	t	t	t	\N	126	0	0	\N	{"sl_set": 126, "sl_failed": 0, "positions_failed": 19, "positions_opened": 127}	2025-09-22 14:38:37.684564+00
4896	main_trader	HEALTHY	t	t	t	\N	129	0	0	\N	{"sl_set": 129, "sl_failed": 0, "positions_failed": 19, "positions_opened": 129}	2025-09-22 14:39:39.067437+00
4897	main_trader	HEALTHY	t	t	t	\N	131	0	0	\N	{"sl_set": 131, "sl_failed": 0, "positions_failed": 20, "positions_opened": 131}	2025-09-22 14:40:41.747601+00
4898	main_trader	HEALTHY	t	t	t	\N	133	0	0	\N	{"sl_set": 133, "sl_failed": 0, "positions_failed": 21, "positions_opened": 133}	2025-09-22 14:41:43.479737+00
4899	main_trader	HEALTHY	t	t	t	\N	136	0	0	\N	{"sl_set": 136, "sl_failed": 0, "positions_failed": 21, "positions_opened": 136}	2025-09-22 14:42:45.028879+00
4900	main_trader	HEALTHY	t	t	t	\N	136	0	0	\N	{"sl_set": 136, "sl_failed": 0, "positions_failed": 21, "positions_opened": 136}	2025-09-22 14:43:46.487496+00
4901	main_trader	HEALTHY	t	t	t	\N	136	0	0	\N	{"sl_set": 136, "sl_failed": 0, "positions_failed": 21, "positions_opened": 136}	2025-09-22 14:44:48.584318+00
4902	main_trader	HEALTHY	t	t	t	\N	136	0	0	\N	{"sl_set": 136, "sl_failed": 0, "positions_failed": 21, "positions_opened": 136}	2025-09-22 14:45:49.853569+00
4903	main_trader	HEALTHY	t	t	t	\N	136	0	0	\N	{"sl_set": 136, "sl_failed": 0, "positions_failed": 21, "positions_opened": 136}	2025-09-22 14:46:51.163389+00
4904	main_trader	HEALTHY	t	t	t	\N	136	0	0	\N	{"sl_set": 136, "sl_failed": 0, "positions_failed": 21, "positions_opened": 136}	2025-09-22 14:47:52.488545+00
4905	main_trader	HEALTHY	t	t	t	\N	136	0	0	\N	{"sl_set": 136, "sl_failed": 0, "positions_failed": 21, "positions_opened": 136}	2025-09-22 14:48:53.668956+00
4906	main_trader	HEALTHY	t	t	t	\N	136	0	0	\N	{"sl_set": 136, "sl_failed": 0, "positions_failed": 21, "positions_opened": 136}	2025-09-22 14:49:55.672569+00
4907	main_trader	HEALTHY	t	t	t	\N	138	0	0	\N	{"sl_set": 138, "sl_failed": 0, "positions_failed": 21, "positions_opened": 138}	2025-09-22 14:50:56.721637+00
4908	main_trader	HEALTHY	t	t	t	\N	140	0	0	\N	{"sl_set": 140, "sl_failed": 0, "positions_failed": 22, "positions_opened": 140}	2025-09-22 14:51:57.758966+00
4909	main_trader	HEALTHY	t	t	t	\N	142	0	0	\N	{"sl_set": 142, "sl_failed": 0, "positions_failed": 23, "positions_opened": 142}	2025-09-22 14:52:59.612591+00
4910	main_trader	HEALTHY	t	t	t	\N	144	0	0	\N	{"sl_set": 145, "sl_failed": 0, "positions_failed": 23, "positions_opened": 145}	2025-09-22 14:54:00.61475+00
4911	main_trader	HEALTHY	t	t	t	\N	145	0	0	\N	{"sl_set": 145, "sl_failed": 0, "positions_failed": 23, "positions_opened": 145}	2025-09-22 14:55:02.474724+00
4912	main_trader	HEALTHY	t	t	t	\N	145	0	0	\N	{"sl_set": 145, "sl_failed": 0, "positions_failed": 23, "positions_opened": 145}	2025-09-22 14:56:03.61775+00
4913	main_trader	HEALTHY	t	t	t	\N	145	0	0	\N	{"sl_set": 145, "sl_failed": 0, "positions_failed": 23, "positions_opened": 145}	2025-09-22 14:57:04.987461+00
4914	main_trader	HEALTHY	t	t	t	\N	145	0	0	\N	{"sl_set": 145, "sl_failed": 0, "positions_failed": 23, "positions_opened": 145}	2025-09-22 14:58:06.240417+00
4915	main_trader	HEALTHY	t	t	t	\N	145	0	0	\N	{"sl_set": 145, "sl_failed": 0, "positions_failed": 23, "positions_opened": 145}	2025-09-22 14:59:07.66177+00
4916	main_trader	HEALTHY	t	t	t	\N	145	0	0	\N	{"sl_set": 145, "sl_failed": 0, "positions_failed": 23, "positions_opened": 145}	2025-09-22 15:00:09.053948+00
4917	main_trader	HEALTHY	t	t	t	\N	145	0	0	\N	{"sl_set": 145, "sl_failed": 0, "positions_failed": 23, "positions_opened": 145}	2025-09-22 15:01:10.557695+00
4918	main_trader	HEALTHY	t	t	t	\N	145	0	0	\N	{"sl_set": 145, "sl_failed": 0, "positions_failed": 23, "positions_opened": 145}	2025-09-22 15:02:12.294927+00
4919	main_trader	HEALTHY	t	t	t	\N	145	0	0	\N	{"sl_set": 145, "sl_failed": 0, "positions_failed": 23, "positions_opened": 145}	2025-09-22 15:03:13.627553+00
4920	main_trader	HEALTHY	t	t	t	\N	145	0	0	\N	{"sl_set": 145, "sl_failed": 0, "positions_failed": 23, "positions_opened": 145}	2025-09-22 15:04:14.901409+00
4921	main_trader	HEALTHY	t	t	t	\N	145	0	0	\N	{"sl_set": 145, "sl_failed": 0, "positions_failed": 23, "positions_opened": 145}	2025-09-22 15:05:16.507292+00
4922	main_trader	HEALTHY	t	t	t	\N	145	0	0	\N	{"sl_set": 145, "sl_failed": 0, "positions_failed": 23, "positions_opened": 145}	2025-09-22 15:06:17.912682+00
4923	main_trader	HEALTHY	t	t	t	\N	148	0	0	\N	{"sl_set": 148, "sl_failed": 0, "positions_failed": 23, "positions_opened": 148}	2025-09-22 15:07:19.452819+00
4924	main_trader	HEALTHY	t	t	t	\N	151	0	0	\N	{"sl_set": 151, "sl_failed": 0, "positions_failed": 23, "positions_opened": 151}	2025-09-22 15:08:21.104348+00
4925	main_trader	HEALTHY	t	t	t	\N	153	0	0	\N	{"sl_set": 153, "sl_failed": 0, "positions_failed": 24, "positions_opened": 153}	2025-09-22 15:09:22.334136+00
4926	main_trader	HEALTHY	t	t	t	\N	156	0	0	\N	{"sl_set": 156, "sl_failed": 0, "positions_failed": 24, "positions_opened": 156}	2025-09-22 15:10:23.684688+00
4927	main_trader	HEALTHY	t	t	t	\N	158	0	0	\N	{"sl_set": 158, "sl_failed": 0, "positions_failed": 25, "positions_opened": 158}	2025-09-22 15:11:25.240464+00
4928	main_trader	HEALTHY	t	t	t	\N	161	0	0	\N	{"sl_set": 161, "sl_failed": 0, "positions_failed": 25, "positions_opened": 161}	2025-09-22 15:12:26.49544+00
4929	main_trader	HEALTHY	t	t	t	\N	164	0	0	\N	{"sl_set": 164, "sl_failed": 0, "positions_failed": 25, "positions_opened": 164}	2025-09-22 15:13:28.154772+00
4930	main_trader	HEALTHY	t	t	t	\N	166	0	0	\N	{"sl_set": 166, "sl_failed": 0, "positions_failed": 26, "positions_opened": 166}	2025-09-22 15:14:29.149258+00
4931	main_trader	HEALTHY	t	t	t	\N	169	0	0	\N	{"sl_set": 169, "sl_failed": 0, "positions_failed": 26, "positions_opened": 169}	2025-09-22 15:15:31.313631+00
4932	main_trader	HEALTHY	t	t	t	\N	172	0	0	\N	{"sl_set": 172, "sl_failed": 0, "positions_failed": 26, "positions_opened": 172}	2025-09-22 15:16:32.540495+00
4933	main_trader	HEALTHY	t	t	t	\N	172	0	0	\N	{"sl_set": 172, "sl_failed": 0, "positions_failed": 26, "positions_opened": 172}	2025-09-22 15:17:33.996282+00
4934	main_trader	HEALTHY	t	t	t	\N	172	0	0	\N	{"sl_set": 172, "sl_failed": 0, "positions_failed": 26, "positions_opened": 172}	2025-09-22 15:18:35.791821+00
4935	main_trader	HEALTHY	t	t	t	\N	172	0	0	\N	{"sl_set": 172, "sl_failed": 0, "positions_failed": 26, "positions_opened": 172}	2025-09-22 15:19:36.889379+00
4936	main_trader	HEALTHY	t	t	t	\N	172	0	0	\N	{"sl_set": 173, "sl_failed": 0, "positions_failed": 26, "positions_opened": 173}	2025-09-22 15:20:38.485287+00
4937	main_trader	HEALTHY	t	t	t	\N	175	0	0	\N	{"sl_set": 175, "sl_failed": 0, "positions_failed": 26, "positions_opened": 176}	2025-09-22 15:21:40.023044+00
4938	main_trader	HEALTHY	t	t	t	\N	178	0	0	\N	{"sl_set": 178, "sl_failed": 0, "positions_failed": 26, "positions_opened": 178}	2025-09-22 15:22:41.156875+00
4939	main_trader	HEALTHY	t	t	t	\N	180	0	0	\N	{"sl_set": 181, "sl_failed": 0, "positions_failed": 26, "positions_opened": 181}	2025-09-22 15:23:42.118075+00
4940	main_trader	HEALTHY	t	t	t	\N	183	0	0	\N	{"sl_set": 184, "sl_failed": 0, "positions_failed": 26, "positions_opened": 184}	2025-09-22 15:24:43.579957+00
4941	main_trader	HEALTHY	t	t	t	\N	185	0	0	\N	{"sl_set": 185, "sl_failed": 0, "positions_failed": 27, "positions_opened": 186}	2025-09-22 15:25:46.432184+00
4942	main_trader	HEALTHY	t	t	t	\N	188	0	0	\N	{"sl_set": 188, "sl_failed": 0, "positions_failed": 27, "positions_opened": 188}	2025-09-22 15:26:48.21317+00
4943	main_trader	HEALTHY	t	t	t	\N	191	0	0	\N	{"sl_set": 191, "sl_failed": 0, "positions_failed": 27, "positions_opened": 191}	2025-09-22 15:27:49.792729+00
4944	main_trader	HEALTHY	t	t	t	\N	192	0	0	\N	{"sl_set": 192, "sl_failed": 0, "positions_failed": 27, "positions_opened": 192}	2025-09-22 15:28:50.901126+00
4945	main_trader	HEALTHY	t	t	t	\N	192	0	0	\N	{"sl_set": 192, "sl_failed": 0, "positions_failed": 27, "positions_opened": 192}	2025-09-22 15:29:52.761546+00
4946	main_trader	HEALTHY	t	t	t	\N	192	0	0	\N	{"sl_set": 192, "sl_failed": 0, "positions_failed": 27, "positions_opened": 192}	2025-09-22 15:30:54.737961+00
4947	main_trader	HEALTHY	t	t	t	\N	192	0	0	\N	{"sl_set": 192, "sl_failed": 0, "positions_failed": 27, "positions_opened": 192}	2025-09-22 15:31:56.486969+00
4948	main_trader	HEALTHY	t	t	t	\N	192	0	0	\N	{"sl_set": 192, "sl_failed": 0, "positions_failed": 27, "positions_opened": 192}	2025-09-22 15:32:57.94204+00
4949	main_trader	HEALTHY	t	t	t	\N	192	0	0	\N	{"sl_set": 192, "sl_failed": 0, "positions_failed": 27, "positions_opened": 192}	2025-09-22 15:33:59.400207+00
4950	main_trader	HEALTHY	t	t	t	\N	192	0	0	\N	{"sl_set": 192, "sl_failed": 0, "positions_failed": 27, "positions_opened": 192}	2025-09-22 15:35:01.275387+00
4951	main_trader	HEALTHY	t	t	t	\N	195	0	0	\N	{"sl_set": 195, "sl_failed": 0, "positions_failed": 27, "positions_opened": 195}	2025-09-22 15:36:03.080217+00
4952	main_trader	HEALTHY	t	t	t	\N	198	0	0	\N	{"sl_set": 198, "sl_failed": 0, "positions_failed": 27, "positions_opened": 198}	2025-09-22 15:37:04.525824+00
4953	main_trader	HEALTHY	t	t	t	\N	201	0	0	\N	{"sl_set": 201, "sl_failed": 0, "positions_failed": 27, "positions_opened": 201}	2025-09-22 15:38:06.016487+00
4954	main_trader	HEALTHY	t	t	t	\N	204	0	0	\N	{"sl_set": 204, "sl_failed": 0, "positions_failed": 27, "positions_opened": 204}	2025-09-22 15:39:06.974446+00
4955	main_trader	HEALTHY	t	t	t	\N	206	0	0	\N	{"sl_set": 206, "sl_failed": 0, "positions_failed": 28, "positions_opened": 206}	2025-09-22 15:40:08.105077+00
4956	main_trader	HEALTHY	t	t	t	\N	207	0	0	\N	{"sl_set": 207, "sl_failed": 0, "positions_failed": 29, "positions_opened": 207}	2025-09-22 15:41:09.659825+00
4957	main_trader	HEALTHY	t	t	t	\N	210	0	0	\N	{"sl_set": 210, "sl_failed": 0, "positions_failed": 29, "positions_opened": 210}	2025-09-22 15:42:10.877623+00
4958	main_trader	HEALTHY	t	t	t	\N	212	0	0	\N	{"sl_set": 212, "sl_failed": 0, "positions_failed": 29, "positions_opened": 212}	2025-09-22 15:43:12.192034+00
4959	main_trader	HEALTHY	t	t	t	\N	214	0	0	\N	{"sl_set": 214, "sl_failed": 0, "positions_failed": 29, "positions_opened": 214}	2025-09-22 15:44:15.877006+00
4960	main_trader	HEALTHY	t	t	t	\N	216	0	0	\N	{"sl_set": 217, "sl_failed": 0, "positions_failed": 29, "positions_opened": 217}	2025-09-22 15:45:17.409703+00
4961	main_trader	HEALTHY	t	t	t	\N	219	0	0	\N	{"sl_set": 219, "sl_failed": 0, "positions_failed": 29, "positions_opened": 219}	2025-09-22 15:46:18.860421+00
4962	main_trader	HEALTHY	t	t	t	\N	219	0	0	\N	{"sl_set": 219, "sl_failed": 0, "positions_failed": 29, "positions_opened": 219}	2025-09-22 15:47:20.060716+00
4963	main_trader	HEALTHY	t	t	t	\N	219	0	0	\N	{"sl_set": 219, "sl_failed": 0, "positions_failed": 29, "positions_opened": 219}	2025-09-22 15:48:21.37247+00
4964	main_trader	HEALTHY	t	t	t	\N	219	0	0	\N	{"sl_set": 219, "sl_failed": 0, "positions_failed": 29, "positions_opened": 219}	2025-09-22 15:49:23.789746+00
4965	main_trader	HEALTHY	t	t	t	\N	220	0	0	\N	{"sl_set": 220, "sl_failed": 0, "positions_failed": 29, "positions_opened": 220}	2025-09-22 15:50:26.74587+00
4966	main_trader	HEALTHY	t	t	t	\N	222	0	0	\N	{"sl_set": 222, "sl_failed": 0, "positions_failed": 29, "positions_opened": 222}	2025-09-22 15:51:28.036349+00
4967	main_trader	HEALTHY	t	t	t	\N	224	0	0	\N	{"sl_set": 224, "sl_failed": 0, "positions_failed": 30, "positions_opened": 225}	2025-09-22 15:52:29.365021+00
4968	main_trader	HEALTHY	t	t	t	\N	227	0	0	\N	{"sl_set": 227, "sl_failed": 0, "positions_failed": 30, "positions_opened": 227}	2025-09-22 15:53:30.969196+00
4969	main_trader	HEALTHY	t	t	t	\N	230	0	0	\N	{"sl_set": 230, "sl_failed": 0, "positions_failed": 30, "positions_opened": 230}	2025-09-22 15:54:32.163648+00
4970	main_trader	HEALTHY	t	t	t	\N	233	0	0	\N	{"sl_set": 233, "sl_failed": 0, "positions_failed": 30, "positions_opened": 233}	2025-09-22 15:55:34.425799+00
4971	main_trader	HEALTHY	t	t	t	\N	234	0	0	\N	{"sl_set": 234, "sl_failed": 0, "positions_failed": 30, "positions_opened": 234}	2025-09-22 15:56:35.5958+00
4972	main_trader	HEALTHY	t	t	t	\N	234	0	0	\N	{"sl_set": 234, "sl_failed": 0, "positions_failed": 30, "positions_opened": 234}	2025-09-22 15:57:36.715096+00
4973	main_trader	HEALTHY	t	t	t	\N	234	0	0	\N	{"sl_set": 234, "sl_failed": 0, "positions_failed": 30, "positions_opened": 234}	2025-09-22 15:58:38.475587+00
4974	main_trader	HEALTHY	t	t	t	\N	234	0	0	\N	{"sl_set": 234, "sl_failed": 0, "positions_failed": 30, "positions_opened": 234}	2025-09-22 15:59:40.245245+00
4975	main_trader	HEALTHY	t	t	t	\N	234	0	0	\N	{"sl_set": 234, "sl_failed": 0, "positions_failed": 30, "positions_opened": 234}	2025-09-22 16:00:42.151837+00
4976	main_trader	HEALTHY	t	t	t	\N	234	0	0	\N	{"sl_set": 234, "sl_failed": 0, "positions_failed": 30, "positions_opened": 234}	2025-09-22 16:01:43.565294+00
4977	main_trader	HEALTHY	t	t	t	\N	234	0	0	\N	{"sl_set": 234, "sl_failed": 0, "positions_failed": 30, "positions_opened": 234}	2025-09-22 16:02:45.348343+00
4978	main_trader	HEALTHY	t	t	t	\N	234	0	0	\N	{"sl_set": 234, "sl_failed": 0, "positions_failed": 30, "positions_opened": 234}	2025-09-22 16:03:46.697564+00
4979	main_trader	HEALTHY	t	t	t	\N	234	0	0	\N	{"sl_set": 234, "sl_failed": 0, "positions_failed": 30, "positions_opened": 234}	2025-09-22 16:04:48.239977+00
4980	main_trader	HEALTHY	t	t	t	\N	234	0	0	\N	{"sl_set": 234, "sl_failed": 0, "positions_failed": 30, "positions_opened": 234}	2025-09-22 16:05:50.106264+00
4981	main_trader	HEALTHY	t	t	t	\N	234	0	0	\N	{"sl_set": 234, "sl_failed": 0, "positions_failed": 30, "positions_opened": 234}	2025-09-22 16:06:52.04434+00
4982	main_trader	HEALTHY	t	t	t	\N	234	0	0	\N	{"sl_set": 234, "sl_failed": 0, "positions_failed": 30, "positions_opened": 234}	2025-09-22 16:07:53.537171+00
4983	main_trader	HEALTHY	t	t	t	\N	234	0	0	\N	{"sl_set": 234, "sl_failed": 0, "positions_failed": 30, "positions_opened": 234}	2025-09-22 16:08:54.657824+00
4984	main_trader	HEALTHY	t	t	t	\N	234	0	0	\N	{"sl_set": 234, "sl_failed": 0, "positions_failed": 30, "positions_opened": 234}	2025-09-22 16:09:55.881205+00
4985	main_trader	HEALTHY	t	t	t	\N	234	0	0	\N	{"sl_set": 234, "sl_failed": 0, "positions_failed": 30, "positions_opened": 234}	2025-09-22 16:10:58.391313+00
4986	main_trader	HEALTHY	t	t	t	\N	234	0	0	\N	{"sl_set": 234, "sl_failed": 0, "positions_failed": 30, "positions_opened": 234}	2025-09-22 16:11:59.83908+00
4987	main_trader	HEALTHY	t	t	t	\N	234	0	0	\N	{"sl_set": 234, "sl_failed": 0, "positions_failed": 30, "positions_opened": 234}	2025-09-22 16:13:01.301665+00
4988	main_trader	HEALTHY	t	t	t	\N	234	0	0	\N	{"sl_set": 234, "sl_failed": 0, "positions_failed": 30, "positions_opened": 234}	2025-09-22 16:14:02.939711+00
4989	main_trader	HEALTHY	t	t	t	\N	234	0	0	\N	{"sl_set": 234, "sl_failed": 0, "positions_failed": 30, "positions_opened": 234}	2025-09-22 16:15:04.050472+00
4990	main_trader	HEALTHY	t	t	t	\N	234	0	0	\N	{"sl_set": 234, "sl_failed": 0, "positions_failed": 30, "positions_opened": 234}	2025-09-22 16:16:05.493304+00
4991	main_trader	HEALTHY	t	t	t	\N	234	0	0	\N	{"sl_set": 234, "sl_failed": 0, "positions_failed": 30, "positions_opened": 234}	2025-09-22 16:17:09.604463+00
4992	main_trader	HEALTHY	t	t	t	\N	234	0	0	\N	{"sl_set": 234, "sl_failed": 0, "positions_failed": 30, "positions_opened": 234}	2025-09-22 16:18:10.955199+00
4993	main_trader	HEALTHY	t	t	t	\N	234	0	0	\N	{"sl_set": 234, "sl_failed": 0, "positions_failed": 30, "positions_opened": 234}	2025-09-22 16:19:12.349381+00
4994	main_trader	HEALTHY	t	t	t	\N	234	0	0	\N	{"sl_set": 234, "sl_failed": 0, "positions_failed": 30, "positions_opened": 234}	2025-09-22 16:20:13.751885+00
4995	main_trader	HEALTHY	t	t	t	\N	235	0	0	\N	{"sl_set": 235, "sl_failed": 0, "positions_failed": 30, "positions_opened": 235}	2025-09-22 16:21:15.207657+00
4996	main_trader	HEALTHY	t	t	t	\N	235	0	0	\N	{"sl_set": 235, "sl_failed": 0, "positions_failed": 30, "positions_opened": 235}	2025-09-22 16:22:16.898926+00
4997	main_trader	HEALTHY	t	t	t	\N	235	0	0	\N	{"sl_set": 235, "sl_failed": 0, "positions_failed": 30, "positions_opened": 235}	2025-09-22 16:23:18.500313+00
4998	main_trader	HEALTHY	t	t	t	\N	235	0	0	\N	{"sl_set": 235, "sl_failed": 0, "positions_failed": 30, "positions_opened": 235}	2025-09-22 16:24:19.913929+00
4999	main_trader	HEALTHY	t	t	t	\N	235	0	0	\N	{"sl_set": 235, "sl_failed": 0, "positions_failed": 30, "positions_opened": 235}	2025-09-22 16:25:21.151709+00
5000	main_trader	HEALTHY	t	t	t	\N	235	0	0	\N	{"sl_set": 235, "sl_failed": 0, "positions_failed": 30, "positions_opened": 235}	2025-09-22 16:26:22.388285+00
5001	main_trader	HEALTHY	t	t	t	\N	235	0	0	\N	{"sl_set": 235, "sl_failed": 0, "positions_failed": 30, "positions_opened": 235}	2025-09-22 16:27:25.264133+00
5002	main_trader	HEALTHY	t	t	t	\N	235	0	0	\N	{"sl_set": 235, "sl_failed": 0, "positions_failed": 30, "positions_opened": 235}	2025-09-22 16:28:26.59359+00
5003	main_trader	HEALTHY	t	t	t	\N	235	0	0	\N	{"sl_set": 235, "sl_failed": 0, "positions_failed": 30, "positions_opened": 235}	2025-09-22 16:29:27.966613+00
5004	main_trader	HEALTHY	t	t	t	\N	235	0	0	\N	{"sl_set": 235, "sl_failed": 0, "positions_failed": 30, "positions_opened": 235}	2025-09-22 16:30:29.341128+00
5005	main_trader	HEALTHY	t	t	t	\N	235	0	0	\N	{"sl_set": 235, "sl_failed": 0, "positions_failed": 30, "positions_opened": 235}	2025-09-22 16:31:30.761282+00
5006	main_trader	HEALTHY	t	t	t	\N	235	0	0	\N	{"sl_set": 235, "sl_failed": 0, "positions_failed": 30, "positions_opened": 235}	2025-09-22 16:32:32.438365+00
5007	main_trader	HEALTHY	t	t	t	\N	235	0	0	\N	{"sl_set": 235, "sl_failed": 0, "positions_failed": 30, "positions_opened": 235}	2025-09-22 16:33:33.971196+00
5008	main_trader	HEALTHY	t	t	t	\N	235	0	0	\N	{"sl_set": 235, "sl_failed": 0, "positions_failed": 30, "positions_opened": 235}	2025-09-22 16:34:35.429367+00
5009	main_trader	HEALTHY	t	t	t	\N	237	0	0	\N	{"sl_set": 238, "sl_failed": 0, "positions_failed": 30, "positions_opened": 238}	2025-09-22 16:35:36.47383+00
5010	main_trader	HEALTHY	t	t	t	\N	238	0	0	\N	{"sl_set": 238, "sl_failed": 0, "positions_failed": 30, "positions_opened": 238}	2025-09-22 16:36:37.886156+00
5011	main_trader	HEALTHY	t	t	t	\N	238	0	0	\N	{"sl_set": 238, "sl_failed": 0, "positions_failed": 30, "positions_opened": 238}	2025-09-22 16:37:39.415087+00
5012	main_trader	HEALTHY	t	t	t	\N	238	0	0	\N	{"sl_set": 238, "sl_failed": 0, "positions_failed": 30, "positions_opened": 238}	2025-09-22 16:38:40.6688+00
5013	main_trader	HEALTHY	t	t	t	\N	238	0	0	\N	{"sl_set": 238, "sl_failed": 0, "positions_failed": 30, "positions_opened": 238}	2025-09-22 16:39:41.835818+00
5014	main_trader	HEALTHY	t	t	t	\N	238	0	0	\N	{"sl_set": 238, "sl_failed": 0, "positions_failed": 30, "positions_opened": 238}	2025-09-22 16:40:43.512478+00
5015	main_trader	HEALTHY	t	t	t	\N	238	0	0	\N	{"sl_set": 238, "sl_failed": 0, "positions_failed": 30, "positions_opened": 238}	2025-09-22 16:41:44.807727+00
5016	main_trader	HEALTHY	t	t	t	\N	238	0	0	\N	{"sl_set": 238, "sl_failed": 0, "positions_failed": 30, "positions_opened": 238}	2025-09-22 16:42:46.81299+00
5017	main_trader	HEALTHY	t	t	t	\N	238	0	0	\N	{"sl_set": 238, "sl_failed": 0, "positions_failed": 30, "positions_opened": 238}	2025-09-22 16:43:48.062306+00
5018	main_trader	HEALTHY	t	t	t	\N	238	0	0	\N	{"sl_set": 238, "sl_failed": 0, "positions_failed": 30, "positions_opened": 238}	2025-09-22 16:44:49.239656+00
5019	main_trader	HEALTHY	t	t	t	\N	238	0	0	\N	{"sl_set": 238, "sl_failed": 0, "positions_failed": 30, "positions_opened": 238}	2025-09-22 16:45:50.693658+00
5020	main_trader	HEALTHY	t	t	t	\N	238	0	0	\N	{"sl_set": 238, "sl_failed": 0, "positions_failed": 30, "positions_opened": 238}	2025-09-22 16:46:51.728904+00
5021	main_trader	HEALTHY	t	t	t	\N	238	0	0	\N	{"sl_set": 238, "sl_failed": 0, "positions_failed": 30, "positions_opened": 238}	2025-09-22 16:47:53.488399+00
5022	main_trader	HEALTHY	t	t	t	\N	238	0	0	\N	{"sl_set": 238, "sl_failed": 0, "positions_failed": 30, "positions_opened": 238}	2025-09-22 16:48:55.242678+00
5023	main_trader	HEALTHY	t	t	t	\N	238	0	0	\N	{"sl_set": 238, "sl_failed": 0, "positions_failed": 30, "positions_opened": 238}	2025-09-22 16:49:57.13868+00
5024	main_trader	HEALTHY	t	t	t	\N	238	0	0	\N	{"sl_set": 238, "sl_failed": 0, "positions_failed": 30, "positions_opened": 238}	2025-09-22 16:50:58.678903+00
5025	main_trader	HEALTHY	t	t	t	\N	238	0	0	\N	{"sl_set": 238, "sl_failed": 0, "positions_failed": 30, "positions_opened": 238}	2025-09-22 16:52:00.541307+00
5026	main_trader	HEALTHY	t	t	t	\N	238	0	0	\N	{"sl_set": 238, "sl_failed": 0, "positions_failed": 30, "positions_opened": 238}	2025-09-22 16:53:02.398672+00
5027	main_trader	HEALTHY	t	t	t	\N	238	0	0	\N	{"sl_set": 238, "sl_failed": 0, "positions_failed": 30, "positions_opened": 238}	2025-09-22 16:54:03.700789+00
5028	main_trader	HEALTHY	t	t	t	\N	238	0	0	\N	{"sl_set": 238, "sl_failed": 0, "positions_failed": 30, "positions_opened": 238}	2025-09-22 16:55:06.318607+00
5029	main_trader	HEALTHY	t	t	t	\N	238	0	0	\N	{"sl_set": 238, "sl_failed": 0, "positions_failed": 30, "positions_opened": 238}	2025-09-22 16:56:09.053389+00
5030	main_trader	HEALTHY	t	t	t	\N	238	0	0	\N	{"sl_set": 238, "sl_failed": 0, "positions_failed": 30, "positions_opened": 238}	2025-09-22 16:57:10.410085+00
5031	main_trader	HEALTHY	t	t	t	\N	238	0	0	\N	{"sl_set": 238, "sl_failed": 0, "positions_failed": 30, "positions_opened": 238}	2025-09-22 16:58:12.084422+00
5032	main_trader	HEALTHY	t	t	t	\N	238	0	0	\N	{"sl_set": 238, "sl_failed": 0, "positions_failed": 30, "positions_opened": 238}	2025-09-22 16:59:13.393751+00
5033	main_trader	HEALTHY	t	t	t	\N	238	0	0	\N	{"sl_set": 238, "sl_failed": 0, "positions_failed": 30, "positions_opened": 238}	2025-09-22 17:00:14.79995+00
5034	main_trader	HEALTHY	t	t	t	\N	238	0	0	\N	{"sl_set": 238, "sl_failed": 0, "positions_failed": 30, "positions_opened": 238}	2025-09-22 17:01:16.28772+00
5035	main_trader	HEALTHY	t	t	t	\N	238	0	0	\N	{"sl_set": 238, "sl_failed": 0, "positions_failed": 30, "positions_opened": 238}	2025-09-22 17:02:18.07968+00
5036	main_trader	HEALTHY	t	t	t	\N	238	0	0	\N	{"sl_set": 238, "sl_failed": 0, "positions_failed": 30, "positions_opened": 238}	2025-09-22 17:03:20.021611+00
5037	main_trader	HEALTHY	t	t	t	\N	238	0	0	\N	{"sl_set": 238, "sl_failed": 0, "positions_failed": 30, "positions_opened": 238}	2025-09-22 17:04:21.337608+00
5038	main_trader	HEALTHY	t	t	t	\N	238	0	0	\N	{"sl_set": 238, "sl_failed": 0, "positions_failed": 30, "positions_opened": 238}	2025-09-22 17:05:22.787816+00
5039	main_trader	HEALTHY	t	t	t	\N	238	0	0	\N	{"sl_set": 238, "sl_failed": 0, "positions_failed": 30, "positions_opened": 238}	2025-09-22 17:06:24.040659+00
5040	main_trader	HEALTHY	t	t	t	\N	238	0	0	\N	{"sl_set": 238, "sl_failed": 0, "positions_failed": 30, "positions_opened": 238}	2025-09-22 17:07:25.499102+00
5041	main_trader	HEALTHY	t	t	t	\N	238	0	0	\N	{"sl_set": 238, "sl_failed": 0, "positions_failed": 30, "positions_opened": 238}	2025-09-22 17:08:27.026055+00
5042	main_trader	HEALTHY	t	t	t	\N	238	0	0	\N	{"sl_set": 238, "sl_failed": 0, "positions_failed": 30, "positions_opened": 238}	2025-09-22 17:09:28.63323+00
5043	main_trader	HEALTHY	t	t	t	\N	238	0	0	\N	{"sl_set": 238, "sl_failed": 0, "positions_failed": 30, "positions_opened": 238}	2025-09-22 17:10:30.085452+00
5044	main_trader	HEALTHY	t	t	t	\N	238	0	0	\N	{"sl_set": 238, "sl_failed": 0, "positions_failed": 30, "positions_opened": 238}	2025-09-22 17:11:31.356658+00
5045	main_trader	HEALTHY	t	t	t	\N	238	0	0	\N	{"sl_set": 238, "sl_failed": 0, "positions_failed": 30, "positions_opened": 238}	2025-09-22 17:12:32.398408+00
5046	main_trader	HEALTHY	t	t	t	\N	238	0	0	\N	{"sl_set": 238, "sl_failed": 0, "positions_failed": 30, "positions_opened": 238}	2025-09-22 17:13:34.415039+00
5047	main_trader	HEALTHY	t	t	t	\N	238	0	0	\N	{"sl_set": 238, "sl_failed": 0, "positions_failed": 30, "positions_opened": 238}	2025-09-22 17:14:35.882059+00
5048	main_trader	HEALTHY	t	t	t	\N	238	0	0	\N	{"sl_set": 238, "sl_failed": 0, "positions_failed": 30, "positions_opened": 238}	2025-09-22 17:15:37.214974+00
5049	main_trader	HEALTHY	t	t	t	\N	238	0	0	\N	{"sl_set": 238, "sl_failed": 0, "positions_failed": 30, "positions_opened": 238}	2025-09-22 17:16:38.389456+00
5050	main_trader	HEALTHY	t	t	t	\N	238	0	0	\N	{"sl_set": 238, "sl_failed": 0, "positions_failed": 30, "positions_opened": 238}	2025-09-22 17:17:39.775627+00
5051	main_trader	HEALTHY	t	t	t	\N	238	0	0	\N	{"sl_set": 238, "sl_failed": 0, "positions_failed": 30, "positions_opened": 238}	2025-09-22 17:18:41.239073+00
5052	main_trader	HEALTHY	t	t	t	\N	238	0	0	\N	{"sl_set": 238, "sl_failed": 0, "positions_failed": 30, "positions_opened": 238}	2025-09-22 17:19:42.882583+00
5053	main_trader	HEALTHY	t	t	t	\N	238	0	0	\N	{"sl_set": 238, "sl_failed": 0, "positions_failed": 30, "positions_opened": 238}	2025-09-22 17:20:44.323999+00
5054	main_trader	HEALTHY	t	t	t	\N	238	0	0	\N	{"sl_set": 238, "sl_failed": 0, "positions_failed": 30, "positions_opened": 238}	2025-09-22 17:21:46.811434+00
5055	main_trader	HEALTHY	t	t	t	\N	238	0	0	\N	{"sl_set": 238, "sl_failed": 0, "positions_failed": 30, "positions_opened": 238}	2025-09-22 17:22:48.466698+00
5056	main_trader	HEALTHY	t	t	t	\N	238	0	0	\N	{"sl_set": 238, "sl_failed": 0, "positions_failed": 30, "positions_opened": 238}	2025-09-22 17:23:51.29798+00
5057	main_trader	HEALTHY	t	t	t	\N	238	0	0	\N	{"sl_set": 238, "sl_failed": 0, "positions_failed": 30, "positions_opened": 238}	2025-09-22 17:24:52.695116+00
5058	main_trader	HEALTHY	t	t	t	\N	238	0	0	\N	{"sl_set": 238, "sl_failed": 0, "positions_failed": 30, "positions_opened": 238}	2025-09-22 17:25:54.187065+00
5059	main_trader	HEALTHY	t	t	t	\N	238	0	0	\N	{"sl_set": 238, "sl_failed": 0, "positions_failed": 30, "positions_opened": 238}	2025-09-22 17:26:55.880858+00
5060	main_trader	HEALTHY	t	t	t	\N	238	0	0	\N	{"sl_set": 238, "sl_failed": 0, "positions_failed": 30, "positions_opened": 238}	2025-09-22 17:27:57.497678+00
5061	main_trader	HEALTHY	t	t	t	\N	238	0	0	\N	{"sl_set": 238, "sl_failed": 0, "positions_failed": 30, "positions_opened": 238}	2025-09-22 17:28:59.078236+00
5062	main_trader	HEALTHY	t	t	t	\N	238	0	0	\N	{"sl_set": 238, "sl_failed": 0, "positions_failed": 30, "positions_opened": 238}	2025-09-22 17:30:00.41308+00
5063	main_trader	HEALTHY	t	t	t	\N	238	0	0	\N	{"sl_set": 238, "sl_failed": 0, "positions_failed": 30, "positions_opened": 238}	2025-09-22 17:31:01.765673+00
5064	main_trader	HEALTHY	t	t	t	\N	238	0	0	\N	{"sl_set": 238, "sl_failed": 0, "positions_failed": 30, "positions_opened": 238}	2025-09-22 17:32:03.027084+00
5065	main_trader	HEALTHY	t	t	t	\N	238	0	0	\N	{"sl_set": 238, "sl_failed": 0, "positions_failed": 30, "positions_opened": 238}	2025-09-22 17:33:04.329951+00
5066	main_trader	HEALTHY	t	t	t	\N	238	0	0	\N	{"sl_set": 238, "sl_failed": 0, "positions_failed": 30, "positions_opened": 238}	2025-09-22 17:34:06.06631+00
5067	main_trader	HEALTHY	t	t	t	\N	238	0	0	\N	{"sl_set": 238, "sl_failed": 0, "positions_failed": 30, "positions_opened": 238}	2025-09-22 17:35:07.694862+00
5068	main_trader	HEALTHY	t	t	t	\N	239	0	0	\N	{"sl_set": 239, "sl_failed": 0, "positions_failed": 30, "positions_opened": 239}	2025-09-22 17:36:08.9148+00
5069	main_trader	HEALTHY	t	t	t	\N	239	0	0	\N	{"sl_set": 239, "sl_failed": 0, "positions_failed": 30, "positions_opened": 239}	2025-09-22 17:37:10.445438+00
5070	main_trader	HEALTHY	t	t	t	\N	239	0	0	\N	{"sl_set": 239, "sl_failed": 0, "positions_failed": 30, "positions_opened": 239}	2025-09-22 17:38:11.613553+00
5071	main_trader	HEALTHY	t	t	t	\N	239	0	0	\N	{"sl_set": 239, "sl_failed": 0, "positions_failed": 30, "positions_opened": 239}	2025-09-22 17:39:12.967011+00
5072	main_trader	HEALTHY	t	t	t	\N	239	0	0	\N	{"sl_set": 239, "sl_failed": 0, "positions_failed": 30, "positions_opened": 239}	2025-09-22 17:40:14.290205+00
5073	main_trader	HEALTHY	t	t	t	\N	239	0	0	\N	{"sl_set": 239, "sl_failed": 0, "positions_failed": 30, "positions_opened": 239}	2025-09-22 17:41:15.525958+00
5074	main_trader	HEALTHY	t	t	t	\N	239	0	0	\N	{"sl_set": 239, "sl_failed": 0, "positions_failed": 30, "positions_opened": 239}	2025-09-22 17:42:17.834718+00
5075	main_trader	HEALTHY	t	t	t	\N	239	0	0	\N	{"sl_set": 239, "sl_failed": 0, "positions_failed": 30, "positions_opened": 239}	2025-09-22 17:43:19.10864+00
5076	main_trader	HEALTHY	t	t	t	\N	239	0	0	\N	{"sl_set": 239, "sl_failed": 0, "positions_failed": 30, "positions_opened": 239}	2025-09-22 17:44:20.246638+00
5077	main_trader	HEALTHY	t	t	t	\N	239	0	0	\N	{"sl_set": 239, "sl_failed": 0, "positions_failed": 30, "positions_opened": 239}	2025-09-22 17:45:21.279934+00
5078	main_trader	HEALTHY	t	t	t	\N	239	0	0	\N	{"sl_set": 239, "sl_failed": 0, "positions_failed": 30, "positions_opened": 239}	2025-09-22 17:46:22.421412+00
5079	main_trader	HEALTHY	t	t	t	\N	239	0	0	\N	{"sl_set": 239, "sl_failed": 0, "positions_failed": 30, "positions_opened": 239}	2025-09-22 17:47:24.182159+00
5080	main_trader	HEALTHY	t	t	t	\N	239	0	0	\N	{"sl_set": 239, "sl_failed": 0, "positions_failed": 30, "positions_opened": 239}	2025-09-22 17:48:25.598425+00
5081	main_trader	HEALTHY	t	t	t	\N	239	0	0	\N	{"sl_set": 239, "sl_failed": 0, "positions_failed": 30, "positions_opened": 239}	2025-09-22 17:49:27.15641+00
5082	main_trader	HEALTHY	t	t	t	\N	239	0	0	\N	{"sl_set": 240, "sl_failed": 0, "positions_failed": 30, "positions_opened": 240}	2025-09-22 17:50:28.307042+00
5083	main_trader	HEALTHY	t	t	t	\N	240	0	0	\N	{"sl_set": 240, "sl_failed": 0, "positions_failed": 31, "positions_opened": 240}	2025-09-22 17:51:29.712947+00
5084	main_trader	HEALTHY	t	t	t	\N	240	0	0	\N	{"sl_set": 240, "sl_failed": 0, "positions_failed": 31, "positions_opened": 240}	2025-09-22 17:52:31.769362+00
5085	main_trader	HEALTHY	t	t	t	\N	240	0	0	\N	{"sl_set": 240, "sl_failed": 0, "positions_failed": 31, "positions_opened": 240}	2025-09-22 17:53:33.10385+00
5086	main_trader	HEALTHY	t	t	t	\N	240	0	0	\N	{"sl_set": 240, "sl_failed": 0, "positions_failed": 31, "positions_opened": 240}	2025-09-22 17:54:35.444327+00
5087	main_trader	HEALTHY	t	t	t	\N	240	0	0	\N	{"sl_set": 240, "sl_failed": 0, "positions_failed": 31, "positions_opened": 240}	2025-09-22 17:55:36.931452+00
5088	main_trader	HEALTHY	t	t	t	\N	240	0	0	\N	{"sl_set": 240, "sl_failed": 0, "positions_failed": 31, "positions_opened": 240}	2025-09-22 17:56:38.559269+00
5089	main_trader	HEALTHY	t	t	t	\N	240	0	0	\N	{"sl_set": 240, "sl_failed": 0, "positions_failed": 31, "positions_opened": 240}	2025-09-22 17:57:40.335576+00
5090	main_trader	HEALTHY	t	t	t	\N	240	0	0	\N	{"sl_set": 240, "sl_failed": 0, "positions_failed": 31, "positions_opened": 240}	2025-09-22 17:58:41.921851+00
5091	main_trader	HEALTHY	t	t	t	\N	240	0	0	\N	{"sl_set": 240, "sl_failed": 0, "positions_failed": 31, "positions_opened": 240}	2025-09-22 17:59:43.237954+00
5092	main_trader	HEALTHY	t	t	t	\N	240	0	0	\N	{"sl_set": 240, "sl_failed": 0, "positions_failed": 31, "positions_opened": 240}	2025-09-22 18:00:44.601462+00
5093	main_trader	HEALTHY	t	t	t	\N	240	0	0	\N	{"sl_set": 240, "sl_failed": 0, "positions_failed": 31, "positions_opened": 240}	2025-09-22 18:01:45.935761+00
5094	main_trader	HEALTHY	t	t	t	\N	240	0	0	\N	{"sl_set": 240, "sl_failed": 0, "positions_failed": 31, "positions_opened": 240}	2025-09-22 18:02:48.026732+00
5095	main_trader	HEALTHY	t	t	t	\N	240	0	0	\N	{"sl_set": 240, "sl_failed": 0, "positions_failed": 31, "positions_opened": 240}	2025-09-22 18:03:49.387644+00
5096	main_trader	HEALTHY	t	t	t	\N	240	0	0	\N	{"sl_set": 240, "sl_failed": 0, "positions_failed": 31, "positions_opened": 240}	2025-09-22 18:04:50.838344+00
5097	main_trader	HEALTHY	t	t	t	\N	240	0	0	\N	{"sl_set": 240, "sl_failed": 0, "positions_failed": 31, "positions_opened": 240}	2025-09-22 18:05:52.4886+00
5098	main_trader	HEALTHY	t	t	t	\N	240	0	0	\N	{"sl_set": 240, "sl_failed": 0, "positions_failed": 31, "positions_opened": 240}	2025-09-22 18:06:53.94128+00
5099	main_trader	HEALTHY	t	t	t	\N	240	0	0	\N	{"sl_set": 240, "sl_failed": 0, "positions_failed": 31, "positions_opened": 240}	2025-09-22 18:07:55.90663+00
5100	main_trader	HEALTHY	t	t	t	\N	240	0	0	\N	{"sl_set": 240, "sl_failed": 0, "positions_failed": 31, "positions_opened": 240}	2025-09-22 18:08:57.460955+00
5101	main_trader	HEALTHY	t	t	t	\N	240	0	0	\N	{"sl_set": 240, "sl_failed": 0, "positions_failed": 31, "positions_opened": 240}	2025-09-22 18:09:59.239579+00
5102	main_trader	HEALTHY	t	t	t	\N	240	0	0	\N	{"sl_set": 240, "sl_failed": 0, "positions_failed": 31, "positions_opened": 240}	2025-09-22 18:11:00.865092+00
5103	main_trader	HEALTHY	t	t	t	\N	240	0	0	\N	{"sl_set": 240, "sl_failed": 0, "positions_failed": 31, "positions_opened": 240}	2025-09-22 18:12:02.447574+00
5104	main_trader	HEALTHY	t	t	t	\N	240	0	0	\N	{"sl_set": 240, "sl_failed": 0, "positions_failed": 31, "positions_opened": 240}	2025-09-22 18:13:03.539354+00
5105	main_trader	HEALTHY	t	t	t	\N	240	0	0	\N	{"sl_set": 240, "sl_failed": 0, "positions_failed": 31, "positions_opened": 240}	2025-09-22 18:14:05.276267+00
5106	main_trader	HEALTHY	t	t	t	\N	240	0	0	\N	{"sl_set": 240, "sl_failed": 0, "positions_failed": 31, "positions_opened": 240}	2025-09-22 18:15:06.46447+00
5107	main_trader	HEALTHY	t	t	t	\N	240	0	0	\N	{"sl_set": 240, "sl_failed": 0, "positions_failed": 31, "positions_opened": 240}	2025-09-22 18:16:07.861185+00
5108	main_trader	HEALTHY	t	t	t	\N	240	0	0	\N	{"sl_set": 240, "sl_failed": 0, "positions_failed": 31, "positions_opened": 240}	2025-09-22 18:17:09.560201+00
5109	main_trader	HEALTHY	t	t	t	\N	240	0	0	\N	{"sl_set": 240, "sl_failed": 0, "positions_failed": 31, "positions_opened": 240}	2025-09-22 18:18:10.830904+00
5110	main_trader	HEALTHY	t	t	t	\N	240	0	0	\N	{"sl_set": 240, "sl_failed": 0, "positions_failed": 31, "positions_opened": 240}	2025-09-22 18:19:13.330294+00
5111	main_trader	HEALTHY	t	t	t	\N	240	0	0	\N	{"sl_set": 240, "sl_failed": 0, "positions_failed": 31, "positions_opened": 240}	2025-09-22 18:20:15.573438+00
5112	main_trader	HEALTHY	t	t	t	\N	240	0	0	\N	{"sl_set": 240, "sl_failed": 0, "positions_failed": 31, "positions_opened": 240}	2025-09-22 18:21:17.04594+00
5113	main_trader	HEALTHY	t	t	t	\N	240	0	0	\N	{"sl_set": 240, "sl_failed": 0, "positions_failed": 31, "positions_opened": 240}	2025-09-22 18:22:18.554678+00
5114	main_trader	HEALTHY	t	t	t	\N	240	0	0	\N	{"sl_set": 240, "sl_failed": 0, "positions_failed": 31, "positions_opened": 240}	2025-09-22 18:23:19.883361+00
5115	main_trader	HEALTHY	t	t	t	\N	240	0	0	\N	{"sl_set": 240, "sl_failed": 0, "positions_failed": 31, "positions_opened": 240}	2025-09-22 18:24:21.563491+00
5116	main_trader	RUNNING	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 18:24:56.643738+00
5117	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 18:25:58.451772+00
5118	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 18:27:00.107085+00
5119	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 18:28:01.64005+00
5120	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 18:29:03.816891+00
5121	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 18:30:05.181206+00
5122	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 18:31:06.54249+00
5123	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 18:32:08.388735+00
5124	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 18:33:09.797207+00
5125	main_trader	DEGRADED	t	t	t	\N	0	0	0	\N	{"sl_set": 0, "sl_failed": 0, "positions_failed": 0, "positions_opened": 0}	2025-09-22 18:34:11.617351+00
5126	main_trader	HEALTHY	t	t	t	\N	0	0	0	\N	{"sl_set": 1, "sl_failed": 0, "positions_failed": 0, "positions_opened": 1}	2025-09-22 18:35:12.862467+00
5127	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 18:36:14.604334+00
5128	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 18:37:15.845299+00
5129	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 18:38:17.372124+00
5130	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 18:39:18.816677+00
5131	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 18:40:20.038171+00
5132	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 18:41:22.714361+00
5133	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 18:42:24.427998+00
5134	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 18:43:25.811274+00
5135	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 18:44:27.110034+00
5136	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 18:45:28.353034+00
5137	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 18:46:29.993098+00
5138	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 18:47:31.61278+00
5139	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 18:48:33.075471+00
5140	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 18:49:34.663332+00
5141	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 18:50:36.030013+00
5142	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 18:51:37.884014+00
5143	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 18:52:39.964145+00
5144	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 18:53:41.238969+00
5145	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 18:54:42.551301+00
5146	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 18:55:43.985768+00
5147	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 18:56:46.782613+00
5148	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 18:57:48.314094+00
5149	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 18:58:49.542841+00
5150	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 18:59:50.635958+00
5151	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 19:00:51.814635+00
5152	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 19:01:53.736189+00
5153	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 19:02:55.011189+00
5154	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 19:03:56.466728+00
5155	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 19:04:57.866667+00
5156	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 19:05:59.03924+00
5157	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 19:07:00.471277+00
5158	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 19:08:02.620005+00
5159	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 19:09:03.715729+00
5160	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 19:10:05.098819+00
5161	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 19:11:06.423366+00
5162	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 19:12:08.282379+00
5163	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 19:13:09.927044+00
5164	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 19:14:11.238446+00
5165	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 19:15:12.53712+00
5166	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 19:16:13.824671+00
5167	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 19:17:15.370368+00
5168	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 19:18:16.868487+00
5169	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 19:19:18.11147+00
5170	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 19:20:19.493616+00
5171	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 19:21:21.05573+00
5172	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 19:22:22.990658+00
5173	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 19:23:24.322825+00
5174	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 19:24:25.581623+00
5175	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 19:25:26.819451+00
5176	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 19:26:27.984642+00
5177	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 19:27:29.453609+00
5178	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 19:28:30.936018+00
5179	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 19:29:32.241329+00
5180	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 19:30:33.696094+00
5181	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 19:31:35.058965+00
5182	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 19:32:36.769326+00
5183	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 19:33:38.289671+00
5184	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 19:34:39.609119+00
5185	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 19:35:40.761238+00
5186	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 19:36:42.294499+00
5187	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 19:37:44.68432+00
5188	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 19:38:46.409971+00
5189	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 19:39:48.034707+00
5190	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 19:40:49.835283+00
5191	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 19:41:51.200453+00
5192	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 19:42:53.095731+00
5193	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 19:43:54.747326+00
5194	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 19:44:56.840745+00
5195	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 19:45:58.045652+00
5196	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 19:46:59.245058+00
5197	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 19:48:01.315485+00
5198	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 19:49:02.486634+00
5199	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 19:50:03.810284+00
5200	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 19:51:05.358865+00
5201	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 19:52:06.629029+00
5202	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 19:53:08.291158+00
5203	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 19:54:09.588713+00
5204	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 19:55:10.891289+00
5205	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 19:56:12.313741+00
5206	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 19:57:13.767096+00
5207	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 19:58:15.457196+00
5208	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 19:59:17.062687+00
5209	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 20:00:18.815764+00
5210	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 20:01:20.243101+00
5211	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 20:02:21.826865+00
5212	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 20:03:23.867849+00
5213	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 20:04:25.106247+00
5214	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 20:05:26.510091+00
5215	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 20:06:27.83059+00
5216	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 20:07:29.202985+00
5217	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 20:08:30.854349+00
5218	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 20:09:32.658808+00
5219	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 20:10:33.893498+00
5220	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 20:11:35.294251+00
5221	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 20:12:36.869017+00
5222	main_trader	HEALTHY	t	t	t	\N	2	0	0	\N	{"sl_set": 2, "sl_failed": 0, "positions_failed": 0, "positions_opened": 2}	2025-09-22 20:13:38.335774+00
\.


--
-- Data for Name: trades; Type: TABLE DATA; Schema: monitoring; Owner: elcrypto
--

COPY monitoring.trades (id, signal_id, trading_pair_id, symbol, exchange, side, quantity, executed_qty, price, status, order_id, error_message, created_at, updated_at) FROM stdin;
1	12024414	\N	FLUXUSDT	binance	sell	1056.00000000	1056.00000000	0.18910000	FILLED	8979362	\N	2025-10-08 18:06:09.754049+00	2025-10-08 18:06:09.754049+00
2	12024420	\N	EIGENUSDT	binance	sell	103.00000000	103.00000000	1.92310000	FILLED	17836818	\N	2025-10-08 18:06:15.985793+00	2025-10-08 18:06:15.985793+00
3	12024422	\N	SCRUSDT	binance	sell	723.00000000	723.00000000	0.27650000	FILLED	9248581	\N	2025-10-08 18:06:22.838702+00	2025-10-08 18:06:22.838702+00
4	12024423	\N	1000000MOGUSDT	binance	sell	252.00000000	252.00000000	0.79170000	FILLED	14448584	\N	2025-10-08 18:06:29.241137+00	2025-10-08 18:06:29.241137+00
5	12024424	\N	PNUTUSDT	binance	sell	928.00000000	928.00000000	0.21499000	FILLED	28536189	\N	2025-10-08 18:06:36.039578+00	2025-10-08 18:06:36.039578+00
6	12027175	\N	KSMUSDT	binance	sell	13.00000000	13.00000000	15.07500000	FILLED	45904014	\N	2025-10-08 18:21:12.649685+00	2025-10-08 18:21:12.649685+00
7	12027184	\N	ZRCUSDT	binance	sell	9474.00000000	9474.00000000	0.02111000	FILLED	7690348	\N	2025-10-08 18:21:18.990189+00	2025-10-08 18:21:18.990189+00
8	12027079	\N	XTZUSDT	binance	sell	286.00000000	286.00000000	0.69700000	FILLED	135037830	\N	2025-10-08 18:21:25.14828+00	2025-10-08 18:21:25.14828+00
9	12028267	\N	HOOKUSDT	binance	sell	1937.00000000	1937.00000000	0.10281000	FILLED	39269343	\N	2025-10-08 18:36:20.48056+00	2025-10-08 18:36:20.48056+00
10	12028275	\N	GASUSDT	binance	sell	65.00000000	65.00000000	3.06000000	FILLED	16621272	\N	2025-10-08 18:36:27.801962+00	2025-10-08 18:36:27.801962+00
11	12028266	\N	QNTUSDT	binance	sell	1.00000000	1.00000000	102.52000000	FILLED	21342149	\N	2025-10-08 18:36:33.667097+00	2025-10-08 18:36:33.667097+00
12	12028255	\N	DENTUSDT	binance	sell	313971.00000000	313971.00000000	0.00063700	FILLED	59547127	\N	2025-10-08 18:36:45.383566+00	2025-10-08 18:36:45.383566+00
13	12028289	\N	LISTAUSDT	binance	sell	394.00000000	394.00000000	0.50622540	FILLED	11814044	\N	2025-10-08 18:36:51.504145+00	2025-10-08 18:36:51.504145+00
14	12029755	\N	TUSDT	binance	sell	13114.00000000	13114.00000000	0.01523000	FILLED	23131464	\N	2025-10-08 18:51:13.099945+00	2025-10-08 18:51:13.099945+00
15	12029758	\N	ARBUSDT	binance	sell	459.00000000	459.00000000	0.43420000	FILLED	22579593	\N	2025-10-08 18:51:19.403906+00	2025-10-08 18:51:19.403906+00
16	12029759	\N	EDUUSDT	binance	sell	1352.00000000	1352.00000000	0.14750000	FILLED	19772810	\N	2025-10-08 18:51:25.926283+00	2025-10-08 18:51:25.926283+00
17	12029763	\N	SUPERUSDT	binance	sell	337.00000000	337.00000000	0.59050000	FILLED	11249138	\N	2025-10-08 18:51:31.955658+00	2025-10-08 18:51:31.955658+00
18	12029764	\N	USTCUSDT	binance	sell	17975.00000000	17975.00000000	0.01108800	FILLED	26432731	\N	2025-10-08 18:51:38.097568+00	2025-10-08 18:51:38.097568+00
19	12032259	\N	IDUSDT	binance	sell	1300.00000000	1300.00000000	0.15340000	FILLED	18032379	\N	2025-10-08 19:22:11.893219+00	2025-10-08 19:22:11.893219+00
20	12032260	\N	OXTUSDT	binance	sell	4011.00000000	4011.00000000	0.04969000	FILLED	11366317	\N	2025-10-08 19:22:18.37417+00	2025-10-08 19:22:18.37417+00
21	12032181	\N	BSVUSDT	binance	sell	7.00000000	7.00000000	25.82000000	FILLED	8647714	\N	2025-10-08 19:22:24.435193+00	2025-10-08 19:22:24.435193+00
22	12032232	\N	SKATEUSDT	binance	sell	3732.00000000	3732.00000000	0.05346930	FILLED	4665215	\N	2025-10-08 19:22:38.635774+00	2025-10-08 19:22:38.635774+00
23	12033369	\N	RAREUSDT	binance	sell	3941.00000000	3941.00000000	0.05059000	FILLED	16253288	\N	2025-10-08 19:36:11.633374+00	2025-10-08 19:36:11.633374+00
24	12033376	\N	DEGOUSDT	binance	sell	175.00000000	175.00000000	1.13660000	FILLED	8290004	\N	2025-10-08 19:36:17.726563+00	2025-10-08 19:36:17.726563+00
25	12033395	\N	MILKUSDT	binance	sell	4482.00000000	4482.00000000	0.04448000	FILLED	11096916	\N	2025-10-08 19:36:24.055171+00	2025-10-08 19:36:24.055171+00
26	12034548	\N	ARUSDT	binance	sell	33.00000000	33.00000000	6.01600000	FILLED	23315937	\N	2025-10-08 19:51:11.581537+00	2025-10-08 19:51:11.581537+00
27	12034560	\N	LQTYUSDT	binance	sell	273.00000000	273.00000000	0.72630000	FILLED	20777823	\N	2025-10-08 19:51:18.477293+00	2025-10-08 19:51:18.477293+00
28	12034562	\N	YGGUSDT	binance	sell	1172.00000000	1172.00000000	0.16940000	FILLED	9285227	\N	2025-10-08 19:51:24.484825+00	2025-10-08 19:51:24.484825+00
29	12034563	\N	CYBERUSDT	binance	sell	123.00000000	123.00000000	1.60300000	FILLED	9487413	\N	2025-10-08 19:51:30.559964+00	2025-10-08 19:51:30.559964+00
30	12034564	\N	BIGTIMEUSDT	binance	sell	4095.00000000	4095.00000000	0.04872000	FILLED	18256071	\N	2025-10-08 19:51:36.830904+00	2025-10-08 19:51:36.830904+00
31	12038803	\N	DOGEUSDT	binance	sell	773.00000000	773.00000000	0.25854000	FILLED	195769784	\N	2025-10-08 20:36:14.444333+00	2025-10-08 20:36:14.444333+00
32	12038804	\N	BANDUSDT	binance	sell	291.00000000	291.00000000	0.68550000	FILLED	90042199	\N	2025-10-08 20:36:21.891744+00	2025-10-08 20:36:21.891744+00
33	12038807	\N	EGLDUSDT	binance	sell	14.00000000	14.00000000	13.49900000	FILLED	51875428	\N	2025-10-08 20:36:29.042469+00	2025-10-08 20:36:29.042469+00
34	12038822	\N	NKNUSDT	binance	sell	7727.00000000	7727.00000000	0.02581000	FILLED	13150061	\N	2025-10-08 20:36:36.149713+00	2025-10-08 20:36:36.149713+00
35	12038827	\N	LPTUSDT	binance	sell	30.00000000	30.00000000	6.43800000	FILLED	13570469	\N	2025-10-08 20:36:43.108125+00	2025-10-08 20:36:43.108125+00
36	12040616	\N	DOGSUSDT	binance	sell	1672240.00000000	1672240.00000000	0.00011950	FILLED	27494261	\N	2025-10-08 20:51:13.212038+00	2025-10-08 20:51:13.212038+00
37	12040619	\N	COWUSDT	binance	sell	698.00000000	698.00000000	0.28630000	FILLED	10850469	\N	2025-10-08 20:51:19.505671+00	2025-10-08 20:51:19.505671+00
38	12040589	\N	PHBUSDT	binance	sell	332.00000000	332.00000000	0.60020000	FILLED	16657176	\N	2025-10-08 20:51:26.021339+00	2025-10-08 20:51:26.021339+00
39	12040572	\N	RLCUSDT	binance	sell	184.00000000	184.00000000	1.08240000	FILLED	68287945	\N	2025-10-08 20:51:32.501813+00	2025-10-08 20:51:32.501813+00
40	12040646	\N	PUNDIXUSDT	binance	sell	636.00000000	636.00000000	0.31440000	FILLED	8319323	\N	2025-10-08 20:51:38.459756+00	2025-10-08 20:51:38.459756+00
41	12043587	\N	TOWNSUSDT	binance	sell	10554.00000000	10554.00000000	0.01890000	FILLED	10824955	\N	2025-10-08 21:21:46.578566+00	2025-10-08 21:21:46.578566+00
42	12043595	\N	FLOCKUSDT	binance	sell	717.00000000	717.00000000	0.27790000	FILLED	4319356	\N	2025-10-08 21:21:53.260347+00	2025-10-08 21:21:53.260347+00
43	12044695	\N	MUBARAKUSDT	binance	sell	4968.00000000	4968.00000000	0.04021000	FILLED	18761043	\N	2025-10-08 21:36:12.252381+00	2025-10-08 21:36:12.252381+00
44	12044696	\N	BIDUSDT	binance	sell	2864.00000000	2864.00000000	0.06966531	FILLED	10864913	\N	2025-10-08 21:36:18.672849+00	2025-10-08 21:36:18.672849+00
45	12044705	\N	FISUSDT	binance	sell	2366.00000000	2366.00000000	0.08450000	FILLED	7171194	\N	2025-10-08 21:36:24.536266+00	2025-10-08 21:36:24.536266+00
46	12045966	\N	LINKUSDT	binance	sell	8.00000000	8.00000000	22.43700000	FILLED	208589169	\N	2025-10-08 21:51:12.925381+00	2025-10-08 21:51:12.925381+00
47	12045978	\N	SFPUSDT	binance	sell	371.00000000	371.00000000	0.53880000	FILLED	23394428	\N	2025-10-08 21:51:19.260588+00	2025-10-08 21:51:19.260588+00
48	12045982	\N	MTLUSDT	binance	sell	313.00000000	313.00000000	0.63580000	FILLED	28457955	\N	2025-10-08 21:51:26.081999+00	2025-10-08 21:51:26.081999+00
49	12046106	\N	ARIAUSDT	binance	sell	1345.00000000	1345.00000000	0.14860000	FILLED	5644094	\N	2025-10-08 21:51:32.549862+00	2025-10-08 21:51:32.549862+00
50	12046021	\N	FIOUSDT	binance	sell	12084.00000000	12084.00000000	0.01655000	FILLED	20085689	\N	2025-10-08 21:51:38.320026+00	2025-10-08 21:51:38.320026+00
51	12049321	\N	IDOLUSDT	binance	sell	5305.00000000	5305.00000000	0.03758000	FILLED	8482944	\N	2025-10-08 22:21:11.50584+00	2025-10-08 22:21:11.50584+00
52	12050431	\N	HBARUSDT	binance	sell	908.00000000	908.00000000	0.21909000	FILLED	29375823	\N	2025-10-08 22:36:13.132942+00	2025-10-08 22:36:13.132942+00
53	12050433	\N	HOTUSDT	binance	sell	224971.00000000	224971.00000000	0.00088800	FILLED	60311785	\N	2025-10-08 22:36:19.911101+00	2025-10-08 22:36:19.911101+00
54	12050435	\N	APTUSDT	binance	sell	38.00000000	38.00000000	5.17690000	FILLED	41700782	\N	2025-10-08 22:36:25.942642+00	2025-10-08 22:36:25.942642+00
55	12050530	\N	HOLOUSDT	binance	sell	930.00000000	930.00000000	0.21450000	FILLED	4757164	\N	2025-10-08 22:36:32.097825+00	2025-10-08 22:36:32.097825+00
56	12050468	\N	SPXUSDT	binance	sell	126.00000000	126.00000000	1.58130000	FILLED	14582975	\N	2025-10-08 22:36:38.010063+00	2025-10-08 22:36:38.010063+00
57	12051649	\N	EPTUSDT	binance	sell	34211.00000000	34211.00000000	0.00583150	FILLED	8554301	\N	2025-10-08 22:51:11.514119+00	2025-10-08 22:51:11.514119+00
58	12051661	\N	SKATEUSDT	binance	sell	3752.00000000	3752.00000000	0.05312100	FILLED	4683202	\N	2025-10-08 22:51:19.800439+00	2025-10-08 22:51:19.800439+00
59	12051715	\N	FLUIDUSDT	binance	sell	30.00000000	30.00000000	6.63800000	FILLED	15988823	\N	2025-10-08 22:51:26.516911+00	2025-10-08 22:51:26.516911+00
60	12051594	\N	ONGUSDT	binance	sell	1318.00000000	1318.00000000	0.15120000	FILLED	10841775	\N	2025-10-08 22:51:32.699875+00	2025-10-08 22:51:32.699875+00
61	12051601	\N	GLMUSDT	binance	sell	901.00000000	901.00000000	0.22117000	FILLED	17925839	\N	2025-10-08 22:51:38.891822+00	2025-10-08 22:51:38.891822+00
62	12054944	\N	API3USDT	binance	buy	226.00000000	226.00000000	0.88520000	FILLED	40841139	\N	2025-10-08 23:21:10.480287+00	2025-10-08 23:21:10.480287+00
63	12054926	\N	NEOUSDT	binance	sell	31.00000000	31.00000000	6.27039000	FILLED	111020324	\N	2025-10-08 23:21:16.992139+00	2025-10-08 23:21:16.992139+00
64	12054927	\N	COMPUSDT	binance	sell	4.00000000	4.00000000	42.65000000	FILLED	422155773	\N	2025-10-08 23:21:23.230928+00	2025-10-08 23:21:23.230928+00
65	12054933	\N	RVNUSDT	binance	sell	16920.00000000	16920.00000000	0.01179000	FILLED	14107948	\N	2025-10-08 23:21:29.471116+00	2025-10-08 23:21:29.471116+00
66	12054934	\N	MANAUSDT	binance	sell	615.00000000	615.00000000	0.32450000	FILLED	31196413	\N	2025-10-08 23:21:35.920396+00	2025-10-08 23:21:35.920396+00
67	12056723	\N	HOMEUSDT	binance	sell	6574.00000000	6574.00000000	0.03028600	FILLED	3863233	\N	2025-10-08 23:36:10.176156+00	2025-10-08 23:36:10.176156+00
68	12056653	\N	ALICEUSDT	binance	sell	555.00000000	555.00000000	0.35800000	FILLED	27619247	\N	2025-10-08 23:36:16.92445+00	2025-10-08 23:36:16.92445+00
69	12056667	\N	HFTUSDT	binance	sell	2675.00000000	2675.00000000	0.07424000	FILLED	14416394	\N	2025-10-08 23:36:22.651+00	2025-10-08 23:36:22.651+00
70	12056668	\N	BLURUSDT	binance	sell	2695.00000000	2695.00000000	0.07370000	FILLED	15371482	\N	2025-10-08 23:36:28.703173+00	2025-10-08 23:36:28.703173+00
71	12056676	\N	KASUSDT	binance	sell	2654.00000000	2654.00000000	0.07498000	FILLED	1074459863	\N	2025-10-08 23:36:34.947767+00	2025-10-08 23:36:34.947767+00
72	12058162	\N	REDUSDT	binance	buy	426.00000000	426.00000000	0.46940000	FILLED	14710987	\N	2025-10-08 23:51:12.148591+00	2025-10-08 23:51:12.148591+00
73	12058063	\N	1000SHIBUSDT	binance	sell	16220.00000000	16220.00000000	0.01230300	FILLED	54460816	\N	2025-10-08 23:51:32.518552+00	2025-10-08 23:51:32.518552+00
74	12058072	\N	SSVUSDT	binance	sell	24.00000000	24.00000000	8.02400000	FILLED	21149817	\N	2025-10-08 23:51:38.377023+00	2025-10-08 23:51:38.377023+00
75	12058073	\N	LQTYUSDT	binance	sell	270.00000000	270.00000000	0.73600000	FILLED	20798436	\N	2025-10-08 23:51:45.276983+00	2025-10-08 23:51:45.276983+00
76	12060832	\N	PROMUSDT	binance	sell	19.00000000	19.00000000	10.06200000	FILLED	12053640	\N	2025-10-09 00:21:09.94965+00	2025-10-09 00:21:09.94965+00
77	12060745	\N	XLMUSDT	binance	sell	515.00000000	515.00000000	0.38628000	FILLED	183993041	\N	2025-10-09 00:21:17.530422+00	2025-10-09 00:21:17.530422+00
78	12060746	\N	XTZUSDT	binance	sell	292.00000000	292.00000000	0.68210000	FILLED	135069697	\N	2025-10-09 00:21:24.079127+00	2025-10-09 00:21:24.079127+00
79	12060758	\N	FILUSDT	binance	sell	84.00000000	84.00000000	2.35400000	FILLED	50385043	\N	2025-10-09 00:21:31.106935+00	2025-10-09 00:21:31.106935+00
80	12062555	\N	KAVAUSDT	binance	sell	616.00000000	616.00000000	0.32400000	FILLED	80375122	\N	2025-10-09 00:36:15.975176+00	2025-10-09 00:36:15.975176+00
81	12062656	\N	FUSDT	binance	sell	17911.00000000	17911.00000000	0.01115200	FILLED	9302319	\N	2025-10-09 00:36:22.512153+00	2025-10-09 00:36:22.512153+00
82	12062658	\N	DMCUSDT	binance	sell	59364.00000000	59364.00000000	0.00336800	FILLED	7806243	\N	2025-10-09 00:36:28.682342+00	2025-10-09 00:36:28.682342+00
83	12062673	\N	A2ZUSDT	binance	sell	35198.00000000	35198.00000000	0.00567600	FILLED	8892166	\N	2025-10-09 00:36:35.030979+00	2025-10-09 00:36:35.030979+00
84	12062674	\N	TOWNSUSDT	binance	sell	10723.00000000	10723.00000000	0.01865000	FILLED	10851591	\N	2025-10-09 00:36:41.040007+00	2025-10-09 00:36:41.040007+00
85	12063959	\N	RSRUSDT	binance	sell	33074.00000000	33074.00000000	0.00603200	FILLED	49722074	\N	2025-10-09 00:51:13.385386+00	2025-10-09 00:51:13.385386+00
86	12063965	\N	ARUSDT	binance	sell	33.00000000	33.00000000	5.97100000	FILLED	23342391	\N	2025-10-09 00:51:20.898784+00	2025-10-09 00:51:20.898784+00
87	12064088	\N	AIOUSDT	binance	sell	1382.00000000	1382.00000000	0.14448000	FILLED	8845191	\N	2025-10-09 00:51:27.485985+00	2025-10-09 00:51:27.485985+00
88	12064095	\N	SKYUSDT	binance	sell	2907.00000000	2907.00000000	0.06855000	FILLED	3748483	\N	2025-10-09 00:51:38.105668+00	2025-10-09 00:51:38.105668+00
89	12066974	\N	BARDUSDT	binance	sell	258.00000000	258.00000000	0.76900000	FILLED	3719891	\N	2025-10-09 01:21:11.350764+00	2025-10-09 01:21:11.350764+00
90	12066844	\N	CFXUSDT	binance	sell	1358.00000000	1358.00000000	0.14713000	FILLED	23862298	\N	2025-10-09 01:21:18.010927+00	2025-10-09 01:21:18.010927+00
91	12066845	\N	STXUSDT	binance	sell	330.00000000	330.00000000	0.60430000	FILLED	22899984	\N	2025-10-09 01:21:24.965452+00	2025-10-09 01:21:24.965452+00
92	12066851	\N	AGLDUSDT	binance	sell	357.00000000	357.00000000	0.55890000	FILLED	12873860	\N	2025-10-09 01:21:31.889175+00	2025-10-09 01:21:31.889175+00
93	12066863	\N	XAIUSDT	binance	sell	4826.00000000	4826.00000000	0.04139000	FILLED	21799972	\N	2025-10-09 01:21:38.58068+00	2025-10-09 01:21:38.58068+00
94	12068504	\N	IOTAUSDT	binance	sell	1084.00000000	1084.00000000	0.18440000	FILLED	157226908	\N	2025-10-09 01:36:22.706725+00	2025-10-09 01:36:22.706725+00
95	12068520	\N	CHZUSDT	binance	sell	4765.00000000	4765.00000000	0.04192000	FILLED	41303680	\N	2025-10-09 01:36:29.095198+00	2025-10-09 01:36:29.095198+00
96	12068537	\N	STGUSDT	binance	sell	966.00000000	966.00000000	0.20690000	FILLED	20694252	\N	2025-10-09 01:36:35.515384+00	2025-10-09 01:36:35.515384+00
97	12070361	\N	TRXUSDT	binance	sell	586.00000000	586.00000000	0.34019000	FILLED	469468759	\N	2025-10-09 01:51:11.724835+00	2025-10-09 01:51:11.724835+00
98	12070367	\N	ONTUSDT	binance	sell	1579.70000000	1579.70000000	0.12580000	FILLED	197205582	\N	2025-10-09 01:51:18.568329+00	2025-10-09 01:51:18.568329+00
99	12070383	\N	GTCUSDT	binance	sell	711.00000000	711.00000000	0.28000000	FILLED	16293566	\N	2025-10-09 01:51:25.009795+00	2025-10-09 01:51:25.009795+00
100	12070386	\N	LPTUSDT	binance	sell	31.00000000	31.00000000	6.39700000	FILLED	13591378	\N	2025-10-09 01:51:31.219215+00	2025-10-09 01:51:31.219215+00
101	12070387	\N	DUSKUSDT	binance	sell	3117.00000000	3117.00000000	0.06403000	FILLED	26163163	\N	2025-10-09 01:51:37.768809+00	2025-10-09 01:51:37.768809+00
102	12073705	\N	FLUIDUSDT	binance	sell	30.00000000	30.00000000	6.59500000	FILLED	16827245	\N	2025-10-09 02:21:12.195637+00	2025-10-09 02:21:12.195637+00
103	12073574	\N	DYDXUSDT	binance	sell	339.00000000	339.00000000	0.58808080	FILLED	25343613	\N	2025-10-09 02:21:21.200431+00	2025-10-09 02:21:21.200431+00
104	12073588	\N	MAVUSDT	binance	sell	3857.00000000	3857.00000000	0.05176000	FILLED	16644575	\N	2025-10-09 02:21:28.059191+00	2025-10-09 02:21:28.059191+00
105	12073592	\N	ILVUSDT	binance	sell	13.00000000	13.00000000	14.46300000	FILLED	11067033	\N	2025-10-09 02:21:34.320495+00	2025-10-09 02:21:34.320495+00
106	12073599	\N	ALTUSDT	binance	sell	7034.00000000	7034.00000000	0.02841000	FILLED	34020908	\N	2025-10-09 02:21:41.832242+00	2025-10-09 02:21:41.832242+00
107	12075289	\N	ORDERUSDT	binance	sell	610.00000000	610.00000000	0.32754000	FILLED	3643204	\N	2025-10-09 02:36:18.085531+00	2025-10-09 02:36:18.085531+00
108	12075132	\N	SUIUSDT	binance	sell	57.00000000	57.00000000	3.46690000	FILLED	304712308	\N	2025-10-09 02:36:24.867845+00	2025-10-09 02:36:24.867845+00
109	12075134	\N	WLDUSDT	binance	sell	161.00000000	161.00000000	1.23690000	FILLED	26267607	\N	2025-10-09 02:36:31.579128+00	2025-10-09 02:36:31.579128+00
110	12075141	\N	CAKEUSDT	binance	sell	51.00000000	51.00000000	3.85049410	FILLED	18340451	\N	2025-10-09 02:36:38.158728+00	2025-10-09 02:36:38.158728+00
111	12077186	\N	LTCUSDT	binance	sell	1.00000000	1.00000000	117.16145000	FILLED	727708474	\N	2025-10-09 02:51:10.879656+00	2025-10-09 02:51:10.879656+00
112	12077202	\N	DOTUSDT	binance	sell	49.00000000	49.00000000	4.07400000	FILLED	74981109	\N	2025-10-09 02:51:18.311706+00	2025-10-09 02:51:18.311706+00
113	12077207	\N	STORJUSDT	binance	sell	890.00000000	890.00000000	0.22420000	FILLED	52987657	\N	2025-10-09 02:51:25.123764+00	2025-10-09 02:51:25.123764+00
114	12077209	\N	AVAXUSDT	binance	sell	7.00000000	7.00000000	28.13600000	FILLED	81050178	\N	2025-10-09 02:51:31.356153+00	2025-10-09 02:51:31.356153+00
115	12077266	\N	NMRUSDT	binance	sell	12.00000000	12.00000000	15.93200000	FILLED	14786298	\N	2025-10-09 02:51:37.622913+00	2025-10-09 02:51:37.622913+00
116	12083291	\N	PENGUUSDT	binance	sell	6347.00000000	6347.00000000	0.03139800	FILLED	21300082	\N	2025-10-09 03:36:13.782559+00	2025-10-09 03:36:13.782559+00
117	12083292	\N	KMNOUSDT	binance	sell	2678.00000000	2678.00000000	0.07466000	FILLED	9672322	\N	2025-10-09 03:36:20.865197+00	2025-10-09 03:36:20.865197+00
118	12083294	\N	BIOUSDT	binance	sell	1588.00000000	1588.00000000	0.12544000	FILLED	13473901	\N	2025-10-09 03:36:28.46987+00	2025-10-09 03:36:28.46987+00
119	12083302	\N	NILUSDT	binance	sell	580.00000000	580.00000000	0.34290000	FILLED	7348522	\N	2025-10-09 03:36:35.176051+00	2025-10-09 03:36:35.176051+00
120	12083304	\N	FUNUSDT	binance	sell	23261.00000000	23261.00000000	0.00856100	FILLED	105301957	\N	2025-10-09 03:36:41.428356+00	2025-10-09 03:36:41.428356+00
121	12084597	\N	SUSDT	binance	sell	718.00000000	718.00000000	0.27780000	FILLED	22748977	\N	2025-10-09 03:51:12.14489+00	2025-10-09 03:51:12.14489+00
122	12084537	\N	VETUSDT	binance	sell	8913.00000000	8913.00000000	0.02239100	FILLED	143599400	\N	2025-10-09 03:51:19.397272+00	2025-10-09 03:51:19.397272+00
123	12084544	\N	GRTUSDT	binance	sell	2443.00000000	2443.00000000	0.08144000	FILLED	30747704	\N	2025-10-09 03:51:27.407652+00	2025-10-09 03:51:27.407652+00
124	12084545	\N	ARPAUSDT	binance	sell	9569.00000000	9569.00000000	0.02085000	FILLED	33956167	\N	2025-10-09 03:51:33.53645+00	2025-10-09 03:51:33.53645+00
125	12084552	\N	SSVUSDT	binance	sell	25.00000000	25.00000000	7.91900000	FILLED	21174023	\N	2025-10-09 03:51:40.251766+00	2025-10-09 03:51:40.251766+00
126	12087207	\N	DAMUSDT	binance	sell	3051.00000000	3051.00000000	0.06541270	FILLED	10962432	\N	2025-10-09 04:21:12.283537+00	2025-10-09 04:21:12.283537+00
127	12087094	\N	RLCUSDT	binance	sell	187.00000000	187.00000000	1.05940000	FILLED	68323112	\N	2025-10-09 04:21:19.974499+00	2025-10-09 04:21:19.974499+00
128	12087095	\N	SNXUSDT	binance	sell	183.00000000	183.00000000	1.08900000	FILLED	91464847	\N	2025-10-09 04:21:26.041848+00	2025-10-09 04:21:26.041848+00
129	12087104	\N	ENSUSDT	binance	sell	9.00000000	9.00000000	20.95800000	FILLED	131304426	\N	2025-10-09 04:21:33.011016+00	2025-10-09 04:21:33.011016+00
130	12087106	\N	GMTUSDT	binance	sell	5252.00000000	5252.00000000	0.03800000	FILLED	38176761	\N	2025-10-09 04:21:41.026685+00	2025-10-09 04:21:41.026685+00
131	12088323	\N	GALAUSDT	binance	sell	12828.00000000	12828.00000000	0.01555000	FILLED	4352138080	\N	2025-10-09 04:36:14.643725+00	2025-10-09 04:36:14.643725+00
132	12088325	\N	JASMYUSDT	binance	sell	15875.00000000	15875.00000000	0.01253200	FILLED	32268470	\N	2025-10-09 04:36:21.921703+00	2025-10-09 04:36:21.921703+00
133	12088386	\N	SKATEUSDT	binance	sell	3804.00000000	3804.00000000	0.05257300	FILLED	4725355	\N	2025-10-09 04:36:28.684917+00	2025-10-09 04:36:28.684917+00
134	12088387	\N	TAIKOUSDT	binance	sell	552.00000000	552.00000000	0.35990000	FILLED	7154729	\N	2025-10-09 04:36:34.974147+00	2025-10-09 04:36:34.974147+00
135	12089695	\N	ERAUSDT	binance	sell	385.00000000	385.00000000	0.51430000	FILLED	6501216	\N	2025-10-09 04:51:12.280206+00	2025-10-09 04:51:12.280206+00
136	12089593	\N	ALGOUSDT	binance	sell	914.90000000	914.90000000	0.21790000	FILLED	76963419	\N	2025-10-09 04:51:20.703449+00	2025-10-09 04:51:20.703449+00
137	12089594	\N	KNCUSDT	binance	sell	600.00000000	600.00000000	0.33230000	FILLED	82064535	\N	2025-10-09 04:51:27.466455+00	2025-10-09 04:51:27.466455+00
138	12089597	\N	OGNUSDT	binance	sell	3378.00000000	3378.00000000	0.05910000	FILLED	42733894	\N	2025-10-09 04:51:35.274319+00	2025-10-09 04:51:35.274319+00
139	12089598	\N	C98USDT	binance	sell	3424.00000000	3424.00000000	0.05840000	FILLED	29817604	\N	2025-10-09 04:51:41.646347+00	2025-10-09 04:51:41.646347+00
140	12092086	\N	MANAUSDT	binance	sell	632.00000000	632.00000000	0.31510000	FILLED	31244484	\N	2025-10-09 05:35:13.16355+00	2025-10-09 05:35:13.16355+00
141	12092089	\N	MASKUSDT	binance	sell	157.00000000	157.00000000	1.26510000	FILLED	39866019	\N	2025-10-09 05:35:21.727613+00	2025-10-09 05:35:21.727613+00
142	12094774	\N	DOODUSDT	binance	sell	18554.00000000	18554.00000000	0.01072860	FILLED	11740180	\N	2025-10-09 05:51:12.561584+00	2025-10-09 05:51:12.561584+00
143	12094736	\N	STEEMUSDT	binance	sell	1658.00000000	1658.00000000	0.12039000	FILLED	17867072	\N	2025-10-09 05:51:19.814704+00	2025-10-09 05:51:19.814704+00
144	12094739	\N	1000RATSUSDT	binance	sell	7610.00000000	7610.00000000	0.02626000	FILLED	21579793	\N	2025-10-09 05:51:27.449199+00	2025-10-09 05:51:27.449199+00
145	12094743	\N	TNSRUSDT	binance	sell	2012.00000000	2012.00000000	0.09940000	FILLED	10523407	\N	2025-10-09 05:51:34.785169+00	2025-10-09 05:51:34.785169+00
146	12094756	\N	SPXUSDT	binance	sell	135.00000000	135.00000000	1.47450000	FILLED	14630756	\N	2025-10-09 05:51:41.42661+00	2025-10-09 05:51:41.42661+00
147	12097157	\N	ATOMUSDT	binance	sell	49.00000000	49.00000000	4.06600000	FILLED	115577052	\N	2025-10-09 06:21:12.71598+00	2025-10-09 06:21:12.71598+00
148	12097158	\N	IOSTUSDT	binance	sell	65338.00000000	65338.00000000	0.00306000	FILLED	121479329	\N	2025-10-09 06:21:19.440177+00	2025-10-09 06:21:19.440177+00
149	12097175	\N	ORDIUSDT	binance	sell	24.00000000	24.00000000	8.04200000	FILLED	24854902	\N	2025-10-09 06:21:25.738536+00	2025-10-09 06:21:25.738536+00
150	12097176	\N	PYTHUSDT	binance	sell	1272.00000000	1272.00000000	0.15713000	FILLED	16390941	\N	2025-10-09 06:21:32.715653+00	2025-10-09 06:21:32.715653+00
151	12098276	\N	KERNELUSDT	binance	buy	893.00000000	893.00000000	0.22390000	FILLED	17578640	\N	2025-10-09 06:36:13.44475+00	2025-10-09 06:36:13.44475+00
152	12098210	\N	TRBUSDT	binance	sell	6.00000000	6.00000000	32.98900000	FILLED	53162365	\N	2025-10-09 06:36:22.757157+00	2025-10-09 06:36:22.757157+00
153	12098212	\N	UNIUSDT	binance	sell	25.00000000	25.00000000	7.87300000	FILLED	79923776	\N	2025-10-09 06:36:29.323631+00	2025-10-09 06:36:29.323631+00
154	12098213	\N	NEARUSDT	binance	sell	68.00000000	68.00000000	2.90500000	FILLED	76519285	\N	2025-10-09 06:36:35.515673+00	2025-10-09 06:36:35.515673+00
155	12098230	\N	DODOXUSDT	binance	sell	4272.00000000	4272.00000000	0.04659800	FILLED	9493997	\N	2025-10-09 06:36:42.034324+00	2025-10-09 06:36:42.034324+00
156	12099534	\N	HOTUSDT	binance	sell	229095.00000000	229095.00000000	0.00087300	FILLED	60381429	\N	2025-10-09 06:51:13.824579+00	2025-10-09 06:51:13.824579+00
157	12099569	\N	PNUTUSDT	binance	sell	959.00000000	959.00000000	0.20838000	FILLED	28626755	\N	2025-10-09 06:51:20.767102+00	2025-10-09 06:51:20.767102+00
158	12099574	\N	VELODROMEUSDT	binance	sell	4364.00000000	4364.00000000	0.04582000	FILLED	21742178	\N	2025-10-09 06:51:27.479581+00	2025-10-09 06:51:27.479581+00
159	12102351	\N	OPUSDT	binance	sell	281.00000000	281.00000000	0.70900000	FILLED	38314863	\N	2025-10-09 07:22:14.22147+00	2025-10-09 07:22:14.22147+00
160	12102357	\N	HIGHUSDT	binance	sell	429.00000000	429.00000000	0.46404230	FILLED	19002047	\N	2025-10-09 07:22:22.162343+00	2025-10-09 07:22:22.162343+00
161	12103424	\N	EGLDUSDT	binance	sell	15.00000000	15.00000000	13.15300000	FILLED	51931892	\N	2025-10-09 07:37:16.091281+00	2025-10-09 07:37:16.091281+00
162	12104621	\N	NEOUSDT	binance	sell	32.00000000	32.00000000	6.14000000	FILLED	111072254	\N	2025-10-09 07:52:12.392665+00	2025-10-09 07:52:12.392665+00
163	12104622	\N	ZILUSDT	binance	sell	18779.00000000	18779.00000000	0.01060000	FILLED	70604545	\N	2025-10-09 07:52:19.030284+00	2025-10-09 07:52:19.030284+00
164	12107119	\N	ASTRUSDT	binance	sell	7701.00000000	7701.00000000	0.02596800	FILLED	22550784	\N	2025-10-09 08:21:17.987455+00	2025-10-09 08:21:17.987455+00
165	12116870	\N	VINEUSDT	binance	sell	3192.00000000	3192.00000000	0.06220000	FILLED	19414060	\N	2025-10-09 09:36:10.270781+00	2025-10-09 09:36:10.270781+00
166	12116867	\N	ALCHUSDT	binance	sell	2675.00000000	2675.00000000	0.07447000	FILLED	22703667	\N	2025-10-09 09:36:19.08759+00	2025-10-09 09:36:19.08759+00
167	12117788	\N	ZEREBROUSDT	binance	sell	11111.00000000	11111.00000000	0.01800000	FILLED	21404686	\N	2025-10-09 09:51:13.978402+00	2025-10-09 09:51:13.978402+00
168	12117761	\N	ARKUSDT	binance	sell	466.00000000	466.00000000	0.42650000	FILLED	15403194	\N	2025-10-09 09:51:31.41625+00	2025-10-09 09:51:31.41625+00
169	12117858	\N	XPINUSDT	binance	sell	185994.00000000	185994.00000000	0.00107410	FILLED	5517578	\N	2025-10-09 09:51:38.933764+00	2025-10-09 09:51:38.933764+00
170	12117860	\N	LIGHTUSDT	binance	sell	224.00000000	224.00000000	0.88659130	FILLED	2871054	\N	2025-10-09 09:51:45.800571+00	2025-10-09 09:51:45.800571+00
171	12120107	\N	XVSUSDT	binance	sell	28.00000000	28.00000000	6.96900000	FILLED	13329875	\N	2025-10-09 10:21:11.765559+00	2025-10-09 10:21:11.765559+00
172	12120098	\N	APTUSDT	binance	sell	40.00000000	40.00000000	4.95000000	FILLED	42002468	\N	2025-10-09 10:21:19.109783+00	2025-10-09 10:21:19.109783+00
173	12121367	\N	LQTYUSDT	binance	sell	280.00000000	280.00000000	0.71400000	FILLED	20865776	\N	2025-10-09 10:36:12.520451+00	2025-10-09 10:36:12.520451+00
174	12121416	\N	IPUSDT	binance	sell	22.00000000	22.00000000	8.93084450	FILLED	24488037	\N	2025-10-09 10:36:20.12533+00	2025-10-09 10:36:20.12533+00
175	12121344	\N	FLMUSDT	binance	sell	8032.00000000	8032.00000000	0.02480000	FILLED	57134721	\N	2025-10-09 10:36:33.924251+00	2025-10-09 10:36:33.924251+00
176	12121425	\N	BANKUSDT	binance	sell	1538.00000000	1538.00000000	0.12973660	FILLED	11555083	\N	2025-10-09 10:36:40.404643+00	2025-10-09 10:36:40.404643+00
177	12123123	\N	TAKEUSDT	binance	sell	696.00000000	696.00000000	0.28689000	FILLED	5874818	\N	2025-10-09 10:51:20.113807+00	2025-10-09 10:51:20.113807+00
178	12123112	\N	REDUSDT	binance	buy	429.00000000	429.00000000	0.46760000	FILLED	14785963	\N	2025-10-09 10:51:26.774568+00	2025-10-09 10:51:26.774568+00
179	12125551	\N	FLOWUSDT	binance	sell	558.00000000	558.00000000	0.35500000	FILLED	24241026	\N	2025-10-09 11:21:13.577851+00	2025-10-09 11:21:13.577851+00
180	12125566	\N	SKYUSDT	binance	sell	3017.00000000	3017.00000000	0.06624000	FILLED	3802394	\N	2025-10-09 11:21:20.307454+00	2025-10-09 11:21:20.307454+00
181	12125466	\N	CTSIUSDT	binance	sell	2751.00000000	2751.00000000	0.07240000	FILLED	20630127	\N	2025-10-09 11:21:26.375791+00	2025-10-09 11:21:26.375791+00
182	12125468	\N	FETUSDT	binance	sell	378.00000000	378.00000000	0.52660000	FILLED	35147382	\N	2025-10-09 11:21:32.81035+00	2025-10-09 11:21:32.81035+00
183	12126675	\N	REZUSDT	binance	sell	14245.00000000	14245.00000000	0.01397000	FILLED	17117186	\N	2025-10-09 11:36:09.825675+00	2025-10-09 11:36:09.825675+00
184	12126761	\N	BTRUSDT	binance	sell	2538.00000000	2538.00000000	0.07880000	FILLED	9095994	\N	2025-10-09 11:36:17.288364+00	2025-10-09 11:36:17.288364+00
185	12127987	\N	SIRENUSDT	binance	sell	1869.00000000	1869.00000000	0.10686000	FILLED	9979515	\N	2025-10-09 11:51:10.601718+00	2025-10-09 11:51:10.601718+00
186	12127985	\N	BERAUSDT	binance	sell	75.00000000	75.00000000	2.66100000	FILLED	18865733	\N	2025-10-09 11:51:17.621373+00	2025-10-09 11:51:17.621373+00
187	12128034	\N	TAKEUSDT	binance	sell	705.00000000	705.00000000	0.28352000	FILLED	5887905	\N	2025-10-09 11:51:24.054326+00	2025-10-09 11:51:24.054326+00
188	12128029	\N	PROVEUSDT	binance	sell	262.00000000	262.00000000	0.76320580	FILLED	7015578	\N	2025-10-09 11:51:31.492456+00	2025-10-09 11:51:31.492456+00
189	12128030	\N	YALAUSDT	binance	sell	1943.00000000	1943.00000000	0.10270000	FILLED	8972193	\N	2025-10-09 11:51:37.560043+00	2025-10-09 11:51:37.560043+00
190	12131420	\N	BSVUSDT	binance	sell	8.00000000	8.00000000	24.98000000	FILLED	8763217	\N	2025-10-09 12:36:20.114568+00	2025-10-09 12:36:20.114568+00
191	12131428	\N	AXLUSDT	binance	sell	686.00000000	686.00000000	0.29060000	FILLED	11394158	\N	2025-10-09 12:36:26.496409+00	2025-10-09 12:36:26.496409+00
192	12131429	\N	MYROUSDT	binance	sell	10989.00000000	10989.00000000	0.01805000	FILLED	21356815	\N	2025-10-09 12:36:32.864116+00	2025-10-09 12:36:32.864116+00
193	12131435	\N	REIUSDT	binance	sell	13262.00000000	13262.00000000	0.01496000	FILLED	8462498	\N	2025-10-09 12:36:39.204131+00	2025-10-09 12:36:39.204131+00
194	12131437	\N	GOATUSDT	binance	sell	2430.00000000	2430.00000000	0.08198000	FILLED	15443637	\N	2025-10-09 12:36:46.407272+00	2025-10-09 12:36:46.407272+00
195	12132347	\N	XVGUSDT	binance	sell	27851.00000000	27851.00000000	0.00718090	FILLED	45765460	\N	2025-10-09 12:51:19.745889+00	2025-10-09 12:51:19.745889+00
196	12132348	\N	AGLDUSDT	binance	sell	363.00000000	363.00000000	0.54700000	FILLED	12937076	\N	2025-10-09 12:51:27.31747+00	2025-10-09 12:51:27.31747+00
197	12132362	\N	SLERFUSDT	binance	sell	2497.00000000	2497.00000000	0.07965000	FILLED	10543348	\N	2025-10-09 12:51:33.405379+00	2025-10-09 12:51:33.405379+00
198	12132371	\N	GPSUSDT	binance	sell	14958.00000000	14958.00000000	0.01336000	FILLED	13160034	\N	2025-10-09 12:51:40.191244+00	2025-10-09 12:51:40.191244+00
199	12132413	\N	ETHWUSDT	binance	sell	144.00000000	144.00000000	1.38058330	FILLED	9562097	\N	2025-10-09 12:51:54.56758+00	2025-10-09 12:51:54.56758+00
200	12134189	\N	ADAUSDT	binance	sell	245.00000000	245.00000000	0.81420000	FILLED	209750756	\N	2025-10-09 13:21:20.949078+00	2025-10-09 13:21:20.949078+00
201	12134195	\N	DOTUSDT	binance	sell	49.00000000	49.00000000	4.04800000	FILLED	75064304	\N	2025-10-09 13:21:27.572629+00	2025-10-09 13:21:27.572629+00
202	12134197	\N	CRVUSDT	binance	sell	274.00000000	274.00000000	0.72600000	FILLED	99239380	\N	2025-10-09 13:21:37.306837+00	2025-10-09 13:21:37.306837+00
203	12134206	\N	OGNUSDT	binance	sell	3436.00000000	3436.00000000	0.05800000	FILLED	42793438	\N	2025-10-09 13:21:43.877885+00	2025-10-09 13:21:43.877885+00
204	12134207	\N	1000SHIBUSDT	binance	sell	16561.00000000	16561.00000000	0.01205700	FILLED	54532873	\N	2025-10-09 13:21:50.235409+00	2025-10-09 13:21:50.235409+00
205	12135422	\N	1000FLOKIUSDT	binance	sell	2131.00000000	2131.00000000	0.09372000	FILLED	28396589	\N	2025-10-09 13:36:11.719374+00	2025-10-09 13:36:11.719374+00
206	12135440	\N	EIGENUSDT	binance	sell	111.00000000	111.00000000	1.78550000	FILLED	17956336	\N	2025-10-09 13:36:18.200745+00	2025-10-09 13:36:18.200745+00
207	12135441	\N	SANTOSUSDT	binance	sell	103.00000000	103.00000000	1.92500000	FILLED	7987654	\N	2025-10-09 13:36:25.713354+00	2025-10-09 13:36:25.713354+00
208	12135442	\N	GRASSUSDT	binance	sell	250.00000000	250.00000000	0.79740000	FILLED	17738321	\N	2025-10-09 13:36:32.54954+00	2025-10-09 13:36:32.54954+00
209	12135464	\N	FHEUSDT	binance	sell	4256.00000000	4256.00000000	0.04698000	FILLED	9888110	\N	2025-10-09 13:36:38.626529+00	2025-10-09 13:36:38.626529+00
210	12136641	\N	ONTUSDT	binance	sell	1633.90000000	1633.90000000	0.12220000	FILLED	197295326	\N	2025-10-09 13:51:21.687832+00	2025-10-09 13:51:21.687832+00
211	12136642	\N	ALGOUSDT	binance	sell	917.40000000	917.40000000	0.21700000	FILLED	77030959	\N	2025-10-09 13:51:28.460909+00	2025-10-09 13:51:28.460909+00
212	12136649	\N	NEARUSDT	binance	sell	69.00000000	69.00000000	2.87110000	FILLED	77444884	\N	2025-10-09 13:51:35.097382+00	2025-10-09 13:51:35.097382+00
213	12136650	\N	FILUSDT	binance	sell	87.00000000	87.00000000	2.26600000	FILLED	50501464	\N	2025-10-09 13:51:42.283264+00	2025-10-09 13:51:42.283264+00
214	12136651	\N	GRTUSDT	binance	sell	2473.00000000	2473.00000000	0.08056000	FILLED	30799660	\N	2025-10-09 13:51:48.848967+00	2025-10-09 13:51:48.848967+00
215	12139584	\N	ZEREBROUSDT	binance	sell	11293.00000000	11293.00000000	0.01767000	FILLED	21439354	\N	2025-10-09 14:21:42.804211+00	2025-10-09 14:21:42.804211+00
216	12139608	\N	MILKUSDT	binance	sell	4826.00000000	4826.00000000	0.04143000	FILLED	11241402	\N	2025-10-09 14:21:49.57066+00	2025-10-09 14:21:49.57066+00
217	12141692	\N	RLCUSDT	binance	sell	193.00000000	193.00000000	1.03160000	FILLED	68372427	\N	2025-10-09 14:36:16.264898+00	2025-10-09 14:36:16.264898+00
218	12141694	\N	UNIUSDT	binance	sell	25.00000000	25.00000000	7.70400000	FILLED	79969193	\N	2025-10-09 14:36:26.205356+00	2025-10-09 14:36:26.205356+00
219	12141701	\N	ATAUSDT	binance	sell	5089.00000000	5089.00000000	0.03930000	FILLED	31120227	\N	2025-10-09 14:36:33.106839+00	2025-10-09 14:36:33.106839+00
220	12141702	\N	DYDXUSDT	binance	sell	358.00000000	358.00000000	0.55800000	FILLED	25428119	\N	2025-10-09 14:36:41.993709+00	2025-10-09 14:36:41.993709+00
221	12141703	\N	ARUSDT	binance	sell	35.00000000	35.00000000	5.58500000	FILLED	23429170	\N	2025-10-09 14:36:47.945144+00	2025-10-09 14:36:47.945144+00
222	12147314	\N	ETCUSDT	binance	sell	10.00000000	10.00000000	18.83000000	FILLED	242767969	\N	2025-10-09 15:37:18.650701+00	2025-10-09 15:37:18.650701+00
223	12147315	\N	ADAUSDT	binance	sell	248.00000000	248.00000000	0.80440000	FILLED	210476930	\N	2025-10-09 15:37:27.007013+00	2025-10-09 15:37:27.007013+00
224	12147317	\N	KNCUSDT	binance	sell	618.00000000	618.00000000	0.32300000	FILLED	82127283	\N	2025-10-09 15:37:34.158957+00	2025-10-09 15:37:34.158957+00
225	12147318	\N	BANDUSDT	binance	sell	300.00000000	300.00000000	0.66430000	FILLED	90165061	\N	2025-10-09 15:50:16.789942+00	2025-10-09 15:50:16.789942+00
226	12147319	\N	DOTUSDT	binance	sell	49.00000000	49.00000000	3.98500000	FILLED	75082935	\N	2025-10-09 15:50:23.319337+00	2025-10-09 15:50:23.319337+00
227	12147322	\N	CHZUSDT	binance	sell	4924.00000000	4924.00000000	0.04047000	FILLED	41382243	\N	2025-10-09 15:50:30.410912+00	2025-10-09 15:50:30.410912+00
\.


--
-- Name: alert_rules_id_seq; Type: SEQUENCE SET; Schema: monitoring; Owner: elcrypto
--

SELECT pg_catalog.setval('monitoring.alert_rules_id_seq', 4, true);


--
-- Name: applied_migrations_id_seq; Type: SEQUENCE SET; Schema: monitoring; Owner: elcrypto
--

SELECT pg_catalog.setval('monitoring.applied_migrations_id_seq', 7, true);


--
-- Name: daily_stats_id_seq; Type: SEQUENCE SET; Schema: monitoring; Owner: elcrypto
--

SELECT pg_catalog.setval('monitoring.daily_stats_id_seq', 8295, true);


--
-- Name: performance_metrics_id_seq; Type: SEQUENCE SET; Schema: monitoring; Owner: elcrypto
--

SELECT pg_catalog.setval('monitoring.performance_metrics_id_seq', 324, true);


--
-- Name: positions_id_seq; Type: SEQUENCE SET; Schema: monitoring; Owner: elcrypto
--

SELECT pg_catalog.setval('monitoring.positions_id_seq', 232, true);


--
-- Name: processed_signals_id_seq; Type: SEQUENCE SET; Schema: monitoring; Owner: elcrypto
--

SELECT pg_catalog.setval('monitoring.processed_signals_id_seq', 1, false);


--
-- Name: protection_events_id_seq; Type: SEQUENCE SET; Schema: monitoring; Owner: elcrypto
--

SELECT pg_catalog.setval('monitoring.protection_events_id_seq', 1209, true);


--
-- Name: system_health_id_seq; Type: SEQUENCE SET; Schema: monitoring; Owner: elcrypto
--

SELECT pg_catalog.setval('monitoring.system_health_id_seq', 5222, true);


--
-- Name: trades_id_seq; Type: SEQUENCE SET; Schema: monitoring; Owner: elcrypto
--

SELECT pg_catalog.setval('monitoring.trades_id_seq', 227, true);


--
-- Name: alert_rules alert_rules_pkey; Type: CONSTRAINT; Schema: monitoring; Owner: elcrypto
--

ALTER TABLE ONLY monitoring.alert_rules
    ADD CONSTRAINT alert_rules_pkey PRIMARY KEY (id);


--
-- Name: alert_rules alert_rules_rule_name_key; Type: CONSTRAINT; Schema: monitoring; Owner: elcrypto
--

ALTER TABLE ONLY monitoring.alert_rules
    ADD CONSTRAINT alert_rules_rule_name_key UNIQUE (rule_name);


--
-- Name: applied_migrations applied_migrations_migration_file_key; Type: CONSTRAINT; Schema: monitoring; Owner: elcrypto
--

ALTER TABLE ONLY monitoring.applied_migrations
    ADD CONSTRAINT applied_migrations_migration_file_key UNIQUE (migration_file);


--
-- Name: applied_migrations applied_migrations_pkey; Type: CONSTRAINT; Schema: monitoring; Owner: elcrypto
--

ALTER TABLE ONLY monitoring.applied_migrations
    ADD CONSTRAINT applied_migrations_pkey PRIMARY KEY (id);


--
-- Name: daily_stats daily_stats_date_key; Type: CONSTRAINT; Schema: monitoring; Owner: elcrypto
--

ALTER TABLE ONLY monitoring.daily_stats
    ADD CONSTRAINT daily_stats_date_key UNIQUE (date);


--
-- Name: daily_stats daily_stats_pkey; Type: CONSTRAINT; Schema: monitoring; Owner: elcrypto
--

ALTER TABLE ONLY monitoring.daily_stats
    ADD CONSTRAINT daily_stats_pkey PRIMARY KEY (id);


--
-- Name: performance_metrics performance_metrics_metric_date_metric_hour_exchange_key; Type: CONSTRAINT; Schema: monitoring; Owner: elcrypto
--

ALTER TABLE ONLY monitoring.performance_metrics
    ADD CONSTRAINT performance_metrics_metric_date_metric_hour_exchange_key UNIQUE (metric_date, metric_hour, exchange);


--
-- Name: performance_metrics performance_metrics_pkey; Type: CONSTRAINT; Schema: monitoring; Owner: elcrypto
--

ALTER TABLE ONLY monitoring.performance_metrics
    ADD CONSTRAINT performance_metrics_pkey PRIMARY KEY (id);


--
-- Name: positions positions_pkey; Type: CONSTRAINT; Schema: monitoring; Owner: elcrypto
--

ALTER TABLE ONLY monitoring.positions
    ADD CONSTRAINT positions_pkey PRIMARY KEY (id);


--
-- Name: processed_signals processed_signals_pkey; Type: CONSTRAINT; Schema: monitoring; Owner: elcrypto
--

ALTER TABLE ONLY monitoring.processed_signals
    ADD CONSTRAINT processed_signals_pkey PRIMARY KEY (id);


--
-- Name: processed_signals processed_signals_signal_id_key; Type: CONSTRAINT; Schema: monitoring; Owner: elcrypto
--

ALTER TABLE ONLY monitoring.processed_signals
    ADD CONSTRAINT processed_signals_signal_id_key UNIQUE (signal_id);


--
-- Name: protection_events protection_events_pkey; Type: CONSTRAINT; Schema: monitoring; Owner: elcrypto
--

ALTER TABLE ONLY monitoring.protection_events
    ADD CONSTRAINT protection_events_pkey PRIMARY KEY (id);


--
-- Name: system_health system_health_pkey; Type: CONSTRAINT; Schema: monitoring; Owner: elcrypto
--

ALTER TABLE ONLY monitoring.system_health
    ADD CONSTRAINT system_health_pkey PRIMARY KEY (id);


--
-- Name: trades trades_pkey; Type: CONSTRAINT; Schema: monitoring; Owner: elcrypto
--

ALTER TABLE ONLY monitoring.trades
    ADD CONSTRAINT trades_pkey PRIMARY KEY (id);


--
-- Name: idx_daily_stats_date; Type: INDEX; Schema: monitoring; Owner: elcrypto
--

CREATE INDEX idx_daily_stats_date ON monitoring.daily_stats USING btree (date DESC);


--
-- Name: idx_performance_metrics_date; Type: INDEX; Schema: monitoring; Owner: elcrypto
--

CREATE INDEX idx_performance_metrics_date ON monitoring.performance_metrics USING btree (metric_date DESC, metric_hour DESC);


--
-- Name: idx_performance_metrics_exchange; Type: INDEX; Schema: monitoring; Owner: elcrypto
--

CREATE INDEX idx_performance_metrics_exchange ON monitoring.performance_metrics USING btree (exchange);


--
-- Name: idx_positions_created_at; Type: INDEX; Schema: monitoring; Owner: elcrypto
--

CREATE INDEX idx_positions_created_at ON monitoring.positions USING btree (created_at DESC);


--
-- Name: idx_positions_exchange_symbol; Type: INDEX; Schema: monitoring; Owner: elcrypto
--

CREATE INDEX idx_positions_exchange_symbol ON monitoring.positions USING btree (exchange, symbol);


--
-- Name: idx_positions_exit_reason; Type: INDEX; Schema: monitoring; Owner: elcrypto
--

CREATE INDEX idx_positions_exit_reason ON monitoring.positions USING btree (exit_reason);


--
-- Name: idx_positions_leverage; Type: INDEX; Schema: monitoring; Owner: elcrypto
--

CREATE INDEX idx_positions_leverage ON monitoring.positions USING btree (leverage);


--
-- Name: idx_positions_opened_at; Type: INDEX; Schema: monitoring; Owner: elcrypto
--

CREATE INDEX idx_positions_opened_at ON monitoring.positions USING btree (opened_at DESC);


--
-- Name: idx_positions_status; Type: INDEX; Schema: monitoring; Owner: elcrypto
--

CREATE INDEX idx_positions_status ON monitoring.positions USING btree (status);


--
-- Name: idx_positions_trade_id; Type: INDEX; Schema: monitoring; Owner: elcrypto
--

CREATE INDEX idx_positions_trade_id ON monitoring.positions USING btree (trade_id);


--
-- Name: idx_positions_trailing_activated; Type: INDEX; Schema: monitoring; Owner: elcrypto
--

CREATE INDEX idx_positions_trailing_activated ON monitoring.positions USING btree (trailing_activated);


--
-- Name: idx_processed_signals_created_at; Type: INDEX; Schema: monitoring; Owner: elcrypto
--

CREATE INDEX idx_processed_signals_created_at ON monitoring.processed_signals USING btree (created_at DESC);


--
-- Name: idx_processed_signals_signal_id; Type: INDEX; Schema: monitoring; Owner: elcrypto
--

CREATE INDEX idx_processed_signals_signal_id ON monitoring.processed_signals USING btree (signal_id);


--
-- Name: idx_processed_signals_symbol; Type: INDEX; Schema: monitoring; Owner: elcrypto
--

CREATE INDEX idx_processed_signals_symbol ON monitoring.processed_signals USING btree (symbol);


--
-- Name: idx_processed_signals_symbol_action_created; Type: INDEX; Schema: monitoring; Owner: elcrypto
--

CREATE INDEX idx_processed_signals_symbol_action_created ON monitoring.processed_signals USING btree (symbol, action, created_at DESC);


--
-- Name: idx_protection_events_created_at; Type: INDEX; Schema: monitoring; Owner: elcrypto
--

CREATE INDEX idx_protection_events_created_at ON monitoring.protection_events USING btree (created_at DESC);


--
-- Name: idx_protection_events_position_id; Type: INDEX; Schema: monitoring; Owner: elcrypto
--

CREATE INDEX idx_protection_events_position_id ON monitoring.protection_events USING btree (position_id);


--
-- Name: idx_protection_events_type; Type: INDEX; Schema: monitoring; Owner: elcrypto
--

CREATE INDEX idx_protection_events_type ON monitoring.protection_events USING btree (event_type);


--
-- Name: idx_system_health_service; Type: INDEX; Schema: monitoring; Owner: elcrypto
--

CREATE INDEX idx_system_health_service ON monitoring.system_health USING btree (service_name, created_at DESC);


--
-- Name: idx_system_health_status; Type: INDEX; Schema: monitoring; Owner: elcrypto
--

CREATE INDEX idx_system_health_status ON monitoring.system_health USING btree (status);


--
-- Name: idx_trades_created_at; Type: INDEX; Schema: monitoring; Owner: elcrypto
--

CREATE INDEX idx_trades_created_at ON monitoring.trades USING btree (created_at DESC);


--
-- Name: idx_trades_exchange_symbol; Type: INDEX; Schema: monitoring; Owner: elcrypto
--

CREATE INDEX idx_trades_exchange_symbol ON monitoring.trades USING btree (exchange, symbol);


--
-- Name: idx_trades_order_id; Type: INDEX; Schema: monitoring; Owner: elcrypto
--

CREATE INDEX idx_trades_order_id ON monitoring.trades USING btree (order_id) WHERE (order_id IS NOT NULL);


--
-- Name: idx_trades_signal_id; Type: INDEX; Schema: monitoring; Owner: elcrypto
--

CREATE INDEX idx_trades_signal_id ON monitoring.trades USING btree (signal_id);


--
-- Name: idx_trades_status; Type: INDEX; Schema: monitoring; Owner: elcrypto
--

CREATE INDEX idx_trades_status ON monitoring.trades USING btree (status);


--
-- Name: unique_open_position_per_symbol_exchange_monitoring; Type: INDEX; Schema: monitoring; Owner: elcrypto
--

CREATE UNIQUE INDEX unique_open_position_per_symbol_exchange_monitoring ON monitoring.positions USING btree (symbol, exchange) WHERE ((status)::text = 'active'::text);


--
-- Name: trades update_daily_stats_trigger; Type: TRIGGER; Schema: monitoring; Owner: elcrypto
--

CREATE TRIGGER update_daily_stats_trigger AFTER INSERT ON monitoring.trades FOR EACH ROW EXECUTE FUNCTION monitoring.update_daily_stats();


--
-- Name: positions positions_trade_id_fkey; Type: FK CONSTRAINT; Schema: monitoring; Owner: elcrypto
--

ALTER TABLE ONLY monitoring.positions
    ADD CONSTRAINT positions_trade_id_fkey FOREIGN KEY (trade_id) REFERENCES monitoring.trades(id);


--
-- Name: protection_events protection_events_position_id_fkey; Type: FK CONSTRAINT; Schema: monitoring; Owner: elcrypto
--

ALTER TABLE ONLY monitoring.protection_events
    ADD CONSTRAINT protection_events_position_id_fkey FOREIGN KEY (position_id) REFERENCES monitoring.positions(id);


--
-- Name: trades trades_signal_id_fkey; Type: FK CONSTRAINT; Schema: monitoring; Owner: elcrypto
--

ALTER TABLE ONLY monitoring.trades
    ADD CONSTRAINT trades_signal_id_fkey FOREIGN KEY (signal_id) REFERENCES fas.scoring_history(id);


--
-- Name: trades trades_trading_pair_id_fkey; Type: FK CONSTRAINT; Schema: monitoring; Owner: elcrypto
--

ALTER TABLE ONLY monitoring.trades
    ADD CONSTRAINT trades_trading_pair_id_fkey FOREIGN KEY (trading_pair_id) REFERENCES public.trading_pairs(id);


--
-- PostgreSQL database dump complete
--

\unrestrict Idez8L2LWS1btaNranFxDrq6iMpyA7ycvwjgsBeqhyVpCvezTXXgp4cHxwgE0tx

