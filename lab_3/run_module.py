# BEWARE: If module_name imports other modules, they are not reloaded automatically
import sys
import os
import bpy
import importlib


def run_module(module_name, verbose=False):
    blend_dir = os.path.dirname(bpy.data.filepath)
    if blend_dir not in sys.path:
        sys.path.append(blend_dir)

    module = importlib.import_module(module_name)
    importlib.reload(module)
    if hasattr(module, "main"):
        module.main(verbose)
    else:
        print(f"{module_name} has no main()")


print("------------------------------------------------------Running")
run_module("lab_3", verbose=False)

print("------------------------------------------------------Finished")
