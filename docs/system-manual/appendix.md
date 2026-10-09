---
title: 蓝穹云眼 · 环境监管工作台
subtitle: 系统技术附录册
author: 【使用单位】 · 环境监测与执法辅助平台项目组
date: 文档编号【ESP-DOC-2026-02】 · 密级【内部】 · 试运行版 v2.0 · 2026-10
lang: zh-CN
---

# 说明

本册由 `gen_appendix.py` 依据运行系统的 OpenAPI 契约、数据库 schema 与路由鉴权声明自动生成，与 v2.0 试运行版代码一致。路径前缀均为 `/api/v2`；标记 * 的参数为必填。

# 附录 A 接口清单


## 后台任务

| 方法 | 路径 | 说明 | 参数 | 请求体 | 角色要求 |
| --- | --- | --- | --- | --- | --- |
| POST | /imports | Upload Import | — | Body_upload_import_api_v2_imports_post | 管理员、监管主管 |
| POST | /jobs | Create Job | — | JobBody | 已认证 |
| GET | /jobs | Jobs | status,page_number,page_size | — | 已认证 |
| GET | /jobs/{identifier} | Job Detail | identifier* | — | 已认证 |
| POST | /jobs/{identifier}/cancel | Cancel Job | identifier* | — | 已认证 |
| GET | /jobs/{identifier}/download | Download | identifier* | — | 已认证 |
| POST | /jobs/{identifier}/retry | Retry Job | identifier* | — | 已认证 |

## 执法监督

| 方法 | 路径 | 说明 | 参数 | 请求体 | 角色要求 |
| --- | --- | --- | --- | --- | --- |
| POST | /attachments | Upload Attachment | — | Body_upload_attachment_api_v2_attachments_post | 管理员、监管主管、执法人员 |
| GET | /attachments/{identifier}/download | Download Attachment | identifier* | — | 管理员、监管主管、执法人员 |
| GET | /enterprises | Enterprises | q,page_number,page_size | — | 管理员、监管主管、执法人员 |
| POST | /enterprises | Create Enterprise | — | EnterpriseBody | 管理员、监管主管、执法人员 |
| GET | /enterprises/{identifier} | Enterprise Detail | identifier* | — | 管理员、监管主管、执法人员 |
| PUT | /enterprises/{identifier} | Update Enterprise | identifier* | EnterpriseBody | 管理员、监管主管、执法人员 |
| POST | /enterprises/{identifier}/records | Enterprise Record | identifier* | RecordBody | 管理员、监管主管、执法人员 |
| GET | /inspections | Inspections | status,q,page_number,page_size | — | 管理员、监管主管、执法人员 |
| GET | /inspections/{identifier} | Inspection Detail | identifier* | — | 管理员、监管主管、执法人员 |
| PUT | /inspections/{identifier} | Save Inspection | identifier* | InspectionBody | 管理员、监管主管、执法人员 |
| POST | /inspections/{identifier}/rectifications | Add Rectification | identifier* | RectificationBody | 管理员、监管主管、执法人员 |
| PUT | /inspections/{identifier}/rectifications/{rectification_id} | Update Rectification | identifier*,rectification_id* | RectificationUpdate | 管理员、监管主管、执法人员 |
| POST | /inspections/{identifier}/transition | Transition | identifier* | TransitionBody | 管理员、监管主管、执法人员 |
| GET | /leads | Leads | status,q,page_number,page_size | — | 管理员、监管主管、执法人员 |
| POST | /leads | Create Lead | — | LeadBody | 管理员、监管主管、执法人员 |
| POST | /leads/{identifier}/assign | Assign | identifier* | AssignBody | 管理员、监管主管 |
| POST | /leads/{identifier}/claim | Claim Lead | identifier* | — | 管理员、监管主管、执法人员 |
| POST | /leads/{identifier}/reject | Reject Lead | identifier* | ReasonBody | 管理员、监管主管 |

## 监测与评价

