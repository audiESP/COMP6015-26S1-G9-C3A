create table if not exists c3a_app_training_topics (
    id uuid primary key default gen_random_uuid(),
    slug text not null unique,
    title text not null,
    description text,
    sort_order int not null default 0,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists c3a_app_training_materials (
    id uuid primary key default gen_random_uuid(),
    topic_id uuid not null references c3a_app_training_topics(id) on delete cascade,
    title text not null,
    type text not null check (type in ('article', 'video', 'pdf', 'link')),
    summary text,
    body text,
    url text,
    duration_minutes int,
    sort_order int not null default 0,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists c3a_app_training_materials_topic_sort_idx
    on c3a_app_training_materials(topic_id, sort_order);

insert into c3a_app_training_topics (slug, title, description, sort_order) values
    ('emergency-response', 'Emergency Response', 'Recognising and responding to urgent situations during a visit.', 1),
    ('medication-support', 'Medication Support', 'Safe practices for assisting clients with medication.', 2),
    ('manual-handling', 'Manual Handling', 'Safe techniques for assisting client mobility and transfers.', 3)
on conflict (slug) do nothing;

insert into c3a_app_training_materials (topic_id, title, type, summary, body, duration_minutes, sort_order)
select t.id, m.title, m.type, m.summary, m.body, m.duration_minutes, m.sort_order
from c3a_app_training_topics t
join (values
    (
        'emergency-response',
        'CPR Training',
        'article',
        'Step-by-step adult CPR guidance for home-care settings.',
        e'1. Check responsiveness and call for help.\n2. Call emergency services immediately.\n3. Place the person on their back on a firm surface.\n4. Give 30 chest compressions at a rate of 100-120 per minute, pressing at least 5cm deep.\n5. Give 2 rescue breaths if trained to do so.\n6. Continue cycles of 30 compressions and 2 breaths until help arrives or the person responds.',
        8,
        1
    ),
    (
        'emergency-response',
        'Recognising a Fall',
        'article',
        'What to check and report immediately after a client fall.',
        e'1. Do not move the client until you have checked for injury.\n2. Check for pain, bleeding, and ability to move limbs.\n3. If a head injury or fracture is suspected, do not attempt to move the client - call emergency services.\n4. Note the time, location, and circumstances of the fall.\n5. Report the incident through the app immediately after ensuring safety.',
        5,
        2
    ),
    (
        'medication-support',
        'Safe Medication Assistance',
        'article',
        'Core rules for supporting clients with their medication.',
        e'1. Only assist with medication that is already prescribed and packaged for the client.\n2. Always check the medication label against the care plan before assisting.\n3. Never administer an injection or crush tablets unless explicitly authorised.\n4. Record what was given, when, and note anything unusual (refusal, side effects).\n5. If a dose is missed or refused, report it through the app the same day.',
        6,
        1
    ),
    (
        'manual-handling',
        'Safe Transfer Techniques',
        'article',
        'Protecting yourself and the client during transfers and repositioning.',
        e'1. Assess the client''s mobility and any equipment needed before starting.\n2. Keep your back straight and bend at the knees, not the waist.\n3. Keep the client close to your body during transfers.\n4. Use mobility aids (hoists, slide sheets, belts) as specified in the care plan.\n5. Stop and ask for help if the transfer feels unsafe for either of you.',
        7,
        1
    )
) as m(topic_slug, title, type, summary, body, duration_minutes, sort_order)
    on m.topic_slug = t.slug
where not exists (
    select 1 from c3a_app_training_materials existing
    where existing.topic_id = t.id and existing.title = m.title
);
