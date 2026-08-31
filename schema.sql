create table if not exists tu_raw (
    record_key text primary key,
    source text not null,
    source_url text not null,
    source_page integer not null,
    fetched_at timestamptz not null,
    tu_number text,
    tu_date date,
    installation_type text,
    connection_point_raw text,
    voltage_raw text,
    requested_power_kw double precision,
    connection_type text,
    rem text,
    raw_payload jsonb not null default '{}'::jsonb,
    first_seen_at timestamptz not null default now(),
    last_seen_at timestamptz not null default now()
);

create table if not exists tu_parsed (
    record_key text primary key references tu_raw(record_key) on delete cascade,
    activity_type text not null,
    requested_power_kw double precision,
    connection_object_type text,
    connection_voltage_kv double precision,
    connection_object_number text,
    connection_object_name text,
    feeder_id text,
    parent_object_type text,
    parent_number text,
    parent_name text,
    parent_voltage_levels_kv jsonb not null default '[]'::jsonb,
    canonical_node_id text,
    confidence double precision not null default 0,
    needs_review boolean not null default true,
    flags jsonb not null default '[]'::jsonb,
    parse_error text,
    parsed_payload jsonb not null default '{}'::jsonb,
    parsed_at timestamptz not null default now()
);

create table if not exists grid_nodes (
    canonical_node_id text primary key,
    parent_object_type text,
    parent_number text,
    parent_name text,
    parent_voltage_levels_kv jsonb not null default '[]'::jsonb,
    first_seen_at timestamptz not null,
    last_seen_at timestamptz not null
);

create table if not exists node_metrics (
    canonical_node_id text not null references grid_nodes(canonical_node_id) on delete cascade,
    snapshot_date date not null,
    generation_mw double precision not null default 0,
    load_mw double precision not null default 0,
    bess_mw double precision not null default 0,
    other_mw double precision not null default 0,
    generation_tu_count integer not null default 0,
    load_tu_count integer not null default 0,
    bess_tu_count integer not null default 0,
    other_tu_count integer not null default 0,
    generation_3m_mw double precision not null default 0,
    generation_6m_mw double precision not null default 0,
    generation_12m_mw double precision not null default 0,
    load_3m_mw double precision not null default 0,
    load_6m_mw double precision not null default 0,
    load_12m_mw double precision not null default 0,
    bess_3m_mw double precision not null default 0,
    bess_6m_mw double precision not null default 0,
    bess_12m_mw double precision not null default 0,
    generation_tu_velocity_3m_per_month double precision not null default 0,
    load_tu_velocity_3m_per_month double precision not null default 0,
    bess_tu_velocity_3m_per_month double precision not null default 0,
    generation_tu_velocity_12m_per_month double precision not null default 0,
    load_tu_velocity_12m_per_month double precision not null default 0,
    bess_tu_velocity_12m_per_month double precision not null default 0,
    generation_load_ratio double precision,
    net_tu_imbalance_mw double precision not null default 0,
    bess_share double precision not null default 0,
    review_count integer not null default 0,
    data_confidence double precision not null default 0,
    generation_pressure integer not null default 0,
    load_pressure integer not null default 0,
    bess_pressure integer not null default 0,
    created_at timestamptz not null default now(),
    primary key (canonical_node_id, snapshot_date)
);

create table if not exists pipeline_runs (
    id bigserial primary key,
    source text not null,
    status text not null check (status in ('running', 'success', 'failed')),
    started_at timestamptz not null default now(),
    finished_at timestamptz,
    counts jsonb not null default '{}'::jsonb,
    error text
);

create table if not exists tu_row_versions (
    row_fingerprint text primary key,
    logical_tu_key text not null,
    source text not null,
    tu_number text,
    tu_date date,
    contract_number text,
    contract_date text,
    installation_type text,
    commissioning_stages text,
    connection_point_raw text,
    voltage_raw text,
    requested_power_kw double precision,
    connection_type text,
    rem text,
    payment_date text,
    raw_payload jsonb not null default '{}'::jsonb,
    first_seen_at timestamptz not null,
    last_seen_at timestamptz not null
);

create table if not exists tu_observations (
    observation_key text primary key,
    run_id bigint not null references pipeline_runs(id),
    row_fingerprint text not null references tu_row_versions(row_fingerprint),
    source_page integer not null,
    source_row_index integer not null,
    fetched_at timestamptz not null,
    unique (run_id, source_page, source_row_index)
);

create table if not exists tu_snapshot_resolution (
    run_id bigint not null references pipeline_runs(id),
    logical_tu_key text not null,
    status text not null check (status in ('canonical', 'ambiguous')),
    representative_row_fingerprint text references tu_row_versions(row_fingerprint),
    observation_count integer not null check (observation_count >= 1),
    row_version_count integer not null check (row_version_count >= 1),
    material_signature_count integer not null check (material_signature_count >= 1),
    conflict_fields jsonb not null default '[]'::jsonb,
    ambiguous_capacity_min_kw double precision,
    ambiguous_capacity_max_kw double precision,
    resolution_reason text not null,
    resolved_at timestamptz not null default now(),
    primary key (run_id, logical_tu_key),
    check (
        ambiguous_capacity_min_kw is null
        or ambiguous_capacity_max_kw is null
        or ambiguous_capacity_min_kw <= ambiguous_capacity_max_kw
    ),
    check (
        (status = 'canonical' and representative_row_fingerprint is not null)
        or (status = 'ambiguous' and representative_row_fingerprint is null)
    )
);

