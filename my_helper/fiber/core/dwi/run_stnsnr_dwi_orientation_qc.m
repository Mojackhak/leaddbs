function status = run_stnsnr_dwi_orientation_qc(varargin)
% Generate candidate image-content orientation corrections for STNSNr DWI.

p = inputParser;
p.FunctionName = 'run_stnsnr_dwi_orientation_qc';
p.addParameter('RepoDir', '', @(x) ischar(x) || isstring(x));
p.addParameter('SourceRoot', '/Volumes/VAL/STNSNrdwi', @(x) ischar(x) || isstring(x));
p.addParameter('SubjectIds', {}, @(x) iscell(x) || isstring(x) || ischar(x));
p.addParameter('TransformCandidates', ...
    {'identity', 'flipY', 'flipZ', 'rotX180', 'rotZ180'}, ...
    @(x) iscell(x) || isstring(x) || ischar(x));
p.addParameter('OutputRoot', '', @(x) ischar(x) || isstring(x));
p.addParameter('GenerateColorFa', true, @(x) islogical(x) || isnumeric(x));
p.addParameter('AllowIncrementalCorrection', false, @(x) islogical(x) || isnumeric(x));
p.addParameter('Force', false, @(x) islogical(x) || isnumeric(x));
p.parse(varargin{:});
opts = normalize_options(p.Results);

repoDir = resolve_repo_dir(opts.RepoDir);
addpath(genpath(repoDir));

if isempty(opts.OutputRoot)
    opts.OutputRoot = fullfile(opts.SourceRoot, '_export_logs', ...
        ['orientation_qc_', char(datetime('now', 'Format', 'yyyyMMdd_HHmmss'))]);
end
mh_util_make_dir(opts.OutputRoot);

rows = repmat(empty_row(), 0, 1);
for subjectIndex = 1:numel(opts.SubjectIds)
    subjectId = opts.SubjectIds{subjectIndex};
    source = locate_source_dwi(opts.SourceRoot, subjectId);
    for transformIndex = 1:numel(opts.TransformCandidates)
        transformName = opts.TransformCandidates{transformIndex};
        candidateDir = fullfile(opts.OutputRoot, ['sub-', subjectId], transformName);
        mh_util_make_dir(candidateDir);
        row = empty_row();
        row.subject = subjectId;
        row.transform = transformName;
        row.source_nifti = source.Nifti;
        row.output_dir = candidateDir;
        try
            result = mh_fiber_reorient_dwi_image_content( ...
                'SourceNifti', source.Nifti, ...
                'SourceJson', source.Json, ...
                'SourceBval', source.Bval, ...
                'SourceBvec', source.Bvec, ...
                'OutputDir', candidateDir, ...
                'OutputBase', source.Base, ...
                'Transform', transformName, ...
                'AllowIncrementalCorrection', opts.AllowIncrementalCorrection, ...
                'Force', opts.Force);
            row.output_nifti = result.Nifti;
            row.output_bval = result.Bval;
            row.output_bvec = result.Bvec;
            row.output_json = result.Json;
            row.b0_montage = fullfile(candidateDir, [source.Base, '_b0_montage.png']);
            write_b0_montage(result.Nifti, result.Bval, row.b0_montage);
            [row.color_fa_status, row.color_fa_montage] = maybe_run_color_fa_qc( ...
                result, candidateDir, opts.GenerateColorFa);
            row.dimensions = image_size_string(result.Nifti);
            row.bval_count = numel(mh_fiber_load_bval(result.Bval));
            row.bvec_count = mh_fiber_bvec_count(result.Bvec);
            row.status = 'ok';
            row.message = 'ok';
        catch ME
            row.status = 'error';
            row.message = compact_error(ME);
        end
        rows(end + 1) = row; %#ok<AGROW>
        fprintf('%s %s: %s\n', subjectId, transformName, row.status);
    end
end

status = struct2table(rows, 'AsArray', true);
statusPath = fullfile(opts.OutputRoot, 'orientation_qc_status.csv');
writetable(status, statusPath);
fprintf('Wrote orientation QC status: %s\n', statusPath);
end

function opts = normalize_options(opts)
opts.RepoDir = char(string(opts.RepoDir));
opts.SourceRoot = char(string(opts.SourceRoot));
opts.OutputRoot = char(string(opts.OutputRoot));
opts.SubjectIds = to_cellstr(opts.SubjectIds);
if isempty(opts.SubjectIds)
    error('run_stnsnr_dwi_orientation_qc:MissingSubjectIds', ...
        'SubjectIds must be provided by the project caller.');
