from unit_gears_model.unit_gears.model_library import GearModelLibrary

#Load Model
gml = GearModelLibrary()
gml.load_path('unit_gears_model/models', verbose=False)
gear_models = next(gml.gear_models())
attrs1 = [attr for attr in dir(gml) if not attr.startswith('_')]
attrs2 = [attr for attr in dir(gear_models) if not attr.startswith('_')]
print(f'GearModelLibrary has attribute{attrs1}')
print(f'gear_models has attribute{attrs2}')

#retrieve all purse-seine records for gear_model
gear_models = gml.gear_models(gear='Purse seine')

#Different gear_model of gear_intensity Calculate
for gear_model in gear_models:
    name = gear_model.name
    param_unit = gear_model.param_unit
    scaling_unit = gear_model.scaling_unit
    unit_mean = gear_model.mean()[-1]
    gear = gear_model.gear_types
    print('=====')
    print(name + '\n' + str(param_unit) + '\n'+ str(scaling_unit) + '\n' + str(unit_mean) + '\n' + str(gear))
    print('=====')

