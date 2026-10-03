import { useAction, useApi } from '../../shared/api';

export const useAdminUsers = (path = '/admin/users') => useApi(path);
export const useAudits = (path = '/admin/audits') => useApi(path);
export const useAdminQuery = useApi;
export const useAdminAction = useAction;
export const useUpdateAdminUser = () => useAction<{ id: string; role: string; active: boolean }>(body => `/admin/users/${body.id}`, 'PATCH', ({ id, ...values }) => values);
export const useUpdateStation = () => useAction<{ id: string; values: Record<string, unknown> }>(body => `/admin/stations/${body.id}`, 'PUT', body => body.values);
export const useAddStationAlias = () => useAction<{ id: string; values: Record<string, unknown> }>(body => `/admin/stations/${body.id}/aliases`, 'POST', body => body.values);
export const useToggleChannel = () => useAction<{ id: string; enabled: boolean }>(body => `/admin/channels/${body.id}`, 'PATCH', ({ id, ...values }) => values);
