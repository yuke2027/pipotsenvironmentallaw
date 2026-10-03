import { useAction, useApi } from '../../shared/api';
import type { Enterprise, Inspection, Lead, Page } from '../../shared/api';

export const useEnterprises = (path = '/enterprises') => useApi<Page<Enterprise>>(path);
export const useLeads = (path = '/leads') => useApi<Page<Lead>>(path);
export const useInspections = (path = '/inspections') => useApi<Page<Inspection>>(path);
export const useEnforcementQuery = useApi;
export const useEnforcementAction = useAction;
export const useAssignLead = () => useAction<{ id: string; [key: string]: unknown }>(body => `/leads/${body.id}/assign`, 'POST', ({ id, ...values }) => values);
export const useRejectLead = () => useAction<{ id: string; reason?: string }>(body => `/leads/${body.id}/reject`, 'POST', ({ id, ...values }) => values);
export const useClaimLead = () => useAction<{ id: string }>(body => `/leads/${body.id}/claim`, 'POST', () => undefined);
export const useUploadAttachment = () => useAction<FormData>('/attachments');
export const useUpdateRectification = () => useAction<{ id: string; rectification_id: string; [key: string]: unknown }>(body => `/inspections/${body.id}/rectifications/${body.rectification_id}`, 'PUT', ({ id, rectification_id, ...values }) => values);
export const useImportEnterprises = () => useAction<FormData>('/imports');