| 方法 | 路径 | 说明 | 参数 | 请求体 | 角色要求 |
| --- | --- | --- | --- | --- | --- |
| GET | /aqi | Aqi | station_id*,start*,end* | — | 已认证 |
| GET | /cities | Cities | — | — | 已认证 |
| GET | /dashboard | Dashboard | city_id,start,end | — | 已认证 |
| GET | /data-quality | Quality | start,end,city_id | — | 已认证 |
| GET | /evaluations | Evaluations | start,end,city_id,station_id,pollutant,status,page_number,page_size | — | 已认证 |
| GET | /forecasts | Forecasts | station_id*,pollutant,job_id | — | 已认证 |
| GET | /imputations | Imputations | station_id*,start*,end*,pollutant | — | 已认证 |
| GET | /observations | Observations | start,end,station_id,pollutant,city_id,page_number,page_size | — | 已认证 |
| GET | /stations | Stations | city_id | — | 已认证 |
| GET | /stations/{station_id} | Station Detail | station_id* | — | 已认证 |
| GET | /timeseries | Timeseries | start*,end*,pollutant,station_ids,city_id,resolution | — | 已认证 |

## 系统管理

| 方法 | 路径 | 说明 | 参数 | 请求体 | 角色要求 |
| --- | --- | --- | --- | --- | --- |
| GET | /admin/audits | Audits | page_number | — | 管理员 |
| GET | /admin/channels | Channels | — | — | 管理员 |
| POST | /admin/channels | Add Channel | — | ChannelBody | 管理员、监管主管 |
| PATCH | /admin/channels/{identifier} | Toggle Channel | identifier* | ChannelToggle | 管理员、监管主管 |
| POST | /admin/laws | Add Law | — | LawBody | 管理员、监管主管 |
| PATCH | /admin/laws/{identifier}/end | End Law | identifier* | ReferenceEnd | 管理员、监管主管 |
| GET | /admin/sources | Sources | — | — | 管理员 |
| POST | /admin/standards | Add Standard | — | StandardBody | 管理员、监管主管 |
| PATCH | /admin/standards/{identifier}/end | End Standard | identifier* | ReferenceEnd | 管理员、监管主管 |
| PUT | /admin/stations/{identifier} | Update Station | identifier* | StationBody | 管理员、监管主管 |
| POST | /admin/stations/{identifier}/aliases | Add Alias | identifier* | AliasBody | 管理员、监管主管 |
| GET | /admin/users | Users | — | — | 管理员 |
| POST | /admin/users | Create User | — | UserBody | 管理员 |
| PATCH | /admin/users/{identifier} | Update User | identifier* | UserUpdate | 管理员 |
| GET | /laws | Laws | — | — | 已认证 |
| GET | /models | Models | — | — | 已认证 |
| POST | /models/{identifier}/activate | Activate | identifier* | — | 管理员、监管主管 |
| POST | /models/{task}/rollback | Rollback | task* | — | 管理员、监管主管 |
| GET | /notifications | Notifications | — | — | 已认证 |
| POST | /notifications/{identifier}/read | Mark Read | identifier* | — | 已认证 |
| GET | /people | People | — | — | 管理员、监管主管、执法人员 |
| GET | /standards | Standards | — | — | 已认证 |

## 认证

| 方法 | 路径 | 说明 | 参数 | 请求体 | 角色要求 |
| --- | --- | --- | --- | --- | --- |
| POST | /auth/change-password | Change Password | — | PasswordBody | 已认证 |
| POST | /auth/login | Login | — | LoginBody | 已认证 |
| POST | /auth/logout | Logout | — | — | 已认证 |
| GET | /auth/me | Me | — | — | 已认证 |

# 附录 B 数据字典

共 28 张业务表，按域分组。`v2_alembic_version` 为迁移版本表，不列入。


## 监测域


### v2_cities — 城市目录

纳入观测口径的城市

| 字段 | 类型 | 可空 | 说明 |
| --- | --- | :-: | --- |
| code | varchar(30) |  | 编码/标准编号 |
| name | varchar(80) |  | 名称 |
| timezone | varchar(40) |  |  |
| id | varchar(36) |  | 主键（UUID） |
| created_at | timestamptz |  | 创建时间 |

### v2_derived_values — 派生值

插补与预测结果，独立存储不覆盖原始证据

