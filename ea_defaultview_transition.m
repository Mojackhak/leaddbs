function [] = ea_defaultview_transition(varargin)
% transition between current view and defaultview

[resultfig, v, ~] = local_resolve_inputs(varargin);
set(0,'CurrentFigure',resultfig);

togglestates_init = getappdata(resultfig,'togglestates');
togglestates_init.xyztransparencies(~togglestates_init.xyztoggles) = 0;
togglestates_init.xyztoggles = [1 1 1]; 
togglestates_init.refreshview = 1;

v_init = ea_view();


v_az_diff = (v.az - v_init.az);
v_el_diff = (v.el - v_init.el);
v_camva_diff = (v.camva - v_init.camva);
v_camup_diff = (v.camup - v_init.camup);
v_out.camproj = 'orthographic';
v_camtarget_diff = (v.camtarget - v_init.camtarget);
v_campos_diff = (v.campos - v_init.campos);

speed_factor = 60;
steps = abs(v_camva_diff) / 40;
steps = steps + max(abs(v_campos_diff)) / 800;
steps = steps + max(abs(v_camtarget_diff)) / 500;

steps = round(steps * speed_factor);

for i = 1:steps
    v_out.az = v_init.az + v_az_diff / steps * i;
    v_out.el = v_init.el + v_el_diff / steps * i;
    v_out.camva = v_init.camva + v_camva_diff / steps * i;
    v_out.camup = v_init.camup + v_camup_diff / steps * i;
    v_out.camtarget = v_init.camtarget + v_camtarget_diff / steps * i;
    v_out.campos = v_init.campos + v_campos_diff / steps * i;
    ea_view(v_out);
    drawnow
end

end

function [resultfig, v, togglestates] = local_resolve_inputs(arguments)
if numel(arguments) == 3 && isscalar(arguments{1}) && ...
        isgraphics(arguments{1}, 'figure')
    resultfig = arguments{1};
    v = arguments{2};
    togglestates = arguments{3};
    return;
end
if numel(arguments) ~= 2
    error('ea_defaultview_transition:BadInput', ...
        'Expected view and toggle states after an optional figure.');
end

v = arguments{1};
togglestates = arguments{2};
H = findall(0,'type','figure');
resultfig = H(contains({H(:).Name},'Electrode-Scene'));
if isempty(resultfig)
    error('ea_defaultview_transition:MissingElectrodeScene', ...
        'No Electrode-Scene figure is available.');
end
resultfig = resultfig(1); % take the first if there are many.
end
