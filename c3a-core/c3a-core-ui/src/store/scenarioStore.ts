import { useCallback, useMemo, useState } from 'react';
import {
  CareTask,
  CareTaskStatus,
  IncidentChecklistItem,
  PatientInfo,
  RiskAlert,
  ScenarioContext,
  ScenarioEvent,
  VisitLifecycleStep,
  VisitQueueItem,
  VisitStatus,
} from '../types';
import {
  baselineAlerts,
  createDemoScenario,
  createVisitQueue,
  demoScenarioSeeds,
  incidentChecklistTemplate,
} from '../data/demoScenario';

function timestamp() {
  return new Date().toISOString();
}

function eventId(type: ScenarioEvent['type']) {
  return `${type}-${Date.now()}`;
}

function setTaskStatus(tasks: CareTask[], id: string, status: CareTaskStatus) {
  return tasks.map((task) => (task.id === id ? { ...task, status } : task));
}

function upsertAlert(alerts: RiskAlert[], alert: RiskAlert) {
  const exists = alerts.some((item) => item.id === alert.id);
  if (exists) {
    return alerts.map((item) => (item.id === alert.id ? alert : item));
  }
  return [alert, ...alerts];
}

function lifecycleForEvent(type: ScenarioEvent['type']): VisitLifecycleStep {
  switch (type) {
    case 'arrived':
      return 'arrival';
    case 'care_started':
    case 'medication_given':
      return 'care_tasks';
    case 'running_late':
      return 'pre_visit';
    case 'medication_delayed':
    case 'patient_unsteady':
    case 'fall_found':
    case 'escalation_triggered':
      return 'incident_active';
    case 'follow_up_required':
    case 'review_started':
      return 'review';
    case 'visit_completed':
      return 'closed';
    default:
      return 'care_tasks';
  }
}

function statusForEvent(type: ScenarioEvent['type']): VisitStatus {
  switch (type) {
    case 'arrived':
      return 'arrived';
    case 'care_started':
      return 'in_progress';
    case 'running_late':
    case 'medication_delayed':
      return 'delayed';
    case 'patient_unsteady':
    case 'fall_found':
    case 'escalation_triggered':
      return 'incident';
    case 'follow_up_required':
      return 'follow_up_required';
    case 'review_started':
      return 'review_required';
    case 'visit_completed':
      return 'completed';
    case 'medication_given':
      return 'in_progress';
    default:
      return 'in_progress';
  }
}

function alertsForEvent(type: ScenarioEvent['type']): RiskAlert[] {
  switch (type) {
    case 'running_late':
      return [
        {
          id: 'delay-risk',
          level: 'moderate',
          title: 'Visit is running late',
          message:
            'Medication and meal support may be affected. Record the delay reason and check whether escalation is needed.',
          source: 'rules',
        },
      ];
    case 'medication_delayed':
      return [
        {
          id: 'medication-delay',
          level: 'high',
          title: 'Medication timing issue',
          message:
            'Document the delay, avoid doubling doses, and seek nurse or supervisor advice if outside the safe administration window.',
          source: 'rules',
        },
      ];
    case 'patient_unsteady':
      return [
        {
          id: 'unsteady-risk',
          level: 'high',
          title: 'Patient appears unsteady',
          message:
            'Pause routine tasks, complete mobility observations, and consider a later follow-up or escalation.',
          source: 'rules',
        },
      ];
    case 'fall_found':
      return [
        {
          id: 'fall-incident',
          level: 'high',
          title: 'Incident mode: patient found on floor',
          message:
            'Check responsiveness, pain, visible injury, and head impact. Do not move the patient if injury is suspected; escalate immediately.',
          source: 'rules',
        },
      ];
    case 'follow_up_required':
      return [
        {
          id: 'follow-up',
          level: 'moderate',
          title: 'Follow-up required',
          message:
            'Schedule a later check and include the reason in the visit summary.',
          source: 'rules',
        },
      ];
    default:
      return [];
  }
}

