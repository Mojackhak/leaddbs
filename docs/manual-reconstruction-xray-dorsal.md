# Manual Reconstruction X-Ray Dorsal Sampling

The manual electrode reconstruction window has an X-Ray mode for the Dorsal View.
In this mode, the view is not a single axial slice through the selected head or
tail marker. Instead, the viewer samples a stack of planes around the marker
along the current electrode axis and averages those samples into one projected
image.

For marker-centered visual inspection, the axial sampling window should be
balanced around the selected marker. A symmetric window reduces directional
bias in the projected bright artifact and makes the projected artifact center
easier to compare with the marker location. This display aid is used only for
visual review in the manual reconstruction UI; it does not change stored
reconstruction coordinates by itself.

The intended X-Ray Dorsal sampling interval is:

```matlab
slicstra = -10:1:10;
```

Use this view to inspect the continuity and approximate centerline of the metal
artifact near the selected marker. For final marker placement, disable X-Ray
mode and confirm the marker on the single-slice Dorsal View together with the
Anterior and Left longitudinal views.
