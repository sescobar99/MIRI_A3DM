import bpy
import bmesh

from mathutils import Vector
from time import time
from utils import print_vector

# from utils import UnionFind


# https://www.youtube.com/watch?v=mfp1Z1mBClc
# https://www.youtube.com/watch?v=kC8jbGSiuIQ


class MeshTopology:
    def __init__(
        self,
        me: bpy.types.Mesh,
    ):
        # Create a Bmesh instance from regular mesh
        self.me = me
        self.bm = bmesh.new()  # create an empty BMesh
        self.bm.from_mesh(me)  # fill it in from a Mesh

    def clean_up(self):
        # Finish up, write the bmesh back to the mesh
        self.bm.to_mesh(self.me)
        # Free and prevent further access
        self.bm.free()

        # Apparently Blender follows a "don't update unless told" policy for the
        # viewport to save processing power. We need to do it explicitly
        self.me.update()

    def simple_subdivision(self):
        """
        Function that modifies the mesh associated to the active object performing
        one step of topological subdivision of the mesh (as defined by Catmull-Clark),
        but without perturbing the positions.

        https://en.wikipedia.org/wiki/Catmull%E2%80%93Clark_subdivision_surface

        New vertices will be at the barycenter of each face and at the midpoint of
        each edge. (What blender calls “Simple” subdivision).

        The input mesh may contain faces of any arity.
        The result should be made of quads only. ()
        The original mesh is assumed to be 2-manifold without boundary

        The modified Bmesh keeps the original faces in order to ease other exercises
        """
        t = time()
        # Useful for catmull clark stuff
        original_points = {vert: len(vert.link_edges) for vert in list(self.bm.verts)}

        # 1. For each face, add a face point (use barycenter of original points)
        # print("Faces")
        new_face_points: dict[bmesh.types.BMFace, bmesh.types.BMVert] = {}
        for face in self.bm.faces:
            center_placeholder = Vector((0, 0, 0))
            vert_count = len(face.verts)
            for vert in face.verts:
                center_placeholder += vert.co
            center = center_placeholder / vert_count
            # print_vector("Center:", center)
            # Create new geometry and save it in a F:{V}  way
            new_face_points[face] = self.bm.verts.new(center)
            # print("----------------------------")

        # 2. For each edge, add an edge point (use midpoint of original points)
        # print("Edges")
        new_edge_points: dict[bmesh.types.BMEdge, bmesh.types.BMVert] = {}
        for edge in self.bm.edges:
            center_placeholder = Vector((0, 0, 0))
            for vert in edge.verts:
                center_placeholder += vert.co
            # Number of vertices for an edge should be 2
            center = center_placeholder / 2
            # print_vector("Center:", center)
            # Create new geometry and save it in a E:{V} way (kind of)
            new_edge_points[edge] = self.bm.verts.new(center)
            # print("----------------------------")

        # 3. Connect each new face point to the new edge points of all original
        # edges defining the original face

        # The  quads are ensured by creating a new face for every loop (corner)
        # of the original topology.
        # The points used are (p_o, mp_ne, p_f, and mp_pe)
        # p_o: original vertex
        # mp_ne: new vertex created in the midpoint wrt the next edge
        # p_f: new vertex created in the barycenter of the face
        # mp_pe:new vertex created in the midpoint wrt the previous edge

        # This avoids iterating over the list we need to update
        original_faces = list(self.bm.faces)

        new_faces = []
        for face in original_faces:
            p_f = new_face_points[face]
            for loop in face.loops:
                p_o = loop.vert
                mp_ne = new_edge_points[loop.edge]
                # p_f = new_face_points[face]
                mp_pe = new_edge_points[loop.link_loop_prev.edge]

                # Create new face (order matters!)
                new_face = self.bm.faces.new((p_o, mp_ne, p_f, mp_pe))
                new_faces.append(new_face)

        # for loop in self.bm.loops:
        #     print(loop)

        return time() - t, new_face_points, new_edge_points, original_points

    def move_points(
        self,
        new_face_points: dict[bmesh.types.BMFace, bmesh.types.BMVert],
        new_edge_points: dict[bmesh.types.BMEdge, bmesh.types.BMVert],
        original_points: dict[bmesh.types.BMVert, int],
    ):
        """
        Catmull-Clark subdivision
        Function that applies one step of Catmull-Clark subdivision to the active
        object.

        simple_subdivision() must be used before to prepare the topology


        There are three kind of vertex.
        p_f: new vertex created in the barycenter of a face (created using all vertices
            in the loop)
        mp_e: new vertex created in the midpoint wrt to an edge (created using the two
            vertices of the edge p_e1 and p_e2)
        p_o: original vertices

        Algorithm:

        1. p_f positions are conserved after creation. (Already done in
            simple_subdivision())
        2. mp_e position needs to be re-calculated based on the barycenter using
            original vertices of the edge and the p_f of adjacent faces
            mp_e_new: (p_e1 + p_e2 + p_f1 + p_f2) / 4
        3. p_o position need to be re-calculated  using a weighted barycenter based on
            adjacent p_f's, adjacent mp_e's, and original p_o and the valence of the
            vertex (m)
            p_o_new: (F/m) + (2R/m) + ((m-3)V/m)
            F: centroid of adjacent p_f's
            R: centroid of adjacent mp_e's
            V: p_o

        4. Apply mp_e_new and p_o_new. (This is done after previous calculation to avoid
            "polluting" calculations.

        TODO: Confirm if p_o updating is based on original midpoint or translated
            adjacnet mp_e's
        """
        t = time()
        # 1. p_f positions
        # No need to do anything
        # new_face_points

        # 2.calculate mp_e_new
        mp_e_new = {}
        for edge, vert in new_edge_points.items():
            # (p_e1 + p_e2 + p_f1 + p_f2)
            needed_points = []
            # Get the coords of p_e1 and p_e2
            for p_e in edge.verts:
                needed_points.append(p_e.co)

            # We assume 2-manifold. This should bring 2 faces always
            for adjacent_face in edge.link_faces:
                needed_points.append(new_face_points[adjacent_face].co)

            if len(needed_points) != 4:
                raise Exception(
                    "Calculation of mp_e new location expects only 4 values"
                )
            # print(f"Vert {vert.co}: {needed_points}")
            # print("_________________")
            mp_e_new[vert] = sum(needed_points, Vector()) / 4
            # vert.co = mp_e_new[vert]
        # print(mp_e_new)

        # 3. Calcula p_o_new
        p_o_new = {}
        print("Original")
        adjacent_p_f = []
        for vert, m in original_points.items():
            print(vert.co, m, len(vert.link_edges), len(vert.link_faces))
            # Get adjacent new faces. (Because we )
            for f in vert.link_faces:
                aux = new_face_points.get(f)
                if aux:
                    adjacent_p_f.append()

        # F = ...

        #
        # R = ...
        #
        # V = ...
        #  current vertex position
        # V = v.co

        # # Apply the formula
        # p_o_new[v] = (F + 2 * R + (n - 3) * V) / n

        return time() - t


