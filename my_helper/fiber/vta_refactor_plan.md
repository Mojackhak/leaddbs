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

Status: **implemented**.

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

Phase 2I validation completed:

- `git diff --check`
- `checkcode` passes cleanly for `mh_fiber_stnsnr_region_spec`; the two large
  analyzers still have only their existing dynamic-growth performance warnings.
- MATLAB smoke test proving the shared helper returns project `STNSNr`,
  `membership_partition`, STN/SNr region names, and L/R mask path fields.
- Static search confirms both STNSNr analyzers now call
  `mh_fiber_stnsnr_region_spec` and no local `stnsnr_region_spec` functions
  remain.

## Phase 2J Implementation Scope

Status: **implemented**.

Phase 2J removes duplicated STN/SNr contact-table normalization from the cohort
coverage and target-component analyzers:

- Add `mh_fiber_stnsnr_normalize_contact_table(tableIn)` as the shared
  normalizer for old workbook-style headers and normalized per-subject contact
  QC CSV headers.
- Preserve accepted legacy column names, normalized snake_case names, string
  columns, logical parsing for `contact_side_rule_ok`, and numeric conversion
  for contact/parameter columns.
- Replace local `normalize_contact_table` functions in both analyzers with
  calls to the shared helper.
- Keep analyzer-local `force_string_vars` helpers that are still used for
  analyzer-specific output tables.

Phase 2J validation target:

- `git diff --check`
- Focused `checkcode` for the new helper and both touched analyzers.
- MATLAB synthetic smoke test covering old header renaming, string conversion,
  numeric conversion, and logical parsing.
- Non-destructive cohort-only aggregation regression into `/tmp`, comparing the
  regenerated cohort contact QC and coverage tables against existing real
  outputs.

Phase 2J validation completed:

- `git diff --check`
- `checkcode` passes cleanly for `mh_fiber_stnsnr_normalize_contact_table`; the
  two large analyzers still have only their existing dynamic-growth performance
  warnings.
- MATLAB synthetic smoke test covering legacy header renaming, string
  conversion, numeric conversion, valid logical parsing, and invalid logical
  rejection.
- Static search confirms both analyzers call
  `mh_fiber_stnsnr_normalize_contact_table` and no local
  `normalize_contact_table` functions remain.
- Non-destructive cohort-only aggregation regression into
  `/tmp/stnsnr_vta_contact_reg_*`; regenerated coverage table matched existing
  output shape at 1536 x 25, and regenerated contact QC matched existing output
  shape, key columns, logical column, and numeric columns at 194 x 20.

## Phase 2K Implementation Scope

Status: **implemented**.

Phase 2K externalizes the VTA gray-matter restriction atlas used by the STNSNr
project analyzers:

- Add `VtaGmAtlas` to `mh_fiber_run_stnsnr_vta_coverage` and
  `mh_fiber_run_stnsnr_target_component_vta_distribution`.
- Replace analyzer-internal hardcoded `DISTAL Minimal (Ewert 2017)` assignments
  with `opts.VtaGmAtlas` when populating `cfg.vta.gmAtlas` and
  `request.gmAtlas`.
- Add `STNSNR_VTA_GM_ATLAS` overrides to the STNSNr project scripts and the
  subject-level parallel launcher environment propagation.
- Keep default behavior unchanged by defaulting to
  `DISTAL Minimal (Ewert 2017)`.

Phase 2K validation target:

- `git diff --check`
- Focused `checkcode` for touched STNSNr scripts/analyzers.
- Static search confirming STNSNr analyzers no longer assign hardcoded
  `DISTAL Minimal (Ewert 2017)` directly.
- MATLAB dry-run regression for the parallel launcher proving
  `STNSNR_VTA_GM_ATLAS` is forwarded to worker command files.

Phase 2K validation completed:

- `git diff --check`
- Focused `checkcode`: STNSNr project scripts are clean; the two large analyzers
  still have only their existing dynamic-growth performance warnings.
- Static search confirms STNSNr analyzers no longer assign hardcoded
  `DISTAL Minimal (Ewert 2017)` directly to `cfg.vta.gmAtlas` or
  `request.gmAtlas`; they use `opts.VtaGmAtlas`.
- MATLAB dry-run regression for `run_stnsnr_vta_coverage_parallel.m`, proving
  `STNSNR_VTA_GM_ATLAS` is forwarded into worker command files.

## Phase 2L Implementation Scope

Status: **implemented**.

Phase 2L makes the cohort aggregation script consistent with the parallel
launcher and worker scripts:

- Read `STNSNR_VTA_SUBJECT_ROOT`, `STNSNR_VTA_WORKBOOK`,
  `STNSNR_VTA_COHORT_OUTPUT_DIR`, and `STNSNR_VTA_GM_ATLAS` in
  `stnsnr/run_stnsnr_vta_coverage_cohort_aggregate.m`.
- Pass those values into `mh_fiber_run_stnsnr_vta_coverage` with
  `CohortOnly = true`.
- Keep default behavior unchanged when the environment variables are unset.

Phase 2L validation target:

- `git diff --check`
- Focused `checkcode` for the aggregate script.
- Non-destructive aggregate smoke/regression into `/tmp`, verifying custom
  output directory use and cohort CSV shape against existing outputs.

Phase 2L validation completed:

- `git diff --check`
- `checkcode` passes cleanly for `run_stnsnr_vta_coverage_cohort_aggregate.m`.
- Non-destructive aggregate script regression with
  `STNSNR_VTA_COHORT_OUTPUT_DIR=/tmp/stnsnr_vta_aggregate_env_*`, verifying the
  script writes outputs to the env-selected directory, produces
  `cohort_vta_coverage_long.csv` at 1536 x 25, and records the env-selected
  `vta_gm_atlas` in `cohort_vta_generation_manifest.json`.

## Phase 2M Implementation Scope

Status: **implemented**.

Phase 2M removes the remaining local stimulation-label sanitizer while
preserving existing label semantics:

- Extend `mh_util_sanitize_label` with optional `PreservePlus` and `ErrorId`
  arguments. Defaults must preserve current utility behavior, including
  converting `+` to `plus`.
- Update `mh_fiber_set_stimulation` to call `mh_util_sanitize_label` with
  `PreservePlus = true`, preserving its previous explicit-label behavior.
- Preserve the previous `mh_fiber_set_stimulation:InvalidLabel` error for labels
  that sanitize to an empty string.

Phase 2M validation target:

- `git diff --check`
- Focused `checkcode` for the utility and `mh_fiber_set_stimulation`.
- MATLAB smoke test proving default utility behavior is unchanged,
  `PreservePlus` keeps `+`, explicit stimulation labels keep `+`, and empty
  explicit labels still raise `mh_fiber_set_stimulation:InvalidLabel`.

Phase 2M validation completed:

- `git diff --check`
- `checkcode` passes cleanly for `mh_util_sanitize_label` and
  `mh_fiber_set_stimulation`.
- MATLAB smoke test proving default `mh_util_sanitize_label('STN+SNr')` remains
  `STNplusSNr`, `PreservePlus = true` returns `STN+SNr`, utility `ErrorId`
  rejects empty sanitized labels, explicit stimulation labels preserve `+`, and
  empty explicit stimulation labels still raise
  `mh_fiber_set_stimulation:InvalidLabel`.
- Static search confirms `mh_fiber_set_stimulation` now calls
  `mh_util_sanitize_label` and no local `sanitize_label` function remains.

## Phase 2N Implementation Scope

Status: **implemented**.

Phase 2N unifies Horn invocation retry behavior across VTA backends:

- Route the SimBio one-solve backend's headmodel-preparation
  `ea_genvat_horn` call through `mh_vta_run_horn_with_retry`.
- Generalize the retry helper wording from "expected e-field" to "expected
  output" because the one-solve backend treats the headmodel file as the
  expected post-write artifact.
- Keep the two-source backend behavior unchanged.

Phase 2N validation target:

- `git diff --check`
- Focused `checkcode` for `mh_vta_run_horn_with_retry` and
  `mh_vta_backend_simbio_onesolve`.
- MATLAB synthetic smoke test with a temporary `ea_genvat_horn` stub proving the
  retry helper returns successfully when the expected output file exists after a
  Horn error.

Phase 2N validation completed:

- `git diff --check`
- `checkcode` passes cleanly for `mh_vta_run_horn_with_retry` and
  `mh_vta_backend_simbio_onesolve`.
- MATLAB synthetic smoke test with a temporary `ea_genvat_horn` stub verifies
  that `mh_vta_run_horn_with_retry` returns successfully when the expected
  output file exists after a Horn error. The smoke test runs from the temporary
  stub directory so MATLAB resolves the stub instead of the repository-root
  `ea_genvat_horn.m`.

## Phase 2O Implementation Scope

Status: **implemented**.

Phase 2O removes the remaining duplicated VTA task-assembly sequence from the
two STN/SNr analyzers while preserving project-specific stimulation semantics:

- Add `mh_vta_run_stim_spec_tasks` as a shared Layer 2 helper that consumes a
  prepared `cfg`, a Layer 1 `stimSpec`, a side list, and request options.
- The helper applies the stimulation spec, builds Lead-DBS stimulation inputs,
  constructs one atomic task per side, and dispatches those tasks through
  `mh_vta_run_compute_tasks`.
- Update STN/SNr cohort coverage and target-component coverage so each
  analyzer still owns table-to-`stimSpec` conversion, while task request
  construction and execution live in the VTA model layer.
- Keep default execution, output paths, request fields, GM atlas injection, and
  task result metadata unchanged.

Phase 2O validation target:

- `git diff --check`
- Focused `checkcode` for `mh_vta_run_stim_spec_tasks` and both touched STN/SNr
  analyzers.
- MATLAB synthetic smoke test with temporary stubs proving the helper builds
  ordered side tasks and forwards request options without requiring real FEM
  data.
- Static verification that both STN/SNr analyzers call
  `mh_vta_run_stim_spec_tasks` and no longer call
  `mh_vta_make_compute_task` directly.

Phase 2O validation completed:

- `git diff --check`
- `checkcode` passes cleanly for `mh_vta_run_stim_spec_tasks`; the two large
  STN/SNr analyzers still report only their existing dynamic-growth warnings.
- MATLAB synthetic smoke test with temporary stubs verifies that
  `mh_vta_run_stim_spec_tasks` applies the stimulation spec, builds ordered R/L
  side tasks, forwards output-space, threshold, GM atlas, atlas-use, electrode
  removal, force, and model request options, and dispatches through
  `mh_vta_run_compute_tasks` without real FEM data.
- Static search confirms both STN/SNr analyzers call
  `mh_vta_run_stim_spec_tasks` and no longer call
  `mh_vta_make_compute_task` directly.

## Phase 2P Implementation Scope

Status: **implemented**.

Phase 2P tightens the shared utility boundary for the VTA-facing default
configuration:

- Replace `mh_fiber_default_config`'s local `resolve_repo_dir` helper with the
  shared `mh_util_resolve_repo_dir`.
- Keep subject-dir validation, fallback path behavior, and generated `cfg`
  fields unchanged.
- Leave DWI/ROI-local `resolve_repo_dir` helpers out of scope for this VTA
  cleanup because those scripts belong to separate non-VTA workflows.

Phase 2P validation target:

- `git diff --check`
- Focused `checkcode` for `mh_fiber_default_config` and
  `mh_util_resolve_repo_dir`.
- MATLAB smoke test using a temporary subject directory proving
  `mh_fiber_default_config` resolves `cfg.repoDir` to the repository root and
  keeps standard VTA defaults intact.
- Static verification that `mh_fiber_default_config` calls
  `mh_util_resolve_repo_dir` and no longer defines a local `resolve_repo_dir`.

Phase 2P validation completed:

- `git diff --check`
- `checkcode` passes cleanly for `mh_fiber_default_config` and
  `mh_util_resolve_repo_dir`.
- MATLAB smoke test with a temporary `sub-smoke` subject directory verifies that
  `mh_fiber_default_config` resolves `cfg.repoDir` to
  `/Users/mojackhu/Github/leaddbs` and preserves standard VTA defaults,
  including `modelKey = simbio`, `executionMode = sequential`, and
  `gmAtlas = DISTAL Nano (Ewert 2017)`.
- Static search confirms `mh_fiber_default_config` calls
  `mh_util_resolve_repo_dir` and no longer defines a local `resolve_repo_dir`.

## Phase 2Q Implementation Scope

Status: **implemented**.

Phase 2Q removes the duplicated STN/SNr table-to-stimulation-spec conversion
from the two STN/SNr analyzers:

- Add `mh_fiber_stnsnr_stimspec_from_table(rows, label)` as a shared
  project-level Layer 1 helper.
- Support both workbook-style columns (`Side`, `LeadContact`, `Voltage`,
  `PulseWidth`, `Frequency`) and normalized columns (`side`, `lead_contact`,
  `voltage`, `pulse_width`, `frequency`).
- Delegate the final source construction to the generic
  `mh_fiber_stimspec_from_table` helper so source defaults remain centralized.
- Update STN/SNr cohort coverage and target-component coverage to call the
  shared helper and remove their local `rows_to_stim_spec` and `empty_source`
  functions.

Phase 2Q validation target:

- `git diff --check`
- Focused `checkcode` for `mh_fiber_stnsnr_stimspec_from_table` and both
  touched STN/SNr analyzers.
- MATLAB synthetic smoke test proving workbook-style and normalized STN/SNr
  tables produce identical stimulation specs for side, contact, voltage, pulse
  width, frequency, unit, cathode, anode, model, and space.
- Static verification that no local `rows_to_stim_spec` or `empty_source`
  functions remain in the STN/SNr analyzers.

Phase 2Q validation completed:

- `git diff --check`
- `checkcode` passes cleanly for `mh_fiber_stnsnr_stimspec_from_table` and
  `mh_fiber_stimspec_from_table`; the two large STN/SNr analyzers still report
  only their existing dynamic-growth warnings.
- MATLAB synthetic smoke test proves workbook-style and normalized STN/SNr
  tables produce matching source fields for side, contact, voltage, pulse width,
  frequency, unit, cathode, and anode while preserving requested labels, model,
  and space.
- Static search confirms no local `rows_to_stim_spec` or `empty_source`
  functions remain in the STN/SNr analyzers.

## Phase 2R Implementation Scope

Status: **implemented**.

Phase 2R removes duplicated standard coverage-mask writing from the two STN/SNr
analyzers:

- Add `mh_coverage_write_standard_masks` under `core/coverage`.
- The helper builds the standard VTA, category, and program-overlap mask paths
  from an output directory and base label, preserves the existing suffixes, and
  writes each NIfTI only when forced or missing.
- Update STN/SNr cohort coverage and target-component coverage so they keep
  project-specific base-label construction and description text, but delegate
  path construction and NIfTI writing to the shared coverage helper.
- Keep output filenames, force/reuse behavior, datatypes, and descriptions
  unchanged.

Phase 2R validation target:

- `git diff --check`
- Focused `checkcode` for `mh_coverage_write_standard_masks` and both touched
  STN/SNr analyzers.
- MATLAB synthetic smoke test with a temporary `mh_coverage_write_ref_nii` stub
  proving the helper writes the three standard paths when forced and reuses
  existing paths when not forced.
