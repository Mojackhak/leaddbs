# DWI 导入/预处理/配准模块重构计划

> Status: **in progress**. 目标是把 DWI 相关代码的「后端计算」与「项目/患者调用」解耦，
> 并给最重的 registration/Synb0/eddy 阶段补上被试级并行。范围对齐三点决策：
> (1) 让 Group 3 收敛到 Groups 1&2 已有的三段式；(2) 被试级 `parfor` + 内存/容器感知并发上限；
> (3) 把重复私有 helper 收敛到已有 `core/util/`。

## Context（背景与目标）

`my_helper/fiber/` 下的 DWI 链路目前分 5 组（DICOM 转换、SaveBySlc mosaic 修复、
Synb0/eddy/fake-B0 预处理、Lead-DBS UI coreg/normalize 接入、文档）。整体调用链：

```
DICOM -> mh_fiber_convert_dicom_dwi_to_leaddbs -> dcm2niix
      -> direct DWI / SaveBySlc mosaic reconstruction
      -> rawdata/sub-*/ses-preop/dwi/*.{nii.gz,json,bval,bvec}
      -> run_project_dwi_fake_b0_coreg -> mh_fiber_register_imported_dwi_batch
      -> mh_fiber_dwi_distortion_correction (Synb0/topup/eddy)
      -> BIDSFetcher.getPreprocB0 -> Lead-DBS UI Coregister Volumes -> ea_normalize filters B0
```

经过多轮迭代出现三个结构性问题：

1. **后端计算与项目/患者调用耦合（核心问题）**：Groups 1&2 已经是干净的
   「core 单件（纯路径 in/out）→ `parfor` batch → 项目 wrapper 建表」三段式；但 Group 3 的
   `core/dwi/mh_fiber_register_imported_dwi_batch.m`（1220 行）把 **BIDS/项目路径解析** +
   **后端计算**（stage、distortion correction、b0 提取、coreg、QC）+ **编排/状态 CSV**
   全部熔在一个 `for` 循环里。BIDS 约定（`sub-<id>/ses-preop/dwi`、`desc-preproc`、
   `space-anchorNative`、coreg tag、anchor 匹配、被试发现）写死在计算核心内，别的数据布局无法复用计算。
2. **最贵的阶段完全串行**：`register_one_subject` 顺序遍历被试（`for i = 1:numel(subjects)`），
   而每个被试的 Synb0（docker，约 12GB）+ topup + eddy 可达数十分钟。被试之间完全独立，
   却没有任何并行；反观已经并行的 convert/mosaic batch 反而是最轻的阶段。
3. **helper 大面积复制**：`load_numeric_vector`（6 份）、`ensure_dir`（6 份）、`must_be_file`
   （6 份）、`bvec_volume_count`/`compact_message`/`cleanup_temp_dir`/`get_file_name`（4 份）、
   `resolve_repo_dir`/`shell_quote`/`strip_nii_ext`/`ensure_parallel_pool`（3 份）、`write_json`（2 份），
   而 `core/util/` 早已提供 `mh_util_make_dir`/`mh_util_must_be_file`/`mh_util_write_json`/
   `mh_util_resolve_repo_dir`（VTA 重构建立），DWI 代码却各写各的私有拷贝。

预期结果：Group 3 与 Groups 1&2 同构（计算核心不知道 BIDS/被试）；registration batch 获得
被试级并行且对 Synb0/eddy 有内存感知并发上限；重复 helper 单份化并复用 `core/util/`。

## 当前状态清单（关键文件）

- **Group 1 DICOM 转换**（已三段式、已 `parfor`）：
  `core/dwi/mh_fiber_convert_dicom_dwi_to_leaddbs.m`、`..._batch.m`、`core/dwi/mh_fiber_resolve_dcm2niix.m`
- **Group 2 mosaic 修复**（已三段式、已 `parfor`）：
  `core/dwi/mh_fiber_reconstruct_mosaic_dwi.m`、`..._batch.m`、`core/dwi/mh_fiber_infer_mosaic_geometry.m`、
  项目 wrapper `stnsnr/run_stnsnr_reconstruct_savebyslc_dwi.m`
