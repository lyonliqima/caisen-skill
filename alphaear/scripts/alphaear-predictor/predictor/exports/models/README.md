# Kronos 新闻感知投影层权重（.pt）获取说明

本目录存放 alphaear-predictor 的训练后权重文件（`kronos_news_v1_*.pt`，约 1.2MB）。
**权重为二进制大文件，已从 git 版本控制中移出**（见仓库根 `.gitignore`），克隆本仓库后此目录默认为空（仅有本说明）。

## 获取方式（任选其一）

1. **从源机器复制**：源机器路径
   `$CAISEN_ROOT/alphaear/scripts/alphaear-predictor/predictor/exports/models/kronos_news_v1_20260101_0015.pt`
   直接拷贝到本目录即可。
2. **重新训练**：权重由归档的 `training.py`（现位于 `_archive/alphaear-dup-utils-predictor/from-alphaear-predictor/training.py`）训练产出，
   训练完成后自动保存为 `kronos_news_v1_<时间戳>.pt`，放入本目录。

## 缺失时的行为

`kronos_predictor.py` 启动时会检查本目录：找不到 `kronos_news_*.pt` 时**自动降级为 Kronos base 基础模型**继续运行
（无新闻感知投影层，预测不含新闻增强），并在日志给出警告与本 README 路径。功能可用，精度打折。

## 安全约定

- 仅加载文件名匹配 `kronos_news_*.pt` 前缀的文件（防供应链投毒）。
- 优先 `torch.load(..., weights_only=True)` 安全加载（PyTorch 1.13+）。