- Static verification that the STN/SNr analyzers call
  `mh_coverage_write_standard_masks` and no longer call
  `mh_coverage_write_ref_nii` directly.

Phase 2R validation completed:

- `git diff --check`
- `checkcode` passes cleanly for `mh_coverage_write_standard_masks`; the two
  large STN/SNr analyzers still report only their existing dynamic-growth
  warnings.
- MATLAB synthetic smoke test with a temporary `mh_coverage_write_ref_nii` stub
  verifies that `mh_coverage_write_standard_masks` writes the three standard
  paths when forced and reuses existing paths without rewriting when not forced.
- Static search confirms the STN/SNr analyzers call
  `mh_coverage_write_standard_masks` and no longer call
  `mh_coverage_write_ref_nii` directly.

## Phase 2S Implementation Scope

Status: **implemented**.

Phase 2S removes the duplicated table string-column conversion helper from the
two STN/SNr analyzers:

- Add `mh_util_force_string_vars(tableIn, stringVars)` under `core/util`.
- Preserve the current behavior: convert only variables present in the table,
  leave missing requested variables ignored, and leave all other variables
  unchanged.
- Update STN/SNr cohort coverage and target-component coverage to call the
  shared utility and remove their local `force_string_vars` functions.
- Keep output table variable names, row counts, and value conversions unchanged.

Phase 2S validation target:

- `git diff --check`
- Focused `checkcode` for `mh_util_force_string_vars` and both touched STN/SNr
  analyzers.
- MATLAB synthetic smoke test proving selected present variables are converted
  to string, missing requested variables are ignored, and untouched variables
  keep their original type/value.
- Static verification that no local `force_string_vars` functions remain in the
  STN/SNr analyzers.

Phase 2S validation completed:

- `git diff --check`
- `checkcode` passes cleanly for `mh_util_force_string_vars`; the two large
  STN/SNr analyzers still report only their existing dynamic-growth warnings.
- MATLAB synthetic smoke test verifies that selected present variables are
  converted to string, missing requested variables are ignored, and untouched
  numeric variables keep their original values and type.
- Static search confirms no local `force_string_vars` functions remain in the
  STN/SNr analyzers.

## Phase 2T Implementation Scope

Status: **implemented**.

Phase 2T removes duplicated threshold-label formatting from the two STN/SNr
analyzers:

- Add `mh_coverage_threshold_label(value)` under `core/coverage`.
- Preserve the current formatting exactly: `sprintf('%.2f', value)` followed by
  replacing `.` with `p`.
- Update STN/SNr cohort coverage and target-component coverage to call the
  shared helper and remove their local `threshold_label` functions.
- Keep existing output filenames and threshold labels unchanged.

Phase 2T validation target:

- `git diff --check`
- Focused `checkcode` for `mh_coverage_threshold_label` and both touched STN/SNr
  analyzers.
- MATLAB synthetic smoke test proving representative thresholds format to the
  previous labels, including rounding behavior.
- Static verification that no local `threshold_label` functions remain in the
  STN/SNr analyzers.

Phase 2T validation completed:

- `git diff --check`
- `checkcode` passes cleanly for `mh_coverage_threshold_label`; the two large
  STN/SNr analyzers still report only their existing dynamic-growth warnings.
- MATLAB synthetic smoke test verifies representative labels and rounding:
  `0.2 -> 0p20`, `0 -> 0p00`, `1.234 -> 1p23`,
  `1.235 -> 1p24`, and `12 -> 12p00`.
- Static search confirms no local `threshold_label` functions remain in the
  STN/SNr analyzers.

## Phase 2U Implementation Scope

Status: **implemented**.

Phase 2U removes the remaining local shell quoting helper from the STN/SNr VTA
coverage analyzer:

- Replace the analyzer-local `shell_quote` function used for subject lock
  directory creation with the shared `mh_fiber_shell_quote` helper.
- Preserve the existing POSIX single-quote escaping semantics exactly.
- Leave unrelated DWI script-local shell quoting out of scope for this VTA
  refactor slice.

Phase 2U validation target:

- `git diff --check`
- Focused `checkcode` for `mh_fiber_run_stnsnr_vta_coverage` and
  `mh_fiber_shell_quote`.
- MATLAB synthetic smoke test proving `mh_fiber_shell_quote` preserves existing
  quoting behavior for spaces and embedded single quotes.
- Static verification that `mh_fiber_run_stnsnr_vta_coverage` calls
  `mh_fiber_shell_quote` and no longer defines a local `shell_quote`.

Phase 2U validation completed:

- `git diff --check`
- `checkcode` passes cleanly for `mh_fiber_shell_quote`; the large STN/SNr
  coverage analyzer still reports only its existing dynamic-growth warnings.
- MATLAB synthetic smoke test verifies quoting for paths with spaces, string
  inputs, and embedded single quotes.
- Static search confirms `mh_fiber_run_stnsnr_vta_coverage` calls
  `mh_fiber_shell_quote` and no longer defines a local `shell_quote`.

## Phase 2V Implementation Scope

Status: **implemented**.

Phase 2V removes remaining local struct-field helpers from the STN/SNr VTA
coverage analyzer:

- Add `mh_util_rmfield_safe(in, fields)` under `core/util`.
- Add `mh_util_get_field(s, fieldName, fallback)` under `core/util`.
- Preserve the current behavior: remove only fields that are present, leave
  other fields unchanged, and return fallback values for missing fields.
- Update STN/SNr cohort coverage to call the shared utilities and remove the
  local `rmfield_safe` and `safe_get_field` functions.

Phase 2V validation target:

- `git diff --check`
- Focused `checkcode` for the two new utilities and
  `mh_fiber_run_stnsnr_vta_coverage`.
- MATLAB synthetic smoke test proving present-field removal, missing-field
  no-op behavior, present-field lookup, and fallback lookup.
- Static verification that no local `rmfield_safe` or `safe_get_field`
  functions remain in the STN/SNr VTA coverage analyzer.

Phase 2V validation completed:

- `git diff --check`
- `checkcode` passes cleanly for `mh_util_rmfield_safe` and
  `mh_util_get_field`; the large STN/SNr coverage analyzer still reports only
  its existing dynamic-growth warnings.
- MATLAB synthetic smoke test verifies present-field removal, missing-field
  no-op behavior, present-field lookup, and fallback lookup.
- Static search confirms no local `rmfield_safe` or `safe_get_field` functions
  remain in the STN/SNr VTA coverage analyzer.

## Phase 2W Implementation Scope

Status: **implemented**.

Phase 2W centralizes repeated semicolon-joined report-field formatting used by
the STN/SNr VTA analyzers:

- Add `mh_util_join_values(values, 'Delimiter', ';')` under `core/util`.
- Preserve the current behavior: reshape inputs to a row string array and join
  values with semicolons by default.
- Update STN/SNr cohort coverage and target-component coverage to use the
  shared helper for raw contacts, lead contacts, target lists, e-field path
  lists, voltages, pulse widths, and frequencies.
- Remove the target-component analyzer's local `join_numeric` helper.

Phase 2W validation target:

- `git diff --check`
- Focused `checkcode` for `mh_util_join_values` and both touched STN/SNr
  analyzers.
- MATLAB synthetic smoke test proving numeric arrays, string arrays, cellstr
  inputs, column vectors, and custom delimiters format as expected.
- Static verification that the target-component analyzer no longer defines
  `join_numeric` and that STN/SNr analyzer semicolon joins call
  `mh_util_join_values`.

Phase 2W validation completed:

- `git diff --check`
- `checkcode` passes cleanly for `mh_util_join_values`; the two large STN/SNr
  analyzers still report only their existing dynamic-growth warnings.
- MATLAB synthetic smoke test verifies numeric row and column vectors, string
  arrays, cellstr inputs, and a custom delimiter.
- Static search confirms the target-component analyzer no longer defines
  `join_numeric` and that STN/SNr analyzer report-field joins call
  `mh_util_join_values`.

## Phase 2X Implementation Scope

Status: **implemented**.

Phase 2X centralizes STN/SNr stimulation-pattern report labels:

- Add `mh_fiber_stnsnr_stimulation_pattern_label` under `core/stimulation`.
- Support the two existing label modes:
  - condition union mode: `continuous`, `alternating_union`, or `mixed_union`.
  - list mode: unique stable stimulation patterns joined with semicolons.
- Update STN/SNr cohort coverage and target-component coverage to call the
  shared helper and remove their local `condition_pattern` and
  `component_pattern` functions.
- Keep output `stimulation_pattern` values unchanged.

Phase 2X validation target:

- `git diff --check`
- Focused `checkcode` for `mh_fiber_stnsnr_stimulation_pattern_label` and both
  touched STN/SNr analyzers.
- MATLAB synthetic smoke test proving condition-union labels and list labels
  match previous behavior for continuous, alternating, and mixed inputs.
- Static verification that no local `condition_pattern` or `component_pattern`
  functions remain in the STN/SNr analyzers.

Phase 2X validation completed:

- `git diff --check`
- `checkcode` passes cleanly for
  `mh_fiber_stnsnr_stimulation_pattern_label`; the two large STN/SNr analyzers
  still report only their existing dynamic-growth warnings.
- MATLAB synthetic smoke test verifies condition-union labels for continuous,
  alternating, and mixed inputs, plus list labels for table and vector inputs.
- Static search confirms no local `condition_pattern` or `component_pattern`
  functions remain in the STN/SNr analyzers.

## Phase 2Y Implementation Scope

Status: **implemented**.

Phase 2Y removes the target-component analyzer's hand-written standard e-field
path constructor:

- Add `mh_fiber_vta_efield_path` as a shared VTA path helper that delegates
  standard filename construction to `mh_fiber_vta_paths`.
- Replace the target-component analyzer-local `efield_path` helper with the
  shared path helper.
- Preserve existing MNI SimBio e-field filenames and side labels exactly.
- Keep observed component e-field selection logic unchanged.

Phase 2Y validation target:

- `git diff --check`
- Focused `checkcode` for `mh_fiber_vta_efield_path` and the target-component
  analyzer.
- MATLAB synthetic smoke test proving the shared helper returns the same MNI
  SimBio e-field path as the previous hard-coded format for both hemispheres.
- Static verification that the target-component analyzer calls
  `mh_fiber_vta_efield_path` and no longer defines a local `efield_path`.

Phase 2Y validation completed:

- `git diff --check`
- `checkcode` passes cleanly for `mh_fiber_vta_efield_path`; the large
  target-component analyzer still reports only its existing dynamic-growth
  warning.
- MATLAB synthetic smoke test verifies that right and left MNI SimBio e-field
  paths match the previous hard-coded filename format.
- Static search confirms the target-component analyzer calls
  `mh_fiber_vta_efield_path` and no longer defines a local `efield_path`.

## Phase 2Z Implementation Scope

Status: **implemented**.

Phase 2Z centralizes the stable STN/SNr observed VTA program label format:

- Add `mh_fiber_stnsnr_vta_program_label` under `core/stimulation`.
- Preserve both existing observed program label formats:
  - continuous condition labels:
    `stnsnr_vta_<subject>_<phase>_<protocol>_continuous`.
  - alternating subprogram labels:
    `stnsnr_vta_<subject>_<phase>_<protocol>_alt_<side>_<target>_c<rawContact>_row<rowIndex>`.
- Update STN/SNr cohort coverage and target-component coverage to call the
  shared helper instead of duplicating `sprintf` plus label sanitization.
- Keep all downstream stimulation labels and e-field folder lookups unchanged.

Phase 2Z validation target:

- `git diff --check`
- Focused `checkcode` for `mh_fiber_stnsnr_vta_program_label` and both touched
  STN/SNr analyzers.
- MATLAB synthetic smoke test proving continuous, alternating, and sanitized
  special-character labels match the previous formats.
- Static verification that direct `stnsnr_vta_%s_%s_%s` format strings no
  longer remain in the STN/SNr analyzers.

Phase 2Z validation completed:

- `git diff --check`
- `checkcode` passes cleanly for `mh_fiber_stnsnr_vta_program_label`; the two
  large STN/SNr analyzers still report only their existing dynamic-growth
  warnings.
- MATLAB synthetic smoke test verifies continuous, alternating, and sanitized
  special-character labels match the previous `sprintf` plus sanitizer output.
- Static search confirms direct `stnsnr_vta_%s_%s_%s` format strings now live
  only in the shared helper and documentation, not in the STN/SNr analyzers.

## Phase 2AA Implementation Scope

Status: **implemented**.

Phase 2AA centralizes STN/SNr condition and target directory keys:

- Add `mh_fiber_stnsnr_condition_key` under `core/stimulation`.
- Preserve the existing condition key format:
  `mh_util_sanitize_label(sprintf('%s_%s', phase, protocol))`.
- Preserve the existing target key behavior by sanitizing the condition key
  first, then sanitizing `conditionKey_target`.
- Update STN/SNr cohort coverage and target-component coverage to call the
  shared helper instead of keeping local or inline key formatting.
- Remove the cohort coverage analyzer's local `make_condition_key` helper.

Phase 2AA validation target:

- `git diff --check`
- Focused `checkcode` for `mh_fiber_stnsnr_condition_key` and both touched
  STN/SNr analyzers.
- MATLAB synthetic smoke test proving condition and target keys match the
  previous formatter behavior, including plus and slash sanitization.
- Static verification that no local `make_condition_key` helper or inline
  `sprintf('%s_%s', phase, protocol)` condition-key formatter remains in the
  STN/SNr analyzers.

Phase 2AA validation completed:

- `git diff --check`
- `checkcode` passes cleanly for `mh_fiber_stnsnr_condition_key`; the two large
  STN/SNr analyzers still report only their existing dynamic-growth warnings.
- MATLAB synthetic smoke test verifies condition and target keys match the
  previous formatter behavior, including plus and slash sanitization.
- Static search confirms no local `make_condition_key` helper or inline
  condition/target key sanitizer remains in the STN/SNr analyzers.

## Phase 2AB Implementation Scope

Status: **implemented**.

Phase 2AB centralizes STN/SNr VTA coverage artifact basenames:

- Add `mh_fiber_stnsnr_vta_artifact_base` under `core/stimulation`.
- Preserve the condition-level basename format:
  `<patient>_phase-<phase>_protocol-<protocol>_hemi-<side>_thr-<threshold>`.
- Preserve the target-component basename format by inserting
  `_target-<target>` before `_thr-<threshold>`.
- Update condition and target-component mask writers and figure writers to use
  the shared basename helper.
- Keep mask suffixes, figure suffixes, descriptions, paths, and visualization
  behavior unchanged.

Phase 2AB validation target:

- `git diff --check`
- Focused `checkcode` for `mh_fiber_stnsnr_vta_artifact_base` and both touched
  STN/SNr analyzers.
- MATLAB synthetic smoke test proving condition-level and target-component
  basenames match the previous `sprintf` plus sanitizer output.
- Static verification that direct VTA coverage basename format strings no
  longer remain in the STN/SNr analyzers.

Phase 2AB validation completed:

- `git diff --check`
- `checkcode` passes cleanly for `mh_fiber_stnsnr_vta_artifact_base`; the two
  large STN/SNr analyzers still report only their existing dynamic-growth
  warnings.
