# 四模型执行方案（Codex + 子代理编排）

> 用途：本文件是 `/goal` 的方案文档，作为 codex 主编排器与子代理执行以下四个 model 任务的“北极星”与工程路线图。
> 权威规范：以 `model_summaries/` 下四份英文 `.md` 为唯一可执行规范（`_zh` 为镜像，冲突时以英文为准）。本方案只负责**跨模型编排、环境落地、护栏与排期**，不重复各规范内部细节。
> 建立日期：2026-07-04。工作区：codex worktree `a409`（`/Users/mojackhu/.codex/worktrees/a409/leaddbs`）。

---

## 0. 一句话目标（可直接粘贴进 /goal）

> 在 n=16 的 STN/SNr DBS 队列上，用 MATLAB/Lead-DBS 做电场与纤维建模的影像域预处理、用 Python（conda `leaddbs`）做统计后处理，按各自 `model_summaries` 规范中的 Round 门控，交付四个刺激-疗效关联模型（HF 直接体素、HF 归一化连接组纤维、HF 校正后的 ULF-only 加载增益的体素与纤维模型），每个模型都以**先验证主分支 LOOCV 增量信号、再投入敏感性/展示层**为原则，全流程种子固定 42、可复现、带 manifest，并遵守各规范的精确等价（no-shortcut）契约。

---

## 1. 范围：四个模型

| 代号 | 规范文件 | 类型 | 主 tau | 主预测量 / 分数 | 依赖 |
|---|---|---|---|---|---|
| **A** | `hf_3m_direct_voxel_model.md` | 直接体素 sweet-spot | 200 V/m（180/220 敏感性） | `HFScore_mean_main`（partial Spearman） | 无（基础） |
| **B** | `hf_3m_normative_connectome_fiber_model.md` | 归一化连接组纤维过滤 | 800 V/m（1500 敏感性） | `NetFiberScore`；PPMI/MGH/dTOR；OSS-DBS 敏感性 | 无（基础） |
| **C** | `ulf_addon_gain_direct_voxel_model.md` | ULF-only 加载增益·体素 | 200 V/m（180/220 = 曝光定义敏感性） | `ULFScore_mean_main`，协变量含 `DeltaHFScore` | **锁定的 A**（体素 DeltaHFScore） |
| **D** | `ulf_addon_gain_normative_connectome_fiber_model.md` | ULF-only 加载增益·纤维 | 800 V/m（1500 = 曝光定义敏感性） | `NetULFFiberScore`，协变量含 `DeltaHFScore` | **锁定的 B**（纤维 DeltaHFScore） |

**范围外（本次不做）**：`*_individualized_dwi_seed_target_model.md` 两个个体化 DWI 种子-靶点模型；`OLS ANCOVA` 补充估计量（各规范均标注“documented only, not run”）；5/7/10-fold CV 等仅文档化项。`Coverage>=6/8` 仍不属于 HF direct-voxel primary mainline，但 A-model post-hoc tau/coverage scan 可以把它作为 exploratory threshold-optimization branch 评估。

---

## 2. 依赖关系与执行顺序

```
        ┌─────────────┐        ┌─────────────┐
        │  A: HF 体素  │        │  B: HF 纤维  │     ← 两者可并行
        └──────┬──────┘        └──────┬──────┘
               │ lock (tau200/         │ lock (dTOR peak_efield_
               │ partial_spearman)     │ tau800_primary)
               ▼                       ▼
        ┌─────────────┐        ┌─────────────┐
        │ C: ULF 体素  │        │ D: ULF 纤维  │     ← A/B 锁定后可并行
        │ 用 A 的      │        │ 用 B 的      │
        │ DeltaHFScore │        │ DeltaHFScore │
        └─────────────┘        └─────────────┘
```

