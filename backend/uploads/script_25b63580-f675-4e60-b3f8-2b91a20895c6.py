import bpy

# Clear all objects from the scene
# Ensure we are in OBJECT mode to be able to select and delete objects
if bpy.context.object and bpy.context.object.mode != 'OBJECT':
    bpy.ops.object.mode_set(mode='OBJECT')
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

# Import the BVH file
input_filepath = '/workspace/input.bvh'
bpy.ops.import_anim.bvh(filepath=input_filepath)

# Find the imported armature object
armature = None
for obj in bpy.context.scene.objects:
    if obj.type == 'ARMATURE':
        armature = obj
        break

if not armature:
    raise Exception("Failed to find an armature in the scene after importing.")

# Select the armature and make it the active object
bpy.context.view_layer.objects.active = armature
armature.select_set(True)

# --- User's modification starts here ---

# To reduce the speed, we scale the animation in time.
# A scale_factor of 2.0 will make the animation twice as long, i.e., half the speed.
scale_factor = 2.0

# Get the action associated with the armature
action = armature.animation_data.action

if action:
    # Iterate over all F-Curves (animation channels) in the action
    for fcurve in action.fcurves:
        # Iterate over all keyframe points in the F-Curve
        for keyframe in fcurve.keyframe_points:
            # Scale the keyframe's time coordinate (x-axis)
            keyframe.co.x *= scale_factor
            # Also scale the handles' time coordinates to maintain the curve's shape
            keyframe.handle_left.x *= scale_factor
            keyframe.handle_right.x *= scale_factor

    # Update the scene's end frame to match the new animation length
    bpy.context.scene.frame_end = int(bpy.context.scene.frame_end * scale_factor)

# --- User's modification ends here ---

# Export the modified armature to a new BVH file
output_filepath = '/workspace/output.bvh'
bpy.ops.export_anim.bvh(
    filepath=output_filepath,
    frame_start=bpy.context.scene.frame_start,
    frame_end=bpy.context.scene.frame_end,
    root_transform_only=False  # Export the entire skeleton's animation
)