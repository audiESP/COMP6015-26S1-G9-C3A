create table if not exists c3a_app_medication_support_records (
    id uuid primary key default gen_random_uuid(),
    visit_id uuid not null references c3a_app_visits(id) on delete cascade,
    task_id uuid references c3a_app_care_tasks(id) on delete set null,
    hcw_id text not null references c3a_app_workers(id),
    status text not null check (
        status in (
            'Completed',
            'Delayed',
            'Declined',
            'Unavailable',
            'Unable to Confirm'
        )
    ),
    notes text,
    recorded_at timestamptz not null default now(),
    medication_names jsonb not null default '[]'::jsonb,
    medication_items jsonb not null default '[]'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (visit_id),
    check (status = 'Completed' or nullif(trim(notes), '') is not null)
);

create index if not exists c3a_app_medication_support_visit_status_idx
    on c3a_app_medication_support_records(visit_id, status);

create index if not exists c3a_app_medication_support_hcw_recorded_idx
    on c3a_app_medication_support_records(hcw_id, recorded_at desc);

alter table c3a_app_medication_support_records
    add column if not exists medication_items jsonb not null default '[]'::jsonb;