| 字段 | 类型 | 可空 | 说明 |
| --- | --- | :-: | --- |
| station_id | varchar(36) |  | 站点编号 |
| observed_at | timestamptz |  | 观测时刻（UTC 存储） |
| pollutant | varchar(16) |  | 污染物 |
| kind | varchar(20) |  | 类型/任务类型 |
| value | float8 |  | 浓度/数值 |
| lower | float8 | ✓ | 区间下界 |
| upper | float8 | ✓ | 区间上界 |
| model_id | varchar(36) | ✓ | 模型编号 |
| job_id | varchar(36) |  | 任务编号 |
| data_cutoff | timestamptz |  | 数据截止时间 |
| snapshot_hash | varchar(64) |  | 输入快照哈希 |
| id | varchar(36) |  | 主键（UUID） |
| created_at | timestamptz |  | 创建时间 |

### v2_observations — 原始观测

小时值/滚动均值，UTC 存储，绑定来源文件

| 字段 | 类型 | 可空 | 说明 |
| --- | --- | :-: | --- |
| source_file_id | varchar(36) |  |  |
| station_id | varchar(36) |  | 站点编号 |
| observed_at | timestamptz |  | 观测时刻（UTC 存储） |
| local_date | date |  | 北京自然日 |
| pollutant | varchar(16) |  | 污染物 |
| basis | varchar(24) |  | 统计口径 |
| value | float8 | ✓ | 浓度/数值 |
| unit | varchar(20) |  | 计量单位 |
| quality | varchar(20) |  | 质量标记 |
| id | varchar(36) |  | 主键（UUID） |
| created_at | timestamptz |  | 创建时间 |

### v2_station_aliases — 站点别名

来源文件中的站名与目录映射，带有效期

| 字段 | 类型 | 可空 | 说明 |
| --- | --- | :-: | --- |
| station_id | varchar(36) |  | 站点编号 |
| provider | varchar(50) |  |  |
| external_name | varchar(100) |  | 来源文件中的名称 |
| valid_from | date |  | 适用起始日 |
| valid_to | date | ✓ | 适用截至日 |
| id | varchar(36) |  | 主键（UUID） |
| created_at | timestamptz |  | 创建时间 |

### v2_stations — 站点目录

监测站点档案：编码、名称、坐标、启停；坐标为参考数据

| 字段 | 类型 | 可空 | 说明 |
| --- | --- | :-: | --- |
| city_id | varchar(36) |  |  |
| code | varchar(100) |  | 编码/标准编号 |
| name | varchar(100) |  | 名称 |
| latitude | float8 | ✓ | 纬度 |
| longitude | float8 | ✓ | 经度 |
| active | boolean |  | 启用状态 |
| id | varchar(36) |  | 主键（UUID） |
| created_at | timestamptz |  | 创建时间 |

## 采集域


### v2_source_attempts — 采集尝试记录

每次获取尝试的结果与说明（含失败留痕）

| 字段 | 类型 | 可空 | 说明 |
| --- | --- | :-: | --- |
| local_date | date |  | 北京自然日 |
| kind | varchar(20) |  | 类型/任务类型 |
| status | varchar(20) |  | 状态 |
| message | text | ✓ | 消息 |
| job_id | varchar(36) | ✓ | 任务编号 |
| id | varchar(36) |  | 主键（UUID） |
| created_at | timestamptz |  | 创建时间 |

### v2_source_files — 来源文件

每次采集的原始文件登记，SHA-256 指纹与修订链

| 字段 | 类型 | 可空 | 说明 |
| --- | --- | :-: | --- |
| source_key | varchar(200) |  |  |
| local_date | date |  | 北京自然日 |
| kind | varchar(20) |  | 类型/任务类型 |
| origin | varchar(20) |  | 来源（在线/导入） |
| url | text | ✓ |  |
| sha256 | varchar(64) |  | SHA-256 指纹 |
| storage_key | text |  | 私有存储键 |
| is_current | boolean |  | 是否当前有效版本 |
| row_count | integer |  | 观测条数 |
| invalid_count | integer |  |  |
| attribution | text |  |  |
| id | varchar(36) |  | 主键（UUID） |
| created_at | timestamptz |  | 创建时间 |

## 评价域


### v2_aqi_results — AQI 结果

