import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ApiError } from './api';
import { QueryState, Status } from './components';

describe('business feedback states', () => {
  it('shows access denied separately and retries a failed request', () => {
    const refetch = vi.fn();
    render(<QueryState query={{ isPending: false, error: new ApiError('无权访问该任务', 403, 'trace-id'), refetch }}><div>private</div></QueryState>);
    expect(screen.getByText('没有访问权限')).toBeInTheDocument();
    expect(screen.queryByText('private')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /重试/ }));
    expect(refetch).toHaveBeenCalledOnce();
  });
  it('labels incomplete evaluation distinctly from compliance', () => {
    render(<Status value="insufficient" />);
    expect(screen.getByText('数据不足')).toBeInTheDocument();
    expect(screen.queryByText('未超限')).not.toBeInTheDocument();
  });
});
