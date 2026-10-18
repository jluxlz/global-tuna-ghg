from unit_gears_model.unit_gears.model_library import GearModelLibrary, MODELS_DIR

gml = GearModelLibrary(verbose=False)
gml.load_path(MODELS_DIR)

# 打印所有 effort_model 的 gear_types（查看实际包含的类型）
print("===== effort_model 的 gear_types =====")
for effort in gml.effort_models():
    print(f"模型名称: {effort.name}")
    print(f"gear_types: {effort.gear_types}\n")  # 重点看这里的键和值

# 打印所有 gear_model 的 gear_types
print("\n===== gear_model 的 gear_types =====")
for gear in gml.gear_models():
    print(f"模型名称: {gear.name}")
    print(f"gear_types: {gear.gear_types}\n")