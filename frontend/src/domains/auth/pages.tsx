import { useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Alert, Button, Form, Input } from 'antd';
import { ArrowRightOutlined, CloudOutlined, LockOutlined, SafetyCertificateOutlined, UserOutlined } from '@ant-design/icons';
import { useQueryClient } from '@tanstack/react-query';
import type { components } from '../../generated/api';
import { useAuthAction } from './hooks';

export function Login({ changePassword = false }: { changePassword?: boolean }) {
  const action = useAuthAction<Record<string, string>>(changePassword ? '/auth/change-password' : '/auth/login');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const client = useQueryClient();
  async function submit(values: components['schemas']['LoginBody'] | components['schemas']['PasswordBody']) {
    setError(''); setBusy(true);
    try {
      const result = await action.mutateAsync(values);
      client.clear();
      navigate(changePassword ? '/login' : result.user.must_change_password ? '/change-password' : location.state?.from || '/', { replace: true });
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  return <main className="login-page"><section className="login-brand-panel"><div className="login-brand"><CloudOutlined /><strong>清境</strong><span>ENVIRONMENTAL WORKSPACE</span></div><div className="login-message"><span className="eyebrow">观测有据 · 核查有序</span><h1>连接环境数据<br />与每一次行动。</h1><p>从空气质量监测到现场核查与整改复查，<br />让监管协作清晰、有序、可追溯。</p><div className="login-features"><span>真实观测</span><i /><span>科学研判</span><i /><span>闭环协作</span></div></div><div className="login-landscape"><div /><div /><div /><div /></div><small className="login-brand-footer">环境监测与执法辅助平台 / 北京工作空间</small></section><section className="login-form-panel"><div className="login-form"><span className="eyebrow">{changePassword ? 'ACCOUNT SECURITY' : 'WELCOME TO WORKSPACE'}</span><h2>{changePassword ? '设置新的登录密码' : '登录工作台'}</h2><p className="muted">{changePassword ? '首次登录须修改密码。更新后请重新登录。' : '使用组织分配的账号访问您的工作空间。'}</p>{error && <Alert type="error" showIcon message={error} className="mb16" />}<Form layout="vertical" requiredMark={false} onFinish={submit} size="large">{changePassword ? <><Form.Item label="当前密码" name="current_password" rules={[{ required: true }]}><Input.Password prefix={<LockOutlined />} autoComplete="current-password" /></Form.Item><Form.Item label="新密码" name="new_password" rules={[{ required: true, min: 12, message: '密码至少 12 个字符' }]}><Input.Password prefix={<LockOutlined />} autoComplete="new-password" /></Form.Item></> : <><Form.Item label="账号" name="username" rules={[{ required: true, message: '请输入账号' }]}><Input prefix={<UserOutlined />} placeholder="请输入您的账号" autoComplete="username" autoFocus /></Form.Item><Form.Item label="密码" name="password" rules={[{ required: true, message: '请输入密码' }]}><Input.Password prefix={<LockOutlined />} placeholder="请输入密码" autoComplete="current-password" /></Form.Item></>}<Button type="primary" htmlType="submit" block loading={busy}>{changePassword ? '更新密码' : '进入工作台'} <ArrowRightOutlined /></Button></Form><div className="login-security"><SafetyCertificateOutlined /><span>会话受保护 · 按角色与任务授权访问</span></div><p className="login-help">{changePassword ? '修改密码后，此前的登录会话将失效。' : '尚未获得账号？请联系组织管理员。'}</p></div><footer>清境 Environmental Workspace · 2.0</footer></section></main>;
}
