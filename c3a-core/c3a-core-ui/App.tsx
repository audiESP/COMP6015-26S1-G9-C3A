import React, { useState } from 'react';
import { TrainingScreen } from './src/screens/TrainingScreen';
import { VisitScreen } from './src/screens/VisitScreen';

export default function App() {
  const [mode, setMode] = useState<'visits' | 'training'>('visits');

  if (mode === 'training') {
    return <TrainingScreen onClose={() => setMode('visits')} />;
  }

  return <VisitScreen onOpenTraining={() => setMode('training')} />;
}