create table if not exists tu_canonical_parsed (
    run_id bigint not null references pipeline_runs(id),
    logical_tu_key text not null,
    representative_row_fingerprint text not null references tu_row_versions(row_fingerprint),
    activity_type text not null,
    requested_power_kw double precision,
    connection_object_type text,
    connection_voltage_kv double precision,
    connection_object_number text,
    connection_object_name text,
    feeder_id text,
    parent_object_type text,
    parent_number text,
    parent_name text,
    parent_voltage_levels_kv jsonb not null default '[]'::jsonb,
    canonical_node_id text,
    confidence double precision not null default 0,
    needs_review boolean not null default true,
    flags jsonb not null default '[]'::jsonb,
    parse_error text,
    parsed_payload jsonb not null default '{}'::jsonb,
    parsed_at timestamptz not null default now(),
    primary key (run_id, logical_tu_key)
);

create table if not exists node_metrics_v2 (
    run_id bigint not null references pipeline_runs(id),
    canonical_node_id text not null references grid_nodes(canonical_node_id) on delete cascade,
    snapshot_date date not null,
    generation_mw double precision not null default 0,
    load_mw double precision not null default 0,
    bess_mw double precision not null default 0,
    other_mw double precision not null default 0,
    generation_tu_count integer not null default 0,
    load_tu_count integer not null default 0,
    bess_tu_count integer not null default 0,
    other_tu_count integer not null default 0,
    generation_3m_mw double precision not null default 0,
    generation_6m_mw double precision not null default 0,
    generation_12m_mw double precision not null default 0,
    load_3m_mw double precision not null default 0,
    load_6m_mw double precision not null default 0,
    load_12m_mw double precision not null default 0,
    bess_3m_mw double precision not null default 0,
    bess_6m_mw double precision not null default 0,
    bess_12m_mw double precision not null default 0,
    generation_tu_velocity_3m_per_month double precision not null default 0,
    load_tu_velocity_3m_per_month double precision not null default 0,
    bess_tu_velocity_3m_per_month double precision not null default 0,
    generation_tu_velocity_12m_per_month double precision not null default 0,
    load_tu_velocity_12m_per_month double precision not null default 0,
    bess_tu_velocity_12m_per_month double precision not null default 0,
    generation_load_ratio double precision,
    net_tu_imbalance_mw double precision not null default 0,
    bess_share double precision not null default 0,
    review_count integer not null default 0,
    data_confidence double precision not null default 0,
    generation_pressure integer not null default 0,
    load_pressure integer not null default 0,
    bess_pressure integer not null default 0,
    ambiguous_tu_count integer not null default 0,
    ambiguous_capacity_min_mw double precision,
    ambiguous_capacity_max_mw double precision,
    created_at timestamptz not null default now(),
    primary key (run_id, canonical_node_id)
);

create or replace view current_node_metrics_v2 as
select m.*
from node_metrics_v2 m
join pipeline_runs r on r.id = m.run_id
where r.status = 'success'
  and r.id = (
      select max(r2.id)
      from pipeline_runs r2
      where r2.source = r.source and r2.status = 'success'
  );

create index if not exists idx_tu_raw_tu_date on tu_raw(tu_date);
create index if not exists idx_tu_raw_last_seen_at on tu_raw(last_seen_at);
create index if not exists idx_tu_parsed_node on tu_parsed(canonical_node_id);
create index if not exists idx_tu_parsed_activity on tu_parsed(activity_type);
create index if not exists idx_node_metrics_snapshot_date on node_metrics(snapshot_date);
create index if not exists idx_node_metrics_generation_pressure on node_metrics(generation_pressure desc);
create index if not exists idx_node_metrics_bess_pressure on node_metrics(bess_pressure desc);
create index if not exists idx_grid_nodes_last_seen_at on grid_nodes(last_seen_at);
create index if not exists idx_pipeline_runs_started_at on pipeline_runs(started_at desc);
create index if not exists idx_tu_row_versions_logical_tu_key on tu_row_versions(logical_tu_key);
create index if not exists idx_tu_row_versions_last_seen_at on tu_row_versions(last_seen_at);
create index if not exists idx_tu_observations_run_id on tu_observations(run_id);
create index if not exists idx_tu_snapshot_resolution_run_status on tu_snapshot_resolution(run_id, status);
create index if not exists idx_tu_canonical_parsed_run_node on tu_canonical_parsed(run_id, canonical_node_id);
create index if not exists idx_node_metrics_v2_snapshot_date on node_metrics_v2(snapshot_date);
create index if not exists idx_node_metrics_v2_generation_pressure on node_metrics_v2(generation_pressure desc);
create index if not exists idx_node_metrics_v2_bess_pressure on node_metrics_v2(bess_pressure desc);
