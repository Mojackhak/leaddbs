# HF-only 3m 直接 Voxel-Level 模型

## 研究问题

哪些高频刺激 territory 内的 voxel，其 HF-only 暴露与更好的 3 个月 HF-only 临床结局相关？

这是一个局部刺激 sweet spot 模型。原 STN-only 阶段在这里解释为 HF-only DBS territory，而不是解剖学 STN-only 模型。STN/SNr mask 只用于 territory 定义、覆盖描述和可视化 overlay，不用于把模型效应硬分给某一个核团。


频率定义固定为：

```text
HF  = high-frequency stimulation component, frequency_Hz >= 100
ULF = ultra-low-frequency stimulation component, frequency_Hz <= 50
```

## 终点

主终点：

```text
Y_HF3m = raw HF-only 3-month clinical score
```

主协变量：

```text
Y_Preop = raw preoperative clinical score
```

对于低分更好的量表，系数需要 sign flip 后构成 benefit-oriented map。对于 SE-ADL，正系数本身表示获益。

首轮实现的量表范围（后续再扩展）：

```text
scales = { MDS-UPDRS III, MDS-UPDRS III axial }   # 均为低分更好
```

每个量表独立拟合并各自导出 map。两个首轮量表都属低分更好，故 `M_HF(v) = -theta_HF(v)`。

## 输入

- 每侧 HF-only 连续 E-field，直接取自 Lead-DBS Horn/SimBio FEM 在 `3m/STN`（STN-only 3 个月）条件下的输出：

  ```text
  stimulations/MNI152NLin2009bAsym/<stimlabel>_3m_STN_continuous/sub-<Subject>_sim-efield_model-simbio_hemi-{L,R}.nii
  ```

  使用原始 `sim-efield` 变体（不用 `sim-efieldgauss`）。`<stimlabel>` 前缀每个受试者不同（如 `stnsnr_vta_SNr026`），用 `*_3m_STN_*` 在该受试者 MNI stimulations 目录下 glob 定位文件夹。E-field 保持 Lead-DBS 原始单位 `V/m`。无需重新导出，这些图已在磁盘上。
- 交替刺激的 `3m/STN`（无 `_continuous` 文件夹、只有 `_3m_STN_alt_*` 子程序）：对同一侧多个子程序的连续 E-field 做逐体素取最大，合成该侧单一 HF-only 场。不要把交替子程序当作同时双阴极刺激。
- territory 掩膜（已 2mm 扩张的 STN∪SNr，每侧一个）：

  ```text
  templates/space/MNI152NLin2009bAsym/atlases/STNSNr-connected regions/{rh,lh}/STNSNrplus.nii.gz
  ```

  manifest：`dilate_mm(2 mm, union(STN>0.05, SNr>0.05))`，在 MNI152NLin2009bAsym 参考网格上。不再额外扩张。
- 左→右同源形变（Lead-DBS 内置非对称非线性翻转）：

  ```text
  helpers/ea_flip_lr_nonlinear.m
  templates/space/MNI152NLin2009bAsym/fliplr/{Composite,InverseComposite}.nii.gz
  ```

- 来自 `subject_effect_origin.xlsx` 的原始临床分数（上游源 `scale_raw/scale_subject.xlsx`）。临床行与影像以受试者姓名（如 `ChenLingHua`）连接；确切 sheet/列名在实现时读工作簿核对。

STN/SNr 解剖 mask 仅保留用于 overlay 和 coverage summary。

## 特征构建

territory 定义为数据驱动的覆盖包络与解剖掩膜求交：

```text
Omega_HF = { v : Coverage(v) >= 5 }  与  STNSNrplus（右侧标准网格）求交
```

模型不把 overlap 或 border-zone voxel 强行分成 STN 或 SNr。

### 双侧同源 voxel 暴露

直接 voxel-level 模型需要同源 voxel 坐标系。以右侧 `STNSNrplus` 网格为标准网格。对每个右侧标准 voxel center `c_R(v)`，用左到右形变的逆变换给出左侧同源连续坐标：

```text
c_L(v) = phi_inverse_L_to_R(c_R(v))
```

在该连续位置对左侧 E-field 做三线性插值采样。实现上用 `ea_flip_lr_nonlinear`（借助 `fliplr/Composite.nii.gz`）把左侧 E-field 翻到右侧空间，直接得到标准网格上的 `E_L_to_R_i(v)`。患者层面双侧暴露为：

```text
X_HF_only_i(v) = ( E_R_i(c_R(v)) + E_L_to_R_i(v) ) / 2
```

这样每患者每同源 voxel 只有一个值（最多 `n = 16`），避免左右伪重复。

