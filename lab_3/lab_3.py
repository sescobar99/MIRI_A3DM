import bpy
import bmesh

from bpy.app.handlers import persistent
from mathutils import Vector
from time import time


# Subdivision Surface Modifier
# https://docs.blender.org/manual/en/4.5/modeling/modifiers/generate/subdivision_surface.html
# Implementing Catmull-Clark Subdivision - Introduction & Rules
# https://www.youtube.com/watch?v=mfp1Z1mBClc
# Subdivision surfaces in 5 minutes
# https://www.youtube.com/watch?v=kC8jbGSiuIQ
# Math and Movies (Animation at Pixar) - Numberphile
# https://www.youtube.com/watch?v=mX0NB9IyYpU
# Recursively generated B-spline surfaces on arbitrary topological meshes
# https://people.eecs.berkeley.edu/~sequin/CS284/PAPERS/CatmullClark_SDSurf.pdf

# How to Render Your 3d Animation to a Video File (Blender Tutorial)
# https://www.youtube.com/watch?v=OENbinegV2c
# Blender doesn't use GPU when rendering with Cycles
# https://www.reddit.com/r/blender/comments/14tezr9/blender_doesnt_use_gpu_when_rendering_with_cycles/
# How to - Orbit & Rotate Your Camera Around an Object : Blender 4.5
# https://www.youtube.com/watch?v=A62Exb4Hheg
# BEGINNERS Guide to Rendering in Blender (it's really simple)
# https://www.youtube.com/watch?v=APmw2Q8kBOM

# Global dictionary to store our animation data so the handler can access it
# In a professional addon, you'd store this in Scene properties or a Singleton
START_FRAME = 1
END_FRAME = 100
anim_data = {
    "me_name": "",
    "simple_coords": [],
    "cc_coords": [],
    "start_frame": START_FRAME,
    "end_frame": END_FRAME,
}

def subdivision_animation_callback(scene: bpy.types.Scene):
    """
    Callback function that runs every frame animating the mesh interpolation
    """
    # 1. Confirm the mesh to animate exists
    me = bpy.data.meshes.get(anim_data["me_name"])
    if not me or not anim_data["simple_coords"]:
        return

    # 2. Calculate interpolation factor based on current frame
    start = anim_data["start_frame"]
    end = anim_data["end_frame"]
    curr = scene.frame_current
    # Normalize and clamp
    t = max(0.0, min(1.0, (curr - start) / (end - start)))

    # 3. Update vertex positions
    # This way of updating the vertices is less intuitive but more efficient 
    t_coords = []
    for p0, p1 in zip(anim_data["simple_coords"], anim_data["cc_coords"]):
        p_t = (1 - t) * p0 + t * p1
        t_coords.extend(p_t)  # Flatten for foreach_set
    me.vertices.foreach_set("co", t_coords)
    me.update()


def setup_animation(me: bpy.types.Mesh, n_iterations, start_f, end_f):
    """
    Prepares the mesh and registers the animation handler
    """
    custom_mesh = MeshTopology(me)

    # 1. Perform 'n' iterations of subdivision to get the final topology
    for _ in range(n_iterations):
        _, nfp, nep = custom_mesh.simple_subdivision()
        custom_mesh.calculate_catmull_clark_positions(nfp, nep)
        # Apply t=1.0 so the next iteration starts from the appropriate location
        custom_mesh.apply_interpolation(t=1)

    # 2. Store the final state coordinates for the callback
    # We need the Simple positions (t=0) and CC positions (t=1) of the FINAL topology
    verts = custom_mesh.bm.verts
    verts.ensure_lookup_table()

    anim_data["me_name"] = me.name
    anim_data["simple_coords"] = [
        custom_mesh.pos_simple_subdivision[v].copy() for v in verts
    ]
    anim_data["cc_coords"] = [custom_mesh.pos_catmull_clark[v].copy() for v in verts]
    anim_data["start_frame"] = start_f
    anim_data["end_frame"] = end_f

    # 3. Clean up BMesh and write to Mesh
    custom_mesh.clean_up()

    # Register the handler
    # Remove existing handlers first to avoid duplicates
    bpy.app.handlers.frame_change_pre.clear()
    bpy.app.handlers.frame_change_pre.append(subdivision_animation_callback)


