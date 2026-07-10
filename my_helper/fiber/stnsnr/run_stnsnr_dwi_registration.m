% Run the STN/SNr BIDS DWI preset through the generic preprocessing runner.

repoDir = fileparts(fileparts(fileparts(fileparts(mfilename('fullpath')))));
addpath(genpath(repoDir));
configPath = fullfile(repoDir, 'my_helper', 'stnsnr', 'config', 'dwi.yaml');

result = run_bids_dwi_preprocessing( ...
    'Config', configPath, ...
    'Mode', 'run');

fprintf('\nFinished STN/SNr DWI preprocessing.\n');
fprintf('Run record: %s\n', result.runRecord.runDir);