end
opts.TransformCandidates = to_cellstr(opts.TransformCandidates);
opts.GenerateColorFa = logical(opts.GenerateColorFa);
opts.AllowIncrementalCorrection = logical(opts.AllowIncrementalCorrection);
opts.Force = logical(opts.Force);
for i = 1:numel(opts.TransformCandidates)
    opts.TransformCandidates{i} = validatestring(opts.TransformCandidates{i}, ...
        {'identity', 'flipY', 'flipZ', 'rotX180', 'rotZ180'}, ...
        'run_stnsnr_dwi_orientation_qc', 'TransformCandidates');
end
end

function values = to_cellstr(value)
if iscell(value)
    values = cellfun(@(x) char(string(x)), value, 'UniformOutput', false);
elseif isstring(value)
    values = cellstr(value(:));
else
    values = {char(string(value))};
end
values = values(~cellfun(@isempty, values));
end

function repoDir = resolve_repo_dir(repoDir)
repoDir = char(string(repoDir));
if ~isempty(repoDir)
    return;
end

current = fileparts(mfilename('fullpath'));
while ~isempty(current)
    if isfile(fullfile(current, 'ea_normalize.m'))
        repoDir = current;
        return;
    end
    parent = fileparts(current);
    if strcmp(parent, current)
        break;
    end
    current = parent;
end
error('run_stnsnr_dwi_orientation_qc:RepoRootNotFound', ...
    'Could not resolve Lead-DBS repository root. Provide RepoDir explicitly.');
end

function source = locate_source_dwi(sourceRoot, subjectId)
subjectDir = fullfile(sourceRoot, ['sub-', subjectId]);
if ~isfolder(subjectDir)
    error('run_stnsnr_dwi_orientation_qc:MissingSubjectDir', ...
        'Subject DWI directory does not exist: %s', subjectDir);
end

files = [dir(fullfile(subjectDir, '*.nii.gz')); dir(fullfile(subjectDir, '*.nii'))];
files = files(~startsWith({files.name}, '._'));
if numel(files) ~= 1
    error('run_stnsnr_dwi_orientation_qc:AmbiguousDwi', ...
        'Expected exactly one source DWI NIfTI in %s, found %d.', subjectDir, numel(files));
end

source = struct();
source.Nifti = fullfile(files(1).folder, files(1).name);
source.Base = mh_fiber_nii_basename(source.Nifti);
source.Json = fullfile(subjectDir, [source.Base, '.json']);
source.Bval = fullfile(subjectDir, [source.Base, '.bval']);
source.Bvec = fullfile(subjectDir, [source.Base, '.bvec']);
mh_util_must_be_file(source.Json, 'source DWI JSON', ...
    'run_stnsnr_dwi_orientation_qc:MissingSidecar');
mh_util_must_be_file(source.Bval, 'source DWI bval', ...
    'run_stnsnr_dwi_orientation_qc:MissingSidecar');
mh_util_must_be_file(source.Bvec, 'source DWI bvec', ...
    'run_stnsnr_dwi_orientation_qc:MissingSidecar');
end

function write_b0_montage(niftiPath, bvalPath, pngPath)
data = single(niftiread(niftiPath));
bvals = mh_fiber_load_bval(bvalPath);
b0Index = find(bvals < 10);
if isempty(b0Index)
    b0Index = 1;
end
if ndims(data) == 4
    b0 = mean(data(:, :, :, b0Index), 4, 'omitnan');
else
    b0 = data;
end
write_scalar_montage_png(b0, pngPath, 'Mean b0');
end

function [status, montagePath] = maybe_run_color_fa_qc(result, candidateDir, generateColorFa)
status = 'skipped';
montagePath = '';
if ~generateColorFa
    return;
end
if ~mrtrix_available()
    status = 'skipped_mrtrix_not_available';
    return;
end

commandsPath = fullfile(candidateDir, 'color_fa_commands.sh');
dwiMif = fullfile(candidateDir, 'dwi.mif');
maskMif = fullfile(candidateDir, 'mask.mif');
tensorMif = fullfile(candidateDir, 'tensor.mif');
faMif = fullfile(candidateDir, 'fa.mif');
v1Mif = fullfile(candidateDir, 'v1.mif');
colorFaMif = fullfile(candidateDir, 'color_fa.mif');
faNii = fullfile(candidateDir, 'fa.nii.gz');
v1Nii = fullfile(candidateDir, 'v1.nii.gz');
colorFaNii = fullfile(candidateDir, 'color_fa.nii.gz');
commands = {
    sprintf('mrconvert %s %s -fslgrad %s %s -json_import %s -force', ...
        q(result.Nifti), q(dwiMif), q(result.Bvec), q(result.Bval), q(result.Json))
    sprintf('dwi2mask %s %s -force', q(dwiMif), q(maskMif))
    sprintf('dwi2tensor %s %s -mask %s -force', q(dwiMif), q(tensorMif), q(maskMif))
    sprintf('tensor2metric %s -fa %s -vector %s -force', q(tensorMif), q(faMif), q(v1Mif))
    sprintf('mrcalc %s -abs %s -mult %s -force', q(v1Mif), q(faMif), q(colorFaMif))
    sprintf('mrconvert %s %s -force', q(faMif), q(faNii))
    sprintf('mrconvert %s %s -force', q(v1Mif), q(v1Nii))
    sprintf('mrconvert %s %s -force', q(colorFaMif), q(colorFaNii))
    };
