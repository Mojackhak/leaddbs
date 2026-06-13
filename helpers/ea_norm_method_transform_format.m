function format = ea_norm_method_transform_format(method)
% Return the transform format normally written by a normalization method.

method = lower(method);

if contains(method, 'fnirt')
    format = 'fnirt';
elseif contains(method, 'three-step') || contains(method, 'threestep') || ...
        contains(method, 'schonecker') || contains(method, 'schoenecker')
    format = 'ants_affine';
else
    format = 'ants';
end
