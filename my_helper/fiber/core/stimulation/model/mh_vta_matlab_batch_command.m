function cmd = mh_vta_matlab_batch_command(matlabExe, batchExpr, condaEnv)
% Build a shell command that runs MATLAB batch code, optionally through Conda.

matlabExe = char(string(matlabExe));
batchExpr = char(string(batchExpr));
condaEnv = char(string(condaEnv));

if strlength(string(condaEnv)) > 0
    cmd = sprintf(['if command -v conda >/dev/null 2>&1; then ', ...
        'conda run -n %s %s -batch %s; else %s -batch %s; fi'], ...
        mh_fiber_shell_quote(condaEnv), mh_fiber_shell_quote(matlabExe), ...
        mh_fiber_shell_quote(batchExpr), mh_fiber_shell_quote(matlabExe), ...
        mh_fiber_shell_quote(batchExpr));
else
    cmd = sprintf('%s -batch %s', mh_fiber_shell_quote(matlabExe), ...
        mh_fiber_shell_quote(batchExpr));
end
end
