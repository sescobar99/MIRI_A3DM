import bpy
import numpy as np

from mathutils import Vector
from time import time
from utils import print_vector
from utils import UnionFind


class MeshTopology:
    def __init__(
        self,
        me: bpy.types.Mesh,
    ):
        # self.me = me

        # Having a copy of the data as bpy_prop_collection and another one
        # as np array seems to be non-efficient memory wise but right now
        # we care on being time efficient, taking advantage of vectorized operations
        # and fast access to basic-type attributes within collections.
        startup_t = time()
        t = time()
        ### Vertices
        self.vertices = me.vertices
        self.V_count = len(self.vertices)
        # Get all coords from all vertices into a flat array
        # Each vertex has 3 cords, so the size is len() * 3
        coords = np.empty(self.V_count * 3, dtype=np.float32)
        # Bulk pull the data
        self.vertices.foreach_get("co", coords)
        # Reshape it back to (N, 3)
        self.vertices_np = coords.reshape((self.V_count, 3))

        t_vertices = time() - t
        # print(f"{t_vertices=}")
        t = time()
        ### Edges
        self.E_to_V = me.edges
        self.E_count = len(me.edges)

        # Get all vertex indices from all edges into a flat array
        # Each edge has 2 vertices, so the size is len() * 2
        edge_verts = np.empty(self.E_count * 2, dtype=np.int32)
        self.E_to_V.foreach_get("vertices", edge_verts)
        self.E_to_V_np = edge_verts.reshape((self.E_count, 2))

        ### E:{F}
        # I'm not going to over-complicate things here dealing with numpy
        self.E_to_F: list[list[int]] = [[] for _ in range(self.E_count)]
        for poly_idx, poly in me.polygons.items():
            # I prefer poly.loop_indices but this way allows typehints
            loop_indices = range(poly.loop_start, poly.loop_start + poly.loop_total)
            for loop_idx in loop_indices:
                self.E_to_F[me.loops[loop_idx].edge_index].append(poly_idx)
        
        t_edges = time() - t
        # print(f"{t_edges=}")
        t = time()

        ### Faces
        self.faces = me.polygons
        self.F_count = len(me.polygons)

        t_faces = time() - t
        # print(f"{t_faces=}")
        self.startup_time = time() - startup_t

    def calculate_centroid(self):
        t = time()
        # Average over each axis (x,y,z)
        centroid = np.mean(self.vertices_np, axis=0)
        return time() - t, Vector(centroid)

    def calculate_valence(self):
        """
        Returns:
            Tuple: Time elapsed, Minimum Valence, Maximum valence, Average valence
        """
        t = time()
        # https://numpy.org/doc/stable/reference/generated/numpy.bincount.html
        # np.bincount to count how many times each Vertex ID appears
        # ravel() is needed to flatten the array back again
        valences = np.bincount(self.E_to_V_np.ravel(), minlength=self.V_count)
        # get vectorized stats:
        max_v = np.max(valences)
        min_v = np.min(valences)
        avg_v = np.mean(valences)
        return time() - t, min_v, max_v, avg_v, valences

    def edges_manifoldness(self):
        """
        Returns:
            Tuple: Time elapsed, Boundary edges #, Manifold edges #, Non-manifold edges #,
            Boundary faces (list),  Non-manifold faces (list)
        """
        t = time()
        boundary = 0
        manifold = 0
        non_manifold = 0

        # Eases exercise 9 logic
        boundary_faces = []
        non_manifold_faces = []

        for e_idx, faces in enumerate(self.E_to_F):
            manifoldness = len(faces)

            match manifoldness:
                case 1:
                    boundary += 1
                    boundary_faces.extend(faces[:])
                case 2:
                    manifold += 1
                # len<1 or len>2. Apparently there is something called "wire edge",
                # in that case the edge is not adjacent to any face
                # Todo pal mismo saco
                case _:
                    non_manifold += 1
                    non_manifold_faces.extend(faces[:])

        return (
            time() - t,
            boundary,
            manifold,
            non_manifold,
            list(set(boundary_faces)),
            list(set(non_manifold_faces)),
        )

    def edges_curvature(self):
        """
        For each edge  test if it is, concave, convex or planar.

        An edge is convex if Ve - Vs (edge as vector) and LxR (cross product of the normals)
            have same direction

        Returns:
            Tuple: Time elapsed, Planar edges #, Convex edges #, Concave edges #, Non-manifold edges #
        """
        t = time()
        concave = 0
        convex = 0
        planar = 0
        skipped = 0

        zero_vector = Vector()
        for e_idx, faces in enumerate(self.E_to_F):
            # Only apply curvature test to manifold edges
            if len(faces) != 2:
                skipped += 1
                continue

            # Assign arbitrary directions. (Blender's mesh doesn't use half edges
            # so we are going to have to figure out direction anyways)
            left_face_idx, right_face_idx = faces
            left_normal = self.faces[left_face_idx].normal
            right_normal = self.faces[right_face_idx].normal

            # Check planar faces: (both normals point in the same direction)
            LxR = left_normal.cross(right_normal)
            if LxR == zero_vector:
                planar += 1
                continue

            # Check if initial assumption was ok.
            # If we find our vertices (self.E_to_V_np[e_idx]) to be in the same order
            # in the left face, we were right. Otherwise we need to take the edge on the
            # other way around (swap end<->start)
            # And then compare Ve-Vs against LxR (using dot product)
            v_idx_start, v_idx_end = self.E_to_V_np[e_idx]
            face_verts = list(self.faces[left_face_idx].vertices)
            # Find where v_idx_start is in the face and check if the next vertex
            # in the face is v_idx_end
            if (
                face_verts[(face_verts.index(v_idx_start) + 1) % len(face_verts)]
                == v_idx_end
            ):
                # Order is v_idx_start -> v_idx_end
                Ve_minus_Vs = (
                    self.vertices[v_idx_end].co - self.vertices[v_idx_start].co
                )
            else:
                # Order is v_idx_end -> v_idx_start. We need to swap
                Ve_minus_Vs = (
                    self.vertices[v_idx_start].co - self.vertices[v_idx_end].co
                )
            # Using self.vertices instead of vertices_np to avoid recasting to vector

            # Prone to floating point errors. :(
            if LxR.dot(Ve_minus_Vs) > 0:
                convex += 1
            else:
                concave += 1
        return time() - t, planar, convex, concave, skipped

    def count_shells(self):
        """
        Use union find structure/algorithm to join faces based on shared edges.
        At the end the number of shells is the number of different roots of the union find

        Returns:
            Tuple: Time elapsed, Number of shells, UnionFind
        """
        t = time()
        uf = UnionFind(self.F_count)

        # Connect faces sharing edges
        for edge_faces in self.E_to_F:
            # Edge is not being shared
            if len(edge_faces) < 2:
                continue

            # Union all faces sharing this edge
            f0 = edge_faces[0]
            # Should work for non-manyfold too (Not tested)
            for f in edge_faces[1:]:
                uf.union(f0, f)

        # Count unique roots
        shells_count = len({uf.find(f) for f in range(self.F_count)})

        return time() - t, shells_count, uf

    def count_genus(self, raise_exception=True):
        """
        Counts genus using Euler equation and number of shells
          (uses count_shells() internally )

        Returns:
            Tuple: Time elapsed, Genus count

        Raises:
            Exception: Genus only makes sense on valid polyhedra i.e. closed, orientable,
            and free of self intersections. The main goal now is something different than
            checking all of those. In case genus calculation gives non integer number,
            raise exception

        """
        t = time()
        _, shells_count, _ = self.count_shells()

        NUMBER_OF_RINGS = 0
        # Blender doesn't allows rings -> Always 0

        # F + V = E + R + 2(S - H)
        # H = S - (F + V - E - R)/2
        genus_count = (
            shells_count
            - (self.F_count + self.V_count - self.E_count - NUMBER_OF_RINGS) / 2
        )
        if not genus_count.is_integer() and raise_exception:
            err_msg = (
                f"Genus calculation gives non-integer number ({genus_count}). "
                "Probably the object is a not valid surface (e.g. open)"
            )

            raise Exception(err_msg)
        return time() - t, genus_count

    def calculate_surfaces_area(self):
        """
        Uses algorithm for 3D arbitrary polygon.

        Returns:
            Tuple: Time elapsed, Total Area (Own), Total Area(Blender), Area per Face (Own),
            Area per Face (Blender), Normal vectors by face (Own)

        """
        # For each face get all coords from vertices corresponding to it
        # Xi denotes x coordinate of i vertex. Xii denotes x coordinate of the next vertex
        # in the loop
        # Sx = (1/2) * SUM [(Yi-Yii) * (Zi+Zii)]
        # Sy = (1/2) * SUM [(Zi-Zii) * (Xi+Xii)]
        # Sz = (1/2) * SUM [(Xi-Xii) * (Yi+Yii)]
        # Normal vector is given by: (Sx, Sy, Sz)
        # Area of the face is || normal || = sqr(Sx^2 + Sy^2 + Sz^2)

        t = time()

        # I'm tired boss. No more numpy micro-optimizations please :(
        normal_vectors = np.zeros((self.F_count, 3))
        for f_idx, face in enumerate(self.faces):
            Sx = 0.0
            Sy = 0.0
            Sz = 0.0

            # Get vertex indices for this polygon
            v_indices = face.vertices
            v_count = len(v_indices)
            # And then for each one get+sum its coord
            for v_idx in range(v_count):
                # Current vertex (i)
                v_i = self.vertices[v_indices[v_idx]].co
                # Next vertex (ii)
                v_ii = self.vertices[v_indices[(v_idx + 1) % v_count]].co

                # Sx = (1/2) * SUM [(Yi - Yii) * (Zi + Zii)]
                Sx += (v_i.y - v_ii.y) * (v_i.z + v_ii.z)
                Sy += (v_i.z - v_ii.z) * (v_i.x + v_ii.x)
                Sz += (v_i.x - v_ii.x) * (v_i.y + v_ii.y)
                # print(Sx, Sy,Sz)
            # Apply the  (1/2) * ...  part
            normal_vectors[f_idx] = [Sx * 0.5, Sy * 0.5, Sz * 0.5]
        # Vectorized area calculation ( np again :| )
        # Area = sqrt(Sx^2 + Sy^2 + Sz^2)
        computed_areas = np.linalg.norm(normal_vectors, axis=1)

        # Get Blender's areas for comparison
        blender_areas = np.empty(self.F_count)
        self.faces.foreach_get("area", blender_areas)

        total_computed = sum(computed_areas)
        total_blender = sum(blender_areas)
        return (
            time() - t,
            total_computed,
            total_blender,
            computed_areas,
            blender_areas,
            normal_vectors,
        )

    def calculate_volume(self):
        # Uses face trinagulation + tretrahedron volume calculation
        t = time()
        total_volume = 0.0

        _, boundary_count, _, non_manifold_count, boundary_faces, non_manifold_faces = (
            self.edges_manifoldness()
        )
        # if len(self.edges_non_manifold) != 0:
        #     print("Not defined for non manifolds")

        # print(f"{boundary_count=}")
        # print(f"{non_manifold_count=}")
        # print(f"{boundary_faces=}")
        # print(f"{non_manifold_faces=}")

        _, shells_count, uf = self.count_shells()

        # PAra cada sheel. Comrobar si tiene edges boundary o non manifold.
        # -> skip
        # otherwise. procesar
        # print(uf.parent)
        # print(uf.rank)
        # Agrupar por shell
        shells: dict[int, list[int]] = {}
        for f in range(self.F_count):
            root = uf.find(f)
            shells.setdefault(root, []).append(f)
        # print(shells)

        for root, faces in shells.items():
            if boundary_count != 0 and (not set(faces).isdisjoint(set(boundary_faces))):
                # Check if this is a problematic shell
                # print(f"Problematic shell")
                # print(f"{faces=}")
                # print(f"{boundary_faces=}")
                continue
            if non_manifold_count != 0 and (
                not set(faces).isdisjoint(set(non_manifold_faces))
            ):
                # Check if this is a problematic shell
                # No non_manifold in the examples.
                continue

            # Compute volume
            shell_volume = 0.0

            # Triangulate faces and create tetrahedrons with the tip at the origin
            for f_idx in faces:
                face = self.faces[f_idx]
                vertices = face.vertices
                # triangulate fan: v0, v[i], v[i+1]
                v0 = self.vertices[vertices[0]].co
                for i in range(1, len(vertices) - 1):
                    v1 = self.vertices[vertices[i]].co
                    v2 = self.vertices[vertices[i + 1]].co
                    # Signed volume of tetrahedron (pyramid)
                    # 1/3 * Base * Height
                    # base = triangle area = (v1 cross v2) /2
                    # Equivalent to the barycenter calculation
                    # For me simpler conceptually
                    shell_volume += v0.dot(v1.cross(v2)) / 6.0

            # print(f"{shell_volume=}")
            total_volume += shell_volume

        # print(f"Total volume: {total_volume:.3f}")
        return time() - t, total_volume

    def print_info(self, precision=3):
        # Vertices
        header = f"{'Vertex':>6} | {'X':>8} {'Y':>8} {'Z':>8}"
        lines = [
            f"{i:6d} | {vertex.co.x:8.{precision}f} {vertex.co.y:8.{precision}f} {vertex.co.z:8.{precision}f}"
            for i, vertex in self.vertices.items()
        ]
        output = "\n".join([header] + lines)
        print(output)
        print("-" * len(header))

        # Edges
        header = f"{'Edge':>6} | {'V1':>6} {'V2':>6}"
        lines = [f"{i:6d} | {e[0]:6d} {e[1]:6d}" for i, e in enumerate(self.E_to_V_np)]

        output = "\n".join([header] + lines)
        print(output)
        print("-" * len(header))

        print(self.E_to_F)


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

    # If we are in edit mode, return to object mode
    bpy.ops.object.mode_set(mode="OBJECT")

    # Retrieve the mesh data
    me: bpy.types.Mesh = ob.data

    # Function that does all the work
    mesh_topology = MeshTopology(me)
    if verbose:
        mesh_topology.print_info()

    print(f"Startup took: {mesh_topology.startup_time:.3f} s")

    # Exercise 1 - Centroid
    elapsed_t, result = mesh_topology.calculate_centroid()
    print_vector(f"Centroid (took {elapsed_t:.3f} s):\n\t", result)

    # Exercise 2
    # Result for hollow icosas:
    # Centroid: (0.016, 6.077, 0.000)
    # Centroid in World coordinates: (-0.267, 0.000, -0.186)
    # 1. It is not evenly distributed in the x axis. There is one piece a little bit off
    # 2. Vertex coordinates are given in local coordinates.
    # 3. The local coordinates of hollow isocas are different than world coordinates.
    #  (Maybe this model comes from another 3D software as its local coordinates are Y-up)
    print_vector("Centroid in World coordinates: ", ob.matrix_world @ result)

    # Exercise 3
    elapsed_t, min_v, max_v, avg_v, _ = mesh_topology.calculate_valence()
    print(
        f"Valence  (took {elapsed_t:.3f} s):\n\t"
        f"Min: {min_v} | Max: {max_v} | Avg: {avg_v:.3f}"
    )

    # Exercise 4
    elapsed_t, boundary, manifold, non_manifold, _, _ = (
        mesh_topology.edges_manifoldness()
    )
    print(
        f"Edges manifoldness (took {elapsed_t:.3f} s):\n\t",
        f"Boundary: {boundary} | Manifold: {manifold} | Non-manifold: {non_manifold}",
    )

    # Exercise 5
    elapsed_t, planar, convex, concave, skipped = mesh_topology.edges_curvature()
    print(
        f"Edges curvature (took {elapsed_t:.3f} s):\n\t",
        f"Planar: {planar} | Convex: {convex} | Concave: {concave} | Skipped(non-manyfold): {skipped}",
    )

    # Exercise 6
    elapsed_t, shells_count, _ = mesh_topology.count_shells()
    print(f"Number of shells (took {elapsed_t:.3f} s):\n\t{shells_count} shell/s")

    # Exercise7 — genus
    # Using your result in Ex. 6 and the fact that Blender’s model does not include rings, use the
    # euler formula to compute the genus of the selected object.
    elapsed_t, genus_count = mesh_topology.count_genus(raise_exception=False)
    print(f"Number of genus (took {elapsed_t:.3f} s):\n\t{genus_count} genus/genera")

    # Exercise8 — Surface area
    elapsed_t, area_o, area_b, _, _, _ = mesh_topology.calculate_surfaces_area()
    print(
        f"Surface area (took {elapsed_t:.3f} s):\n\t"
        f"Ours:{area_o:.3f} | Blender's {area_b:.3f}"
    )

    # Exercise9 — Total volume
    elapsed_t, total_volume = mesh_topology.calculate_volume()
    print(f"Surface volume (took {elapsed_t:.3f} s):\n\t{total_volume:.3f}")
    # Report performance...
    print(f"Script took: {time() - t:.3f} s")


if __name__ == "__main__":
    main()
