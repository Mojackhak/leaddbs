function entry = mh_vta_model_registry(modelKey)
% Resolve VTA model keys to backend functions and Lead-DBS model metadata.

entries = registry_entries();
if nargin < 1 || strlength(string(modelKey)) == 0
    entry = entries;
    return;
end

key = lower(char(string(modelKey)));
for i = 1:numel(entries)
    aliases = lower(string(entries(i).aliases));
    if any(key == aliases)
        entry = entries(i);
        return;
    end
end

error('mh_vta_model_registry:UnsupportedModel', ...
    'Unsupported VTA model key: %s', key);
end

function entries = registry_entries()
simbio = struct();
simbio.key = 'simbio';
simbio.aliases = {'simbio', 'horn', 'fieldtrip', 'simbio/fieldtrip', 'simbio_twosource'};
simbio.modelName = 'SimBio/FieldTrip (see Horn 2017)';
simbio.modelLabel = 'simbio';
simbio.backend = 'mh_vta_backend_simbio_twosource';
simbio.supportsVoltage = true;
simbio.supportsCurrent = true;
simbio.supportsMultiVoltage = false;
simbio.outputs = mh_vta_output_spaces_from_config();

oneSolve = simbio;
oneSolve.key = 'simbio_onesolve';
oneSolve.aliases = {'simbio_onesolve', 'onesolve', 'helper_onesolve_multivoltage'};
oneSolve.backend = 'mh_vta_backend_simbio_onesolve';
oneSolve.supportsCurrent = false;
oneSolve.supportsMultiVoltage = true;

entries = [simbio, oneSolve];
end
