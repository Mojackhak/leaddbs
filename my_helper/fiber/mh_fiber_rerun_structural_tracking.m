function options = mh_fiber_rerun_structural_tracking(subjectDir, fiberCount)
% Rerun patient-specific structural fiber tracking and normalization.

if nargin < 2 || isempty(fiberCount)
    fiberCount = 200000;
end

subjectDir = char(string(subjectDir));
if ~isfolder(subjectDir)
    error('mh_fiber_rerun_structural_tracking:MissingSubjectDir', ...
        'Subject directory does not exist: %s', subjectDir);
end

options = struct();
options = ea_getptopts(subjectDir, options);
options = ea_defaultoptions(options);

[options.root, options.patientname] = fileparts(subjectDir);
options.root = [options.root, filesep];
options.overwriteapproved = 1;
options.leadprod = 'dbs';

options = configure_fiber_normalization_reference(options);
stage_b0_to_t1_transform_for_normalization(options);

prefs = ea_prefs;
lc = struct();
lc.general.parcellation = prefs.lc.defaultParcellation;
lc.graph.degree_centrality = 0;
lc.graph.eigenvector_centrality = 0;
lc.graph.nodal_efficiency = 0;
lc.graph.struc_func_sim = 0;
lc.graph.fthresh = nan;
lc.graph.sthresh = nan;
lc.func.compute_CM = 0;
lc.func.compute_GM = 0;
lc.func.prefs.TR = 2;
lc.struc.compute_CM = 0;
lc.struc.compute_GM = 0;
lc.struc.ft.do = 1;
lc.struc.ft.method = 'ea_ft_gqi_yeh';
lc.struc.ft.dsistudio.fiber_count = fiberCount;
lc.struc.ft.normalize = 0;
lc.struc.ft.upsample.factor = 1;
lc.struc.ft.upsample.how = 0;
lc.nbs.adv.method = 1;
lc.nbs.adv.compsize = 1;
lc.nbs.adv.perm = 5000;
lc.nbs.adv.alpha = 0.05;
lc.nbs.adv.exch = '';
options.lc = lc;

fprintf('Rerunning structural fiber tracking with %d fibers...\n', fiberCount);
ea_perform_ft_proxy(options);

fprintf('Normalizing fibers with the accepted b0-to-anchorNative T1 chain...\n');
options = configure_fiber_normalization_reference(options);
stage_b0_to_t1_transform_for_normalization(options);
ea_normalize_fibers(options);
fprintf('Structural fiber tracking rerun complete.\n');

end

function options = configure_fiber_normalization_reference(options)
% Keep fiber normalization tied to the visually approved b0-to-anchorNative
% T1 ANTs transform rather than the default anatomical filename refreshed by
% ea_getptopts.
options.coregmr.method = 'ANTs';
options.coregb0.addSyN = 0;
options.prefs.prenii_unnormalized = fullfile( ...
    'coregistration', 'anat', ...
    [options.patientname, '_ses-preop_space-anchorNative_desc-preproc_acq-iso_T1w.nii']);
end

function stage_b0_to_t1_transform_for_normalization(options)
subjectDir = fullfile(options.root, options.patientname);
[~, b0Name] = ea_niifileparts(options.prefs.b0);
[~, anatName] = ea_niifileparts(options.prefs.prenii_unnormalized);

expectedName = [b0Name, '2', anatName, '_ants1.mat'];
expectedPath = fullfile(subjectDir, 'preprocessing', 'anat', expectedName);

sourceCandidates = { ...
    fullfile(subjectDir, 'coregistration', 'dwi', expectedName), ...
    fullfile(subjectDir, 'coregistration', 'manual_dwi_t1_coreg', expectedName)};

sourcePath = '';
for i = 1:numel(sourceCandidates)
    if isfile(sourceCandidates{i})
        sourcePath = sourceCandidates{i};
        break;
    end
end

if isempty(sourcePath)
    files = dir(fullfile(subjectDir, 'coregistration', '**', [b0Name, '2', anatName, '_ants*.mat']));
    if ~isempty(files)
        sourcePath = fullfile(files(end).folder, files(end).name);
    end
end

if isempty(sourcePath) || ~isfile(sourcePath)
    error('mh_fiber_rerun_structural_tracking:MissingTransform', ...
        'Could not find b0-to-anchorNative T1 ANTs transform matching %s.', expectedName);
end

if ~isfolder(fileparts(expectedPath))
    mkdir(fileparts(expectedPath));
end

copyfile(sourcePath, expectedPath, 'f');
fprintf('Staged b0-to-T1 transform for fiber normalization:\n%s\n', expectedPath);
end
