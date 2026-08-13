import {
  CareTask,
  IncidentChecklistItem,
  PatientInfo,
  RiskAlert,
  ScenarioContext,
  VisitContext,
  VisitQueueItem,
  WorkerContext,
} from '../types';

export const demoWorker: WorkerContext = {
  id: 'cw-001',
  name: 'Ava Chen',
  role: 'care_worker',
  shift: 'Morning home-care run',
};

export const demoPatient: PatientInfo = {
  id: '70b32985-ca41-2bd6-7b1a-7b2e031a9f37',
  name: 'Tresa Beier',
  age: 84,
  gender: 'Female',
  medicalRecordNumber: '70b32985',
  diagnosis: 'Chronic disease monitoring; falls risk; polypharmacy review',
  preferredLanguage: 'Vietnamese',
  interpreterRequired: true,
  culturalBackground: 'Vietnamese Australian',
  mobilitySupport: 'Walker',
  cognitiveStatus: 'No known impairment',
  dietaryNotes: 'Ask before serving beef-heavy meals; prefers rice-based meals.',
  communicationNotes:
    'Speak slowly, avoid idioms, and allow a family member to support medication discussions.',
  careRiskFlags: ['falls risk', 'language barrier', 'polypharmacy review'],
  allergies: ['Mold - mild cutaneous hypersensitivity'],
  medications: ['Lunchtime medication assistance required'],
  pastMedicalHistory: 'Type 2 diabetes; recurrent falls; chronic hypertension.',
  notes:
    'Synthetic patient from Neon c3a_synthea tables, paired with CALD profile for scenario testing.',
};

const florPatient: PatientInfo = {
  id: '96779f23-e1c7-9b86-f7b5-bfae61b7eaec',
  name: 'Flor Bauch',
  age: 93,
  gender: 'Female',
  medicalRecordNumber: '96779f23',
  diagnosis: 'Transfer assistance; nutrition monitoring; polypharmacy review',
  preferredLanguage: 'Mandarin',
  interpreterRequired: true,
  culturalBackground: 'Chinese Australian',
  mobilitySupport: 'Requires transfer assistance',
  cognitiveStatus: 'Requires orientation prompts',
  dietaryNotes: 'Prefers warm meals; avoid cold drinks when possible.',
  communicationNotes:
    'Use plain language, confirm understanding with teach-back, involve adult child for complex care decisions.',
  careRiskFlags: ['polypharmacy review', 'language barrier', 'nutrition monitoring'],
  medications: ['Afternoon medication prompt'],
  pastMedicalHistory: 'Osteoarthritis; chronic pain; previous hospital admissions for dizziness.',
};

const tyeshaPatient: PatientInfo = {
  id: '8b9f8dea-94be-df0d-4eff-b79f01091f3d',
  name: 'Tyesha Brakus',
  age: 77,
  gender: 'Female',
  medicalRecordNumber: '8b9f8dea',
  diagnosis: 'Falls risk; language barrier; personal-care preferences',
  preferredLanguage: 'Arabic',
  interpreterRequired: true,
  culturalBackground: 'Lebanese Australian',
  mobilitySupport: 'Independent',
  cognitiveStatus: 'Requires orientation prompts',
  dietaryNotes: 'Halal diet; avoid pork-derived products unless clinically necessary and discussed.',
  communicationNotes:
    'Offer same-gender care worker for personal care when possible; check prayer-time preferences.',
  careRiskFlags: ['falls risk', 'language barrier', 'polypharmacy review'],
  medications: ['Evening medication prompt'],
  pastMedicalHistory: 'Atrial fibrillation; recent discharge after dehydration-related admission.',
};

type DemoScenarioSeed = {
  patient: PatientInfo;
  visit: VisitContext;
  tasks: CareTask[];
  alerts: RiskAlert[];
};

