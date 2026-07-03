# VTA 计算模块重构计划

> Status: **Phase 1 implemented**. The initial checkpoint commit `ddb6888f0`
> recorded this plan before code changes. Phase 1 keeps existing public entry
> points compatible while extracting shared VTA, coverage, utility, and
> visualization primitives.

## Context（背景与目标）

`my_helper/fiber/` 下与 VTA（Volume of Tissue Activated）计算相关的代码经过多轮迭代后，出现了三个结构性问题，需要重构：

1. **后段计算与项目调用耦合**：真正被 cohort 分析使用的 VTA 生成逻辑并不在 `mh_fiber_ensure_vta` 内核里，而是内联在 1269 行的 STNSNr 编排器中（`ensure_program_efields` → `run_horn_with_retry` → `ea_genvat_horn`），连电导率、阈值、atlas、removeElectrode 等 `vatsettings` 都硬编码在里面。全仓库存在三条各自为政、互相复制的 VTA 生成入口。
2. **VTA 模型未分模块**：两个后段（two-source `ensure_vta`、one-solve `ensure_vta_onesolve`）没有共同接口，靠“调不同函数名”选模型；`mh_fiber_model_name` 只认 `'simbio'`；无法按模型类型分发，加新模型要改每个编排器。
3. **并行度低**：并行只做在被试级，靠 env 变量 + 锁目录 + PID 表 spawn 多个 `matlab -batch` 进程实现，粗粒度且脆弱；被试内部 phase×protocol×side×threshold 完全串行，最贵的 FEM 求解（每个 program×side 独立）没有并行；阈值扫描对同一 e-field 每阈值重读重采样。

**新增要求（本轮）**：
- atlas 指定必须作为项目编排层的一部分注入，而不是固定在内核/分析层。这同时适用于「VTA 灰质限制 atlas」和「分类/分割 atlas」两类。
- 美化输出 figure，并按数据类型选择合适图型——占比类（和=100%，如 VTA 各类别占比）用环形图/饼图，而非普通柱状图。

预期结果：形成自上而下依赖、下层不知上层的五层结构；VTA 生成收敛到唯一入口；模型可插拔；atlas 由项目注入；并行下沉到任务级。

## 当前状态清单（关键文件）

- 刺激规格（已基本项目无关）：`mh_fiber_stimspec_from_table.m`、`mh_fiber_set_stimulation.m`、`mh_fiber_build_stimulation.m`、`mh_fiber_make_stim_label.m`、`mh_fiber_model_name.m`
- VTA 后段内核：`core/stimulation/mh_fiber_ensure_vta.m`（two-source）、`core/stimulation/mh_fiber_ensure_vta_onesolve.m`（334 行，内联复制了 Lead-DBS 的 apply_dbs/calc_gradient/dbs_matrix/sb_solve）
- 编排器（项目耦合严重）：`core/stimulation/mh_fiber_run_stnsnr_vta_coverage.m`（1269 行）、`core/stimulation/mh_fiber_run_stnsnr_target_component_vta_distribution.m`（967 行）、`core/stimulation/mh_fiber_compare_vta_schemes.m`
- 项目脚本：`stnsnr/run_stnsnr_vta_coverage{,_parallel,_worker,_cohort_aggregate}.m`
- 分层违规：`core/stimulation/mh_fiber_build_l2_l5to8_stimulation.m` 是 sub-001 专用预设却放在 core
- 错放的默认：`core/config/mh_fiber_default_config.m:40` `cfg.vta.gmAtlas = 'DISTAL Nano (Ewert 2017)'`

## 已确认的重复定义（去重依据）

| 函数 | 定义处 |
|---|---|
| `run_horn_with_retry` / `is_horn_index_error` / `stable_retry_seed` | 2（两个 STNSNr 编排器各一份） |
| `sample_image_to_grid` / `classify_vta` / `atlas_path` / `verify_atlas_files` | 2 |
| `normalize_contact_table` / `write_json` / `make_dir` / `must_be_folder` | 2 |
| `sanitize_label` / `resolve_repo_dir` | 3 |

## 目标架构（五层）

