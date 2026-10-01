"""
数据插补模块 - 支持PyPOTS SAITS和LSTM神经网络
"""

import os
import pandas as pd
import numpy as np
from datetime import datetime
from sklearn.preprocessing import StandardScaler, LabelEncoder
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
RESULTS_DIR = os.path.join(BASE_DIR, "results", "imputed")
PLOTS_DIR = os.path.join(BASE_DIR, "results", "plots")
MODELS_DIR = os.path.join(BASE_DIR, "results", "models")
os.makedirs(PLOTS_DIR, exist_ok=True)
os.makedirs(MODELS_DIR, exist_ok=True)


class Visualizer:
    """可视化器"""
    def __init__(self, plots_dir):
        self.plots_dir = plots_dir
        os.makedirs(plots_dir, exist_ok=True)
        
    def plot_data_distribution(self, df, feature_columns, title):
        """绘制数据分布图"""
        plt.figure(figsize=(15, 5))
        for i, col in enumerate(feature_columns, 1):
            plt.subplot(1, 3, i)
            sns.histplot(data=df[col], kde=True)
            plt.title(f'{col}分布')
            plt.xlabel('值')
            plt.ylabel('频次')
        plt.tight_layout()
        plt.savefig(os.path.join(self.plots_dir, f'{title}_distribution.png'))
        plt.close()
        
    def plot_time_series(self, original, imputed, mask, feature_name, station_id):
        """绘制时间序列对比图"""
        plt.figure(figsize=(12, 6))
        time_points = range(len(original))
        
        plt.plot(time_points, original, 'b-', label='原始数据', alpha=0.7)
        missing_points = np.where(mask)[0]
        plt.scatter(missing_points, imputed[missing_points], 
                   color='r', label='插补数据', alpha=0.7)
        
        plt.title(f'站点{station_id} - {feature_name}时间序列插补对比')
        plt.xlabel('时间步')
        plt.ylabel('值')
        plt.legend()
        plt.grid(True, alpha=0.3)
        plt.savefig(os.path.join(self.plots_dir, 
                                f'timeseries_{feature_name}_station_{station_id}.png'))
        plt.close()
        
    def plot_correlation_matrix(self, df, title):
        """绘制相关性矩阵"""
        plt.figure(figsize=(8, 6))
        sns.heatmap(df.corr(), annot=True, cmap='coolwarm', center=0)
        plt.title(f'{title}特征相关性矩阵')
        plt.savefig(os.path.join(self.plots_dir, f'{title}_correlation.png'))
        plt.close()
        
    def plot_boxplot(self, df, feature_columns, title):
        """绘制箱线图"""
        plt.figure(figsize=(12, 6))
        df[feature_columns].boxplot()
        plt.title(f'{title}箱线图')
        plt.xticks(rotation=45)
        plt.ylabel('值')
        plt.tight_layout()
        plt.savefig(os.path.join(self.plots_dir, f'{title}_boxplot.png'))
        plt.close()
        
    def plot_imputation_comparison(self, original_data, imputed_data, mask, 
                                 feature_columns, station_ids):
        """绘制插补效果对比图"""
        for station_id in station_ids[:3]:
            for feature_idx, feature_name in enumerate(feature_columns):
                original = original_data[station_id, :, feature_idx]
                imputed = imputed_data[station_id, :, feature_idx]
                station_mask = mask[station_id, :, feature_idx]
                self.plot_time_series(original, imputed, station_mask, 
                                    feature_name, station_id)
    
    def plot_metrics_comparison(self, metrics_dict, title):
        """绘制评估指标对比图"""
        plt.figure(figsize=(10, 6))
        metrics = pd.DataFrame(metrics_dict)
        metrics.plot(kind='bar')
        plt.title(f'{title}评估指标对比')
        plt.xlabel('指标类型')
        plt.ylabel('值')
        plt.legend(title='数据集')
        plt.tight_layout()
        plt.savefig(os.path.join(self.plots_dir, f'{title}_metrics_comparison.png'))
        plt.close()


