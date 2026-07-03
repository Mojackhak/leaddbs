function parser = mh_fiber_stnsnr_add_vta_parser_params(parser)
% Add shared STN/SNr VTA model, atlas, and execution parser parameters.

parser.addParameter('VtaGmAtlas', 'DISTAL Minimal (Ewert 2017)', ...
    @(x) ischar(x) || isstring(x));
parser.addParameter('VtaModelKey', 'simbio', @(x) ischar(x) || isstring(x));
parser.addParameter('VtaExecutionMode', 'sequential', @(x) ischar(x) || isstring(x));
parser.addParameter('VtaParallelWorkers', 1, @(x) isnumeric(x) && isscalar(x) && x >= 1);
parser.addParameter('VtaMatlabExe', '/Applications/MATLAB_R2024b.app/bin/matlab', ...
    @(x) ischar(x) || isstring(x));
parser.addParameter('VtaCondaEnv', 'leaddbs', @(x) ischar(x) || isstring(x));
parser.addParameter('VtaProcessWorkDir', '', @(x) ischar(x) || isstring(x));
parser.addParameter('VtaProcessDryRun', false, @(x) islogical(x) || isnumeric(x));
parser.addParameter('VtaProcessPollSeconds', 2, @(x) isnumeric(x) && isscalar(x) && x > 0);
parser.addParameter('VtaProcessTimeoutSeconds', 0, @(x) isnumeric(x) && isscalar(x) && x >= 0);
end