class MeshTopology:
    def __init__(
        self,
        me: bpy.types.Mesh,
    ):

        # Create a Bmesh instance from regular mesh
        self.me = me
        self.bm = bmesh.new()  # create an empty BMesh
        self.bm.from_mesh(me)  # fill it in from a Mesh

        # We are going to store the two different information types of the subdivision
        # process to perform animation
        self.pos_simple_subdivision: dict[bmesh.types.BMVert, Vector] = {}
        self.pos_catmull_clark: dict[bmesh.types.BMVert, Vector] = {}

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
        one step of topological simple subdivision of the mesh (similar to Catmull-Clark
        but without perturbing the positions,
        https://en.wikipedia.org/wiki/Catmull%E2%80%93Clark_subdivision_surface )

        New vertices will be at the barycenter of each face and at the midpoint of
        each edge. (What blender calls “Simple” subdivision).

        The input mesh may contain faces of any arity.
        The result should be made of quads only.
        The original mesh is assumed to be 2-manifold without boundary

        The modified Bmesh keeps the original faces and edges as they are needed in the
        Catmull-Clark calculation step
        """
        t = time()

        # 0. Save original elements before modifying the mesh (useful for future steps)
        # list creates a copy
        self.original_verts = {v: len(v.link_edges) for v in self.bm.verts}
        self.original_edges = list(self.bm.edges)
        self.original_faces = list(self.bm.faces)

        # 1. Generate Face Points
        # For each face, add a face point (using barycenter of original points)
        # print("Faces")
        new_face_verts: dict[bmesh.types.BMFace, bmesh.types.BMVert] = {}
        for face in self.original_faces:
            center = face.calc_center_median()
            # center_placeholder = Vector((0, 0, 0))
            # vert_count = len(face.verts)
            # for vert in face.verts:
            #     center_placeholder += vert.co
            # center = center_placeholder / vert_count
            # print_vector("Center:", center)
            # print("----------------------------")

            # Create new geometry and save it in a F:{V} way
            new_vertex = self.bm.verts.new(center)
            new_face_verts[face] = new_vertex
            # Save simple subdivision positions
            self.pos_simple_subdivision[new_vertex] = center

        # 2. Generate Edge Points (Midpoints)
        # For each edge, add an edge point (use midpoint of original points)
        # print("Edges")
        new_edge_verts: dict[bmesh.types.BMEdge, bmesh.types.BMVert] = {}
        for edge in self.original_edges:
            # midpoint_placeholder = Vector((0, 0, 0))
            # for vert in edge.verts:
            #     midpoint_placeholder += vert.co
            # # Number of vertices for an edge should be 2
            # midpoint = midpoint_placeholder / 2
            # # print_vector("Midpoint:", midpoint)
            # # print("----------------------------")

            # Accessing Bmesh by index is dangerous but it should not matter here
            midpoint = (edge.verts[0].co + edge.verts[1].co) / 2
            new_vertex = self.bm.verts.new(midpoint)
            # Create new geometry and save it in a E:{V} way (kind of, actually E:{V.co})
            new_edge_verts[edge] = new_vertex
            # Save simple subdivision positions
            self.pos_simple_subdivision[new_vertex] = midpoint

        # 3. Save simple subdivision position for original vertices
        for vertex in self.original_verts:
            self.pos_simple_subdivision[vertex] = vertex.co.copy()

        # 4. Create the Quad Topology
        # Connect each new face point to the new edge points of all original
        # edges defining the original face

        # The  quads are ensured by creating a new face for every loop (corner)
        # of the original topology.
        # The points used are (p_o, mp_ne, p_f, and mp_pe)
        # p_o: original vertex
        # mp_ne: new vertex created in the midpoint wrt the next edge
        # p_f: new vertex created in the barycenter of the face
        # mp_pe:new vertex created in the midpoint wrt the previous edge
        for face in self.original_faces:
            p_f = new_face_verts[face]
            for loop in face.loops:
                p_o = loop.vert  # v1
                mp_ne = new_edge_verts[loop.edge]  # v2
                # p_f = new_face_points[face] # v3
                mp_pe = new_edge_verts[loop.link_loop_prev.edge]  # v4

                # Create new face (order matters!)
                self.bm.faces.new((p_o, mp_ne, p_f, mp_pe))

        return time() - t, new_face_verts, new_edge_verts

    def calculate_catmull_clark_positions(
        self,
        new_face_verts: dict[bmesh.types.BMFace, bmesh.types.BMVert],
        new_edge_verts: dict[bmesh.types.BMEdge, bmesh.types.BMVert],
    ):
        """
        Function that calculates one step of Catmull-Clark subdivision to the active
        object.
        No relocation is performed in this function. Info is saved in self.pos_catmull_clark
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

        4. Clean topology (erase original faces and edges)

        """
        t = time()

        # 1. Face Points
        # These are not relocated
        for face, vertex in new_face_verts.items():
            self.pos_catmull_clark[vertex] = vertex.co.copy()

        # 2. Recalculate Edge Points position
        # mp_e_new
        for edge, vertex in new_edge_verts.items():
            # (p_e1 + p_e2 + p_f1 + p_f2)
            needed_points = []
            # Get the coords of p_e1 and p_e2 (original edge vertices)
            for p_e in edge.verts:
                needed_points.append(p_e.co)

            # We assume 2-manifold. This should bring 2 faces always
            for adjacent_face in edge.link_faces:
                needed_points.append(new_face_verts[adjacent_face].co)

            # print(f"Vert {vertex.co}: {needed_points}")
            # print("_________________")
            # if len(needed_points) != 4:
            #     raise Exception(
            #         "Calculation of mp_e new location expects only 4 values"
            #     )
            # Original weight
            self.pos_catmull_clark[vertex] = sum(needed_points, Vector()) / 4

            # Other weights
            # self.pos_catmull_clark[vertex] = (
            #     (2 * needed_points[0])
            #     + (2 * needed_points[1])
            #     + needed_points[2]
            #     + needed_points[3]
            # ) / 6

        # 3. Recalculate Original Vertex position
        # p_o_new
        for vertex, m in self.original_verts.items():
            # These lookups are probably quite costly but...
            # If there is enough time i could try to build V: {new_edges} and V:{new_faces}
            # F: Centroid of Vf  (average of adjacent Face Points)
            adj_face_points = [
                new_face_verts[f].co for f in vertex.link_faces if f in new_face_verts
            ]
            F = sum(adj_face_points, Vector()) / len(adj_face_points)

            # R: centroid of edge midpoints (average of adjacent original Edge Midpoints)
            adj_edges_mp = [
                new_edge_verts[e].co for e in vertex.link_edges if e in new_edge_verts
            ]
            R = sum(adj_edges_mp, Vector()) / len(adj_edges_mp)

            # V: original position
            V = vertex.co

            # print(vertex.co, m)
            # print(F, len(adj_face_points), adj_face_points)
            # print(R, len(adj_edges_mp), adj_edges_mp)
            # print("-----------------------")
            # Apply the weighted barycenter
            p_o_new = (F + (2 * R) + ((m - 3) * V)) / m

            # Catmull-Clark paper
            # (A) New face points - the average of all of the old points
            # defining the face.
            # (B) New edge points - the average of the midpoints of
            # the old edge with the average of the two new face
            # points of the faces sharing the edge.
            # (C) New vertex points - the average
            # Q/n + 2R/n + S(n-3)/n
            # Q = the average of the new face points of all faces
            # adjacent to the old vertex point.
            # R = the average of the midpoints of all old edges
            # incident on the old vertex point.
            # S = old vertex point.

            # Other weights
            # p_o_new = (F + (2 * R) + ((2 * m - 3) * V)) / (2 * m)
            # p_o_new = (F / 4) + (R / 2) + (V / 4)

            self.pos_catmull_clark[vertex] = p_o_new

        bmesh.ops.delete(self.bm, geom=self.original_faces, context="FACES_ONLY")
        bmesh.ops.delete(self.bm, geom=self.original_edges, context="EDGES")

        return time() - t

    def apply_interpolation(self, t: float):
        """
        This function relocates the vertices following the calculation from
        simple_subdivision() and calculate_catmull_clark_positions()

        Linear Interpolation between Simple subdivision(P0) and Catmull-Clark(P1)
        t = 0.0 -> Simple subdivision
        t = 1.0 -> Catmull-Clark

        """
        time_1 = time()
        if t < 0 or t > 1:
            raise ValueError("t value must be between 0 and 1 (inclusive)")

        for v in self.bm.verts:
            # This works for:
            #   - Face vertices(as p0 = p1 and it does not change)
            #   - Edge vertices(going from the midpoint of the edge to the Catmull-Clark pos)
            #   - Original vertices( p0 original pos to p1 weighted barycenter)
            if v in self.pos_simple_subdivision and v in self.pos_catmull_clark:
                p0 = self.pos_simple_subdivision[v]
                p1 = self.pos_catmull_clark[v]
                p_t = (1 - t) * p0 + t * p1
                # Apply the change
                v.co = p_t

        return time() - time_1


def main(verbose=True, ex_3_n: int = 1):
    # Get current time
    t = time()

    # Retrieve the active object (the last one selected)
    ob = bpy.context.active_object

    # Check that it is indeed a mesh
    if not ob or ob.type != "MESH":
        print("Active object is not a MESH! Aborting...")
        print(f"(It is a {ob.type})")
        return

    # Go to edit mode... or maybe stay in object mode... apparently there are subtle
    # changes on how to use bpy on each one
    bpy.ops.object.mode_set(mode="OBJECT")

    # Retrieve the mesh data
    me: bpy.types.Mesh = ob.data
    # custom_mesh = MeshTopology(me)

    # # Exercise 1 — “Simple” subdivision
    # elapsed_t, new_face_points, new_edge_points = custom_mesh.simple_subdivision()
    # print(f"Simple subdivision took {elapsed_t:.3f} s")

    # # Exercise 2 — Catmull-Clark subdivision
    # elapsed_t = custom_mesh.calculate_catmull_clark_positions(
    #     new_face_points, new_edge_points
    # )
    # print(f"calculate_catmull_clark_positions took {elapsed_t:.3f} s")

    # # Exercise 3 — One-parameter family of surfaces
    # elapsed_t = custom_mesh.apply_interpolation(t=1.0)
    # print(f"First subdivision step took {elapsed_t:.3f} s")
    # print("CK iteration #1 applied")

    # if ex_3_n > 1:
    #     t_lerp = time()
    #     for i in range(2, ex_3_n + 1):
    #         print(f"CK iteration #{i} applied")
    #         _, new_face_points, new_edge_points = custom_mesh.simple_subdivision()
    #         _ = custom_mesh.calculate_catmull_clark_positions(
    #             new_face_points, new_edge_points
    #         )
    #         custom_mesh.apply_interpolation(t=1.0)
    #     print(f"CK iterations took {time()-t_lerp:.3f} s")

    # Exercise 4 — Tweak parameters
    # Code with different weights commented + lab3.blend file with results

    # Exercise 5 - ANimate interpolation using t parameter.
    setup_animation(ob, n_iterations=1, start_f=START_FRAME, end_f=END_FRAME)
    bpy.context.scene.frame_start = START_FRAME
    bpy.context.scene.frame_end = END_FRAME
    bpy.context.scene.frame_set(1)

    # Push changes back to the mesh
    # custom_mesh.clean_up()
    # # Is easier to see the results in edit mode
    # bpy.ops.object.mode_set(mode="EDIT")
    # Report performance...
    print(f"Script took: {time() - t:.3f} s")


if __name__ == "__main__":
    main()