class ResultsSaver:
    """结果保存器"""
    def __init__(self, results_dir, plots_dir):
        self.results_dir = results_dir
        self.visualizer = Visualizer(plots_dir)
        os.makedirs(results_dir, exist_ok=True)
    
    def calculate_metrics(self, original_data, imputed_data, mask, scaler, n_features, masked_positions=None):
        """计算评估指标（在原始尺度上）
        
        Args:
            original_data: 原始完整数据（train_X_ori）
            imputed_data: 插补后的数据
            mask: 当前数据的mask（train_missing_mask）
            scaler: 标准化器
            n_features: 特征数量
            masked_positions: 被随机mask的位置（用于评估，只在训练集有）
        """
        # 将数据重塑为2D以便逆标准化
        original_flat = original_data.reshape(-1, n_features)
        imputed_flat = imputed_data.reshape(-1, n_features)
        mask_flat = mask.reshape(-1, n_features)
        
        # 逆标准化到原始尺度
        if hasattr(scaler, 'inverse_transform'):
            original_orig_scale = scaler.inverse_transform(original_flat)
            imputed_orig_scale = scaler.inverse_transform(imputed_flat)
        elif hasattr(scaler, 'mean_') and hasattr(scaler, 'scale_'):
            # 手动逆标准化
            original_orig_scale = original_flat.copy()
            imputed_orig_scale = imputed_flat.copy()
            for i in range(n_features):
                if len(scaler.mean_.shape) == 0:  # 单特征scaler
                    original_orig_scale[:, i] = original_flat[:, i] * scaler.scale_ + scaler.mean_
                    imputed_orig_scale[:, i] = imputed_flat[:, i] * scaler.scale_ + scaler.mean_
                else:  # 多特征scaler
                    original_orig_scale[:, i] = original_flat[:, i] * scaler.scale_[i] + scaler.mean_[i]
                    imputed_orig_scale[:, i] = imputed_flat[:, i] * scaler.scale_[i] + scaler.mean_[i]
        else:
            # 如果没有scaler信息，直接使用原始数据
            original_orig_scale = original_flat
            imputed_orig_scale = imputed_flat
        
        # 计算评估指标
        # 如果有masked_positions，计算被mask位置的差异
        # 否则计算所有有值位置的差异（用于验证集和测试集）
        orig_values = []
        imputed_values = []
        
        if masked_positions is not None:
            # 使用被mask的位置进行评估
            masked_flat = masked_positions.reshape(-1, n_features)
            for i in range(n_features):
                feature_masked = masked_flat[:, i]
                if feature_masked.sum() > 0:
                    orig_feat = original_orig_scale[feature_masked, i]
                    imputed_feat = imputed_orig_scale[feature_masked, i]
                    
                    # 过滤NaN值
                    valid_idx = ~(np.isnan(orig_feat) | np.isnan(imputed_feat))
                    if valid_idx.sum() > 0:
                        orig_values.extend(orig_feat[valid_idx].tolist())
                        imputed_values.extend(imputed_feat[valid_idx].tolist())
        else:
            # 使用所有有值位置（验证集/测试集）
            for i in range(n_features):
                feature_mask = mask_flat[:, i]
                if feature_mask.sum() > 0:
                    orig_feat = original_orig_scale[feature_mask, i]
                    imputed_feat = imputed_orig_scale[feature_mask, i]
                    
                    # 过滤NaN值
                    valid_idx = ~(np.isnan(orig_feat) | np.isnan(imputed_feat))
                    if valid_idx.sum() > 0:
                        orig_values.extend(orig_feat[valid_idx].tolist())
                        imputed_values.extend(imputed_feat[valid_idx].tolist())
        
        if len(orig_values) > 0:
            orig_values = np.array(orig_values)
            imputed_values = np.array(imputed_values)
            
            mse = np.mean((orig_values - imputed_values)**2)
            mae = np.mean(np.abs(orig_values - imputed_values))
            rmse = np.sqrt(mse)
        else:
            mse = mae = rmse = 0.0
        
        return {
            'MSE': float(mse),
            'MAE': float(mae),
            'RMSE': float(rmse)
        }
    
    def save_results(self, imputed_data, dataset, model_name='pypots'):
        """保存插补结果和评估指标"""
        print("保存结果和生成可视化...")
        
        metrics_collection = {}
        
        for name, data in imputed_data.items():
            # 保存基本结果
            reshaped_data = data.reshape(-1, dataset['n_features'])
            original_scale_data = dataset['scaler'].inverse_transform(reshaped_data)
            
            df = pd.DataFrame(
                original_scale_data, 
                columns=dataset['feature_columns']
            )
            
            output_path = os.path.join(self.results_dir, f"{model_name}_{name}.csv")
            df.to_csv(output_path, index=False)
            
            # 生成可视化
            self.visualizer.plot_data_distribution(
                df, dataset['feature_columns'], 
                f'{model_name}_{name}_after_imputation'
            )
            self.visualizer.plot_correlation_matrix(df, f'{model_name}_{name}')
            self.visualizer.plot_boxplot(df, dataset['feature_columns'], f'{model_name}_{name}')
            
            # 计算和保存评估指标
            if name != 'test_imputed':
                set_type = name.split('_')[0]
                original_data = dataset[f'{set_type}_X_ori']
                mask = dataset['mask'][set_type]
                
                # 获取被mask的位置（仅训练集有）
                masked_positions = dataset.get(f'{set_type}_masked_positions', None)
                metrics = self.calculate_metrics(
                    original_data, data, mask, 
                    dataset['scaler'], 
                    dataset['n_features'],
                    masked_positions=masked_positions
                )
                metrics_collection[set_type] = metrics
                
                metrics_df = pd.DataFrame(list(metrics.items()), 
                                        columns=['metric', 'value'])
                metrics_path = os.path.join(self.results_dir, f"{model_name}_{name}_metrics.csv")
                metrics_df.to_csv(metrics_path, index=False, float_format='%.6f')
                print(f"评估指标已保存: {metrics_path}")
                print(f"  MSE: {metrics['MSE']:.6f}")
                print(f"  MAE: {metrics['MAE']:.6f}")
                print(f"  RMSE: {metrics['RMSE']:.6f}")
                
                # 生成插补效果对比图
                self.visualizer.plot_imputation_comparison(
                    original_data, data, mask,
                    dataset['feature_columns'],
                    range(min(3, len(original_data)))
                )
        
        # 生成评估指标对比图
        if metrics_collection:
            self.visualizer.plot_metrics_comparison(
                metrics_collection, f'{model_name}_imputation'
            )