- **A ∥ B** 并行推进（不同预处理、不同 tau、共享统计内核）。
- **C 仅在 A 锁定后**才进入正式分析；**D 仅在 B 锁定后**。若被依赖的 HF 模型 QC 失败/退化，则对应 ULF 模型只能作为 exploratory，且 `DeltaHFScore` 标注为 unstable generated covariate（见各 ULF 规范 “Locked HF Prerequisite”）。
- 连接组匹配（D）：`ULF/PPMI` 用 `HF/PPMI` 的 DeltaHFScore，`ULF/MGH` 用 `HF/MGH`，`ULF/dTOR` 用 `HF/dTOR`；跨连接组共享只能作为 `shared_dTOR_HF_adjustment_sensitivity`。
- **B 的状态汇总：** gate/status 汇总必须分别报告 HF normative fiber 的 `PPMI`、`MGH`、`dTOR` observed 分支；只有 PPMI 一行不足以证明模型 B 已完成 observed connectome 序列。

---

## 3. 环境与数据（已核验）

**计算环境**
- conda base：`/opt/anaconda3`（注意：非交互 shell 里 `conda` 不在 PATH）。规范执行前先 `source /opt/anaconda3/etc/profile.d/conda.sh`，或统一用绝对路径 `/opt/anaconda3/bin/conda run -n leaddbs ...`。
- `leaddbs` env ✓：Python 统计后处理（LOOCV / permutation / bootstrap / jitter / NIfTI 输出）。
- `ossdbsv2` env ✓：仅 B、D 的 OSS-DBS activation 敏感性分支使用。
- MATLAB + Lead-DBS：影像域预处理（**Round 0 需核验版本与 `ea_flip_lr_nonlinear` 可调用**）。
- BLAS 线程钉死：Python 侧 import numpy/scipy 前导出 `OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1`，用 worker 级并行。
- 默认资源：MATLAB workers 8；Python jobs 14；随机种子 42。MATLAB 相与 Python 相**分阶段串行**，避免 CPU 超订。

**数据（已核验存在）**
- 临床原始分：`/Users/mojackhu/Research/STNSNr/summary/cohort/subj/subject_effect_origin.xlsx` ✓（按 `ID` 如 `SNr003` join）。该工作簿是从 `/Users/mojackhu/Research/STNSNr/summary/stats/clinic/effect/3m/scale_subject.xlsx` 重建的 raw endpoint 表：`Scale` 存放 28 个临床 feature 名，`Protocol`/`Phase` 存放刺激条件，`Value` 是 raw score。该表不得包含 `Δ...` 派生行；add-on gain/delta endpoint 后续从 raw `STN` 与 raw `STN+SNr` 行现场重建。
- 刺激参数审计：同目录 `followup_stimulation.xlsx`（sheet `Contact Parameters`）✓。
- `/Volumes/VAL` 已挂载 ✓，含 `reference/`（方法学 PDF）、`summary/`（现有 `cohort/ stats/ table/ vta/`）。
- 输出根 `/Volumes/VAL/STNSNr/summary/direct_voxel/` 与 `.../normative_connectome_fiber/` **尚未创建**（全新）。
- stnsnr 下**无既有 `.py`/`.m` 实现**：可执行流水线为绿地开发；`.md` 仅规范。

**外部卷风险**：`/Volumes/VAL` 与 clinical 目录为可卸载卷/受限权限；每个 Round 0 都应重新校验挂载与可读写。

---

## 4. 两相分离架构（所有模型共用）

**Phase 1 — MATLAB/Lead-DBS 预处理（影像域）**
- 发现并可用性校验所需 e-field（raw `sim-efield`，**非** `sim-efieldgauss`，单位 V/m；唯一匹配 subject×side×condition/phase/component）。
- 同侧交替子程序按体素-wise 最大合并；所有左右翻转用 `ea_flip_lr_nonlinear`；采样到右半球 canonical grid（体素）或右-canonical 流线特征（纤维）。
- 写 MAT v7 设计矩阵 + memmap 友好 sidecar（体素-major / fiber-major `.npy`、S{tau}_bool、candidate ijk/xyz、metadata、flip audit）。dTOR 必须 chunked，**禁止**整载 fibers 矩阵。

