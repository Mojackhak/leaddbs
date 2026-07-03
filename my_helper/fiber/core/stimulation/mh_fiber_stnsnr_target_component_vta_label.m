function label = mh_fiber_stnsnr_target_component_vta_label(componentId)
% Build a stable VTA stimulation label for an STN/SNr target component.

label = mh_util_sanitize_label(['stnsnr_target_component_', char(string(componentId))]);
end
