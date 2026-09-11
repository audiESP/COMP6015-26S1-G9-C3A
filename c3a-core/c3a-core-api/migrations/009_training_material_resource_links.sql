-- Keep one material per document/topic, with related files and translations
-- displayed together. Existing single-source materials remain supported.
alter table c3a_app_training_materials
    add column if not exists resource_links jsonb not null default '[]'::jsonb
        check (jsonb_typeof(resource_links) = 'array');

insert into c3a_app_training_topics (slug, title, description, sort_order) values
    ('food-nutrition-dining', 'Food, Nutrition & Dining', 'Supporting safe, enjoyable meals, swallowing and daily oral health care.', 5),
    ('skin-pressure-injury', 'Skin Care & Pressure Injury Prevention', 'Understanding pressure injuries and supporting patients and families with prevention.', 6),
    ('rights-responsibilities', 'Rights & Responsibilities', 'Respectful care, privacy, safe practice and raising concerns in aged care.', 7)
on conflict (slug) do nothing;

-- Update matching materials in place and insert only missing ones. This avoids
-- resetting the catalogue or duplicating materials when the migration is rerun.
with seed (topic_slug, title, type, summary, url, source_name, source_url, sort_order, resource_links) as (
    values
    (
        'emergency-response',
        'CPR Training',
        'pdf',
        'NSW Ambulance CPR chart covering the DRSABCD emergency response, cardiopulmonary resuscitation and use of an automated external defibrillator (AED).',
        'https://www.ambulance.nsw.gov.au/__data/assets/pdf_file/0006/976398/NSW-Ambulance-CPR-chart.pdf',
        'NSW Ambulance - NSW Government',
        'https://www.ambulance.nsw.gov.au/__data/assets/pdf_file/0006/976398/NSW-Ambulance-CPR-chart.pdf',
        1,
        $$[
            {"title": "NSW Ambulance CPR Chart", "language": "en", "type": "pdf", "url": "https://www.ambulance.nsw.gov.au/__data/assets/pdf_file/0006/976398/NSW-Ambulance-CPR-chart.pdf"}
        ]$$::jsonb
    ),
    (
        'infection-control-hygiene',
        'The Aged Care Infection Prevention and Control Guide',
        'pdf',
        'A guide to infection prevention in aged care, including hand hygiene, protective equipment, standard and transmission-based precautions, cleaning and staff safety. Includes the full PDF and the official page for chapter downloads and updates.',
        'https://www.safetyandquality.gov.au/sites/default/files/resources/attachments//The-Aged-Care-Infection-Prevention-and-Control-Guide.pdf',
        'Australian Commission on Safety and Quality in Health Care',
        'https://www.safetyandquality.gov.au/resources/aged-care-infection-prevention-and-control-guide',
        2,
        $$[
            {"title": "The Aged Care Infection Prevention and Control Guide - Full PDF", "language": "en", "type": "pdf", "url": "https://www.safetyandquality.gov.au/sites/default/files/resources/attachments//The-Aged-Care-Infection-Prevention-and-Control-Guide.pdf"},
            {"title": "The Aged Care Infection Prevention and Control Guide - Chapters and Updates", "language": "en", "type": "link", "url": "https://www.safetyandquality.gov.au/resources/aged-care-infection-prevention-and-control-guide"}
        ]$$::jsonb
    ),
    (
        'manual-handling',
        'Manual Tasks Guide for Carers',
        'pdf',
        'WorkSafe WA guidance for carers supporting people at home. Explains manual-task injury risks, planning, equipment and ways to reduce strain during transfers, mobility and personal care.',
        'https://www.worksafe.wa.gov.au/system/files/documents/2024-12/GL_ManualTask_Carers.pdf',
        'WorkSafe WA - Government of Western Australia',
        'https://www.worksafe.wa.gov.au/system/files/documents/2024-12/GL_ManualTask_Carers.pdf',
        3,
        $$[
            {"title": "Manual Tasks Guide for Carers", "language": "en", "type": "pdf", "url": "https://www.worksafe.wa.gov.au/system/files/documents/2024-12/GL_ManualTask_Carers.pdf"}
        ]$$::jsonb
    ),
    (
        'emergency-response',
        'Preventing Falls and Harm from Falls in Residential Aged Care',
        'pdf',
        'Best-practice guidelines for Australian residential aged care services. Covers individual fall risks, mobility, the care environment, monitoring and post-fall management.',
        'https://www.safetyandquality.gov.au/sites/default/files/resources/attachments/falls-guidelines-for-racs.pdf',
        'Australian Commission on Safety and Quality in Health Care',
        'https://www.safetyandquality.gov.au/sites/default/files/resources/attachments/falls-guidelines-for-racs.pdf',
        6,
        $$[
            {"title": "Preventing Falls and Harm from Falls in Older People - Australian Residential Aged Care Services", "language": "en", "type": "pdf", "url": "https://www.safetyandquality.gov.au/sites/default/files/resources/attachments/falls-guidelines-for-racs.pdf"}
        ]$$::jsonb
    ),
    (
        'food-nutrition-dining',
        'Supporting Safe and Enjoyable Mealtimes',
        'pdf',
        'A fact sheet for providers and aged care workers supporting people with eating, drinking and swallowing difficulties. Covers recognising concerns, assessment, mealtime support plans and individual preferences.',
        'https://www.agedcarequality.gov.au/sites/default/files/media/supporting-safe-and-enjoyable-mealtimes-for-people-with-swallowing-difficulties-age-care-staff.pdf',
        'Aged Care Quality and Safety Commission - Australian Government',
        'https://www.agedcarequality.gov.au/sites/default/files/media/supporting-safe-and-enjoyable-mealtimes-for-people-with-swallowing-difficulties-age-care-staff.pdf',
        1,
        $$[
            {"title": "Supporting Safe and Enjoyable Mealtimes for People with Eating, Drinking and Swallowing Difficulties", "language": "en", "type": "pdf", "url": "https://www.agedcarequality.gov.au/sites/default/files/media/supporting-safe-and-enjoyable-mealtimes-for-people-with-swallowing-difficulties-age-care-staff.pdf"}
        ]$$::jsonb
    ),
    (
        'food-nutrition-dining',
        'Know, Observe, Support, Act - Mealtime Support',
        'pdf',
        'A practical poster for aged care staff about knowing each resident, observing their dining experience and changes, supporting their needs and acting on mealtime concerns.',
        'https://www.agedcarequality.gov.au/sites/default/files/media/p-know-observe-support-act_poster.pdf',
        'Aged Care Quality and Safety Commission - Australian Government',
        'https://www.agedcarequality.gov.au/resource-library/know-observe-support-act-poster',
        2,
        $$[
            {"title": "Know, Observe, Support, Act - Poster for Aged Care Staff", "language": "en", "type": "pdf", "url": "https://www.agedcarequality.gov.au/sites/default/files/media/p-know-observe-support-act_poster.pdf"},
            {"title": "Know, Observe, Support, Act - Official Resource Page", "language": "en", "type": "link", "url": "https://www.agedcarequality.gov.au/resource-library/know-observe-support-act-poster"}
        ]$$::jsonb
    ),
    (
        'food-nutrition-dining',
        'Food, Nutrition and Dining - Resources for Workers',
        'link',
        'Official resources for aged care workers on food choices, enjoyable dining, swallowing difficulties, oral health and supporting people living with dementia. Includes fact sheets, posters and educational videos.',
        'https://www.agedcarequality.gov.au/workers/food-nutrition-and-dining-resources-workers',
        'Aged Care Quality and Safety Commission - Australian Government',
        'https://www.agedcarequality.gov.au/workers/food-nutrition-and-dining-resources-workers',
        3,
        $$[
            {"title": "Food, Nutrition & Dining: Resources for Workers", "language": "en", "type": "link", "url": "https://www.agedcarequality.gov.au/workers/food-nutrition-and-dining-resources-workers"}
        ]$$::jsonb
    ),
    (
        'rights-responsibilities',
        'Aged Care Code of Conduct - Guide for Workers and Responsible Persons',
        'pdf',
        'A guide to the Aged Care Code of Conduct for workers and responsible persons. Covers personal choice, dignity, diversity, privacy, safe and competent care, honesty and responding to concerns about harm.',
        'https://www.agedcarequality.gov.au/sites/default/files/media/code-guide-for-workers-and-responsible-persons.pdf',
        'Aged Care Quality and Safety Commission - Australian Government',
        'https://www.agedcarequality.gov.au/sites/default/files/media/code-guide-for-workers-and-responsible-persons.pdf',
        1,
        $$[
            {"title": "Aged Care Code of Conduct - Guide for Aged Care Workers and Responsible Persons", "language": "en", "type": "pdf", "url": "https://www.agedcarequality.gov.au/sites/default/files/media/code-guide-for-workers-and-responsible-persons.pdf"}
        ]$$::jsonb
    ),
    (
        'skin-pressure-injury',
        'Pressure Injury Prevention - Information for Patients and Families',
        'pdf',
        'NSW Health information for patients and families about pressure injuries and their prevention. Use this page to open the English, Arabic, Greek, Hindi, Italian, Korean, Traditional Chinese, Simplified Chinese or Vietnamese handout.',
        'https://cec.health.nsw.gov.au/__data/assets/pdf_file/0007/259288/Pressure-Injury-Prevention-Information-for-Patients-and-Families-English.pdf',
        'Clinical Excellence Commission - NSW Health',
        'https://cec.health.nsw.gov.au/__data/assets/pdf_file/0007/259288/Pressure-Injury-Prevention-Information-for-Patients-and-Families-English.pdf',
        1,
        $$[
            {"title": "Pressure Injury Prevention - English", "language": "en", "type": "pdf", "url": "https://cec.health.nsw.gov.au/__data/assets/pdf_file/0007/259288/Pressure-Injury-Prevention-Information-for-Patients-and-Families-English.pdf"},
            {"title": "الوقاية من إصابات الضغط - العربية", "language": "ar", "type": "pdf", "url": "https://cec.health.nsw.gov.au/__data/assets/pdf_file/0009/259281/arabic-pipp.pdf"},
            {"title": "Πρόληψη ελκών πίεσης - Ελληνικά", "language": "el", "type": "pdf", "url": "https://cec.health.nsw.gov.au/__data/assets/pdf_file/0003/259284/greek-pipp.pdf"},
            {"title": "दबाव से होने वाली चोटों की रोकथाम - हिन्दी", "language": "hi", "type": "pdf", "url": "https://cec.health.nsw.gov.au/__data/assets/pdf_file/0004/259285/hindi-pipp.pdf"},
            {"title": "Prevenzione delle lesioni da pressione - Italiano", "language": "it", "type": "pdf", "url": "https://cec.health.nsw.gov.au/__data/assets/pdf_file/0005/259286/italian-pipp.pdf"},
            {"title": "욕창 예방 - 한국어", "language": "ko", "type": "pdf", "url": "https://cec.health.nsw.gov.au/__data/assets/pdf_file/0006/259287/korean-pipp.pdf"},
            {"title": "壓力性損傷預防 - 繁體中文", "language": "zh-Hant", "type": "pdf", "url": "https://cec.health.nsw.gov.au/__data/assets/pdf_file/0011/259283/chinesetrad-pipp.pdf"},
            {"title": "压力性损伤预防 - 简体中文", "language": "zh-Hans", "type": "pdf", "url": "https://cec.health.nsw.gov.au/__data/assets/pdf_file/0010/259282/chinesesimp-pipp.pdf"},
            {"title": "Phòng ngừa tổn thương do tì đè - Tiếng Việt", "language": "vi", "type": "pdf", "url": "https://cec.health.nsw.gov.au/__data/assets/pdf_file/0008/259289/vietnamese-pipp.pdf"}
        ]$$::jsonb
    )
), materials as (
    select t.id as topic_id, seed.*
    from seed
    join c3a_app_training_topics t on t.slug = seed.topic_slug
), updated as (
    update c3a_app_training_materials existing
    set type = m.type,
        summary = m.summary,
        body = null,
        url = m.url,
        source_name = m.source_name,
        source_url = m.source_url,
        duration_minutes = null,
        sort_order = m.sort_order,
        resource_links = m.resource_links,
        updated_at = now()
    from materials m
    where existing.topic_id = m.topic_id and existing.title = m.title
      and (existing.type, existing.summary, existing.body, existing.url,
           existing.source_name, existing.source_url, existing.duration_minutes,
           existing.sort_order, existing.resource_links)
          is distinct from
          (m.type, m.summary, null::text, m.url, m.source_name, m.source_url,
           null::int, m.sort_order, m.resource_links)
    returning existing.id
)
insert into c3a_app_training_materials (
    topic_id, title, type, summary, body, url, source_name, source_url,
    duration_minutes, sort_order, resource_links
)
select
    m.topic_id, m.title, m.type, m.summary, null, m.url, m.source_name, m.source_url,
    null, m.sort_order, m.resource_links
from materials m
where not exists (
    select 1 from c3a_app_training_materials existing
    where existing.topic_id = m.topic_id and existing.title = m.title
);
