import { useEffect, useMemo, useRef } from 'react';
import type { ReactNode } from 'react';
import { Alert, Button, Card, Empty, Skeleton, Tag } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import * as echarts from 'echarts/core';
import { LineChart, BarChart } from 'echarts/charts';
import { GridComponent, TooltipComponent, LegendComponent, DataZoomComponent, AriaComponent, MarkLineComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import type { EChartsCoreOption } from 'echarts/core';
import type { ApiError } from './api';

echarts.use([LineChart, BarChart, GridComponent, TooltipComponent, LegendComponent, DataZoomComponent, AriaComponent, MarkLineComponent, CanvasRenderer]);
export const colors = ['#087f8c', '#4169bf', '#9b70b5', '#b47e28', '#648c49'];
export const labels: Record<string, string> = {
  pending: '待研判', assigned: '待核查', inspection: '现场核查', rectification: '整改跟踪', reinspection: '复查', review: '主管审核', archived: '已归档', rejected: '已驳回', closed: '已闭环',
  queued: '排队中', running: '执行中', succeeded: '已完成', failed: '失败', partial: '部分成功', cancelled: '已取消',
  within: '未超限', exceeded: '超过限值', insufficient: '数据不足', validated: '验证通过', experimental: '实验状态',
  normal: '普通', high: '较高', urgent: '紧急', valid: '有效', missing: '缺失', invalid: '无效', responded: '已反馈', verified: '复查通过',
  collect: '在线采集', import: '文件导入', evaluate: '标准评价', train: '模型训练', forecast: '趋势预测', impute: '数据插补', export: '报告导出',
};
export function Status({ value }: { value: string }) {
  const color = ['failed', 'exceeded', 'urgent'].includes(value) ? 'error' : ['partial', 'cancelled', 'insufficient', 'rectification', 'high'].includes(value) ? 'warning' : ['succeeded', 'within', 'archived', 'validated', 'verified'].includes(value) ? 'success' : ['running', 'inspection', 'review', 'reinspection'].includes(value) ? 'processing' : 'default';
  return <Tag color={color}>{labels[value] || value}</Tag>;
}
export function Heading({ title, eyebrow, description, extra }: { title: string; eyebrow?: string; description?: ReactNode; extra?: ReactNode }) {
  return <div className="page-heading"><div>{eyebrow && <div className="eyebrow">{eyebrow}</div>}<h1>{title}</h1>{description && <p>{description}</p>}</div><div className="heading-actions">{extra}</div></div>;
}
export function QueryState({ query, children, empty }: { query: { isPending: boolean; error: ApiError | null; refetch: () => unknown }; children: ReactNode; empty?: boolean }) {
  if (query.isPending) return <Card><Skeleton active paragraph={{ rows: 5 }} /></Card>;
  if (query.error) return <Alert type={query.error.status === 403 ? 'warning' : 'error'} showIcon message={query.error.status === 403 ? '没有访问权限' : '数据暂时无法加载'} description={<>{query.error.message}{query.error.requestId && <small className="block">请求编号：{query.error.requestId}</small>}</>} action={<Button icon={<ReloadOutlined />} onClick={() => query.refetch()}>重试</Button>} />;
  if (empty) return <Card><Empty description="当前条件下没有记录，可调整筛选条件或创建任务" /></Card>;
  return <>{children}</>;
}
export function Chart({ option, summary, onPoint, height = 320 }: { option: EChartsCoreOption; summary: string; onPoint?: (data: any) => void; height?: number }) {
  const ref = useRef<HTMLDivElement>(null);
  const callback = useRef(onPoint);
  callback.current = onPoint;
  useEffect(() => {
    if (!ref.current) return;
    const chart = echarts.init(ref.current);
    chart.on('click', p => callback.current?.(p));
    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(ref.current);
    return () => { observer.disconnect(); chart.dispose(); };
  }, []);
  useEffect(() => {
    if (ref.current) echarts.getInstanceByDom(ref.current)?.setOption({
      color: colors, animation: false, aria: { enabled: true }, textStyle: { fontFamily: 'Inter, Microsoft YaHei, sans-serif', color: '#667b87' },
      grid: { left: 50, right: 24, top: 48, bottom: 55 }, tooltip: { trigger: 'axis', confine: true },
      legend: { top: 0, right: 10, icon: 'roundRect' }, ...option,
    }, true);
  }, [option]);
  return <figure className="chart-figure"><div ref={ref} role="img" aria-label={summary} style={{ height }} tabIndex={0} /><figcaption>{summary}</figcaption></figure>;
}
export function useUnsaved(dirty: boolean) {
  useEffect(() => {
    if (!dirty) return;
    const beforeUnload = (event: BeforeUnloadEvent) => { event.preventDefault(); };
    window.addEventListener('beforeunload', beforeUnload);
    return () => window.removeEventListener('beforeunload', beforeUnload);
  }, [dirty]);
}