站点日 AQI 与六项分指数、完整性标记

| 字段 | 类型 | 可空 | 说明 |
| --- | --- | :-: | --- |
| station_id | varchar(36) |  | 站点编号 |
| local_date | date |  | 北京自然日 |
| value | integer | ✓ | 浓度/数值 |
| components | json |  | 分指数明细 |
| complete | boolean |  | 数据完整性是否满足 |
| version | varchar(32) |  | 版本号/乐观并发控制 |
| snapshot_hash | varchar(64) |  | 输入快照哈希 |
| is_current | boolean |  | 是否当前有效版本 |
| id | varchar(36) |  | 主键（UUID） |
| created_at | timestamptz |  | 创建时间 |

### v2_evaluations — 标准评价

站点×日×污染物评价：浓度、限值快照、超标倍数、完整性

| 字段 | 类型 | 可空 | 说明 |
| --- | --- | :-: | --- |
| station_id | varchar(36) |  | 站点编号 |
| local_date | date |  | 北京自然日 |
| pollutant | varchar(16) |  | 污染物 |
| basis | varchar(24) |  | 统计口径 |
| standard_id | varchar(36) |  |  |
| standard_snapshot | json |  |  |
| snapshot_hash | varchar(64) |  | 输入快照哈希 |
| valid_points | integer |  |  |
| value | float8 | ✓ | 浓度/数值 |
| exceed_ratio | float8 | ✓ |  |
| status | varchar(24) |  | 状态 |
| is_current | boolean |  | 是否当前有效版本 |
| job_id | varchar(36) | ✓ | 任务编号 |
| id | varchar(36) |  | 主键（UUID） |
| created_at | timestamptz |  | 创建时间 |

## 参考域


### v2_laws — 法规依据

法规版本与有效期，核查适用依据来源

| 字段 | 类型 | 可空 | 说明 |
| --- | --- | :-: | --- |
| title | varchar(240) |  | 标题 |
| region | varchar(80) |  | 适用地区 |
| effective_from | date |  | 生效日期 |
| effective_to | date | ✓ | 截至日期 |
| source_url | text |  | 原文链接 |
| summary | text |  | 摘要 |
| id | varchar(36) |  | 主键（UUID） |
| created_at | timestamptz |  | 创建时间 |

### v2_standards — 环境质量标准

标准版本、限值、口径、有效期、原文链接

| 字段 | 类型 | 可空 | 说明 |
| --- | --- | :-: | --- |
| code | varchar(80) |  | 编码/标准编号 |
| pollutant | varchar(16) |  | 污染物 |
| basis | varchar(24) |  | 统计口径 |
| grade | varchar(16) |  | 适用等级 |
| region | varchar(80) |  | 适用地区 |
| limit_value | float8 |  | 标准限值 |
| unit | varchar(20) |  | 计量单位 |
| min_points | integer |  | 最低有效统计数 |
| effective_from | date |  | 生效日期 |
| effective_to | date | ✓ | 截至日期 |
| source_url | text |  | 原文链接 |
| article | text |  |  |
| enabled | boolean |  | 启用标记 |
| version | integer |  | 版本号/乐观并发控制 |
| id | varchar(36) |  | 主键（UUID） |
| created_at | timestamptz |  | 创建时间 |

## 执法域


### v2_attachments — 证据附件

内容寻址文件引用，SHA-256 与版本链

| 字段 | 类型 | 可空 | 说明 |
| --- | --- | :-: | --- |
| inspection_id | varchar(36) | ✓ | 所属核查任务 |
| enterprise_id | varchar(36) | ✓ | 关联企业 |
| owner_id | varchar(36) |  | 发起人/属主 |
| original_name | varchar(240) |  | 原始文件名 |
| mime | varchar(100) |  | MIME 类型 |
| size | integer |  | 字节数 |
| sha256 | varchar(64) |  | SHA-256 指纹 |
| storage_key | text |  | 私有存储键 |
| replaces_id | varchar(36) | ✓ | 替换的原附件 |
| id | varchar(36) |  | 主键（UUID） |
| created_at | timestamptz |  | 创建时间 |

### v2_enterprise_records — 企业资料

