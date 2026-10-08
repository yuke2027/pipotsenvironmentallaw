import React from 'react';
import ReactDOM from 'react-dom/client';
import { createHashRouter, RouterProvider } from 'react-router-dom';
import { App, ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import dayjs from 'dayjs';
import 'dayjs/locale/zh-cn';
import 'antd/dist/reset.css';
import './prototype.css';
import { antdTheme } from './tokens';
import { Placeholder, ProtoProvider, Shell } from './shell';
import { Dashboard } from './pages/dashboard';
import { Monitoring, StationDetail } from './pages/monitoring';
import { InspectionDetail, InspectionList } from './pages/inspection';
import { Screen } from './pages/screen';

dayjs.locale('zh-cn');

const router = createHashRouter([
  { path: '/screen', element: <Screen /> },
  {
    path: '/', element: <Shell />, children: [
      { index: true, element: <Dashboard /> },
      { path: 'monitoring', element: <Monitoring /> },
      { path: 'stations/:id', element: <StationDetail /> },
      { path: 'inspections', element: <InspectionList /> },
      { path: 'inspections/:id', element: <InspectionDetail /> },
      { path: '*', element: <Placeholder /> },
    ],
  },
]);

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ConfigProvider locale={zhCN} theme={antdTheme}>
      <App>
        <ProtoProvider><RouterProvider router={router} /></ProtoProvider>
      </App>
    </ConfigProvider>
  </React.StrictMode>,
);