function tasksForVisit(kind: 'lunch' | 'wellbeing' | 'mobility'): CareTask[] {
  if (kind === 'wellbeing') {
    return [
      {
        id: 'arrival',
        label: 'Arrive and confirm identity',
        type: 'arrival',
        status: 'pending',
        dueAt: '13:30',
        detail: 'Confirm interpreter preference and orient the patient to the visit.',
      },
      {
        id: 'wellbeing',
        label: 'Wellbeing and nutrition check',
        type: 'wellbeing',
        status: 'pending',
        dueAt: '13:40',
        detail: 'Check comfort, hydration, appetite, and orientation.',
      },
      {
        id: 'mobility',
        label: 'Transfer assistance observation',
        type: 'mobility',
        status: 'pending',
        dueAt: '13:50',
        detail: 'Observe transfer support needs and document changes.',
      },
      {
        id: 'documentation',
        label: 'Complete visit summary',
        type: 'documentation',
        status: 'pending',
        dueAt: '14:05',
        detail: 'Record nutrition, transfer support, and family communication needs.',
      },
    ];
  }

  if (kind === 'mobility') {
    return [
      {
        id: 'arrival',
        label: 'Arrive and confirm identity',
        type: 'arrival',
        status: 'pending',
        dueAt: '15:00',
        detail: 'Check communication preferences before personal-care support.',
      },
      {
        id: 'wellbeing',
        label: 'Orientation and comfort check',
        type: 'wellbeing',
        status: 'pending',
        dueAt: '15:10',
        detail: 'Confirm comfort, pain, and any confusion today.',
      },
      {
        id: 'mobility',
        label: 'Mobility and personal-care support',
        type: 'mobility',
        status: 'pending',
        dueAt: '15:20',
        detail: 'Observe steadiness and respect same-gender care preference where possible.',
      },
      {
        id: 'documentation',
        label: 'Complete visit summary',
        type: 'documentation',
        status: 'pending',
        dueAt: '15:40',
        detail: 'Record mobility, preferences, and any escalation.',
      },
    ];
  }

  return [
  {
    id: 'arrival',
    label: 'Arrive and confirm identity',
    type: 'arrival',
    status: 'pending',
    dueAt: '12:00',
    detail: 'Confirm address, introduce visit purpose, check preferred communication.',
  },
  {
    id: 'meal',
    label: 'Support lunch routine',
    type: 'meal',
    status: 'pending',
    dueAt: '12:10',
    detail: 'Offer rice-based meal option and check appetite.',
  },
  {
    id: 'medication',
    label: 'Assist lunchtime medication',
    type: 'medication',
    status: 'pending',
    dueAt: '12:20',
    detail: 'Confirm medication prompt and document if delayed or refused.',
  },
  {
    id: 'wellbeing',
    label: 'Wellbeing and comfort check',
    type: 'wellbeing',
    status: 'pending',
    dueAt: '12:30',
    detail: 'Ask about pain, dizziness, hydration, and unusual symptoms.',
  },
  {
    id: 'mobility',
    label: 'Observe mobility and falls risk',
    type: 'mobility',
    status: 'pending',
    dueAt: '12:35',
    detail: 'Check walker use and whether gait is steady today.',
  },
  {
    id: 'documentation',
    label: 'Complete visit summary',
    type: 'documentation',
    status: 'pending',
    dueAt: '12:45',
    detail: 'Record completed tasks, issues, escalation, and follow-up needs.',
  },
  ];
}

export const baselineAlerts: RiskAlert[] = [
  {
    id: 'cald-language',
    level: 'moderate',
    title: 'Interpreter support may be needed',
    message:
      'Use plain language, avoid idioms, and confirm understanding before discussing medication.',
    source: 'rules',
  },
  {
    id: 'falls-baseline',
    level: 'moderate',
    title: 'Falls risk flagged',
    message: 'Patient uses a walker. Observe steadiness before mobility support.',
    source: 'rules',
  },
];

