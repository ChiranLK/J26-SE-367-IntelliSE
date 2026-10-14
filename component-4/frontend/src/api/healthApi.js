import apiClient from './client';

export async function checkBackendHealth() {
  const startTime = performance.now();
  const response = await apiClient.get('/health');
  const latencyMs = Math.round(performance.now() - startTime);
  return {
    ...response.data,
    latencyMs,
  };
}
