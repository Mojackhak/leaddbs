function tests = test_ants_d99_engine
% Exercise stage reuse with real NIfTI I/O and mocked external execution.
tests = functiontests(localfunctions);
end

function setupOnce(test)
root = fileparts(fileparts(mfilename('fullpath')));
test.TestData.originalPath = path;
test.TestData.originalDirectory = pwd;
test.TestData.directory = tempname;
mkdir(test.TestData.directory);
addpath(root, fullfile(root, 'helpers'), fullfile(root, 'helpers', 'gui'), ...
    fullfile(root, 'ext_libs'), fullfile(root, 'ext_libs', 'ANTs'), ...
    fullfile(root, 'ext_libs', 'ANTs', 'presets'), fullfile(root, 'ext_libs', 'nii_lib'), ...
    fullfile(root, 'ext_libs', 'GetFullPath'), fullfile(root, 'ext_libs', 'spm'));
test.TestData.preset = ea_antspreset_macaque_d99_deep(struct);
stubs = fullfile(test.TestData.directory, 'stubs');
mkdir(stubs);
write_stub(stubs, 'ea_libs_helper', {'function ea_libs_helper', 'end'});
write_stub(stubs, 'ea_getExec', {'function result = ea_getExec(executable, varargin)', ...
    'result = executable;', 'end'});
write_stub(stubs, 'ea_runcmd', {'function status = ea_runcmd(command, varargin)', ...
    'global EA_D99_ENGINE_TEST', 'status = EA_D99_ENGINE_TEST.external(command);', 'end'});
write_stub(stubs, 'ea_gencheckregpair', {'function ea_gencheckregpair(fixed, mask, output, varargin)', ...
    'global EA_D99_ENGINE_TEST', ...
    'EA_D99_ENGINE_TEST.qaCount = EA_D99_ENGINE_TEST.qaCount + 1;', ...
    'imwrite(uint8(zeros(2,2)), output);', 'end'});
write_stub(stubs, 'ea_antspreset_macaque_d99_deep', ...
    {'function result = ea_antspreset_macaque_d99_deep(varargin)', ...
    'global EA_D99_ENGINE_TEST', 'result = EA_D99_ENGINE_TEST.preset;', 'end'});
addpath(stubs, '-begin');
cd(test.TestData.directory);
clear_stubs;
end

function teardownOnce(test)
clear_stubs;
cd(test.TestData.originalDirectory);
path(test.TestData.originalPath);
clear global EA_D99_ENGINE_TEST
rmdir(test.TestData.directory, 's');
end

function setup(test)
global EA_D99_ENGINE_TEST
EA_D99_ENGINE_TEST = struct('preset', test.TestData.preset, 'commands', {{}}, ...
    'registrationStages', {{}}, 'qaCount', 0, 'external', @mock_external);
directory = tempname(test.TestData.directory);
mkdir(directory);
template = fullfile(directory, 'template');
mkdir(template);
fixedShape = [10, 12, 8];
movingShape = [9, 11, 7];
fixedAffine = diag([0.5, 0.5, 0.5, 1]);
movingAffine = diag([0.6, 0.6, 0.6, 1]);
movingAffine(1:3, 4) = [-1; 2; -3];
write_nifti(fullfile(template, 't1.nii'), reshape(1:prod(fixedShape), fixedShape), fixedAffine);
moving = fullfile(directory, 'moving.nii');
write_nifti(moving, reshape(1:prod(movingShape), movingShape), movingAffine);
fixedBrain = false(fixedShape);
fixedBrain(2:end-1, 2:end-1, 2:end-1) = true;
nativeBrain = false(movingShape);
nativeBrain(2:end-1, 2:end-1, 2:end-1) = true;
deep = false(fixedShape);
deep(4:6, 5:7, 3:5) = true;
masks = struct('fixed', fullfile(directory, 'fixed_mask.nii'), ...
    'moving', fullfile(directory, 'moving_mask.nii'), ...
    'deep', fullfile(directory, 'deep_mask.nii'));
write_nifti(masks.fixed, fixedBrain, fixedAffine);
write_nifti(masks.moving, nativeBrain, movingAffine);
write_nifti(masks.deep, deep, fixedAffine);
test.TestData.template = template;
test.TestData.moving = moving;
test.TestData.work = fullfile(directory, 'work');
test.TestData.masks = masks;
test.TestData.fixedAffine = fixedAffine;
test.TestData.deep = deep;
end

