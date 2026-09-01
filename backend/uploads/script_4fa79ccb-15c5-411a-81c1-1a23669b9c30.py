import bpy

# --- SCRIPT START ---

# Define the scale factor for time.
# A factor of 2.0 will make the animation twice as long (half speed).
# A factor of 0.5 will make the animation half as long (double speed).
time_scale_factor = 2.0

# Clean the scene
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

# Import the BVH file
bpy.ops.import_anim.bvh(filepath='/workspace/input.bvh')

# Find the imported armature object
armature_obj = None
for obj in bpy.context.scene.objects:
    if obj.type == 'ARMATURE':
        armature_obj = obj
        break

if armature_obj is None:
    raise RuntimeError("No armature found in the scene after BVH import.")

# Ensure the armature is the active object
bpy.context.view_layer.objects.active = armature_obj
armature_obj.select_set(True)

# Access the animation data (Action)
action = armature_obj.animation_data.action

if action:
    # Iterate through all F-Curves in the action
    for fcurve in action.fcurves:
        # Iterate through all keyframe points in the F-Curve
        for keyframe in fcurve.keyframe_points:
            # Scale the frame (x-coordinate) of the keyframe and its handles
            keyframe.co.x *= time_scale_factor
            keyframe.handle_left.x *= time_scale_factor
            keyframe.handle_right.x *= time_scale_factor

    # Update the scene's end frame to match the new animation length
    bpy.context.scene.frame_end = int(bpy.context.scene.frame_end * time_scale_factor)

# Export the modified animation to a new BVH file
# The exporter will use the current scene's frame range
bpy.ops.export_anim.bvh(
    filepath='/workspace/output.bvh',
    check_existing=False,
    root_transform_only=False
)

# --- SCRIPT END ---