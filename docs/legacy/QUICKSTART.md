# 快速开始指南

## 项目已转换为Python格式

所有Jupyter Notebook已转换为Python脚本，并添加了LSTM神经网络训练功能。

## 文件结构

```
pipotsenvironmentallaw/
├── data_preprocessing.py      # 数据预处理模块
├── data_imputation.py         # 数据插补模块（PyPOTS + LSTM）
├── legal_supervision.py       # 法律监督模块
├── train_all_models.py        # 统一训练脚本（推荐使用）
├── requirements.txt           # 依赖包列表
└── README.md                  # 项目说明
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

**注意**: 如果使用LSTM，需要安装TensorFlow：
```bash
pip install tensorflow>=2.10.0
```

### 2. 训练所有模型（推荐）

这是最简单的方式，会自动训练PyPOTS和LSTM两个模型：

```bash
python train_all_models.py
```

**自定义参数**:
```bash
# 设置训练轮数
python train_all_models.py --pypots-epochs 20 --lstm-epochs 100

# 仅训练PyPOTS
python train_all_models.py --pypots-only

# 仅训练LSTM
python train_all_models.py --lstm-only --lstm-epochs 50 --lstm-units 128
```

### 3. 单独使用各个模块

#### 数据预处理
```bash
python data_preprocessing.py
```

#### 数据插补（包含PyPOTS和LSTM）
```bash
python data_imputation.py
```

#### 法律监督检查
```bash
python legal_supervision.py
```

## 模型说明

### PyPOTS SAITS模型
- **类型**: 基于自注意力机制的时间序列插补模型
- **特点**: 专门为时间序列缺失值插补设计
- **训练时间**: 较快（约10-20分钟）
- **默认轮数**: 10 epochs

### LSTM神经网络模型
- **类型**: 长短期记忆神经网络
- **特点**: 深度学习模型，适合复杂时间序列模式
- **训练时间**: 较慢（约30-60分钟，取决于数据量）
- **默认轮数**: 50 epochs
- **架构**: 双层LSTM + Dropout + Dense

## 输出文件

训练完成后，会在以下目录生成结果：

```
results/
├── imputed/
│   ├── pypots_train_imputed.csv
│   ├── pypots_val_imputed.csv
│   ├── pypots_test_imputed.csv
│   ├── pypots_train_imputed_metrics.csv
│   ├── lstm_train_imputed.csv
│   ├── lstm_val_imputed.csv
│   ├── lstm_test_imputed.csv
│   └── lstm_train_imputed_metrics.csv
├── plots/
│   ├── pypots_*.png          # PyPOTS可视化图表
│   └── lstm_*.png            # LSTM可视化图表
└── models/
    └── lstm_imputer.h5       # 保存的LSTM模型
```

## 模型对比

训练完成后，`train_all_models.py`会自动对比两个模型的性能：

- **MSE** (均方误差): 越小越好
- **MAE** (平均绝对误差): 越小越好
- **RMSE** (均方根误差): 越小越好

## 常见问题

### 1. TensorFlow安装问题

如果遇到TensorFlow安装问题，可以尝试：
```bash
pip install tensorflow-cpu  # CPU版本
# 或
pip install tensorflow-gpu  # GPU版本（需要CUDA）
```

### 2. 内存不足

如果数据量很大导致内存不足：
- 减少batch_size（在代码中修改）
- 减少训练轮数
- 使用更少的站点数据

### 3. 训练时间过长

- PyPOTS: 可以设置较少的epochs（如5-10）
- LSTM: 可以减少hidden_units或epochs

## 下一步

训练完成后，可以：
1. 查看可视化图表（`results/plots/`）
2. 查看评估指标（`results/imputed/*_metrics.csv`）
3. 运行法律监督检查（`python legal_supervision.py`）

## 技术支持

如有问题，请查看：
- `README.md`: 详细项目说明
- `项目结构说明.md`: 完整项目结构
- 代码注释: 每个函数都有详细说明


