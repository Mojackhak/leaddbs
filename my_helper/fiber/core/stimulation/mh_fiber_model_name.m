function modelName = mh_fiber_model_name(modelKey)
% Resolve a stimulation model key through the VTA model registry.

entry = mh_vta_model_registry(modelKey);
modelName = entry.modelName;
end
