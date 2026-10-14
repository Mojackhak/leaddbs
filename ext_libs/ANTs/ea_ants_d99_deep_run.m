function result = ea_ants_d99_deep_run(templateDir, movingImage, workDir, preparedMasks)
% Run the fixed D99 profile without publishing or reading prior patient warps.
arguments
    templateDir {mustBeFolder}
    movingImage {mustBeFile}
    workDir {mustBeTextScalar}
    preparedMasks struct = struct
end

preset = ea_antspreset_macaque_d99_deep(struct);
fixedSource = ea_niigz(fullfile(templateDir, 't1.nii'));
assert(isfile(fixedSource), 'The D99 T1 reference is missing.');
ea_mkdir(workDir);
environmentNames = {'ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS','OMP_NUM_THREADS', ...
    'OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'};
previousEnvironment = cellfun(@getenv, environmentNames, 'UniformOutput', false);
environmentCleanup = onCleanup(@() restore_environment(environmentNames, previousEnvironment)); %#ok<NASGU>
cellfun(@(name) setenv(name, '1'), environmentNames);
ea_libs_helper;
ants = ea_getExec(fullfile(ea_getearoot, 'ext_libs', 'ANTs', 'antsRegistration'));
apply = ea_getExec(fullfile(ea_getearoot, 'ext_libs', 'ANTs', 'antsApplyTransforms'));

% Own uncompressed copies prevent readers from unpacking beside source images.
inputDir = fullfile(workDir, 'inputs');
fixed = fullfile(inputDir, 'fixed.nii');
moving = fullfile(inputDir, 'moving.nii');
spec = struct('inputs', file_records({fixedSource,movingImage}));
newInputs = start_stage(inputDir, spec, {fixed,moving});
if newInputs
    copy_image(fixedSource, fixed);
    copy_image(movingImage, moving);
end
fixedNii = read_image(fixed);
movingNii = read_image(moving);
if newInputs, finish_stage(inputDir, spec); end
supplied = ~isempty(fieldnames(preparedMasks));
if supplied
    assert(all(isfield(preparedMasks, {'fixed','moving','deep'})), ...
        'Prepared masks must specify fixed, moving, and deep paths.');
end

fixedDir = fullfile(workDir, 'fixed_mask');
fixedMask = fullfile(fixedDir, 'mask.nii');
fixedInputs = {fixed};
if supplied
    fixedInputs{end+1} = preparedMasks.fixed;
end
spec = struct('inputs', file_records(fixedInputs), 'supplied', supplied, ...
    'method', 'largest_positive_6_connected_component_fill_holes');
newFixed = start_stage(fixedDir, spec, {fixedMask});
if newFixed
    if supplied
        copy_image(preparedMasks.fixed, fixedMask);
    else
        brain = largest_filled(fixedNii.img > 0);
        write_mask(fixedMask, brain, fixedNii);
    end
end
fixedBrain = read_mask(fixedMask, fixedNii);
if newFixed, finish_stage(fixedDir, spec); end

deepDir = fullfile(workDir, 'deep_mask');
deepMask = fullfile(deepDir, 'mask.nii');
if supplied
    deepInputs = {fixed, fixedMask, preparedMasks.deep};
    atlasFiles = {};
else
    atlasFiles = atlas_files(templateDir);
    deepInputs = [{fixed,fixedMask}, atlasFiles];
end
spec = struct('inputs', file_records(deepInputs), 'supplied', supplied, ...
    'margin_mm', preset.deepMarginMm);
if start_stage(deepDir, spec, {deepMask})
    if supplied
        copy_image(preparedMasks.deep, deepMask);
        deep = read_mask(deepMask, fixedNii);
    else
        nuclei = atlas_union(atlasFiles, fixedNii);
        assert(~any(nuclei(:) & ~fixedBrain(:)), 'D99 target ROIs extend outside the fixed brain mask.');
        spacing = sqrt(sum(fixedNii.mat(1:3,1:3).^2,1));
        assert(max(spacing)-min(spacing)<1e-6, 'The D99 profile requires an isotropic template grid.');
        deep = bwdist(nuclei)*spacing(1) <= preset.deepMarginMm & fixedBrain;
        write_mask(deepMask, deep, fixedNii);
        write_mask(fullfile(deepDir,'nuclei.nii'), nuclei, fixedNii);
    end
    assert(~any(deep(:) & ~fixedBrain(:)), 'The deep mask extends outside the brain mask.');
    finish_stage(deepDir, spec);