- **Group 3 preproc/Synb0/eddy（耦合 + 串行，本轮重点）**：
  编排+计算熔合 `core/dwi/mh_fiber_register_imported_dwi_batch.m`（1220 行）、
  数值内核 `core/dwi/mh_fiber_dwi_distortion_correction.m`、
  预设 wrapper `core/dwi/run_project_dwi_fake_b0_coreg.m`、
  项目脚本 `stnsnr/run_stnsnr_dwi_registration.m`、
  `stnsnr/run_stnsnr_dwi_import_stage.m`（import+copy+sha256+stage 脚本）
- **Group 4 Lead-DBS UI 接入（稳定 seam，不动语义）**：
  `helpers/BIDSFetcher.m` 的 `getPreprocB0`、`ea_normalize.m` 过滤 pseudo B0
- **Group 5 文档**：`core/dwi/fake_b0_ui_coreg_tutorial.md`、`core/dwi/synb0_eddy_bbr_upgrade.md`、`README.md`

## 已确认的重复定义（去重依据）

| 函数 | 定义处（个数） | 目标 |
|---|---|---|
| `ensure_dir` / `must_be_file` / `load_numeric_vector` | 6 | `mh_util_make_dir` / `mh_util_must_be_file` / 新增 `mh_fiber_load_bval` |
| `bvec_volume_count` / `compact_message` / `cleanup_temp_dir` / `get_file_name` | 4 | 新增 `mh_fiber_bvec_count` / `mh_fiber_compact_message` / `mh_fiber_cleanup_temp_dir` / `mh_fiber_nii_basename` |
| `resolve_repo_dir` / `shell_quote` / `strip_nii_ext` / `ensure_parallel_pool` | 3 | `mh_util_resolve_repo_dir` / `mh_fiber_shell_quote` / `mh_fiber_strip_nii_ext` / 新增 `mh_fiber_ensure_parallel_pool` |
| `write_json` / `extract_mean_b0`↔`extract_b0`（两份分歧实现） | 2 | `mh_util_write_json` / 新增 `mh_fiber_extract_mean_b0`（统一并保留单层特判） |

> 分歧注意：register batch 的 `extract_b0` 对单层 mosaic 走 `write_single_slice_b0` 特判，
> distortion correction 的 `extract_mean_b0` 没有。统一时必须保留单层分支。

## 目标架构（对齐 Groups 1&2 的三段式）

```
Layer 5  项目编排   stnsnr/、run_project_*   —— 建 job 列表：被试、绝对路径、anchor/coreg/distortion 选项
Layer 4  批处理调度 通用 batch：建池 → serial/parfor(带并发上限) → per-item try/catch → 状态 CSV
Layer 3  单被试管线 mh_fiber_process_imported_dwi(jobSpec, opts)：stage→distortion→b0→QC→coreg→overlay
Layer 2  数值内核   dcm2niix / mosaic 重建 / Synb0·topup·eddy / b0 提取 / coreg backend —— 纯文件 in/out
Layer 1  IO/util    core/util 共享件 + 新增 nifti/bval/bvec/pool/message 共享 helper
```

关键点：Group 3 现在缺 Layer 5↔Layer 3 的**边界契约**——一个 `jobSpec` 结构体，携带某被试的全部
绝对输入/输出路径（rawDwi 四件套、staged dwi/b0、anchorAnat、t1Anat、coregDir/coregAnatDir/qcDir、
fakeB0Coreg 目标、normalization forward transform、coregTag）。项目层负责按 BIDS 约定**生成** jobSpec；
计算层只**消费** jobSpec，绝不自己拼 BIDS 路径或发现被试。这正是 mosaic/convert wrapper 里
`build_inputs` 建表、core 消费的同一范式。

## 目标 1 — 后端计算与项目/患者调用解耦

把 `core/dwi/mh_fiber_register_imported_dwi_batch.m` 按职责拆成三段：

1. **项目层 jobSpec 构建**（Layer 5，新增）`mh_fiber_dwi_bids_jobspec(studyRoot, subjectId, opts) -> jobSpec`：
   吸收现有 `resolve_subject_paths`、`resolve_anchor_anat`、`resolve_anchor_t1`、
   `resolve_anchor_to_mni_transform`、`anchor_patterns`、coreg/qc tag 派生、`discover_subjects_from_rawdata`、
   `read_subjects_from_import_log`。BIDS/项目命名约定只此一处。
