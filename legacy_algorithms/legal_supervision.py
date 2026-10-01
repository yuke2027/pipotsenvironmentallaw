"""
法律监督体系模块
环境空气质量合规性检查和风险评估
"""

import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
import seaborn as sns
import warnings
warnings.filterwarnings('ignore')

plt.rcParams['font.sans-serif'] = ['SimHei']  
plt.rcParams['axes.unicode_minus'] = False

# 定义基础路径
# The module is packaged under ``legacy_algorithms`` while its data and output
# locations intentionally remain rooted at the historical project directory.
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if not BASE_DIR:
    BASE_DIR = os.getcwd()
DATA_DIR = os.path.join(BASE_DIR, "data", "air_quality")
LEGAL_SUPERVISION_DIR = os.path.join(BASE_DIR, "results", "legal_supervision")
os.makedirs(LEGAL_SUPERVISION_DIR, exist_ok=True)


class EnvironmentalLegalStandards:
    """环境法律标准数据库"""
    
    def __init__(self):
        """初始化环境空气质量标准（GB 3095-2012）"""
        self.standards = {
            'PM2.5': {
                '24h_mean': 75,
                'annual_mean': 35,
                'legal_basis': 'GB 3095-2012《环境空气质量标准》',
                'penalty_basis': '《大气污染防治法》第九十九条'
            },
            'PM10': {
                '24h_mean': 150,
                'annual_mean': 70,
                'legal_basis': 'GB 3095-2012《环境空气质量标准》',
                'penalty_basis': '《大气污染防治法》第九十九条'
            },
            'AQI': {
                'excellent': 50,
                'good': 100,
                'light_pollution': 150,
                'moderate_pollution': 200,
                'heavy_pollution': 300,
                'severe_pollution': 500,
                'legal_basis': 'HJ 633-2012《环境空气质量指数（AQI）技术规定（试行）》',
                'penalty_basis': '《大气污染防治法》第九十九条'
            }
        }
        
        self.risk_levels = {
            'low': {'threshold': 0.8, 'description': '低风险：符合标准，无需采取行动'},
            'medium': {'threshold': 1.0, 'description': '中风险：接近标准限值，需要关注'},
            'high': {'threshold': 1.5, 'description': '高风险：超过标准限值，需要采取治理措施'},
            'critical': {'threshold': float('inf'), 'description': '严重风险：严重超标，可能面临法律处罚'}
        }
    
    def get_standard(self, pollutant, standard_type='24h_mean'):
        """获取污染物标准限值"""
        if pollutant in self.standards:
            return self.standards[pollutant].get(standard_type, None)
        return None
    
    def get_risk_level(self, value, pollutant, standard_type='24h_mean'):
        """计算风险等级"""
        standard = self.get_standard(pollutant, standard_type)
        if standard is None:
            return None
        
        ratio = value / standard
        
        if ratio < self.risk_levels['low']['threshold']:
            return 'low'
        elif ratio < self.risk_levels['medium']['threshold']:
            return 'medium'
        elif ratio < self.risk_levels['high']['threshold']:
            return 'high'
        else:
            return 'critical'
    
    def get_risk_description(self, risk_level):
        """获取风险等级描述"""
        return self.risk_levels.get(risk_level, {}).get('description', '未知风险等级')


