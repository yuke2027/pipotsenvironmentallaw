"""Generate appendix.md (技术附录册) from runtime OpenAPI + DB schema + router auth scan.

Inputs (already captured in this directory):
  - openapi.json   : GET /api/v2/openapi.json from a running API
  - schema.txt     : psql information_schema dump (table|column|type|nullable|len|default)

Usage:  python gen_appendix.py
Output: appendix.md  (plus prints a summary)
"""
from __future__ import annotations

import json
import re
from pathlib import Path

HERE = Path(__file__).parent
APP = HERE.parent.parent / "app" / "v2"

ROLE_GROUPS = {
    "MANAGERS": "管理员、监管主管",
    "REGULATORS": "管理员、监管主管、执法人员",
}

TABLE_INFO = {
    "v2_cities": ("监测", "城市目录", "纳入观测口径的城市"),
    "v2_stations": ("监测", "站点目录", "监测站点档案：编码、名称、坐标、启停；坐标为参考数据"),
    "v2_station_aliases": ("监测", "站点别名", "来源文件中的站名与目录映射，带有效期"),
    "v2_source_files": ("采集", "来源文件", "每次采集的原始文件登记，SHA-256 指纹与修订链"),
    "v2_source_attempts": ("采集", "采集尝试记录", "每次获取尝试的结果与说明（含失败留痕）"),
    "v2_observations": ("监测", "原始观测", "小时值/滚动均值，UTC 存储，绑定来源文件"),
    "v2_derived_values": ("监测", "派生值", "插补与预测结果，独立存储不覆盖原始证据"),
    "v2_evaluations": ("评价", "标准评价", "站点×日×污染物评价：浓度、限值快照、超标倍数、完整性"),
    "v2_aqi_results": ("评价", "AQI 结果", "站点日 AQI 与六项分指数、完整性标记"),
    "v2_standards": ("参考", "环境质量标准", "标准版本、限值、口径、有效期、原文链接"),
    "v2_laws": ("参考", "法规依据", "法规版本与有效期，核查适用依据来源"),
    "v2_leads": ("执法", "线索", "待研判线索：来源、优先级、认领/分派/驳回"),
    "v2_inspections": ("执法", "核查任务", "状态机载体；facts、legal_references、version 乐观锁"),
    "v2_rectifications": ("执法", "整改事项", "整改要求、期限、反馈、复查结论"),
    "v2_attachments": ("执法", "证据附件", "内容寻址文件引用，SHA-256 与版本链"),
    "v2_workflow_events": ("执法", "流转留痕", "每次状态流转的动作、说明、操作人"),
    "v2_enterprises": ("执法", "企业档案", "企业身份、信用代码、行业、地址"),
    "v2_enterprise_records": ("执法", "企业资料", "排放口/许可证专项资料"),
    "v2_users": ("账号", "用户", "账号、角色、口令散列、锁定与强制改密"),
    "v2_sessions": ("账号", "会话", "服务端会话，可整批吊销"),
    "v2_audits": ("账号", "操作审计", "不可变审计流水：操作、对象、请求编号、明细"),
    "v2_jobs": ("任务", "异步任务", "任务登记、状态、进度、结果与产物引用"),
    "v2_outbox": ("任务", "事务发件箱", "与业务写入同一事务的任务派发消息"),
    "v2_models": ("模型", "模型制品", "算法、指标、特征、环境指纹、权重与重载校验"),
    "v2_model_activations": ("模型", "模型激活", "各任务当前使用版本与回滚指针"),
    "v2_notifications": ("通知", "站内通知", "分派/退回等事件通知"),
    "v2_channels": ("通知", "通知通道", "Webhook/邮件外部通道配置与启停"),
    "v2_deliveries": ("通知", "发送记录", "外部通道投递状态与尝试次数"),
}