```
Layer 5  项目编排   stnsnr/、pipelines/sub001/  —— 只知数据 schema、路径、atlas 选择，薄
Layer 4  执行/并行  通用任务调度（parpool 或进程池），替代 env+锁
Layer 3  覆盖分析   通用 e-field→体素网格→region 分类→汇总，atlas-agnostic
Layer 2  VTA 内核   按模型分发的计算引擎（唯一 VTA 生成入口）
Layer 1  刺激规格   stimSpec 构建/校验（已基本就绪）
```

## 目标 1 — 后段计算与项目调用解耦

1. 新增唯一 VTA 生成 façade `core/stimulation/model/mh_vta_compute.m`，签名 `vta = mh_vta_compute(cfg, S, options, request)`，`request` 指定 sides/force/model/输出 space。所有 VTA 生成统一走它。
2. 把 STNSNr 编排器里内联的 `ensure_program_efields`/`generate_component_efield`/`run_horn_with_retry`/`is_horn_index_error`/`stable_retry_seed` 全部收回 Layer 2，删除重复；编排器改为只调 `mh_vta_compute`。
3. 抽出通用覆盖分析引擎 Layer 3（`core/coverage/`）：`build_condition_reference_grid`、`sample_image_to_grid`、区域分类、`category_summary_rows`、`write_ref_nii` 项目无关化。
4. 抽出通用工具 `core/util/`：`sanitize_label`/`resolve_repo_dir`/`make_dir`/`must_be_folder`/`must_be_file`/`write_json` 单份化。
5. 把 `mh_fiber_build_l2_l5to8_stimulation.m` 移到 `pipelines/sub001/`。
6. 新增 `mh_vta_settings.m` 作为 `vatsettings`（0.33/0.14、ethresh、removeElectrode）唯一默认来源。

## 目标 2 — 不同 VTA 计算类型分模块

1. `core/stimulation/model/mh_vta_model_registry.m`：model key → 后端函数 + 能力标志（电压/电流、多电压、输出类型）。`mh_vta_compute` 据此分发；`mh_fiber_model_name` 改为查注册表。
2. `model/backends/`：`mh_vta_backend_simbio_twosource.m`（← ensure_vta）、`mh_vta_backend_simbio_onesolve.m`（← ensure_vta_onesolve 薄壳）；统一契约 `(cfg,S,options,side)->写标准路径`；`missing_vta_files`/`read_vat_volume` 提公共层。
3. `model/fem/`：把 one-solve 的数值内核（apply_dbs/gradient/solve/matrix）从 334 行大文件剥离，便于单测与复用。
4. 加新模型只需新增 backend 文件 + 注册，编排/分析层零改动。

## 目标 3 — 提升并行度

1. 定义原子计算单元 = (subject × program × side) 的 e-field 生成，生成任务清单后用 parpool（parfor/parfeval）在单进程内并行，取代 env+锁+PID 表+单独 aggregate；沿用 seed-target 已验证的「串行 setup + 独立任务」范式。
2. 保留进程隔离作为一种模式：把现有 spawn 逻辑封进统一执行 harness（`executionMode = 'parpool' | 'process'`），两模式共用任务清单与错误汇总。
3. 阈值扫描去冗余：reference grid 每 condition 只建一次；e-field 只重采样到网格一次，之后在内存里对多阈值做 `>=` 比较。
4. 并行参数入 config：`cfg.vta.parallel/parallelWorkers/executionMode`。
5. 风险：`ea_genvat_horn` 依赖 `options.prefs.machine.vatsettings` 全局态，parpool worker 需各自持独立 options 副本；one-solve 复用 headmodel 文件，需保证同 subject/side 的 headmodel 不被并发写。

## atlas 外置化（本轮新增要求，贯穿三个目标）

当前两类 atlas 都写死，均改为由 Layer 5 项目编排注入：

**Role 1 — VTA 灰质限制 atlas**（`cfg.vta.gmAtlas` → `options.atlasset`/`horn_atlasset`/`horn_useatlas`）
- 现状：default_config 写死 'DISTAL Nano'，两编排器覆盖成 'DISTAL Minimal'。
- 改法：作为 VTA 模型配置的一部分由项目显式传入；内核只消费，不内置默认。default_config 可保留一个有文档说明的兜底值，但项目层显式设置。

