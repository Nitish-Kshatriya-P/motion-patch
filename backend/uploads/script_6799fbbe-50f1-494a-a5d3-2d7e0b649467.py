import bpy

# This script reduces the speed of a BVH animation by stretching its keyframes.
# A scale_factor of 2.0 makes the animation twice as long (half speed).
scale_factor = 2.0

# --- SCRIPT START ---

# 1. Clear the scene of all objects
# This ensures we start with a clean slate before importing the BVH.
if bpy.ops.object.mode_set.poll():
    bpy.ops.object.mode_set(mode='OBJECT')
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

# 2. Import the BVH file
input_filepath = '/workspace/input.bvh'
bpy.ops.import_anim.bvh(filepath=input_filepath, filter_glob="*.bvh", global_scale=1.0, use_fps_scale=False, update_scene_fps=False, update_scene_duration=True)

# 3. Select the imported armature
# The BVH importer automatically selects the created armature.
try:
    armature = bpy.context.view_layer.objects.active
    if not armature or armature.type != 'ARMATURE':
        raise RuntimeError("No armature found after import. The BVH file might be empty or invalid.")
except (RuntimeError, IndexError):
    print("Error: Could not find the imported armature. Aborting.")
    # In case of an error, exit Blender.
    bpy.ops.wm.quit_blender()

# 4. Scale the animation keyframes to change the speed
if armature.animation_data and armature.animation_data.action:
    action = armature.animation_data.action
    
    # Find the first frame of the animation to use as a pivot for scaling
    # This ensures the animation scales from its beginning.
    pivot_frame = action.frame_range[0]

    # Iterate over all F-curves (animation data for each bone's location, rotation, etc.)
    for fcurve in action.fcurves:
        # For each keyframe point in the curve...
        for keyframe in fcurve.keyframe_points:
            # Scale its frame number (the 'x' coordinate) relative to the pivot
            original_frame = keyframe.co.x
            new_frame = pivot_frame + (original_frame - pivot_frame) * scale_factor
            keyframe.co.x = new_frame
            
            # Also scale the handles for bezier interpolated curves to maintain the curve's shape
            original_handle_left = keyframe.handle_left.x
            new_handle_left = pivot_frame + (original_handle_left - pivot_frame) * scale_factor
            keyframe.handle_left.x = new_handle_left
            
            original_handle_right = keyframe.handle_right.x
            new_handle_right = pivot_frame + (original_handle_right - pivot_frame) * scale_factor
            keyframe.handle_right.x = new_handle_right
            
    # After scaling all keyframes, update the action's overall frame range
    action.frame_range = (action.frame_range[0], action.frame_range[0] + (action.frame_range[1] - action.frame_range[0]) * scale_factor)
    
    # Update the scene's end frame to ensure the entire scaled animation is included in the export
    bpy.context.scene.frame_end = int(action.frame_range[1])
    
else:
    print("Warning: The imported armature has no animation data to modify.")

# 5. Export the modified animation to a new BVH file
output_filepath = '/workspace/output.bvh'
bpy.ops.export_anim.bvh(
    filepath=output_filepath,
    frame_start=int(bpy.context.scene.frame_start),
    frame_end=int(bpy.context.scene.frame_end),
    root_transform_only=False  # Export transformations for all bones
)

print(f"Animation speed reduced and saved to {output_filepath}")