COL_DESC = {
    "id": "主键（UUID）", "created_at": "创建时间", "updated_at": "更新时间",
    "is_current": "是否当前有效版本", "sha256": "SHA-256 指纹", "version": "版本号/乐观并发控制",
    "local_date": "北京自然日", "observed_at": "观测时刻（UTC 存储）", "status": "状态",
    "role": "角色：管理员/监管主管/执法人员/研究者", "active": "启用状态",
    "must_change_password": "首次登录强制改密标记", "failed_logins": "连续失败次数",
    "locked_until": "锁定截止时间", "password_hash": "Argon2 口令散列",
    "display_name": "姓名", "username": "登录名",
    "station_id": "站点编号", "pollutant": "污染物", "value": "浓度/数值",
    "limit_value": "标准限值", "unit": "计量单位", "basis": "统计口径",
    "effective_from": "生效日期", "effective_to": "截至日期", "source_url": "原文链接",
    "snapshot_hash": "输入快照哈希", "complete": "数据完整性是否满足",
    "title": "标题", "description": "描述", "priority": "优先级",
    "assignee_id": "负责人", "due_date": "期限", "facts": "核查事实",
    "legal_references": "适用依据清单（法规+条款+理由）", "reason": "理由",
    "requirement": "整改要求", "response": "整改反馈", "review_note": "复查结论",
    "verified": "复查已核实", "kind": "类型/任务类型", "progress": "进度百分比",
    "attempts": "执行次数", "error": "失败原因", "result": "执行结果",
    "parameters": "任务参数", "owner_id": "发起人/属主", "job_id": "任务编号",
    "credit_code": "统一社会信用代码", "industry": "行业", "address": "地址",
    "contact": "联系方式", "latitude": "纬度", "longitude": "经度",
    "code": "编码/标准编号", "name": "名称", "grade": "适用等级",
    "min_points": "最低有效统计数", "region": "适用地区", "summary": "摘要",
    "external_name": "来源文件中的名称", "valid_from": "适用起始日", "valid_to": "适用截至日",
    "read_at": "已读时间", "enabled": "启用标记", "config": "通道配置",
    "credential_ref": "凭据环境变量名（ESP_NOTIFY_*）", "notification_id": "通知编号",
    "artifact_key": "产物存储键", "algorithm": "算法", "metrics": "评估指标",
    "evaluation_id": "关联评价记录", "enterprise_id": "关联企业", "claimed_by": "认领人",
    "replaces_id": "替换的原附件", "inspection_id": "所属核查任务",
    "user_id": "所属用户", "actor_id": "操作人", "object_type": "对象类型",
    "object_id": "对象编号", "request_id": "请求编号", "detail": "结构化明细",
    "session_id": "会话编号", "expires_at": "过期时间", "revoked_at": "吊销时间",
    "target_key": "业务目标指纹（去重）", "heartbeat_at": "最近心跳",
    "storage_key": "私有存储键", "original_name": "原始文件名", "mime": "MIME 类型",
    "size": "字节数", "row_count": "观测条数", "origin": "来源（在线/导入）",
    "revision": "修订序号", "job_id_fk": "任务", "generated_at": "生成时间",
    "data_cutoff": "数据截止时间", "lower": "区间下界", "upper": "区间上界",
    "model_id": "模型编号", "task": "任务类型", "previous_id": "上一版本指针",
    "action": "动作", "from_status": "原状态", "to_status": "目标状态",
    "note": "说明", "body": "正文", "href": "跳转链接", "count": "条数",
    "message": "消息", "components": "分指数明细", "quality": "质量标记",
    "filename": "文件名", "content_hash": "内容哈希", "downloaded_at": "获取时间",
    "aqi": "AQI 值", "primary": "首要污染物", "window": "窗口",
}

ENUMS = [
    ("核查任务状态", "assigned 待核查 · inspection 现场核查 · rectification 整改跟踪 · reinspection 复查 · review 主管审核 · archived 已归档"),
    ("核查流转动作", "start 开始现场核查 · rectify 进入整改跟踪 · no_rectification 无需整改 · submit_rectification 提交整改复查 · submit_review 提交主管审核 · approve 审核通过归档 · return 退回补充核查 · reopen 重新开启"),
    ("线索状态", "pending 待研判 · assigned 已分派 · closed 已关闭 · rejected 已驳回"),
    ("线索优先级", "normal 普通 · high 较高 · urgent 紧急"),
    ("任务类型 kind", "collect 采集 · import 导入 · evaluate 评价 · train 训练 · forecast 预测 · impute 插补 · export 导出"),
    ("任务状态", "queued 排队中 · running 执行中 · succeeded 已完成 · partial 部分完成 · failed 失败 · cancelled 已取消"),
    ("评价结论", "exceeded 超过限值 · within 未超限 · insufficient 数据不足"),
    ("观测质量标记", "valid 有效 · missing 缺失 · invalid 无效 · imputed 插补（派生）"),
    ("评价口径 basis", "daily_mean 自然日有效小时均值 · daily_max_8h 日最大 8 小时均值"),
    ("来源文件类型", "all 颗粒物日文件 · extra 气态污染物日文件"),
    ("许可范围 scope", "trial_operation 试运行授权（须 valid_until）· continuous_business_use 持续业务使用"),
    ("通知通道", "webhook HTTPS 接收 · email SMTP 邮件"),
    ("导出报告", "observations 原始环境观测 · inspections 授权核查任务汇总（监管角色）"),
    ("导出格式", "csv 数据交换 · xlsx 含来源说明"),
    ("角色", "管理员 · 监管主管 · 执法人员 · 研究者"),
]


