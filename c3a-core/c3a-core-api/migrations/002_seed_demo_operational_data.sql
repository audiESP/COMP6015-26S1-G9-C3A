insert into c3a_app_workers (id, name, role, active, metadata, updated_at)
values ('cw-001', 'Ava Chen', 'care_worker', true, '{"shift":"Morning home-care run"}'::jsonb, now())
on conflict (id) do update
set name = excluded.name,
    role = excluded.role,
    active = excluded.active,
    metadata = excluded.metadata,
    updated_at = now();

insert into c3a_app_patient_profiles (
    patient_id,
    display_name,
    medical_record_number,
    diagnosis_summary,
    notes,
    preferred_language,
    interpreter_required,
    cultural_background,
    mobility_support,
    cognitive_status,
    dietary_notes,
    communication_notes,
    care_risk_flags,
    medications_override,
    updated_at
)
values
(
    '70b32985-ca41-2bd6-7b1a-7b2e031a9f37'::uuid,
    'Tresa Beier',
    '70b32985',
    'Chronic disease monitoring; falls risk; polypharmacy review',
    'Synthetic patient from Neon c3a_synthea tables, paired with CALD profile for scenario testing.',
    'Vietnamese',
    true,
    'Vietnamese Australian',
    'Walker',
    'No known impairment',
    'Ask before serving beef-heavy meals; prefers rice-based meals.',
    'Speak slowly, avoid idioms, and allow a family member to support medication discussions.',
    '["falls risk","language barrier","polypharmacy review"]'::jsonb,
    '["Lunchtime medication assistance required"]'::jsonb,
    now()
),
(
    '96779f23-e1c7-9b86-f7b5-bfae61b7eaec'::uuid,
    'Flor Bauch',
    '96779f23',
    'Transfer assistance; nutrition monitoring; polypharmacy review',
    null,
    'Mandarin',
    true,
    'Chinese Australian',
    'Requires transfer assistance',
    'Requires orientation prompts',
    'Prefers warm meals; avoid cold drinks when possible.',
    'Use plain language, confirm understanding with teach-back, involve adult child for complex care decisions.',
    '["polypharmacy review","language barrier","nutrition monitoring"]'::jsonb,
    '["Afternoon medication prompt"]'::jsonb,
    now()
),
(
    '8b9f8dea-94be-df0d-4eff-b79f01091f3d'::uuid,
    'Tyesha Brakus',
    '8b9f8dea',
    'Falls risk; language barrier; personal-care preferences',
    null,
    'Arabic',
    true,
    'Lebanese Australian',
    'Independent',
    'Requires orientation prompts',
    'Halal diet; avoid pork-derived products unless clinically necessary and discussed.',
    'Offer same-gender care worker for personal care when possible; check prayer-time preferences.',
    '["falls risk","language barrier","polypharmacy review"]'::jsonb,
    '["Evening medication prompt"]'::jsonb,
    now()
)
on conflict (patient_id) do update
set display_name = excluded.display_name,
    medical_record_number = excluded.medical_record_number,
    diagnosis_summary = excluded.diagnosis_summary,
    notes = excluded.notes,
    preferred_language = excluded.preferred_language,
    interpreter_required = excluded.interpreter_required,
    cultural_background = excluded.cultural_background,
    mobility_support = excluded.mobility_support,
    cognitive_status = excluded.cognitive_status,
    dietary_notes = excluded.dietary_notes,
    communication_notes = excluded.communication_notes,
    care_risk_flags = excluded.care_risk_flags,
    medications_override = excluded.medications_override,
    updated_at = now();

insert into c3a_app_shifts (worker_id, shift_date, label, status, updated_at)
values ('cw-001', date '2026-05-12', 'Morning home-care run', 'scheduled', now())
on conflict (worker_id, shift_date, label) do update
set status = excluded.status,
    updated_at = now();