**Role 2 — 分类/分割 atlas**（`atlasDir` + `atlas_path` + `classify_vta`）
- 现状：路径写死 `Custom_Ewert_Zhang_Middlebrooks0.05`；类别写死 STN_only/SNr_only/STN_SNr/Outside；布局写死 `<dir>/<hemi>/<roi>.nii.gz`。
- 改法（**已确认：通用 N 区域归属划分**）：Layer 3 覆盖引擎接收项目提供的 **region 规格**（一组命名区域，每个含 per-hemisphere 掩膜路径或解析器），引擎把每个区域掩膜重采样到 reference grid，做通用「成员归属划分」分类。STN/SNr 语义变成 STNSNr 项目定义的一个实例。
- region 规格数据契约（草案）：
  ```
  regionSpec.regions(i).name       e.g. 'STN'
  regionSpec.regions(i).maskPaths  struct('L', path, 'R', path)
  regionSpec.categoryScheme        'membership_partition'（默认）
  ```
  N 个区域 → 2^N−1 个非空归属组合 + 'Outside'。N=2 时正好复现现有 {STN_only,SNr_only,STN_SNr,Outside}，输出向后兼容。
- 类别命名规则：单区域组合 = `<region>_only`；多区域交集 = 区域名按注入顺序用 `_` 连接（如 `STN_SNr`）；无归属 = `Outside`。`classify_vta`（现写死 4 类）与 `category_summary_rows` 的 `names`/`categoryImg` 整数编码改为按 region 规格动态生成，`write_condition_masks` 的 category NIfTI 编码值与图例随之动态化。
- STNSNr 编排器保留一个 `stnsnr_region_spec`（STN+SNr，沿用 `Custom_Ewert_Zhang_Middlebrooks0.05` 的 `<hemi>/<roi>.nii.gz` 布局作为该项目自己的解析约定），验证其输出与重构前逐数值一致。

## 目标 4 — 图表美化 + 按数据类型选择图型（本轮新增）

现状：两个编排器里的绘图各写一份，只用了 `bar` / `boxchart` / `plot` 三种，且把「本应是占比合成」的类别体积也画成普通柱状图，风格分散、无统一配色/字体。

**核心原则：图型由数据语义决定，占比合成（和=100%）用环形图/饼图。**

抽出统一可视化子模块 `core/viz/`（Layer 3 的一部分，项目无关），提供：
- `mh_viz_apply_style(ax)`：统一字体、字号、留白、网格、白底、去 chartjunk。
- `mh_viz_palette(names)`：按区域/类别名解析配色，复用 `cfg.figure.colors`（NAc `#82D143`、ALIC `#3070B7` 等），并为 N 区域类别扩展稳定色板。
- 按语义分型的绘图函数：
  - `mh_viz_composition_donut(names, values)`：**部分-整体、和=100%** → 环形图，扇区标百分比，中心孔显示总量/标签，图例按类别。用于 VTA 各类别占比（现 `write_condition_figure`/`write_component_figure` 的 bar 改为此）。
  - `mh_viz_stacked_share_bar(...)`：多分组的 100% 堆叠占比条（现 cohort/target-component 的 `stacked_bar` 改为真正 100% 堆叠并标百分比）。
  - `mh_viz_box(...)`：跨被试**分布** → 保留 boxchart，套统一风格（现 `*_boxplot_*`）。
  - `mh_viz_trend_line(...)`：连续变量**趋势** → 保留 line（现 `*_threshold_sensitivity`）。
- 因分类已泛化为 N 区域，环形图/堆叠条须支持任意 N 个类别、动态配色与图例；类别名与颜色与 region 规格一致。

图型选型速查：

| 数据语义 | 现状 | 目标图型 |
|---|---|---|
| VTA 各类别占比（和=100%） | 普通柱状图 | 环形图/饼图，扇区标百分比 |
| 多分组占比 | 普通/伪堆叠 bar | 真正 100% 堆叠条并标百分比 |
| 跨被试体积分布 | boxchart | 箱线图（保留，统一风格） |
| 阈值-体积趋势 | line | 折线图（保留，统一风格） |

图型选型样例（以 STN/SNr 覆盖为例，仅示意目标图型，非真实数据）：

