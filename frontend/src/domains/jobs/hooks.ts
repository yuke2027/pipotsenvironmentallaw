import { useApi } from '../../shared/api';
import type { JobInput, Page } from '../../shared/api';
import { useAction } from '../../shared/api';
import { queryKeys } from '../../shared/queryKeys';

export function useJobs(path = '/jobs') {
  const query = useApi<Page>(path, true, true);
  return { ...query, domainQueryKey: queryKeys.jobs(path) };
}

export function useJob(identifier: string | undefined) {
  return useApi(identifier ? `/jobs/${identifier}` : '/jobs/invalid', Boolean(identifier), true);
}

export type { JobInput };

export function useCreateJob() {
  // The API supplies defaults for optional fields; keep the domain hook
  // ergonomic for forms that only collect the fields relevant to one job.
  return useAction<Record<string, unknown>>('/jobs');
}

export function useRetryJob() {
  return useAction<{ id: string }>(body => `/jobs/${body.id}/retry`);
}

export function useCancelJob() {
  return useAction<{ id: string }>(body => `/jobs/${body.id}/cancel`);
}
