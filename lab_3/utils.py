from mathutils import Vector


def print_vector(name: str, vec: Vector):
    # Formats each component to exactly 3 decimal places
    print(f"{name}({vec.x:.3f}, {vec.y:.3f}, {vec.z:.3f})")