排放口/许可证专项资料

| 字段 | 类型 | 可空 | 说明 |
| --- | --- | :-: | --- |
| enterprise_id | varchar(36) |  | 关联企业 |
| kind | varchar(20) |  | 类型/任务类型 |
| name | varchar(200) |  | 名称 |
| details | json |  |  |
| id | varchar(36) |  | 主键（UUID） |
| created_at | timestamptz |  | 创建时间 |

### v2_enterprises — 企业档案

企业身份、信用代码、行业、地址

| 字段 | 类型 | 可空 | 说明 |
| --- | --- | :-: | --- |
| name | varchar(200) |  | 名称 |
| credit_code | varchar(18) | ✓ | 统一社会信用代码 |
| industry | varchar(100) |  | 行业 |
| address | text |  | 地址 |
| contact | varchar(200) |  | 联系方式 |
| version | integer |  | 版本号/乐观并发控制 |
| created_by | varchar(36) |  |  |
| id | varchar(36) |  | 主键（UUID） |
| created_at | timestamptz |  | 创建时间 |

### v2_inspections — 核查任务

状态机载体；facts、legal_references、version 乐观锁

| 字段 | 类型 | 可空 | 说明 |
| --- | --- | :-: | --- |
| title | varchar(200) |  | 标题 |
| lead_id | varchar(36) | ✓ |  |
| enterprise_id | varchar(36) | ✓ | 关联企业 |
| assignee_id | varchar(36) |  | 负责人 |
| collaborators | json |  |  |
| created_by | varchar(36) |  |  |
| status | varchar(32) |  | 状态 |
| due_date | date | ✓ | 期限 |
| facts | text |  | 核查事实 |
| legal_references | json |  | 适用依据清单（法规+条款+理由） |
| version | integer |  | 版本号/乐观并发控制 |
| id | varchar(36) |  | 主键（UUID） |
| created_at | timestamptz |  | 创建时间 |

### v2_leads — 线索

待研判线索：来源、优先级、认领/分派/驳回

| 字段 | 类型 | 可空 | 说明 |
| --- | --- | :-: | --- |
| title | varchar(200) |  | 标题 |
| description | text |  | 描述 |
| station_id | varchar(36) | ✓ | 站点编号 |
| enterprise_id | varchar(36) | ✓ | 关联企业 |
| evaluation_id | varchar(36) | ✓ | 关联评价记录 |
| status | varchar(24) |  | 状态 |
| priority | varchar(20) |  | 优先级 |
| created_by | varchar(36) | ✓ |  |
| reason | text | ✓ | 理由 |
| id | varchar(36) |  | 主键（UUID） |
| created_at | timestamptz |  | 创建时间 |
| claimed_by | varchar(36) | ✓ | 认领人 |

### v2_rectifications — 整改事项

整改要求、期限、反馈、复查结论

| 字段 | 类型 | 可空 | 说明 |
| --- | --- | :-: | --- |
| inspection_id | varchar(36) |  | 所属核查任务 |
| requirement | text |  | 整改要求 |
| due_date | date |  | 期限 |
| response | text |  | 整改反馈 |
| review_note | text |  | 复查结论 |
| status | varchar(24) |  | 状态 |
| id | varchar(36) |  | 主键（UUID） |
| created_at | timestamptz |  | 创建时间 |

### v2_workflow_events — 流转留痕

每次状态流转的动作、说明、操作人

| 字段 | 类型 | 可空 | 说明 |
| --- | --- | :-: | --- |
| inspection_id | varchar(36) |  | 所属核查任务 |
| actor_id | varchar(36) |  | 操作人 |
| action | varchar(40) |  | 动作 |
| from_status | varchar(32) |  | 原状态 |
| to_status | varchar(32) |  | 目标状态 |
| note | text |  | 说明 |
| id | varchar(36) |  | 主键（UUID） |
| created_at | timestamptz |  | 创建时间 |

## 账号域


### v2_audits — 操作审计

不可变审计流水：操作、对象、请求编号、明细

