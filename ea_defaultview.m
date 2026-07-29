function [] = ea_defaultview(varargin)
% saves and sets default view preferences
% there must be Electrode-Scene figure
%
% ea_defaultview() saves current view as default view
%
% ea_defaultview(v,togglestates) sets view and togglesates
%
% ea_defaultview(resultfig) saves the current view for an explicit figure
%
% ea_defaultview(resultfig,v,togglestates) sets an explicit figure

[resultfig, arguments] = local_resolve_figure(varargin);
togglestates = getappdata(resultfig,'togglestates');
set(0,'CurrentFigure',resultfig);

if isempty(arguments)
    % save current view and togglesates
    ea_setprefs('view',ea_view);
    ea_setprefs('togglestates',getappdata(resultfig,'togglestates'));

elseif numel(arguments) == 2
    % set preferences specified in vararg in
    % togglestates
    viewSpec = arguments{1};
    requestedToggleStates = arguments{2};
    togglestates.xyzmm = requestedToggleStates.xyzmm;
    togglestates.xyztoggles = requestedToggleStates.xyztoggles;
    togglestates.xyztransparencies = ...
        requestedToggleStates.xyztransparencies;
    togglestates.refreshview = 1;
    ea_anatomyslices(resultfig,togglestates,struct,[]);
    % camera view
    ea_view(viewSpec);
    % update togglestates
    setappdata(resultfig,'togglestates',togglestates);
    % update anatomy control
    anatomyWindow = getappdata(resultfig,'awin');
    if ~isempty(anatomyWindow) && isvalid(anatomyWindow)
        close(anatomyWindow);
    end
    options = getappdata(resultfig,'options');
    awin = ea_anatomycontrol(resultfig,options);
    setappdata(resultfig,'awin',awin);
else
    error('ea_defaultview:BadInput', ...
        'Expected zero or two view arguments after an optional figure.');
end

end

function [resultfig, arguments] = local_resolve_figure(arguments)
if ~isempty(arguments) && isscalar(arguments{1}) && ...
        isgraphics(arguments{1}, 'figure')
    resultfig = arguments{1};
    arguments = arguments(2:end);
    return;
end

H = findall(0,'type','figure');
resultfig = H(contains({H(:).Name},'Electrode-Scene'));
if isempty(resultfig)
    error('ea_defaultview:MissingElectrodeScene', ...
        'No Electrode-Scene figure is available.');
end
resultfig = resultfig(1); % take the first if there are many.
end