![按数据语义选择图型：VTA 类别占比→环形图，多分组占比→100% 堆叠条，跨被试分布→箱线图，阈值敏感性→折线图](vta_refactor_assets/figure_type_mapping.svg)

编排器的 `write_condition_figure`/`write_component_figure`/`write_cohort_figures`/`write_summary_figures` 改为组装「图规格（数据 + 语义类型）」后交给 `core/viz/`，不再各自内联 `figure/bar/exportgraphics`。

## 建议执行顺序（每步可独立验证、结果不变）

1. 抽公共工具 + 覆盖分析引擎去重（纯搬移，用现有 cohort 输出做数值回归）。
2. 建 VTA 内核 façade + 模型后端/注册表 + atlas 作为参数注入（三处生成入口收敛，对 sub-001 与 STNSNr 各跑一次逐体素比对 binary/e-field 一致）。
3. 移预设、集中 vatsettings、修分层、externalize gmAtlas。
4. 并行 harness + 阈值扫描去冗余（先做 IO 去冗余结果不变，再切并行，用小样本比对与全 cohort 计时验证）。
5. 统一 `core/viz/` 子模块 + 按数据语义换图型（占比→环形/100% 堆叠，分布→boxplot，趋势→line），编排器改为组装图规格。

## 验证

- **数值回归**：重构前后对同一 subject/label 跑 VTA，逐体素比对 `*_binary_*.nii` 与 `*_efield_*.nii`（应完全一致）；对 STNSNr cohort 比对 `cohort_vta_coverage_long.csv` 数值。
- **atlas 注入验证**：用非 STN/SNr 的 region 规格（如临时造一个单区域 atlas）跑覆盖引擎，确认分类类别按注入生成而非写死。
- **并行验证**：小样本（1–2 subject）比对 parpool 模式与串行模式输出一致；全 cohort 记录并行前后墙钟时间。
- **图表验证**：目视检查 cohort/per-subject figures——占比类图为环形/100% 堆叠且扇区标百分比、和为 100%；分布类为 boxplot；趋势类为 line；配色/字体全项目统一。底层数值表（CSV）不受绘图改动影响。
- 运行入口：`matlab -batch "cd('/Users/mojackhu/Github/leaddbs'); addpath(genpath(pwd)); run('.../stnsnr/run_stnsnr_vta_coverage.m')"`。

## Phase 1 Implementation Scope

Phase 1 implements the smallest behavior-preserving cut through the plan:

- Add `core/util/` helpers for labels, repository resolution, directory/file
  validation, JSON writing, and VTA output introspection.
- Add `core/coverage/` helpers for reference-grid construction, image sampling,
  generic membership-partition region classification, category summaries, and
  reference NIfTI writing.
- Add `core/stimulation/model/` with `mh_vta_compute`, `mh_vta_settings`, and a
  model registry. Existing `mh_fiber_ensure_vta*` functions become compatibility
  wrappers around the facade.
- Add `core/stimulation/model/backends/` and `core/stimulation/model/fem/` so
  the SimBio two-source backend, SimBio one-solve backend, and one-solve FEM
  primitives have separate responsibilities.
- Add `core/viz/` helpers for shared style, stable palettes, donut composition
  plots, 100% stacked share bars, box plots, and threshold trend plots.
- Update STNSNr coverage code to receive an explicit region specification for
  classification atlas paths. STN/SNr output category names remain compatible:
  `STN_only`, `SNr_only`, `STN_SNr`, and `Outside`.

Deferred beyond Phase 1:

- Replacing process-level worker launch with a full task-level parpool harness.
- Full cohort-scale numerical regression, because it requires the external
  `/Volumes/VAL/STNSNr` subject data and long FEM generation runtime.

Phase 1 validation completed:

- `git diff --check`
- MATLAB smoke test for `mh_vta_model_registry`, `mh_fiber_model_name`, generic
  membership-partition classification, category summary rows, and category voxel
  accounting.
- MATLAB smoke test for `mh_viz_composition_donut` and
  `mh_viz_stacked_share_bar` PNG export in `-batch` mode.

## Phase 2A Implementation Scope

Status: **implemented**.

Phase 2A targets the threshold-scanning redundancy from Goal 3 without changing
VTA generation semantics:

