# STN 3m Normative Connectome Seed-Target 模型

## 研究问题

公共 normative connectome 中哪些 STN-connected targets 与更好的 STN-only 3 个月临床结局相关？

这是一个 seed-target / fiber-derived target-level 模型。单条 streamline 用于构建 target connectivity features 和可视化输出；主预测变量不是 top-correlated individual fibers。

## 终点

主终点：

```text
Y_STN3m = raw STN-only 3-month clinical score
```

主协变量：

```text
Y_Preop = raw preoperative clinical score
```

## 输入

- 公共 Lead-DBS structural connectomes：dTOR-985 Full、MGH-USC HCP 32、PPMI 85。
- 来自 `STN-connected regions` 的 STN seed 和 target masks。
- 来自 seed-target atlas registry 的 STN targets，包括 M1、SMA、preSMA、premotor、GPe、GPi、DLPFC、ACC、OFC、vmPFC 和 SNr。
- STN-only 3 个月刺激暴露图或 e-field-like proxy maps。
- 来自 `subject_effect_origin.xlsx` 的原始临床分数。

## 特征构建

对患者 `i`、侧别 `h` 和 target `k`，定义同侧 normative streamlines：

```text
G_norm_STN(k,h) = streamlines connecting same-side STN seed to target P(k,h)
```

Streamline exposure：

```text
A_norm_i,h,j = max exposure along streamline j
```

Target-level side-specific connectivity：

```text
C_norm_STN(i,h,k) =
  sum_j A_norm_i,h,j / (number of streamlines in G_norm_STN(k,h) + lambda)
```

患者层面的双侧特征：

```text
C_norm_STN_bilat(i,k) =
  (C_norm_STN(i,L,k) + C_norm_STN(i,R,k)) / 2
```

主分析中同一 target 内 streamlines 采用 equal weights。

## 统计模型

对每个 target `k`：

```text
Y_STN3m_i = alpha_k
          + theta_STN,k * Z(C_norm_STN_bilat(i,k))
          + beta_k      * Z(Y_Preop_i)
          + error_i,k
```

Benefit-oriented target weight：

```text
w_STN,k = -theta_STN,k   for lower-is-better scales
w_STN,k =  theta_STN,k   for SE-ADL
```

在 training fold 内选择 targets：

```text
S_STN = top sweet and sour STN targets
```

患者层面的 normative STN target score：

```text
STNTargetScore_norm_i =
  sum_{k in S_STN} w_STN,k * Z(C_norm_STN_bilat(i,k))
  / sum_{k in S_STN} abs(w_STN,k)
```

最终预测模型：

```text
Y_STN3m_i = alpha
          + delta * STNTargetScore_norm_i
          + beta  * Y_Preop_i
          + error_i
```

## 验证

- 使用 fully nested leave-one-patient-out cross-validation。
- 每个 fold 内只用 training patients 估计 target weights、选择 targets、标准化 features，并拟合最终模型。
- 与 covariate-only prediction 比较：`Y_STN3m ~ Y_Preop`。
- 报告 cross-validated Pearson `r`、Spearman `rho`、MAE、RMSE、`Q2`、target selection stability 和 permutation P value。
- 先用 PPMI 作为 smoke test，再运行 MGH，最后用 chunked access 运行 dTOR。

## 下游可视化

导出：

```text
target weights and target ranking tables
STNTargetScore_norm.csv
selected-target fiber subsets
target-weighted streamline density maps
STN_lh_coverage/sweet/sour/net/stability.nii.gz
STN_rh_coverage/sweet/sour/net/stability.nii.gz
```

STN voxel maps 是通过 normative streamline density 将 `w_STN,k` 反投影到 STN seed 得到的 target-derived seed voxel maps。它们不是直接 voxel-wise discovery maps。

## 解释边界

该模型是 network-informed normative connectome 模型。它识别与临床获益相关的 STN-connected targets，并提供 fiber-derived 解剖解释。它不能证明单条 fiber 的因果性，也不应被描述为以 top-correlated fibers 为主分析的模型。