- MATLAB synthetic smoke test verifies condition-level and target-component
  basenames match the previous `sprintf` plus sanitizer output.
- Static search confirms direct VTA coverage basename format strings no longer
  remain in the STN/SNr analyzers.

## Phase 2AC Implementation Scope

Status: **implemented**.

Phase 2AC routes generated stimulation-label sanitization through the shared
label utility:

- Update `mh_fiber_make_stim_label` to call `mh_util_sanitize_label`.
- Preserve the existing generated-label behavior by converting dots to `p`
  before sanitization and passing `PreservePlus = true`.
- Keep token grouping, amplitude formatting, source ordering, and explicit
  stimulation-label handling unchanged.
- Remove the local duplicated regex sanitizer from `mh_fiber_make_stim_label`.

Phase 2AC validation target:

- `git diff --check`
- Focused `checkcode` for `mh_fiber_make_stim_label`.
- MATLAB synthetic smoke test proving generated labels match the previous
  manual regex sanitizer behavior for bilateral grouping, decimal amplitudes,
  plus-preserving units, and punctuation cleanup.
- Static verification that `mh_fiber_make_stim_label` no longer contains the
  duplicated non-utility sanitizer regex sequence.

Phase 2AC validation completed:

- `git diff --check`
- `checkcode` for `mh_fiber_make_stim_label` still reports only its existing
  dynamic-growth warnings.
- MATLAB synthetic smoke test verifies generated labels match the previous
  manual regex sanitizer behavior for bilateral grouping, decimal amplitudes,
  plus-preserving units, and punctuation cleanup.
- Static search confirms `mh_fiber_make_stim_label` now calls
  `mh_util_sanitize_label(label, 'PreservePlus', true)` and no longer contains
  the duplicated non-utility sanitizer regex sequence.

## Phase 2AD Implementation Scope

Status: **implemented**.

Phase 2AD centralizes STN/SNr target-component identifiers and their generated
VTA stimulation labels:

- Add `mh_fiber_stnsnr_target_component_id` under `core/stimulation`.
- Add `mh_fiber_stnsnr_target_component_vta_label` under `core/stimulation`.
- Preserve the existing component ID format:
  `<subject_id>_<phase>_<protocol>_<side>_<target>`, sanitized with
  `mh_util_sanitize_label`.
- Preserve the existing generated target-component VTA label format:
  `stnsnr_target_component_<component_id>`, sanitized with
  `mh_util_sanitize_label`.
- Update `mh_fiber_run_stnsnr_target_component_vta_distribution` to call the
  shared helpers instead of hand-writing the ID and label format.

Phase 2AD validation target:

- `git diff --check`
- Focused `checkcode` for both new helpers and the target-component analyzer.
- MATLAB synthetic smoke test proving component IDs and target-component VTA
  labels match the previous formatter behavior, including plus and slash
  sanitization.
- Static verification that the target-component analyzer no longer directly
  constructs the component ID format or `stnsnr_target_component_` label.

Phase 2AD validation completed:

- `git diff --check`
- `checkcode` passes cleanly for `mh_fiber_stnsnr_target_component_id` and
  `mh_fiber_stnsnr_target_component_vta_label`; the target-component analyzer
  still reports only its existing dynamic-growth warning.
- MATLAB synthetic smoke test verifies component IDs and target-component VTA
  labels match the previous formatter behavior, including plus and slash
  sanitization.
- Static search confirms the target-component analyzer now calls the shared
  helpers instead of directly constructing the component ID format or
  `stnsnr_target_component_` label.

## Phase 2AE Implementation Scope

Status: **implemented**.

Phase 2AE extracts the common coverage threshold primitive used by the STN/SNr
condition and target-component analyzers:

- Add `mh_coverage_sample_efields_to_grid` under `core/coverage` to sample a
  list of e-field NIfTIs onto one reference grid.
- Add `mh_coverage_threshold_sampled_efields` under `core/coverage` to combine
  sampled e-fields at one threshold, derive VTA and overlap masks, classify
  region membership, validate category voxel sums, and return category summary
  rows.
- Update both STN/SNr analyzers to call the shared helpers instead of repeating
  the sampling, hit-count, VTA/overlap mask, classification, and category-sum
  logic.
- Keep threshold labels, mask-writing descriptions, report rows, figures, and
  manifest fields unchanged.

Phase 2AE validation target:

- `git diff --check`
- Focused `checkcode` for both new coverage helpers and both touched STN/SNr
  analyzers.
- MATLAB synthetic smoke test proving thresholded VTA masks, overlap masks,
  total voxels, overlap voxels, and category rows match the previous inline
  behavior on small in-memory sampled e-field arrays.
- Static verification that both STN/SNr analyzers call the shared helpers, pass
  their original category-sum error IDs, and no longer contain duplicated
  `hitCount` threshold loops.

Phase 2AE validation completed:

- `git diff --check`
- `checkcode` passes cleanly for `mh_coverage_sample_efields_to_grid` and
  `mh_coverage_threshold_sampled_efields`; the two large STN/SNr analyzers
  still report only their existing dynamic-growth warnings.
- MATLAB synthetic smoke test verifies thresholded VTA masks, overlap masks,
  total voxels, overlap voxels, category rows, and category-row voxel sums match
  the previous inline behavior on small in-memory sampled e-field arrays.
- Static search confirms both STN/SNr analyzers call the shared helpers and no
  longer contain duplicated `hitCount` threshold loops.

## Phase 2AF Implementation Scope

Status: **implemented**.

Phase 2AF centralizes the repeated VTA coverage composition-figure writer:

- Add `mh_coverage_write_composition_figure` under `core/coverage`.
- Preserve the existing figure behavior: use category names from column 1,
  volumes from column 3, center text as the rounded total volume in `mm3`,
  write through `mh_viz_composition_donut`, and close the hidden figure.
- Update STN/SNr condition coverage and target-component coverage figure
  writers to compute only their project-specific base label and title, then
  call the shared helper.
- Keep figure filenames, titles, image resolution, palette, and chart layout
  unchanged.

Phase 2AF validation target:

- `git diff --check`
- Focused `checkcode` for `mh_coverage_write_composition_figure` and both
  touched STN/SNr analyzers.
- MATLAB synthetic smoke test using a temporary `mh_viz_composition_donut` stub
  to verify names, volumes, title, center text, output path, and figure close
  behavior without writing a real PNG.
- Static verification that the STN/SNr analyzers no longer call
  `mh_viz_composition_donut` directly.

Phase 2AF validation completed:

- `git diff --check`
- `checkcode` passes cleanly for `mh_coverage_write_composition_figure`; the two
  large STN/SNr analyzers still report only their existing dynamic-growth
  warnings.
- MATLAB synthetic smoke test with a temporary `mh_viz_composition_donut` stub
  verifies names, volumes, title, center text, output path, and figure close
  behavior without writing a real PNG.
- Static search confirms the STN/SNr analyzers no longer call
  `mh_viz_composition_donut` directly.

## Phase 2AG Implementation Scope

Status: **implemented**.

Phase 2AG moves the target-component analyzer's local IQR statistic into the
shared coverage layer:

- Add `mh_coverage_iqr(values)` under `core/coverage`.
- Preserve the existing behavior: drop `NaN` values, return `NaN` for empty
  inputs, and compute `quantile(values, 0.75) - quantile(values, 0.25)`.
- Update `mh_fiber_run_stnsnr_target_component_vta_distribution` to use the
  shared helper in `summarize_distribution`.
- Remove the analyzer-local `local_iqr` helper.

Phase 2AG validation target:

- `git diff --check`
- Focused `checkcode` for `mh_coverage_iqr` and the target-component analyzer.
- MATLAB synthetic smoke test proving finite values, mixed `NaN` values, all
  `NaN` values, and column-vector inputs match the previous local helper
  behavior.
- Static verification that the target-component analyzer no longer defines
  `local_iqr`.

Phase 2AG validation completed:

- `git diff --check`
- `checkcode` passes cleanly for `mh_coverage_iqr`; the target-component
  analyzer still reports only its existing dynamic-growth warning.
- MATLAB synthetic smoke test verifies finite values, mixed `NaN` values, all
  `NaN` values, and column-vector inputs match the previous local helper
  behavior.
- Static search confirms the target-component analyzer now calls
  `mh_coverage_iqr` and no longer defines `local_iqr`.

## Phase 2AH Implementation Scope

Status: **implemented**.

Phase 2AH centralizes the repeated category-by-group matrix construction used by
the STN/SNr cohort and target-component stacked-share figures:

- Add `mh_coverage_category_matrix(groupValues, categoryValues, values)` under
  `core/coverage`.
- Preserve the existing behavior: stable unique group labels, stable unique
  category labels, zero-filled missing group/category combinations, and the
  first matching value for duplicate group/category rows.
- Update `write_cohort_figures` and `write_summary_figures` to call the shared
  helper before `mh_viz_stacked_share_bar`.
- Keep stacked-share figure titles, filenames, value source columns, and
  plotting behavior unchanged.

Phase 2AH validation target:

- `git diff --check`
- Focused `checkcode` for `mh_coverage_category_matrix` and both touched
  STN/SNr analyzers.
- MATLAB synthetic smoke test proving stable ordering, missing-combination zero
  fill, duplicate first-value behavior, and numeric matrix values match the
  previous inline loop behavior.
- Static verification that the STN/SNr analyzers no longer contain duplicated
  nested category-matrix loops for stacked-share figures.

Phase 2AH validation completed:

- `git diff --check`
- `checkcode` passes cleanly for `mh_coverage_category_matrix`; the two large
  STN/SNr analyzers still report only their existing dynamic-growth warnings.
- MATLAB synthetic smoke test verifies stable ordering, missing-combination
  zero fill, duplicate first-value behavior, and numeric matrix values match the
  previous inline loop behavior.
- Static search confirms the STN/SNr analyzers call
  `mh_coverage_category_matrix` and no longer contain duplicated nested
  category-matrix loops for stacked-share figures.

## Phase 2AI Implementation Scope

Status: **implemented**.

Phase 2AI centralizes threshold-sensitivity trend table construction used by
the STN/SNr cohort and target-component summary figures:

- Add `mh_coverage_threshold_trend_table(tableIn, groupVars)` under
  `core/coverage`.
- Preserve the existing behavior: deduplicate caller-provided total-VTA rows,
  group by stable threshold alone or by stable group variables plus threshold,
  and compute mean total VTA volume with `omitnan`.
- Update `write_cohort_figures` and `write_summary_figures` to call the shared
  helper before `mh_viz_trend_line`.
- Keep trend figure titles, filenames, axis labels, group labels, and plotted
  values unchanged.

Phase 2AI validation target:

- `git diff --check`
- Focused `checkcode` for `mh_coverage_threshold_trend_table` and both touched
  STN/SNr analyzers.
- MATLAB synthetic smoke test proving ungrouped cohort trends, grouped target
  trends, duplicate-row deduplication, stable ordering, and `NaN` omission match
  the previous inline behavior.
- Static verification that the STN/SNr analyzers no longer contain duplicated
  `findgroups(... threshold_v_per_mm)` trend-preparation blocks.

Phase 2AI validation completed:

- `git diff --check`
- `checkcode` passes cleanly for `mh_coverage_threshold_trend_table`; the two
  large STN/SNr analyzers still report only their existing dynamic-growth
  warnings.
- MATLAB synthetic smoke test verifies ungrouped cohort trends, grouped target
  trends, duplicate-row deduplication, stable ordering, and `NaN` omission match
  the previous inline behavior.
- Static search confirms the STN/SNr summary-figure trend blocks call
  `mh_coverage_threshold_trend_table` instead of duplicating
  `findgroups(... threshold_v_per_mm)` trend preparation.

## Phase 2AJ Implementation Scope

Status: **implemented**.

Phase 2AJ centralizes long-to-wide category coverage table construction:

- Add `mh_coverage_category_wide_table(tableIn, keyVars)` under `core/coverage`.
- Preserve the existing behavior: unstack `volume_mm3` by `category`, either
  using all existing non-value columns or a caller-provided stable key-column
  list.
- Update STN/SNr cohort coverage and target-component coverage output writers
  to call the shared helper.
- Remove the target-component analyzer-local `make_wide_table` helper.
- Keep CSV filenames, long table schemas, selected target-component key columns,
  and wide table values unchanged.

Phase 2AJ validation target:

- `git diff --check`
- Focused `checkcode` for `mh_coverage_category_wide_table` and both touched
  STN/SNr analyzers.
- MATLAB synthetic smoke test proving full-table unstacking and key-limited
  unstacking match the previous inline behavior.
- Static verification that the STN/SNr analyzers call the shared helper and no
  longer define `make_wide_table` or inline `unstack(..., 'volume_mm3',
  'category')`.

Phase 2AJ validation completed:

- `git diff --check`
- `checkcode` passes cleanly for `mh_coverage_category_wide_table`; the two
  large STN/SNr analyzers still report only their existing dynamic-growth
  warnings.
- MATLAB synthetic smoke test verifies full-table unstacking and key-limited
  unstacking match the previous inline behavior.
- Static search confirms the STN/SNr analyzers call
  `mh_coverage_category_wide_table` and no longer define `make_wide_table` or
  inline `unstack(..., 'volume_mm3', 'category')`.

## Phase 2AK Implementation Scope

Status: **implemented**.

Phase 2AK centralizes repeated coverage output-file existence checks:

- Add `mh_coverage_require_output_files(outputDir, requiredFiles)` under
  `core/coverage`.
- Support an optional `DescriptionPrefix` so callers can preserve existing
  `mh_util_must_be_file` descriptions.
- Update STN/SNr cohort coverage output validation, cohort files-only
  validation, and target-component output validation to call the shared helper
  instead of open-coding the required-file loop.
- Keep required filename lists, nested figure paths, error behavior, and
  validation order unchanged.

Phase 2AK validation target:

- `git diff --check`
- Focused `checkcode` for `mh_coverage_require_output_files` and both touched
  STN/SNr analyzers.
- MATLAB synthetic smoke test proving present files pass, nested relative paths
  pass, missing files raise through `mh_util_must_be_file`, and description
  prefixes are accepted.
- Static verification that the STN/SNr analyzers no longer contain duplicated
  `for i = 1:numel(required)` output-file loops.

Phase 2AK validation completed:

- `git diff --check`
- `checkcode` passes cleanly for `mh_coverage_require_output_files`; the two
  large STN/SNr analyzers still report only their existing dynamic-growth
  warnings.
- MATLAB synthetic smoke test verifies present files pass, nested relative paths
  pass, missing files raise through `mh_util_must_be_file`, and description
  prefixes are accepted.
- Static search confirms output-file validation now calls
  `mh_coverage_require_output_files`; remaining `for i = 1:numel(required)`
  loops are table-column validation loops, not output-file checks.

## Phase 2AL Implementation Scope

Status: **completed**.

Phase 2AL centralizes threshold-series validation for total VTA volumes:

- Add `mh_coverage_validate_threshold_series(totalRows, groupVars, thresholds)`
  under `core/coverage`.
- Preserve the existing validation behavior: sort each group by
  `threshold_v_per_mm`, require one row per expected threshold, and require
  `total_vta_volume_mm3` to be monotonic non-increasing within a `1e-6`
  tolerance.
