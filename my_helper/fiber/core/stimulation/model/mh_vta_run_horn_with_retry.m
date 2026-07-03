function mh_vta_run_horn_with_retry(S, sideIdx, options, stimLabel, expectedPath, varargin)
% Run ea_genvat_horn with deterministic retries for known post-write failures.

parser = inputParser;
parser.FunctionName = 'mh_vta_run_horn_with_retry';
parser.addParameter('MaxAttempts', 4, @(x) isnumeric(x) && isscalar(x) && x >= 1);
parser.addParameter('WarningPrefix', 'mh_vta_run_horn_with_retry', @(x) ischar(x) || isstring(x));
parser.parse(varargin{:});
opts = parser.Results;
warningPrefix = char(string(opts.WarningPrefix));

for attempt = 1:opts.MaxAttempts
    try
        rng(stable_retry_seed(stimLabel, sideIdx, attempt), 'twister');
        ea_genvat_horn([], S, sideIdx, options, stimLabel);
        return;
    catch ME
        if isfile(expectedPath)
            warning([warningPrefix, ':HornPostWriteFailure'], ...
                ['Lead-DBS Horn raised an error after writing the expected output ', ...
                'for %s side %d: %s'], stimLabel, sideIdx, ME.message);
            return;
        end
        if ~is_horn_index_error(ME) || attempt == opts.MaxAttempts
            rethrow(ME);
        end
        warning([warningPrefix, ':HornIndexRetry'], ...
            'Retrying Lead-DBS Horn e-field generation for %s side %d after index error (%d/%d).', ...
            stimLabel, sideIdx, attempt, opts.MaxAttempts);
    end
end
end

function seed = stable_retry_seed(stimLabel, sideIdx, attempt)
labelValues = double(char(string(stimLabel)));
seed = 42 + 1009 * double(attempt) + 101 * double(sideIdx) + sum(labelValues);
seed = mod(seed, 2^32 - 1);
if seed == 0
    seed = 42;
end
end

function tf = is_horn_index_error(ME)
stackNames = string({ME.stack.name});
tf = contains(ME.message, 'Array indices must be positive integers') && ...
    any(stackNames == "ea_write_vta_nii");
end