function updateTasksForEvent(tasks: CareTask[], type: ScenarioEvent['type']): CareTask[] {
  switch (type) {
    case 'arrived':
      return setTaskStatus(tasks, 'arrival', 'completed');
    case 'running_late':
      return setTaskStatus(tasks, 'arrival', 'delayed');
    case 'medication_given':
      return setTaskStatus(tasks, 'medication', 'completed');
    case 'medication_delayed':
      return setTaskStatus(tasks, 'medication', 'delayed');
    case 'patient_unsteady':
      return setTaskStatus(tasks, 'mobility', 'issue');
    case 'fall_found':
      return tasks.map((task) =>
        task.id === 'mobility' || task.id === 'wellbeing'
          ? { ...task, status: 'issue' as CareTaskStatus }
          : task,
      );
    case 'follow_up_required':
      return tasks.map((task) =>
        task.id === 'documentation'
          ? {
              ...task,
              label: 'Complete visit summary and follow-up note',
              status: task.status === 'completed' ? 'completed' : 'pending',
            }
          : task,
      );
    case 'review_started':
      return setTaskStatus(tasks, 'documentation', 'pending');
    case 'visit_completed':
      return tasks.map((task) => ({
        ...task,
        status: task.status === 'pending' ? ('completed' as CareTaskStatus) : task.status,
      }));
    default:
      return tasks;
  }
}

function createEvent(type: ScenarioEvent['type'], note?: string): ScenarioEvent {
  return {
    id: eventId(type),
    type,
    timestamp: timestamp(),
    note,
  };
}

function completedVisitIdsFromQueue(queue: VisitQueueItem[]) {
  return queue.filter((item) => item.status === 'completed').map((item) => item.id);
}

