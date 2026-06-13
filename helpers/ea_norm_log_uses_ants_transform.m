function useAnts = ea_norm_log_uses_ants_transform(json)
% True when the method log points to an ANTs-compatible transform.

format = ea_norm_log_transform_format(json);
useAnts = ismember(format, {'ants', 'ants_affine'});