- Add `mh_coverage_sample_scalar_to_grid(sourcePath, ref)` to resample an
  e-field NIfTI onto the condition/component reference grid once as a numeric
  array.
- In STNSNr cohort coverage and target-component coverage, precompute one
  sampled e-field array per program/component e-field before the threshold loop.
- For each threshold, derive `hitCount` from the in-memory sampled arrays with
  `sampledEfield >= thresholdVPerM` instead of reloading and resampling the same
  NIfTI for every threshold.
- Preserve existing nearest-neighbor sampling, outside-grid non-hit behavior,
  output CSV fields, output mask names, and category calculations.
- Keep `mh_coverage_sample_threshold_to_grid` for compatibility and tests that
  need direct one-threshold sampling.

Phase 2A validation target:

- MATLAB smoke test proving `mh_coverage_sample_scalar_to_grid(path, ref) >= t`
  matches `mh_coverage_sample_threshold_to_grid(path, ref, t)` on a synthetic
  NIfTI for multiple thresholds.
- MATLAB smoke test proving multi-threshold in-memory `hitCount` union/overlap
  logic matches repeated threshold sampling for two synthetic e-fields.
- `git diff --check`.

Phase 2A validation completed:

- `git diff --check`
- MATLAB synthetic NIfTI smoke test comparing scalar sampling plus in-memory
  thresholding against repeated direct threshold sampling, including `t = 0`
  outside-grid behavior.
- MATLAB synthetic two-e-field smoke test comparing in-memory union/overlap
  `hitCount` logic against repeated threshold sampling.
- `checkcode` on the new scalar sampler and both STNSNr analyzers; only existing
  dynamic-growth performance warnings remain in the large analyzers.

## Phase 2B Implementation Scope

Status: **implemented**.

Phase 2B starts the execution-harness migration without changing runtime
parallelism yet:

- Add VTA execution defaults to `mh_fiber_default_config`:
  `cfg.vta.parallel`, `cfg.vta.parallelWorkers`, and `cfg.vta.executionMode`.
- Add shared task primitives under `core/stimulation/model/`:
  - `mh_vta_make_compute_task(cfg, stimFolders, sideCode, request)` builds one
    atomic `(stimLabel x side)` task with expected standard VTA/e-field paths.
  - `mh_vta_run_compute_task(cfg, S, options, task)` executes that task by
    calling `mh_vta_compute` with `request.sides = {sideCode}` and returns
    standardized output paths/status metadata.
- Route STNSNr program e-field generation through those primitives so each
  program side is represented as a task before execution. Phase 2B still runs
  tasks sequentially; it is the behavior-preserving bridge to later
  `executionMode = 'parpool' | 'process'`.

Phase 2B validation target:

- MATLAB smoke test for VTA execution defaults and task construction.
- MATLAB smoke test with a stub `mh_vta_compute` proving
  `mh_vta_run_compute_task` passes only the task side and returns the expected
  MNI paths.
- `git diff --check`.

Phase 2B validation completed:

- `git diff --check`
- MATLAB smoke test for `cfg.vta.parallel`, `cfg.vta.parallelWorkers`, and
  `cfg.vta.executionMode` defaults plus `mh_vta_make_compute_task` path/request
  construction.
- MATLAB smoke test with a temporary `mh_vta_compute` stub proving
  `mh_vta_run_compute_task` passes `request.sides = {'R'}` for a right-side
  task and returns standard MNI/native output path metadata.
- `checkcode` on the new task helpers, default config, and both STNSNr analyzers;
  only existing dynamic-growth performance warnings remain in the large
  analyzers.

## Phase 2C Implementation Scope

Status: **implemented**.

Phase 2C adds the first reusable batch execution helper for VTA tasks:

- Add `mh_vta_execution_config(cfg, taskCount)` to resolve
  `cfg.vta.executionMode`, `cfg.vta.parallel`, and `cfg.vta.parallelWorkers`,
  with safe fallback to sequential execution when the Parallel Computing Toolbox
  is unavailable.
- Add `mh_vta_run_compute_tasks(cfg, S, options, tasks)` to run an array of
  atomic VTA compute tasks through either sequential execution or `parfor`.
