function modelName = mh_fiber_model_name(modelKey)
% Resolve a short stimulation model key to the Lead-DBS model name.

modelKey = lower(char(string(modelKey)));
switch modelKey
    case {'simbio', 'horn', 'fieldtrip', 'simbio/fieldtrip'}
        modelName = 'SimBio/FieldTrip (see Horn 2017)';
    otherwise
        error('mh_fiber_model_name:UnsupportedModel', ...
            'Unsupported VTA model key: %s', modelKey);
end
end