function testInitialExecutionAndResidualComposition(test)
result = run_engine(test);
state = captured_state;
verifyEqual(test, state.registrationStages, {'linear', 'wholebrain', 'deep'});
verifyEqual(test, state.qaCount, 3);
verifyTrue(test, isfile(result.forward));
verifyTrue(test, isfile(result.inverse));
verifyEqual(test, size(niftiread(result.forward)), [10, 12, 8, 1, 3]);
verifyEqual(test, size(niftiread(result.inverse)), [9, 11, 7, 1, 3]);
work = test.TestData.work;
deepCommand = fileread(fullfile(work, 'deep', 'registration.txt'));
verifyTrue(test, contains(deepCommand, [' --initial-moving-transform ', ...
    ea_path_helper(fullfile(work, 'wholebrain', 'forward.nii.gz'))]));
verifyTrue(test, contains(deepCommand, ' --write-composite-transform 0 --collapse-output-transforms 0'));
forward = transform_chain(fileread(fullfile(work, 'deep', 'compose_forward.txt')));
inverse = transform_chain(fileread(fullfile(work, 'deep', 'compose_inverse.txt')));
verifyEqual(test, forward, {fullfile(work, 'deep', 'transform_1Warp.nii.gz'), ...
    fullfile(work, 'wholebrain', 'forward.nii.gz')});
verifyEqual(test, inverse, {fullfile(work, 'wholebrain', 'inverse.nii.gz'), ...
    fullfile(work, 'deep', 'transform_1InverseWarp.nii.gz')});
end

function testIdenticalRunReusesStagesAndRestoresThreads(test)
names = {'ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS', 'OMP_NUM_THREADS', ...
    'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS'};
previous = cellfun(@getenv, names, 'UniformOutput', false);
cleanup = onCleanup(@() restore_environment(names, previous));
cellfun(@(name) setenv(name, '7'), names);
run_engine(test);
before = stage_records(test.TestData.work);
run_engine(test);
state = captured_state;
verifyEqual(test, state.registrationStages, {'linear', 'wholebrain', 'deep'});
verifyEqual(test, state.qaCount, 3);
verifyEqual(test, stage_records(test.TestData.work), before);
verifyEqual(test, cellfun(@getenv, names, 'UniformOutput', false), repmat({'7'}, size(names)));
end

function testDeepMaskChangeRerunsOnlyDeepRegistration(test)
run_engine(test);
before = stage_records(test.TestData.work);
deep = test.TestData.deep;
deep(3, 5, 3) = true;
source = test.TestData.masks.deep;
previousTime = java.io.File(source).lastModified();
write_nifti(source, deep, test.TestData.fixedAffine);
assert(java.io.File(source).setLastModified(previousTime + 5000));
run_engine(test);
state = captured_state;
verifyEqual(test, state.registrationStages, {'linear', 'wholebrain', 'deep', 'deep'});
after = stage_records(test.TestData.work);
verifyEqual(test, after.linear, before.linear);
verifyEqual(test, after.wholebrain, before.wholebrain);
verifyNotEqual(test, after.deep, before.deep);
actual = ea_load_nii(fullfile(test.TestData.work, 'deep_mask', 'mask.nii'));
verifyEqual(test, logical(actual.img), deep);
end

function testResolvedScrfChangeRerunsOnlyDeepRegistration(test)
run_engine(test);
before = stage_records(test.TestData.work);
global EA_D99_ENGINE_TEST
EA_D99_ENGINE_TEST.preset.scrf.gradientstep = '0.07,3,1';
run_engine(test);
state = captured_state;
verifyEqual(test, state.registrationStages, {'linear', 'wholebrain', 'deep', 'deep'});
after = stage_records(test.TestData.work);
verifyEqual(test, after.linear, before.linear);
verifyEqual(test, after.wholebrain, before.wholebrain);
verifyNotEqual(test, after.deep, before.deep);
verifyTrue(test, contains(fileread(fullfile(test.TestData.work, 'deep', 'registration.txt')), ...
    ' --transform SyN[0.07,3,1]'));
end

function testCompletionJsonFormattingAndKeyOrderDoNotInvalidate(test)
run_engine(test);
files = dir(fullfile(test.TestData.work, '**', 'complete.json'));
verifyGreaterThanOrEqual(test, numel(files), 8);
for index = 1:numel(files)
    filename = fullfile(files(index).folder, files(index).name);
    original = fileread(filename);
    record = reverse_fields(jsondecode(original));
    reformatted = [jsonencode(record), newline];
    verifyNotEqual(test, reformatted, original);
    write_text(filename, reformatted);