def norm_type(t: str, length: str) -> str:
    if t == "character varying":
        return f"varchar({length})" if length else "varchar"
    if t == "timestamp with time zone":
        return "timestamptz"
    if t == "double precision":
        return "float8"
    return t


def scan_roles() -> dict[tuple[str, str], str]:
    """Map (METHOD, path) -> role requirement by scanning router decorators and signatures."""
    roles: dict[tuple[str, str], str] = {}
    for f in APP.glob("*.py"):
        src = f.read_text(encoding="utf8")
        router_dep = ""
        m = re.search(r"router = APIRouter\((.*?)\)", src, re.S)
        if m and "dependencies" in m.group(1):
            router_dep = m.group(1)
        router_role = "已认证"
        if "REGULATORS" in router_dep:
            router_role = ROLE_GROUPS["REGULATORS"]
        elif "MANAGERS" in router_dep:
            router_role = ROLE_GROUPS["MANAGERS"]
        for dm in re.finditer(
            r'@router\.(get|post|put|patch|delete)\(\s*"([^"]+)".*?\n(?:async )?def\s+\w+\((.*?)\)\s*->',
            src, re.S,
        ):
            method, path, sig = dm.group(1).upper(), dm.group(2), dm.group(3)
            role = router_role
            am = re.search(r"authorize\(([^)]*)\)", sig)
            if am:
                arg = am.group(1)
                if "MANAGERS" in arg:
                    role = ROLE_GROUPS["MANAGERS"]
                elif "REGULATORS" in arg:
                    role = ROLE_GROUPS["REGULATORS"]
                else:
                    role = ",".join(re.findall(r'"([^"]+)"', arg)) or router_role
            roles[(method, path)] = role
    return roles