with shift_row as (
    select id
    from c3a_app_shifts
    where worker_id = 'cw-001'
      and shift_date = date '2026-05-12'
      and label = 'Morning home-care run'
)
insert into c3a_app_visits (
    external_key,
    shift_id,
    patient_id,
    worker_id,
    scheduled_at,
    sort_order,
    purpose,
    location,
    planned_address,
    planned_lat,
    planned_lon,
    location_threshold_meters,
    status,
    lifecycle_step,
    updated_at
)
select *
from (
    values
    (
        'visit-home-1200',
        (select id from shift_row),
        '70b32985-ca41-2bd6-7b1a-7b2e031a9f37'::uuid,
        'cw-001',
        '2026-05-12T12:00:00+08:00'::timestamptz,
        1,
        'Home visit - lunch and medication support',
        'Home visit - lunch and medication support',
        'Demo home address, Victoria Park WA',
        -31.9766,
        115.9007,
        150,
        'completed',
        'closed',
        now()
    ),
    (
        'visit-home-1330',
        (select id from shift_row),
        '96779f23-e1c7-9b86-f7b5-bfae61b7eaec'::uuid,
        'cw-001',
        '2026-05-12T13:30:00+08:00'::timestamptz,
        2,
        'Home visit - wellbeing and transfer support',
        'Home visit - wellbeing and transfer support',
        'Demo home address, East Perth WA',
        -31.9583,
        115.877,
        150,
        'scheduled',
        'pre_visit',
        now()
    ),
    (
        'visit-home-1500',
        (select id from shift_row),
        '8b9f8dea-94be-df0d-4eff-b79f01091f3d'::uuid,
        'cw-001',
        '2026-05-12T15:00:00+08:00'::timestamptz,
        3,
        'Home visit - mobility and personal-care support',
        'Home visit - mobility and personal-care support',
        'Demo home address, Cannington WA',
        -32.0155,
        115.9369,
        150,
        'scheduled',
        'pre_visit',
        now()
    )
) as seed (
    external_key,
    shift_id,
    patient_id,
    worker_id,
    scheduled_at,
    sort_order,
    purpose,
    location,
    planned_address,
    planned_lat,
    planned_lon,
    location_threshold_meters,
    status,
    lifecycle_step,
    updated_at
)
on conflict (external_key) do update
set shift_id = excluded.shift_id,
    patient_id = excluded.patient_id,
    worker_id = excluded.worker_id,
    scheduled_at = excluded.scheduled_at,
    sort_order = excluded.sort_order,
    purpose = excluded.purpose,
    location = excluded.location,
    planned_address = excluded.planned_address,
    planned_lat = excluded.planned_lat,
    planned_lon = excluded.planned_lon,
    location_threshold_meters = excluded.location_threshold_meters,
    status = excluded.status,
    lifecycle_step = excluded.lifecycle_step,
    arrived_at = case
        when excluded.status = 'completed' then coalesce(c3a_app_visits.arrived_at, excluded.scheduled_at)
        else null
    end,
    completed_at = case
        when excluded.status = 'completed' then coalesce(c3a_app_visits.completed_at, excluded.scheduled_at + interval '1 hour')
        else null
    end,
    updated_at = now();

update c3a_app_visits
set arrived_at = case
        when status = 'completed' then coalesce(arrived_at, scheduled_at)
        else null
    end,
    completed_at = case
        when status = 'completed' then coalesce(completed_at, scheduled_at + interval '1 hour')
        else null
    end,
    updated_at = now()
where external_key in ('visit-home-1200', 'visit-home-1330', 'visit-home-1500');

