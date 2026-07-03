function bvals = mh_fiber_load_bval(path)
% Load a bval file as one numeric row vector.

bvals = load(path);
bvals = bvals(:)';
if isempty(bvals) || ~isnumeric(bvals)
    error('mh_fiber_load_bval:InvalidBval', ...
        'Could not read numeric b-values from %s', path);
end
end
