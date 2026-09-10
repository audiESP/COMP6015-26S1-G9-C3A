alter table c3a_app_risk_alerts
    drop constraint if exists c3a_app_risk_alerts_status_check;

alter table c3a_app_risk_alerts
    add constraint c3a_app_risk_alerts_status_check
    check (status in ('active', 'acknowledged', 'resolved', 'dismissed'));

alter table c3a_app_risk_alerts
    add column if not exists acknowledged_at timestamptz,
    add column if not exists acknowledged_by_worker_id text references c3a_app_workers(id),
    add column if not exists resolved_at timestamptz,
    add column if not exists resolved_by_worker_id text references c3a_app_workers(id),
    add column if not exists dismissed_at timestamptz,
    add column if not exists dismissed_by_worker_id text references c3a_app_workers(id),
    add column if not exists review_note text;

create table if not exists c3a_app_risk_alert_actions (
    id uuid primary key default gen_random_uuid(),
    alert_id uuid not null references c3a_app_risk_alerts(id) on delete cascade,
    visit_id uuid not null references c3a_app_visits(id) on delete cascade,
    action text not null check (action in ('acknowledged', 'resolved', 'dismissed')),
    previous_status text not null,
    resulting_status text not null,
    actor_worker_id text not null references c3a_app_workers(id),
    note text,
    acted_at timestamptz not null default now()
);

create index if not exists c3a_app_risk_alert_actions_alert_time_idx
    on c3a_app_risk_alert_actions(alert_id, acted_at desc);

create index if not exists c3a_app_risk_alert_actions_visit_time_idx
    on c3a_app_risk_alert_actions(visit_id, acted_at desc);
