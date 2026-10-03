import { createContext, useContext } from 'react';
import type { User } from './api';

export type Workbench = { user: User; start: string; end: string; city: string; params: URLSearchParams; setFilter: (values: Record<string, string | undefined>) => void; link: (path: string) => string; openJob: (id: string) => void };
export const WorkbenchContext = createContext<Workbench>(null!);
export const useWorkbench = () => useContext(WorkbenchContext);
