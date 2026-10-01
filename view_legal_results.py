"""查看法律监督检查结果摘要"""
import pandas as pd
import os

LEGAL_SUPERVISION_DIR = os.path.join("results", "legal_supervision")

# 读取风险评估结果
risk_df = pd.read_csv(os.path.join(LEGAL_SUPERVISION_DIR, 'risk_assessments.csv'))
compliance_df = pd.read_csv(os.path.join(LEGAL_SUPERVISION_DIR, 'compliance_results.csv'))

print("=" * 80)
print("法律监督检查结果摘要")
print("=" * 80)

print("\n1. 风险等级统计:")
print(risk_df['risk_level'].value_counts())

print("\n2. 合规性统计:")
print(f"总检查记录数: {len(compliance_df)}")
print(f"合规记录数: {len(compliance_df[compliance_df['is_compliant'] == True])}")
print(f"超标记录数: {len(compliance_df[compliance_df['is_compliant'] == False])}")

print("\n3. 高风险/严重风险事件:")
critical = risk_df[risk_df['risk_level'].isin(['high', 'critical'])]
print(f"共 {len(critical)} 起高风险/严重风险事件")

if len(critical) > 0:
    print("\n前10条高风险事件详情:")
    print(critical[['station_id', 'date', 'pollutant', 'risk_level', 'penalty_estimate', 'compliance_status']].head(10))

print("\n4. 超标事件统计:")
non_compliant = compliance_df[compliance_df['is_compliant'] == False]
if len(non_compliant) > 0:
    print(f"共 {len(non_compliant)} 起超标事件")
    print("\n按污染物统计:")
    print(non_compliant['pollutant'].value_counts())
    print("\n前10条超标事件详情:")
    print(non_compliant[['station_id', 'date', 'pollutant', 'daily_mean', 'standard_limit', 'exceed_ratio', 'risk_level']].head(10))
else:
    print("未发现超标事件")

print("\n5. 各站点风险统计:")
station_risks = risk_df.groupby(['station_id', 'risk_level']).size().unstack(fill_value=0)
print(station_risks.head(10))

print("\n" + "=" * 80)
print("结果文件位置:")
print(f"- 合规性检查结果: {os.path.join(LEGAL_SUPERVISION_DIR, 'compliance_results.csv')}")
print(f"- 风险评估结果: {os.path.join(LEGAL_SUPERVISION_DIR, 'risk_assessments.csv')}")
print("=" * 80)


