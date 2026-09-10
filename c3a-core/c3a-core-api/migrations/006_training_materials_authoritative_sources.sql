alter table c3a_app_training_materials
    add column if not exists source_name text,
    add column if not exists source_url text;

delete from c3a_app_training_materials;

insert into c3a_app_training_materials (
    topic_id, title, type, summary, body, url, source_name, source_url, duration_minutes, sort_order
)
select
    t.id, m.title, m.type, m.summary, m.body, m.url, m.source_name, m.source_url, m.duration_minutes, m.sort_order
from c3a_app_training_topics t
join (values
    (
        'emergency-response',
        'CPR Training',
        'pdf',
        'The DRSABCD action plan and core compression technique for adult CPR.',
        e'1. Check for Danger to yourself, bystanders, and the patient before approaching.\n2. Check Responsiveness - talk to the person and gently squeeze their shoulders.\n3. Send for help - call 000 and ask someone to find an AED if one is available.\n4. Open the Airway and check for normal Breathing for no more than 10 seconds.\n5. If not breathing normally, start CPR: 30 chest compressions followed by 2 breaths, for all ages.\n6. Compress at a rate of 100-120 per minute, pushing down at least one-third of the chest depth (more than 5cm in an adult).\n7. Attach a Defibrillator (AED) as soon as one arrives and follow its voice prompts.\n8. Continue CPR until the person responds normally, a health professional takes over, or an AED advises otherwise.',
        'https://www.anzcor.org/assets/anzcor-guidelines/guideline-8-cardiopulmonary-resuscitation-cpr-225.pdf',
        'Australian Resuscitation Council (ANZCOR) - Guideline 8: Cardiopulmonary Resuscitation',
        'https://www.anzcor.org/assets/anzcor-guidelines/guideline-8-cardiopulmonary-resuscitation-cpr-225.pdf',
        8,
        1
    ),
    (
        'emergency-response',
        'Recognising and Responding to a Fall',
        'pdf',
        'What to check and how to respond immediately after a client fall.',
        e'1. Stay calm and do not rush to move the person - check for injury first.\n2. Check for pain, bleeding, obvious deformity, or loss of consciousness before helping them move.\n3. If a head injury, spinal injury, or fracture is suspected, do not move the person - call 000 immediately.\n4. If no serious injury is suspected, assist the person up slowly using safe manual handling technique, or wait for help if needed.\n5. Monitor the person closely afterwards for delayed symptoms such as confusion or worsening pain.\n6. Record the time, location, and circumstances of the fall, and report it through the required process as soon as possible.\n7. Every fall should also prompt a review of the person''s fall-risk factors as part of their ongoing care plan.',
        'https://www.safetyandquality.gov.au/sites/default/files/resources/attachments/falls-guidelines-for-community-care.pdf',
        'Australian Commission on Safety and Quality in Health Care - Preventing Falls and Harm from Falls in Older People (Community Care)',
        'https://www.safetyandquality.gov.au/sites/default/files/resources/attachments/falls-guidelines-for-community-care.pdf',
        6,
        2
    ),
    (
        'medication-support',
        'Safe Medication Assistance',
        'pdf',
        'Core rules for safely supporting a client with their medication.',
        e'1. Only assist with medication that has already been prescribed, dispensed, and clearly labelled for that specific client.\n2. Check the "5 rights" before assisting: right person, right medication, right dose, right time, right route.\n3. Compare the label on the medication against the client''s current medication list or care plan.\n4. Do not alter, crush, or repackage medication unless you are specifically authorised and trained to do so.\n5. Record what was given (or not given) and at what time, immediately after assisting.\n6. If a dose is refused, missed, or you are unsure, do not guess - withhold the dose and report it the same day.\n7. Store any medication you are responsible for securely, and keep each client''s medication separate.',
        'https://www.hpw.qld.gov.au/__data/assets/pdf_file/0026/3779/guidelineformedicationassistance.pdf',
        'Queensland Government - Guideline for Medication Assistance',
        'https://www.hpw.qld.gov.au/__data/assets/pdf_file/0026/3779/guidelineformedicationassistance.pdf',
        6,
        1
    ),
    (
        'manual-handling',
        'Safe Transfer and Manual Handling',
        'pdf',
        'Risk-reduction steps for safely assisting a client to move, transfer, or reposition.',
        e'1. Assess the task before starting: the client''s mobility, weight, ability to assist, and the space available.\n2. Follow the hierarchy of controls - use mechanical aids (hoists, slide sheets, transfer belts) instead of manual lifting wherever possible.\n3. If manual assistance is unavoidable, keep your back straight, bend at the knees, and keep the client close to your body.\n4. Never lift and twist at the same time - move your feet to turn instead of twisting your spine.\n5. Use a team transfer (two or more workers) for tasks that cannot be done safely alone.\n6. Communicate clearly with the client and any co-worker before and during the movement.\n7. Stop the task and seek help if it feels unsafe, painful, or beyond what you are trained and equipped to do.',
        'https://www.safeworkaustralia.gov.au/system/files/documents/1905/model-cop-hazardous-manual-tasks.pdf',
        'Safe Work Australia - Model Code of Practice: Hazardous Manual Tasks',
        'https://www.safeworkaustralia.gov.au/system/files/documents/1905/model-cop-hazardous-manual-tasks.pdf',
        7,
        1
    )
) as m(topic_slug, title, type, summary, body, url, source_name, source_url, duration_minutes, sort_order)
    on m.topic_slug = t.slug;
