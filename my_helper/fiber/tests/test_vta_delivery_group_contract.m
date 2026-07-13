% Validate delivery-group expansion without running VTA/FEM.

repoDir = fileparts(fileparts(fileparts(fileparts(mfilename('fullpath')))));
addpath(genpath(fullfile(repoDir, 'my_helper', 'fiber')));
addpath(repoDir);

source1 = source_spec('source-1', 130, 'voltage');
source2 = source_spec('source-2', 130, 'voltage');
source2.amplitude = 1.5;

[continuousSpecs, continuousKind] = mh_vta_expand_delivery_group( ...
    'continuous', [source1, source2]);
assert(strcmp(continuousKind, 'joint'));
assert(iscell(continuousSpecs));
assert(isscalar(continuousSpecs));
assert(numel(continuousSpecs{1}) == 2);

[alternatingSpecs, alternatingKind] = mh_vta_expand_delivery_group( ...
    'alternating', [source1, source2]);
assert(strcmp(alternatingKind, 'independent'));
assert(numel(alternatingSpecs) == 2);
assert(all(cellfun(@isscalar, alternatingSpecs)));
assert(strcmp(alternatingSpecs{1}.source_id, 'source-1'));
assert(strcmp(alternatingSpecs{2}.source_id, 'source-2'));

singleAlternating = mh_vta_expand_delivery_group('alternating', source1);
assert(isscalar(singleAlternating));
assert(strcmp(singleAlternating{1}.source_id, 'source-1'));

mixedFrequency = [source1, source2];
mixedFrequency(2).frequency_hz = 30;
assert_error(@() mh_vta_expand_delivery_group('alternating', mixedFrequency), ...
    'mh_vta_expand_delivery_group:MixedFrequency');

current1 = source_spec('source-1', 130, 'current');
current2 = source_spec('source-2', 130, 'current');
[continuousCurrent, currentKind] = mh_vta_expand_delivery_group( ...
    'continuous', [current1, current2]);
assert(strcmp(currentKind, 'joint'));
assert(numel(continuousCurrent{1}) == 2);

mixedControl = [source1, current2];
assert_error(@() mh_vta_expand_delivery_group('continuous', mixedControl), ...
    'mh_vta_expand_delivery_group:MixedControlMode');

fprintf('VTA delivery group contract test passed.\n');

function source = source_spec(sourceId, frequency, controlMode)
source = struct( ...
    'source_id', sourceId, ...
    'amplitude', 2.0, ...
    'pulse_width_us', 60, ...
    'frequency_hz', frequency, ...
    'control_mode', controlMode, ...
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
