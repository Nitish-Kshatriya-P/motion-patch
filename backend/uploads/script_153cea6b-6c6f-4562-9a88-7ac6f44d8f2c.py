import bpy

# Clear all objects in the scene to ensure a clean slate.
# We select all objects and then delete the selection.
# A check is added to prevent an error if the scene is already empty.
if bpy.data.objects:
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()

# Import the BVH file from the specified input path.
# The importer will create an armature and load the animation data.
# By default, the scene's frame range is updated to match the animation's length.
bpy.ops.import_anim.bvh(filepath='/workspace/input.bvh')

# The user requested to "Revert the change".
# In the context of a single script execution, this means no modifications
# should be applied to the armature or its animation.
# Therefore, this script will simply load the BVH and then immediately export it.
# This can be useful for re-saving a BVH through Blender's engine, which can
# help standardize or clean up the file format.

# The BVH importer automatically selects the created armature.
# We can rely on this selection for the export step.

# Export the armature to a new BVH file.
# The `export_anim.bvh` operator defaults to `selection_only=True`,
# so it will correctly export only the armature we just imported.
# It also uses the scene's frame range, which was set by the importer.
bpy.ops.export_anim.bvh(filepath='/workspace/output.bvh')