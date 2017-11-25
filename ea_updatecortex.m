function [structures] = ea_updatecortex(options,resultfig,sides,structures,labelidx,alpha)

cortex = getappdata(resultfig,'cortex');
annot = getappdata(resultfig,'annot');

if ~exist('alpha','var')
    alpha = options.prefs.d3.cortexalpha;
end

if iscell(labelidx{1}) % both sides
   labelstruct = labelidx; 
end
for s = sides
    if exist('labelstruct','var')
        labelidx = labelstruct{s};
    end
    vertices=cortex{s}.Vertices;
    annot(s).adat=ones(size(vertices,1),1)*alpha;
    
    % Choose gyri
    % labels = cell2mat(arrayfun(@(x) find(x==annot(s).label),annot(s).colortable.table(:,5),'uni',0));    
    structidx = arrayfun(@(x) find(annot(s).label==annot(s).colortable.table(x,5)),[labelidx{:}],'uni',0);
    for i=1:length(structidx)
        colorindex = structidx{i};
        %annot(s).cdat(colorindex,:) = repmat(annot(s).colortable.table(i,1:3)/256,[length(colorindex),1]);
        annot(s).adat(colorindex,:) = alpha;
    end
    
    labelsoff = setdiff(1:length(annot(s).colortable.table),cell2mat(labelidx));
    invisidx = arrayfun(@(x) find(annot(s).label==annot(s).colortable.table(x,5)),labelsoff,'uni',0);
    for i=1:length(invisidx)
        %annot(s).cdat(invisidx{i},:) = repmat(annot(s).colortable.table(i,1:3)/256,[length(colorindex),1]);
        annot(s).adat(invisidx{i},:) = 0;
    end
    
    %annot(side).adat(annot(side).adat==0.1111)=0;
    set(cortex{s},'FaceVertexCData',annot(s).cdat);
    set(cortex{s},'FaceVertexAlphaData',annot(s).adat,'FaceAlpha','interp');
    
end
    setappdata(resultfig,'cortex',cortex);
    setappdata(resultfig,'annot',annot);
end