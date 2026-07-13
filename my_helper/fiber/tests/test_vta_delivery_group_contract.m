% Validate delivery-group expansion without running VTA/FEM.

repoDir = fileparts(fileparts(fileparts(fileparts(mfilename('fullpath')))));
addpath(genpath(fullfile(repoDir, 'my_helper', 'fiber')));
addpath(repoDir);

source1 = source_spec('L', 130, 'voltage');
source2 = source_spec('L', 130, 'voltage');
source2.amp = 1.5;

continuous = struct( ...
    'delivery_mode', 'continuous', ...
    'sources', [source1, source2]);
oneSolve = mh_vta_model_registry('simbio_onesolve');
[continuousSpecs, continuousKind] = mh_vta_expand_delivery_group(continuous, oneSolve);
assert(strcmp(continuousKind, 'joint'));
assert(numel(continuousSpecs) == 1);
assert(numel(continuousSpecs.sources) == 2);

alternating = continuous;
alternating.delivery_mode = 'alternating';
simbio = mh_vta_model_registry('simbio');
[alternatingSpecs, alternatingKind] = mh_vta_expand_delivery_group(alternating, simbio);
assert(strcmp(alternatingKind, 'independent'));
assert(numel(alternatingSpecs) == 2);
assert(all(arrayfun(@(value) numel(value.sources) == 1, alternatingSpecs)));

invalidAlternating = alternating;
invalidAlternating.sources = source1;
assert_error(@() mh_vta_expand_delivery_group(invalidAlternating, simbio), ...
    'mh_vta_expand_delivery_group:InvalidAlternatingGroup');

mixedFrequency = alternating;
mixedFrequency.sources(2).frequency = 30;
assert_error(@() mh_vta_expand_delivery_group(mixedFrequency, simbio), ...
    'mh_vta_expand_delivery_group:MixedFrequency');

current1 = source_spec('L', 130, 'current');
current2 = source_spec('L', 130, 'current');
continuousCurrent = struct( ...
    'delivery_mode', 'continuous', ...
    'sources', [current1, current2]);
assert_error(@() mh_vta_expand_delivery_group(continuousCurrent, simbio), ...
    'mh_vta_expand_delivery_group:UnsupportedBackendCapability');

fprintf('VTA delivery group contract test passed.\n');

function source = source_spec(side, frequency, controlMode)
if strcmp(controlMode, 'voltage')
    unit = 'V';
else
    unit = 'mA';
end
source = struct( ...
    'side', side, ...
    'amp', 2.0, ...
    'unit', unit, ...
    'pulseWidth', 60, ...
    'frequency', frequency, ...
    'controlMode', controlMode, ...
    'contacts', [ ...
        struct('contact', 1, 'polarity', 'cathode', 'fraction', 1.0), ...
        struct('contact', 'case', 'polarity', 'anode', 'fraction', 1.0)]);
end

function assert_error(callback, expectedId)
raised = false;
try
    callback();
catch ME
    raised = true;
    assert(strcmp(ME.identifier, expectedId), ...
        'Expected error %s, received %s.', expectedId, ME.identifier);
end
assert(raised, 'Expected error was not raised: %s', expectedId);
end
