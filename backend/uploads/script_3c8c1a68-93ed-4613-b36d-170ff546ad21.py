import bpy

# Define the scale factor for the animation speed.
# A value of 2.0 will make the animation twice as long (half the speed).
# A value of 0.5 will make it half as long (twice the speed).
speed_scale_factor = 2.0

# --- Clear the scene ---
# Ensure we are in OBJECT mode to select and delete objects
if bpy.context.object and bpy.context.object.mode != 'OBJECT':
    bpy.ops.object.mode_set(mode='OBJECT')
# Select all objects in the scene
bpy.ops.object.select_all(action='SELECT')
# Delete all selected objects
bpy.ops.object.delete()

# --- Import the BVH file ---
input_filepath = '/workspace/input.bvh'
bpy.ops.import_anim.bvh(filepath=input_filepath)

# --- Select the imported armature ---
# After clearing the scene and importing, the armature will be the first object
try:
    armature = bpy.data.objects[0]
    bpy.context.view_layer.objects.active = armature
    armature.select_set(True)
except IndexError:
    print("Error: No object found after importing BVH. Exiting.")
    exit()

# --- Modify the animation speed ---
if armature.animation_data and armature.animation_data.action:
    action = armature.animation_data.action

    # Iterate over all the F-curves in the action
    for fcurve in action.fcurves:
        # Iterate over all the keyframe points in the F-curve
        for keyframe in fcurve.keyframe_points:
            # Scale the frame (time) of the keyframe
            keyframe.co.x *= speed_scale_factor
            # Also scale the handles for correct interpolation
            keyframe.handle_left.x *= speed_scale_factor
            keyframe.handle_right.x *= speed_scale_factor
        
        # Update the F-curve to apply the changes
        fcurve.update()

    # Adjust the scene's end frame to encompass the new animation length.
    # The BVH exporter uses the scene's frame range by default.
    original_end_frame = bpy.context.scene.frame_end
    bpy.context.scene.frame_end = int(original_end_frame * speed_scale_factor)
else:
    print("Warning: Armature has no animation data to modify.")

# --- Export the modified BVH file ---
output_filepath = '/workspace/output.bvh'
# Ensure the active object is selected for export
bpy.ops.export_anim.bvh(
    filepath=output_filepath,
    frame_start=bpy.context.scene.frame_start,
    frame_end=bpy.context.scene.frame_end,
    root_transform_only=False
)

print(f"Successfully processed {input_filepath} and saved to {output_filepath}")
print(f"Animation speed reduced by a factor of {1/speed_scale_factor}. New length: {bpy.context.scene.frame_end} frames.")