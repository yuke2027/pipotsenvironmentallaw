"""
数据预处理模块
将原始空气质量数据转换为结构化格式
"""

import pandas as pd
import os
from datetime import datetime
import numpy as np


def process_air_quality_data(input_file_path, output_dir="processed_data", date_format="%Y%m%d"):
    """处理空气质量数据文件"""
    # 创建输出目录
    os.makedirs(output_dir, exist_ok=True)
    
    print(f"正在处理文件: {input_file_path}")
    
    try:
        # 读取CSV文件
        df = pd.read_csv(input_file_path)
        print(f"原始数据形状: {df.shape}")
        
        # 查看前几列的名称以确认列结构
        print(f"列名: {df.columns.tolist()[:10]}...")
        
        # 确保基本列存在
        required_cols = ['date', 'hour', 'type']
        for col in required_cols:
            if col not in df.columns:
                raise ValueError(f"未找到必需的列: {col}")
        
        # 识别所有站点列
        station_cols = [col for col in df.columns if col not in required_cols]
        n_stations = len(station_cols)
        print(f"发现{n_stations}个监测站")
        
        # 检查数据中的日期范围
        unique_dates = df['date'].unique()
        print(f"数据包含{len(unique_dates)}个日期")
        
        # 对每个日期分别处理
        for date_val in unique_dates:
            # 转换日期格式
            try:
                # 将整数日期转换为字符串
                if isinstance(date_val, (int, float)):
                    date_val = str(int(date_val))
                
                # 解析日期
                date_obj = datetime.strptime(date_val, date_format)
                formatted_date = date_obj.strftime("%Y-%m-%d")
            except:
                print(f"警告: 无法解析日期 {date_val}，使用原始值")
                formatted_date = str(date_val)
            
            print(f"处理日期: {formatted_date}")
            
            # 筛选当前日期的数据
            date_df = df[df['date'] == date_val]
            
            # 创建DataFrame来保存结果
            particulate_df = pd.DataFrame()
            gas_df = pd.DataFrame()
            
            # 处理不同的污染物类型
            pm25_rows = date_df[date_df['type'] == 'PM2.5']
            pm10_rows = date_df[date_df['type'] == 'PM10']
            aqi_rows = date_df[date_df['type'] == 'AQI']
            
            # 查找气体类型
            gas_types = [t for t in date_df['type'].unique() 
                        if t not in ['PM2.5', 'PM10', 'AQI', 'PM2.5_24h', 'PM10_24h']]
            
            print(f"发现的污染物类型: {date_df['type'].unique().tolist()}")
            
            # 1. 准备颗粒物数据集
            all_hours = date_df['hour'].unique()
            rows = []
            
            for station in station_cols:
                for hour in all_hours:
                    row = {
                        'station_id': station,
                        'timestamp': hour
                    }
                    
                    # 添加PM2.5值
                    pm25_hour_data = pm25_rows[pm25_rows['hour'] == hour]
                    if not pm25_hour_data.empty and station in pm25_hour_data.columns:
                        row['PM2.5'] = pm25_hour_data[station].values[0]
                    
                    # 添加PM10值
                    pm10_hour_data = pm10_rows[pm10_rows['hour'] == hour]
                    if not pm10_hour_data.empty and station in pm10_hour_data.columns:
                        row['PM10'] = pm10_hour_data[station].values[0]
                    
                    # 添加AQI值
                    aqi_hour_data = aqi_rows[aqi_rows['hour'] == hour]
                    if not aqi_hour_data.empty and station in aqi_hour_data.columns:
                        row['AQI'] = aqi_hour_data[station].values[0]
                    
                    rows.append(row)
            
            # 创建颗粒物DataFrame
            particulate_df = pd.DataFrame(rows)
            
            # 2. 准备气体数据集
            gas_rows = []
            
            for station in station_cols:
                for hour in all_hours:
                    row = {
                        'station_id': station,
                        'timestamp': hour
                    }
                    
                    # 添加各类气体污染物的值
                    for gas_type in gas_types:
                        gas_data = date_df[(date_df['type'] == gas_type) & (date_df['hour'] == hour)]
                        if not gas_data.empty and station in gas_data.columns:
                            row[gas_type] = gas_data[station].values[0]
                    
                    gas_rows.append(row)
            
            # 创建气体DataFrame
            gas_df = pd.DataFrame(gas_rows)
            
            # 添加日期列
            particulate_df['date'] = formatted_date
            gas_df['date'] = formatted_date
            
            # 对结果进行排序
            particulate_df = particulate_df.sort_values(['station_id', 'timestamp']).reset_index(drop=True)
            gas_df = gas_df.sort_values(['station_id', 'timestamp']).reset_index(drop=True)
            
            print(f"颗粒物数据形状: {particulate_df.shape}")
            print(f"气体数据形状: {gas_df.shape}")
            
            # 保存处理后的结果
            particulate_file = os.path.join(output_dir, f"{formatted_date}_particulate.csv")
            gas_file = os.path.join(output_dir, f"{formatted_date}_gas.csv")
            
            particulate_df.to_csv(particulate_file, index=False)
            gas_df.to_csv(gas_file, index=False)
            
            print(f"已保存到: {particulate_file} 和 {gas_file}")
        
        return True
    
    except Exception as e:
        print(f"处理文件时出错: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def process_monthly_files(base_dir, pattern="beijing_all_", year=2025, month=1, output_dir="processed_data"):
    """处理月度数据文件"""
    print(f"处理{year}年{month}月的所有数据文件...")
    
    # 构建月份字符串
    month_str = f"{month:02d}"
    
    # 列出目录中的所有文件
    all_files = os.listdir(base_dir)
    
    # 筛选出匹配的文件
    target_pattern = f"{pattern}{year}{month_str}"
    month_files = [f for f in all_files if target_pattern in f and f.endswith('.csv')]
    
    if not month_files:
        print(f"未找到{year}年{month}月的数据文件!")
        return []
    
    print(f"找到{len(month_files)}个文件: {', '.join(month_files[:5])}...")
    
    # 处理每个文件
    results = []
    for file in month_files:
        file_path = os.path.join(base_dir, file)
        success = process_air_quality_data(file_path, output_dir)
        results.append({
            'file': file,
            'success': success
        })
    
    # 输出处理结果摘要
    success_count = sum(1 for r in results if r['success'])
    print(f"\n处理完成! 成功: {success_count}/{len(results)} 个文件")
    
    return results


if __name__ == "__main__":
    # 设置参数
    BASE_DIR = "E:/24-25-2/环境与资源保护法/大作业数据分析/beijing_20250101-20250510"
    OUTPUT_DIR = "data/air_quality"
    
    # 创建输出目录
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # 处理1月份的数据文件
    process_monthly_files(
        base_dir=BASE_DIR,
        pattern="beijing_all_",
        year=2025,
        month=1,
        output_dir=OUTPUT_DIR
    )
    
    print("\n数据预处理完成!")


