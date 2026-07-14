function result = mh_fiber_prepare_mrtrix_seed_target_subject(manifestPath)
% Transform a validated ROI manifest from MNI space to anchorNative space.

arguments
    manifestPath (1, :) char
end

manifest = jsondecode(fileread(manifestPath));
subjectDir = char(string(manifest.subject_dir));
anchorReference = char(string(manifest.anchor_native_reference));
resultPath = char(string(manifest.result_path));

if ~isfolder(subjectDir)
    error('mh_fiber_prepare_mrtrix_seed_target_subject:MissingSubject', ...
        'Subject directory does not exist: %s', subjectDir);
end
if ~isfile(anchorReference)
    error('mh_fiber_prepare_mrtrix_seed_target_subject:MissingAnchor', ...
        'anchorNative reference does not exist: %s', anchorReference);
end

options = struct();
options = ea_getptopts(subjectDir, options);
options = ea_defaultoptions(options);
options.root = [fileparts(subjectDir), filesep];
[~, options.patientname] = fileparts(subjectDir);

roiRecords = manifest.rois;
if isempty(roiRecords)
    error('mh_fiber_prepare_mrtrix_seed_target_subject:EmptyManifest', ...
        'ROI manifest contains no source images.');
end
sources = cell(numel(roiRecords), 1);
outputs = cell(numel(roiRecords), 1);
for index = 1:numel(roiRecords)
    sources{index} = char(string(roiRecords(index).source));
    outputs{index} = char(string(roiRecords(index).anchor_output));
    if ~isfile(sources{index})
        error('mh_fiber_prepare_mrtrix_seed_target_subject:MissingSource', ...
            'ROI source does not exist: %s', sources{index});
    end
    outputDir = fileparts(outputs{index});
    if ~isfolder(outputDir)
        mkdir(outputDir);
    end
end

ea_apply_normalization_tofile( ...
    options, sources, outputs, 1, 'GenericLabel', anchorReference);

for index = 1:numel(outputs)
    if ~isfile(outputs{index})
        error('mh_fiber_prepare_mrtrix_seed_target_subject:MissingOutput', ...
            'Lead-DBS did not create transformed ROI: %s', outputs{index});
    end
end

result = struct();
result.status = 'complete';
result.subject_id = char(string(manifest.subject_id));
result.subject_dir = subjectDir;
result.anchor_native_reference = anchorReference;
result.roi_count = numel(outputs);
result.matlab_version = version;
result.matlab_release = version('-release');

resultDir = fileparts(resultPath);
if ~isfolder(resultDir)
    mkdir(resultDir);
end
temporaryPath = [resultPath, '.tmp'];
fileId = fopen(temporaryPath, 'w');
if fileId < 0
    error('mh_fiber_prepare_mrtrix_seed_target_subject:ResultOpenFailed', ...
        'Cannot open result file: %s', temporaryPath);
end
cleanup = onCleanup(@() fclose(fileId));
fprintf(fileId, '%s\n', jsonencode(result, PrettyPrint=true));
clear cleanup;
movefile(temporaryPath, resultPath, 'f');
end