function alertsForPatient(patient: PatientInfo): RiskAlert[] {
  const alerts: RiskAlert[] = [];
  if (patient.interpreterRequired) {
    alerts.push({
      id: 'cald-language',
      level: 'moderate',
      title: 'Interpreter support may be needed',
      message:
        'Use plain language, avoid idioms, and confirm understanding before discussing medication or care decisions.',
      source: 'rules',
    });
  }
  if (patient.careRiskFlags?.some((flag) => flag.toLowerCase().includes('fall')) || patient.mobilitySupport) {
    alerts.push({
      id: 'falls-baseline',
      level: 'moderate',
      title: 'Mobility or falls risk flagged',
      message: `${patient.name} mobility support: ${patient.mobilitySupport ?? 'not recorded'}. Observe steadiness before support.`,
      source: 'rules',
    });
  }
  if (alerts.length === 0) {
    alerts.push({
      id: 'routine-care',
      level: 'low',
      title: 'Routine visit',
      message: 'No high-priority risk flags are active at the start of this visit.',
      source: 'rules',
    });
  }
  return alerts;
}

export const demoScenarioSeeds: DemoScenarioSeed[] = [
  {
    patient: demoPatient,
    visit: {
      id: 'visit-home-1200',
      patientId: demoPatient.id,
      scheduledAt: '2026-05-12T12:00:00+08:00',
      location: 'Home visit - lunch and medication support',
      plannedAddress: 'Demo home address, Victoria Park WA',
      plannedCoords: { latitude: -31.9766, longitude: 115.9007 },
      locationThresholdMeters: 150,
      status: 'completed',
    },
    tasks: tasksForVisit('lunch').map((task) => ({ ...task, status: 'completed' })),
    alerts: alertsForPatient(demoPatient),
  },
  {
    patient: florPatient,
    visit: {
      id: 'visit-home-1330',
      patientId: florPatient.id,
      scheduledAt: '2026-05-12T13:30:00+08:00',
      location: 'Home visit - wellbeing and transfer support',
      plannedAddress: 'Demo home address, East Perth WA',
      plannedCoords: { latitude: -31.9583, longitude: 115.877 },
      locationThresholdMeters: 150,
      status: 'scheduled',
    },
    tasks: tasksForVisit('wellbeing'),
    alerts: alertsForPatient(florPatient),
  },
  {
    patient: tyeshaPatient,
    visit: {
      id: 'visit-home-1500',
      patientId: tyeshaPatient.id,
      scheduledAt: '2026-05-12T15:00:00+08:00',
      location: 'Home visit - mobility and personal-care support',
      plannedAddress: 'Demo home address, Cannington WA',
      plannedCoords: { latitude: -32.0155, longitude: 115.9369 },
      locationThresholdMeters: 150,
      status: 'scheduled',
    },
    tasks: tasksForVisit('mobility'),
    alerts: alertsForPatient(tyeshaPatient),
  },
];

export const incidentChecklistTemplate: IncidentChecklistItem[] = [
  { id: 'consciousness', label: 'Check consciousness and breathing', completed: false },
  { id: 'pain', label: 'Ask about pain, dizziness, and head impact', completed: false },
  { id: 'injury', label: 'Look for visible injury without moving the patient unnecessarily', completed: false },
  { id: 'supervisor', label: 'Contact supervisor or emergency support according to policy', completed: false },
  { id: 'document', label: 'Record incident note and schedule follow-up', completed: false },
];

export function createVisitQueue(activeIndex = 0, completedIds: string[] = []): VisitQueueItem[] {
  return demoScenarioSeeds.map((seed, index) => ({
    id: seed.visit.id,
    scheduledAt: seed.visit.scheduledAt,
    patientName: seed.patient.name,
    patientMeta: `${seed.patient.age} yrs · ${seed.patient.preferredLanguage ?? 'Language unknown'}`,
    purpose: seed.visit.location,
    status: completedIds.includes(seed.visit.id)
      ? 'completed'
      : index === activeIndex
        ? seed.visit.status
        : 'scheduled',
  }));
}

export function createDemoScenario(index = 0): ScenarioContext {
  const seed = demoScenarioSeeds[index] ?? demoScenarioSeeds[0];
  return {
    worker: demoWorker,
    patient: { ...seed.patient },
    visit: { ...seed.visit },
    lifecycleStep: seed.visit.status === 'completed' ? 'closed' : 'pre_visit',
    tasks: seed.tasks.map((task) => ({ ...task })),
    events: [],
    alerts: seed.alerts.map((alert) => ({ ...alert })),
    incidentChecklist: incidentChecklistTemplate.map((item) => ({ ...item })),
  };
}
