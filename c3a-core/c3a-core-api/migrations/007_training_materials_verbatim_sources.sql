insert into c3a_app_training_topics (slug, title, description, sort_order) values
    ('infection-control-hygiene', 'Infection Control & Hygiene', 'Hand hygiene and infection prevention practices for home visits.', 4)
on conflict (slug) do nothing;

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
        'The DRS ABCD action plan and core compression technique, quoted from ANZCOR Guideline 8.',
        $$DRS ABCD

1. DANGERS - Check for danger (assess and manage risks to the rescuer and others)
2. RESPONSIVENESS - Check for response (if unresponsive)
3. SEND - Send for help
4. AIRWAY - Open the airway
5. BREATHING - Check breathing (if not breathing / abnormal breathing)
6. CPR - Start CPR (give 30 chest compressions followed by two breaths)
7. DEFIBRILLATION - Attach an Automated External Defibrillator (AED) as soon as available and follow the prompts.

When rescuers perform chest compressions they should be at a rate of approximately 100-120/min. (See ANZCOR Guideline 6 Compressions)

The rescuer should continue cardiopulmonary resuscitation until any of the following conditions have been met: the person responds or begins breathing normally; it is impossible to continue (e.g. exhaustion); a health care professional arrives and takes over CPR; a health care professional directs that CPR be ceased.$$,
        'https://www.anzcor.org/assets/anzcor-guidelines/guideline-8-cardiopulmonary-resuscitation-cpr-225.pdf',
        'Australian Resuscitation Council (ANZCOR) - Guideline 8: Cardiopulmonary Resuscitation',
        'https://www.anzcor.org/assets/anzcor-guidelines/guideline-8-cardiopulmonary-resuscitation-cpr-225.pdf',
        6,
        1
    ),
    (
        'emergency-response',
        'Recognising and Responding to a Fall',
        'pdf',
        'The post-fall management good practice points, quoted from the ACSQHC community care falls guidelines.',
        $$Post-fall Management

All falls, including falls which result in minor or no injury, must be taken seriously. Falls may be the first and main indication of another underlying and treatable condition in an older person. Older people who fall are also more likely to fall again.

All members of the multidisciplinary team, including aged care workers, the general practitioner, nurse practitioner, registered nurses and health professionals, should be aware of:
- what constitutes a fall
- what to do when an older person falls, or if an older person reports a recent fall
- what follow-up is necessary, including reporting and incident managing processes

Good practice points
- Immediately after a fall, provide a post-fall response, clinical care and escalation where required. In collaboration with the older person and their carer, assess whether basic life support is needed and provide as required.
- Identify, investigate and report the cause and the consequences of the fall.
- Facilitate a comprehensive assessment for every older person who falls and implement immediate actions such as a medication review.
- Conduct a post-fall analysis to inform the evaluation of the older person's multidisciplinary care plan, including fall prevention interventions.
- Support more mobile older people to improve their ability to rise from the floor after a fall unassisted to reduce the risk of a 'long-lie' occurring.$$,
        'https://www.safetyandquality.gov.au/sites/default/files/resources/attachments/falls-guidelines-for-community-care.pdf',
        'Australian Commission on Safety and Quality in Health Care - Preventing Falls and Harm from Falls in Older People (Community Care)',
        'https://www.safetyandquality.gov.au/sites/default/files/resources/attachments/falls-guidelines-for-community-care.pdf',
        6,
        2
    ),
    (
        'emergency-response',
        'Recognising Stroke - F.A.S.T.',
        'link',
        'The F.A.S.T. test, quoted from the Stroke Foundation Australia.',
        $$F.A.S.T.

Face: Check their face. Has their mouth drooped?
Arms: Can they lift both arms?
Speech: Is their speech slurred? Do they understand you?
Time: Is critical. If you see any of these signs, call 000 straight away.

A stroke is always a medical emergency. If you or someone else experiences the signs of stroke, no matter how long they last, call 000 immediately.$$,
        'https://strokefoundation.org.au/about-stroke/learn/signs-of-stroke',
        'Stroke Foundation Australia - Signs of Stroke',
        'https://strokefoundation.org.au/about-stroke/learn/signs-of-stroke',
        3,
        3
    ),
    (
        'medication-support',
        'Safe Medication Assistance - The Seven Rights',
        'pdf',
        'The seven "rights" for safe medication administration, quoted from the Queensland Government guideline.',
        $$Seven 'rights' for safe medication administration

To reduce the risk of a resident experiencing a medication error, it is recommended that staff assisting with medication follow the principles of the seven 'rights' for safe medication administration that have been developed within the healthcare sector and are widely used:

Right person - check the resident's photo identification to ensure the medication is for the right person. Check that the name on the medication container label matches the resident's name. When the resident is commenced on a new medication, check that they have no previous allergy to the medication.

Right medication - cross check the medication name in the Medication Record with the medication label. Check the medication has been stored correctly, and where an expiry date is visible check the medication has not expired.

Right dosage - for dose administration aids, check the right number of capsules or tablets are contained in the section that is to be used. For other medication packaging, ensure the dose is clearly documented on the pharmacist's label on the medication container.

Right time - ensure medication is taken as close as possible to the prescribed time. Some medications have further instructions that should be adhered to, e.g. 'with food', 'half hour before food' or 'after other medications'. Confirm the time since the last dose is appropriate, particularly for 'when required' (PRN) medications.

Right route - ensure medication is taken or applied via the prescribed route, e.g. oral, topical, inhalation. Instructions for the specific route should be provided in writing by the resident's medical practitioner, which staff are to follow.

Right to refuse - the resident has the right to refuse to take a medication. If a resident refuses to take their medication, this must be recorded on the Medication Distribution Record, and contact should be made with the resident's medical practitioner or pharmacist and their instructions followed.

Right documentation - ensure that the medication is signed for by the staff member on the relevant form and that the correct code for specific circumstances is used when applicable.$$,
        'https://www.hpw.qld.gov.au/__data/assets/pdf_file/0026/3779/guidelineformedicationassistance.pdf',
        'Queensland Government - Guideline for Medication Assistance (s1.7)',
        'https://www.hpw.qld.gov.au/__data/assets/pdf_file/0026/3779/guidelineformedicationassistance.pdf',
        6,
        1
    ),
    (
        'medication-support',
        'Responding to a Missed or Refused Dose',
        'pdf',
        'What to do if a client refuses or misses medication, quoted from the Queensland Government guideline.',
        $$Refusal to take medication by a resident

If a resident refuses medication, or has missed taking their dose for other reasons:
- observe the resident for any changes to their condition and/or behaviour
- if it is believed that a resident may suffer acute symptoms unless prompt treatment is given, or their safety may be at risk, call an ambulance
- contact the resident's medical practitioner or pharmacist as soon as possible and follow their instructions
- if the medical practitioner or pharmacist are not available, call the Medicines Line on 1300 633 424 or 13HEALTH
- if changes in the resident's condition or behaviour are observed, or it is suspected that a resident is displaying withdrawal effects, contact the resident's medical practitioner for instruction.

The service provider and staff must be aware of the risk of withdrawal effects in instances where a resident has refused to take their medication.$$,
        'https://www.hpw.qld.gov.au/__data/assets/pdf_file/0026/3779/guidelineformedicationassistance.pdf',
        'Queensland Government - Guideline for Medication Assistance (s1.11)',
        'https://www.hpw.qld.gov.au/__data/assets/pdf_file/0026/3779/guidelineformedicationassistance.pdf',
        4,
        2
    ),
    (
        'manual-handling',
        'Safe Transfer and Manual Handling',
        'pdf',
        'What counts as a hazardous manual task and the hierarchy of controls, quoted from Safe Work Australia.',
        $$What is a hazardous manual task?

A hazardous manual task is a task requiring a person to lift, lower, push, pull, carry or otherwise move, hold or restrain any person, animal or thing involving one or more of the following:
- repetitive or sustained force
- high or sudden force
- repetitive movement
- sustained or awkward posture, or
- exposure to vibration.

These hazards directly stress the body and can lead to an injury.

The hierarchy of control measures

You must always aim to eliminate the risk. If eliminating the hazards and associated risks is not reasonably practicable, you must minimise the risk by one or more of the following:
- Substitution - minimise the risk by substituting or replacing a hazard or hazardous work practice with something that gives rise to a lesser risk.
- Isolation - minimise the risk by isolating or separating the hazard or hazardous work practice from any person exposed to it.
- Engineering controls - physical control measures to minimise risk, aimed at eliminating or minimising the frequency, magnitude and duration of movements, forces and postures.

If risk remains, it must be minimised by implementing administrative controls, so far as is reasonably practicable. Any remaining risk must be minimised with suitable personal protective equipment (PPE).$$,
        'https://www.safeworkaustralia.gov.au/system/files/documents/1905/model-cop-hazardous-manual-tasks.pdf',
        'Safe Work Australia - Model Code of Practice: Hazardous Manual Tasks (s1.2, s4.1)',
        'https://www.safeworkaustralia.gov.au/system/files/documents/1905/model-cop-hazardous-manual-tasks.pdf',
        7,
        1
    ),
    (
        'infection-control-hygiene',
        'Hand Hygiene - The 5 Moments',
        'pdf',
        'The 5 Moments for Hand Hygiene in aged care, quoted from the ACSQHC fact sheet.',
        $$Know the 5 Moments for Hand Hygiene in aged care

HAND HYGIENE IS FOR EVERYBODY including older people, nurses, doctors, allied health, support workers, domestic staff, contractors, administration staff, families and volunteers.

You must ALWAYS use alcohol-based hand rub when performing hand hygiene UNLESS hands are visibly soiled or after contact with bodily fluids, then use soap and water.

1. BEFORE touching a person - to protect older people from germs.
2. BEFORE any procedure - to protect older people from germs.
3. IMMEDIATELY AFTER a procedure, or bodily fluid exposure - to protect older people, yourself, other staff, and visitors from germs.
4. AFTER touching a person - to protect older people, yourself, other staff, and visitors from germs.
5. AFTER touching a person's surroundings - to protect older people and their home environment from germs.

Gloves should always be worn when in contact with blood or body fluid, non-intact skin, mucous membranes or chemical hazards. Both gloves should be removed and changed as soon as they are damaged, when no longer in contact with blood/body fluids/chemicals, and between care activities. Gloves do not replace the need to perform hand hygiene.$$,
        'https://www.safetyandquality.gov.au/sites/default/files/2026-04/know-the-5-moments-for-hand-hygiene-in-aged-care-fs.pdf',
        'Australian Commission on Safety and Quality in Health Care - Know the 5 Moments for Hand Hygiene in Aged Care',
        'https://www.safetyandquality.gov.au/sites/default/files/2026-04/know-the-5-moments-for-hand-hygiene-in-aged-care-fs.pdf',
        4,
        1
    )
) as m(topic_slug, title, type, summary, body, url, source_name, source_url, duration_minutes, sort_order)
    on m.topic_slug = t.slug;
