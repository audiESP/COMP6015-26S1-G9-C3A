import React from 'react';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import { CareScreen } from './src/screens/CareScreen';

export default function App() {
  return <SafeAreaProvider><StatusBar style="dark" /><CareScreen /></SafeAreaProvider>;
}
