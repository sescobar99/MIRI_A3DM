import bpy
from time import time
from lab_2 import MeshTopology


def main(verbose=None):
    # Get current time
    t = time()

    # Retrieve the active object (the last one selected)
    ob = bpy.context.active_object

    # Check that it is indeed a mesh
    if not ob or ob.type != "MESH":
        print("Active object is not a MESH! Aborting...")
        print(f"(It is a {ob.type})")
        return

    # If we are in edit mode, return to object mode
    bpy.ops.object.mode_set(mode="OBJECT")

    # Retrieve the mesh data
    me: bpy.types.Mesh = ob.data

    # Function that does all the work
    mesh_topology = MeshTopology(me)
    print(f"Startup took: {mesh_topology.startup_time:.3f} s")

    # Exercise7 — genus
    # Using your result in Ex. 6 and the fact that Blender’s model does not include rings, use the
    # Euler formula to compute the genus of the selected object.
    elapsed_t, genus_count = mesh_topology.count_genus(raise_exception=True)
    print(f"Number of genus (took {elapsed_t:.3f} s):\n\t{genus_count} genus/genera")

    # Report performance...
    print(f"Script took: {time() - t:.3f} s")


if __name__ == "__main__":
    main()
