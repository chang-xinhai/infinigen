# Structured Light rendering module for Infinigen.
# Integrates structured light camera rig (2x IR cameras + 1 projector + 1 RGB camera)
# into the Infinigen scene generation pipeline.
#
# Camera layout (viewed from behind):
#   [Left IR] --- [Projector + RGB] --- [Right IR]
# The projector and RGB camera share the same position (center).
# Left/Right IR cameras are offset by ±baseline/2 along the local X axis.
# RGB captures the scene WITHOUT projection (ambient light only).
# IR cameras capture the scene WITH the projected pattern.

import json
import logging
import time
from pathlib import Path

import bpy
import gin
import mathutils
import numpy as np

from infinigen.core import init

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
# Constants – names used in blender objects
# ──────────────────────────────────────────────────────────────

SL_ROOT_NAME = "_SL_Root_"
SL_LEFT_CAM_NAME = "_SL_LeftIR_"
SL_RIGHT_CAM_NAME = "_SL_RightIR_"
SL_RGB_CAM_NAME = "_SL_RGB_"
SL_PROJ_OBJ_NAME = "_SL_Projector_"
SL_PROJ_SPOT_NAME = "_SL_Projector_Spot_"

# ──────────────────────────────────────────────────────────────
# Structured‑Light Camera Rig
# ──────────────────────────────────────────────────────────────


