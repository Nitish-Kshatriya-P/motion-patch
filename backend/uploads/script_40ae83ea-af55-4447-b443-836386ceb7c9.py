import bpy

# This factor determines how much to slow down the animation.
# A value of 2.0 will make the animation twice as long (half speed).
# A value of 3.0 will make it three times as long (one-third speed).
slowdown_factor = 2.0

# --- Script Start ---

# Clear all objects from the scene
if bpy.ops.object.mode_set.poll():
    bpy.ops.object.mode_set(mode='OBJECT')
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

# Import the BVH file
bpy.ops.import_anim.bvh(filepath='/workspace/input.bvh')

# Find and select the imported armature
try:
    armature = next(obj for obj in bpy.context.scene.objects if obj.type == 'ARMATURE')
    bpy.context.view_layer.objects.active = armature
    armature.select_set(True)
except StopIteration:
    print("Error: No armature found in the scene after import.")
    armature = None

# Proceed only if an armature was found and it has animation
if armature and armature.animation_data and armature.animation_data.action:
    action = armature.animation_data.action
    
    # Update the scene's end frame to match the new scaled duration
    bpy.context.scene.frame_end = int(bpy.context.scene.frame_end * slowdown_factor)

    # Iterate over all F-curves (animation channels)
    for fcurve in action.fcurves:
        # Iterate over all keyframes in the F-curve
        for keyframe in fcurve.keyframe_points:
            # Scale the frame number (x-coordinate) of the keyframe
            keyframe.co.x *= slowdown_factor
            # Also scale the handles for correct interpolation
            keyframe.handle_left.x *= slowdown_factor
            keyframe.handle_right.x *= slowdown_factor
            
    # Refresh the animation data
    action.update_tag()

# Export the modified animation to a new BVH file
# The exporter will use the scene's start and end frames by default
bpy.ops.export_anim.bvh(
    filepath='/workspace/output.bvh',
    frame_start=bpy.context.scene.frame_start,
    frame_end=bpy.context.scene.frame_end,
    root_transform_only=False
)