- Support caller-provided missing-threshold and monotonicity error IDs plus
  message formats so STN/SNr cohort and target-component validators keep their
  current public errors.
- Update both STN/SNr validators to call the shared helper after constructing
  their existing deduplicated `totalRows` tables.

Phase 2AL validation target:

- `git diff --check`
- Focused `checkcode` for `mh_coverage_validate_threshold_series` and both
  touched STN/SNr analyzers.
- MATLAB synthetic smoke test proving valid series pass, missing-threshold
  series raise the caller-provided missing error ID, increasing-volume series
  raise the caller-provided monotonicity error ID, and multi-column group labels
  work.
- Static verification that the STN/SNr analyzers no longer contain duplicated
  sorted-threshold monotonicity loops.

Phase 2AL validation results:

- `git diff --check` passed.
- `mh_coverage_validate_threshold_series` passed focused `checkcode` with zero
  messages.
- The two touched STN/SNr analyzers report only pre-existing `AGROW`
  `checkcode` messages outside the refactored validation blocks.
- MATLAB synthetic smoke tests passed for valid threshold series, missing
  threshold rows, monotonicity failure, multi-column cohort grouping, and
  target-component grouping.

## Phase 2AM Implementation Scope

Status: **completed**.

Phase 2AM centralizes remaining analyzer-local required table-column checks:

- Add `mh_util_require_table_vars(tableIn, requiredVars, errorId, messageFormat)`
  under `core/util`.
- Preserve the existing behavior: check required variables in caller-provided
  order and raise on the first missing variable.
- Preserve caller-specific public errors by passing the existing missing-column
  error IDs and message formats from the STN/SNr workbook reader and
  target-component contact-QC validator.
- Leave coverage-helper internal all-missing-column messages unchanged because
  they intentionally report complete missing-column lists.
- Leave output-file required lists unchanged because Phase 2AK already routes
  those through `mh_coverage_require_output_files`.

Phase 2AM validation target:

- `git diff --check`
- Focused `checkcode` for `mh_util_require_table_vars` and both touched
  STN/SNr analyzers.
- MATLAB synthetic smoke test proving present columns pass and missing columns
  raise the caller-provided error ID for both workbook-style and contact-QC
  table schemas.
- Static verification that the two STN/SNr analyzers no longer contain
  analyzer-local `for i = 1:numel(required)` table-column validation loops.

Phase 2AM validation results:

- `git diff --check` passed.
- `mh_util_require_table_vars` passed focused `checkcode` with zero messages.
- The two touched STN/SNr analyzers report only pre-existing `AGROW`
  `checkcode` messages outside the refactored required-column checks.
- MATLAB synthetic smoke tests passed for present workbook/contact-QC columns
  and missing-column failures using caller-provided error IDs and message
  formats.
- Static search confirms the analyzer-local required table-column loops were
  replaced with `mh_util_require_table_vars`.

## Phase 2AN Implementation Scope

Status: **completed**.

Phase 2AN centralizes category summary-table construction for VTA coverage:

- Add `mh_coverage_category_summary_table(tableIn, groupVars, ...)` under
  `core/coverage`.
- Preserve the cohort summary schema by default:
  `groupVars`, `threshold_v_per_mm`, `category`, `mean_volume_mm3`,
  `median_volume_mm3`, `sd_volume_mm3`, and `mean_percent_total_vta`.
- Support target-component summary extras through options:
  `n_components`, `n_subjects`, `iqr_volume_mm3`, `min_volume_mm3`, and
  `max_volume_mm3`.
- Update STN/SNr cohort and target-component summary builders to call the
  shared helper while keeping output column order, names, grouping keys, and
  `omitnan` behavior unchanged.

Phase 2AN validation target:

- `git diff --check`
- Focused `checkcode` for `mh_coverage_category_summary_table` and both touched
  STN/SNr analyzers.
- MATLAB synthetic smoke test comparing cohort-style and target-component-style
  summary outputs against hand-computed expected values, including duplicate
  rows, NaN omission, component counts, unique-subject counts, IQR, and min/max.
- Static verification that the two STN/SNr analyzers call the shared helper and
  no longer duplicate splitapply-based category summary statistics.

Phase 2AN validation results:

- `git diff --check` passed.
- `mh_coverage_category_summary_table` passed focused `checkcode` with zero
  messages.
- The two touched STN/SNr analyzers report only pre-existing `AGROW`
  `checkcode` messages outside the refactored summary builders.
- MATLAB synthetic regression tests passed by comparing helper output with the
  previous explicit `findgroups`/`splitapply` formulas for both cohort-style and
  target-component-style summaries.
- The smoke test covered duplicate rows, NaN omission, component counts,
  unique-subject counts, IQR, min/max, and missing-column errors.
- Static search confirms the STN/SNr summary builders call
  `mh_coverage_category_summary_table` instead of duplicating category summary
  statistic blocks.

## Phase 2AO Documentation Sync

Status: **completed**.

Phase 2AO updates user-facing execution documentation to match the current VTA
task harness:

- Replace stale README wording that described task-level `parpool` support as a
  future capability.
- Document the current behavior: sequential execution remains the default, and
  `cfg.vta.executionMode` can select `parpool` or `process` task execution
  through `mh_vta_run_compute_tasks`.
- Leave code unchanged because the execution harness already implements the
  documented modes.

Phase 2AO validation target:

- `git diff --check`
- Static verification that README no longer describes parpool/process task
  execution as future-only.

Phase 2AO validation results:

- `git diff --check` passed.
- Static search confirms README no longer contains the stale future-parpool
  wording or the old sequential-unless-process-launcher sentence.

## Phase 2AP Implementation Scope

Status: **completed**.

Phase 2AP centralizes repeated cell-row table construction boilerplate:

- Add `mh_util_cell_rows_to_table(rows, variableNames, stringVars)` under
  `core/util`.
- Preserve existing empty-row behavior: return `table()` when `rows` is empty.
- Preserve caller-owned schemas by keeping variable-name and string-variable
  lists in each STN/SNr analyzer.
- Update cohort coverage/contact table builders and target-component
  coverage/component-QC table builders to call the shared utility.
- Keep table column order, numeric values, string conversions, and empty-table
  behavior unchanged.

Phase 2AP validation target:

- `git diff --check`
- Focused `checkcode` for `mh_util_cell_rows_to_table` and both touched
  STN/SNr analyzers.
- MATLAB synthetic regression test proving helper-built tables match the
  previous `cell2table` plus string-conversion behavior for all four local
  table schemas, including empty-row outputs.
- Static verification that the touched STN/SNr analyzers no longer call
  `cell2table` directly in their `rows_to_*_table` helpers.

Phase 2AP validation results:

- `git diff --check` passed.
- `mh_util_cell_rows_to_table` passed focused `checkcode` with zero messages.
- The two touched STN/SNr analyzers report only pre-existing `AGROW`
  `checkcode` messages outside the refactored table builders.
- MATLAB synthetic regression tests passed for all four local table schemas:
  cohort coverage, cohort contact QC, target-component coverage, and
  target-component component QC.
- The smoke test confirmed helper-built tables match the previous `cell2table`
  plus string-conversion behavior, preserve variable order, convert the same
  string variables, and preserve empty-row `table()` output behavior.
- Static search confirms the touched `rows_to_*_table` helpers now call
  `mh_util_cell_rows_to_table` instead of calling `cell2table` directly.

## Phase 2AQ Implementation Scope

Status: **completed**.

Phase 2AQ centralizes total VTA summary-table construction:

- Add `mh_coverage_total_vta_summary(tableIn, groupVars, ...)` under
  `core/coverage`.
- Preserve the cohort summary behavior: group by caller-provided variables and
  report the maximum `total_vta_volume_mm3` per group.
- Update the STN/SNr cohort summary writer to call the shared helper while
  keeping output column order and variable names unchanged.
- Keep target-component distribution summaries unchanged because they summarize
  category rows rather than per-condition total VTA maxima.

Phase 2AQ validation target:

- `git diff --check`
- Focused `checkcode` for `mh_coverage_total_vta_summary` and the touched
  cohort analyzer.
- MATLAB synthetic regression test proving helper output matches the previous
  `findgroups`/`splitapply(@max)` formula, including stable group columns and
  duplicate rows.
- Static verification that the cohort analyzer no longer defines a local
  `summarize_total_vta` implementation with `splitapply(@max)`.

Phase 2AQ validation results:

- `git diff --check` passed.
- `mh_coverage_total_vta_summary` passed focused `checkcode` with zero
  messages.
- The touched cohort analyzer reports only pre-existing `AGROW` `checkcode`
  messages outside the refactored total-summary wrapper.
- MATLAB synthetic regression tests passed by comparing helper output with the
  previous explicit `findgroups`/`splitapply(@max)` formula, including duplicate
  rows, stable group columns, custom output-column naming, and missing-column
  errors.
- Static search confirms the cohort analyzer delegates `summarize_total_vta` to
  `mh_coverage_total_vta_summary` instead of implementing `splitapply(@max)`
  locally.

## Phase 2AR Implementation Scope

Status: **completed**.

Phase 2AR centralizes category-total output validation:

- Add `mh_coverage_validate_category_totals(tableIn, groupVars, expectedRows, ...)`
  under `core/coverage`.
- Preserve the target-component validation behavior: for each
  `component_id x threshold_v_per_mm` group, require exactly four category rows
  and require `sum(voxel_count)` to equal the group's `total_vta_voxels`.
- Support caller-provided row-count and voxel-sum error IDs plus message
  formats so target-component validation keeps its public errors.
- Preserve numeric group-value formatting for threshold messages such as
  `%.2f`.

Phase 2AR validation target:

- `git diff --check`
- Focused `checkcode` for `mh_coverage_validate_category_totals` and the touched
  target-component analyzer.
- MATLAB synthetic smoke test proving valid category totals pass, row-count
  failures raise the caller-provided missing-category error ID with numeric
  threshold formatting, and voxel-sum failures raise the caller-provided mismatch
  error ID.
- Static verification that the target-component analyzer no longer contains the
  local category-total `findgroups` validation loop.

Phase 2AR validation results:

- `git diff --check` passed.
- `mh_coverage_validate_category_totals` passed focused `checkcode` with zero
  messages.
- The touched target-component analyzer reports only its pre-existing `AGROW`
  `checkcode` message outside the refactored validation block.
- MATLAB synthetic smoke tests passed for valid category totals, missing
  category rows with caller-provided row-count error ID and numeric threshold
  formatting, voxel-sum mismatch with caller-provided mismatch error ID, and
  missing required columns.
- Static search confirms the target-component analyzer calls
  `mh_coverage_validate_category_totals` instead of keeping a local
  `findgroups` category-total validation loop.

## Phase 2AS Implementation Scope

Status: **completed**.

Phase 2AS applies the shared cell-row table builder to the VTA process launcher:

- Update `mh_vta_launch_process_workers` to build its worker job table through
  `mh_util_cell_rows_to_table`.
- Preserve the existing seven-column job table schema:
  `worker_index`, `subject_ids`, `pid`, `log_path`, `status`,
  `inner_command_path`, and `launch_command_path`.
- Keep job row values, dry-run behavior, command-file paths, and CSV readability
  unchanged.
- Leave DWI script-local `cell2table` calls out of scope for this VTA phase.

Phase 2AS validation target:

- `git diff --check`
- Focused `checkcode` for `mh_vta_launch_process_workers`.
- MATLAB dry-run smoke test proving a two-worker launch returns the same
  seven-column job table schema, writes command files, uses semicolon-separated
  subject chunks, and keeps string-valued job metadata readable.
- Static verification that VTA process launcher no longer calls `cell2table`
  directly.

Phase 2AS validation results:

- `git diff --check` passed.
- `mh_vta_launch_process_workers` passed focused `checkcode` with zero
  messages.
- MATLAB dry-run smoke test passed for a two-worker launch, confirming the
  seven-column job table schema, round-robin semicolon-separated subject chunks,
  command-file creation, dry-run status metadata, and CSV readability.
- Static search confirms `mh_vta_launch_process_workers` now calls
  `mh_util_cell_rows_to_table` instead of `cell2table` directly.

## Phase 2AT Implementation Scope

Status: **completed**.

Phase 2AT applies the shared cell-row table builder to VTA scheme comparison:

- Update `mh_fiber_compare_vta_schemes` to build its comparison table through
  `mh_util_cell_rows_to_table`.
- Preserve the existing comparison table schema and variable order.
- Preserve the existing `side` column type because the Markdown writer indexes
  it with `comparison.side{i}`.
- Keep VTA volume, Dice, activation-count, CSV, and Markdown behavior unchanged.

Phase 2AT validation target:

- `git diff --check`
- Focused `checkcode` for `mh_fiber_compare_vta_schemes`.
- MATLAB synthetic regression proving the shared helper with the comparison
  schema matches the previous `cell2table` behavior and keeps the `side` column
  cell-indexable.
- Static verification that VTA stimulation code no longer calls `cell2table`
  directly outside DWI scripts.

Phase 2AT validation results:

- `git diff --check` passed.
- `mh_fiber_compare_vta_schemes` passed focused `checkcode` with zero messages.
- MATLAB synthetic regression confirmed the comparison schema built through
  `mh_util_cell_rows_to_table` matches the previous `cell2table` behavior and
  preserves a cell-indexable `side` column for Markdown rendering.
- Static search confirms VTA stimulation code now uses `mh_util_cell_rows_to_table`
  for cell-row table construction; remaining direct `cell2table` calls are in
  DWI scripts outside this VTA phase.

## Phase 2AU Implementation Scope

Status: **completed**.

Phase 2AU removes the remaining local VTA MAT volume reader from scheme
comparison:

- Update `mh_fiber_compare_vta_schemes` to call the shared
  `mh_vta_read_vat_volume` helper.
- Remove the analyzer-local `read_vat_volume` function.
- Preserve the existing behavior for missing MAT files and MAT files without a
  `vatvolume` variable: return `NaN`.
- Keep scheme comparison CSV and Markdown schemas unchanged.

Phase 2AU validation target:

- `git diff --check`
- Focused `checkcode` for `mh_fiber_compare_vta_schemes` and
  `mh_vta_read_vat_volume`.
- MATLAB synthetic smoke test proving `mh_vta_read_vat_volume` returns the
  saved `vatvolume`, returns `NaN` for missing files, and returns `NaN` when the
  variable is absent.
- Static verification that `mh_fiber_compare_vta_schemes` no longer defines a
  local `read_vat_volume` function.

Phase 2AU validation results:

- `git diff --check` passed.
- `mh_fiber_compare_vta_schemes` and `mh_vta_read_vat_volume` passed focused
  `checkcode` with zero messages.
- MATLAB synthetic smoke tests passed for reading a saved `vatvolume`, returning
  `NaN` for a missing MAT file, and returning `NaN` when the MAT file lacks
  `vatvolume`.
- Static search confirms `mh_fiber_compare_vta_schemes` calls
  `mh_vta_read_vat_volume` and no longer defines a local `read_vat_volume`
  function.

## Phase 2AV Implementation Scope

Status: **completed**.

Phase 2AV removes the remaining hand-written output directory creation from VTA
scheme comparison:

- Update `mh_fiber_compare_vta_schemes` to call the shared
  `mh_util_make_dir` helper for its comparison output directory.
- Preserve output directory paths, CSV and Markdown filenames, comparison table
  schema, and report contents.
- Leave temporary Dice-resampling cleanup and optional activation CSV probing
  unchanged because those are file-existence checks rather than reusable
  directory setup.

Phase 2AV validation target:

- `git diff --check`
- Focused `checkcode` for `mh_fiber_compare_vta_schemes` and
  `mh_util_make_dir`.
- MATLAB synthetic smoke test proving `mh_util_make_dir` creates a missing
  output directory and is idempotent when called again.
- Static verification that `mh_fiber_compare_vta_schemes` no longer calls
  `mkdir` directly.

Phase 2AV validation results:

- `git diff --check` passed.
- `mh_fiber_compare_vta_schemes` and `mh_util_make_dir` passed focused
  `checkcode` with zero messages.
- MATLAB synthetic smoke test confirmed `mh_util_make_dir` creates a missing
  directory and remains idempotent when called again.
- Static search confirms `mh_fiber_compare_vta_schemes` no longer calls
  `mkdir` directly.

## Phase 2AW Implementation Scope

Status: **completed**.

Phase 2AW routes stimulation-parameter directory creation through the shared
utility layer:

- Update `mh_fiber_build_stimulation` to call `mh_util_make_dir` for both
  native-space and MNI-space stimulation folders.
- Preserve the exact folder paths built from `cfg.subjectDir`, `ea_nt`, and
  `cfg.stimLabel`.
- Preserve the saved `*_desc-stimparameters.mat` filenames and stimulation
  structure contents.
- Leave global Lead-DBS `ea_mkdir` usage outside `my_helper/fiber` out of scope.

Phase 2AW validation target:

- `git diff --check`
- Focused `checkcode` for `mh_fiber_build_stimulation` and `mh_util_make_dir`.
- Static verification that `mh_fiber_build_stimulation` no longer calls
  `ea_mkdir` directly.

Phase 2AW validation results:

- `git diff --check` passed.
- `mh_fiber_build_stimulation` and `mh_util_make_dir` passed focused
  `checkcode` with zero messages.
- Static search confirms `mh_fiber_build_stimulation` no longer calls
  `ea_mkdir` directly.

## Phase 2AX Implementation Scope

Status: **completed**.

Phase 2AX removes a remaining STN/SNr four-category assumption from
target-component validation:

- Add `mh_coverage_region_category_count(regionSpec)` under `core/coverage` to
  compute the membership-partition category count as `2^N` for `N` injected
  regions.
- Update `mh_fiber_run_stnsnr_target_component_vta_distribution` so coverage
  row-count validation and per-component category-total validation derive the
  expected category rows from the injected `regionSpec`.
- Preserve current STN/SNr behavior: two injected regions still require four
  category rows per component and threshold, and the expected coverage row count
  remains `190 * numel(thresholds) * 4 = 2280` for the current project data.
- Keep the STN/SNr-specific component QC target-count checks unchanged because
  they validate the project target-component catalog rather than region
  membership categories.

Phase 2AX validation target:

- `git diff --check`
- Focused `checkcode` for `mh_coverage_region_category_count` and the touched
  target-component analyzer.
- MATLAB synthetic smoke test proving the helper returns `2^N`, rejects missing
  or unsupported region specifications, and feeds the shared category-total
  validator for a three-region eight-category table.
- Static verification that target-component validation no longer hard-codes
  four category rows or 2280 coverage rows.

Phase 2AX validation results:

- `git diff --check` passed.
- `mh_coverage_region_category_count` passed focused `checkcode` with zero
  messages.
- The touched target-component analyzer reports only pre-existing `AGROW`
  `checkcode` messages outside the refactored validation logic.
- MATLAB synthetic smoke test confirmed the helper returns `2^N` for a
  three-region specification, rejects missing regions, rejects unsupported
  category schemes, and feeds `mh_coverage_validate_category_totals` for an
  eight-category table.
- Static search confirms target-component validation no longer hard-codes four
  category rows or 2280 coverage rows.

## Phase 2AY Implementation Scope

Status: **completed**.

Phase 2AY enforces the region-spec category-scheme contract at the shared
validation boundary:

- Update `mh_coverage_verify_region_spec` to reject non-`membership_partition`
  `regionSpec.categoryScheme` values before coverage analysis starts.
- Preserve the default behavior for legacy or minimal region specs without a
  `categoryScheme` field by treating the missing field as
  `membership_partition`.
- Preserve existing mask-path validation and caller-provided error-prefix
  behavior.

Phase 2AY validation target:

- `git diff --check`
- Focused `checkcode` for `mh_coverage_verify_region_spec` and
  `mh_coverage_region_category_count`.
- MATLAB synthetic smoke test proving a missing `categoryScheme` passes, an
  explicit `membership_partition` scheme passes, and an unsupported scheme
  raises the caller-prefixed `UnsupportedCategoryScheme` error.

Phase 2AY validation results:

- `git diff --check` passed.
- `mh_coverage_verify_region_spec` and `mh_coverage_region_category_count`
  passed focused `checkcode` with zero messages.
- MATLAB synthetic smoke test passed for a missing `categoryScheme`, explicit
  `membership_partition`, and unsupported scheme rejection with the
  caller-prefixed `UnsupportedCategoryScheme` error.

## Phase 2AZ Implementation Scope

Status: **completed**.

Phase 2AZ routes standard VTA path model-label resolution through the model
registry:

- Update `mh_fiber_vta_paths` so explicit `cfg.vta.modelKey` values resolve
  through `mh_vta_model_registry(...).modelLabel`.
- Preserve backward compatibility for legacy callers that provide only
  `cfg.vta.model` by first trying the registry aliases and then falling back to
  Lead-DBS `ea_simModel2Label` behavior.
- Preserve existing standard file names for current SimBio two-source and
  one-solve backends because both registry entries use `modelLabel = simbio`.
- Make unsupported explicit model keys fail at the registry boundary instead of
  silently falling back to SimBio paths.

Phase 2AZ validation target:

- `git diff --check`
- Focused `checkcode` for `mh_fiber_vta_paths` and `mh_vta_model_registry`.
- MATLAB synthetic smoke test proving SimBio and one-solve model keys produce
  standard `model-simbio` paths, legacy model strings still resolve, and an
  unsupported explicit model key raises `mh_vta_model_registry:UnsupportedModel`.

Phase 2AZ validation results:

- `git diff --check` passed.
- `mh_fiber_vta_paths` and `mh_vta_model_registry` passed focused `checkcode`
  with zero messages.
- MATLAB synthetic smoke test confirmed SimBio, one-solve, and one-solve alias
  model keys produce standard `model-simbio` paths, legacy model strings still
  resolve through the existing Lead-DBS fallback, and unsupported explicit model
  keys raise `mh_vta_model_registry:UnsupportedModel`.

## Phase 2BA Implementation Scope

Status: **completed**.

Phase 2BA adds explicit model-key support to one-side standard e-field path
lookups:

- Add an optional `ModelKey` parameter to `mh_fiber_vta_efield_path`.
- When `ModelKey` is provided, pass it to `mh_fiber_vta_paths` as
  `cfg.vta.modelKey` so path model labels resolve through the VTA registry.
- Preserve the existing `Model` parameter for legacy callers and keep the
  default path unchanged.

Phase 2BA validation target:

- `git diff --check`
- Focused `checkcode` for `mh_fiber_vta_efield_path` and `mh_fiber_vta_paths`.
- MATLAB synthetic smoke test proving default, legacy `Model`, and explicit
  `ModelKey` calls produce standard paths, and unsupported explicit model keys
  raise `mh_vta_model_registry:UnsupportedModel`.

Phase 2BA validation results:

- `git diff --check` passed.
- `mh_fiber_vta_efield_path` and `mh_fiber_vta_paths` passed focused
  `checkcode` with zero messages.
- MATLAB synthetic smoke test confirmed default, legacy `Model`, and explicit
  `ModelKey` calls produce standard `model-simbio` paths, and unsupported
  explicit model keys raise `mh_vta_model_registry:UnsupportedModel`.

## Phase 2BB Implementation Scope

Status: **completed**.

Phase 2BB externalizes the STN/SNr project VTA model key:

- Add `VtaModelKey` parameters to `mh_fiber_run_stnsnr_vta_coverage` and
  `mh_fiber_run_stnsnr_target_component_vta_distribution`, defaulting to
  `simbio`.
- Use `opts.VtaModelKey` when assigning `cfg.vta.modelKey`, resolving
  `cfg.vta.model`, and calling `mh_vta_run_stim_spec_tasks`.
- Ensure `mh_vta_run_stim_spec_tasks` writes the selected `ModelKey` back to
  `stimSpec.model` before `mh_fiber_set_stimulation` so the built stimulation
  structure, cfg metadata, task request, and backend dispatch stay synchronized.
- Add `STNSNR_VTA_MODEL_KEY` environment handling to STN/SNr project scripts
  and forward it through the subject-level process launcher.
- Record the selected model key in cohort and target-component manifests.
- Preserve default behavior because omitted parameters and environment
  variables still select the existing SimBio two-source backend.

Phase 2BB validation target:

- `git diff --check`
- Focused `checkcode` for touched STN/SNr analyzers and scripts.
- Static verification that the analyzers no longer hard-code `ModelKey`,
  `cfg.vta.modelKey`, or `mh_fiber_model_name` to `simbio`.
- MATLAB dry-run smoke test proving the parallel launcher forwards
  `STNSNR_VTA_MODEL_KEY` into worker command files.
- MATLAB synthetic smoke test proving `mh_vta_run_stim_spec_tasks` honors a
  non-default `ModelKey` in both `cfg.vta.modelKey` and the task request.

Phase 2BB validation results:

- `git diff --check` passed.
- Touched STN/SNr project scripts and `mh_vta_run_stim_spec_tasks` passed
  focused `checkcode` with zero messages.
- The two touched large STN/SNr analyzers report only pre-existing `AGROW`
  `checkcode` messages outside the refactored model-key plumbing.
- Static search confirms the analyzers no longer hard-code task `ModelKey`,
  `cfg.vta.modelKey`, or `mh_fiber_model_name` to `simbio`.
- MATLAB dry-run smoke test confirmed the subject-level launcher writes
  `STNSNR_VTA_MODEL_KEY='onesolve'` into the worker launch command file while
  redirecting output to a temporary directory.
- MATLAB synthetic smoke test with temporary build/run stubs confirmed
  `mh_vta_run_stim_spec_tasks` honors a non-default `ModelKey` in
  `cfg.vta.modelKey`, the built stimulation metadata, and the task request, and
  also defaults from `stimSpec.model` when `ModelKey` is omitted.

## Phase 2BC Implementation Scope

Status: **completed**.

Phase 2BC keeps stimulation specifications synchronized with externalized VTA
model keys before task execution:

- Add a `Model` option to `mh_fiber_stnsnr_stimspec_from_table` and use
  `opts.VtaModelKey` when STN/SNr analyzers build stimulation specs.
- Preserve default STN/SNr behavior by defaulting the helper option to
  `simbio`.
- Update `mh_fiber_set_stimulation` so a struct stimulation spec with a missing
  or empty `model` field inherits `cfg.vta.modelKey` instead of being normalized
  to `simbio` first.
- Preserve default behavior for existing default configs because
  `cfg.vta.modelKey` remains `simbio`.

Phase 2BC validation target:

- `git diff --check`
- Focused `checkcode` for `mh_fiber_stnsnr_stimspec_from_table`,
  `mh_fiber_set_stimulation`, and the touched STN/SNr analyzers.
- MATLAB synthetic smoke test proving STN/SNr stimspec construction accepts a
  non-default model key, direct `mh_fiber_set_stimulation` inherits
  `cfg.vta.modelKey` when `stimSpec.model` is absent, and default calls still
  produce `simbio`.

Phase 2BC validation results:

- `git diff --check` passed.
- `mh_fiber_stnsnr_stimspec_from_table` and `mh_fiber_set_stimulation` passed
  focused `checkcode` with zero messages.
- The two touched large STN/SNr analyzers report only pre-existing `AGROW`
  `checkcode` messages outside the refactored stimulation-spec plumbing.
- MATLAB synthetic smoke test confirmed STN/SNr stimspec construction accepts a
  non-default model key, direct `mh_fiber_set_stimulation` inherits
  `cfg.vta.modelKey` when `stimSpec.model` is absent, and default calls still
  produce `simbio`.

## Phase 2BD Implementation Scope

Status: **completed**.

Phase 2BD exposes task-level process dry-run control at the STN/SNr project
layer:

- Add `VtaProcessDryRun` to the shared execution-option plumbing and STN/SNr
  analyzers.
- Add `STNSNR_VTA_PROCESS_DRY_RUN` environment handling to STN/SNr project
  scripts and forward it through the subject-level process launcher.
- Record the selected task-level process dry-run flag in cohort and
  target-component manifests.
- Preserve default behavior because omitted parameters and environment
  variables still leave `cfg.vta.processDryRun = false`.

Phase 2BD validation target:

- `git diff --check`
- Focused `checkcode` for touched execution helper, analyzers, and scripts.
- MATLAB synthetic smoke test proving `mh_vta_apply_execution_options` applies
  `VtaProcessDryRun`.
- MATLAB dry-run smoke test proving the subject-level launcher forwards
  `STNSNR_VTA_PROCESS_DRY_RUN` into worker command files.

Phase 2BD validation results:

- `git diff --check` passed.
- Touched execution helper and STN/SNr project scripts passed focused
  `checkcode` with zero messages.
- The two touched large STN/SNr analyzers report only pre-existing `AGROW`
  `checkcode` messages outside the refactored execution-option plumbing.
- MATLAB synthetic smoke test confirmed `mh_vta_apply_execution_options` applies
  `VtaProcessDryRun`.
- MATLAB dry-run smoke test confirmed the subject-level launcher writes
  `STNSNR_VTA_PROCESS_DRY_RUN='true'` into the worker launch command file while
  redirecting output to a temporary directory.

## Phase 2BE Implementation Scope

Status: **completed**.

Phase 2BE applies region-derived category-total validation to STN/SNr cohort
coverage outputs:

- Update cohort output validation to receive the injected `regionSpec`.
- Use `mh_coverage_region_category_count(regionSpec)` and
  `mh_coverage_validate_category_totals` to validate each
  `subject_id x phase x protocol x condition_key x side x threshold` group.
- Preserve existing contact QC row-count, subject-count, contact-side-rule, and
  threshold monotonicity checks.
- Preserve default STN/SNr behavior because the injected two-region spec still
  expects four category rows per group.

Phase 2BE validation target:

- `git diff --check`
- Focused `checkcode` for the touched cohort analyzer and shared coverage
  validators.
- MATLAB synthetic smoke test proving cohort category totals pass for a
  three-region eight-category table and fail when a category row is missing.

Phase 2BE validation results:

- `git diff --check` passed.
- The touched cohort analyzer reports only pre-existing `AGROW` `checkcode`
  messages outside the refactored validation logic.
- Shared coverage validators passed focused `checkcode` with zero messages.
- MATLAB synthetic smoke test confirmed cohort-style category totals pass for a
  three-region eight-category table and fail when a category row is missing.

