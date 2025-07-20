import aspose.threed as a3d

scene = a3d.Scene.from_file("/home/xinhai/Documents/infinigen/infinigen/assets/static_assets/source/.usd/Microwave/7221.usd")
scene.save("Output.glb")