| 字段 | 类型 | 可空 | 说明 |
| --- | --- | :-: | --- |
| actor_id | varchar(36) | ✓ | 操作人 |
| action | varchar(80) |  | 动作 |
| object_type | varchar(80) |  | 对象类型 |
| object_id | varchar(64) | ✓ | 对象编号 |
| detail | json |  | 结构化明细 |
| request_id | varchar(64) | ✓ | 请求编号 |
| id | varchar(36) |  | 主键（UUID） |
| created_at | timestamptz |  | 创建时间 |

### v2_sessions — 会话

服务端会话，可整批吊销

| 字段 | 类型 | 可空 | 说明 |
| --- | --- | :-: | --- |
| user_id | varchar(36) |  | 所属用户 |
| token_hash | varchar(64) |  |  |
| csrf_hash | varchar(64) |  |  |
| expires_at | timestamptz |  | 过期时间 |
| revoked | boolean |  |  |
| id | varchar(36) |  | 主键（UUID） |
| created_at | timestamptz |  | 创建时间 |

### v2_users — 用户

账号、角色、口令散列、锁定与强制改密

| 字段 | 类型 | 可空 | 说明 |
| --- | --- | :-: | --- |
| username | varchar(80) |  | 登录名 |
| display_name | varchar(80) |  | 姓名 |
| password_hash | text |  | Argon2 口令散列 |
| role | varchar(32) |  | 角色：管理员/监管主管/执法人员/研究者 |
| active | boolean |  | 启用状态 |
| must_change_password | boolean |  | 首次登录强制改密标记 |
| failed_logins | integer |  | 连续失败次数 |
| locked_until | timestamptz | ✓ | 锁定截止时间 |
| id | varchar(36) |  | 主键（UUID） |
| created_at | timestamptz |  | 创建时间 |

## 任务域


### v2_jobs — 异步任务

任务登记、状态、进度、结果与产物引用

| 字段 | 类型 | 可空 | 说明 |
| --- | --- | :-: | --- |
| kind | varchar(40) |  | 类型/任务类型 |
| owner_id | varchar(36) | ✓ | 发起人/属主 |
| parameters | json |  | 任务参数 |
| status | varchar(24) |  | 状态 |
| progress | integer |  | 进度百分比 |
| result | json |  | 执行结果 |
| error | text | ✓ | 失败原因 |
| attempts | integer |  | 执行次数 |
| target_key | varchar(160) |  | 业务目标指纹（去重） |
| started_at | timestamptz | ✓ |  |
| finished_at | timestamptz | ✓ |  |
| heartbeat_at | timestamptz | ✓ | 最近心跳 |
| id | varchar(36) |  | 主键（UUID） |
| created_at | timestamptz |  | 创建时间 |
| progress_stage | varchar(80) | ✓ |  |
| progress_message | varchar(240) | ✓ |  |

### v2_outbox — 事务发件箱

与业务写入同一事务的任务派发消息

| 字段 | 类型 | 可空 | 说明 |
| --- | --- | :-: | --- |
| job_id | varchar(36) |  | 任务编号 |
| sent_at | timestamptz | ✓ |  |
| id | varchar(36) |  | 主键（UUID） |
| created_at | timestamptz |  | 创建时间 |

## 模型域


### v2_model_activations — 模型激活

各任务当前使用版本与回滚指针

| 字段 | 类型 | 可空 | 说明 |
| --- | --- | :-: | --- |
| task | varchar(24) |  | 任务类型 |
| model_id | varchar(36) |  | 模型编号 |
| previous_id | varchar(36) | ✓ | 上一版本指针 |
| updated_at | timestamptz |  | 更新时间 |

### v2_models — 模型制品

算法、指标、特征、环境指纹、权重与重载校验

| 字段 | 类型 | 可空 | 说明 |
| --- | --- | :-: | --- |
| task | varchar(24) |  | 任务类型 |
| algorithm | varchar(40) |  | 算法 |
| status | varchar(24) |  | 状态 |
| storage_key | text |  | 私有存储键 |
| sha256 | varchar(64) |  | SHA-256 指纹 |
| manifest | json |  |  |
| metrics | json |  | 评估指标 |
| job_id | varchar(36) |  | 任务编号 |
| id | varchar(36) |  | 主键（UUID） |
| created_at | timestamptz |  | 创建时间 |