end
run_engine(test);
state = captured_state;
verifyEqual(test, state.registrationStages, {'linear', 'wholebrain', 'deep'});
verifyEqual(test, state.qaCount, 3);
end

function result = run_engine(test)
result = ea_ants_d99_deep_run(test.TestData.template, test.TestData.moving, ...
    test.TestData.work, test.TestData.masks);
end

function records = stage_records(work)
records = struct;
for name = {'linear', 'wholebrain', 'deep'}
    records.(name{1}) = fileread(fullfile(work, name{1}, 'complete.json'));
end
end

function state = captured_state
global EA_D99_ENGINE_TEST
state = EA_D99_ENGINE_TEST;
end

function status = mock_external(command)
global EA_D99_ENGINE_TEST
EA_D99_ENGINE_TEST.commands{end+1} = command;
if contains(command, 'antsRegistration')
    output = regexp(command, ' --output \[([^,]+),([^\]]+)\]', 'tokens', 'once');
    prefix = output{1};
    fixed = regexp(command, ' --metric [A-Za-z]+\[([^,]+),', 'tokens', 'once');
    fixed = fixed{1};
    [~, stage] = fileparts(fileparts(prefix));
    EA_D99_ENGINE_TEST.registrationStages{end+1} = stage;
    copyfile(fixed, output{2});
    if contains(command, ' --write-composite-transform 1')
        write_text([prefix, 'Composite.h5'], 'mock composite');
        write_text([prefix, 'InverseComposite.h5'], 'mock inverse composite');
    else
        write_field([prefix, '1Warp.nii.gz'], fixed);
        write_field([prefix, '1InverseWarp.nii.gz'], fixed);
    end
else
    reference = regexp(command, ' -r ([^ ]+)', 'tokens', 'once');
    output = regexp(command, ' -o \[([^,]+),1\]', 'tokens', 'once');
    for transform = transform_chain(command)
        assert(isfile(transform{1}), 'Mock application input is missing: %s', transform{1});
    end
    write_field(output{1}, reference{1});
end
log = regexp(command, ' > (.+) 2>&1$', 'tokens', 'once');
write_text(log{1}, 'Mock external command completed.');
status = 0;
end

function paths = transform_chain(command)
tokens = regexp(command, ' -t ([^\s]+)', 'tokens');
paths = cellfun(@(token) token{1}, tokens, 'UniformOutput', false);
end

function write_field(filename, reference)
image = ea_load_nii(reference);
affine = image.mat;
affine(:, 4) = affine(:, 4) + sum(affine(:, 1:3), 2);
write_nifti(filename, zeros([image.dim, 1, 3]), affine, true);
end

function write_nifti(filename, values, affine, vector)
if nargin < 4, vector = false; end
spacing = sqrt(sum(affine(1:3, 1:3).^2, 1));
nii = make_nii(double(values), spacing, [], 64);
nii.hdr.hist.qform_code = 0;
nii.hdr.hist.sform_code = 1;
nii.hdr.hist.srow_x = affine(1, :);
nii.hdr.hist.srow_y = affine(2, :);
nii.hdr.hist.srow_z = affine(3, :);
if vector, nii.hdr.dime.intent_code = 1007; end
if endsWith(filename, '.gz')
    plain = filename(1:end-3);
    save_nii(nii, plain);
    gzip(plain);
    delete(plain);
else
    save_nii(nii, filename);
end
end

function value = reverse_fields(value)
if isstruct(value)
    names = fieldnames(value);
    for index = 1:numel(value)
        for name = names'
            value(index).(name{1}) = reverse_fields(value(index).(name{1}));
        end
    end
    value = orderfields(value, flipud(names));
elseif iscell(value)
    value = cellfun(@reverse_fields, value, 'UniformOutput', false);
end
end

function restore_environment(names, values)
for index = 1:numel(names), setenv(names{index}, values{index}); end
end

function write_stub(directory, name, lines)
write_text(fullfile(directory, [name, '.m']), strjoin(lines, newline));
end

function write_text(filename, content)
file = fopen(filename, 'w');
cleanup = onCleanup(@() fclose(file));
fprintf(file, '%s', content);
end

function clear_stubs
clear ea_libs_helper ea_getExec ea_runcmd ea_gencheckregpair ea_antspreset_macaque_d99_deep
end
