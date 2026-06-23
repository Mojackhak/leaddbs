% Compare HybraPD STN/SNr labels against Custom_Ewert_Zhang_Middlebrooks0.05.

repoDir = '/Users/mojackhu/Github/leaddbs';
cd(repoDir);
addpath(genpath(repoDir));

outputDir = fullfile(repoDir, 'connectomes', 'dMRI', 'public_tracking', ...
    'STN_SNr', 'roi_definition_qc');

result = mh_fiber_compare_stnsnr_roi_definitions( ...
    'RepoDir', repoDir, ...
    'OutputDir', outputDir, ...
    'WriteOutputs', true);

disp(result.summaryTable);
fprintf('\nSTN/SNr ROI definition comparison written to:\n');
fprintf('%s\n', result.summaryCsv);
fprintf('%s\n', result.reportMd);