end

nativeDir = fullfile(workDir, 'native_mask');
nativeMask = fullfile(nativeDir, 'mask.nii');
bootstrap = struct;
if supplied
    nativeInputs = {moving,preparedMasks.moving};
else
    bootstrapDir = fullfile(workDir, 'bootstrap');
    init = ['[',ea_path_helper(fixed),',',ea_path_helper(moving),',0]'];
    bootstrap = registration(bootstrapDir, fixed, moving, fixedMask, 'NULL', ...
        preset.bootstrap, {'rigid','affine','syn'}, init, {}, struct);
    nativeInputs = {moving,fixedMask,bootstrap.inverse};
end
spec = struct('inputs',file_records(nativeInputs),'supplied',supplied, ...
    'method','nearest_neighbor_projection_largest_6_connected_fill_holes');
if start_stage(nativeDir, spec, {nativeMask})
    if supplied
        copy_image(preparedMasks.moving, nativeMask);
        read_mask(nativeMask, movingNii);
    else
        projected = fullfile(nativeDir,'projected.nii');
        command = [apply,' -d 3 --float 0 -i ',ea_path_helper(fixedMask), ...
            ' -r ',ea_path_helper(moving),' -t ',ea_path_helper(bootstrap.inverse), ...
            ' -n NearestNeighbor -o ',ea_path_helper(projected)];
        run_command(command,nativeDir,'project_mask');
        mask = read_mask(projected,movingNii);
        write_mask(nativeMask,largest_filled(mask),movingNii);
    end
    finish_stage(nativeDir,spec);
end

if supplied
    init = ['[',ea_path_helper(fixedMask),',',ea_path_helper(nativeMask),',1]'];
    initialInputs = {};
    initialization = 'brain_mask_center_of_mass';
else
    affineDir = fullfile(workDir,'bootstrap_affine');
    affineFile = fullfile(affineDir,'initial.tfm');
    spec = struct('inputs',file_records({bootstrap.composite}), ...
        'component','AffineTransform_double_3_3','format','ITK_text');
    if start_stage(affineDir,spec,{affineFile})
        extract_affine(bootstrap.composite,affineFile);
        finish_stage(affineDir,spec);
    end
    init = ea_path_helper(affineFile);
    initialInputs = {affineFile};
    initialization = 'bootstrap_affine';
    bootstrap.affine_initialization = affineFile;
end
linear = registration(fullfile(workDir,'linear'),fixed,moving,fixedMask,nativeMask, ...
    preset,{'rigid','affine'},init,initialInputs,struct);
whole = registration(fullfile(workDir,'wholebrain'),fixed,moving,fixedMask,nativeMask, ...
    preset,{'syn'},ea_path_helper(linear.composite),{linear.composite},struct);
deep = registration(fullfile(workDir,'deep'),fixed,moving,deepMask,nativeMask, ...
    preset,{'scrf'},ea_path_helper(whole.forward),{whole.forward,whole.inverse},whole);

qaDir = fullfile(workDir,'mask_qa');
qaPaths = {fullfile(qaDir,'fixed.png'),fullfile(qaDir,'native.png'),fullfile(qaDir,'deep.png')};
spec = struct('inputs',file_records({fixed,moving,fixedMask,nativeMask,deepMask}), ...
    'renderer','ea_gencheckregpair','percentiles',[0.2,99.7]);
if start_stage(qaDir,spec,qaPaths)
    ea_gencheckregpair(fixed,fixedMask,qaPaths{1});
    ea_gencheckregpair(moving,nativeMask,qaPaths{2});
    ea_gencheckregpair(fixed,deepMask,qaPaths{3});
    finish_stage(qaDir,spec);