@gin.configurable
class StructuredLightRig:
    """Create and manage a structured‑light camera rig inside an existing Infinigen scene."""

    def __init__(
        self,
        baseline=0.065,
        cam_fov_deg=69.4,
        cam_sensor_width=6.328,
        cam_sensor_height=4.746,
        proj_fov_delta_deg=5.0,
        proj_dlp_size=6.328,
        proj_energy=30.0,
        resolution_x=1280,
        resolution_y=720,
        pattern_resolution_x=1280,
        pattern_resolution_y=720,
    ):
        self.baseline = baseline
        self.cam_fov_deg = cam_fov_deg
        self.cam_sensor_width = cam_sensor_width
        self.cam_sensor_height = cam_sensor_height
        self.proj_fov_delta_deg = proj_fov_delta_deg
        self.proj_dlp_size = proj_dlp_size
        self.proj_energy = proj_energy
        self.resolution_x = resolution_x
        self.resolution_y = resolution_y
        self.pattern_resolution_x = pattern_resolution_x
        self.pattern_resolution_y = pattern_resolution_y

        # Will be populated by build()
        self.root = None
        self.left_cam = None
        self.right_cam = None
        self.rgb_cam = None
        self.proj_obj = None
        self.proj_spot = None

    # ── maths helpers ──────────────────────────────────────────

    @property
    def cam_fov_rad(self):
        return np.deg2rad(self.cam_fov_deg)

    @property
    def proj_fov_rad(self):
        return np.deg2rad(self.cam_fov_deg + self.proj_fov_delta_deg)

    # ── build the rig ──────────────────────────────────────────

    def build(self):
        """Instantiate all Blender objects for the SL rig."""
        # Root empty
        bpy.ops.object.empty_add(type="PLAIN_AXES")
        self.root = bpy.context.active_object
        self.root.name = SL_ROOT_NAME

        # Left IR camera
        self.left_cam = self._make_camera(SL_LEFT_CAM_NAME)
        self.left_cam.location = mathutils.Vector((-self.baseline / 2, 0, 0))

        # Right IR camera
        self.right_cam = self._make_camera(SL_RIGHT_CAM_NAME)
        self.right_cam.location = mathutils.Vector((self.baseline / 2, 0, 0))

        # RGB camera (centre, co-located with projector)
        self.rgb_cam = self._make_camera(SL_RGB_CAM_NAME)
        self.rgb_cam.location = mathutils.Vector((0, 0, 0))

        # Projector (uses the Blender Projectors addon)
        self._make_projector()

        # Parent everything to root
        for child in [self.left_cam, self.right_cam, self.rgb_cam, self.proj_obj]:
            child.parent = self.root
            child.matrix_parent_inverse = self.root.matrix_world.inverted()

        logger.info("Structured‑light rig built successfully")

    def _make_camera(self, name: str) -> bpy.types.Object:
        bpy.ops.object.camera_add()
        cam = bpy.context.active_object
        cam.name = name
        cam.data.clip_end = 1e4
        # Sensor — adjust height to match resolution aspect ratio so Blender renders correctly
        cam.data.sensor_fit = "HORIZONTAL"
        cam.data.sensor_width = self.cam_sensor_width
        cam.data.sensor_height = self.cam_sensor_width * self.resolution_y / self.resolution_x
        # FOV
        cam.data.angle = self.cam_fov_rad
        return cam

    def _make_projector(self):
        """Create the projector using the Projectors addon, or fall back to manual spot light."""
        addon_available = self._try_enable_projector_addon()

        if addon_available:
            self._make_projector_with_addon()
        else:
            self._make_projector_manual()

    def _try_enable_projector_addon(self) -> bool:
        """Try to enable the Projectors addon. Return True if successful."""
        candidates = [
            "Projectors-main",
            "projectors-main",
            "projectors_main",
            "Projectors",
            "projectors",
        ]
        for name in candidates:
            try:
                bpy.ops.preferences.addon_enable(module=name)
                if name in bpy.context.preferences.addons.keys():
                    logger.info(f"Projector addon enabled: {name}")
                    return True
            except (RuntimeError, Exception):
                continue
        logger.warning(
            "Projectors addon not found — using manual spot light projector. "
            "For best results, install https://github.com/Ocupe/Projectors"
        )
        return False

    def _make_projector_with_addon(self):
        """Create projector via the Blender Projectors addon."""
        bpy.ops.projector.create()
        self.proj_obj = self._find_new_obj("Projector", "CAMERA")
        self.proj_spot = self._find_new_obj("Projector.Spot", "LIGHT")

        # Configure custom texture mode
        self.proj_obj.proj_settings.projected_texture = "custom_texture"

        # Compute projector FOV mapping
        scale_x, scale_y = self._compute_proj_scales()

        mapping_node = (
            self.proj_spot.data.node_tree.nodes["Group"]
            .node_tree.nodes["Mapping.001"]
        )
        mapping_node.inputs[3].default_value[0] = scale_x
        mapping_node.inputs[3].default_value[1] = scale_y

        self.proj_spot.data.energy = self.proj_energy
        self.proj_obj.name = SL_PROJ_OBJ_NAME
        self.proj_spot.name = SL_PROJ_SPOT_NAME
        self._projector_uses_addon = True

    def _make_projector_manual(self):
        """Create a spot light projector manually (no addon required)."""
        # Create spot light
        bpy.ops.object.light_add(type="SPOT")
        spot = bpy.context.active_object
        spot.name = SL_PROJ_SPOT_NAME
        spot_data = spot.data

        # Configure spot
        spot_data.energy = self.proj_energy
        spot_data.spot_size = self.proj_fov_rad
        spot_data.spot_blend = 0.0
        spot_data.shadow_soft_size = 0.0

        # Use nodes for image texture projection
        spot_data.use_nodes = True
        tree = spot_data.node_tree
        nodes = tree.nodes
        links = tree.links

        # Clear default nodes except Emission
        emission_node = None
        for node in list(nodes):
            if node.type == "EMISSION":
                emission_node = node
            elif node.type != "OUTPUT_LIGHT":
                nodes.remove(node)

        # Add Image Texture node
        img_tex = nodes.new(type="ShaderNodeTexImage")
        img_tex.name = "Image Texture"
        img_tex.extension = "CLIP"

        # Add Texture Coordinate node
        tex_coord = nodes.new(type="ShaderNodeTexCoord")

        # Add Mapping node for FOV scaling
        mapping = nodes.new(type="ShaderNodeMapping")
        mapping.name = "Mapping"
        scale_x, scale_y = self._compute_proj_scales()
        mapping.inputs["Scale"].default_value[0] = scale_x
        mapping.inputs["Scale"].default_value[1] = scale_y

        # Connect: TexCoord -> Mapping -> ImageTexture -> Emission
        links.new(tex_coord.outputs["Object"], mapping.inputs["Vector"])
        links.new(mapping.outputs["Vector"], img_tex.inputs["Vector"])
        if emission_node:
            links.new(img_tex.outputs["Color"], emission_node.inputs["Color"])

        # Create a dummy camera object as projector parent (for intrinsic computation)
        bpy.ops.object.empty_add(type="SINGLE_ARROW")
        proj_empty = bpy.context.active_object
        proj_empty.name = SL_PROJ_OBJ_NAME

        self.proj_obj = proj_empty
        self.proj_spot = spot
        self._projector_uses_addon = False

    def _compute_proj_scales(self):
        """Compute mapping scale_x, scale_y for projector FOV."""
        ratio_w = self.cam_sensor_width
        ratio_h = self.cam_sensor_height
        x = np.sqrt(self.proj_dlp_size ** 2 / (ratio_w ** 2 + ratio_h ** 2))
        sensor_w = ratio_w * x
        sensor_h = ratio_h * x
        half_fov = self.proj_fov_rad / 2
        lens_dist = sensor_w / (2 * np.tan(half_fov))
        scale_x = sensor_w / lens_dist
        scale_y = scale_x / sensor_w * sensor_h
        return scale_x, scale_y

    @staticmethod
    def _find_new_obj(prefix: str, obj_type: str) -> bpy.types.Object:
        """Find a recently-created Blender object by name prefix and type."""
        for obj in bpy.data.objects:
            if obj.name.startswith(prefix) and obj.type == obj_type:
                return obj
        raise RuntimeError(f"Cannot find Blender object {prefix} ({obj_type})")

    # ── reload from existing scene ─────────────────────────────

    def load_existing(self):
        """Load SL rig objects that already exist in the .blend file."""
        self.root = bpy.data.objects[SL_ROOT_NAME]
        self.left_cam = bpy.data.objects[SL_LEFT_CAM_NAME]
        self.right_cam = bpy.data.objects[SL_RIGHT_CAM_NAME]
        self.rgb_cam = bpy.data.objects[SL_RGB_CAM_NAME]
        self.proj_obj = bpy.data.objects[SL_PROJ_OBJ_NAME]
        self.proj_spot = bpy.data.objects[SL_PROJ_SPOT_NAME]

    # ── pose helpers ───────────────────────────────────────────

    def set_pose(self, location, rotation_matrix):
        """Set rig world pose. *rotation_matrix* is a 3×3 mathutils.Matrix."""
        self.root.matrix_world = (
            mathutils.Matrix.Translation(location)
            @ rotation_matrix.to_4x4()
        )

    # ── projector helpers ──────────────────────────────────────

    def set_pattern(self, pattern_path: str):
        """Load or switch the pattern image on the projector. Returns the previous image."""
        pattern_path = Path(pattern_path)
        img = bpy.data.images.get(pattern_path.name)
        if img is None:
            img = bpy.data.images.load(filepath=str(pattern_path))

        img_tex_node = self.proj_spot.data.node_tree.nodes["Image Texture"]
        prev = img_tex_node.image
        img_tex_node.image = img
        return prev

    def set_projector_visible(self, on=True):
        self.proj_spot.hide_render = not on

    # ── scene light helpers ────────────────────────────────────

    @staticmethod
    def set_scene_lights(on=True):
        """Toggle all lights in the scene except the SL projector."""
        for obj in bpy.data.objects:
            if obj.type == "LIGHT" and obj.name != SL_PROJ_SPOT_NAME:
                obj.hide_render = not on

    @staticmethod
    def set_env_strength(strength):
        """Set environment (world) background strength. Returns original value."""
        world = bpy.data.worlds.get("World")
        if world is None:
            return 0
        bg = world.node_tree.nodes.get("Background")
        if bg is None:
            return 0
        orig = bg.inputs[1].default_value
        bg.inputs[1].default_value = strength
        return orig

    # ── intrinsic / extrinsic helpers ──────────────────────────

    def get_camera_intrinsic(self):
        """Return 3×3 numpy intrinsic matrix for the IR cameras (identical for L and R)."""
        return self._intrinsic_from_cam(self.left_cam.data)

    def get_rgb_intrinsic(self):
        """Return 3×3 numpy intrinsic matrix for the RGB camera."""
        return self._intrinsic_from_cam(self.rgb_cam.data)

    def _intrinsic_from_cam(self, camd):
        """Compute intrinsic matrix from camera data directly (avoids sensor aspect-ratio check)."""
        f_mm = camd.lens
        scene = bpy.data.scenes["Scene"]
        W = scene.render.resolution_x
        H = scene.render.resolution_y
        sw = camd.sensor_width
        fx = f_mm * W / sw
        fy = f_mm * H / (sw * H / W)  # assuming square pixels
        cx = W / 2.0
        cy = H / 2.0
        return np.array([[fx, 0, cx], [0, fy, cy], [0, 0, 1]], dtype=np.float64)

    def get_projector_intrinsic(self):
        """Compute and return 3×3 projector intrinsic matrix."""
        if getattr(self, "_projector_uses_addon", False):
            mapping_node = (
                self.proj_spot.data.node_tree.nodes["Group"]
                .node_tree.nodes["Mapping.001"]
            )
            scale_x = mapping_node.inputs[3].default_value[0]
            scale_y = mapping_node.inputs[3].default_value[1]
        else:
            scale_x, scale_y = self._compute_proj_scales()

        reso_x = self.pattern_resolution_x
        reso_y = self.pattern_resolution_y
        K = np.array(
            [
                [reso_x / scale_x, 0, 0.5 * reso_x],
                [0, reso_y / scale_y, 0.5 * reso_y],
                [0, 0, 1],
            ],
            dtype=np.float64,
        )
        return K

    def get_camera_extrinsic(self, cam_obj):
        """Return 4×4 world‑to‑camera extrinsic (OpenCV convention: Y‑down, Z‑forward)."""
        T_world2cam = np.asarray(cam_obj.matrix_world, dtype=np.float64) @ np.diag(
            (1.0, -1.0, -1.0, 1.0)
        )
        return T_world2cam

    def get_rel_translation(self, lr: str):
        """Translation of L/R camera relative to projector (centre)."""
        x = -self.baseline / 2 if lr.upper() == "L" else self.baseline / 2
        return np.array([x, 0, 0], dtype=np.float64)