def main(verbose=True):
    # Get current time
    t = time()

    # Retrieve the active object (the last one selected)
    ob = bpy.context.active_object

    # Check that it is indeed a mesh
    if not ob or ob.type != "MESH":
        print("Active object is not a MESH! Aborting...")
        print(f"(It is a {ob.type})")
        return

    # Go to edit mode or maybe stay in object... aparently there are subtle
    # changes on how to use bpy on each one
    bpy.ops.object.mode_set(mode="OBJECT")

    # Retrieve the mesh data
    me: bpy.types.Mesh = ob.data

    custom_mesh = MeshTopology(me)
    elapsed_t, new_face_points, new_edge_points, original_points = (
        custom_mesh.simple_subdivision()
    )
    print(f"Simple subdivision took {elapsed_t:.3f} s")

    elapsed_t = custom_mesh.move_points(
        new_face_points, new_edge_points, original_points
    )
    print(f"Move points took {elapsed_t:.3f} s")

    # print(f"{bm.edges=}")
    # print(f"{bm.edges=}")
    # print(f"{bm.faces=}")
    # print(f"{bm.loops=}")
    # print(f"{bm.verts=}")
    # print(f"{bm.select_history=}")
    # print(f"{bm.select_mode=}")
    # print(f"{bm.is_valid=}")
    # print(f"{bm.is_wrapped=}")

    # Exercise 1 — “Simple” subdivision

    # Modify the BMesh, can do anything here...
    # for v in custom_mesh.bm.verts:
    #     v.co.x += 1.0

    # # Recalculate internal index tables (CRITICAL)
    # bm.verts.ensure_lookup_table()

    # # Push changes back to the mesh
    # bmesh.update_edit_mesh(me)

    custom_mesh.clean_up()
    bpy.ops.object.mode_set(mode="EDIT")
    # Report performance...
    print(f"Script took: {time() - t:.3f} s")


if __name__ == "__main__":
    main()