2. **单被试计算核心**（Layer 3，新增）`mh_fiber_process_imported_dwi(jobSpec, opts) -> resultRow`：
   吸收现有 `register_one_subject` 主体——validate → stage → （synb0 时）`mh_fiber_dwi_distortion_correction`
   → b0 提取/校验 → 可选 FA/mask QC → `ensure_b0_anchor_coregistration` → overlay PNG → 写 QC JSON。
   入参全是显式路径与选项，**不含**任何 `sub-*/ses-preop/dwi` 拼接、被试发现或 CSV 汇总。
   与 `mh_fiber_convert_dicom_dwi_to_leaddbs` / `mh_fiber_reconstruct_mosaic_dwi` 同构、可单件复用与单测。
3. **薄 batch 调度**（Layer 4，瘦身后的原文件）`mh_fiber_process_imported_dwi_batch(jobSpecs, opts) -> statusTable`：
   只做 job 列表遍历、并行、per-item try/catch → 状态行、`writetable` CSV、`disp` 摘要。
   与 convert/mosaic batch 的骨架一致（见目标 2 复用共享 batch runner）。
4. 现有 `core/dwi/run_project_dwi_fake_b0_coreg.m` 与 stnsnr wrapper 改为：解析 studyRoot/被试 →
   调 `mh_fiber_dwi_bids_jobspec` 批量建 spec → 调 batch。`run_project_*` 保持向后兼容的公开签名
   （`StudyRoot`/`SubjectIds`/`ImportLog`/...）。
5. **coreg backend 拆分**：把 `run_spm_/run_ants_ui_/run_hybrid_/run_flirtbbr_coregistration_branch`
   与 `ensure_legacy_ants_coregistration` 归入 Layer 2 的 coreg backend 集合（消费 jobSpec 里的
   b0/anchor/输出路径），使「配准方法选择」成为可注入项而非核心内 `switch`。

**不变量（保证 UI 不破）**：输出文件名/元数据保持逐字一致——
`preprocessing/dwi/*_desc-preproc_b0.nii`、`coregistration/anat/*_space-anchorNative_desc-preproc_B0.nii`、
sidecar 里的 `FakeCoregisterVolume`/`ExcludeFromNormalization`。Group 4 的 `BIDSFetcher.getPreprocB0`
与 `ea_normalize` 依赖这些命名，本轮**只保不改**。

## 目标 2 — 提升 batch 并行度（被试级 parfor + 并发上限）

1. **单份并行池 helper**：新增 `mh_fiber_ensure_parallel_pool(workerCount)`，替换 convert/mosaic/mosaic-single
   三处相同实现。顺手修掉现有实现的缺陷——**worker 数不匹配就 `delete(pool)` 重建** 太重且会打断他用的池；
   改为「已有池 `NumWorkers >= 请求` 时直接复用，只在需要时扩容」。
2. **给 registration batch 加被试级 `parfor`**：`mh_fiber_process_imported_dwi_batch` 用
   `parfor i = 1:nJobs`（被试互相独立、`rows(i)` 切片赋值），复用 Groups 1&2 已验证的写法。
   本地 parpool 默认 `AutoAddClientPath=true`，client 端一次 `addpath(genpath(repoDir))` 即可，
   无需在核心里反复 `genpath`。
3. **内存/容器感知并发上限（关键约束）**：Synb0 每容器约 `Synb0MinDockerMemoryGB`（默认 12）GB、
   topup/eddy 本身多线程。因此**同时运行的被试数**必须区别于 CPU 核数，取
   `min(ParallelWorkers, floor(可用内存GB / Synb0MinDockerMemoryGB))`；并把每 worker 的工具线程
   （OMP/eddy 线程）下调以免过订阅——沿用 seed-target 已验证的 `threads=1 × workers=N` 权衡。
   distortion=`none` 的纯 stage/coreg 路径无此内存约束，可用满 worker 数。
4. **并行参数入选项**：`Parallel` / `ParallelWorkers` / 新增 `MaxConcurrentSynb0`（或由内存推导），
   经 `run_project_*` 与 stnsnr wrapper 透传；默认串行、行为不变。
