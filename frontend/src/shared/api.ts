import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { App } from 'antd';
import type { components } from '../generated/api';
import { queryKeys } from './queryKeys';

export type User = components['schemas']['UserView'];
export type Station = components['schemas']['StationView'];
export type Observation = components['schemas']['ObservationView'];
export type Evaluation = components['schemas']['EvaluationView'];
export type Enterprise = components['schemas']['EnterpriseView'];
export type Inspection = components['schemas']['InspectionView'];
export type Lead = components['schemas']['LeadView'];
export type JobInput = components['schemas']['JobBody'];
export type Row = Record<string, any>;
export type Page<T = Row> = { items: T[]; total: number; page: number; page_size: number };
export class ApiError extends Error {
  constructor(message: string, public status: number, public requestId?: string) { super(message); }
}

export const queryString = (values: Record<string, unknown>) => {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(values)) if (value !== undefined && value !== null && value !== '') params.set(key, String(value));
  return params.toString();
};

export async function api<T = Row>(path: string, options: RequestInit = {}): Promise<T> {
  const csrf = document.cookie.split('; ').find(c => c.startsWith('esp_csrf='))?.slice(9);
  const headers = new Headers(options.headers);
  if (!(options.body instanceof FormData)) headers.set('Content-Type', 'application/json');
  if (csrf) headers.set('X-CSRF-Token', decodeURIComponent(csrf));
  const response = await fetch(`/api/v2${path}`, { ...options, credentials: 'same-origin', headers });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    const detail = payload.error?.details?.map((d: Row) => `${d.field}：${d.reason}`).join('；');
    throw new ApiError(detail || payload.error?.message || '请求失败，请稍后重试', response.status, payload.request_id);
  }
  return response.status === 204 ? undefined as T : response.json();
}

export function useApi<T = Row>(path: string, enabled = true, poll = false) {
  return useQuery<T, ApiError>({ queryKey: queryKeys.api(path), queryFn: () => api<T>(path), enabled,
    refetchInterval: poll ? 4000 : false, retry: (count, error) => error.status >= 500 && count < 1 });
}

export function useAction<T = Row>(path: string | ((body: T) => string), method = 'POST', mapBody: (body: T) => unknown = body => body) {
  const client = useQueryClient();
  const { message } = App.useApp();
  return useMutation({ mutationFn: (body: T) => {
    const payload = mapBody(body);
    return api(typeof path === 'function' ? path(body) : path, {
      method,
      ...(payload === undefined ? {} : { body: payload instanceof FormData ? payload : JSON.stringify(payload) }),
    });
  },
    onSuccess: () => { client.invalidateQueries({ queryKey: ['api'] }); },
    onError: (error: Error) => { message.error(error.message); } });
}

export const dateTime = (value?: string | null) => value ? new Intl.DateTimeFormat('zh-CN', {
  timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false,
}).format(new Date(value)) : '—';
export const number = (value: unknown, decimals = 1) => typeof value === 'number' && Number.isFinite(value) ? value.toLocaleString('zh-CN', { maximumFractionDigits: decimals }) : '—';
