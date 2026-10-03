import React, { Suspense, lazy } from 'react';
import ReactDOM from 'react-dom/client';
import { createBrowserRouter, RouterProvider, Navigate, useRouteError } from 'react-router-dom';
import { App, ConfigProvider, Result, Button, Spin } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import dayjs from 'dayjs';
import 'dayjs/locale/zh-cn';
import { Shell } from './shared/layout';
import { Login } from './domains/auth/pages';
import { Dashboard, Monitoring, StationDetail, Evaluations, Forecasts } from './domains/monitoring/pages';
import { Leads, Inspections, InspectionDetail, Enterprises, EnterpriseDetail } from './domains/enforcement/pages';
import { Reports, Models } from './domains/operations/pages';
import { Administration } from './domains/admin/pages';
import './styles.css';

dayjs.locale('zh-cn');
const client = new QueryClient({ defaultOptions: { queries: { staleTime: 15000, refetchOnWindowFocus: false }, mutations: { retry: false } } });
const router = createBrowserRouter([
  { path: '/login', element: <Login /> }, { path: '/change-password', element: <Login changePassword /> },
  { path: '/', element: <Shell />, errorElement: <Result status="error" title="页面暂时无法显示" subTitle="请刷新页面重试。" extra={<Button onClick={() => location.reload()}>刷新</Button>} />, children: [
    { index: true, element: <Dashboard /> }, { path: 'monitoring', element: <Monitoring /> }, { path: 'stations/:id', element: <StationDetail /> },
    { path: 'evaluations', element: <Evaluations /> }, { path: 'forecasts', element: <Forecasts /> },
    { path: 'leads', element: <Leads /> }, { path: 'inspections', element: <Inspections /> }, { path: 'inspections/:id', element: <InspectionDetail /> },
    { path: 'enterprises', element: <Enterprises /> }, { path: 'enterprises/:id', element: <EnterpriseDetail /> },
    { path: 'models', element: <Models /> }, { path: 'reports', element: <Reports /> }, { path: 'admin', element: <Administration /> },
    { path: '*', element: <Result status="404" title="页面不存在" extra={<Button href="/">返回工作台</Button>} /> },
  ] },
]);

ReactDOM.createRoot(document.getElementById('root')!).render(<React.StrictMode><QueryClientProvider client={client}><ConfigProvider locale={zhCN} theme={{ token: { colorPrimary: '#087f8c', colorInfo: '#087f8c', colorSuccess: '#388469', colorWarning: '#bd861b', colorError: '#c75849', colorText: '#20343f', colorTextSecondary: '#71838e', colorBorder: '#dce5e9', colorBgLayout: '#f3f6f8', borderRadius: 8, fontSize: 14, controlHeight: 36, fontFamily: 'Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif' }, components: { Layout: { siderBg: '#102b37', headerBg: '#ffffff' }, Menu: { darkItemBg: '#102b37', darkItemSelectedBg: '#164953', darkItemSelectedColor: '#a9f1e6', darkItemColor: '#a8bfc8', itemHeight: 44 }, Table: { headerBg: '#f5f8fa', headerColor: '#637580', cellPaddingBlock: 15 }, Card: { headerFontSize: 15, headerHeight: 60, paddingLG: 22 }, Button: { primaryShadow: 'none' } } }}><App><RouterProvider router={router} /></App></ConfigProvider></QueryClientProvider></React.StrictMode>);