class AirQualityDataProcessor:
    """空气质量数据处理器"""
    def __init__(self):
        self.scaler = StandardScaler()
        self.label_encoder = LabelEncoder()
        
    def process_daily_data(self, file_path):
        """处理单日数据文件"""
        try:
            df = pd.read_csv(file_path)
            feature_cols = ['PM2.5', 'PM10', 'AQI']
            if all(col in df.columns for col in feature_cols):
                processed_data = df[['station_id'] + feature_cols].copy()
                if 'date' in df.columns:
                    processed_data['date'] = df['date'].iloc[0]
                return processed_data
            else:
                print(f"警告: 文件 {file_path} 缺少必要的特征列")
                return None
        except Exception as e:
            print(f"处理文件 {file_path} 时出错: {str(e)}")
            return None
    
    def process_dataset(self, data_list):
        """处理数据集，准备用于插补"""
        try:
            all_data = pd.concat(data_list, ignore_index=True)
            feature_columns = ['PM2.5', 'PM10', 'AQI']
            
            stations = all_data['station_id'].unique()
            n_stations = len(stations)
            n_days = len(data_list)
            n_steps = n_days * 24
            
            X_list = []
            station_ids = []
            
            for station in stations:
                station_data = all_data[all_data['station_id'] == station].copy()
                if 'date' in station_data.columns and 'timestamp' in station_data.columns:
                    station_data = station_data.sort_values(['date', 'timestamp'])
                features = station_data[feature_columns].values
                
                if len(features) < n_steps:
                    padding = np.full((n_steps - len(features), len(feature_columns)), np.nan)
                    features = np.vstack([features, padding])
                elif len(features) > n_steps:
                    features = features[:n_steps]
                
                X_list.append(features)
                station_ids.append(station)
            
            X = np.array(X_list, dtype=np.float32)
            n_features = len(feature_columns)
            mask = ~np.isnan(X)
            
            # 标准化数据
            X_flat = X.reshape(-1, n_features)
            mask_flat = mask.reshape(-1, n_features)
            
            # 为每个特征创建单独的scaler并保存统计信息
            feature_scalers = []
            X_scaled = X_flat.copy()
            
            for i in range(n_features):
                valid_values = X_flat[mask_flat[:, i], i]
                if len(valid_values) > 0:
                    feature_scaler = StandardScaler()
                    feature_scaler.fit(valid_values.reshape(-1, 1))
                    X_scaled[mask_flat[:, i], i] = feature_scaler.transform(
                        valid_values.reshape(-1, 1)
                    ).flatten()
                    feature_scalers.append({
                        'mean': feature_scaler.mean_[0],
                        'scale': feature_scaler.scale_[0]
                    })
                else:
                    feature_scalers.append({'mean': 0.0, 'scale': 1.0})
            
            X_scaled = X_scaled.reshape(n_stations, n_steps, n_features)
            
            # 分割数据集
            train_size = int(0.7 * n_stations)
            val_size = int(0.15 * n_stations)
            
            train_X = X_scaled[:train_size]
            val_X = X_scaled[train_size:train_size + val_size]
            test_X = X_scaled[train_size + val_size:]
            
            train_mask = mask[:train_size]
            val_mask = mask[train_size:train_size + val_size]
            test_mask = mask[train_size + val_size:]
            
            # 创建缺失值用于训练
            train_X_intact = train_X.copy()
            train_X_missing = train_X.copy()
            train_missing_mask = train_mask.copy()
            
            # 随机mask 20%的数据用于训练和评估
            random_mask = np.random.random(train_X.shape) < 0.2
            # 保存被mask的位置（用于后续评估）
            train_masked_positions = random_mask & train_mask
            train_X_missing[train_masked_positions] = np.nan
            train_missing_mask = ~np.isnan(train_X_missing) & train_mask
            
            # 保存scaler用于逆变换（保存每个特征的统计信息）
            class MultiFeatureScaler:
                def __init__(self, feature_scalers):
                    self.feature_scalers = feature_scalers
                    # 为了兼容inverse_transform，创建mean_和scale_数组
                    self.mean_ = np.array([fs['mean'] for fs in feature_scalers])
                    self.scale_ = np.array([fs['scale'] for fs in feature_scalers])
                
                def inverse_transform(self, X):
                    X_inv = X.copy()
                    for i in range(len(self.feature_scalers)):
                        X_inv[:, i] = X[:, i] * self.scale_[i] + self.mean_[i]
                    return X_inv
            
            self.scaler = MultiFeatureScaler(feature_scalers)
            
            return {
                'n_steps': n_steps,
                'n_features': n_features,
                'feature_columns': feature_columns,
                'scaler': self.scaler,
                'train_X': train_X_missing,
                'train_X_ori': train_X_intact,
                'train_masked_positions': train_masked_positions,  # 保存被mask的位置
                'val_X': val_X,
                'val_X_ori': val_X,
                'val_masked_positions': np.zeros_like(val_mask, dtype=bool),  # 验证集不mask
                'test_X': test_X,
                'mask': {
                    'train': train_missing_mask,
                    'val': val_mask,
                    'test': test_mask
                }
            }
        except Exception as e:
            print(f"处理数据集时出错: {str(e)}")
            import traceback
            traceback.print_exc()
            return None


