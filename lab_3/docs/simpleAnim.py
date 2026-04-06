import bpy


# List of actions blender will do before doing the fram painting function
#Everithjin we append here is going to be executred before the frame is visualized

def frame_change_pre(scene):
    # A triangle that shifts in the z direction
    zshift = scene.frame_current * 0.02
    
    vertices = [(-1, -1, zshift), (1, -1, zshift), (0, 1, zshift)]
    triangles = [(0, 1, 2)]
    object = bpy.data.objects["Example"]
    object.data.clear_geometry()
    object.data.from_pydata(vertices, [], triangles)
    
    
me = bpy.data.meshes.new('ExampleMesh')
ob = bpy.data.objects.new('Example', me)
bpy.context.scene.collection.objects.link(ob)
    
bpy.app.handlers.frame_change_pre.append(frame_change_pre)


# When we want to do some long computation we are interested on 
# not letting blender anything apart from what it is doingç
# This basically locks/frees interaction wiht blender

def playback_start(scene):
    scene.render.use_lock_interface = True
    
def playback_end(scene):
    scene.render.use_lock_interface = False
    
bpy.app.handlers.animation_playback_pre.append(playback_start)
bpy.app.handlers.animation_playback_post.append(playback_end)
