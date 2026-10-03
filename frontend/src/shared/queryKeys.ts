export const queryKeys = {
  all: ['api'] as const,
  resource: (path: string) => ['api', path] as const,
  api: (path: string) => ['api', path] as const,
  jobs: (path = '') => ['jobs', path] as const,
  monitoring: (path = '') => ['monitoring', path] as const,
  enforcement: (path = '') => ['enforcement', path] as const,
  admin: (path = '') => ['admin', path] as const,
};