end

result = struct('forward',deep.forward,'inverse',deep.inverse,'warped',deep.warped, ...
    'masks',struct('fixed',fixedMask,'moving',nativeMask,'deep',deepMask,'qa',{qaPaths}), ...
    'preset',preset);
provenance = struct('profile','ea_antspreset_macaque_d99_deep', ...
    'sources',file_records({fixedSource,movingImage}),'prepared_masks_supplied',supplied, ...
    'initialization',initialization, ...
    'bootstrap',bootstrap,'linear',linear,'wholebrain',whole,'deep',deep, ...
    'mask_records',{{fullfile(fixedDir,'complete.json'),fullfile(nativeDir,'complete.json'), ...
                    fullfile(deepDir,'complete.json')}}, ...
    'note','Operational masks and image fit are not independent nucleus-localization ground truth.');
result.provenance = provenance;
result.provenance_file = fullfile(workDir,'provenance.json');
replace_record(result.provenance_file,provenance);

    function output = registration(folder,fixedImage,movingImage,fMask,mMask,parameters,stages,initial,parentInputs,parent)
        prefix = fullfile(folder,'transform_');
        output = struct('forward',fullfile(folder,'forward.nii.gz'), ...
            'inverse',fullfile(folder,'inverse.nii.gz'),'warped',fullfile(folder,'warped.nii'), ...
            'record',fullfile(folder,'complete.json'),'command',fullfile(folder,'registration.txt'));
        residual = ~isempty(fieldnames(parent));
        if ~residual
            output.composite = [prefix,'Composite.h5'];
        end
        command = [ants,' --dimensionality 3 --float ',num2str(preset.float), ...
            ' --verbose 1 --random-seed ',num2str(preset.randomseed), ...
            ' --use-histogram-matching 0 --interpolation ',preset.interpolation, ...
            ' --output [',ea_path_helper(prefix),',',ea_path_helper(output.warped),']', ...
            ' --write-composite-transform ',num2str(~residual), ...
            ' --collapse-output-transforms ',num2str(~residual), ...
            ' --initial-moving-transform ',initial];
        for s = 1:numel(stages)
            name = stages{s};
            switch name
                case 'rigid', transform = 'Rigid';
                case 'affine', transform = 'Affine';
                otherwise, transform = 'SyN';
            end
            stage = parameters.(name);
            command = [command,' --transform ',transform,'[',stage.gradientstep,']', ...
                ' --metric ',stage.metric,'[',ea_path_helper(fixedImage),',', ...
                ea_path_helper(movingImage),',',stage.metricparams,']', ...
                ' --convergence ',stage.convergence,' --shrink-factors ',stage.shrinkfactors, ...
                ' --smoothing-sigmas ',stage.smoothingsigmas, ...
                ' --masks [',mask_path(fMask),',',mask_path(mMask),']']; %#ok<AGROW>
        end
        inputs = [{fixedImage,movingImage,fMask},parentInputs];
        if ~strcmp(mMask,'NULL'), inputs{end+1} = mMask; end
        stageSpec = struct('inputs',file_records(inputs),'command',command, ...
            'threads',1,'precision','double');
        required = {output.forward,output.inverse,output.warped};
        if ~residual, required{end+1} = output.composite; end
        if start_stage(folder,stageSpec,required)
            run_command(command,folder,'registration');
            if residual
                forwardChain = {[prefix,'1Warp.nii.gz'],parent.forward};
                inverseChain = {parent.inverse,[prefix,'1InverseWarp.nii.gz']};
            else
                forwardChain = {[prefix,'Composite.h5']};
                inverseChain = {[prefix,'InverseComposite.h5']};
            end
            compose_field(apply,fixedImage,output.forward,forwardChain,folder,'compose_forward',preset.float);
            compose_field(apply,movingImage,output.inverse,inverseChain,folder,'compose_inverse',preset.float);
            validate_field(output.forward,fixedNii.dim);
            validate_field(output.inverse,movingNii.dim);
            read_image(output.warped);
            finish_stage(folder,stageSpec);
        end
    end
