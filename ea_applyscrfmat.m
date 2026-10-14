function scrf=ea_applyscrfmat(mat,native,sides,scrf)

if nargin < 4
    scrf=native;
end

for side = sides
    % coords
    scrf.coords_mm{side}=mat*[native.coords_mm{side},ones(size(native.coords_mm{side},1),1)]';
    scrf.coords_mm{side}=scrf.coords_mm{side}(1:3,:)';
    
    % trajec
    scrf.trajectory{side}=mat*[native.trajectory{side},ones(size(native.trajectory{side},1),1)]';
    scrf.trajectory{side}=scrf.trajectory{side}(1:3,:)';
    
    % markers
    scrf.markers(side).head=mat*[native.markers(side).head,1]';
    scrf.markers(side).head=scrf.markers(side).head(1:3)';
    
    scrf.markers(side).tail=mat*[native.markers(side).tail,1]';
    scrf.markers(side).tail=scrf.markers(side).tail(1:3)';
    
    scrf.markers(side).x=mat*[native.markers(side).x,1]';
    scrf.markers(side).x=scrf.markers(side).x(1:3)';
    
    scrf.markers(side).y=mat*[native.markers(side).y,1]';
    scrf.markers(side).y=scrf.markers(side).y(1:3)';
end
