
# Installation

## Installation Options & Supported Platforms

You can install Infinigen either as a Python Module or a Blender Python script:
- Python Module (default option)
  - Cannot open a Blender UI - headless execution only
  - Installs the `infinigen` package into the user's own python environment
  - Installs `bpy` as a [pip dependency](https://docs.blender.org/api/current/info_advanced_blender_as_bpy.html)
- Blender Python script 
  - Can use Infinigen interactively in the Blender UI
  - Installs the `infinigen` package into *Blender's* built-in python interpreter, not the user's python.
  - Uses a standard standalone installation of Blender.

In either case, certain features have limited support on some operating systems, as shown below:

| Feature Set        | Needed to generate...    | Linux x86_64 | Mac x86_64   | Mac ARM      | Windows x86_64 | Windows WSL2 x86_64 |
|--------------------|--------------------------|--------------|--------------|--------------|----------------|---------------------|
| Minimal Install.   | objects & materials      | yes          | yes          | yes          | experimental   | experimental        |
| Terrain (CPU)      | full scenes              | yes          | yes          | yes          | no             | experimental        |
| Terrain (CUDA)     | speedup, faster videos   | yes          | no           | no           | no             | experimental        |
| OpenGL Annotations | *additional* training GT | yes          | yes          | yes          | no             | experimental        |
| Fluid Simulation   | fires, simulated water   | yes          | experimental | experimental | no             | experimental        |

Users wishing to run our [Hello World Demo](./HelloWorld.md) or generate full scenes should install Infinigen as a Python Module and enable the Terrain (CPU) setting.
Users wishing to use Infinigen assets in the Blender UI, or develop their own assets, can install Infinigen as a Blender-Python script with the "Minimal Install" setting.

See our [Configuring Infinigen](./ConfiguringInfinigen.md), [Ground Truth Annotations ](./GroundTruthAnnotations.md), and [Fluid Simulation](./GeneratingFluidSimulations.md) docs for more information about the various optional features. Note: fields marked "experimental" are feasible but untested and undocumented. Fields marked "no" are largely _possible_ but not yet implemented.

Once you have chosen your configuration, proceed to the relevant section below for instructions.

## Installing Infinigen as a Python Module

### Dependencies

Please install anaconda or miniconda. Platform-specific instructions can be found [here](https://docs.conda.io/projects/miniconda/en/latest/miniconda-install.html)

Then, install the following dependencies using the method of your choice. Examples are shown for Ubuntu, Mac ARM and Mac x86.
```bash
# on Ubuntu / Debian / WSL / etc
sudo apt-get install wget cmake g++ libgles2-mesa-dev libglew-dev libglfw3-dev libglm-dev zlib1g-dev

# on an Mac ARM (M1/M2/...)
arch -arm64 brew install wget cmake llvm open-mpi libomp glm glew zlib

# on  Mac x86_64 (Intel)
brew install wget cmake llvm open-mpi libomp glm glew zlib

# on Conda. Useful when you don't have sudo permissions
conda install conda-forge::gxx=11.4.0 mesalib glew glm menpo::glfw3
export C_INCLUDE_PATH=$CONDA_PREFIX/include:$C_INCLUDE_PATH
export CPLUS_INCLUDE_PATH=$CONDA_PREFIX/include:$CPLUS_INCLUDE_PATH
export LIBRARY_PATH=$CONDA_PREFIX/lib:$LIBRARY_PATH
export LD_LIBRARY_PATH=$CONDA_PREFIX/lib:$LD_LIBRARY_PATH
```

### Installation

First, download the repo and set up a conda environment (you may need to [install conda](https://conda.io/projects/conda/en/latest/user-guide/install/index.html))
```bash
git clone https://github.com/princeton-vl/infinigen.git
cd infinigen
conda create --name infinigen python=3.11
conda activate infinigen
```

Then, install the infinigen package using one of the options below:

```bash
# Minimal install (No terrain or opengl GT, ok for Infinigen-Indoors or single-object generation) 
INFINIGEN_MINIMAL_INSTALL=True pip install -e .

# Full install (Terrain & OpenGL-GT enabled, needed for Infinigen-Nature HelloWorld)
pip install -e ".[terrain,vis]"

# Installation for simulation assets
pip install -e ".[sim]"

# Developer install (includes pytest, ruff, other recommended dev tools)
pip install -e ".[dev,terrain,vis]"
pre-commit install
```

:exclamation: If you encounter any issues with the above, please add `-vv > logs.txt 2>&1` to the end of your command and run again, then provide the resulting logs.txt file as an attachment when making a Github Issue.

### Additional setup for exact structured-light reproduction

If you plan to run the structured-light pipeline, the base `pip install -e .` environment is not fully self-contained by itself.

Pattern images are shipped in-repo under `data/patterns/`, but the projector implementation has two modes:

- Recommended / exact reproduction: install the external Blender addon [`Ocupe/Projectors`](https://github.com/Ocupe/Projectors)
- Fallback mode: if the addon is missing, Infinigen falls back to a manual spot-light projector and logs a warning

The fallback path keeps the pipeline runnable, but it is not the exact same projector implementation and outputs may differ. For parity across machines, install the addon explicitly.

Recommended headless install:

```bash
bash scripts/install/install_projectors_addon.sh
```

The install script:

- clones `https://github.com/Ocupe/Projectors.git` into `~/.cache/deepsl-setup/Projectors`
- links it into the active Blender addons directory as `Projectors`
- works without opening the Blender GUI when the addons path can be resolved automatically or is passed through `BLENDER_ADDONS=/path/to/addons`

If you prefer Blender's own install flow instead, install the ZIP from the Blender GUI, or use a `bpy` script on headless machines:

```python
import bpy
bpy.app.binary_path = "<blender_bin_path>"
bpy.ops.preferences.addon_install(filepath="<path_to_downloaded_zip>")
```

After installation, make sure the addon appears as `Projectors` in Blender. The structured-light renderer will attempt to enable module names such as `Projectors` automatically at runtime.

## Installing Infinigen as a Blender Python script

On Linux / Mac / WSL:
```bash
git clone https://github.com/princeton-vl/infinigen.git
cd infinigen
conda create --name infinigen python=3.11
conda activate infinigen 
```

Then, install using one of the options below:
```bash

# Minimal installation (recommended setting for use in the Blender UI)
INFINIGEN_MINIMAL_INSTALL=True bash scripts/install/interactive_blender.sh

# Normal install
bash scripts/install/interactive_blender.sh

# Enable OpenGL GT
INFINIGEN_INSTALL_CUSTOMGT=True bash scripts/install/interactive_blender.sh
```

:exclamation: If you encounter any issues with the above, please add ` > logs.txt 2>&1` to the end of your command and run again, then provide the resulting logs.txt file as an attachment when making a Github Issue.

For exact structured-light reproduction on this installation path, also run:

```bash
bash scripts/install/install_projectors_addon.sh
```

Without that addon, structured-light rendering falls back to a manual spot-light projector, which is useful for debugging but is not the intended parity path across machines.

Once complete, you can use the helper script `python -m infinigen.launch_blender` to launch a blender UI, which will find and execute the `blender` executable in your `infinigen/blender` or `infinigen/Blender.app` folder.

:warning: If you installed Infinigen as a Blender-Python script and encounter encounter example commands of the form `python -m <MODULEPATH> <ARGUMENTS>` in our documentation, you should instead run `python -m infinigen.launch_blender -m <MODULEPATH> -- <ARGUMENTS>` to launch them using your standalone blender installation rather than the system python..

## Using Infinigen in a Docker Container

**Docker on Linux**

```
git clone https://github.com/princeton-vl/infinigen.git
cd infinigen
make docker-build
make docker-setup
make docker-run
```
To enable CUDA compilation, use `make docker-build-cuda` instead of `make docker-build`

To run without GPU passthrough use `make docker-run-no-gpu`
To run without OpenGL ground truth use `docker-run-no-opengl` 
To run without either, use `docker-run-no-gpu-opengl` 

Note: `make docker-setup` can be skipped if not using OpenGL.

Use `exit` to exit the container and `docker exec -it infinigen bash` to re-enter the container as needed. Remember to `conda activate infinigen` before running scenes.

**Docker on Windows**

Install [WSL2](https://infinigen.org/docs/installation/intro#setup-for-windows) and [Docker Desktop](https://www.docker.com/products/docker-desktop/), with "Use the WSL 2 based engine..." enabled in settings. Keep the Docker Desktop application open while running containers. Then follow instructions as above.
