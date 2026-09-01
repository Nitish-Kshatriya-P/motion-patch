import bpy
import sys

# --- Clean the scene ---
# Make sure we are in Object Mode
if bpy.context.active_object and bpy.context.active_object.mode != 'OBJECT':
    bpy.ops.object.mode_set(mode='OBJECT')

# Select all objects in the scene
bpy.ops.object.select_all(action='SELECT')
# Delete all selected objects
bpy.ops.object.delete()

# --- Import the BVH file ---
input_filepath = '/workspace/input.bvh'
bpy.ops.import_anim.bvh(filepath=input_filepath)

# --- Select the imported armature ---
# Find the armature object in the scene
try:
    armature = next(obj for obj in bpy.context.scene.objects if obj.type == 'ARMATURE')
except StopIteration:
    print("Error: No armature found after importing BVH. Exiting.", file=sys.stderr)
    bpy.ops.wm.quit_blender()

# Set the armature as the active object and select it
bpy.context.view_layer.objects.active = armature
armature.select_set(True)

# --- Modify the animation speed ---
# A scale factor > 1.0 slows down the animation (makes it longer).
# A scale factor < 1.0 speeds up the animation (makes it shorter).
# We will use 2.0 to make the animation twice as long (half the speed).
scale_factor = 2.0

if armature.animation_data and armature.animation_data.action:
    action = armature.animation_data.action

    # Store the original frame range before modification
    original_start_frame = action.frame_range[0]
    original_end_frame = action.frame_range[1]

    # Iterate over all F-Curves (animation channels) in the action
    for fcurve in action.fcurves:
        # Iterate over all keyframe points in the F-Curve
        for keyframe in fcurve.keyframe_points:
            # Scale the frame number (the x-coordinate of the keyframe)
            keyframe.co.x *= scale_factor
            # Also scale the handles to maintain the curve's shape relative to time
            keyframe.handle_left.x *= scale_factor
            keyframe.handle_right.x *= scale_factor
            
    # Update the action's frame range to reflect the new duration
    action.frame_range[0] = original_start_frame * scale_factor
    action.frame_range[1] = original_end_frame * scale_factor

    # Update the scene's frame range to match the new animation length
    # This is crucial for the export operator to use the correct range
    bpy.context.scene.frame_start = int(action.frame_range[0])
    bpy.context.scene.frame_end = int(action.frame_range[1])
    
    print(f"Animation scaled by a factor of {scale_factor}.")
    print(f"New frame range: {bpy.context.scene.frame_start} to {bpy.context.scene.frame_end}")

else:
    print("Warning: Armature has no animation data to modify.", file=sys.stderr)

# --- Export the modified BVH file ---
output_filepath = '/workspace/output.bvh'

# Export the animation, ensuring the full new frame range is included
bpy.ops.export_anim.bvh(
    filepath=output_filepath,
    frame_start=bpy.context.scene.frame_start,
    frame_end=bpy.context.scene.frame_end,
    root_transform_only=False # Export animation for all bones
)

print(f"Successfully exported modified BVH to {output_filepath}")