**Phase 2 — Python 统计后处理（conda `leaddbs`）**
- 读 sidecar → 折内重建 coverage/candidate → partial Spearman 建图 → 分数 → LOOCV → permutation/bootstrap/jitter → CSV/JSON/NIfTI/PDF。
- 单一长驻 Python 入口编排，避免在 tau/fold/perm/boot/jitter 循环里反复 `conda run`。

**Phase OSS —（conda `ossdbsv2`，仅 B/D 纤维）**
- 在 peak-E-field candidate 锁定**之后**计算 activation，不得重定义/增删 candidate 纤维；参数集先 `primary_locked` 写入 manifest。

---

## 5. 共享统计内核：build once, reuse ×4

四个模型共用同一套统计骨架，**先建一次、参数化复用**，是本项目最大的省力点与一致性保证：

- sidecar schema 与 memmap loader（体素-major / fiber-major；dTOR chunk manifest）。
- fold coverage 由**减法**得到：`Coverage_fold_h = Coverage_all - S_tau(·,h)`，held-out 不进入折内 candidate。
- 向量化 rank-residual **partial Spearman kernel**（折内 rank，禁止全样本 rank）。
- **fold-level score operator**（permutation 复用 outcome-independent 部分：`A_h`、`Z_h`）。
- **Freedman-Lane permutation** harness（nuisance 残差置换、plus-one 双侧 p、统计量=LOOCV Spearman rho）。
- **streaming Welford bootstrap**（不落 10000 张图，累计 mean/M2/finite_count）。
- **spatial jitter**（FWHM 2mm，sigma 0.849；平移-only 线性重采样；重建全链）。
- **精确等价回归测试** 框架（brute-force vs optimized，小子集 + B_perm/B_boot=20，seed 42）。
- manifest/QC 写入器（provenance、env 快照 `conda list --explicit` + `pip freeze`、hash、runtime_profile）。
- 展示层：display smoothing FWHM 1/2mm、bilateral homologous 展示图、top-x + stability 展示 mask、PDF QC —— 均仅展示，不回灌统计。

**需按模型参数化的差异点**：预测单元（voxel grid ↔ streamline，dTOR chunk）；tau（200 ↔ 800，及 ULF 中 tau 属曝光定义）；分数定义（`HFScore_mean_main` / `NetFiberScore` / `ULFScore_mean_main` / `NetULFFiberScore`，含 F+/F- top-k 选纤维）；nuisance 协变量（A/B：`Y_base`；C/D：`Y_HF_ref` + `DeltaHFScore`）；ULF 的 HF-overlap 排除与 in-support `DeltaHFScore` 投影；B/D 的 OSS 分支与 FDR/label/density 展示。

---

## 6. Codex + 子代理编排策略

**主编排器（codex main）**：持有依赖图、门控与排期，负责在 A/B 锁定后放行 C/D，负责跨模型一致性（seed、sidecar schema、manifest 规范）。

**建议的子代理分解（bounded、可并行、依赖感知）：**

| 子代理 | 职责 | 依赖 | 可与谁并行 |
|---|---|---|---|
| **S0** 环境/数据就绪 + 骨架 | 核验 conda/MATLAB/VAL/clinical、建输出根、搭仓库骨架与 scale 方向表 | — | 起点 |
| **S1** 共享统计内核 (Python/leaddbs) | 实现 §5 内核 + 等价测试框架 | S0 | S2a, S2b |
| **S2a** MATLAB 体素预处理 | 服务 A、C 的 e-field 采样与 sidecar | S0 | S1, S2b |
| **S2b** MATLAB 纤维预处理 | 服务 B、D；dTOR chunk；OSS sidecar 脚手架 | S0 | S1, S2a |
| **S3** 模型 A 驱动 | 装配 A 的 Round 0→lock，跑主分支 | S1, S2a | S4 |
| **S4** 模型 B 驱动 | 装配 B 的 Round 0→lock（含 PPMI/MGH/dTOR、OSS） | S1, S2b | S3 |
| **S5** 模型 C 驱动 | ULF 体素，消费**锁定的 A** DeltaHFScore | S3(lock), S2a | S6 |
| **S6** 模型 D 驱动 | ULF 纤维，消费**锁定的 B** DeltaHFScore | S4(lock), S2b | S5 |