- Update STNSNr program-side generation to call the batch helper while keeping
  default execution mode sequential. This preserves current behavior and creates
  one shared call site for future task-level parpool/process scheduling.

Phase 2C validation target:

- MATLAB smoke test for `mh_vta_execution_config` sequential defaults and
  explicit parpool fallback behavior when parallel execution is unavailable.
- MATLAB smoke test with a stub `mh_vta_compute` proving
  `mh_vta_run_compute_tasks` executes two side tasks and returns standardized
  result structs.
- `git diff --check`.

Phase 2C validation completed:

- `git diff --check`
- MATLAB smoke test for `mh_vta_execution_config` defaults, explicit sequential
  behavior, and invalid-mode rejection.
- MATLAB smoke test with a temporary `mh_vta_compute` stub proving
  `mh_vta_run_compute_tasks` executes right and left side tasks and preserves
  standardized result ordering/path metadata.
- `checkcode` passes cleanly for `mh_vta_execution_config` and
  `mh_vta_run_compute_tasks`; the large STNSNr analyzer still has only existing
  dynamic-growth performance warnings.

## Phase 2D Implementation Scope

Status: **implemented**.

Phase 2D encapsulates the current process-isolated worker launcher behind a
reusable harness while preserving the existing subject-level worker behavior:

- Add `mh_vta_launch_process_workers(subjectIds, workerScript, logDir, ...)`
  under `core/stimulation/model/`.
- The helper owns round-robin subject chunking, environment variable assembly,
  Conda-aware MATLAB batch command construction, dry-run mode, PID capture, and
  job table construction.
- Update `stnsnr/run_stnsnr_vta_coverage_parallel.m` to build project-specific
  inputs and delegate process launching to the helper.
- Keep the existing worker script and cohort aggregation flow unchanged.

Phase 2D intentionally does **not** complete task-level process execution for
program-by-side VTA tasks. It is the first process-mode harness extraction; the
remaining step is to connect the program-side task list from Phase 2B/2C to a
process executor and then validate process/parpool/sequential equivalence on a
small subject subset.

Phase 2D validation target:

- MATLAB dry-run smoke test for `mh_vta_launch_process_workers`, verifying
  subject chunking, environment assignment, command construction, log paths, and
  no real worker launch.
- MATLAB dry-run smoke test for `run_stnsnr_vta_coverage_parallel.m` with a
  temporary workbook and `STNSNR_VTA_DRY_RUN=true`.
- `git diff --check`.

Phase 2D validation completed:

- `git diff --check`
- MATLAB dry-run smoke test for `mh_vta_launch_process_workers`, verifying
  subject chunking, environment assignment, command construction, log paths,
  dry-run status, and semicolon-separated job-table subject lists.
- MATLAB dry-run smoke test for `run_stnsnr_vta_coverage_parallel.m` with a
  temporary workbook/output directory and `STNSNR_VTA_DRY_RUN=true`, verifying
  the project launcher delegates to the shared process harness and preserves
  project-specific environment overrides.

## Phase 2E Implementation Scope

Status: **implemented**.

Phase 2E connects the program-side task list from Phase 2B/2C to process-mode
execution while keeping sequential execution as the default:

- Extend the task batch helper so `cfg.vta.executionMode = 'process'` is a
  supported task execution mode instead of only a subject-level launcher mode.
- Add process-mode configuration defaults for the MATLAB executable, Conda
  environment, dry-run planning, task work directory, polling interval, and
  timeout.
- Add a task-worker entry point that receives serialized `(program x side)`
  task payloads, reconstructs the shared VTA inputs, and calls
  `mh_vta_run_compute_task` in an isolated MATLAB process.
- Keep existing STNSNr subject-level process workers compatible; they remain a
  project launcher around whole-subject batches, while Phase 2E handles
  intra-subject program-side tasks.
- Validate with dry-run and stubbed compute tests before any real FEM run.

Phase 2E validation target:

- MATLAB smoke test proving sequential and process-mode dry-run planning create
  equivalent task ordering and expected output metadata for two side tasks.
- MATLAB stub-worker smoke test proving a serialized task payload can be loaded
  and executed by the process task-worker entry point without requiring real FEM
  data.
- `git diff --check`.

Phase 2E validation completed:

- `git diff --check`
- `checkcode` passes cleanly for the new process-mode helpers and touched VTA
  execution/config files.
- MATLAB smoke test proving `cfg.vta.executionMode = 'process'` plus
  `cfg.vta.processDryRun = true` serializes two side tasks, writes worker
  manifests, and preserves task ordering/result metadata without launching
  workers.
- MATLAB stub-worker smoke test proving `mh_vta_compute_task_worker` can load a
  serialized payload and execute `mh_vta_run_compute_task` with a stubbed
  `mh_vta_compute`.
- MATLAB dry-run regression for `mh_vta_launch_process_workers`, confirming the
  subject-level STNSNr launcher still preserves subject chunking, Conda-aware
  command construction, and environment assignment.

Deferred validation:

- Real FEM process-mode execution on a 1-2 subject subset.
- Numerical equivalence among sequential, parpool, and process modes for
  program-side e-field outputs.
- Full cohort timing and numerical regression against
  `cohort_vta_coverage_long.csv`.

## Phase 2F Implementation Scope

Status: **implemented**.

Phase 2F wires the execution harness into the STNSNr project entry points so
the new modes are selectable during real cohort runs:

- Add `VtaExecutionMode`, `VtaParallelWorkers`, `VtaMatlabExe`, `VtaCondaEnv`,
  `VtaProcessWorkDir`, `VtaProcessPollSeconds`, and
  `VtaProcessTimeoutSeconds` parameters to
  `mh_fiber_run_stnsnr_vta_coverage`.
- Pass those options into each per-program VTA cfg before
  `mh_vta_run_compute_tasks` is called.
- Add matching environment variable overrides to
  `stnsnr/run_stnsnr_vta_coverage_worker.m` so subject-level process workers can
  choose intra-subject `sequential`, `parpool`, or `process` execution without
  code edits.
- Add the same environment variable overrides to
  `stnsnr/run_stnsnr_vta_coverage.m` for non-parallel cohort runs.
- Propagate those environment variables from
  `stnsnr/run_stnsnr_vta_coverage_parallel.m` into spawned subject workers.
- Keep subject-level job CSV files readable by MATLAB `readtable` by writing
  full shell commands to per-worker command files and storing only command file
  paths in the job table.
- Keep all defaults behavior-preserving: execution remains sequential with one
  worker unless explicitly overridden.

Phase 2F validation target:

- MATLAB parser/config smoke test proving the STNSNr coverage entry point
  writes the requested execution mode into the per-program cfg before task
  dispatch.
- MATLAB dry-run regression for `run_stnsnr_vta_coverage_parallel.m`, verifying
  worker environment propagation for VTA execution options.
- MATLAB dry-run regression proving `parallel_jobs_latest.csv` remains a
  seven-column comma-delimited table when read with MATLAB `readtable`.
- `git diff --check` and focused `checkcode`.

Phase 2F validation completed:

- `git diff --check`
- Focused `checkcode` passes cleanly for `mh_vta_apply_execution_options`,
  `mh_vta_launch_process_workers`, `mh_fiber_env_double`, and the STNSNr worker
  and parallel launcher scripts.
- MATLAB smoke test for `mh_vta_apply_execution_options`, verifying execution
  mode normalization, worker count, process MATLAB/Conda settings, poll/timeout
  settings, and invalid-mode rejection.
- MATLAB dry-run regression for `run_stnsnr_vta_coverage_parallel.m`, verifying
  execution environment propagation into per-worker command files and confirming
  `parallel_jobs_latest.csv` remains a seven-column comma-delimited job table.
- MATLAB dry-run regression for `mh_vta_launch_process_workers`, verifying
  command-file generation and semicolon-separated subject env chunks.
- Static verification that both non-parallel and worker STNSNr scripts pass the
  VTA execution parameters into `mh_fiber_run_stnsnr_vta_coverage`.

Deferred validation:

- Real FEM process-mode execution on a 1-2 subject subset.
- Numerical equivalence among sequential, parpool, and process modes for
  program-side e-field outputs.
- Full cohort timing and numerical regression against
  `cohort_vta_coverage_long.csv`.

## Phase 2G Validation Audit

Status: **partial validation completed**.

Phase 2G checked what can be verified safely against the available real STNSNr
outputs without overwriting non-Git files under `/Volumes/VAL`:

- Confirmed the real STNSNr subject root exists at
  `/Volumes/VAL/STNSNr/derivatives/leaddbs`.
- Confirmed the real stimulation workbook exists at
  `/Users/mojackhu/Research/STNSNr/summary/cohort/subj/followup_stimulation.xlsx`.
- Confirmed existing cohort outputs exist under `/Volumes/VAL/STNSNr/summary/vta`.
- Ran `mh_fiber_run_stnsnr_vta_coverage` with `CohortOnly = true` into a
  temporary `/tmp/stnsnr_vta_cohort_reg_*` output directory.
- Compared the regenerated temporary `cohort_vta_coverage_long.csv` against the
  existing `/Volumes/VAL/STNSNr/summary/vta/cohort_vta_coverage_long.csv`.
  The tables matched exactly for row count, column count, variable names, key
  columns, and numeric coverage columns: 1536 rows x 25 columns.

Real subject reruns remain deferred because even with `ForceVta = false`, the
STNSNr subject pipeline rewrites subject-level CSV/manifest files under
`/Volumes/VAL/STNSNr/derivatives/leaddbs/<subject>/connectomics/stnsnr_vta_coverage`.
Those files are outside Git, so they should not be overwritten without an
explicit validation run decision and backup/trash policy.

Still deferred:

- Real FEM process-mode execution on a copied or explicitly approved 1-2 subject
  validation subset.
- Numerical equivalence among sequential, parpool, and process modes for
  program-side e-field outputs.
- Full cohort timing comparison after an approved real execution run.

## Phase 2H Implementation Scope

Status: **implemented**.

Phase 2H applies the same execution-harness controls to target-component
counterfactual VTA generation:

- Add the `VtaExecutionMode`, `VtaParallelWorkers`, `VtaMatlabExe`,
  `VtaCondaEnv`, `VtaProcessWorkDir`, `VtaProcessPollSeconds`, and
  `VtaProcessTimeoutSeconds` parameters to
  `mh_fiber_run_stnsnr_target_component_vta_distribution`.
- Apply those options to each generated counterfactual component cfg before VTA
  task execution.
- Replace the direct `mh_vta_run_compute_task` call with
  `mh_vta_run_compute_tasks` so target-component generation uses the same
  sequential/parpool/process execution harness as cohort coverage.
- Add matching environment variable overrides to
  `stnsnr/run_stnsnr_target_component_vta_distribution.m`.
- Keep default behavior unchanged: sequential execution with one worker.

Phase 2H validation target:

- `git diff --check`
- Focused `checkcode` for the target-component analyzer and runner.
- Static verification that target-component counterfactual generation calls
  `mh_vta_run_compute_tasks` and that the project runner passes VTA execution
  parameters into the core analyzer.

Phase 2H validation completed:

- `git diff --check`
- Focused `checkcode`: the target-component runner is clean; the large
  target-component analyzer still has only its existing dynamic-growth
  performance warning.
- Static verification that the target-component analyzer applies
  `mh_vta_apply_execution_options`, calls `mh_vta_run_compute_tasks`, and records
  VTA execution options in its manifest.
- Static verification that `run_stnsnr_target_component_vta_distribution.m`
  reads and passes the shared `STNSNR_VTA_*` execution environment variables.
- MATLAB stub smoke test proving the single-task `mh_vta_run_compute_tasks`
  path returns the same result metadata expected by target-component generation.

## Phase 2I Implementation Scope

Phase 2I removes the duplicated STN/SNr region-spec helper from the two STNSNr
analyzers:

- Add `mh_fiber_stnsnr_region_spec(atlasDir)` as the single project-level
  region-spec constructor for the injected STN/SNr classification atlas.
- Replace local `stnsnr_region_spec` functions in cohort coverage and
  target-component coverage with calls to the shared helper.
- Keep the region names, project label, description, and hemisphere atlas layout
  unchanged.

Phase 2I validation target:

- `git diff --check`
- Focused `checkcode` for the new helper and both touched analyzers.
- MATLAB smoke test proving `mh_fiber_stnsnr_region_spec` returns the expected
  project metadata, region names, category scheme, and per-hemisphere mask path
  fields.
