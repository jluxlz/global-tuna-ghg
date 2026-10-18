from unit_gears_model.unit_gears.model_library import GearModelLibrary, MODELS_DIR

gml = GearModelLibrary(verbose=False)
gml.load_path(MODELS_DIR)

# Print All effort_model of gear_types (View the type actually included) 
print("===== effort_model of gear_types =====")
for effort in gml.effort_models():
    print(f"Model Name: {effort.name}")
    print(f"gear_types: {effort.gear_types}\n")  # Focus on the keys and values here

# Print All gear_model of gear_types
print("\n===== gear_model of gear_types =====")
for gear in gml.gear_models():
    print(f"Model Name: {gear.name}")
    print(f"gear_types: {gear.gear_types}\n")