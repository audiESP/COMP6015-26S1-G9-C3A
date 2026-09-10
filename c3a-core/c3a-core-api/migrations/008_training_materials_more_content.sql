insert into c3a_app_training_materials (
    topic_id, title, type, summary, body, url, source_name, source_url, duration_minutes, sort_order
)
select
    t.id, m.title, m.type, m.summary, m.body, m.url, m.source_name, m.source_url, m.duration_minutes, m.sort_order
from c3a_app_training_topics t
join (values
    (
        'emergency-response',
        'Recognising and Responding to a Diabetic Emergency',
        'pdf',
        'Signs of high and low blood sugar and what to do, quoted from the St John Ambulance Australia fact sheet.',
        $$Signs and symptoms

High blood sugar (hyperglycaemia): excessive thirst, tiredness, blurred vision, hot, dry skin, smell of acetone on breath.

Low blood sugar (hypoglycaemia): weakness, shaking, sweating, headache, faintness, dizziness, lack of concentration, teariness or crying, irritability or altered behaviour, hunger, numbness around the lips and fingers. These can progress quickly to slurred speech, confusion, loss of consciousness, seizures.

What to do - Low blood sugar (hypoglycaemia)
1. Help the patient to sit or lie in a comfortable position.
2. Reassure the patient.
3. Loosen any tight clothing.
4. Give the patient sugar, such as fruit juice or a soft drink (NOT 'diet' eg Coke Zero, Pepsi Max), sugar, jellybeans, glucose tablets.
5. Continue giving sugar every 15 minutes until the patient recovers.
6. Follow with carbohydrates, eg a sandwich, milk, fresh or dry fruit, or dry biscuits and cheese.
7. If there is no improvement in symptoms or the patient becomes unconscious, call Triple Zero (000) for an ambulance.

If you are not sure if the patient has low or high blood sugar, give them a drink containing sugar (DO NOT use 'diet' soft drinks). Giving any form of sugar can save a patient's life if blood sugar is low, and will not cause undue harm if blood sugar is high.$$,
        'https://stjohn.org.au/app/uploads/2025/08/Fact-sheets_diabetes.pdf',
        'St John Ambulance Australia - First Aid Fact Sheet: Diabetes Emergency',
        'https://stjohn.org.au/app/uploads/2025/08/Fact-sheets_diabetes.pdf',
        5,
        4
    ),
    (
        'emergency-response',
        'Recognising and Responding to Anaphylaxis',
        'link',
        'Signs of a severe allergic reaction and the emergency first aid steps, quoted from the Better Health Channel.',
        $$Signs of a mild to moderate allergic reaction: swelling of the lips, face and eyes; hives or welts; tingling mouth; abdominal pain, vomiting - these are signs of anaphylaxis for insect allergy.

Symptoms of a severe allergic reaction (anaphylaxis): difficult or noisy breathing; swelling of the tongue; swelling or tightness in the throat; wheeze or persistent cough; difficulty talking or hoarse voice; persistent dizziness or collapse; pale and floppy (young children).

Emergency first aid steps for anaphylaxis:
1. Lay the person flat - do not allow them to stand or walk.
2. Give adrenaline injector (such as EpiPen or Anapen) into the outer mid-thigh.
3. Phone an ambulance - call triple zero (000).
4. Phone family or emergency contact.
5. Further adrenaline may be given if there is no response after 5 minutes.
6. Transfer person to hospital for at least 4 hours of observation.$$,
        'https://www.betterhealth.vic.gov.au/health/conditionsandtreatments/allergic-reactions-emergency-first-aid',
        'Better Health Channel (Victorian Government) - Allergic Reactions Emergency First Aid',
        'https://www.betterhealth.vic.gov.au/health/conditionsandtreatments/allergic-reactions-emergency-first-aid',
        4,
        5
    ),
    (
        'medication-support',
        'When Required (PRN) Medication',
        'pdf',
        'Rules for assisting with as-needed medication, quoted from the Queensland Government guideline.',
        $$'When required' medication (pro re nata, PRN medication)

PRN medication is medication that is to be taken on an as required basis and is not intended for regular, continuous use. PRN medication can only be provided when the resident requests assistance, and is to be prescribed by a doctor to be given under specific circumstances. It is recommended the doctor provide written instructions about the particular circumstances under which the medication is to be given to a resident for relief of symptoms (temporary or intermittent), the interval between doses and the maximum total dose in 24 hours.

PRN medication can include pain relief for intermittent pain, sedatives for insomnia, or medication used for behaviour modification.

PRN medication must be given from a container that has been labelled for the specific resident. When assisting with PRN medication, check the Medication Record to ensure that the medication is given according to the prescribed time interval and that the maximum daily dose has not been exceeded. If advice about the use of PRN medication is needed, contact the resident's medical practitioner or pharmacist.

Doses of PRN medication taken by a resident must be recorded by the service provider and staff.$$,
        'https://www.hpw.qld.gov.au/__data/assets/pdf_file/0026/3779/guidelineformedicationassistance.pdf',
        'Queensland Government - Guideline for Medication Assistance (s2.5)',
        'https://www.hpw.qld.gov.au/__data/assets/pdf_file/0026/3779/guidelineformedicationassistance.pdf',
        4,
        3
    ),
    (
        'manual-handling',
        'Recognising Manual Handling Risk Factors',
        'pdf',
        'How to tell whether a task is hazardous, quoted from Safe Work Australia.',
        $$What are the risk factors?

A task involves a risk of a musculoskeletal disorder (MSD) developing if you answer 'yes' to the following:

Does the task involve any of the following: repetitive movement; sustained or awkward postures, or repetitive or sustained forces?

As a general guideline, 'repetitive' means a movement or force is performed more than twice a minute; 'sustained' means a posture or force is held for more than 30 seconds at a time. The risk increases as the degree of bending and twisting increases. The risk is greatest when the postures and movements are extreme, that is, towards the end of the movement range, and when they feel uncomfortable for the worker. The risk also increases as the magnitude of the force, the frequency of actions and the speed of actions increase.

As a general guideline, long duration means the task is done for more than a total of 2 hours over a whole shift or continuously for more than 30 minutes at a time.$$,
        'https://www.safeworkaustralia.gov.au/system/files/documents/1905/model-cop-hazardous-manual-tasks.pdf',
        'Safe Work Australia - Model Code of Practice: Hazardous Manual Tasks (s3.3)',
        'https://www.safeworkaustralia.gov.au/system/files/documents/1905/model-cop-hazardous-manual-tasks.pdf',
        5,
        2
    )
) as m(topic_slug, title, type, summary, body, url, source_name, source_url, duration_minutes, sort_order)
    on m.topic_slug = t.slug;
