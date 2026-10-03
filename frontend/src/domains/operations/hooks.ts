import { useAction, useApi } from '../../shared/api';

export const useOperationsQuery = useApi;
export const useOperationsAction = useAction;
export const useImportJob = () => useAction<FormData>('/imports');
export const useModelRollback = () => useAction<{ task: string }>(body => `/models/${body.task}/rollback`, 'POST', () => undefined);
export const useModelActivate = () => useAction<{ id: string }>(body => `/models/${body.id}/activate`, 'POST', () => undefined);