class ComplianceChecker:
    """合规性检查器"""
    
    def __init__(self, legal_standards):
        self.standards = legal_standards
    
    def check_compliance(self, data_df, pollutant_col, date_col='date', station_col='station_id'):
        """检查数据合规性"""
        results = []
        
        for station in data_df[station_col].unique():
            station_data = data_df[data_df[station_col] == station].copy()
            
            for date in station_data[date_col].unique():
                daily_data = station_data[station_data[date_col] == date]
                
                daily_mean = daily_data[pollutant_col].mean()
                pollutant_name = pollutant_col
                standard = self.standards.get_standard(pollutant_name, '24h_mean')
                
                if standard is None:
                    continue
                
                exceed_ratio = daily_mean / standard if standard > 0 else 0
                is_compliant = daily_mean <= standard
                risk_level = self.standards.get_risk_level(daily_mean, pollutant_name, '24h_mean')
                risk_desc = self.standards.get_risk_description(risk_level)
                
                results.append({
                    'station_id': station,
                    'date': date,
                    'pollutant': pollutant_name,
                    'daily_mean': daily_mean,
                    'standard_limit': standard,
                    'exceed_ratio': exceed_ratio,
                    'is_compliant': is_compliant,
                    'risk_level': risk_level,
                    'risk_description': risk_desc,
                    'max_value': daily_data[pollutant_col].max(),
                    'min_value': daily_data[pollutant_col].min(),
                    'data_points': len(daily_data)
                })
        
        return pd.DataFrame(results)
    
    def check_all_pollutants(self, data_df, pollutant_cols=['PM2.5', 'PM10', 'AQI']):
        """检查所有污染物的合规性"""
        all_results = []
        
        for pollutant in pollutant_cols:
            if pollutant in data_df.columns:
                results = self.check_compliance(data_df, pollutant)
                all_results.append(results)
        
        if all_results:
            return pd.concat(all_results, ignore_index=True)
        return pd.DataFrame()


class LegalRiskAssessor:
    """法律风险评估器"""
    
    def __init__(self, legal_standards):
        self.standards = legal_standards
    
    def assess_risk(self, compliance_results):
        """评估法律风险"""
        if compliance_results.empty:
            return pd.DataFrame()
        
        risk_assessments = []
        
        for _, row in compliance_results.iterrows():
            risk_score = self._calculate_risk_score(row)
            legal_consequences = self._assess_legal_consequences(row)
            recommended_actions = self._recommend_actions(row)
            
            risk_assessments.append({
                'station_id': row['station_id'],
                'date': row['date'],
                'pollutant': row['pollutant'],
                'risk_score': risk_score,
                'risk_level': row['risk_level'],
                'legal_consequences': legal_consequences,
                'recommended_actions': recommended_actions,
                'penalty_estimate': self._estimate_penalty(row),
                'compliance_status': '合规' if row['is_compliant'] else '超标'
            })
        
        return pd.DataFrame(risk_assessments)
    
    def _calculate_risk_score(self, row):
        """计算风险评分（0-100）"""
        if row['is_compliant']:
            base_score = 20
        else:
            base_score = 50 + min(50, row['exceed_ratio'] * 20)
        
        risk_multipliers = {
            'low': 0.5,
            'medium': 1.0,
            'high': 1.5,
            'critical': 2.0
        }
        
        multiplier = risk_multipliers.get(row['risk_level'], 1.0)
        return min(100, base_score * multiplier)
    
    def _assess_legal_consequences(self, row):
        """评估法律后果"""
        if row['is_compliant']:
            return "无法律风险，符合环境空气质量标准"
        
        consequences = []
        
        if row['exceed_ratio'] >= 1.5:
            consequences.append("可能面临行政处罚（10-100万元）")
            consequences.append("可能被责令限期治理")
        
        if row['exceed_ratio'] >= 2.0:
            consequences.append("可能面临更严厉的行政处罚（50-500万元）")
            consequences.append("可能被责令停产整治")
        
        if row['pollutant'] == 'AQI' and row['daily_mean'] >= 300:
            consequences.append("严重污染天气，可能启动应急响应")
            consequences.append("可能面临最高1000万元罚款")
        
        return "; ".join(consequences) if consequences else "轻微超标，建议加强监测"
    
    def _recommend_actions(self, row):
        """推荐应对措施"""
        actions = []
        
        if not row['is_compliant']:
            actions.append("立即采取减排措施")
            actions.append("加强监测频率")
            
            if row['risk_level'] == 'high' or row['risk_level'] == 'critical':
                actions.append("启动应急预案")
                actions.append("向环保部门报告")
                actions.append("考虑临时停产或限产")
        
        if row['risk_level'] == 'medium':
            actions.append("加强日常监管")
            actions.append("预防性减排措施")
        
        return "; ".join(actions) if actions else "保持现状，继续监测"
    
    def _estimate_penalty(self, row):
        """估算可能的处罚金额"""
        if row['is_compliant']:
            return "无处罚"
        
        exceed_ratio = row['exceed_ratio']
        
        if exceed_ratio < 1.2:
            return "10-50万元"
        elif exceed_ratio < 1.5:
            return "50-100万元"
        elif exceed_ratio < 2.0:
            return "100-300万元"
        else:
            return "300-1000万元"