# ──────────────────────────────────────────────────────────────
# Core rendering function
# ──────────────────────────────────────────────────────────────


@gin.configurable
def render_structured_light(
    frames_folder: Path,
    camera: bpy.types.Object,
    sl_baseline=0.065,
    sl_cam_fov_deg=69.4,
    sl_cam_sensor_width=6.328,
    sl_cam_sensor_height=4.746,
    sl_proj_fov_delta_deg=5.0,
    sl_proj_dlp_size=6.328,
    sl_proj_energy=30.0,
    sl_resolution_x=1280,
    sl_resolution_y=720,
    sl_pattern_resolution_x=1280,
    sl_pattern_resolution_y=720,
    sl_pattern_dir=None,
    sl_pattern_white="white.png",
    sl_max_samples=64,
    sl_exr_depth=16,
):
    """
    Render structured‑light data for every frame that the *camera* has keyframes for.

    Outputs per frame per pattern:
        {frame}_{pattern}_{L/R}_Image.{exr,png}  – IR images with pattern projected
        {frame}_{L/R}_Depth.exr                  – depth from L/R IR cameras
        {frame}_{L/R}_Normal.exr                 – normals from L/R IR cameras
        {frame}_RGB.{exr,png}                    – RGB without projector
        {frame}_Depth.exr                        – depth from RGB camera
        parameters.npz                           – all intrinsic / extrinsic data
    """
    tic = time.time()

    frames_folder = Path(frames_folder)
    sl_output = frames_folder / "structured_light"
    sl_output.mkdir(parents=True, exist_ok=True)

    init.configure_cycles_devices()

    # ── Resolve pattern files ──────────────────────────────────
    if sl_pattern_dir is None:
        # Try to auto-detect patterns from common locations
        candidates = [
            Path(__file__).resolve().parents[3] / "data" / "patterns",
            Path.home() / "projects" / "deepsl-data" / "data" / "patterns",
        ]
        for cand in candidates:
            if cand.is_dir():
                sl_pattern_dir = str(cand)
                logger.info(f"Auto-detected pattern directory: {sl_pattern_dir}")
                break
        else:
            logger.warning("No pattern directory found; only white pattern will be used")

    pattern_paths = []
    white_pattern_path = None
    if sl_pattern_dir is not None:
        pdir = Path(sl_pattern_dir)
        white_pattern_path = pdir / sl_pattern_white
        for p in sorted(pdir.iterdir()):
            if p.suffix.lower() in {".png", ".jpg", ".jpeg"} and p.name != sl_pattern_white:
                pattern_paths.append(str(p))
        if white_pattern_path.exists():
            white_pattern_path = str(white_pattern_path)
        else:
            white_pattern_path = None

    if not pattern_paths:
        logger.warning("No structured light patterns found – will render without patterns")

    # ── Build the SL rig ───────────────────────────────────────
    rig = StructuredLightRig(
        baseline=sl_baseline,
        cam_fov_deg=sl_cam_fov_deg,
        cam_sensor_width=sl_cam_sensor_width,
        cam_sensor_height=sl_cam_sensor_height,
        proj_fov_delta_deg=sl_proj_fov_delta_deg,
        proj_dlp_size=sl_proj_dlp_size,
        proj_energy=sl_proj_energy,
        resolution_x=sl_resolution_x,
        resolution_y=sl_resolution_y,
        pattern_resolution_x=sl_pattern_resolution_x,
        pattern_resolution_y=sl_pattern_resolution_y,
    )
    rig.build()

    # ── Render settings ────────────────────────────────────────
    scene = bpy.data.scenes["Scene"]
    scene.render.engine = "CYCLES"
    scene.cycles.device = "GPU"
    scene.cycles.samples = sl_max_samples
    scene.render.use_persistent_data = True
    scene.render.resolution_x = sl_resolution_x
    scene.render.resolution_y = sl_resolution_y

    # Store original env strength
    orig_env_strength = rig.set_env_strength(0)
    rig.set_env_strength(orig_env_strength)  # restore for now

    # ── Iterate over frames ────────────────────────────────────
    frame_start = scene.frame_start
    frame_end = scene.frame_end

    all_extrinsics = []

    # Get the camera rig that owns the infinigen camera so we can
    # copy its per‑frame pose onto the SL rig.
    cam_rig = camera.parent

    for frame_idx in range(frame_start, frame_end + 1):
        scene.frame_set(frame_idx)
        bpy.context.view_layer.update()

        # Copy pose from the infinigen camera rig to the SL root
        if cam_rig is not None:
            rig.set_pose(
                cam_rig.matrix_world.translation.copy(),
                cam_rig.matrix_world.to_3x3(),
            )
        else:
            rig.set_pose(
                camera.matrix_world.translation.copy(),
                camera.matrix_world.to_3x3(),
            )

        frame_tag = f"{frame_idx:04d}"

        # ── Record extrinsics ──────────────────────────────────
        extri = {
            "L": rig.get_camera_extrinsic(rig.left_cam).tolist(),
            "R": rig.get_camera_extrinsic(rig.right_cam).tolist(),
            "RGB": rig.get_camera_extrinsic(rig.rgb_cam).tolist(),
        }
        all_extrinsics.append(extri)

        # ═══════════════════════════════════════════════════════
        # 1. Render RGB (no projector, ambient light on)
        # ═══════════════════════════════════════════════════════
        rig.set_projector_visible(False)
        rig.set_scene_lights(True)
        rig.set_env_strength(orig_env_strength)

        _render_single(
            scene, rig.rgb_cam, sl_output, frame_tag, "RGB", sl_exr_depth,
            render_depth=True, render_normal=False,
        )

        # ═══════════════════════════════════════════════════════
        # 2. Render L/R IR images for each pattern (projector ON, scene lights OFF)
        # ═══════════════════════════════════════════════════════
        rig.set_projector_visible(True)
        rig.set_scene_lights(False)
        rig.set_env_strength(0)

        # L/R depth only once (pattern‑independent)
        for lr, cam_obj in [("L", rig.left_cam), ("R", rig.right_cam)]:
            # Render depth with white pattern (any pattern would work, depth is the same)
            if white_pattern_path:
                rig.set_pattern(white_pattern_path)
            _render_single(
                scene, cam_obj, sl_output, frame_tag, lr, sl_exr_depth,
                render_depth=True, render_normal=True, render_image=False,
            )

        # IR images per pattern
        for pat_path in pattern_paths:
            pat_name = Path(pat_path).stem
            rig.set_pattern(pat_path)
            for lr, cam_obj in [("L", rig.left_cam), ("R", rig.right_cam)]:
                _render_single(
                    scene, cam_obj, sl_output, frame_tag,
                    f"{pat_name}_{lr}", sl_exr_depth,
                    render_depth=False, render_normal=False, render_image=True,
                )

        # Restore lights for next iteration
        rig.set_scene_lights(True)
        rig.set_env_strength(orig_env_strength)

    # ── Save parameters.npz ────────────────────────────────────
    parameters = {
        "baseline": rig.baseline,
        "intrinsic": {
            "L": rig.get_camera_intrinsic().tolist(),
            "R": rig.get_camera_intrinsic().tolist(),
            "RGB": rig.get_rgb_intrinsic().tolist(),
            "Proj": rig.get_projector_intrinsic().tolist(),
        },
        "rel_R": {
            "L": np.eye(3).tolist(),
            "R": np.eye(3).tolist(),
        },
        "rel_T": {
            "L": rig.get_rel_translation("L").tolist(),
            "R": rig.get_rel_translation("R").tolist(),
        },
        "extrinsic": all_extrinsics,
        "patterns": [Path(p).stem for p in pattern_paths],
    }
    np.savez(sl_output / "parameters.npz", parameters)

    # Also save as JSON for easy inspection
    with open(sl_output / "parameters.json", "w") as f:
        json.dump(parameters, f, indent=2)

    # ── Copy patterns into output ──────────────────────────────
    if sl_pattern_dir:
        pattern_out = sl_output / "patterns"
        pattern_out.mkdir(exist_ok=True)
        import shutil
        for p in pattern_paths:
            shutil.copy2(p, pattern_out / Path(p).name)
        if white_pattern_path:
            shutil.copy2(white_pattern_path, pattern_out / "white.png")

    logger.info(f"Structured light rendering complete in {time.time() - tic:.1f}s")
    logger.info(f"Output: {sl_output}")