export function useScenarioStore() {
  const [activeVisitIndex, setActiveVisitIndex] = useState(0);
  const [scenario, setScenario] = useState<ScenarioContext>(() => createDemoScenario(0));
  const [visitQueue, setVisitQueue] = useState<VisitQueueItem[]>(() => createVisitQueue(0));

  const refreshQueue = useCallback((nextScenario: ScenarioContext, index = activeVisitIndex) => {
    setVisitQueue((currentQueue) => {
      const completedIds = completedVisitIdsFromQueue(currentQueue);
      const queue = createVisitQueue(index, completedIds);
      return queue.map((item) =>
        item.id === nextScenario.visit.id
          ? { ...item, status: nextScenario.visit.status }
          : item,
      );
    });
  }, [activeVisitIndex]);

  const recordEvent = useCallback((type: ScenarioEvent['type'], note?: string) => {
    setScenario((current) => {
      const event = createEvent(type, note);
      const eventAlerts = alertsForEvent(type);
      const nextAlerts = eventAlerts.reduce(upsertAlert, current.alerts);
      const arrivedAt =
        type === 'arrived' && !current.visit.arrivedAt
          ? event.timestamp
          : current.visit.arrivedAt;
      const nextScenario: ScenarioContext = {
        ...current,
        lifecycleStep: lifecycleForEvent(type),
        visit: {
          ...current.visit,
          status: statusForEvent(type),
          arrivedAt,
        },
        tasks: updateTasksForEvent(current.tasks, type),
        events: [event, ...current.events],
        alerts: nextAlerts,
      };
      refreshQueue(nextScenario);
      return nextScenario;
    });
  }, [refreshQueue]);

  const startCare = useCallback(() => {
    recordEvent('care_started');
  }, [recordEvent]);

  const startReview = useCallback(() => {
    recordEvent('review_started');
  }, [recordEvent]);

  const closeVisit = useCallback(() => {
    recordEvent('visit_completed');
  }, [recordEvent]);

  const startVisit = useCallback(() => {
    setScenario((current) => {
      if (
        current.lifecycleStep !== 'pre_visit' &&
        current.lifecycleStep !== 'arrival' &&
        current.visit.status !== 'scheduled' &&
        current.visit.status !== 'arrived'
      ) {
        return current;
      }
      const arrivedEvent = current.visit.arrivedAt ? null : createEvent('arrived');
      const careStartedEvent = createEvent('care_started');
      const nextScenario: ScenarioContext = {
        ...current,
        lifecycleStep: 'care_tasks',
        visit: {
          ...current.visit,
          status: 'in_progress',
          arrivedAt: current.visit.arrivedAt ?? arrivedEvent?.timestamp,
        },
        tasks: updateTasksForEvent(current.tasks, 'arrived'),
        events: arrivedEvent
          ? [careStartedEvent, arrivedEvent, ...current.events]
          : [careStartedEvent, ...current.events],
      };
      refreshQueue(nextScenario);
      return nextScenario;
    });
  }, [refreshQueue]);

  const completeCurrentTask = useCallback(() => {
    setScenario((current) => {
      const task =
        current.tasks.find((item) => item.status === 'pending') ??
        current.tasks.find((item) => ['issue', 'delayed'].includes(item.status)) ??
        current.tasks.find((item) => item.status !== 'completed');
      if (!task) return current;

      const event = task.type === 'medication' ? createEvent('medication_given') : null;
      const nextScenario: ScenarioContext = {
        ...current,
        lifecycleStep:
          current.lifecycleStep === 'pre_visit' || current.lifecycleStep === 'arrival'
            ? 'care_tasks'
            : current.lifecycleStep,
        visit: {
          ...current.visit,
          status:
            current.visit.status === 'scheduled' || current.visit.status === 'arrived'
              ? 'in_progress'
              : current.visit.status,
        },
        tasks:
          task.type === 'medication'
            ? updateTasksForEvent(current.tasks, 'medication_given')
            : setTaskStatus(current.tasks, task.id, 'completed'),
        events: event ? [event, ...current.events] : current.events,
      };
      refreshQueue(nextScenario);
      return nextScenario;
    });
  }, [refreshQueue]);

  const reportTaskIssue = useCallback((taskId: string, type: 'cannot_complete' | 'patient_declined' | 'safety_concern') => {
    setScenario((current) => {
      const task = current.tasks.find((item) => item.id === taskId);
      if (!task) return current;

      const eventType: ScenarioEvent['type'] =
        type === 'safety_concern'
          ? 'patient_unsteady'
          : task.type === 'medication'
            ? 'medication_delayed'
            : 'follow_up_required';
      const note =
        type === 'patient_declined'
          ? `${task.label}: patient declined`
          : type === 'safety_concern'
            ? `${task.label}: safety concern`
            : `${task.label}: could not complete`;
      const event = createEvent(eventType, note);
      const eventAlerts = alertsForEvent(eventType);
      const nextAlerts = eventAlerts.reduce(upsertAlert, current.alerts);
      const nextScenario: ScenarioContext = {
        ...current,
        lifecycleStep: eventType === 'patient_unsteady' ? 'incident_active' : 'review',
        visit: {
          ...current.visit,
          status: statusForEvent(eventType),
        },
        tasks: setTaskStatus(current.tasks, taskId, type === 'patient_declined' ? 'skipped' : 'issue'),
        events: [event, ...current.events],
        alerts: nextAlerts,
      };
      refreshQueue(nextScenario);
      return nextScenario;
    });
  }, [refreshQueue]);

  const completeVisit = useCallback(() => {
    setScenario((current) => {
      if (current.visit.status === 'completed' || current.lifecycleStep === 'closed') {
        return current;
      }
      const event = createEvent('visit_completed');
      const nextScenario: ScenarioContext = {
        ...current,
        lifecycleStep: 'closed',
        visit: {
          ...current.visit,
          status: 'completed',
        },
        tasks: current.tasks.map((task) =>
          task.status === 'pending'
            ? { ...task, status: 'skipped' as CareTaskStatus }
            : task,
        ),
        events: [event, ...current.events],
      };
      refreshQueue(nextScenario);
      return nextScenario;
    });
  }, [refreshQueue]);

  const updateTask = useCallback((id: string, status: CareTaskStatus) => {
    setScenario((current) => {
      const nextScenario: ScenarioContext = {
        ...current,
        tasks: setTaskStatus(current.tasks, id, status),
        lifecycleStep:
          current.lifecycleStep === 'pre_visit' || current.lifecycleStep === 'arrival'
            ? 'care_tasks'
            : current.lifecycleStep,
        visit: {
          ...current.visit,
          status:
            current.visit.status === 'scheduled' || current.visit.status === 'arrived'
              ? 'in_progress'
              : current.visit.status,
        },
      };
      refreshQueue(nextScenario);
      return nextScenario;
    });
  }, [refreshQueue]);

  const toggleIncidentCheck = useCallback((id: string) => {
    setScenario((current) => {
      const nextChecklist = current.incidentChecklist.map((item) =>
        item.id === id ? { ...item, completed: !item.completed } : item,
      );
      const event = createEvent('incident_check_completed', id);
      return {
        ...current,
        incidentChecklist: nextChecklist,
        events: [event, ...current.events],
      };
    });
  }, []);

  const resetScenario = useCallback(() => {
    const nextScenario = createDemoScenario(activeVisitIndex);
    setScenario(nextScenario);
    refreshQueue(nextScenario);
  }, [activeVisitIndex, refreshQueue]);

  const updatePatient = useCallback((patient: PatientInfo) => {
    setScenario((current) => {
      const nextScenario = {
        ...current,
        patient,
        visit: {
          ...current.visit,
          patientId: patient.id,
        },
      };
      refreshQueue(nextScenario);
      return nextScenario;
    });
  }, [refreshQueue]);

  const selectVisit = useCallback((visitId: string) => {
    const index = demoScenarioSeeds.findIndex((seed) => seed.visit.id === visitId);
    if (index < 0) return;
    const nextScenario = createDemoScenario(index);
    setActiveVisitIndex(index);
    setScenario(nextScenario);
    setVisitQueue((currentQueue) => {
      const completedIds = completedVisitIdsFromQueue(currentQueue);
      return createVisitQueue(index, completedIds);
    });
  }, []);

  const goToNextVisit = useCallback(() => {
    const nextIndex = Math.min(activeVisitIndex + 1, demoScenarioSeeds.length - 1);
    const nextScenario = createDemoScenario(nextIndex);
    setActiveVisitIndex(nextIndex);
    setScenario(nextScenario);
    setVisitQueue((currentQueue) => {
      const completedIds = Array.from(new Set([...completedVisitIdsFromQueue(currentQueue), scenario.visit.id]));
      return createVisitQueue(nextIndex, completedIds);
    });
  }, [activeVisitIndex, scenario.visit.id]);

  const activeAlerts = useMemo(() => {
    const severity = { high: 0, moderate: 1, low: 2 };
    return [...scenario.alerts].sort((a, b) => severity[a.level] - severity[b.level]);
  }, [scenario.alerts]);

  const restoreBaselineAlerts = useCallback(() => {
    setScenario((current) => ({
      ...current,
      alerts: baselineAlerts.map((alert) => ({ ...alert })),
    }));
  }, []);

  const incidentChecklistComplete = scenario.incidentChecklist.every((item: IncidentChecklistItem) => item.completed);
  const isLastVisit = activeVisitIndex >= demoScenarioSeeds.length - 1;

  return {
    scenario,
    activeAlerts,
    visitQueue,
    activeVisitIndex,
    isLastVisit,
    incidentChecklistComplete,
    recordEvent,
    startCare,
    startReview,
    closeVisit,
    startVisit,
    completeCurrentTask,
    reportTaskIssue,
    completeVisit,
    updateTask,
    toggleIncidentCheck,
    updatePatient,
    selectVisit,
    goToNextVisit,
    resetScenario,
    restoreBaselineAlerts,
  };
}