write_commands(commandsPath, commands);
for i = 1:numel(commands)
    [exitCode, output] = system(commands{i});
    if exitCode ~= 0
        status = ['error_command_', num2str(i), ': ', mh_fiber_compact_message(output)];
        return;
    end
end
montagePath = fullfile(candidateDir, 'color_fa_montage.png');
write_color_fa_montage(colorFaNii, montagePath);
status = 'ok';
end

function available = mrtrix_available()
tools = {'mrconvert', 'dwi2mask', 'dwi2tensor', 'tensor2metric', 'mrcalc'};
available = true;
for i = 1:numel(tools)
    [status, ~] = system(sprintf('command -v %s >/dev/null 2>&1', tools{i}));
    if status ~= 0
        available = false;
        return;
    end
end
end

function write_commands(commandsPath, commands)
fid = fopen(commandsPath, 'w');
if fid < 0
    error('run_stnsnr_dwi_orientation_qc:CommandWriteFailed', ...
        'Could not write commands: %s', commandsPath);
end
cleanupObj = onCleanup(@() fclose(fid));
fprintf(fid, '#!/usr/bin/env bash\nset -euo pipefail\n\n');
for i = 1:numel(commands)
    fprintf(fid, '%s\n', commands{i});
end
clear cleanupObj;
fileattrib(commandsPath, '+x');
end

function write_color_fa_montage(niftiPath, pngPath)
data = single(niftiread(niftiPath));
if ndims(data) ~= 4 || size(data, 4) < 3
    return;
end
data = data(:, :, :, 1:3);
scale = max(data(:));
if scale > 0
    data = data ./ scale;
end
data = min(max(data, 0), 1);

midX = max(1, round(size(data, 1) / 2));
midY = max(1, round(size(data, 2) / 2));
midZ = max(1, round(size(data, 3) / 2));
panels = {
    rotate_rgb(squeeze(data(:, :, midZ, :)))
    rotate_rgb(squeeze(data(:, midY, :, :)))
    rotate_rgb(squeeze(data(midX, :, :, :)))
    };
write_rgb_panel_row(panels, pngPath);
end

function write_scalar_montage_png(volume, pngPath, titleText)
midX = max(1, round(size(volume, 1) / 2));
midY = max(1, round(size(volume, 2) / 2));
midZ = max(1, round(size(volume, 3) / 2));
panels = {
    rot90(squeeze(volume(:, :, midZ)))
    rot90(squeeze(volume(:, midY, :)))
    rot90(squeeze(volume(midX, :, :)))
    };
fig = figure('Visible', 'off', 'Color', 'w', 'Position', [100 100 1200 420]);
cleanupObj = onCleanup(@() close(fig));
names = {'axial', 'coronal', 'sagittal'};
for i = 1:3
    subplot(1, 3, i);
    imagesc(panels{i});
    axis image off;
    colormap gray;
    title([titleText, ' ', names{i}], 'Interpreter', 'none');
end
exportgraphics(fig, pngPath, 'Resolution', 150);
end

function image = rotate_rgb(image)
image = rot90(image);
end

function write_rgb_panel_row(panels, pngPath)
fig = figure('Visible', 'off', 'Color', 'w', 'Position', [100 100 1200 420]);
cleanupObj = onCleanup(@() close(fig));
names = {'axial', 'coronal', 'sagittal'};
for i = 1:3
    subplot(1, 3, i);
    image(panels{i});
    axis image off;
    title(['color FA ', names{i}], 'Interpreter', 'none');
end
exportgraphics(fig, pngPath, 'Resolution', 150);
end

function text = image_size_string(niftiPath)
info = niftiinfo(niftiPath);
text = strjoin(string(double(info.ImageSize)), 'x');
end

function quoted = q(path)
quoted = mh_fiber_shell_quote(path);
end

function message = compact_error(ME)
message = mh_fiber_compact_message(ME.message);
end

function row = empty_row()
row = struct();
row.subject = '';
row.transform = '';
row.status = '';
row.message = '';
row.source_nifti = '';
row.output_dir = '';
row.output_nifti = '';
row.output_json = '';
row.output_bval = '';
row.output_bvec = '';
row.b0_montage = '';
row.color_fa_status = '';
row.color_fa_montage = '';
row.dimensions = '';
row.bval_count = NaN;
row.bvec_count = NaN;
end