def run_legal_supervision(data_dir=None, output_dir=None):
    """运行完整的法律监督流程"""
    if data_dir is None:
        data_dir = DATA_DIR
    if output_dir is None:
        output_dir = LEGAL_SUPERVISION_DIR
    
    print("=" * 80)
    print("开始执行法律监督检查...")
    print("=" * 80)
    
    # 初始化
    legal_standards = EnvironmentalLegalStandards()
    compliance_checker = ComplianceChecker(legal_standards)
    risk_assessor = LegalRiskAssessor(legal_standards)
    
    # 1. 加载数据
    print("\n步骤1: 加载空气质量数据...")
    particulate_files = [f for f in os.listdir(data_dir) 
                        if f.endswith('_particulate.csv')]
    
    if not particulate_files:
        print("错误: 未找到数据文件！")
        return None
    
    print(f"找到 {len(particulate_files)} 个数据文件")
    
    all_data = []
    for file_name in particulate_files:
        file_path = os.path.join(data_dir, file_name)
        try:
            df = pd.read_csv(file_path)
            all_data.append(df)
        except Exception as e:
            print(f"警告: 无法读取文件 {file_name}: {str(e)}")
    
    if not all_data:
        print("错误: 无法加载任何数据！")
        return None
    
    combined_data = pd.concat(all_data, ignore_index=True)
    print(f"成功加载数据: {len(combined_data)} 条记录")
    
    # 2. 合规性检查
    print("\n步骤2: 执行合规性检查...")
    compliance_results = compliance_checker.check_all_pollutants(
        combined_data, 
        pollutant_cols=['PM2.5', 'PM10', 'AQI']
    )
    
    if compliance_results.empty:
        print("警告: 合规性检查未产生结果")
        return None
    
    print(f"完成合规性检查: {len(compliance_results)} 条检查结果")
    
    # 保存合规性检查结果
    compliance_file = os.path.join(output_dir, 'compliance_results.csv')
    compliance_results.to_csv(compliance_file, index=False, encoding='utf-8-sig')
    print(f"合规性检查结果已保存: {compliance_file}")
    
    # 3. 法律风险评估
    print("\n步骤3: 执行法律风险评估...")
    risk_assessments = risk_assessor.assess_risk(compliance_results)
    
    if not risk_assessments.empty:
        risk_file = os.path.join(output_dir, 'risk_assessments.csv')
        risk_assessments.to_csv(risk_file, index=False, encoding='utf-8-sig')
        print(f"风险评估结果已保存: {risk_file}")
    
    print("\n" + "=" * 80)
    print("法律监督检查完成！")
    print("=" * 80)
    
    return {
        'compliance_results': compliance_results,
        'risk_assessments': risk_assessments
    }


if __name__ == "__main__":
    results = run_legal_supervision()
    
    if results:
        print("\n法律监督检查摘要:")
        print(f"- 合规性检查记录数: {len(results['compliance_results'])}")
        if not results['risk_assessments'].empty:
            print(f"- 风险评估记录数: {len(results['risk_assessments'])}")
            critical_risks = results['risk_assessments'][
                results['risk_assessments']['risk_level'].isin(['high', 'critical'])
            ]
            print(f"- 高风险/严重风险事件: {len(critical_risks)} 起")