end

function path = mask_path(path)
if ~strcmp(path,'NULL'), path = ea_path_helper(path); end
end

function compose_field(apply,reference,output,chain,folder,name,floatPrecision)
command = [apply,' -d 3 --float ',num2str(floatPrecision),' -r ',ea_path_helper(reference), ...
    ' -o [',ea_path_helper(output),',1]'];
for index=1:numel(chain)
    command = [command,' -t ',ea_path_helper(chain{index})]; %#ok<AGROW>
end
run_command(command,folder,name);
end

function run_command(command,folder,name)
file = fopen(fullfile(folder,[name,'.txt']),'w');
fprintf(file,'%s\n',command); fclose(file);
fprintf('D99 ANTs: %s / %s\n',folder,name);
status = ea_runcmd([command,' > ',ea_path_helper(fullfile(folder,[name,'.log'])),' 2>&1']);
if status~=0
    error('D99:CommandFailed','ANTs command failed; inspect %s.',fullfile(folder,[name,'.log']));
end
end

function run = start_stage(folder,spec,outputs)
record = fullfile(folder,'complete.json');
normalized = jsondecode(jsonencode(spec));
if isfile(record)
    previous = jsondecode(fileread(record));
    if isequaln(previous.spec,normalized) && all(cellfun(@isfile,outputs))
        fprintf('D99 ANTs: reuse %s\n',folder); run=false; return;
    end
end
if isfolder(folder), ea_delete(folder,recycle='on'); end
mkdir(folder); run=true;
end

function finish_stage(folder,spec)
record = struct('spec',spec,'completed_utc',char(datetime('now','TimeZone','UTC', ...
    'Format','yyyy-MM-dd''T''HH:mm:ss.SSSXXX')));
write_record(fullfile(folder,'complete.json'),record);
end

function records = file_records(paths)
records = repmat(struct('path','','bytes',0,'modified',0),numel(paths),1);
for index=1:numel(paths)
    path = GetFullPath(paths{index}); data=dir(path);
    assert(numel(data)==1 && ~data.isdir,'Required input is missing: %s',path);
    records(index)=struct('path',path,'bytes',data.bytes,'modified',data.datenum);
end
end

function copy_image(source,destination)
if endsWith(source,'.gz')
    packed=[destination,'.gz']; copyfile(source,packed); gunzip(packed);
    ea_delete(packed,recycle='on');
else
    copyfile(source,destination);
end
end

function nii = read_image(path)
nii=ea_load_nii(path);
assert(ndims(nii.img)==3 && all(isfinite(nii.img(:))), ...
    'Expected a finite three-dimensional intensity image: %s',path);
assert(all(isfinite(nii.mat(:))) && det(nii.mat(1:3,1:3))~=0, ...
    'Invalid NIfTI image geometry: %s',path);
end

function mask = read_mask(path,reference)
nii=read_image(path);
assert(isequal(size(nii.img),size(reference.img)) && ...
    max(abs(nii.mat(:)-reference.mat(:)))<1e-5,'Mask grid differs from its reference: %s',path);
assert(all(nii.img(:)==0 | nii.img(:)==1),'Mask is not binary: %s',path);
mask=logical(nii.img);
assert(any(mask(:)),'Mask is empty: %s',path);
end

function mask = largest_filled(mask)
components=bwconncomp(mask,6);
assert(components.NumObjects>0,'The projected or template brain mask is empty.');
[~,largest]=max(cellfun(@numel,components.PixelIdxList));
mask=false(size(mask)); mask(components.PixelIdxList{largest})=true;
mask=imfill(mask,6,'holes');
end

function write_mask(path,mask,reference)
nii=reference; nii.fname=path; nii.img=double(mask); nii.dt=[2,0]; nii.pinfo=[1;0;0];
nii.descrip='D99 operational registration mask'; ea_write_nii(nii);
end

