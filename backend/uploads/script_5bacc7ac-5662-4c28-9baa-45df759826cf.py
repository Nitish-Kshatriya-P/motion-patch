import bpy

# Define a scale factor. 2.0 makes the animation twice as long (half speed).
# 0.5 would make it twice as fast.
SPEED_SCALE_FACTOR = 2.0

# --- 1. Clear the scene ---
# Ensure we are in Object mode
if bpy.ops.object.mode_set.poll():
    bpy.ops.object.mode_set(mode='OBJECT')
# Select all objects
bpy.ops.object.select_all(action='SELECT')
# Delete selected objects
bpy.ops.object.delete()

# --- 2. Import the BVH file ---
input_filepath = '/workspace/input.bvh'
bpy.ops.import_anim.bvh(filepath=input_filepath)

# --- 3. Find and select the imported armature ---
armature = None
for obj in bpy.context.scene.objects:
    if obj.type == 'ARMATURE':
        armature = obj
        break

if not armature:
    raise RuntimeError("BVH import failed: No armature object found in the scene.")

# Set the armature as the active object and select it
bpy.context.view_layer.objects.active = armature
armature.select_set(True)

# --- 4. Modify the animation speed ---
action = armature.animation_data.action

if not action:
    print("Warning: Armature has no animation data to modify.")
else:
    # Store the original end frame before scaling
    original_end_frame = action.frame_range[1]

    # Scale all keyframe X coordinates (time) and their handles
    for fcurve in action.fcurves:
        for keyframe in fcurve.keyframe_points:
            keyframe.co.x *= SPEED_SCALE_FACTOR
            keyframe.handle_left.x *= SPEED_SCALE_FACTOR
            keyframe.handle_right.x *= SPEED_SCALE_FACTOR

    # Update the action's frame range to reflect the new duration
    action.frame_range = (action.frame_range[0], original_end_frame * SPEED_SCALE_FACTOR)

    # Update the scene's frame range to match the new animation length
    bpy.context.scene.frame_start = int(action.frame_range[0])
    bpy.context.scene.frame_end = int(action.frame_range[1])

# --- 5. Export the modified BVH file ---
output_filepath = '/workspace/output.bvh'

# The BVH exporter uses the scene's frame range, which we've already updated.
# We also ensure only the selected armature is exported.
bpy.ops.export_anim.bvh(
    filepath=output_filepath,
    frame_start=bpy.context.scene.frame_start,
    frame_end=bpy.context.scene.frame_end,
    use_selection=True,
    root_transform_only=False
)