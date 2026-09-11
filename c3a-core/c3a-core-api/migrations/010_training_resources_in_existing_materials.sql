-- Correct 009 by retaining the original material pages and attaching related
-- resources to them. Do not replay 007: it deletes the existing catalogue.

-- Restore only the CPR source and excerpt replaced by 009. This is the exact
-- original content from 007; the NSW chart remains an additional resource.
update c3a_app_training_materials m
set body = $$DRS ABCD

1. DANGERS - Check for danger (assess and manage risks to the rescuer and others)
2. RESPONSIVENESS - Check for response (if unresponsive)
3. SEND - Send for help
4. AIRWAY - Open the airway
5. BREATHING - Check breathing (if not breathing / abnormal breathing)
6. CPR - Start CPR (give 30 chest compressions followed by two breaths)
7. DEFIBRILLATION - Attach an Automated External Defibrillator (AED) as soon as available and follow the prompts.

When rescuers perform chest compressions they should be at a rate of approximately 100-120/min. (See ANZCOR Guideline 6 Compressions)

The rescuer should continue cardiopulmonary resuscitation until any of the following conditions have been met: the person responds or begins breathing normally; it is impossible to continue (e.g. exhaustion); a health care professional arrives and takes over CPR; a health care professional directs that CPR be ceased.$$,
    url = 'https://www.anzcor.org/assets/anzcor-guidelines/guideline-8-cardiopulmonary-resuscitation-cpr-225.pdf',
    source_name = 'Australian Resuscitation Council (ANZCOR) - Guideline 8: Cardiopulmonary Resuscitation',
    source_url = 'https://www.anzcor.org/assets/anzcor-guidelines/guideline-8-cardiopulmonary-resuscitation-cpr-225.pdf',
    duration_minutes = 6,
    updated_at = now()
from c3a_app_training_topics t
where m.topic_id = t.id and t.slug = 'emergency-response'
  and m.title = 'CPR Training'
  and m.url = 'https://www.ambulance.nsw.gov.au/__data/assets/pdf_file/0006/976398/NSW-Ambulance-CPR-chart.pdf'
  and m.source_url = m.url
  and m.source_name = 'NSW Ambulance - NSW Government'
  and m.body is null and m.duration_minutes is null;

do $migration$
declare
    addition record;
    target_id uuid;
    target_topic_id uuid;
    combined_links jsonb;
begin
    for addition in
        select * from (values
            (
                'emergency-response',
                'CPR Training',
                'An introduction to the DRS ABCD action plan and cardiopulmonary resuscitation, bringing together the existing ANZCOR Guideline 8 excerpt and full guideline with the NSW Ambulance CPR chart as a separate quick-reference resource.',
                null::text,
                $$[{"title": "NSW Ambulance CPR Chart", "language": "en", "type": "pdf", "url": "https://www.ambulance.nsw.gov.au/__data/assets/pdf_file/0006/976398/NSW-Ambulance-CPR-chart.pdf"}]$$::jsonb
            ),
            (
                'emergency-response',
                'Recognising and Responding to a Fall',
                'Guidance on recognising falls, responding after a fall and reducing future harm, combining the Australian Commission on Safety and Quality in Health Care community care guideline and its existing post-fall management excerpt with a separate guideline for residential aged care services.',
                'Preventing Falls and Harm from Falls in Residential Aged Care',
                $$[{"title": "Preventing Falls and Harm from Falls in Older People - Australian Residential Aged Care Services", "language": "en", "type": "pdf", "url": "https://www.safetyandquality.gov.au/sites/default/files/resources/attachments/falls-guidelines-for-racs.pdf"}]$$::jsonb
            ),
            (
                'manual-handling',
                'Safe Transfer and Manual Handling',
                'Resources for recognising hazardous manual tasks and planning safer assistance, combining the existing Safe Work Australia code of practice and excerpt on hazards and control measures with the WorkSafe WA Manual Tasks Guide for Carers, which discusses reducing strain during transfers, mobility and personal care at home.',
                'Manual Tasks Guide for Carers',
                $$[{"title": "Manual Tasks Guide for Carers - WorkSafe WA", "language": "en", "type": "pdf", "url": "https://www.worksafe.wa.gov.au/system/files/documents/2024-12/GL_ManualTask_Carers.pdf"}]$$::jsonb
            ),
            (
                'infection-control-hygiene',
                'Hand Hygiene - The 5 Moments',
                'Resources from the Australian Commission on Safety and Quality in Health Care covering hand hygiene and wider infection prevention in aged care, bringing together the existing 5 Moments fact sheet and excerpt with The Aged Care Infection Prevention and Control Guide, including its full PDF and official page for chapters and updates on precautions, protective equipment, cleaning and staff safety.',
                'The Aged Care Infection Prevention and Control Guide',
                $$[
                    {"title": "The Aged Care Infection Prevention and Control Guide - Full PDF", "language": "en", "type": "pdf", "url": "https://www.safetyandquality.gov.au/sites/default/files/resources/attachments//The-Aged-Care-Infection-Prevention-and-Control-Guide.pdf"},
                    {"title": "The Aged Care Infection Prevention and Control Guide - Chapters and Updates", "language": "en", "type": "link", "url": "https://www.safetyandquality.gov.au/resources/aged-care-infection-prevention-and-control-guide"}
                ]$$::jsonb
            )
        ) as resources(topic_slug, title, summary, duplicate_title, links)
    loop
        select m.id, m.topic_id into strict target_id, target_topic_id
        from c3a_app_training_materials m
        join c3a_app_training_topics t on t.id = m.topic_id
        where t.slug = addition.topic_slug and m.title = addition.title;

        -- Append missing URLs, preserving any links already on the original page.
        select m.resource_links || coalesce((
            select jsonb_agg(link.value order by link.ordinality)
            from jsonb_array_elements(addition.links) with ordinality as link(value, ordinality)
            where not exists (
                select 1 from jsonb_array_elements(m.resource_links) existing
                where existing->>'url' = link.value->>'url'
            )
        ), '[]'::jsonb) into combined_links
        from c3a_app_training_materials m where m.id = target_id;

        update c3a_app_training_materials
        set summary = addition.summary, resource_links = combined_links, updated_at = now()
        where id = target_id
          and (summary, resource_links) is distinct from (addition.summary, combined_links);

        -- Remove only the duplicate seed pages from 009, after every resource
        -- on that page is available on the original. Keep pages with other
        -- resources, a custom excerpt or a different primary source.
        delete from c3a_app_training_materials duplicate
        where duplicate.topic_id = target_topic_id
          and duplicate.title = addition.duplicate_title
          and duplicate.url = addition.links->0->>'url'
          and duplicate.body is null and duplicate.duration_minutes is null
          and duplicate.source_url in (
              select link->>'url' from jsonb_array_elements(addition.links) link
          )
          and not exists (
              select 1 from jsonb_array_elements(duplicate.resource_links) link
              where not exists (
                  select 1 from jsonb_array_elements(combined_links) combined
                  where combined->>'url' = link->>'url'
              )
          );
    end loop;
end;
$migration$;
