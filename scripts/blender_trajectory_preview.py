import argparse
import sys
from pathlib import Path

import bpy


def _parse_args(argv):
    parser = argparse.ArgumentParser(
        description="Configure an interactive Blender trajectory preview."
    )
    parser.add_argument("--scene-blend", type=Path, default=None)
    parser.add_argument(
        "--shading",
        type=str,
        default="MATERIAL",
        choices=["WIREFRAME", "SOLID", "MATERIAL", "RENDERED"],
    )
    parser.add_argument("--render-engine", type=str, default="BLENDER_EEVEE")
    parser.add_argument("--autoplay", type=int, default=1)
    parser.add_argument("--hide-overlays", type=int, default=1)
    parser.add_argument("--unhide-renderables", type=int, default=1)

    if "--" in argv:
        argv = argv[argv.index("--") + 1 :]
    else:
        argv = []
    return parser.parse_args(argv)


def _load_scene_if_needed(scene_blend: Path | None):
    if scene_blend is None:
        return
    if not scene_blend.exists():
        raise FileNotFoundError(f"Scene blend not found: {scene_blend}")
    if Path(bpy.data.filepath).resolve() == scene_blend.resolve():
        return
    bpy.ops.wm.open_mainfile(filepath=str(scene_blend))


def _unhide_renderables():
    for obj in bpy.data.objects:
        if obj.hide_render:
            continue
        obj.hide_viewport = False
        try:
            obj.hide_set(False)
        except RuntimeError:
            pass

    def walk_layer_collection(layer_collection):
        layer_collection.exclude = False
        layer_collection.hide_viewport = False
        for child in layer_collection.children:
            walk_layer_collection(child)

    walk_layer_collection(bpy.context.view_layer.layer_collection)

    for collection in bpy.data.collections:
        collection.hide_viewport = False


def _configure_viewports(args):
    scene = bpy.context.scene
    scene.frame_set(scene.frame_start)

    if args.shading == "RENDERED":
        try:
            scene.render.engine = args.render_engine
        except TypeError:
            print(
                f"Warning: failed to set render engine to {args.render_engine}, "
                f"keeping {scene.render.engine}",
            )

    for window in bpy.context.window_manager.windows:
        screen = window.screen
        for area in screen.areas:
            if area.type != "VIEW_3D":
                continue
            space = area.spaces.active
            space.region_3d.view_perspective = "CAMERA"
            space.shading.type = args.shading
            if hasattr(space.shading, "use_scene_lights"):
                space.shading.use_scene_lights = True
            if hasattr(space.shading, "use_scene_world"):
                space.shading.use_scene_world = True
            if hasattr(space, "overlay"):
                space.overlay.show_overlays = not bool(args.hide_overlays)
            if hasattr(space, "show_gizmo"):
                space.show_gizmo = False


def _start_playback():
    for window in bpy.context.window_manager.windows:
        screen = window.screen
        for area in screen.areas:
            if area.type != "VIEW_3D":
                continue
            region = next((r for r in area.regions if r.type == "WINDOW"), None)
            if region is None:
                continue
            with bpy.context.temp_override(
                window=window,
                screen=screen,
                area=area,
                region=region,
            ):
                try:
                    bpy.ops.screen.animation_cancel(restore_frame=False)
                except RuntimeError:
                    pass
                bpy.ops.screen.animation_play()
            return


def main():
    args = _parse_args(sys.argv)
    _load_scene_if_needed(args.scene_blend)

    if args.unhide_renderables:
        _unhide_renderables()

    def deferred_setup():
        _configure_viewports(args)
        if args.autoplay:
            _start_playback()
        return None

    bpy.app.timers.register(deferred_setup, first_interval=0.1)


if __name__ == "__main__":
    main()