**子代理纪律（写进每个子代理任务）**：
1. 单一模型/单一阶段边界，返回结构化结果给主进程，由主进程原子写最终 CSV/JSON。
2. **绝不**并发跑 MATLAB 与 Python（CPU 超订）；正式重采样前**必须**先过等价测试。
3. 严格遵守 §8 护栏；每个分支写 manifest 与 QC，未跑分支显式记 `not_run_nonprimary` + reason。
4. 复用共享内核，不各自造轮子；tau/分数/协变量差异通过配置传入。

**并行度**：S1 ∥ S2a ∥ S2b；A ∥ B；C ∥ D（各自 HF lock 后）。OSS（ossdbsv2）与主统计（leaddbs）分阶段，不与 MATLAB 相重叠。

---

## 7. 里程碑路线图（压缩自各规范 Round 0–10）

每个模型独立走下列里程碑；括号内为对应规范 Round。**门控哲学**：主分支必须先证明相对协变量-only 基线有可解释的 LOOCV 增量信号，才投入敏感性/正式重采样/展示；主分支失败时**不**去 tau180/tau220 “调阈值找信号”。

| 里程碑 | 内容 | A | B | C | D |
|---|---|---|---|---|---|
| **M0** 就绪与冻结 | 临床 join、e-field 唯一性、scale 方向、翻转可调用、env manifest、种子 42 | R0 | R0 | R0（+锁定 A） | R0（+锁定 B） |
| **M1** sidecar + 等价测试 | 预处理 sidecar、coverage 缓存、brute-force vs optimized 等价 | R1 | R1 | R1 | R1 |
| **M2** 主分支 observed LOOCV | 主 tau/主 scale，写数值核心输出，延后展示 | R2 | R2–3 | R2(+2b immediate) | R2–3 |
| **M3** smoke 重采样 | 等价 + smoke perm/boot B=1000 + jitter B=100 | R3 | R5 | R3 | R5 |
| **M4** 正式 permutation | Freedman-Lane B=10000（仅主分支/主连接组 dTOR） | R4 | R7 | R4 | R7 |
| **M5** 正式 bootstrap | subject-level B=10000，streaming SE | R5 | R7 | R5 | R7 |
| **M6** 正式 jitter | FWHM 2mm B=1000 | R6 | R9 | R6 | R8 |
| **M7** 敏感性/控制 | tau 敏感性、plain control、no-DeltaHF、total-ULF、OSS 等 | R7 | R4/6/8 | R7–8 | R4/6 |
| **M8** 次要 scale/端点 | axial；C/D 的 immediate 端点 | R8 | R3 | R2b | R3 |
| **M9** 展示与终稿 manifest | smoothing、展示 mask、FDR/label/density、PDF QC、跨连接组汇总 | R9 | R10 | R9 | R9 |

**首批（first batch，强烈建议先只做这一段再评估）**：每个模型的 **M0 + M1 + M2 + M3(smoke)**。具体 scope 见各规范 “Recommended First Batch”，核心是：主 scale（MDS-UPDRS III total）、主 tau、`Coverage>=5`、主分数、LOOCV、协变量-only 对比、等价测试、smoke perm/boot（B=1000）、smoke jitter（B=100）、基础 QC/manifest。**首批过关后**才进 B=10000 正式 permutation/bootstrap。

---

## 8. 不可违反的护栏（精确等价 / no-shortcut 契约）

**通用（四模型）**
- 禁：正式 B 缩水、adaptive permutation 早停、LOOCV/perm/boot 内用全样本 rank、近似 rank、用全样本 candidate 替代折内 candidate、用固定全样本 F+/F- 打分、把解剖 overlay mask 当分析 mask、丢弃要求的 jitter QC、用压缩 NPZ 做正式循环随机访问输入。
- 折内：每折自建 coverage/candidate（held-out 减法）、每折/每 perm/每 boot 重选 F+/F-、rank 折内计算。
- 复现：种子 42 派生确定性子种子；每分支 manifest 记 env（`conda list --explicit` + `pip freeze`）、code version、输入 hash、runtime_profile；完成标记 + force-rerun。
- 正式循环不写每-perm/每-boot 中间图（除非显式 debug）；worker 不并发追加共享 CSV/JSON。

