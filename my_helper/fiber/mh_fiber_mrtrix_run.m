function output = mh_fiber_mrtrix_run(cfg, command, allowFailure)
% Run an MRtrix3 command with a stable PATH and return captured output.

if nargin < 3
    allowFailure = false;
end

if isfield(cfg, 'seedVtaSift2') && isfield(cfg.seedVtaSift2, 'mrtrixPathPrefix')
    prefix = char(string(cfg.seedVtaSift2.mrtrixPathPrefix));
elseif isfield(cfg, 'seedTarget') && isfield(cfg.seedTarget, 'mrtrixPathPrefix')
    prefix = char(string(cfg.seedTarget.mrtrixPathPrefix));
else
    prefix = '';
end
if strlength(string(prefix)) > 0
    currentPath = getenv('PATH');
    if ~contains([':', currentPath, ':'], [':', prefix, ':'])
        setenv('PATH', [prefix, ':', currentPath]);
    end
end

fprintf('[MRtrix] %s\n', command);
[status, output] = system(command);
if status ~= 0 && ~allowFailure
    error('mh_fiber_mrtrix_run:CommandFailed', ...
        'MRtrix command failed with status %d:\n%s\n\n%s', status, command, output);
elseif status ~= 0
    warning('mh_fiber_mrtrix_run:CommandFailed', ...
        'MRtrix command failed with status %d:\n%s\n\n%s', status, command, output);
end
end
