import { useAction, useApi } from '../../shared/api';
import type { Evaluation, Observation, Page, Station } from '../../shared/api';

export function useStations(path = '/stations') {
  return useApi<Page<Station>>(path);
}

export function useObservations(path: string) {
  return useApi<Page<Observation>>(path);
}

export function useEvaluations(path: string) {
  return useApi<Page<Evaluation>>(path);
}

export const useMonitoringQuery = useApi;
export const useMonitoringAction = useAction;
