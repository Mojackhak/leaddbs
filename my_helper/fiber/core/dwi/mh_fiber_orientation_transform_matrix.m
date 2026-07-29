function matrix = mh_fiber_orientation_transform_matrix(transformName)
% Return the signed-axis matrix for a supported image-content transform.

transformName = validatestring(char(string(transformName)), ...
    {'identity', 'flipY', 'flipZ', 'rotX180', 'rotZ180'}, ...
    'mh_fiber_orientation_transform_matrix', 'transformName');

switch transformName
    case 'identity'
        matrix = eye(3);
    case 'flipY'
        matrix = diag([1 -1 1]);
    case 'flipZ'
        matrix = diag([1 1 -1]);
    case 'rotX180'
        matrix = diag([1 -1 -1]);
    case 'rotZ180'
        matrix = diag([-1 -1 1]);
end
end