def main() -> None:
    api = json.loads((HERE / "openapi.json").read_text(encoding="utf8"))
    roles = scan_roles()

    # ---- Appendix A: endpoint list grouped by tag ----
    ops = []
    for path in sorted(api["paths"]):
        for method, op in api["paths"][path].items():
            if method not in ("get", "post", "put", "patch", "delete"):
                continue
            tag = (op.get("tags") or ["其他"])[0]
            summary = (op.get("summary") or op.get("description") or "").replace("\n", " ").strip()
            params = []
            for prm in op.get("parameters", []):
                params.append(prm["name"] + ("*" if prm.get("required") else ""))
            body = ""
            rb = op.get("requestBody", {}).get("content", {})
            if rb:
                sch = list(rb.values())[0].get("schema", {})
                body = sch.get("$ref", "").split("/")[-1] or sch.get("type", "")
            short = path.replace("/api/v2", "")
            role = roles.get((method.upper(), short), roles.get((method.upper(), path), "已认证"))
            ops.append((tag, method.upper(), short, summary, ",".join(params), body, role))

    lines: list[str] = []
    lines.append("""---
title: 蓝穹云眼 · 环境监管工作台
subtitle: 系统技术附录册
author: 【使用单位】 · 环境监测与执法辅助平台项目组
date: 文档编号【ESP-DOC-2026-02】 · 密级【内部】 · 试运行版 v2.0 · 2026-10
lang: zh-CN
---

# 说明

本册由 `gen_appendix.py` 依据运行系统的 OpenAPI 契约、数据库 schema 与路由鉴权声明自动生成，与 v2.0 试运行版代码一致。路径前缀均为 `/api/v2`；标记 * 的参数为必填。

# 附录 A 接口清单
""")
    by_tag: dict[str, list[tuple]] = {}
    for o in ops:
        by_tag.setdefault(o[0], []).append(o)
    for tag in sorted(by_tag):
        lines.append(f"\n## {tag}\n")
        lines.append("| 方法 | 路径 | 说明 | 参数 | 请求体 | 角色要求 |")
        lines.append("| --- | --- | --- | --- | --- | --- |")
        for _, method, short, summary, params, body, role in by_tag[tag]:
            lines.append(f"| {method} | {short} | {summary or '—'} | {params or '—'} | {body or '—'} | {role} |")

    # ---- Appendix B: data dictionary ----
    lines.append("\n# 附录 B 数据字典\n")
    lines.append("共 28 张业务表，按域分组。`v2_alembic_version` 为迁移版本表，不列入。\n")
    rows = []
    for raw in (HERE / "schema.txt").read_text(encoding="utf8").splitlines()[1:]:
        parts = raw.split("|")
        if len(parts) >= 5:
            rows.append(parts[:6])
    by_table: dict[str, list] = {}
    for r in rows:
        by_table.setdefault(r[0], []).append(r)
    domain_order = ["监测", "采集", "评价", "参考", "执法", "账号", "任务", "模型", "通知"]
    grouped: dict[str, list[str]] = {}
    for t in by_table:
        domain = TABLE_INFO.get(t, ("其他", t, ""))[0]
        grouped.setdefault(domain, []).append(t)
    for domain in domain_order + sorted(set(grouped) - set(domain_order)):
        if domain not in grouped:
            continue
        lines.append(f"\n## {domain}域\n")
        for t in sorted(grouped[domain]):
            _, cname, cdesc = TABLE_INFO.get(t, (domain, t, ""))
            lines.append(f"\n### {t} — {cname}\n\n{cdesc}\n")
            lines.append("| 字段 | 类型 | 可空 | 说明 |")
            lines.append("| --- | --- | :-: | --- |")
            for _, col, typ, nullable, length, _default in by_table[t]:
                desc = COL_DESC.get(col, "")
                lines.append(f"| {col} | {norm_type(typ, length)} | {'✓' if nullable == 'YES' else ''} | {desc} |")

    # ---- Appendix C: endpoint permission detail ----
    lines.append("\n# 附录 C 接口权限明细\n")
    lines.append("按路由声明提取：`get_user` 为已认证，`authorize(...)` 为接口级角色。函数体内的额外条件在备注列说明。\n")
    lines.append("| 方法 | 路径 | 角色要求 | 备注 |")
    lines.append("| --- | --- | --- | --- |")
    notes = {
        ("POST", "/jobs"): "collect/train 仅管理员；export 的 inspections 报告限监管角色",
        ("POST", "/imports"): "导入采集类内容限管理员/监管主管",
        ("GET", "/inspections/{identifier}"): "执法人员仅本人负责或协作的任务",
        ("PUT", "/inspections/{identifier}"): "同上；审核/归档状态不可编辑",
        ("POST", "/inspections/{identifier}/transition"): "approve/return/reopen 另需管理员或监管主管",
        ("GET", "/attachments/{identifier}/download"): "每次下载重新鉴权",
        ("GET", "/jobs/{identifier}/download"): "每次下载重新鉴权",
    }
    for tag_, method, short, summary, params, body, role in ops:
        note = notes.get((method, short), "")
        lines.append(f"| {method} | {short} | {role} | {note} |")

    # ---- Appendix D: enums ----
    lines.append("\n# 附录 D 枚举与取值表\n")
    lines.append("| 枚举 | 取值 |")
    lines.append("| --- | --- |")
    for name, values in ENUMS:
        lines.append(f"| {name} | {values} |")

    lines.append("""
# 附录 E 变更记录

| 版本 | 内容 |
| --- | --- |
| v2.0 | 首次生成：62 个接口、28 张表、接口级权限与枚举值表 |
""")

    out = HERE / "appendix.md"
    out.write_text("\n".join(lines), encoding="utf8")
    print(f"appendix.md written: {len(lines)} lines, {len(ops)} endpoints, {len(by_table)} tables")
    missing = [o for o in ops if o[6] == "已认证" and o[1] != "GET"]
    print("non-GET endpoints without explicit role scan:", len(missing))
    for o in missing[:15]:
        print("  ", o[1], o[2])


if __name__ == "__main__":
    main()
