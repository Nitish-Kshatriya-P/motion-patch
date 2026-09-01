import bpy

# This script reduces the speed of a BVH animation by scaling its keyframes in time.

# --- Configuration ---
# Set the factor by which to slow down the animation.
# A value of 2.0 will make the animation twice as long (i.e., half the speed).
# A value of 3.0 will make it three times as long (one-third the speed).
slowdown_factor = 2.0

# --- Script ---

# 1. Clear the scene
# Deselect all objects
bpy.ops.object.select_all(action='DESELECT')
# Select all objects in the scene
bpy.ops.object.select_all(action='SELECT')
# Delete all selected objects
bpy.ops.object.delete()

print("Scene cleared.")

# 2. Import the BVH file
try:
    bpy.ops.import_anim.bvh(filepath='/workspace/input.bvh')
    print("Successfully imported /workspace/input.bvh")
except Exception as e:
    print(f"Error importing BVH file: {e}")
    exit()

# 3. Select the imported armature
# Find the armature object in the scene
armature = None
for obj in bpy.context.scene.objects:
    if obj.type == 'ARMATURE':
        armature = obj
        break

if armature is None:
    print("Error: No armature found after importing BVH. Cannot proceed.")
    exit()

# Make the armature the active object and select it
bpy.context.view_layer.objects.active = armature
armature.select_set(True)
print(f"Found and selected armature: {armature.name}")

# 4. Modify the animation speed
if armature.animation_data and armature.animation_data.action:
    action = armature.animation_data.action
    
    print(f"Slowing down animation by a factor of {slowdown_factor}...")
    
    # Iterate over all F-Curves in the action (which control bone transformations)
    for fcurve in action.fcurves:
        # Iterate over all keyframe points in the F-Curve
        for keyframe in fcurve.keyframe_points:
            # Scale the frame number (x-coordinate) of the keyframe
            keyframe.co.x *= slowdown_factor
            # Also scale the handles to maintain the curve's shape relative to the new timing
            keyframe.handle_left.x *= slowdown_factor
            keyframe.handle_right.x *= slowdown_factor
        
        # Update the F-Curve to apply the changes
        fcurve.update()

    # After scaling, the animation is longer. Update the scene's end frame.
    # action.frame_range is automatically updated when keyframes are moved.
    original_end_frame = bpy.context.scene.frame_end
    new_end_frame = int(action.frame_range[1])
    bpy.context.scene.frame_end = new_end_frame
    
    print(f"Animation speed reduced. Original end frame: {original_end_frame}, New end frame: {new_end_frame}")

else:
    print("Warning: Armature has no animation data to modify.")

# 5. Export the modified BVH
# The exporter uses the scene's start and end frames by default.
try:
    bpy.ops.export_anim.bvh(
        filepath='/workspace/output.bvh',
        check_existing=False,
        frame_start=bpy.context.scene.frame_start,
        frame_end=bpy.context.scene.frame_end
    )
    print(f"Successfully exported modified BVH to /workspace/output.bvh")
except Exception as e:
    print(f"Error exporting BVH file: {e}")
    exit()