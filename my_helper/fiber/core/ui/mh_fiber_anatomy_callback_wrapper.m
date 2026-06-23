function mh_fiber_anatomy_callback_wrapper(src, eventData, originalCallback, resultfig)
% Run a Lead-DBS Anatomy Slices callback, then relock helper-scene slice planes.

controlFig = ancestor(src, 'figure');
if ~isempty(controlFig) && isgraphics(controlFig)
    set(0, 'CurrentFigure', controlFig);
end

cleanup = onCleanup(@() relock_slices(resultfig, controlFig));
invoke_callback(originalCallback, src, eventData);
end

function invoke_callback(callbackSpec, src, eventData)
if isempty(callbackSpec)
    return;
end

if isa(callbackSpec, 'function_handle')
    feval(callbackSpec, src, eventData);
elseif iscell(callbackSpec)
    if isempty(callbackSpec)
        return;
    end
    feval(callbackSpec{1}, src, eventData, callbackSpec{2:end});
elseif ischar(callbackSpec) || isstring(callbackSpec)
    evalin('base', char(callbackSpec));
else
    error('mh_fiber_anatomy_callback_wrapper:UnsupportedCallback', ...
        'Unsupported callback type: %s', class(callbackSpec));
end
end

function relock_slices(resultfig, controlFig)
try
    if nargin < 2 || isempty(controlFig) || ~isgraphics(controlFig)
        controlFig = [];
    end
    mh_fiber_lock_anatomy_slices(resultfig, controlFig);
catch ME
    warning('mh_fiber_anatomy_callback_wrapper:RelockFailed', ...
        'Could not relock Anatomy Slices after callback: %s', ME.message);
end
end
