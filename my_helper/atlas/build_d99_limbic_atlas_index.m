function build_d99_limbic_atlas_index()
% Build a native Lead-DBS display cache without changing full-grid masks.

repo = fileparts(fileparts(fileparts(mfilename('fullpath'))));
spec = jsondecode(fileread(fullfile(repo,'my_helper','atlas','specs','d99_limbic_regions.json')));
output = fullfile(repo,spec.output_dir);
manifest = jsondecode(fileread(fullfile(output,'roi_manifest.json')));
indexFile = fullfile(output,'atlas_index.mat');
assert(~isfile(indexFile),'Refusing to replace an existing display cache.');
sourceCache = load(fullfile(repo,'templates','space','D99v2','atlases', ...
    'D99 v2.0 NAc_ALIC','atlas_index.mat'),'atlases');
entries = manifest.rois(strcmp({manifest.rois.side},'lh'));
names = {entries.roi_name};
count = numel(names);
colors = zeros(count,3);
baseColors = struct('NAc',[0.51,0.82,0.26], 'ALIC',[0.19,0.44,0.72], ...
    'GPi',[0.83,0.36,0.15], 'GPe',[0.95,0.69,0.18], ...
    'AMY',[0.78,0.24,0.39], 'HIP',[0.15,0.66,0.62], ...
    'mPFC',[0.45,0.34,0.73]);
for k = 1:count
    family = entries(k).family;
    group = find(strcmp({entries.family},family));
    rank = find(group==k);
    colors(k,:) = baseColors.(family);
    if ~isempty(entries(k).parent)
        mix = 0.55 + 0.4*(rank-1)/max(1,numel(group)-1);
        colors(k,:) = colors(k,:)*mix + (1-mix);
    end
end
atlases.names = strcat(names,'.nii.gz');
atlases.types = 3*ones(1,count);
atlases.tissuetypes = ones(1,count);
atlases.tissuetypes(strcmp(names,'ALIC')) = 2;
atlases.threshold = struct('type','absolute_intensity','value',0.5);
atlases.colormap = colors;
atlases.colors = 1:count;
atlases.version = sourceCache.atlases.version;
atlases.rebuild = 0;
atlases.defaultset = 1;
parents = find(ismember(names,{'AMY','HIP','mPFC'}));
independent = find(ismember(names,{'NAc','ALIC','GPi','GPe'}));
merged = sort([independent,parents]);
subregions = setdiff(1:count,parents);
atlases.presets(1) = struct('label','Merged regions','show',merged,'hide',setdiff(1:count,merged));
atlases.presets(2) = struct('label','Subregions','show',subregions,'hide',parents);
atlases.subgroups(1) = struct('label','Independent regions','entries',independent);
for k = 1:3
    family = {'AMY','HIP','mPFC'};
    atlases.subgroups(k+1) = struct('label',family{k}, ...
        'entries',find(strcmp({entries.family},family{k})));
end
atlases.citation = struct('name','D99-derived limbic, frontal, and pallidal regions', ...
    'long',{{'Regional labels: D99 v2.0 (Saleem KS 2021). ALIC: existing local D99 NAc_ALIC delineation. Merged definitions are project-specific.'}});
atlases.roi = cell(count,2);
atlases.fv = cell(count,2);
atlases.XYZ = cell(count,2);
atlases.pixdim = cell(count,2);
fig = figure('Visible','off','Name','D99 atlas cache construction');
cleanup = onCleanup(@() close(fig));
for k = 1:count
    for side = 1:2
        sideNames = {'rh','lh'};
        sideName = sideNames{side};
        record = manifest.rois(strcmp({manifest.rois.roi_name},names{k}) & ...
            strcmp({manifest.rois.side},sideName));
        nii = ea_load_nii(record.cache_crop);
        nii.fname = record.output_file;
        properties = struct('nii',nii,'name',names{k},'color',colors(k,:), ...
            'threshold',0.5,'smooth',0,'hullsimplify',0,'binary',1,'plotFigureH',[]);
        object = ea_roi(record.output_file,properties);
        assert(~isempty(object.fv.faces) && ~isempty(object.fv.vertices), ...
            'Native ROI surface is empty: %s %s',names{k},sideName);
        atlases.roi{k,side} = object;
        [x,y,z] = ind2sub(size(nii.img),find(nii.img>0));
        points.vx = [x,y,z];
        points.val = nii.img(nii.img>0);
        points.mm = ea_vox2mm(points.vx,nii.mat);
        points.dims = nii.voxsize;
        atlases.XYZ{k,side} = points;
        atlases.pixdim{k,side} = nii.voxsize(1:3);
        fprintf('Native cache: %s %s\n',sideName,names{k});
    end
end
ea_saveatlas(fileparts(output),spec.atlas_name,atlases);
loaded = ea_loadatlas(indexFile,fig,[]);
assert(isequal(size(loaded.roi),[36,2]));
assert(all(loaded.types==3));
for k = 1:count
    for side = 1:2
        assert(nnz(loaded.roi{k,side}.nii.img)>0);
        assert(strcmp(loaded.roi{k,side}.niftiFilename, ...
            fullfile(output,sideNames{side},[names{k},'.nii.gz'])));
    end
end
qcDir = fullfile(output,'qc');
if ~isfolder(qcDir), mkdir(qcDir); end
% Render the existing native ROI meshes for the two approved selections.
for selection = 1:2
    preview = figure('Visible','off','Color','w','Position',[100,100,1400,650]);
    for panel = 1:2
        ax = subplot(1,2,panel,'Parent',preview);
        hold(ax,'on');
        for k = loaded.presets(selection).show
            for side = 1:2
                surface = loaded.roi{k,side}.sfv;
                patch(ax,'Faces',surface.faces,'Vertices',surface.vertices, ...
                    'FaceColor',colors(k,:),'EdgeColor','none','FaceAlpha',1);
            end
        end
        axis(ax,'equal','tight','off');
        if panel==1, view(ax,3); else, view(ax,0,90); end
        camlight(ax,'headlight');
        lighting(ax,'gouraud');
        title(ax,loaded.presets(selection).label);
    end
    exportgraphics(preview,fullfile(qcDir, ...
        sprintf('native_%s.png',lower(strrep(loaded.presets(selection).label,' ','_')))), ...
        'Resolution',150);
    close(preview);
end
report = struct('bilateral_entries',count,'native_roi_objects',numel(loaded.roi), ...
    'native_load_passed',true,'all_surfaces_nonempty',true,'full_grid_masks_untouched',true, ...
    'cache_format_preserved',loaded.version,'default_preset',loaded.presets(1).label);
fid = fopen(fullfile(output,'native_cache_qc.json'),'w');
fprintf(fid,'%s\n',jsonencode(report,PrettyPrint=true));
fclose(fid);
fprintf('Native atlas cache and rendering checks passed.\n');
end
