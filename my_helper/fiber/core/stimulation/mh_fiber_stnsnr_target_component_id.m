function componentId = mh_fiber_stnsnr_target_component_id(subjectId, phase, protocol, sideCode, target)
% Build a stable STN/SNr target-component identifier.

rawId = sprintf('%s_%s_%s_%s_%s', ...
    char(string(subjectId)), char(string(phase)), char(string(protocol)), ...
    char(string(sideCode)), char(string(target)));
componentId = mh_util_sanitize_label(rawId);
end