with task_seed as (
    select *
    from (
        values
        ('visit-home-1200', 'arrival', 'Arrive and confirm identity', 'arrival', '2026-05-12T12:00:00+08:00'::timestamptz, 'Confirm address, introduce visit purpose, check preferred communication.', 1, 'completed'),
        ('visit-home-1200', 'meal', 'Support lunch routine', 'meal', '2026-05-12T12:10:00+08:00'::timestamptz, 'Offer rice-based meal option and check appetite.', 2, 'completed'),
        ('visit-home-1200', 'medication', 'Assist lunchtime medication', 'medication', '2026-05-12T12:20:00+08:00'::timestamptz, 'Confirm medication prompt and document if delayed or refused.', 3, 'completed'),
        ('visit-home-1200', 'wellbeing', 'Wellbeing and comfort check', 'wellbeing', '2026-05-12T12:30:00+08:00'::timestamptz, 'Ask about pain, dizziness, hydration, and unusual symptoms.', 4, 'completed'),
        ('visit-home-1200', 'mobility', 'Observe mobility and falls risk', 'mobility', '2026-05-12T12:35:00+08:00'::timestamptz, 'Check walker use and whether gait is steady today.', 5, 'completed'),
        ('visit-home-1200', 'documentation', 'Complete visit summary', 'documentation', '2026-05-12T12:45:00+08:00'::timestamptz, 'Record completed tasks, issues, escalation, and follow-up needs.', 6, 'completed'),
        ('visit-home-1330', 'arrival', 'Arrive and confirm identity', 'arrival', '2026-05-12T13:30:00+08:00'::timestamptz, 'Confirm interpreter preference and orient the patient to the visit.', 1, 'pending'),
        ('visit-home-1330', 'wellbeing', 'Wellbeing and nutrition check', 'wellbeing', '2026-05-12T13:40:00+08:00'::timestamptz, 'Check comfort, hydration, appetite, and orientation.', 2, 'pending'),
        ('visit-home-1330', 'mobility', 'Transfer assistance observation', 'mobility', '2026-05-12T13:50:00+08:00'::timestamptz, 'Observe transfer support needs and document changes.', 3, 'pending'),
        ('visit-home-1330', 'documentation', 'Complete visit summary', 'documentation', '2026-05-12T14:05:00+08:00'::timestamptz, 'Record nutrition, transfer support, and family communication needs.', 4, 'pending'),
        ('visit-home-1500', 'arrival', 'Arrive and confirm identity', 'arrival', '2026-05-12T15:00:00+08:00'::timestamptz, 'Check communication preferences before personal-care support.', 1, 'pending'),
        ('visit-home-1500', 'wellbeing', 'Orientation and comfort check', 'wellbeing', '2026-05-12T15:10:00+08:00'::timestamptz, 'Confirm comfort, pain, and any confusion today.', 2, 'pending'),
        ('visit-home-1500', 'mobility', 'Mobility and personal-care support', 'mobility', '2026-05-12T15:20:00+08:00'::timestamptz, 'Observe steadiness and respect same-gender care preference where possible.', 3, 'pending'),
        ('visit-home-1500', 'documentation', 'Complete visit summary', 'documentation', '2026-05-12T15:40:00+08:00'::timestamptz, 'Record mobility, preferences, and any escalation.', 4, 'pending')
    ) as seed(external_key, task_key, label, type, due_at, detail, sort_order, status)
)
insert into c3a_app_care_tasks (
    visit_id,
    task_key,
    label,
    type,
    status,
    due_at,
    detail,
    sort_order,
    completed_at,
    updated_at
)
select v.id,
       s.task_key,
       s.label,
       s.type,
       s.status,
       s.due_at,
       s.detail,
       s.sort_order,
       case when s.status = 'completed' then s.due_at else null end,
       now()
from task_seed s
join c3a_app_visits v on v.external_key = s.external_key
on conflict (visit_id, task_key) do update
set label = excluded.label,
    type = excluded.type,
    status = excluded.status,
    due_at = excluded.due_at,
    detail = excluded.detail,
    sort_order = excluded.sort_order,
    completed_at = excluded.completed_at,
    status_note = null,
    updated_at = now();

delete from c3a_app_visit_events
where visit_id in (
    select id from c3a_app_visits where external_key in ('visit-home-1330', 'visit-home-1500')
);

delete from c3a_app_location_snapshots
where visit_id in (
    select id from c3a_app_visits where external_key in ('visit-home-1330', 'visit-home-1500')
);

delete from c3a_app_risk_alerts
where visit_id in (
    select id from c3a_app_visits where external_key in ('visit-home-1330', 'visit-home-1500')
);

with alert_seed as (
    select *
    from (
        values
        ('visit-home-1200', 'cald-language', 'moderate', 'Interpreter support may be needed', 'Use plain language, avoid idioms, and confirm understanding before discussing medication or care decisions.', 'rules'),
        ('visit-home-1200', 'falls-baseline', 'moderate', 'Mobility or falls risk flagged', 'Tresa Beier mobility support: Walker. Observe steadiness before support.', 'rules'),
        ('visit-home-1330', 'cald-language', 'moderate', 'Interpreter support may be needed', 'Use plain language, avoid idioms, and confirm understanding before discussing medication or care decisions.', 'rules'),
        ('visit-home-1330', 'falls-baseline', 'moderate', 'Mobility or falls risk flagged', 'Flor Bauch mobility support: Requires transfer assistance. Observe steadiness before support.', 'rules'),
        ('visit-home-1500', 'cald-language', 'moderate', 'Interpreter support may be needed', 'Use plain language, avoid idioms, and confirm understanding before discussing medication or care decisions.', 'rules'),
        ('visit-home-1500', 'falls-baseline', 'moderate', 'Mobility or falls risk flagged', 'Tyesha Brakus mobility support: Independent. Observe steadiness before support.', 'rules')
    ) as seed(external_key, alert_key, level, title, message, source)
)
insert into c3a_app_risk_alerts (
    visit_id,
    alert_key,
    level,
    title,
    message,
    source,
    status,
    updated_at
)
select v.id,
       s.alert_key,
       s.level,
       s.title,
       s.message,
       s.source,
       'active',
       now()
from alert_seed s
join c3a_app_visits v on v.external_key = s.external_key
on conflict (visit_id, alert_key) do update
set level = excluded.level,
    title = excluded.title,
    message = excluded.message,
    source = excluded.source,
    status = excluded.status,
    updated_at = now();
