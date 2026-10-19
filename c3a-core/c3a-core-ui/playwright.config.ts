import { defineConfig, devices } from '@playwright/test';

// Automated end-to-end coverage for the 7 usability-test tasks (see
// ../USABILITY_TEST_MODERATOR_GUIDE.md). This exercises the app's own UI
// logic end to end — it is NOT a substitute for the human-moderated
// usability session: it cannot tell you whether a task was confusing, only
// whether the click-path still works. Run both.
//
// Prerequisites (not started by this config):
//   - c3a-core-api on :8000, c3a-core-ai on :8001, Ollama on :11434
//   - Demo data reset: rerun c3a-core-api/migrations/002_seed_demo_operational_data.sql
//     (the suite mutates the seeded visit the same way a real session would)
//
// Run: npx playwright test
export default defineConfig({
  testDir: './e2e',
  timeout: 90_000,
  expect: { timeout: 20_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL: 'http://127.0.0.1:8090',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    viewport: { width: 420, height: 900 },
    geolocation: { latitude: -31.9524, longitude: 115.8613 },
    permissions: ['geolocation'],
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    command: 'npx expo start --web --port 8090',
    url: 'http://127.0.0.1:8090',
    reuseExistingServer: true,
    timeout: 60_000,
  },
});