## Phase 2BF Implementation Scope

Status: **completed**.

Phase 2BF strengthens the shared category-total validator:

- Update `mh_coverage_validate_category_totals` to require that all category
  rows within a group report the same `total_vta_voxels` value before comparing
  `sum(voxel_count)` against that total.
- Reuse the caller-provided sum error ID/message for inconsistent totals because
  the output group is internally inconsistent in the same category-total
  contract.
- Preserve existing row-count validation, missing-column errors, custom column
  options, and tolerance behavior.

Phase 2BF validation target:

- `git diff --check`
- Focused `checkcode` for `mh_coverage_validate_category_totals`.
- MATLAB synthetic smoke test proving valid totals pass, inconsistent total
  columns fail, and sum mismatches still fail with the caller-provided error ID.

Phase 2BF validation results:

- `git diff --check` passed.
- `mh_coverage_validate_category_totals` passed focused `checkcode` with zero
  messages.
- MATLAB synthetic smoke test confirmed valid totals pass, inconsistent total
  columns fail, and sum mismatches still fail with the caller-provided error ID.

## Phase 2BG Implementation Scope

Status: **completed**.

Phase 2BG centralizes STN/SNr project-layer VTA option plumbing:

- Add a shared helper that registers the common STN/SNr `Vta*` parser
  parameters used by cohort coverage and target-component distribution.
- Add a shared helper that copies the selected STN/SNr VTA options into output
  manifests.
- Update both STN/SNr analyzers to use the shared helpers.
- Preserve all existing defaults, parser parameter names, manifest field names,
  and option value conversions.

Phase 2BG validation target:

- `git diff --check`
- Focused `checkcode` for the two new helpers and both touched analyzers.
- MATLAB synthetic smoke test proving the shared parser helper accepts
  non-default VTA options and the shared manifest helper produces the same VTA
  manifest fields and value types as the previous inline assignments.

Phase 2BG validation results:

- `git diff --check` passed.
- `mh_fiber_stnsnr_add_vta_parser_params` and
  `mh_fiber_stnsnr_add_vta_manifest_fields` passed focused `checkcode` with
  zero messages.
- The two touched large STN/SNr analyzers report only pre-existing `AGROW`
  `checkcode` messages outside the refactored option plumbing.
- MATLAB synthetic smoke test confirmed the shared parser helper accepts
  non-default VTA options and the shared manifest helper produces the expected
  VTA manifest fields and value types while preserving existing manifest fields.

## Phase 2BH Implementation Scope

Status: **completed**.

Phase 2BH completes the percentage-label requirement for 100 percent stacked
share figures:

- Update `mh_viz_stacked_share_bar` to place percentage labels inside readable
  nonzero stack segments.
- Preserve existing normalized-share calculation, color palette, figure titles,
  legend behavior, export behavior, and default figure size.
- Avoid clutter by labeling only stack segments above a configurable minimum
  share threshold while keeping all categories represented in the legend.

Phase 2BH validation completed:

- `git diff --check` passed with no whitespace errors.
- Focused `checkcode` for `mh_viz_stacked_share_bar` passed with zero
  messages.
- MATLAB synthetic smoke test confirmed stacked-share figures contain
  percentage text labels for visible segments, omit labels below the minimum
  share threshold, and still export PNG files in `-batch` mode.

## Phase 2BI Implementation Scope

Status: **completed**.

Phase 2BI routes manually built stimulation structures through the shared VTA
task harness:

- Add `mh_vta_run_built_stimulation_tasks` for callers that already have
  `cfg`, `S`, `options`, and `stimFolders`, but still need shared side-task
  construction and sequential/parpool/process dispatch.
- Update the sub-001 two-scheme pipeline to call this helper instead of the
  legacy compatibility wrappers.
- Set the sub-001 two-source and one-solve `cfg.vta.modelKey` values before
  building stimulation structures so cfg metadata, `S.model`, task requests,
  and backend dispatch stay synchronized.
- Preserve existing output path labels: the one-solve backend still resolves to
  the standard `model-simbio` file names through the VTA registry.

Phase 2BI validation completed:

- `git diff --check` passed.
- Focused `checkcode` for `mh_vta_run_built_stimulation_tasks` and the sub-001
  two-scheme pipeline passed with zero messages.
- MATLAB synthetic smoke test with a temporary `mh_vta_compute` stub confirmed
  the built-stimulation helper creates ordered side tasks, canonicalizes
  `onesolve` to `simbio_onesolve`, forwards model/atlas/output-space options,
  and dispatches through `mh_vta_run_compute_tasks` without real FEM data.
- Static verification confirmed the sub-001 two-scheme pipeline no longer calls
  the legacy `mh_fiber_ensure_vta*` wrappers.

## Phase 2BJ Implementation Scope

Status: **completed**.

Phase 2BJ removes duplicated task assembly from the stim-spec helper:

- Keep `mh_vta_run_stim_spec_tasks` responsible for normalizing the requested
  model key, attaching the stimulation specification to `cfg`, and building
  `S`, `options`, and `stimFolders`.
- Delegate the already-built stimulation dispatch to
  `mh_vta_run_built_stimulation_tasks` so stim-spec callers and manual
  stimulation callers share side-task construction, request forwarding, and
  execution-mode selection.
- Preserve the public return values and ordering of
  `mh_vta_run_stim_spec_tasks`: `taskResults`, `taskArray`, `cfg`, `S`,
  `options`, and `stimFolders`.

Phase 2BJ validation completed:

- `git diff --check` passed.
- Focused `checkcode` for `mh_vta_run_stim_spec_tasks` and
  `mh_vta_run_built_stimulation_tasks` passed with zero messages.
- MATLAB synthetic smoke test with temporary `mh_fiber_build_stimulation` and
  `mh_vta_run_built_stimulation_tasks` stubs confirmed
  `mh_vta_run_stim_spec_tasks` sets `stimSpec.model`, builds stimulation once,
  forwards all VTA options to the built-stimulation helper, and preserves output
  ordering without real FEM data.
- Static verification confirmed `mh_vta_run_stim_spec_tasks` no longer calls
  `mh_vta_make_compute_task` or `mh_vta_run_compute_tasks` directly.

## Phase 2BK Implementation Scope

Status: **completed**.

Phase 2BK removes duplicated STN/SNr manifest conductivity defaults:

- Move `gray_matter_conductivity_s_per_m` and
  `white_matter_conductivity_s_per_m` manifest fields into
  `mh_fiber_stnsnr_add_vta_manifest_fields`.
- Populate those fields from `mh_vta_settings()` so manifest metadata and Horn
  VTA defaults share one source.
- Remove analyzer-local hardcoded `0.33` and `0.14` assignments from cohort
  coverage and target-component distribution manifests.
- Preserve existing manifest field names and numeric values.

Phase 2BK validation completed:

- `git diff --check` passed.
- `mh_fiber_stnsnr_add_vta_manifest_fields` passed focused `checkcode` with
  zero messages; the two touched large STN/SNr analyzers still report only
  pre-existing `AGROW` messages outside the manifest change.
- MATLAB synthetic smoke test confirmed the shared manifest helper writes
  conductivity values from `mh_vta_settings()` while preserving existing VTA
  manifest option fields.
- Static verification confirmed the STN/SNr analyzers no longer hard-code
  manifest conductivity values; those fields are assigned only in the shared
  manifest helper.

## Phase 2BL Implementation Scope

Status: **completed**.

Phase 2BL centralizes the STN/SNr project default VTA gray-matter atlas:

- Add `mh_fiber_stnsnr_default_vta_gm_atlas` as the single source for the
  default STN/SNr `VtaGmAtlas` value.
- Update the shared STN/SNr VTA parser helper and STN/SNr project scripts to
  use this helper as their environment-variable fallback/default.
- Preserve the existing default value, `DISTAL Minimal (Ewert 2017)`, and keep
  `STNSNR_VTA_GM_ATLAS`/`VtaGmAtlas` injection behavior unchanged.

Phase 2BL validation completed:

- `git diff --check` passed.
- Focused `checkcode` for the new helper, the shared parser helper, and touched
  STN/SNr project scripts passed with zero messages.
- MATLAB synthetic smoke test confirmed the helper returns the existing default
  atlas, the parser default uses the helper value, and explicit parser
  injection still overrides the default.
- Static verification confirmed STN/SNr VTA scripts no longer duplicate the
  default `DISTAL Minimal (Ewert 2017)` string; the default appears only in
  documentation and `mh_fiber_stnsnr_default_vta_gm_atlas`.

## Phase 2BM Implementation Scope

Status: **completed**.

Phase 2BM centralizes the STN/SNr project default VTA model key:

- Add `mh_fiber_stnsnr_default_vta_model_key` as the single source for the
  default STN/SNr `VtaModelKey` value.
- Update the shared STN/SNr VTA parser helper and STN/SNr project scripts to
  use this helper as their environment-variable fallback/default.
- Preserve the existing default value, `simbio`, and keep
  `STNSNR_VTA_MODEL_KEY`/`VtaModelKey` injection behavior unchanged.

Phase 2BM validation completed:

- `git diff --check` passed.
- Focused `checkcode` for the new helper, the shared parser helper, and touched
  STN/SNr project scripts passed with zero messages.
- MATLAB synthetic smoke test confirmed the helper returns `simbio`, the parser
  default uses the helper value, and explicit parser injection still overrides
  the default.
- Static verification confirmed STN/SNr VTA project scripts and the shared
  parser no longer duplicate the default `simbio` model-key fallback.

## Phase 2BN Implementation Scope

Status: **completed**.

Phase 2BN centralizes VTA task execution defaults:

- Add `mh_vta_default_execution_options` as the single source for default
  task-execution settings: execution mode, worker count, MATLAB executable,
  Conda environment, process dry-run flag, process work directory, poll
  interval, and timeout.
- Update `mh_fiber_default_config`, STN/SNr parser defaults, task process
  execution settings, and process worker launcher defaults to read from this
  helper.
- Update STN/SNr project scripts to use the shared defaults as environment
  fallbacks while preserving all existing environment variable names and default
  values.
- Preserve existing default behavior: sequential execution, one worker,
  `/Applications/MATLAB_R2024b.app/bin/matlab`, Conda env `leaddbs`, poll
  interval `2`, timeout `0`, empty process work directory, and process dry-run
  disabled.

Phase 2BN validation completed:

- `git diff --check` passed.
- Focused `checkcode` for the new helper and touched VTA/STN/SNr execution
  default callers passed with zero messages.
- MATLAB synthetic smoke test confirmed `mh_fiber_default_config`, the STN/SNr
  parser defaults, and `mh_vta_execution_config` use
  `mh_vta_default_execution_options`.
- MATLAB dry-run smoke test confirmed the subject-level process launcher and
  task-level process dry-run path still prepare metadata without launching real
  workers or running FEM.
- Static verification confirmed VTA/STN/SNr execution-default call sites no
  longer duplicate the MATLAB executable and Conda environment defaults outside
  `mh_vta_default_execution_options`.

## Phase 2BO Implementation Scope

Status: **completed**.

Phase 2BO centralizes the generic VTA default model key:

- Add `mh_vta_default_model_key` as the generic fallback model key for VTA
  stimulation specs, task requests, config defaults, and path lookup defaults.
- Update fallback/default call sites to use this helper while leaving explicit
  semantic model selections unchanged, including the compatibility
  `mh_fiber_ensure_vta` wrapper, the sub-001 two-source branch, and the model
  registry entry itself.
- Update the STN/SNr project default model-key helper to delegate to the generic
  VTA helper so project defaults and core defaults stay aligned.
- Preserve existing default behavior: omitted VTA model keys still select
  `simbio`.

Phase 2BO validation completed:

- `git diff --check` passed.
- Focused `checkcode` for the new helper and touched model-default callers
  passed with zero messages.
- MATLAB synthetic smoke test confirmed default config, stimulation-spec
  helpers, VTA path lookup, compute-task fallback, stubbed `mh_vta_compute`
  fallback, and STN/SNr project defaults all resolve to the generic default
  model key.
- Static verification confirmed fallback/default call sites no longer duplicate
  the default `simbio` model key outside `mh_vta_default_model_key`; explicit
  model selections still use `simbio` where semantically intended.

## Phase 2BP Implementation Scope

Status: **completed**.

Phase 2BP centralizes generic VTA output-space defaults:

- Add `mh_vta_default_config_space` for the default config/stimulation-spec
  space string, currently `native_and_mni`.
- Add `mh_vta_output_spaces_from_config` to derive default request output
  spaces from `cfg.vta.space`, preserving the existing rule:
  `native_and_mni` produces `{'native', 'mni'}` and other/missing values fall
  back to `{'mni'}` where the existing task helpers did so.
- Update config defaults, stimulation-spec defaults, task helpers, backend
  request fallbacks, and missing-file checks to use these helpers.
- Preserve explicit output-space choices, including STN/SNr project requests
  for `{'mni'}` and compatibility wrapper requests for `{'native', 'mni'}`.

Phase 2BP validation completed:

- `git diff --check` passed.
- Focused `checkcode` for the new helpers and touched output-space default
  callers passed with zero messages.
- MATLAB synthetic smoke test confirmed default config/stimSpec space values,
  task helper config-derived output spaces, backend/missing-file generic
  fallback behavior, model-registry output metadata, and explicit `{'mni'}`
  overrides are unchanged.
- Static verification confirmed default output-space call sites no longer
  duplicate the `native_and_mni` and `{'native', 'mni'}` defaults outside the
  shared helpers and explicit semantic selections.

## Phase 2BQ Implementation Scope

Status: **completed**.

Phase 2BQ centralizes the generic VTA gray-matter atlas fallback:

- Add `mh_vta_default_gm_atlas` as the generic fallback used by
  `mh_fiber_default_config`.
- Update the default config to read `cfg.vta.gmAtlas` from this helper instead
  of embedding the atlas string directly.
- Preserve the existing fallback value, `DISTAL Nano (Ewert 2017)`.
- Keep project-level atlas injection unchanged: STN/SNr continues to use
  `mh_fiber_stnsnr_default_vta_gm_atlas` and explicit `VtaGmAtlas`/environment
  overrides.

Phase 2BQ validation completed:

- `git diff --check` passed.
- Focused `checkcode` for the new helper and `mh_fiber_default_config` passed
  with zero messages.
- MATLAB synthetic smoke test confirmed `mh_fiber_default_config` uses the
  helper value while preserving model, output-space, and execution defaults.
- Static verification confirmed the generic fallback
  `DISTAL Nano (Ewert 2017)` string appears only in `mh_vta_default_gm_atlas`
  and documentation.

## Phase 2BR Implementation Scope

Status: **completed**.

Phase 2BR centralizes VTA task request defaults that are currently duplicated
between the stim-spec task path and the already-built stimulation task path:

- Add `mh_vta_task_request_defaults` as the shared source for default
  `ModelKey`, `Force`, `OutputSpaces`, and `GmAtlas` parser values.
- Keep stim-spec model precedence unchanged: explicit `stimSpec.model` wins over
  `cfg.vta.modelKey`, which wins over `mh_vta_default_model_key`.
