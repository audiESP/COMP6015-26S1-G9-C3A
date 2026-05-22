create extension if not exists pgcrypto;

create table if not exists c3a_app_workers (
    id text primary key,
    name text not null,
    role text not null check (role in ('care_worker', 'nurse', 'supervisor')),
    active boolean not null default true,
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists c3a_app_patient_profiles (
    patient_id uuid primary key references c3a_synthea_patients(id),
    display_name text,
    medical_record_number text,
    diagnosis_summary text,
    notes text,
    preferred_language text,
    interpreter_required boolean,
    cultural_background text,
    mobility_support text,
    cognitive_status text,
    dietary_notes text,
    communication_notes text,
    care_risk_flags jsonb not null default '[]'::jsonb,
    allergies_override jsonb,
    medications_override jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists c3a_app_shifts (
    id uuid primary key default gen_random_uuid(),
    worker_id text not null references c3a_app_workers(id),
    shift_date date not null,
    label text not null,
    status text not null default 'scheduled'
        check (status in ('scheduled', 'in_progress', 'completed', 'cancelled')),
    started_at timestamptz,
    completed_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (worker_id, shift_date, label)
);

create table if not exists c3a_app_visits (
    id uuid primary key default gen_random_uuid(),
    external_key text unique,
    shift_id uuid references c3a_app_shifts(id) on delete set null,
    patient_id uuid not null references c3a_synthea_patients(id),
    worker_id text not null references c3a_app_workers(id),
    scheduled_at timestamptz not null,
    sort_order int not null default 0,
    purpose text not null,
    location text not null,
    planned_address text,
    planned_lat numeric,
    planned_lon numeric,
    location_threshold_meters numeric not null default 150,
    status text not null check (
        status in (
            'scheduled',
            'arrived',
            'in_progress',
            'delayed',
            'incident',
            'follow_up_required',
            'review_required',
            'completed'
        )
    ),
    lifecycle_step text not null check (
        lifecycle_step in (
            'pre_visit',
            'arrival',
            'care_tasks',
            'incident_active',
            'review',
            'closed'
        )
    ),
    arrived_at timestamptz,
    completed_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists c3a_app_visits_worker_scheduled_idx
    on c3a_app_visits(worker_id, scheduled_at);
create index if not exists c3a_app_visits_shift_sort_idx
    on c3a_app_visits(shift_id, sort_order);
create index if not exists c3a_app_visits_patient_idx
    on c3a_app_visits(patient_id);

create table if not exists c3a_app_care_tasks (
    id uuid primary key default gen_random_uuid(),
    visit_id uuid not null references c3a_app_visits(id) on delete cascade,
    task_key text not null,
    label text not null,
    type text not null check (
        type in (
            'arrival',
            'meal',
            'medication',
            'wellbeing',
            'mobility',
            'documentation',
            'follow_up'
        )
    ),
    status text not null default 'pending'
        check (status in ('pending', 'completed', 'delayed', 'skipped', 'issue')),
    due_at timestamptz,
    detail text,
    sort_order int not null,
    completed_at timestamptz,
    status_note text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (visit_id, task_key)
);

create index if not exists c3a_app_care_tasks_visit_sort_idx
    on c3a_app_care_tasks(visit_id, sort_order);

create table if not exists c3a_app_location_snapshots (
    id uuid primary key default gen_random_uuid(),
    visit_id uuid not null references c3a_app_visits(id) on delete cascade,
    type text not null check (type in ('check_in', 'check_out')),
    recorded_at timestamptz not null,
    lat numeric,
    lon numeric,
    accuracy_meters numeric,
    distance_from_planned_meters numeric,
    within_expected_area boolean,
    permission_status text not null
        check (permission_status in ('unknown', 'granted', 'denied', 'unavailable')),
    source text not null check (source in ('gps', 'manual_override')),
    note text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (visit_id, type)
);

create index if not exists c3a_app_location_snapshots_visit_type_idx
    on c3a_app_location_snapshots(visit_id, type);

create table if not exists c3a_app_visit_events (
    id uuid primary key default gen_random_uuid(),
    visit_id uuid not null references c3a_app_visits(id) on delete cascade,
    task_id uuid references c3a_app_care_tasks(id) on delete set null,
    location_snapshot_id uuid references c3a_app_location_snapshots(id) on delete set null,
    created_by_worker_id text references c3a_app_workers(id),
    type text not null check (
        type in (
            'arrived',
            'care_started',
            'running_late',
            'medication_given',
            'medication_delayed',
            'location_check_in',
            'location_check_out',
            'location_permission_denied',
            'location_out_of_range',
            'patient_unsteady',
            'fall_found',
            'escalation_triggered',
            'follow_up_required',
            'review_started',
            'incident_check_completed',
            'visit_completed'
        )
    ),
    occurred_at timestamptz not null default now(),
    note text,
    idempotency_key text,
    payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create unique index if not exists c3a_app_visit_events_idempotency_idx
    on c3a_app_visit_events(idempotency_key)
    where idempotency_key is not null;
create index if not exists c3a_app_visit_events_visit_time_idx
    on c3a_app_visit_events(visit_id, occurred_at desc);
create index if not exists c3a_app_visit_events_type_idx
    on c3a_app_visit_events(type);

create table if not exists c3a_app_risk_alerts (
    id uuid primary key default gen_random_uuid(),
    visit_id uuid not null references c3a_app_visits(id) on delete cascade,
    alert_key text not null,
    level text not null check (level in ('low', 'moderate', 'high')),
    title text not null,
    message text not null,
    source text not null check (source in ('rules', 'rag', 'ai', 'manual')),
    status text not null default 'active'
        check (status in ('active', 'resolved', 'dismissed')),
    generated_from_event_id uuid references c3a_app_visit_events(id) on delete set null,
    payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (visit_id, alert_key)
);

create index if not exists c3a_app_risk_alerts_visit_status_level_idx
    on c3a_app_risk_alerts(visit_id, status, level);
