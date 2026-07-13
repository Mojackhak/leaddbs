function diagnostics = mh_vta_run_horn_with_retry( ...
        S, sideIdx, options, stimLabel, expectedPath, varargin)
% Run ea_genvat_horn with deterministic retries for known post-write failures.

parser = inputParser;
parser.FunctionName = 'mh_vta_run_horn_with_retry';
parser.addParameter('MaxAttempts', 4, @(x) isnumeric(x) && isscalar(x) && x >= 1);
parser.addParameter('WarningPrefix', 'mh_vta_run_horn_with_retry', @(x) ischar(x) || isstring(x));
parser.addParameter('SeedBase', [], @(x) isempty(x) || ...
    (isnumeric(x) && isscalar(x) && isfinite(x) && x >= 0));
parser.parse(varargin{:});
opts = parser.Results;
warningPrefix = char(string(opts.WarningPrefix));
attemptSeeds = zeros(1, opts.MaxAttempts);

for attempt = 1:opts.MaxAttempts
    attemptSeeds(attempt) = stable_retry_seed( ...
        stimLabel, sideIdx, attempt, opts.SeedBase);
    expectedExistedBefore = isfile(expectedPath);
    try
        rng(attemptSeeds(attempt), 'twister');
        ea_genvat_horn([], S, sideIdx, options, stimLabel);
        diagnostics = make_diagnostics(opts.SeedBase, attempt, attemptSeeds);
        return;
    catch ME
        if ~expectedExistedBefore && isfile(expectedPath)
            warning([warningPrefix, ':HornPostWriteFailure'], ...
                ['Lead-DBS Horn raised an error after writing the expected output ', ...
                'for %s side %d: %s'], stimLabel, sideIdx, ME.message);
            diagnostics = make_diagnostics(opts.SeedBase, attempt, attemptSeeds);
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

function diagnostics = make_diagnostics(seedBase, attempt, attemptSeeds)
diagnostics = struct( ...
    'seed_base', double_or_nan(seedBase), ...
    'attempt_count', attempt, ...
    'attempt_seeds', attemptSeeds(1:attempt), ...
    'seed_used', attemptSeeds(attempt));
end

function value = double_or_nan(value)
if isempty(value)
    value = NaN;
else
    value = double(value);
end
end

function seed = stable_retry_seed(stimLabel, sideIdx, attempt, seedBase)
if isempty(seedBase)
    labelValues = double(char(string(stimLabel)));
    seed = 42 + 1009 * double(attempt) + 101 * double(sideIdx) + ...
        sum(labelValues);
else
    seed = double(seedBase) + 1009 * double(attempt - 1);
end
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
