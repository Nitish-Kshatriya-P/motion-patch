import bpy
import math

# --- Configuration ---
input_filepath = '/workspace/input.bvh'
output_filepath = '/workspace/output.bvh'

# Speed factor:
# > 1.0 to slow down (e.g., 2.0 makes it twice as long, i.e., half speed)
# < 1.0 to speed up (e.g., 0.5 makes it half as long, i.e., double speed)
speed_scale_factor = 2.0

# --- Script ---

# 1. Clear the scene
# Ensure we are in Object mode
if bpy.ops.object.mode_set.poll():
    bpy.ops.object.mode_set(mode='OBJECT')
# Select all objects
bpy.ops.object.select_all(action='SELECT')
# Delete selected objects
bpy.ops.object.delete()

# 2. Import the BVH file
bpy.ops.import_anim.bvh(filepath=input_filepath)

# 3. Select the imported armature
armature = None
for obj in bpy.context.scene.objects:
    if obj.type == 'ARMATURE':
        armature = obj
        break

if not armature:
    raise Exception("No armature found in the scene after importing BVH.")

bpy.context.view_layer.objects.active = armature
armature.select_set(True)

# 4. Perform modifications: Reduce speed by scaling keyframes
action = armature.animation_data.action

if action:
    new_last_frame = 0
    
    # Iterate over all F-curves in the action
    for fcurve in action.fcurves:
        # Iterate over all keyframe points in the F-curve
        for keyframe in fcurve.keyframe_points:
            # Scale the frame (time) of the keyframe
            keyframe.co.x *= speed_scale_factor
            # Also scale the handles to maintain curve shape
            keyframe.handle_left.x *= speed_scale_factor
            keyframe.handle_right.x *= speed_scale_factor
            
            # Keep track of the new maximum frame number
            if keyframe.co.x > new_last_frame:
                new_last_frame = keyframe.co.x
    
    # Update the scene's end frame to match the new animation length
    bpy.context.scene.frame_end = math.ceil(new_last_frame)
else:
    print("Warning: Armature has no animation data to modify.")

# 5. Export the modified armature to a new BVH file
# The exporter will use the scene's frame range by default.
bpy.ops.export_anim.bvh(
    filepath=output_filepath,
    check_existing=False,
    frame_start=bpy.context.scene.frame_start,
    frame_end=bpy.context.scene.frame_end
)

print(f"BVH modification complete. Output saved to {output_filepath}")