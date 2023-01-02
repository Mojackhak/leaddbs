function fibhandle=ea_showfiber(fibers,fibidx,col,fiberalpha,verbose)

if ~exist('col','var')
    col=nan;
end

if ~exist('fiberalpha','var')
    fiberalpha=0.2;
end
if ~exist('verbose','var')
    verbose=1;
end

% Adapt tube width and fv reduce factor for rat (and other) space[s]
if ismember(ea_getspace, {'Waxholm_Space_Atlas_SD_Rat_Brain'})
    sampleFactor = 1; % Do not reduce the points along the fiber
    tubeWidth = 0.02; % Smaller tube width
    reduceFactor = 0; % No patch reduce
else
    sampleFactor = 5; % Reduce the points along the fiber by a factor of 5
    tubeWidth = 0.25; % Larger tube width
    reduceFactor = 0.1; % Set patch reduce factor
end

if ~iscell(fibers)
    if ~(size(fibers,1)==4)
        fibers=fibers';
    end

    fibersnew=mat2cell(fibers(1:3,:)',fibidx);

    fibersnew = cellfun(@(f,len) f(round(linspace(1,len,round(len/sampleFactor))),:), fibersnew, num2cell(cellfun(@(p) size(p,1), fibersnew)), 'UniformOutput', 0);

    k = 1;
    while k <= length(fibersnew)
        if length(fibersnew{k}(:,1)) <= 1
            fibersnew(k) = [];
        else
            k = k+1;
        end
    end
else
    fibersnew=fibers;
end
clear fibers
if isnan(col)
    if verbose
        ea_dispercent(0,'Determine Directions');
    end
    k = 1;
    for k = 1:length(fibersnew)
        if verbose
            ea_dispercent(k/length(fibersnew))
        end
        fibersdiff{k} = abs(diff(fibersnew{k}));
        fibersdiff{k} = vertcat(fibersdiff{k},fibersdiff{k}(end,:));
        for l = 1:length(fibersdiff{k}(:,1))
            fibersdiff{k}(l,:) = fibersdiff{k}(l,:)/norm(fibersdiff{k}(l,:));
        end
    end
    if verbose
        ea_dispercent(1,'end');
    end
end

% Downsample fibers. TODO: Need further validation!
numFiberThreshold = 500;
if length(fibersnew) < numFiberThreshold
    idx = 1:length(fibersnew);
else
    idx = ceil(linspace(1, length(fibersnew), numFiberThreshold));
end

try
    fibhandle = streamtube(fibersnew(idx), tubeWidth);
catch
    keyboard
end
set(fibhandle(:),'CDataMapping','direct')

fprintf('\n');
if isnan(col)
    if verbose
        ea_dispercent(0,'Adding color information');
    end
    for k = 1:length(fibhandle)
        thiscol = fibersdiff{k};
        thiscol = repmat(thiscol,1,1,length(fibhandle(k).ZData(1,:,1)));
        thiscol = permute(thiscol,[1 3 2]);
        set(fibhandle(k),'CData',thiscol)
        if verbose
            ea_dispercent(k/length(fibhandle))
        end
    end
    if verbose
        ea_dispercent(1,'end');
    end
else
    if verbose
        ea_dispercent(0,'Adding color information');
    end
    for k = 1:length(fibhandle)
        thiscol = repmat(col,length(fibhandle(k).ZData(:,1)),1);
        thiscol = repmat(thiscol,1,1,length(fibhandle(k).ZData(1,:,1)));
        thiscol = permute(thiscol,[1 3 2]);
        set(fibhandle(k),'CData',thiscol)
        if verbose
            ea_dispercent(k/length(fibhandle))
        end
    end
    if verbose
        ea_dispercent(1,'end');
    end
end

% we could be done here - but now lets concatenate the tracts for faster
% visualization
afv = ea_concatfv(fibhandle, 0, reduceFactor, verbose);
delete(fibhandle);

fibhandle=patch('Faces',afv.faces,'Vertices',afv.vertices,'FaceVertexCData',afv.facevertexcdata,'EdgeColor','none','FaceAlpha',fiberalpha,'CDataMapping','direct','FaceColor','flat');
