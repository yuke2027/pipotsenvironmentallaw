import { useAction, useApi } from './api';
import type { Page, Row, User } from './api';

/** Cross-cutting queries and actions used by the application shell. */
export const useCurrentUser = () => useApi<User>('/auth/me');
export const useShellDashboard = (enabled: boolean) => useApi<Row>('/dashboard', enabled);
export const useShellCities = (enabled: boolean) => useApi<Page>('/cities', enabled);
export const useShellNotifications = (enabled: boolean) => useApi<Page>('/notifications', enabled, true);
export const useShellJob = (identifier: string | undefined) =>
  useApi<Row>(identifier ? `/jobs/${identifier}` : '/jobs/invalid', Boolean(identifier), true);

export const useLogout = () => useAction<Record<string, never>>('/auth/logout');
export const useMarkNotificationRead = () =>
  useAction<{ id: string }>(body => `/notifications/${body.id}/read`);
export const useCancelShellJob = () =>
  useAction<{ id: string }>(body => `/jobs/${body.id}/cancel`);
