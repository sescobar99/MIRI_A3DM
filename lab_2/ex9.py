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

    # Exercise9 — Total volume
    # Write a function to compute (and to print) the total volume of the selected object. Different
    # connected components should be added, but shells that do not form a 2-manifold without
    # boundary may be ignored (what would be their volume. . . )
    elapsed_t, total_volume = mesh_topology.calculate_volume()
    print(f"Surface volume (took {elapsed_t:.3f} s):\n\t{total_volume:.3f}")

    # Report performance...
    print(f"Script took: {time() - t:.3f} s")


if __name__ == "__main__":
    main()
