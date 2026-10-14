function ea_normalize_ants_d99_deep(options)
% Stage and publish the D99 T1 preset without discarding the prior result.

if ~strcmp(options.bids.spacedef.name, 'D99v2') || ~strcmp(ea_getspace, 'D99v2')
    error('ea_normalize_ants_d99_deep:Space', 'This preset requires D99v2 space.');
end
anchor = options.subj.AnchorModality;
movingImage = options.subj.coreg.anat.preop.(anchor);
if ~strcmpi(ea_getmodality(movingImage, acq=false), 'T1w')
    error('ea_normalize_ants_d99_deep:Anchor', 'This preset requires a preoperative T1w anchor.');
end

templateDir = ea_space(options);
workDir = fullfile(options.subj.subjDir, 'masks', 'ants_d99_deep');
publicationDir = fullfile(workDir, 'publication', ea_generate_uuid);
stagedNormDir = fullfile(publicationDir, 'normalization');
backupDir = fullfile(publicationDir, 'backup');
ea_mkdir(stagedNormDir);
if options.prefs.diary
    diaryFile = [strrep(options.subj.norm.log.logBaseName, options.subj.normDir, stagedNormDir), ...
        char(datetime('now', 'Format', 'yyyyMMdd''T''HHmmss')), '.log'];
    ea_mkdir(fileparts(diaryFile));
    diary(diaryFile);
    diaryCleanup = onCleanup(@() diary('off'));
end
result = ea_ants_d99_deep_run(templateDir, movingImage, workDir);

staged = options;
staged.primarytemplate = 't1';
staged.subj.normDir = stagedNormDir;
for container = {'anat', 'checkreg'}
    name = container{1};
    sessions = fieldnames(options.subj.norm.(name));
    for i = 1:numel(sessions)
        session = sessions{i};
        staged.subj.norm.(name).(session) = structfun( ...
            @(p) strrep(p, options.subj.normDir, stagedNormDir), ...
            options.subj.norm.(name).(session), 'UniformOutput', false);
    end
end
for container = {'transform', 'log'}
    name = container{1};
    staged.subj.norm.(name) = structfun( ...
        @(p) strrep(p, options.subj.normDir, stagedNormDir), ...
        options.subj.norm.(name), 'UniformOutput', false);
end
staged.subj.preopAnat.(anchor).norm = staged.subj.norm.anat.preop.(anchor);
if strcmp(options.subj.postopModality, 'CT')
    staged.subj.postopAnat.CT.norm = staged.subj.norm.anat.postop.CT;
    staged.subj.postopAnat.CT.normTonemap = staged.subj.norm.anat.postop.tonemapCT;
end

% Prior SCRF is normalization-dependent and cannot validate the new result.
hasBrainshift = isfolder(options.subj.brainshiftDir);
staged.subj.brainshift.transform.scrf = '';
staged.normalize.deferApply = false;

forward = [staged.subj.norm.transform.forwardBaseName, 'ants.nii.gz'];
inverse = [staged.subj.norm.transform.inverseBaseName, 'ants.nii.gz'];
ea_mkdir(fileparts(forward));
copyfile(result.forward, forward);
copyfile(result.inverse, inverse);

method.method = 'ANTs (Avants 2008)';
method.approval = 0;
method.settings = struct( ...
    'preset', 'Macaque D99v2: Deep Nuclei (T1)', ...
    'preset_id', 'ea_antspreset_macaque_d99_deep', ...
    'transform', 'SyN', 'metric', 'Mutual Information', ...
    'subcorticalrefine', 1, 'usefa', 0, 'skullstripped', 0, ...
    'interpolation', 'Linear', 'precision', 'double', ...
    'parameters', result.preset);
method.transform = struct('format', 'ants', ...
    'forward', [options.subj.norm.transform.forwardBaseName, 'ants.nii.gz'], ...
    'inverse', [options.subj.norm.transform.inverseBaseName, 'ants.nii.gz']);
