import bpy

# This script reduces the speed of a BVH animation to half its original speed.
# It does this by scaling the time of all keyframes by a factor of 2.

# --- SCRIPT START ---

# Define the file paths
input_file = '/workspace/input.bvh'
output_file = '/workspace/output.bvh'

# Define the scaling factor for time.
# A factor of 2.0 makes the animation twice as long, i.e., half the speed.
time_scale_factor = 2.0

# 1. Clean the scene by deleting all existing objects
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

# 2. Import the BVH file
# The 'update_scene_duration' option is set to True by default,
# which correctly sets the scene's frame_end.
bpy.ops.import_anim.bvh(filepath=input_file)

# 3. Get the imported armature object
# After import, the armature is the active object in the context.
armature = bpy.context.active_object

# Check if an armature was successfully imported and selected
if armature and armature.type == 'ARMATURE':
    # Ensure the armature has animation data
    if armature.animation_data and armature.animation_data.action:
        action = armature.animation_data.action

        # 4. Modify the animation speed by scaling keyframes
        # Iterate over all F-Curves (animation channels for properties like location, rotation)
        for fcurve in action.fcurves:
            # Iterate over all keyframe points in the F-Curve
            for keyframe in fcurve.keyframe_points:
                # Scale the frame number (the 'x' coordinate of the keyframe)
                keyframe.co.x *= time_scale_factor
                # Also scale the handles for correct interpolation curve shape
                keyframe.handle_left.x *= time_scale_factor
                keyframe.handle_right.x *= time_scale_factor

        # Update the scene's end frame to match the new animation length.
        # This is crucial for the exporter to know the new duration.
        bpy.context.scene.frame_end = int(bpy.context.scene.frame_end * time_scale_factor)

# 5. Export the modified animation to a new BVH file
# The operator will use the scene's start and end frames by default.
bpy.ops.export_anim.bvh(
    filepath=output_file,
    frame_start=bpy.context.scene.frame_start,
    frame_end=bpy.context.scene.frame_end
)