## 通知域


### v2_channels — 通知通道

Webhook/邮件外部通道配置与启停

| 字段 | 类型 | 可空 | 说明 |
| --- | --- | :-: | --- |
| name | varchar(120) |  | 名称 |
| kind | varchar(20) |  | 类型/任务类型 |
| config | json |  | 通道配置 |
| credential_ref | varchar(120) | ✓ | 凭据环境变量名（ESP_NOTIFY_*） |
| enabled | boolean |  | 启用标记 |
| id | varchar(36) |  | 主键（UUID） |
| created_at | timestamptz |  | 创建时间 |

### v2_deliveries — 发送记录

外部通道投递状态与尝试次数

| 字段 | 类型 | 可空 | 说明 |
| --- | --- | :-: | --- |
| notification_id | varchar(36) |  | 通知编号 |
| channel_id | varchar(36) |  |  |
| status | varchar(24) |  | 状态 |
| attempts | integer |  | 执行次数 |
| error | text | ✓ | 失败原因 |
| id | varchar(36) |  | 主键（UUID） |
| created_at | timestamptz |  | 创建时间 |

### v2_notifications — 站内通知

分派/退回等事件通知

| 字段 | 类型 | 可空 | 说明 |
| --- | --- | :-: | --- |
| user_id | varchar(36) |  | 所属用户 |
| title | varchar(200) |  | 标题 |
| body | text |  | 正文 |
| href | varchar(240) |  | 跳转链接 |
| dedupe_key | varchar(200) |  |  |
| read_at | timestamptz | ✓ | 已读时间 |
| id | varchar(36) |  | 主键（UUID） |
| created_at | timestamptz |  | 创建时间 |

# 附录 C 接口权限明细

按路由声明提取：`get_user` 为已认证，`authorize(...)` 为接口级角色。函数体内的额外条件在备注列说明。

| 方法 | 路径 | 角色要求 | 备注 |
| --- | --- | --- | --- |
| GET | /admin/audits | 管理员 |  |
| GET | /admin/channels | 管理员 |  |
| POST | /admin/channels | 管理员、监管主管 |  |
| PATCH | /admin/channels/{identifier} | 管理员、监管主管 |  |
| POST | /admin/laws | 管理员、监管主管 |  |
| PATCH | /admin/laws/{identifier}/end | 管理员、监管主管 |  |
| GET | /admin/sources | 管理员 |  |
| POST | /admin/standards | 管理员、监管主管 |  |
| PATCH | /admin/standards/{identifier}/end | 管理员、监管主管 |  |
| PUT | /admin/stations/{identifier} | 管理员、监管主管 |  |
| POST | /admin/stations/{identifier}/aliases | 管理员、监管主管 |  |
| GET | /admin/users | 管理员 |  |
| POST | /admin/users | 管理员 |  |
| PATCH | /admin/users/{identifier} | 管理员 |  |
| GET | /aqi | 已认证 |  |
| POST | /attachments | 管理员、监管主管、执法人员 |  |
| GET | /attachments/{identifier}/download | 管理员、监管主管、执法人员 | 每次下载重新鉴权 |
| POST | /auth/change-password | 已认证 |  |
| POST | /auth/login | 已认证 |  |
| POST | /auth/logout | 已认证 |  |
| GET | /auth/me | 已认证 |  |
| GET | /cities | 已认证 |  |
| GET | /dashboard | 已认证 |  |
| GET | /data-quality | 已认证 |  |
| GET | /enterprises | 管理员、监管主管、执法人员 |  |
| POST | /enterprises | 管理员、监管主管、执法人员 |  |
| GET | /enterprises/{identifier} | 管理员、监管主管、执法人员 |  |
| PUT | /enterprises/{identifier} | 管理员、监管主管、执法人员 |  |
| POST | /enterprises/{identifier}/records | 管理员、监管主管、执法人员 |  |
| GET | /evaluations | 已认证 |  |
| GET | /forecasts | 已认证 |  |
| POST | /imports | 管理员、监管主管 | 导入采集类内容限管理员/监管主管 |
| GET | /imputations | 已认证 |  |
| GET | /inspections | 管理员、监管主管、执法人员 |  |
| GET | /inspections/{identifier} | 管理员、监管主管、执法人员 | 执法人员仅本人负责或协作的任务 |
| PUT | /inspections/{identifier} | 管理员、监管主管、执法人员 | 同上；审核/归档状态不可编辑 |
| POST | /inspections/{identifier}/rectifications | 管理员、监管主管、执法人员 |  |
| PUT | /inspections/{identifier}/rectifications/{rectification_id} | 管理员、监管主管、执法人员 |  |
| POST | /inspections/{identifier}/transition | 管理员、监管主管、执法人员 | approve/return/reopen 另需管理员或监管主管 |
| POST | /jobs | 已认证 | collect/train 仅管理员；export 的 inspections 报告限监管角色 |
| GET | /jobs | 已认证 |  |
| GET | /jobs/{identifier} | 已认证 |  |
| POST | /jobs/{identifier}/cancel | 已认证 |  |
| GET | /jobs/{identifier}/download | 已认证 | 每次下载重新鉴权 |
| POST | /jobs/{identifier}/retry | 已认证 |  |
| GET | /laws | 已认证 |  |
| GET | /leads | 管理员、监管主管、执法人员 |  |
| POST | /leads | 管理员、监管主管、执法人员 |  |
| POST | /leads/{identifier}/assign | 管理员、监管主管 |  |
| POST | /leads/{identifier}/claim | 管理员、监管主管、执法人员 |  |
| POST | /leads/{identifier}/reject | 管理员、监管主管 |  |
| GET | /models | 已认证 |  |
| POST | /models/{identifier}/activate | 管理员、监管主管 |  |
| POST | /models/{task}/rollback | 管理员、监管主管 |  |
| GET | /notifications | 已认证 |  |
| POST | /notifications/{identifier}/read | 已认证 |  |
| GET | /observations | 已认证 |  |
| GET | /people | 管理员、监管主管、执法人员 |  |
| GET | /standards | 已认证 |  |
| GET | /stations | 已认证 |  |
| GET | /stations/{station_id} | 已认证 |  |
| GET | /timeseries | 已认证 |  |