method.inputs = struct('anchor_modality', anchor, 'anchor_image', movingImage);
method.masks = result.masks;
method.provenance = result.provenance;
method.downstream.brainshift = struct('requires_rerun', hasBrainshift, ...
    'applied_to_normalized_images', false);
ea_mkdir(fileparts(staged.subj.norm.log.method));
savejson('', method, staged.subj.norm.log.method);

ea_apply_normalization(staged);
if strcmp(options.subj.postopModality, 'CT')
    ea_tonemapct(staged, 'norm');
end
ea_gencheckregfigs(staged, 'norm');

images = {};
figures = {};
preop = fieldnames(options.subj.coreg.anat.preop);
for i = 1:numel(preop)
    name = preop{i};
    if isfile(options.subj.coreg.anat.preop.(name))
        images{end+1, 1} = staged.subj.norm.anat.preop.(name); %#ok<AGROW>
        figures{end+1, 1} = staged.subj.norm.checkreg.preop.(name); %#ok<AGROW>
    end
end
if strcmp(options.subj.postopModality, 'CT')
    if isfile(options.subj.coreg.anat.postop.CT)
        images = [images; {staged.subj.norm.anat.postop.CT; staged.subj.norm.anat.postop.tonemapCT}];
        figures{end+1, 1} = staged.subj.norm.checkreg.postop.tonemapCT;
    end
elseif strcmp(options.subj.postopModality, 'MRI')
    postop = fieldnames(options.subj.coreg.anat.postop);
    for i = 1:numel(postop)
        name = postop{i};
        if isfile(options.subj.coreg.anat.postop.(name))
            images{end+1, 1} = staged.subj.norm.anat.postop.(name); %#ok<AGROW>
            figures{end+1, 1} = staged.subj.norm.checkreg.postop.(name); %#ok<AGROW>
        end
    end
end

reference = ea_load_nii(fullfile(templateDir, 't1.nii'));
for i = 1:numel(images)
    if ~isfile(images{i})
        error('ea_normalize_ants_d99_deep:IncompleteStage', 'Staged image was not created: %s', images{i});
    end
    image = ea_load_nii(images{i});
    if ~isequal(size(image.img), size(reference.img)) || ...
            max(abs(image.mat(:)-reference.mat(:))) > 1e-5 || any(~isfinite(image.img(:)))
        error('ea_normalize_ants_d99_deep:InvalidStage', 'Staged image does not match the finite D99 reference grid: %s', images{i});
    end
end
for i = 1:numel(figures)
    if ~isfile(figures{i})
        error('ea_normalize_ants_d99_deep:IncompleteStage', 'Staged checkreg figure was not created: %s', figures{i});
    end
    imfinfo(figures{i});
end

% Append the methods record in staging, preserving existing history.
[~, methodsName, methodsExtension] = fileparts(options.subj.methodLog);
staged.subj.methodLog = fullfile(publicationDir, 'log', [methodsName, methodsExtension]);
ea_mkdir(fileparts(staged.subj.methodLog));
if isfile(options.subj.methodLog)
    copyfile(options.subj.methodLog, staged.subj.methodLog);
end
ea_methods(staged, ['The preoperative T1 anchor was normalized into D99v2 using ', ...
    'the Macaque D99v2: Deep Nuclei ANTs preset. Automatic template-based operational ', ...
    'brain-mask preparation was followed by rigid and affine MI32 registration, ', ...
    'whole-brain SyN[0.1,3,0], and 2-mm deep-region SyN[0.1,3,1]. ', ...
    'Only T1 estimated the transform. Other images were resampled with Linear ', ...
    'interpolation in double precision. Atlas-derived masks are not independent ', ...
    'segmentation ground truth. Actual commands and mask provenance are retained ', ...
    'in the normalization method log and masks/ants_d99_deep.']);

formalCommandLog = fullfile(fileparts(options.subj.norm.log.method), ...
    ['sub-', options.subj.subjId, '_desc-antscmd.txt']);
stagedCommandLog = strrep(formalCommandLog, options.subj.normDir, stagedNormDir);
if isfile(formalCommandLog)
    copyfile(formalCommandLog, stagedCommandLog);
