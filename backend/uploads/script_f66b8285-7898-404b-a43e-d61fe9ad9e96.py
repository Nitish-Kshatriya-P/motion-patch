import bpy

# This script reduces the speed of a BVH animation by scaling the keyframes.

# --- Configuration ---
# The factor by which to scale the animation time.
# A value of 2.0 makes the animation twice as long (half speed).
# A value of 0.5 makes the animation half as long (double speed).
speed_scale_factor = 2.0

# --- Script ---

# 1. Clear the scene
# Ensure we are in Object mode
if bpy.ops.object.mode_set.poll():
    bpy.ops.object.mode_set(mode='OBJECT')
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

# 2. Import the BVH file
bpy.ops.import_anim.bvh(filepath='/workspace/input.bvh')

# 3. Select the imported armature
armature = None
for obj in bpy.context.scene.objects:
    if obj.type == 'ARMATURE':
        armature = obj
        break

if not armature:
    raise Exception("No armature found after importing BVH file.")

# Set the armature as the active object
bpy.context.view_layer.objects.active = armature
armature.select_set(True)

# 4. Perform the modification: Reduce animation speed
if armature.animation_data and armature.animation_data.action:
    action = armature.animation_data.action

    # Scale all keyframe X coordinates (frame numbers)
    for fcurve in action.fcurves:
        for keyframe in fcurve.keyframe_points:
            keyframe.co.x *= speed_scale_factor
            keyframe.handle_left.x *= speed_scale_factor
            keyframe.handle_right.x *= speed_scale_factor

    # Update the scene's end frame to match the new animation length
    bpy.context.scene.frame_end = int(bpy.context.scene.frame_end * speed_scale_factor)
else:
    print("Warning: No animation data found on the armature to modify.")

# 5. Export the modified BVH
# The export operator uses the selected object and the scene's frame range.
bpy.ops.export_anim.bvh(
    filepath='/workspace/output.bvh',
    check_existing=False,
    frame_start=bpy.context.scene.frame_start,
    frame_end=bpy.context.scene.frame_end,
    root_transform_only=False
)

print("BVH modification complete. Animation speed reduced.")