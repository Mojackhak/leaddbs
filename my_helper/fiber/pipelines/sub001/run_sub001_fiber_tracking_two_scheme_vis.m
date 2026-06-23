% Rerun sub-001 structural fibers and generate two VTA/Fiber visualization schemes.

cd('/Users/mojackhu/Github/leaddbs');
addpath(genpath('/Users/mojackhu/Github/leaddbs'));

subjectDir = '/Users/mojackhu/Desktop/ASD/derivatives/leaddbs/sub-001';
fiberCount = 200000;

twoSourceLabel = 'clinical_twosource_L2R2_3V_L5to8R5to8_5V';
oneSolveLabel = 'clinical_onesolve_L2R2_3V_L5to8R5to8_5V';

fprintf('\n=== Step 1/4: rerun structural fiber tracking ===\n');
mh_fiber_rerun_structural_tracking(subjectDir, fiberCount);

fprintf('\n=== Step 2/4: Lead-DBS two-source VTA and Fiber/VTA visualization ===\n');
cfgTwo = mh_fiber_default_config(subjectDir, twoSourceLabel);
cfgTwo.forceRecomputeVTA = true;
cfgTwo.figure.openAfterRun = false;
cfgTwo.figure.openAnatomyControl = false;
cfgTwo.figure.closeAfterSave = true;
[cfgTwo, STwo, optionsTwo, stimFoldersTwo] = mh_fiber_build_l2_l5to8_stimulation( ...
    cfgTwo, 'lead_dbs_twosource');
mh_fiber_ensure_vta(cfgTwo, STwo, optionsTwo, stimFoldersTwo);
resultTwo = mh_fiber_run(cfgTwo);

fprintf('\n=== Step 3/4: helper one-solve multi-voltage VTA and Fiber/VTA visualization ===\n');
cfgOne = mh_fiber_default_config(subjectDir, oneSolveLabel);
cfgOne.forceRecomputeVTA = true;
cfgOne.figure.openAfterRun = false;
cfgOne.figure.openAnatomyControl = false;
cfgOne.figure.closeAfterSave = true;
[cfgOne, SOne, optionsOne, stimFoldersOne] = mh_fiber_build_l2_l5to8_stimulation( ...
    cfgOne, 'helper_onesolve_multivoltage');
mh_fiber_ensure_vta_onesolve(cfgOne, SOne, optionsOne, stimFoldersOne);
resultOne = mh_fiber_run(cfgOne);

fprintf('\n=== Step 4/4: compare VTA/Fiber schemes ===\n');
comparison = mh_fiber_compare_vta_schemes(subjectDir, twoSourceLabel, oneSolveLabel);

fprintf('\nDone. Outputs are under:\n');
fprintf('%s\n', fullfile(subjectDir, 'connectomics', 'fiber_vis', twoSourceLabel));
fprintf('%s\n', fullfile(subjectDir, 'connectomics', 'fiber_vis', oneSolveLabel));
fprintf('%s\n', fullfile(subjectDir, 'connectomics', 'fiber_vis', 'two_scheme_comparison'));