# ──────────────────────────────────────────────────────────────
# Single‑shot render helper
# ──────────────────────────────────────────────────────────────


def _render_single(
    scene,
    camera_obj,
    output_dir: Path,
    frame_tag: str,
    label: str,
    exr_depth: int = 16,
    render_depth=True,
    render_normal=False,
    render_image=True,
):
    """Render a single image from *camera_obj* and save outputs with a descriptive filename."""
    scene.camera = camera_obj

    # Ensure compositor is enabled
    scene.use_nodes = True
    tree = scene.node_tree
    # Remove old SL output nodes
    for node in list(tree.nodes):
        if node.name.startswith("SL_"):
            tree.nodes.remove(node)

    # Find or create render layers node
    render_layers = None
    for node in tree.nodes:
        if node.type == "R_LAYERS":
            render_layers = node
            break
    if render_layers is None:
        render_layers = tree.nodes.new(type="CompositorNodeRLayers")

    # Enable passes
    vl = scene.view_layers["ViewLayer"]
    vl.use_pass_z = True
    if render_normal:
        vl.use_pass_normal = True

    # EXR output
    exr_out = tree.nodes.new(type="CompositorNodeOutputFile")
    exr_out.name = "SL_ExrOutput"
    exr_out.format.file_format = "OPEN_EXR"
    exr_out.format.color_mode = "RGB"
    exr_out.format.color_depth = str(exr_depth)
    exr_out.base_path = str(output_dir)
    exr_out.file_slots.clear()

    if render_depth:
        exr_out.file_slots.new(f"{frame_tag}_{label}_Depth")
        tree.links.new(render_layers.outputs["Depth"], exr_out.inputs[f"{frame_tag}_{label}_Depth"])

    if render_normal:
        exr_out.file_slots.new(f"{frame_tag}_{label}_Normal")
        tree.links.new(render_layers.outputs["Normal"], exr_out.inputs[f"{frame_tag}_{label}_Normal"])

    if render_image:
        exr_out.file_slots.new(f"{frame_tag}_{label}_Image")
        tree.links.new(render_layers.outputs["Image"], exr_out.inputs[f"{frame_tag}_{label}_Image"])

    # Also PNG image
    if render_image:
        png_out = tree.nodes.new(type="CompositorNodeOutputFile")
        png_out.name = "SL_PngOutput"
        png_out.format.file_format = "PNG"
        png_out.format.color_mode = "RGB"
        png_out.base_path = str(output_dir)
        png_out.file_slots.clear()
        png_out.file_slots.new(f"{frame_tag}_{label}_Image")
        tree.links.new(render_layers.outputs["Image"], png_out.inputs[f"{frame_tag}_{label}_Image"])

    # Composite node (required)
    comp = None
    for node in tree.nodes:
        if node.type == "COMPOSITE":
            comp = node
            break
    if comp is None:
        comp = tree.nodes.new(type="CompositorNodeComposite")
    # Always link image to composite output
    source = render_layers.outputs["Image"]
    tree.links.new(source, comp.inputs["Image"])

    # Render single frame
    bpy.ops.render.render(write_still=False)

    # Cleanup SL nodes
    for node in list(tree.nodes):
        if node.name.startswith("SL_"):
            tree.nodes.remove(node)