class PyPOTSImputer:
    """PyPOTS SAITS插补器"""
    def __init__(self, n_steps, n_features, n_epochs=10):
        self.n_steps = n_steps
        self.n_features = n_features
        self.n_epochs = n_epochs
        self.model = None
        
    def perform_imputation(self, dataset):
        """执行插补"""
        try:
            from pypots.imputation import SAITS
            
            train_X = dataset['train_X']
            train_mask = dataset['mask']['train']
            
            self.model = SAITS(
                n_steps=self.n_steps,
                n_features=self.n_features,
                n_layers=2,
                d_model=256,
                d_ffn=128,  # 前馈网络维度
                n_heads=4,
                d_k=64,
                d_v=64,
                dropout=0.1,
                epochs=self.n_epochs,
                batch_size=32,
                device='cpu'
            )
            
            print("开始训练PyPOTS SAITS模型...")
            # PyPOTS需要字典格式的数据
            train_set = {
                'X': train_X,
                'missing_mask': ~train_mask  # PyPOTS使用missing_mask（True表示缺失）
            }
            self.model.fit(train_set=train_set)
            
            print("开始执行插补...")
            # 准备插补数据（字典格式）
            train_set_impute = {
                'X': dataset['train_X'],
                'missing_mask': ~dataset['mask']['train']
            }
            val_set_impute = {
                'X': dataset['val_X'],
                'missing_mask': ~dataset['mask']['val']
            }
            test_set_impute = {
                'X': dataset['test_X'],
                'missing_mask': ~dataset['mask']['test']
            }
            
            train_imputed = self.model.impute(train_set_impute)
            val_imputed = self.model.impute(val_set_impute)
            test_imputed = self.model.impute(test_set_impute)
            
            return {
                'train_imputed': train_imputed,
                'val_imputed': val_imputed,
                'test_imputed': test_imputed
            }
        except Exception as e:
            print(f"PyPOTS插补过程中出错: {str(e)}")
            import traceback
            traceback.print_exc()
            return None