end
commandText = sprintf('\n%s: D99 preset publication; resolved stage commands (completed stages may be reused)\n', char(datetime('now')));
for name = {'bootstrap', 'linear', 'wholebrain', 'deep'}
    stage = result.provenance.(name{1});
    if ~isempty(fieldnames(stage))
        commandText = [commandText, sprintf('\n%s:\n%s\n', name{1}, fileread(stage.command))]; %#ok<AGROW>
    end
end
file = fopen(stagedCommandLog, 'a');
if file < 0
    error('ea_normalize_ants_d99_deep:CommandLog', 'Could not stage the ANTs command history.');
end
commandLogCleanup = onCleanup(@() fclose(file));
fprintf(file, '%s', commandText);
clear commandLogCleanup;

sources = [{forward; inverse; staged.subj.norm.log.method}; images; figures];
targets = cellfun(@(p) strrep(p, stagedNormDir, options.subj.normDir), sources, 'UniformOutput', false);
sources{end+1, 1} = staged.subj.methodLog;
targets{end+1, 1} = options.subj.methodLog;
sources{end+1, 1} = stagedCommandLog;
targets{end+1, 1} = formalCommandLog;
if options.prefs.diary
    clear diaryCleanup;
    sources{end+1, 1} = diaryFile;
    targets{end+1, 1} = strrep(diaryFile, stagedNormDir, options.subj.normDir);
end
if hasBrainshift && isfile(options.subj.brainshift.log.method)
    brainshiftLog = loadjson(options.subj.brainshift.log.method);
    brainshiftLog.approval = 0;
    stagedBrainshiftLog = fullfile(publicationDir, 'brainshift_method.json');
    savejson('', brainshiftLog, stagedBrainshiftLog);
    sources{end+1, 1} = stagedBrainshiftLog;
    targets{end+1, 1} = options.subj.brainshift.log.method;
end
retire = {};
for name = {'source.json', 'target.json', 'info.json'}
    previous = fullfile(options.subj.warpdriveDir, name{1});
    if isfile(previous)
        retire{end+1, 1} = previous; %#ok<AGROW>
    end
end
preserved = [targets; retire];
priorExists = cellfun(@isfile, preserved);
backups = cell(size(preserved));
for i = find(priorExists)'
    relative = preserved{i}(numel(options.subj.subjDir)+2:end);
    backups{i} = fullfile(backupDir, relative);
    ea_mkdir(fileparts(backups{i}));
    copyfile(preserved{i}, backups{i});
end
receipt = struct('method', method.method, 'preset_id', method.settings.preset_id, ...
    'sources', {sources}, 'targets', {targets}, 'retired_warpdrive', {retire}, ...
    'preserved_paths', {preserved(priorExists)}, 'backup_paths', {backups(priorExists)}, ...
    'status', 'staged');
receiptFile = fullfile(publicationDir, 'publication.json');
savejson('', receipt, receiptFile);
previousRecycle = recycle;
recycleCleanup = onCleanup(@() recycle(previousRecycle)); %#ok<NASGU>
trashed = false(size(preserved));
published = false(size(targets));
try
    for i = find(priorExists)'
        ea_delete(preserved{i}, recycle='on');
        trashed(i) = true;
    end
    for i = 1:numel(targets)
        ea_mkdir(fileparts(targets{i}));
        published(i) = true;
        copyfile(sources{i}, targets{i});
    end
catch publicationError
    for i = find(published)'
        ea_delete(targets{i}, recycle='on');
    end
    for i = find(trashed)'
        ea_mkdir(fileparts(preserved{i}));
        copyfile(backups{i}, preserved{i});
    end
    receipt.status = 'restored_after_failure';
    receipt.error = publicationError.message;
    savejson('', receipt, receiptFile);
    rethrow(publicationError);
end
receipt.status = 'published';
savejson('', receipt, receiptFile);
if hasBrainshift
    ea_cprintf('CmdWinWarnings', 'Normalization has been rerun. Please also rerun brain shift correction!\n');
end
end