**纤维（B/D）**
- dTOR **必须** chunked/memmap，禁止整载 fibers 或全曝光入内存；two-pass streaming top-k；top-k tie 用 `(-M, fiber_id)` 确定性打破。
- OSS：先锁 candidate 再算 activation；activation 不重定义 candidate。

**ULF（C/D）**
- tau 是**曝光定义**的一部分（决定 ULF 活跃、HF 活跃、overlap 排除、ULF-only 置零、coverage）；禁用 tau-independent 的 `X_ULF_only`。
- 主预测量**硬排除 HF-overlap** 体素/纤维；total-ULF 只作敏感性。
- `DeltaHFScore` 只用**锁定 HF 模型的 in-support 投影**；禁止外推/平滑/最近邻把 HF 权重塞到 support 外；禁止看到 ULF 结果后扩张 HF support；LOOCV 中 held-out 的 DeltaHFScore 必须用**训练折** HF 图（非全样本）。
- out-of-support 负担必须量化并按门控降级解释。

---

## 9. 完成定义（Definition of Done）

**单模型**：主分支 M0–M6 全部产出规范列出的必需输出；每分支 manifest/QC 完整（含 `corr(score, 协变量)`、系数符号、共线性诊断、flip audit、env provenance、runtime_profile）；等价测试通过并记录；负结果按规范如实标注为 exploratory/negative 并给出 minimal report。

**整体**：A、B 锁定并各自主分支完成；C、D 在其依赖锁定后完成主分支；四份 manifest 可追溯到同一 seed 与一致的 sidecar schema；解释边界写明 **n=16 → hypothesis-generating**；跨连接组/跨 scale 汇总（B/D）产出。

---

## 10. 风险登记

| 风险 | 影响 | 缓解 |
|---|---|---|
| n=16 小样本 | LOOCV 可能不显著；单个高杠杆被试主导 | 影响诊断（Cook/DFBETA）、如实标 hypothesis-generating、permutation p 与 rho/Q2 联合解释 |
| conda 不在 PATH | 脚本直接 `conda` 会失败 | 统一 `/opt/anaconda3/bin/conda run -n leaddbs` 或先 source profile |
| `/Volumes/VAL` 外部卷 | 中途卸载/权限致 IO 失败 | 每 Round 0 校验挂载与读写；正式循环用本地 NVMe scratch，验证后原子提升 |
| scale 方向表 | 未知 scale 极性错 → M 图符号反 | Round 0 强制定义 higher/lower-is-better，写入内部方向表 |
| dTOR 体量 | 内存/算力爆 | chunk 自调优（peak mem < budget×0.7）、two-pass streaming、可续块 checkpoint |
| OSS 参数未锁 | 敏感性不可复现 | 跑前 `oss_model_set=primary_locked` 全参数写 manifest |
| ULF 同日 T2 配对 | immediate 端点有效性依赖同日测量 | Round 0 审计 T2 HF-only 与 HF+ULF immediate 同日/同 session |
| C/D 依赖 A/B 质量 | HF 退化 → DeltaHFScore 不稳 | 依赖锁定门控；HF 失败则 ULF 仅 exploratory 并标注 unstable covariate |

---

### 附：权威文档索引
- 规范（可执行）：`model_summaries/{hf_3m_direct_voxel_model, hf_3m_normative_connectome_fiber_model, ulf_addon_gain_direct_voxel_model, ulf_addon_gain_normative_connectome_fiber_model}.md`（+ `_zh` 镜像）
- 上位总纲：`endpoint_specific_sweetspot_plan.md`（Implementation Outline / Statistical Plan / Acceptance Checks）
- 技术细节：`normative_connectome_sweet_sour_technical_details.md`、`dwi_registration_technical_details.md`、`stnsnr_seed_target_atlas_registry.md`