# 附录 D 枚举与取值表

| 枚举 | 取值 |
| --- | --- |
| 核查任务状态 | assigned 待核查 · inspection 现场核查 · rectification 整改跟踪 · reinspection 复查 · review 主管审核 · archived 已归档 |
| 核查流转动作 | start 开始现场核查 · rectify 进入整改跟踪 · no_rectification 无需整改 · submit_rectification 提交整改复查 · submit_review 提交主管审核 · approve 审核通过归档 · return 退回补充核查 · reopen 重新开启 |
| 线索状态 | pending 待研判 · assigned 已分派 · closed 已关闭 · rejected 已驳回 |
| 线索优先级 | normal 普通 · high 较高 · urgent 紧急 |
| 任务类型 kind | collect 采集 · import 导入 · evaluate 评价 · train 训练 · forecast 预测 · impute 插补 · export 导出 |
| 任务状态 | queued 排队中 · running 执行中 · succeeded 已完成 · partial 部分完成 · failed 失败 · cancelled 已取消 |
| 评价结论 | exceeded 超过限值 · within 未超限 · insufficient 数据不足 |
| 观测质量标记 | valid 有效 · missing 缺失 · invalid 无效 · imputed 插补（派生） |
| 评价口径 basis | daily_mean 自然日有效小时均值 · daily_max_8h 日最大 8 小时均值 |
| 来源文件类型 | all 颗粒物日文件 · extra 气态污染物日文件 |
| 许可范围 scope | trial_operation 试运行授权（须 valid_until）· continuous_business_use 持续业务使用 |
| 通知通道 | webhook HTTPS 接收 · email SMTP 邮件 |
| 导出报告 | observations 原始环境观测 · inspections 授权核查任务汇总（监管角色） |
| 导出格式 | csv 数据交换 · xlsx 含来源说明 |
| 角色 | 管理员 · 监管主管 · 执法人员 · 研究者 |

# 附录 E 变更记录

| 版本 | 内容 |
| --- | --- |
| v2.0 | 首次生成：62 个接口、28 张表、接口级权限与枚举值表 |
