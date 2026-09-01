import bpy

# This script reduces the speed of a BVH animation by scaling its keyframes over time.

# --- Configuration ---
# Set the factor by which to scale the animation time.
# A value of 2.0 will make the animation twice as long (half the speed).
# A value of 0.5 will make the animation half as long (twice the speed).
time_scale_factor = 2.0

# --- Script Start ---

# 1. Clear all objects from the scene
# This ensures a clean environment for the import
if bpy.context.object and bpy.context.object.mode != 'OBJECT':
    bpy.ops.object.mode_set(mode='OBJECT')
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

# 2. Import the BVH file
input_filepath = '/workspace/input.bvh'
bpy.ops.import_anim.bvh(filepath=input_filepath)

# 3. Get the imported armature
# The imported object is typically the only one in the scene and is selected.
try:
    armature = bpy.context.view_layer.objects.active
    if not armature or armature.type != 'ARMATURE':
        # Fallback to find the first armature in the scene if the active object is not it
        for obj in bpy.data.objects:
            if obj.type == 'ARMATURE':
                armature = obj
                break
    if not armature:
        raise RuntimeError("No armature object found in the scene after import.")
except (RuntimeError, IndexError):
    print(f"Error: Could not find the imported armature from {input_filepath}.")
    # Exit the script if no armature is found
    # In a headless script, this will cause an error and stop execution, which is desired.

# Ensure the armature is selected and active
bpy.context.view_layer.objects.active = armature
armature.select_set(True)

# 4. Modify the animation speed
if armature.animation_data and armature.animation_data.action:
    action = armature.animation_data.action

    # Iterate through all the F-Curves (animation channels for bones)
    for fcurve in action.fcurves:
        # For each F-Curve, iterate through all its keyframes
        for keyframe in fcurve.keyframe_points:
            # Scale the keyframe's time (X-coordinate) by the scale factor
            keyframe.co.x *= time_scale_factor
            # Also scale the handles' time to maintain the curve's shape
            keyframe.handle_left.x *= time_scale_factor
            keyframe.handle_right.x *= time_scale_factor
        
        # Update the F-Curve to apply the changes
        fcurve.update()

    # Update the scene's end frame to match the new, longer animation
    # We can calculate this by scaling the original frame range
    new_frame_range = action.frame_range
    bpy.context.scene.frame_end = int(new_frame_range[1])
    
    print(f"Animation scaled by a factor of {time_scale_factor}.")
    print(f"New animation end frame: {bpy.context.scene.frame_end}")

else:
    print("Warning: No animation data found on the armature to modify.")

# 5. Export the modified armature to a new BVH file
output_filepath = '/workspace/output.bvh'
bpy.ops.export_anim.bvh(
    filepath=output_filepath,
    frame_start=int(bpy.context.scene.frame_start),
    frame_end=int(bpy.context.scene.frame_end),
    root_transform_only=False  # Export all bones
)

print(f"Successfully exported modified BVH to {output_filepath}")