5. **共享 batch runner（轻量）**：抽 `mh_fiber_run_item_batch(items, itemFn, opts)`——建池、
   serial/parfor 分派、per-item try/catch → 标准状态行。三个 batch（convert/mosaic/register）共用，
   消除各自复制的 batch 骨架。保持「单件失败不拖垮整批、失败也写状态行」的现有语义。
6. **可续跑不变**：`Force=false` 跳过既有产物，故并行重跑安全；各 worker 用 `tempname` 私有工作目录
   （现状已如此）避免竞争。

## 其他缺点与修改意见（顺带处理/记录）

- **两份分歧的 b0 提取器**：`extract_b0`（含单层特判）vs `extract_mean_b0`（无）——统一为
  `mh_fiber_extract_mean_b0`，保留 `bval<10` 平均与「不独立重心化 b0 头」的既定约束（README 已强调）。
- **`ensure_parallel_pool` 重建池**：见目标 2.1，改为幂等扩容。
- **stnsnr 脚本硬编码**：`run_stnsnr_dwi_registration.m`/`run_stnsnr_dwi_import_stage.m` 是内嵌路径/被试的
  脚本；建议参数化为函数（对齐已是函数的 `run_stnsnr_reconstruct_savebyslc_dwi.m`），便于复用与 dry-run。
- **import-stage 复制/校验可核心化（可选）**：`run_stnsnr_dwi_import_stage.m` 的 copy+sha256+validate 与
  「导入已转好的四件套」高度重合，可抽 `mh_fiber_import_dwi_fourfile` core + batch（与 convert 同构），
  让 stnsnr 脚本变薄。列为后段可选 Phase。
- **状态/QC schema 统一**：三个 batch 各有一套 `empty_row`/CSV 字段；建议统一行 schema + 单一 CSV/JSON writer。
- **checkcode 动态增长告警**：`candidates(end+1)`、`rows(end+1,:)` 等；能预分配处预分配。
- **`addpath(genpath(repoDir))` 每次调用**：移到入口一次，避免重复 `genpath` 开销。

## 建议执行顺序（每步独立可验证、数值不变）

1. **Phase 1 — helper 去重**：把 6 组重复 helper 收敛到 `core/util/`（`mh_util_make_dir`/
   `mh_util_must_be_file`/`mh_util_write_json`/`mh_util_resolve_repo_dir`/`mh_fiber_shell_quote`）
   并新增 `mh_fiber_ensure_parallel_pool`/`mh_fiber_extract_mean_b0`/`mh_fiber_load_bval`/
   `mh_fiber_bvec_count`/`mh_fiber_compact_message`/`mh_fiber_cleanup_temp_dir`。纯搬移，产物字节不变。
2. **Phase 2 — Group 3 解耦（不改并行）**：抽 `mh_fiber_dwi_bids_jobspec` + `mh_fiber_process_imported_dwi`，
   原 batch 瘦成 dispatcher，`run_project_*`/wrapper 改建 jobSpec。仍串行，行为逐字一致。
3. **Phase 3 — registration 并行**：接入 `mh_fiber_run_item_batch` + `parfor` + Synb0 内存并发上限；
   默认仍串行，显式开启才并行。
4. **Phase 4（可选）— import 核心化 + stnsnr 脚本参数化**：抽四件套导入 core+batch，stnsnr 脚本变薄。
5. **Phase 5（可选）— 全 batch 统一**：convert/mosaic 也切到共享 pool helper + 统一状态 schema。

## Implementation notes

- Phase 1 starts with shared helper extraction before changing the registration
  orchestration boundary. The first implementation pass adds DWI-specific
  helpers for bval/bvec validation, NIfTI basename handling, shell quoting,
  temporary directory cleanup, compact error messages, parallel pool reuse, and
  mean b0 extraction. Existing DWI modules should then call these helpers instead
  of keeping private local copies.
- The shared mean b0 extractor must preserve the previous single-slice handling
  from `mh_fiber_register_imported_dwi_batch.m`, because single-slice mosaic
  candidates require `niftiwrite` rather than `spm_write_vol` for a valid b0
  output.
- This phase is intended to be behavior-preserving. It should not change DICOM
  conversion, mosaic reconstruction, Synb0/topup/eddy outputs, pseudo B0 naming,
  or Lead-DBS UI/normalization seams.