function files = atlas_files(templateDir)
atlas=fullfile(templateDir,'atlases');
thalamus=fullfile(atlas,'D99 v2.0 thalamus (Saleem KS 2021)');
deep=fullfile(atlas,'D99 v2.0 VA_VL_STN_SN_RN_GP (Saleem KS 2021)');
groups={}; counts=zeros(1,3);
for side={'lh','rh'}
    patterns={fullfile(thalamus,side{1},'*_Thalamus.nii'), ...
        fullfile(deep,side{1},'STN.nii'),fullfile(deep,side{1},'SN*.nii')};
    for k=1:3
        entries=dir(patterns{k}); entries=entries(~startsWith({entries.name},'._'));
        counts(k)=counts(k)+numel(entries);
        groups=[groups,arrayfun(@(entry) fullfile(entry.folder,entry.name),entries,'UniformOutput',false)']; %#ok<AGROW>
    end
end
assert(isequal(counts,[66,2,8]),'D99 deep profile requires the installed 66 thalamic, 2 STN and 8 SN ROIs.');
files=sort(groups);
end

function mask = atlas_union(files,reference)
mask=false(size(reference.img));
for index=1:numel(files)
    roi=read_image(files{index});
    assert(all(roi.img(:)==0 | roi.img(:)==1),'Atlas ROI must be binary: %s',files{index});
    [i,j,k]=ind2sub(size(roi.img),find(roi.img));
    mapped=reference.mat\(roi.mat*[i';j';k';ones(1,numel(i))]);
    voxel=round(mapped(1:3,:));
    assert(max(abs(mapped(1:3,:)-voxel),[],'all')<1e-5,'Atlas ROI is not aligned to D99.');
    assert(all(voxel>=1,'all') && all(voxel<=reference.dim','all'),'Atlas ROI lies outside D99.');
    mask(sub2ind(size(mask),voxel(1,:),voxel(2,:),voxel(3,:)))=true;
end
end

function validate_field(path,dimensions)
info=niftiinfo(path); data=niftiread(info);
assert(isequal(size(data),[dimensions,1,3]),'ANTs field has an unexpected reference grid: %s',path);
assert(all(isfinite(data(:))),'ANTs field contains nonfinite vectors: %s',path);
end

function replace_record(path,data)
if isfile(path)
    previous=jsondecode(fileread(path));
    if isequaln(previous,jsondecode(jsonencode(data))), return; end
    ea_delete(path,recycle='on');
end
write_record(path,data);
end

function write_record(path,data)
file=fopen(path,'w'); assert(file~=-1,'Cannot write record: %s',path);
fprintf(file,'%s\n',jsonencode(data,PrettyPrint=true)); fclose(file);
end

function restore_environment(names,values)
for index=1:numel(names), setenv(names{index},values{index}); end
end


function extract_affine(composite,output)
% Preserve the ITK LPS parameters and center without inversion or conversion.
info=h5info(composite,'/TransformGroup');
found=0;
for index=1:numel(info.Groups)
    group=info.Groups(index).Name;
    type=char(h5read(composite,[group,'/TransformType']));
    if strcmp(strtrim(type),'AffineTransform_double_3_3')
        AffineTransform_double_3_3=double(h5read(composite,[group,'/TransformParameters']));
        fixed=double(h5read(composite,[group,'/TransformFixedParameters']));
        found=found+1;
    end
end
assert(found==1,'Expected one collapsed affine component in the bootstrap transform.');
AffineTransform_double_3_3=AffineTransform_double_3_3(:);
fixed=fixed(:);
file=fopen(output,'w');
assert(file~=-1,'Cannot write the bootstrap affine: %s',output);
fprintf(file,'#Insight Transform File V1.0\n#Transform 0\n');
fprintf(file,'Transform: AffineTransform_double_3_3\nParameters:');
fprintf(file,' %.17g',AffineTransform_double_3_3);
fprintf(file,'\nFixedParameters:');
fprintf(file,' %.17g',fixed);
fprintf(file,'\n'); fclose(file);
end
