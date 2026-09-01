import bpy

# --- Clear the Scene ---
# Make sure we are in Object Mode
if bpy.context.object and bpy.context.object.mode != 'OBJECT':
    bpy.ops.object.mode_set(mode='OBJECT')

# Select all objects in the scene
bpy.ops.object.select_all(action='SELECT')
# Delete all selected objects
bpy.ops.object.delete()

# --- Import the BVH file ---
input_filepath = '/workspace/input.bvh'
bpy.ops.import_anim.bvh(filepath=input_filepath)

# --- Select the Imported Armature ---
armature = None
for obj in bpy.context.scene.objects:
    if obj.type == 'ARMATURE':
        armature = obj
        break

if armature is None:
    print("Error: No armature found after importing BVH. Aborting.")
else:
    # Set the armature as the active object and select it
    bpy.context.view_layer.objects.active = armature
    armature.select_set(True)

    # --- Modify the Animation: Reduce Speed ---
    # A scale factor of 2.0 will make the animation twice as long,
    # effectively running at half speed.
    scale_factor = 2.0

    # Ensure the armature has animation data
    if armature.animation_data and armature.animation_data.action:
        action = armature.animation_data.action

        # Store the original end frame before scaling
        original_end_frame = bpy.context.scene.frame_end

        # Scale all keyframe points in all F-curves
        for fcurve in action.fcurves:
            for keyframe in fcurve.keyframe_points:
                # Scale the frame number (the 'x' coordinate of the keyframe)
                keyframe.co.x *= scale_factor
                # Also scale the handles to maintain the curve's shape
                keyframe.handle_left.x *= scale_factor
                keyframe.handle_right.x *= scale_factor
        
        # Update the fcurves to reflect the changes
        action.fcurves.update()

        # Update the scene's end frame to encompass the new animation length
        new_end_frame = original_end_frame * scale_factor
        bpy.context.scene.frame_end = int(new_end_frame)
        
        print(f"Animation speed reduced by a factor of {scale_factor}.")
        print(f"New animation length: {bpy.context.scene.frame_end} frames.")

        # --- Export the Modified BVH ---
        output_filepath = '/workspace/output.bvh'
        
        # Export the selected armature's animation
        # The operator will use the scene's start and end frames by default
        bpy.ops.export_anim.bvh(
            filepath=output_filepath,
            check_existing=False,
            filter_glob="*.bvh",
            root_transform_only=False
        )
        
        print(f"Successfully exported modified BVH to {output_filepath}")

    else:
        print("Error: The imported armature has no animation data to modify.")