class LSTMImputer:
    """LSTM神经网络插补器"""
    def __init__(self, n_steps, n_features, n_epochs=50, hidden_units=128):
        self.n_steps = n_steps
        self.n_features = n_features
        self.n_epochs = n_epochs
        self.hidden_units = hidden_units
        self.model = None
        
    def _build_model(self):
        """构建LSTM模型"""
        try:
            import tensorflow as tf
            from tensorflow import keras
            from tensorflow.keras import layers
            
            model = keras.Sequential([
                layers.Masking(mask_value=0.0, input_shape=(self.n_steps, self.n_features)),
                layers.LSTM(self.hidden_units, return_sequences=True),
                layers.Dropout(0.2),
                layers.LSTM(self.hidden_units // 2, return_sequences=True),
                layers.Dropout(0.2),
                layers.Dense(self.n_features)
            ])
            
            # 注意：损失函数在训练时设置，因为需要使用自定义masked损失
            
            return model
        except ImportError:
            print("错误: 需要安装tensorflow")
            print("请运行: pip install tensorflow")
            return None
    
    def _prepare_data(self, X, mask):
        """准备训练数据"""
        # 将NaN替换为0，mask标记缺失位置
        X_filled = np.nan_to_num(X, nan=0.0)
        # 创建mask矩阵：1表示有值，0表示缺失（用于LSTM的Masking层）
        mask_matrix = mask.astype(float)
        # 对于缺失值，使用0填充，mask为0
        X_filled[~mask] = 0.0
        return X_filled, mask_matrix
    
    def perform_imputation(self, dataset):
        """执行LSTM插补"""
        try:
            import tensorflow as tf
            from tensorflow import keras
            
            print("构建LSTM模型...")
            self.model = self._build_model()
            if self.model is None:
                return None
            
            # 准备训练数据
            train_X, train_mask = self._prepare_data(
                dataset['train_X'], 
                dataset['mask']['train']
            )
            val_X, val_mask = self._prepare_data(
                dataset['val_X'], 
                dataset['mask']['val']
            )
            
            # 训练目标：原始数据（只对有值的位置计算损失）
            # 使用mask来标记哪些位置需要计算损失
            train_y = train_X.copy()
            val_y = val_X.copy()
            
            print("开始训练LSTM模型...")
            print(f"训练数据形状: {train_X.shape}")
            
            # 自定义损失函数：只对有值的位置计算损失
            import tensorflow as tf
            def masked_mse(y_true, y_pred):
                # 创建mask：y_true中非零的位置表示有值
                mask = tf.cast(tf.not_equal(y_true, 0.0), tf.float32)
                # 计算MSE
                mse = tf.square(y_true - y_pred)
                # 只对有值的位置计算损失
                masked_mse = tf.reduce_sum(mse * mask) / (tf.reduce_sum(mask) + 1e-8)
                return masked_mse
            
            # 重新编译模型使用自定义损失
            self.model.compile(
                optimizer=keras.optimizers.Adam(learning_rate=0.001),
                loss=masked_mse,
                metrics=['mae']
            )
            
            # 训练模型
            history = self.model.fit(
                train_X, train_y,
                validation_data=(val_X, val_y),
                epochs=self.n_epochs,
                batch_size=32,
                verbose=1,
                callbacks=[
                    keras.callbacks.EarlyStopping(
                        monitor='val_loss',
                        patience=10,
                        restore_best_weights=True
                    ),
                    keras.callbacks.ReduceLROnPlateau(
                        monitor='val_loss',
                        factor=0.5,
                        patience=5,
                        min_lr=1e-6
                    )
                ]
            )
            
            # 保存模型
            model_path = os.path.join(MODELS_DIR, 'lstm_imputer.h5')
            self.model.save(model_path)
            print(f"模型已保存: {model_path}")
            
            print("开始执行插补...")
            # 对训练集、验证集、测试集进行插补
            train_X_filled, _ = self._prepare_data(
                dataset['train_X'], 
                dataset['mask']['train']
            )
            val_X_filled, _ = self._prepare_data(
                dataset['val_X'], 
                dataset['mask']['val']
            )
            test_X_filled, _ = self._prepare_data(
                dataset['test_X'], 
                dataset['mask']['test']
            )
            
            train_imputed = self.model.predict(train_X_filled, verbose=0)
            val_imputed = self.model.predict(val_X_filled, verbose=0)
            test_imputed = self.model.predict(test_X_filled, verbose=0)
            
            # 将插补值合并到原始数据中
            # 对于有值的位置，使用原始值；对于缺失位置，使用插补值
            train_mask_bool = dataset['mask']['train']
            val_mask_bool = dataset['mask']['val']
            test_mask_bool = dataset['mask']['test']
            
            # 获取原始数据（NaN替换为0）
            train_orig = np.nan_to_num(dataset['train_X'], nan=0.0)
            val_orig = np.nan_to_num(dataset['val_X'], nan=0.0)
            test_orig = np.nan_to_num(dataset['test_X'], nan=0.0)
            
            # 合并：有值的位置用原始值，缺失位置用插补值
            train_result = np.where(train_mask_bool, train_orig, train_imputed)
            val_result = np.where(val_mask_bool, val_orig, val_imputed)
            test_result = np.where(test_mask_bool, test_orig, test_imputed)
            
            return {
                'train_imputed': train_result,
                'val_imputed': val_result,
                'test_imputed': test_result
            }
        except ImportError:
            print("错误: 需要安装tensorflow")
            return None
        except Exception as e:
            print(f"LSTM插补过程中出错: {str(e)}")
            import traceback
            traceback.print_exc()
            return None


def main():
    """主函数"""
    try:
        print("=" * 80)
        print("开始空气质量数据时间序列插补（PyPOTS + LSTM）")
        print("=" * 80)
        
        os.makedirs(PLOTS_DIR, exist_ok=True)
        
        # 创建处理器实例
        processor = AirQualityDataProcessor()
        
        # 获取particulate数据文件
        particulate_files = [f for f in os.listdir(DATA_DIR) 
                           if f.endswith('_particulate.csv')]
        print(f"找到 {len(particulate_files)} 个particulate数据文件")
        
        # 处理particulate数据
        particulate_data = []
        for file_name in particulate_files:
            file_path = os.path.join(DATA_DIR, file_name)
            df = processor.process_daily_data(file_path)
            if df is not None:
                particulate_data.append(df)
        
        if not particulate_data:
            raise ValueError("未找到有效的particulate数据文件！")
        
        # 处理数据集
        print("\n处理数据集...")
        dataset = processor.process_dataset(particulate_data)
        
        if dataset is None:
            print("数据处理失败")
            return
        
        print(f"数据集形状: {dataset['train_X'].shape}")
        
        # 1. PyPOTS SAITS插补
        print("\n" + "=" * 80)
        print("开始PyPOTS SAITS插补")
        print("=" * 80)
        pypots_imputer = PyPOTSImputer(
            n_steps=dataset['n_steps'],
            n_features=dataset['n_features'],
            n_epochs=10
        )
        
        pypots_results = pypots_imputer.perform_imputation(dataset)
        if pypots_results:
            saver = ResultsSaver(RESULTS_DIR, PLOTS_DIR)
            saver.save_results(pypots_results, dataset, model_name='pypots')
            print("PyPOTS插补完成！")
        
        # 2. LSTM神经网络插补
        print("\n" + "=" * 80)
        print("开始LSTM神经网络插补")
        print("=" * 80)
        lstm_imputer = LSTMImputer(
            n_steps=dataset['n_steps'],
            n_features=dataset['n_features'],
            n_epochs=50,
            hidden_units=128
        )
        
        lstm_results = lstm_imputer.perform_imputation(dataset)
        if lstm_results:
            saver = ResultsSaver(RESULTS_DIR, PLOTS_DIR)
            saver.save_results(lstm_results, dataset, model_name='lstm')
            print("LSTM插补完成！")
        
        print("\n" + "=" * 80)
        print("所有处理完成！")
        print(f"可视化结果保存在: {PLOTS_DIR}")
        print(f"模型保存在: {MODELS_DIR}")
        print("=" * 80)
        
    except Exception as e:
        print(f"错误: {str(e)}")
        import traceback
        traceback.print_exc()
        raise


if __name__ == "__main__":
    main()