- Current Phase 1 scope also covers the STNSNr DWI wrappers that still carry
  local copies of DWI file validation, bval/bvec counting, directory creation,
  and shell quoting. Project wrappers should become thinner but keep their
  existing hard-coded STNSNr defaults until the later project-decoupling phase.

### Phase 2 implementation notes

- Phase 2 introduces three explicit Group 3 boundaries while keeping the public
  `mh_fiber_register_imported_dwi_batch` signature stable:
  `mh_fiber_dwi_bids_jobspec` builds BIDS/Lead-DBS subject path specs,
  `mh_fiber_process_imported_dwi` consumes one fully resolved job spec, and
  `mh_fiber_process_imported_dwi_batch` dispatches those specs serially with
  per-subject error capture.
- This phase intentionally does not add `parfor` yet. Parallel registration and
  Synb0 memory-aware concurrency belong to Phase 3, after the jobSpec boundary
  has been verified in serial mode.
- The single-subject processing core must not discover subjects, parse import
  logs, or construct BIDS subject paths. Those project/layout responsibilities
  stay in the jobSpec builder and wrapper layer.

### Phase 3 implementation notes

- Phase 3 adds opt-in subject-level parallelism to
  `mh_fiber_process_imported_dwi_batch`. The default remains serial, so existing
  callers keep the same behavior unless `Parallel=true` is passed.
- When `DistortionCorrection='synb0'`, the effective worker count is capped by
  `MaxConcurrentSynb0` when provided, otherwise by the available Docker/system
  memory divided by `Synb0MinDockerMemoryGB`. The cap applies to the `parfor`
  worker argument so an existing larger pool can be reused without launching too
  many simultaneous Synb0 containers.
- Parallel workers should set common native thread environment variables to one
  thread per MATLAB worker to reduce FSL/ANTs/ITK over-subscription during batch
  execution.

### Coregistration backend extraction notes

- The b0-to-anchor registration branches are split out of
  `mh_fiber_process_imported_dwi` into a dedicated backend module,
  `mh_fiber_dwi_coregister_b0_to_anchor`. The processing core remains
  responsible for choosing whether coregistration should run, while the backend
  owns SPM, ANTs, hybrid SPM+ANTs, and FLIRT BBR output generation.
- This extraction preserves the current UI-style output names and legacy ANTs
  compatibility behavior. It does not re-enable automatic coregistration for the
  Synb0 fake-B0 workflow; `RunCoregistration=false` still leaves B0 pending for
  Lead-DBS UI coregistration and manual QC.

## 验证

- **数值回归（核心）**：把 1 个真实被试**拷贝**到临时 studyRoot（不覆写 `/Volumes/VAL` 下非 Git 文件），
  重构前后各跑一次，逐字节比对 staged `*_dwi.nii`、`*_b0.nii`、`*_desc-preproc_{dwi,b0}.nii`、
  coreg transform（`*_ants*.mat` / `from-b0_to-anchorNative_*.mat`）与 QC JSON。
- **解耦验证**：给 `mh_fiber_process_imported_dwi` 喂一个手工构造的 jobSpec（非 BIDS 目录布局），
  确认它不依赖 `sub-*/ses-preop/dwi` 也能跑通——证明计算核心已与项目布局无关。
- **并行验证**：1–2 被试 `parfor` vs 串行输出逐字节一致；记录并行前后全 cohort 墙钟时间；
  验证并发上限：设 `Synb0MinDockerMemoryGB`/内存使同时 Synb0 数被正确压到预期值。
- **UI seam 不破**：确认输出仍命中 `_desc-preproc_b0.nii` / `space-anchorNative_desc-preproc_B0.nii`
  与 `FakeCoregisterVolume`/`ExcludeFromNormalization`，`BIDSFetcher.getPreprocB0` 仍暴露 pseudo `B0`、
  `ea_normalize` 仍能过滤。
- **静态检查**：`git diff --check`；对每个新/改文件 `checkcode`；`grep` 确认旧私有 helper 已无残留定义。
- **运行入口**：
  `matlab -batch "cd('/Users/mojackhu/Github/leaddbs'); addpath(genpath(pwd)); run('.../stnsnr/run_stnsnr_dwi_registration.m')"`。
