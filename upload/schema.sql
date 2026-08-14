-- Схема хранилища нейропрофориентации BHS, проект bhs-analytics.
-- Персональные данные лежат отдельно от сигнала, связь только по session_id.

create table if not exists neuro_participants (
  id uuid primary key default gen_random_uuid(),
  full_name text not null,
  birth_year int,
  grade text,
  phone text,
  consent_at timestamptz not null,
  created_at timestamptz not null default now()
);

create table if not exists neuro_sessions (
  id text primary key,
  participant_id uuid references neuro_participants(id),
  created_at timestamptz not null default now(),
  operator text,
  device_serial text,
  lang text not null default 'ru',
  status text not null default 'done',
  has_eeg boolean not null default false,
  quality_score numeric
);

create table if not exists neuro_trials (
  id bigserial primary key,
  session_id text references neuro_sessions(id),
  domain text not null,
  trial_index int not null,
  stimulus_id text,
  correct boolean,
  rt_ms int
);

create table if not exists neuro_block_metrics (
  id bigserial primary key,
  session_id text references neuro_sessions(id),
  domain text not null,
  accuracy numeric,
  median_rt_ms numeric,
  rt_sd_ms numeric,
  erd_alpha_high numeric,
  erd_alpha_low numeric,
  theta_rise numeric,
  engagement numeric,
  attention_slope numeric,
  epochs_total int,
  epochs_rejected int
);

create table if not exists neuro_profiles (
  id bigserial primary key,
  session_id text unique references neuro_sessions(id),
  iaf numeric,
  iaf_prominence numeric,
  bands jsonb,
  domains jsonb,
  quality jsonb,
  method_version text not null
);

create index if not exists neuro_block_metrics_session_idx on neuro_block_metrics(session_id);
create index if not exists neuro_trials_session_idx on neuro_trials(session_id);