paired 分析掩膜只保留逆变形后左侧同源位置仍落在左侧 territory 掩膜内的右侧标准 voxel：

```text
P_left_to_R(v) = interp_linear(1_left_STNSNrplus, c_L(v))
Omega_pair = { v in Omega_R : P_left_to_R(v) > 0.5 }
```

以 `> 0.7` 作为更保守的敏感性阈值。

### 覆盖

模型拟合使用 coverage mask 内的连续暴露值。active-voxel 阈值只用于 coverage/QC：

```text
tau = 200 V/m            # 等价于 0.2 V/mm
Coverage(v) = sum_i 1[X_HF_only_i(v) > tau]
```

在 `Coverage(v) >= 5` 处拟合，并以 `tau = 180` 和 `220 V/m` 做阈值敏感性分析。coverage 掩膜、paired 掩膜、voxel map 与 score 都在每个交叉验证 training fold 内计算；留出患者不参与 fold-specific 掩膜或 map 定义。

## 统计模型

对每个 voxel `v`，使用残差化 ANCOVA（OLS）估计量。先把 `Y_HF3m` 与 `X_HF_only(v)` 对 `Y_Preop` 残差化，再取残差化暴露对残差化结局的 OLS 系数：

```text
Y_HF3m_i = alpha_v
         + theta_HF(v) * X_HF_only_i(v)
         + beta_v      * Y_Preop_i
         + error_i,v
```

不对 `X_HF_only(v)` 或 `M_HF(v)` 做标准化。

Benefit-oriented map：

```text
M_HF(v) = -theta_HF(v)   for lower-is-better scales
M_HF(v) =  theta_HF(v)   for SE-ADL
```

患者层面 HF sweet-spot score（`lambda = 0`）：

```text
HFScore_i =
  sum_v X_HF_only_i(v) * M_HF(v)
  / sum_v X_HF_only_i(v)
```

最终预测模型：

```text
Y_HF3m_i = alpha
         + delta * HFScore_i
         + beta  * Y_Preop_i
         + error_i
```

对低分更好的量表，期望方向为 `delta < 0`（sweet-spot overlap 越高，术后分数越低）。

缺失处理：某量表缺 `Y_HF3m`，或缺某一侧 E-field，只在该量表内剔除该患者（每量表 `n` 可能小于 16）。

## 验证

- 使用 fully nested leave-one-patient-out cross-validation。
- 在每个 training fold 内定义 coverage mask、拟合 voxel map、计算 HF score。
- 与 covariate-only model `Y_HF3m ~ Y_Preop` 比较。
- 报告 LOOCV Pearson `r`、Spearman `rho`、MAE、RMSE、`Q2` 和 permutation P value。
- 显著性检验使用 patient-level Freedman-Lane permutation，`B = 1000`，随机种子 `42`；主置换统计量为 LOOCV Pearson `r`。

## 下游可视化

输出根目录（与 VTA-coverage 队列输出并列），每量表一个子目录：

```text
/Volumes/VAL/STNSNr/summary/direct_voxel/hf/<scale>/
```

导出：

```text
direct_voxel_HF_coverage.nii.gz
direct_voxel_HF_coef.nii.gz
direct_voxel_HF_sweet_sour.nii.gz
direct_voxel_HF_stability.nii.gz
direct_voxel_HF_bootstrap_se.nii.gz
direct_voxel_HF_scores.csv
direct_voxel_HF_loocv_predictions.csv
direct_voxel_HF_permutation_summary.csv
direct_voxel_HF_mapping_qc.json
```

map 定义：

- `direct_voxel_HF_coef.nii.gz` 存原始 `theta_HF(v)`；不做逐体素 FDR。
- `direct_voxel_HF_stability.nii.gz` 是 LOOCV 各折中 `theta_HF(v) > 0` 的折比例。
- `direct_voxel_HF_bootstrap_se.nii.gz` 是患者级 bootstrap 重采样（`B = 1000`，种子 `42`）下 `theta_HF(v)` 的标准差。

平滑为可选且轻度（`FWHM = 1-2 mm`），在系数估计之后施加并重新回掩膜到 territory。未平滑图作为主输出，平滑图作为敏感性输出。

使用以 0 为中心的 diverging color scale 显示 HF sweet/sour map。低覆盖 voxel（低于 fold 覆盖规则）显示为透明或灰色。STN 与 SNr 边界只作为 overlay。

## 解释边界

该模型估计 HF-only 局部刺激暴露与 3 个月结局的关联。它应解释为 STN/SNr stimulation territory 内的 HF efficacy heatmap，而不是纯解剖 STN map，也不是 voxel-wise 因果证据。