- Keep built-stimulation model precedence unchanged: `cfg.vta.modelKey` wins
  over `mh_vta_default_model_key`.
- Preserve existing force, output-space, and gray-matter atlas fallbacks while
  removing duplicated local helper functions from the two task runners.

Phase 2BR validation completed:

- `git diff --check` passed.
- Focused `checkcode` for the new helper and touched task runners passed with
  zero messages.
- MATLAB synthetic smoke test covered task-default precedence for stim-spec and
  built-stimulation paths without running FEM.
- Static verification confirmed `mh_vta_run_built_stimulation_tasks` and
  `mh_vta_run_stim_spec_tasks` no longer carry duplicated local default helper
  functions.

## Phase 2BS Implementation Scope

Status: **completed**.

Phase 2BS centralizes SimBio backend request/config fallback helpers:

- Add `mh_vta_request_field` as the shared model-layer accessor for optional
  request fields with explicit fallback values.
- Add `mh_vta_config_force` as the shared model-layer accessor for
  `cfg.forceRecomputeVTA`.
- Update the SimBio two-source and one-solve backends to use these helpers.
- Preserve existing semantics: a present request field wins even when empty,
  and missing `cfg.forceRecomputeVTA` means `false`.

Phase 2BS validation completed:

- `git diff --check` passed.
- Focused `checkcode` for the new helpers and touched backends passed with zero
  messages.
- MATLAB synthetic smoke test covered request-field fallback behavior and config
  force fallback behavior without running FEM.
- Static verification confirmed the SimBio backends no longer carry duplicated
  local `request_field` or `cfg_force` helper functions.

## Phase 2BT Implementation Scope

Status: **completed**.

Phase 2BT centralizes VTA config-field fallback lookup used by execution
configuration and process-task settings:

- Add `mh_vta_config_field` as the shared accessor for optional `cfg.vta`
  fields with explicit fallback values.
- Update `mh_vta_execution_config` and `mh_vta_run_compute_tasks_process` to use
  this helper for `cfg.vta` execution fields.
- Update process-task root config lookups to use the existing
  `mh_util_get_field` helper instead of local `get_cfg_option`.
- Preserve existing semantics: a present `cfg.vta` field wins even when empty,
  and missing root or VTA fields use their previous fallbacks.

Phase 2BT validation completed:

- `git diff --check` passed.
- Focused `checkcode` for the new helper and touched execution/process files
  passed with zero messages.
- MATLAB synthetic smoke test covered VTA config-field fallback and
  `mh_vta_execution_config` mode/worker resolution without running FEM.
- Static verification confirmed the touched execution/process files no longer
  carry local `get_vta_option` or `get_cfg_option` helper functions.

## Phase 2BU Implementation Scope

Status: **completed**.

Phase 2BU completes use of the shared VTA force fallback helper:

- Update `mh_vta_task_request_defaults` to use `mh_vta_config_force` instead of
  carrying a local `resolve_force` helper.
- Update the two compatibility wrappers, `mh_fiber_ensure_vta` and
  `mh_fiber_ensure_vta_onesolve`, to populate `request.force` through
  `mh_vta_config_force`.
- Preserve existing behavior for normal configs where `cfg.forceRecomputeVTA`
  is present; missing force config now follows the shared fallback of `false`.

Phase 2BU validation completed:

- `git diff --check` passed.
- Focused `checkcode` for touched force-default callers passed with zero
  messages.
- MATLAB synthetic smoke test covered `mh_vta_task_request_defaults` and the
  shared config-force fallback without running FEM.
- Static verification confirmed VTA request force defaults no longer duplicate
  direct `cfg.forceRecomputeVTA` fallback logic outside `mh_vta_config_force`
  and project-level assignment sites.

## Phase 2BV Implementation Scope

Status: **completed**.

Phase 2BV removes the remaining local option-field accessor from VTA execution
option application:

- Update `mh_vta_apply_execution_options` to use the existing
  `mh_util_get_field` helper for optional parser-result fields.
- Remove the local `get_option` helper from `mh_vta_apply_execution_options`.
- Preserve existing semantics: a present option field wins, and a missing field
  keeps the current `cfg.vta` value.

Phase 2BV validation completed:

- `git diff --check` passed.
- Focused `checkcode` for `mh_vta_apply_execution_options` passed with zero
  messages.
- MATLAB synthetic smoke test covered default-preserving and explicit override
  execution-option application without running FEM.
- Static verification confirmed `mh_vta_apply_execution_options` no longer
  carries a local `get_option` helper.

## Phase 2BW Implementation Scope

Status: **completed**.

Phase 2BW adds a copied-subset validation runner for the deferred real FEM and
execution-mode equivalence gates:

- Add an STN/SNr project-layer validation runner that copies a selected 1-2
  subject subset from the real Lead-DBS subject root into a fresh validation
  root before running VTA coverage.
- Keep the real `/Volumes/VAL/STNSNr/derivatives/leaddbs` subject root
  read-only; the runner must fail if the destination validation root already
  exists, rather than overwriting non-Git outputs.
- Run validation modes through the existing `mh_fiber_run_stnsnr_vta_coverage`
  entry point so copied-subset validation exercises the same VTA facade,
  task harness, atlas injection, and coverage pipeline as cohort runs.
- Support `sequential`, `process`, and `parpool` mode selection, with process
  work directories and cohort outputs isolated under the validation root.
- Default to the first workbook subject when no explicit subject filter is
  provided, so a single-subject smoke can be launched without editing code.

Phase 2BW validation completed:

- `git diff --check` passed.
- Focused `checkcode` for the new validation runner passed with zero messages.
- MATLAB synthetic prepare-only smoke using temporary fake subject roots proved
  the runner creates a fresh validation root, copies the selected subject
  directory, writes a validation manifest, and refuses to overwrite an existing
  validation root.
- Real prepare-only setup copied `SNr003` / `sub-LinJia` into
  `/Volumes/VAL/STNSNr/validation/vta_refactor_subset_20260703_234615` without
  running FEM or cohort coverage; the copied subject directory is 3.8G and the
  validation manifest records `prepare_only = true`.
- Static verification confirmed the runner treats the real STN/SNr subject root
  only as `SourceSubjectRoot`, and mode-specific cohort outputs/process work
  directories are built under the fresh validation root.

## Phase 2BX Implementation Scope

Status: **completed**.

Phase 2BX supports two-stage copied-subset validation after a prepare-only
setup has created the copied subject root:

- Add an explicit `ReusePreparedRoot` option to
  `mh_fiber_run_stnsnr_vta_subset_validation`.
- Keep default behavior unchanged: an existing validation root still fails fast
  unless `ReusePreparedRoot` is explicitly true.
- When `ReusePreparedRoot` is true, require the copied subject root and selected
  copied subject directories to already exist, and do not copy or overwrite
  subject data again.
- Allow the prepared
  `/Volumes/VAL/STNSNr/validation/vta_refactor_subset_20260703_234615` root to
  be used for subsequent sequential/process/parpool validation runs.

Phase 2BX validation completed:

- `git diff --check` passed.
- Focused `checkcode` for the validation runner passed with zero messages.
- MATLAB synthetic smoke proved existing roots still fail by default, while
  explicit `ReusePreparedRoot = true` accepts a prepared copied-subject root
  without copying again and writes a timestamped manifest instead of
  overwriting the prepare-only manifest.
- Static verification confirmed the default existing-root protection remains in
  place.

## Phase 2BY Validation Audit

Status: **completed**.

Phase 2BY ran copied-root execution-mode validation on the prepared
`SNr003` / `sub-LinJia` validation subset:

- Validation root:
  `/Volumes/VAL/STNSNr/validation/vta_refactor_subset_20260703_234615`.
- Ran `sequential`, `process`, and `parpool` modes with `ForceVta = false` and
  `ForceOutputs = true`.
- All VTA/e-field tasks reused existing copied-subject outputs; this audit did
  not run real FEM generation.
- `process` mode launched isolated worker processes under
  `process_tasks/process`.
- `parpool` mode launched a two-worker MATLAB process pool.
- Mode-specific cohort outputs were written under
  `summary/vta/sequential`, `summary/vta/process`, and
  `summary/vta/parpool`.

Phase 2BY validation completed:

- `sequential`, `process`, and `parpool` mode runs completed successfully on the
  copied subject root.
- Exact table comparison confirmed identical
  `cohort_vta_coverage_long.csv` outputs across all three modes: 96 data rows.
- Exact table comparison confirmed identical
  `cohort_contact_mapping_qc.csv` outputs across all three modes: 14 data rows.
- Remaining deferred gate: real `ForceVta = true` FEM process/parpool execution
  and any full-cohort timing comparison.

## Phase 2BZ Validation Scope

Status: **completed**.

Phase 2BZ runs the first real FEM copied-subset validation after the safe
mode-equivalence audit:

- Use a fresh validation root so the completed
  `/Volumes/VAL/STNSNr/validation/vta_refactor_subset_20260703_234615`
  `ForceVta = false` evidence remains unchanged.
- Copy the same one-subject subset, `SNr003` / `sub-LinJia`, from the real
  STN/SNr Lead-DBS subject root into the fresh validation root.
- Run `mh_fiber_run_stnsnr_vta_subset_validation` with `ForceVta = true`,
  `ForceOutputs = true`, `Modes = {'process'}`, and two process workers.
- Keep all real FEM writes confined to the copied validation root.
- Defer parpool `ForceVta = true` and full-cohort timing until the process-mode
  FEM gate completes successfully.

Phase 2BZ validation completed:

- Fresh copied validation root created:
  `/Volumes/VAL/STNSNr/validation/vta_refactor_subset_20260703_235948`.
- Prepare-only setup copied `SNr003` / `sub-LinJia` into the fresh root and
  wrote `validation_manifest.json` with `prepare_only = true`.
- `process` mode with `ForceVta = true`, `ForceOutputs = true`, and two workers
  completed on the copied subject root.
- Process task payload/result accounting completed: 14 non-sidecar payload MAT
  files and 14 non-sidecar result MAT files.
- Worker logs confirm actual FEM generation, including `Generating
  VTA/e-field`, `Loading headmodel`, and `Writing files`; final retained worker
  logs contain generation evidence for both process workers.
- Copied subject output contains 56 non-sidecar e-field NIfTI files and 28
  non-sidecar binary VTA NIfTI files.
- Resulting copied-root cohort outputs are present under `summary/vta/process`;
  `cohort_vta_coverage_long.csv` has 96 data rows and
  `cohort_contact_mapping_qc.csv` has 14 data rows.
- Compared with the earlier `ForceVta = false` copied-root process run, all
  non-path coverage columns and all non-path contact-QC columns matched exactly;
  differences were limited to validation-root-specific path strings.
- No writes were made to the real `/Volumes/VAL/STNSNr/derivatives/leaddbs`
  subject root.
- Remaining deferred gate: real `ForceVta = true` parpool execution and any
  full-cohort timing comparison.

## Phase 2CA Validation Scope

Status: **completed**.

Phase 2CA runs real FEM copied-subset validation in parpool mode:

- Use a fresh validation root so the completed process-mode real FEM evidence in
  `/Volumes/VAL/STNSNr/validation/vta_refactor_subset_20260703_235948` remains
  unchanged.
- Copy `SNr003` / `sub-LinJia` from the real STN/SNr Lead-DBS subject root into
  the fresh validation root.
- Run `mh_fiber_run_stnsnr_vta_subset_validation` with `ForceVta = true`,
  `ForceOutputs = true`, `Modes = {'parpool'}`, and two parpool workers.
- Keep all real FEM writes confined to the copied validation root.
- Compare parpool cohort outputs against the Phase 2BZ process-mode real FEM
  outputs, ignoring validation-root-specific path columns.

Phase 2CA validation completed:

- Fresh copied validation root created:
  `/Volumes/VAL/STNSNr/validation/vta_refactor_subset_20260704_000946`.
- Prepare-only setup copied `SNr003` / `sub-LinJia` into the fresh root and
  wrote `validation_manifest.json` with `prepare_only = true`.
- `parpool` mode with `ForceVta = true`, `ForceOutputs = true`, and two workers
  completed on the copied subject root.
- Run output confirmed a two-worker MATLAB process pool and actual FEM
  generation, including `Generating VTA/e-field`, `Loading headmodel`, and
  `Writing files`.
- Copied subject output contains 56 non-sidecar e-field NIfTI files and 28
  non-sidecar binary VTA NIfTI files.
- Resulting copied-root cohort outputs are present under `summary/vta/parpool`;
  `cohort_vta_coverage_long.csv` has 96 data rows and
  `cohort_contact_mapping_qc.csv` has 14 data rows.
- Compared with Phase 2BZ process-mode real FEM outputs, all non-path coverage
  columns and all non-path contact-QC columns matched exactly.
- Process-vs-parpool NIfTI comparison on matching stimulation outputs showed:
  14 binary VTA NIfTI files matched exactly, 14 e-field NIfTI files had maximum
  absolute difference `3.43323e-4`, and 14 Gaussian-smoothed e-field NIfTI files
  had maximum absolute difference `1.05936e-8`.
- No writes were made to the real `/Volumes/VAL/STNSNr/derivatives/leaddbs`
  subject root.
- Remaining deferred gate: full-cohort timing comparison.

## Phase 2CB Validation Scope

Status: **completed**.

Phase 2CB runs a non-destructive full-cohort timing and numerical regression
audit for the cohort aggregation layer:

- Use the real STN/SNr subject root only as read-only input:
  `/Volumes/VAL/STNSNr/derivatives/leaddbs`.
- Run `mh_fiber_run_stnsnr_vta_coverage` with `CohortOnly = true` into a fresh
  validation output directory under `/Volumes/VAL/STNSNr/validation`.
- Measure wall-clock runtime for full-cohort cohort-output regeneration.
- Compare regenerated full-cohort CSV outputs against the existing real
  `/Volumes/VAL/STNSNr/summary/vta` baseline.
- Do not run FEM, do not recompute subject-level VTA/e-field files, and do not
  write subject-level reports/manifests under the real subject root.

Phase 2CB validation completed:

- Fresh full-cohort validation output directory created:
  `/Volumes/VAL/STNSNr/validation/vta_full_cohort_cohortonly_20260704_005937`.
- `CohortOnly = true` completed for all 16 subjects in `7.303271` seconds.
- Regenerated `cohort_vta_coverage_long.csv` had 1536 rows x 25 columns and
  matched the existing `/Volumes/VAL/STNSNr/summary/vta` baseline exactly.
- Regenerated `cohort_contact_mapping_qc.csv` had 194 rows x 20 columns and
  matched the existing baseline exactly.
- Validation output size was 6.5M and was confined to the fresh validation
  directory.
- No FEM, subject-level VTA/e-field generation, or subject-level report/manifest
  writes were performed.
- Remaining deferred gate: destructive/full-FEM full-cohort timing comparison,
  which would require copying or explicitly approving all 16 subjects for a
  full execution run.

## Phase 2CC Feasibility Audit

Status: **completed**.

Phase 2CC audited the storage boundary for a destructive/full-FEM full-cohort
timing run without creating or deleting files:

- `/Volumes/VAL` capacity: 3.6T total, 1.6T used, 2.0T available.
- The real STN/SNr Lead-DBS subject root contains 84 `sub-*` directories, but
  the stimulation workbook selects 16 cohort subjects.
