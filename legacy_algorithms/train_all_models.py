"""
统一训练脚本 - 训练PyPOTS和LSTM模型
"""

import os
import sys
import argparse
from datetime import datetime

from .data_imputation import (
    AirQualityDataProcessor,
    PyPOTSImputer,
    LSTMImputer,
    ResultsSaver
)

# 定义路径
# Keep historical project-relative data and output locations after packaging.
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data", "air_quality")
RESULTS_DIR = os.path.join(BASE_DIR, "results", "imputed")
PLOTS_DIR = os.path.join(BASE_DIR, "results", "plots")
MODELS_DIR = os.path.join(BASE_DIR, "results", "models")

os.makedirs(PLOTS_DIR, exist_ok=True)
os.makedirs(MODELS_DIR, exist_ok=True)


def load_data():
    """加载数据"""
    print("=" * 80)
    print("步骤1: 加载数据")
    print("=" * 80)
    
    processor = AirQualityDataProcessor()
    
    particulate_files = [f for f in os.listdir(DATA_DIR) 
                        if f.endswith('_particulate.csv')]
    print(f"找到 {len(particulate_files)} 个particulate数据文件")
    
    particulate_data = []
    for file_name in particulate_files:
        file_path = os.path.join(DATA_DIR, file_name)
        df = processor.process_daily_data(file_path)
        if df is not None:
            particulate_data.append(df)
    
    if not particulate_data:
        raise ValueError("未找到有效的particulate数据文件！")
    
    print("处理数据集...")
    dataset = processor.process_dataset(particulate_data)
    
    if dataset is None:
        raise ValueError("数据处理失败！")
    
    print(f"数据集形状: {dataset['train_X'].shape}")
    print(f"训练集: {dataset['train_X'].shape[0]} 个站点")
    print(f"验证集: {dataset['val_X'].shape[0]} 个站点")
    print(f"测试集: {dataset['test_X'].shape[0]} 个站点")
    
    return dataset


def train_pypots(dataset, n_epochs=10):
    """训练PyPOTS SAITS模型"""
    print("\n" + "=" * 80)
    print("步骤2: 训练PyPOTS SAITS模型")
    print("=" * 80)
    
    imputer = PyPOTSImputer(
        n_steps=dataset['n_steps'],
        n_features=dataset['n_features'],
        n_epochs=n_epochs
    )
    
    results = imputer.perform_imputation(dataset)
    
    if results:
        saver = ResultsSaver(RESULTS_DIR, PLOTS_DIR)
        saver.save_results(results, dataset, model_name='pypots')
        print("\n[成功] PyPOTS模型训练完成！")
        return results
    else:
        print("\n[失败] PyPOTS模型训练失败！")
        return None


def train_lstm(dataset, n_epochs=50, hidden_units=128):
    """训练LSTM模型"""
    print("\n" + "=" * 80)
    print("步骤3: 训练LSTM神经网络模型")
    print("=" * 80)
    
    imputer = LSTMImputer(
        n_steps=dataset['n_steps'],
        n_features=dataset['n_features'],
        n_epochs=n_epochs,
        hidden_units=hidden_units
    )
    
    results = imputer.perform_imputation(dataset)
    
    if results:
        saver = ResultsSaver(RESULTS_DIR, PLOTS_DIR)
        saver.save_results(results, dataset, model_name='lstm')
        print("\n[成功] LSTM模型训练完成！")
        return results
    else:
        print("\n[失败] LSTM模型训练失败！")
        return None


def compare_models(pypots_results, lstm_results, dataset):
    """比较两个模型的结果"""
    print("\n" + "=" * 80)
    print("步骤4: 模型性能对比")
    print("=" * 80)
    
    saver = ResultsSaver(RESULTS_DIR, PLOTS_DIR)
    
    comparison = {}
    
    if pypots_results:
        print("\nPyPOTS模型评估指标:")
        for name in ['train_imputed', 'val_imputed']:
            if name in pypots_results:
                set_type = name.split('_')[0]
                metrics = saver.calculate_metrics(
                    dataset[f'{set_type}_X_ori'],
                    pypots_results[name],
                    dataset['mask'][set_type],
                    dataset['scaler'],
                    dataset['n_features']
                )
                comparison[f'pypots_{set_type}'] = metrics
                print(f"  {set_type}: MSE={metrics['MSE']:.6f}, "
                      f"MAE={metrics['MAE']:.6f}, RMSE={metrics['RMSE']:.6f}")
    
    if lstm_results:
        print("\nLSTM模型评估指标:")
        for name in ['train_imputed', 'val_imputed']:
            if name in lstm_results:
                set_type = name.split('_')[0]
                metrics = saver.calculate_metrics(
                    dataset[f'{set_type}_X_ori'],
                    lstm_results[name],
                    dataset['mask'][set_type],
                    dataset['scaler'],
                    dataset['n_features']
                )
                comparison[f'lstm_{set_type}'] = metrics
                print(f"  {set_type}: MSE={metrics['MSE']:.6f}, "
                      f"MAE={metrics['MAE']:.6f}, RMSE={metrics['RMSE']:.6f}")
    
    return comparison


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='训练PyPOTS和LSTM模型')
    parser.add_argument('--pypots-epochs', type=int, default=10,
                       help='PyPOTS训练轮数 (默认: 10)')
    parser.add_argument('--lstm-epochs', type=int, default=50,
                       help='LSTM训练轮数 (默认: 50)')
    parser.add_argument('--lstm-units', type=int, default=128,
                       help='LSTM隐藏单元数 (默认: 128)')
    parser.add_argument('--pypots-only', action='store_true',
                       help='仅训练PyPOTS模型')
    parser.add_argument('--lstm-only', action='store_true',
                       help='仅训练LSTM模型')
    
    args = parser.parse_args()
    
    try:
        start_time = datetime.now()
        print("\n" + "=" * 80)
        print("开始训练所有模型")
        print(f"开始时间: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 80)
        
        # 加载数据
        dataset = load_data()
        
        pypots_results = None
        lstm_results = None
        
        # 训练PyPOTS
        if not args.lstm_only:
            pypots_results = train_pypots(dataset, n_epochs=args.pypots_epochs)
        
        # 训练LSTM
        if not args.pypots_only:
            lstm_results = train_lstm(dataset, n_epochs=args.lstm_epochs, 
                                     hidden_units=args.lstm_units)
        
        # 比较模型
        if pypots_results and lstm_results:
            comparison = compare_models(pypots_results, lstm_results, dataset)
        
        end_time = datetime.now()
        duration = end_time - start_time
        
        print("\n" + "=" * 80)
        print("所有训练完成！")
        print("=" * 80)
        print(f"开始时间: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"结束时间: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"总耗时: {duration}")
        print(f"\n结果文件保存在: {RESULTS_DIR}")
        print(f"可视化图表保存在: {PLOTS_DIR}")
        print(f"模型文件保存在: {MODELS_DIR}")
        print("=" * 80)
        
    except Exception as e:
        print(f"\n错误: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

