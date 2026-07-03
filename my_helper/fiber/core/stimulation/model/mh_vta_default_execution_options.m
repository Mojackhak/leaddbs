function defaults = mh_vta_default_execution_options()
% Return default VTA task execution options.

defaults = struct();
defaults.parallel = false;
defaults.parallelWorkers = 1;
defaults.executionMode = 'sequential';
defaults.matlabExe = '/Applications/MATLAB_R2024b.app/bin/matlab';
defaults.condaEnv = 'leaddbs';
defaults.processDryRun = false;
defaults.processWorkDir = '';
defaults.processPollSeconds = 2;
defaults.processTimeoutSeconds = 0;
end