- The 16 workbook-selected subject directories total approximately 86G:
  `sub-LinJia` 3.8G, `sub-HuFengXian` 4.8G, `sub-YuDongJian` 4.9G,
  `sub-WuYueFen` 4.4G, `sub-LiPing` 4.8G, `sub-MaoXiaoMing` 4.6G,
  `sub-ShengGuoLiang` 4.5G, `sub-ZhangXiaoHong` 5.0G,
  `sub-ZhengXiangQuan` 4.7G, `sub-ZhaoPeiGen` 5.5G,
  `sub-ChenLingHua` 4.8G, `sub-FanDongDong` 4.5G, `sub-HuangDan` 7.1G,
  `sub-ZhangMing` 14G, `sub-GengHui` 5.1G, and `sub-ChenMeiJu` 4.4G.
- Existing copied-subset validation roots occupy approximately 3.9G, 3.9G, and
  3.8G; the full-cohort cohort-only validation output occupies 6.5M.

Phase 2CC conclusion:

- Disk capacity is sufficient for a copied full-cohort validation root.
- The run remains high-cost because it would copy about 86G and run real FEM
  across all selected subjects.
- Do not launch destructive/full-FEM full-cohort timing automatically; it should
  be a separate explicitly approved run with the intended execution mode,
  worker count, timeout, and cleanup/retention policy.

## Phase 2CD Final Refactor Gate

Status: **completed with explicit full-FEM full-cohort opt-in gate**.

The VTA refactor is ready under the completed validation envelope:

- Process-backed and parpool-backed execution paths both completed real FEM on a
  copied STNSNr subject root with writes confined to validation directories.
- Sequential, process, and parpool copied-subset cohort outputs matched exactly
  for coverage and contact-QC CSVs after excluding validation-root-specific path
  columns.
- Full-cohort cohort aggregation completed non-destructively with
  `CohortOnly = true` in 7.303271 seconds and matched the existing full-cohort
  baseline exactly.
- The copied full-cohort FEM run is a stress/timing and retention-policy gate,
  not a remaining ordinary refactor task.

Recommended launch policy for the optional copied full-cohort FEM gate:

- Run it only after explicit approval of execution mode, worker count, timeout,
  and retention/cleanup policy.
- Prefer one full-cohort `process` run first, because process workers isolate
  MATLAB state and already matched parpool behavior on the copied real-FEM
  subset.
- Use a fresh validation root under `/Volumes/VAL/STNSNr/validation` and keep
  the real subject root read-only.
- Retain the validation root until coverage CSVs, contact-QC CSVs, worker logs,
  and NIfTI counts have been reviewed. If cleanup is approved later, move the
  copied root to Trash instead of permanently deleting it.

Proposed approved-run command:

```matlab
cd('/Users/mojackhu/Github/leaddbs');
addpath(genpath(pwd));

r = mh_fiber_run_stnsnr_vta_subset_validation( ...
    'Modes', {'process'}, ...
    'MaxSubjects', 16, ...
    'ForceVta', true, ...
    'ForceOutputs', true, ...
    'ParallelWorkers', 4, ...
    'VtaProcessTimeoutSeconds', 28800);
```

After the optional process run passes, a second copied-root parpool run can be
approved separately if full-cohort process-vs-parpool timing is still needed.

## Phase 2CE Real-Root Full-Cohort Rerun Plan

Status: **approved for execution**.

Phase 2CE reruns the observed STN/SNr full-cohort VTA generation on the real
Lead-DBS subject root after moving the previous outputs to Trash:

- Execution target: `/Volumes/VAL/STNSNr/derivatives/leaddbs`.
- Subject scope: the 16 subjects selected by
  `/Users/mojackhu/Research/STNSNr/summary/cohort/subj/followup_stimulation.xlsx`.
- VTA model: `simbio`.
- VTA FEM gray-matter atlas: `Custom_Ewert_Zhang_Middlebrooks`.
- FEM gray-matter surface policy: use the atlas `gm_mask.nii.gz` with the
  existing Lead-DBS/Horn surface behavior, equivalent to an approximately 0.5
  relative-intensity surface threshold.
- Coverage classification atlas:
  `/Users/mojackhu/Github/leaddbs/templates/space/MNI152NLin2009bAsym/atlases/Custom_Ewert_Zhang_Middlebrooks0.05`.
- ROI/connected-region binary definition remains
  `Custom_Ewert_Zhang_Middlebrooks > 0.05`.
- Execution mode: task-level `process` with 4 VTA workers.
- Target-component outputs under
  `/Volumes/VAL/STNSNr/summary/vta/target_component_distribution` remain out of
  scope and must not be moved or regenerated in this run.

Deletion and retention policy:

- Move previous outputs to Trash; do not permanently delete non-Git files.
- Preserve original relative paths in the Trash archive for recovery.
- Move all selected-subject `stimulations/**/**/*model-simbio_hemi-*` payloads
  and matching AppleDouble sidecars.
- Move each selected subject's
  `connectomics/stnsnr_vta_coverage` directory.
- Move observed cohort outputs, figures, logs, manifest files, and
  `parallel_jobs_latest.csv` under `/Volumes/VAL/STNSNr/summary/vta`, while
  preserving `target_component_distribution`.

Run audit policy:

- Create a timestamped audit directory under
  `/Volumes/VAL/STNSNr/validation`.
- Save selected-subject, pre-run VTA/e-field, pre-run subject-output, pre-run
  cohort-output, checksum, and Trash manifest files before starting MATLAB.
- Record shell `/usr/bin/time`, MATLAB `tic/toc`, and process worker logs.
- Validate regenerated per-subject reports, manifests, 48 thresholded coverage
  masks per subject, cohort table dimensions, manifest model settings, and
  worker logs after the run.

This run is a model-configuration update from `DISTAL Minimal (Ewert 2017)` to
`Custom_Ewert_Zhang_Middlebrooks`; regenerated VTA outputs are not expected to
match the old full-cohort numerical baseline exactly.

### Phase 2CE Attempt 1 Failure and Fix Gate

Status: **failed before full-cohort completion; code fix required before
restart**.

Attempt 1 used the approved process-mode command and audit root
`/Volumes/VAL/STNSNr/validation/vta_full_cohort_realroot_rerun_20260704_024228`.
The previous observed outputs had already been moved to
`/Volumes/VAL/.Trashes/501/stnsnr_vta_full_rerun_20260704_024228` with original
paths preserved.

Attempt 1 runtime and boundary status:

- Shell elapsed time: 1208.77 seconds.
- MATLAB elapsed time: 1191.527392 seconds.
- `sub-LinJia` completed subject-level regeneration, including 48 thresholded
  coverage VTA masks.
- `sub-HuFengXian` failed during its first condition, after writing 16
  `model-simbio_hemi-*` files and no coverage masks.
- No subject lock remained after the failed run.
- No cohort-level replacement outputs were accepted as final.

Observed failure:

- Main MATLAB error:
  `One or more VTA process tasks failed: Failed to load gray matter mask.`
- Worker error:
  `Function GUNZIP was unable to find file .../sub-HuFengXian/atlases/Custom_Ewert_Zhang_Middlebrooks/lh/GPe.nii.gz`.

Root-cause assessment:

- `ea_fem_getmask` calls `ea_ptspecific_atl` when Horn/SimBio needs a native
  atlas-derived gray-matter mask.
- `ea_ptspecific_atl` materializes the subject-space atlas by copying, warping,
  gunzipping, gzipping, and rebuilding `atlas_index.mat` under
  `sub-*/atlases/<atlas>`.
- In process mode, left and right VTA workers can enter this subject-space atlas
  materialization at the same time on a subject whose
  `Custom_Ewert_Zhang_Middlebrooks/gm_mask` does not yet exist.
- The first worker can temporarily remove or rewrite `.nii.gz` files while the
  second worker tries to read them, producing the missing `GPe.nii.gz` failure.

Required fix before restart:

- Add a preflight step in the VTA task orchestration path that serially
  materializes the requested subject-space VTA gray-matter atlas before
  launching process or parpool compute workers.
- Keep the actual VTA task execution in the requested mode (`process`, 4
  workers for the full-cohort rerun).
- Validate the preflight on `sub-HuFengXian` before restarting the full cohort.
- Move the failed partial regenerated outputs for selected subjects to a new
  timestamped Trash archive before the restart, preserving original paths.

Fix implementation:

- `mh_vta_run_compute_tasks` now materializes requested subject-space
  gray-matter atlases before launching `process` or `parpool` workers.
- The preflight respects task-level `useAtlas` and `gmAtlas`, falls back to
  `cfg.vta.gmAtlas` or `options.atlasset`, and verifies that the subject
  `gm_mask` exists after `ea_ptspecific_atl`.
- A process dry-run smoke check on `sub-HuFengXian` completed with
  `preflight_smoke_after_fix_ok`; it used the same
  `Custom_Ewert_Zhang_Middlebrooks` atlas and did not launch real VTA workers.

### Phase 2CE Attempt 2 Failure and Environment Gate

Status: **failed before full-cohort completion; MATLAB startup gate required
before restart**.

Attempt 2 used the atlas preflight fix and wrote to
`process_tasks_attempt2`. It reached `sub-LinJia` but failed during
`SNr003_immediate_STNplusSNr_alt_R_SNr_c4_row3_R` because the worker exited
before writing its result MAT:

- Shell elapsed time: 235.44 seconds.
- MATLAB elapsed time: 188.663462 seconds.
- Preflight messages appeared before worker launch:
  `Ensuring subject-space VTA gray-matter atlas: Custom_Ewert_Zhang_Middlebrooks`.
- The original `GPe.nii.gz` gray-matter atlas race did not recur.
- `sub-LinJia` had 64 `model-simbio_hemi-*` files and 12 coverage masks at
  failure; no other selected subject had regenerated VTA outputs.
- No subject lock remained after the failure.

Follow-up diagnostics:

- A direct sequential reproduction of the failed payload also exited through
  MATLAB/Conda without a MATLAB stack trace or result file.
- A basic MATLAB batch smoke (`disp('matlab_basic_ok')`) and a direct MATLAB
  batch smoke both failed or hung without MATLAB output after attempt 2.
- The direct smoke process was terminated after confirming it was the new test
  process and not a user/other-worktree MATLAB process.

Current gate before another restart:

- Do not start attempt 3 until MATLAB batch startup is stable again.
- Move attempt 2 partial regenerated VTA/coverage outputs to a separate Trash
  archive before restarting.
- If MATLAB remains unable to start while unrelated GUI/batch MATLAB sessions
  are running, get explicit approval before terminating those unrelated
  sessions.

### Phase 2CE Attempt 3 Restart Plan

Status: **approved for restart without terminating existing MATLAB sessions**.

Attempt 3 will reuse the same approved real-root full-cohort command and the
same model settings:

- `VtaGmAtlas = Custom_Ewert_Zhang_Middlebrooks`.
- `VtaModelKey = simbio`.
- `VtaExecutionMode = process`.
- `VtaParallelWorkers = 4`.
- Coverage atlas remains `Custom_Ewert_Zhang_Middlebrooks0.05`.

Restart boundary:

- Do not terminate unrelated GUI or batch MATLAB sessions.
- Use a distinct attempt 3 wrapper, runtime file, process work directory, and
  shell log under
  `/Volumes/VAL/STNSNr/validation/vta_full_cohort_realroot_rerun_20260704_024228`.
- The real-root boundary was rechecked before attempt 3: selected subjects had
  zero `model-simbio_hemi-*` files, zero `stnsnr_vta_coverage` directories, and
  zero subject locks; cohort outputs were empty except for the preserved
  `target_component_distribution` directory.
- If attempt 3 fails, preserve logs and move any partial regenerated outputs to
  Trash before any later restart.

### Phase 2CE Attempt 3 Failure and Fixed Mask Restart Plan

Status: **failed during subject 7; code fix required before another full
rerun**.

Attempt 3 started at `2026-07-04 06:37:40 -0700` and ended at
`2026-07-04 07:31:04 -0700` with MATLAB status `error`.

Observed progress before failure:

- Shell elapsed time: 3219.21 seconds.
- MATLAB elapsed time: 3203.230720 seconds.
- Completed subject-level outputs for 6 selected subjects:
  `sub-LinJia`, `sub-HuFengXian`, `sub-YuDongJian`, `sub-WuYueFen`,
  `sub-LiPing`, and `sub-MaoXiaoMing`.
- Failed while processing `sub-ShengGuoLiang`, task
  `stnsnr_vta_SNr016_immediate_STN_continuous` side `R`.
- `process_tasks_attempt3` contained 64 payload MAT files and 64 result MAT
  files, with one result marked as worker error.
- No selected-subject lock remained after MATLAB exited.

Observed failure:

- Main MATLAB error:
  `One or more VTA process tasks failed: Failed to load gray matter mask.`
- Worker log context:
  `Duplicate .nii/.nii.gz files detected for gm_mask` followed by
  `Can't open image file.`
- The failing worker was reading
  `sub-ShengGuoLiang/atlases/Custom_Ewert_Zhang_Middlebrooks/gm_mask`.

Root-cause refinement:

- The attempt 1 fix serially pre-materialized the subject-space atlas before
  launching each process-mode task batch.
- SimBio native `Atlas Based` segmentation still calls `ea_ptspecific_atl`
  inside each worker before reading `gm_mask.nii.gz`.
- A worker can therefore still observe a transient or duplicate
  `gm_mask.nii`/`gm_mask.nii.gz` state while another process is finalizing the
  atlas-derived mask, producing an unreadable gray-matter mask even after
  preflight.

Required fix before attempt 4:

- After serial preflight materialization, copy the resolved subject-space
  `gm_mask` to an immutable per-attempt frozen-mask path under the process work
  directory.
- Serialize that frozen-mask path in the worker payload.
- Update the optional SimBio atlas-segmentation path to use the frozen mask
  when present and matching `options.atlasset`; otherwise preserve the original
  Lead-DBS behavior.
- Move attempt 3 partial regenerated VTA/coverage/cohort outputs to a new Trash
  archive before attempt 4.
- Relaunch with a distinct attempt 4 wrapper, process work directory, MATLAB
  runtime file, result MAT, and shell log.

Fix implementation for attempt 4:

- `mh_vta_run_compute_tasks` now copies the preflight-resolved subject
  `gm_mask` into `processWorkDir/frozen_gm_masks/<subject>/<atlas>/` and
  serializes that immutable path in `options.fixedAtlasGmMaskCache`.
- `ea_segment_MRI` now checks `options.fixedAtlasGmMaskCache` for the active
  `options.atlasset` before calling `ea_ptspecific_atl` in native
  `Atlas Based` mode.
- If no matching frozen mask exists, the original Lead-DBS behavior is kept:
  call `ea_ptspecific_atl` and read the subject atlas `gm_mask.nii.gz`.
- Regression tests:
  - `test_fixed_atlas_gm_mask_cache` verifies native Atlas Based segmentation
    uses the frozen mask path and does not call `ea_ptspecific_atl`.
  - `test_process_frozen_gm_mask_cache` verifies process dry-run payloads carry
    a frozen mask copy under the process work directory rather than the mutable
    subject atlas path.
