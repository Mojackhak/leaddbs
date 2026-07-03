function count = mh_fiber_bvec_count(path)
% Return the number of diffusion directions represented by a bvec file.

bvec = load(path);
if size(bvec, 1) == 3
    count = size(bvec, 2);
elseif size(bvec, 2) == 3
    count = size(bvec, 1);
else
    error('mh_fiber_bvec_count:InvalidBvec', ...
        'bvec file must be 3 x N or N x 3: %s', path);
end
end
