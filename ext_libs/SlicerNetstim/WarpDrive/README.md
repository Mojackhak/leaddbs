# WarpDrive UI overview

Here we provide a general overview of the WarpDrive user interface and the tools functionality. WarpDrive is built as a module is [3D Slicer (Slicer)](https://www.slicer.org/), and we therefore recommend a certain familiarity with the Slicer application, which can be gained with its [documentation](https://slicer.readthedocs.io/en/latest/). WarpDrive can also be run from [Lead-DBS](https://www.lead-dbs.org/), which hides some of the Slicer UI that is not specific for WarpDrive, facilitating navigation in the application.

![](Screenshots/WD_aux_1_edit.png?raw=true)

## I / O panel
This panel is used to set up the inputs and outputs for WarpDrive. When launched from Lead-DBS, this panel is automatically populated and hidden to the user, enabling the user to start the refinements.
-	Input: this selector sets the warpfield that will be used for refinements. In Slicer, this transform is being applied to the subject image. It is also possible to set an image as an input and transform it directly.
-	Source and target fiducials: the nodes selected here will be populated by the fiducials set during the refinements.
-	Output displacement field: this selector sets the output transform that will be generated.

## Lead-DBS launch data

When WarpDrive is launched from Lead-DBS, `ea_runwarpdrive.m` passes a `LeadSubjects` JSON array to the module. Each subject entry contains an `anat_files` object whose keys become the entries in the toolbar `Modality` menu. The toolbar reads `currentSubject["anat_files"].keys()` to populate the menu and loads `currentSubject["anat_files"][modality]` when the user switches modality.

Lead-DBS keeps preoperative modality keys unchanged for compatibility, adds postoperative coregistered images with a `postop_` prefix, and only passes image paths that exist on disk. For postoperative CT, the raw coregistered `CT` image is passed as `postop_CT`; tone-mapped CT is not used as the default postoperative CT modality. The subject entry also carries `native_reference_file`, which is the preoperative anchor image used as the native reference when hardening WarpDrive changes, independent of the currently displayed modality.

## Output

This panel sets parameters used to compute the output displacement field.
-	Spacing: the grid spacing of the output transform. If the same as input checkbox is checked, the same spacing as the input transform/image is set.
-	Stiffness: this is a regularization parameter used for the computation of the output transform. Higher values apply higher regularization.

## Tools

This is the main section of the module, where the user can select tools used to refine the input warpfield. The following figure illustrates the steps for the point to point tool, the following text describes the tools more in detail.

![](Screenshots/WD_aux_1_p2steps.png?raw=true)

-	Point to point: after selecting the point to point tool (1), the user places first source point (2) and then the target point (3) to which it corresponds. To compute new transform the user should click on calculate. If the Auto update checkbox is checked, then the output will be calculated after every correction made.
-	Draw: Drawing works in a similar way, where the user first draws source points which will be matched to the closest structures outlines. These structures outlines can come from atlases, or any model node. It is also possible to manually draw the target drawing by clicking and pressing the Draw button and selecting the respective mode. Drawings become a set of points sampled across the drawing for them to be fed into the output computation algorithm.
-	Smudge: Smudging works by click-and-dragging the image. This computes a temporary transform that follows the cursor movements. Source points are sampled along the trajectory where the mouse moved and target points are obtained by transforming the source points with the temporary transform. They are then used to compute the output transform.
-	Radius: The radius specifies the spread that the correction will have.

## Corrections  

In the corrections panel appear all the corrections that are being made by using the tools.

![](Screenshots/WD_aux_3.png?raw=true)

It is possible to delete, rename, change radius, and include/exclude corrections from the computation of the output. The Undo button will delete the last correction and the Source and Target visibility options will change the visibility of source and target points. When selecting a correction with the preview selected correction checkbox checked, the slices will be moved to the respective slice and an arrow will preview the correction.
Finally, it is also possible to add fix points. These points indicate points that shouldn’t move in the new output transform.

## Atlases

The atlases tab is for Lead-DBS users to load atlas structures of interest included in Lead-DBS into WarpDrive.
