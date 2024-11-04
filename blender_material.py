import bpy

# mat = bpy.data.materials.new(name = "FullColorMat")
# mat.use_nodes = True
#initialize defaultMat node group
def Full_color_texture(mat, albedo_texture_file, tactile_texture_file):
    defaultmat = mat.node_tree
    # Clean node tree
    for node in defaultmat.nodes:
        defaultmat.nodes.remove(node)
        
    # Initialize nodes
    material_output = defaultmat.nodes.new("ShaderNodeOutputMaterial")
    material_output.name = "Material Output"
    material_output.is_active_output = True
    
    # Image Texture for Albedo
    image_texture = defaultmat.nodes.new("ShaderNodeTexImage")
    image_texture.name = "Image Texture"
    image_texture.extension = 'REPEAT'
    image_texture.interpolation = 'Linear'
    image_texture.image = bpy.data.images.load(albedo_texture_file)
    
    # Principled BSDF
    principled_bsdf = defaultmat.nodes.new("ShaderNodeBsdfPrincipled")
    principled_bsdf.name = "Principled BSDF"
    principled_bsdf.inputs['Roughness'].default_value = 0.5
    
    # Normal Map Setup - Updated for Blender 4.0+
    normal_map = defaultmat.nodes.new("ShaderNodeNormalMap")
    normal_map.name = "Normal Map"
    normal_map.space = 'TANGENT'
    # In Blender 4.0+, strength is handled differently
    normal_map.inputs['Strength'].default_value = 1.0
    
    # Tactile Image Texture (Normal Map)
    tactile_image = defaultmat.nodes.new("ShaderNodeTexImage")
    tactile_image.name = "Tactile Image"
    tactile_image.extension = 'REPEAT'
    tactile_image.interpolation = 'Linear'
    
    if tactile_texture_file is not None:
        tactile_image.image = bpy.data.images.load(tactile_texture_file)
        # Important change for Blender 4.0+: Explicitly set to Non-Color
        tactile_image.image.colorspace_settings.name = 'Non-Color'
        # Add UV Map node for proper tangent space handling
        uv_map = defaultmat.nodes.new('ShaderNodeUVMap')
        uv_map.uv_map = "UVMap"  # Use your UV map name here
    else:
        normal_map.inputs['Strength'].default_value = 0.0
    
    # Node locations
    material_output.location = (430, 300)
    image_texture.location = (-480, 300)
    principled_bsdf.location = (150, 300)
    normal_map.location = (-80, -225)
    tactile_image.location = (-488, -130)
    if tactile_texture_file is not None:
        uv_map.location = (-680, -130)
    
    # Create links
    defaultmat.links.new(image_texture.outputs['Color'], principled_bsdf.inputs['Base Color'])
    defaultmat.links.new(principled_bsdf.outputs['BSDF'], material_output.inputs['Surface'])
    defaultmat.links.new(normal_map.outputs['Normal'], principled_bsdf.inputs['Normal'])
    defaultmat.links.new(tactile_image.outputs['Color'], normal_map.inputs['Color'])
    
    if tactile_texture_file is not None:
        defaultmat.links.new(uv_map.outputs['UV'], tactile_image.inputs['Vector'])
    
    return defaultmat

# defaultmat = defaultmat_node_group()

# mat = bpy.data.materials.new(name = "normal_render")
# mat.use_nodes = True
#initialize normal_render node group
def normal_render_texture(mat, tactile_texture_file):

	normal_render = mat.node_tree
	#start with a clean node tree
	for node in normal_render.nodes:
		normal_render.nodes.remove(node)
	#initialize normal_render nodes
	
    #node Normal Map
	normal_map = normal_render.nodes.new("ShaderNodeNormalMap")
	normal_map.name = "Normal Map"
	normal_map.space = 'TANGENT'
	normal_map.uv_map = ""
	#Strength
	normal_map.inputs[0].default_value = 1.0
	
	#node Image Texture.001
	image_texture_001 = normal_render.nodes.new("ShaderNodeTexImage")
	image_texture_001.label = "tactile"
	image_texture_001.name = "Image Texture.001"
	image_texture_001.extension = 'REPEAT'
	image_texture_001.image_user.frame_current = 1
	image_texture_001.image_user.frame_duration = 1
	image_texture_001.image_user.frame_offset = -1
	image_texture_001.image_user.frame_start = 1
	image_texture_001.image_user.tile = 0
	image_texture_001.image_user.use_auto_refresh = False
	image_texture_001.image_user.use_cyclic = False
	image_texture_001.interpolation = 'Linear'
	image_texture_001.projection = 'FLAT'
	image_texture_001.projection_blend = 0.0
	if tactile_texture_file is not None:
		image_texture_001.image = bpy.data.images.load(tactile_texture_file)
		image_texture_001.image.colorspace_settings.name = 'Non-Color'
	else:
		normal_map.inputs[0].default_value = 0.0
	#Vector
	image_texture_001.inputs[0].default_value = (0.0, 0.0, 0.0)
	
	#node Gamma
	gamma = normal_render.nodes.new("ShaderNodeGamma")
	gamma.name = "Gamma"
	#Gamma
	gamma.inputs[1].default_value = 2.200000047683716
	
	#node Material Output
	material_output = normal_render.nodes.new("ShaderNodeOutputMaterial")
	material_output.name = "Material Output"
	material_output.is_active_output = True
	material_output.target = 'ALL'
	#Displacement
	material_output.inputs[2].default_value = (0.0, 0.0, 0.0)
	#Thickness
	material_output.inputs[3].default_value = 0.0
	
	#node Vector Transform
	vector_transform = normal_render.nodes.new("ShaderNodeVectorTransform")
	vector_transform.name = "Vector Transform"
	vector_transform.convert_from = 'WORLD'
	vector_transform.convert_to = 'CAMERA'
	vector_transform.vector_type = 'NORMAL'
	
	#node Mapping
	mapping = normal_render.nodes.new("ShaderNodeMapping")
	mapping.name = "Mapping"
	mapping.vector_type = 'TEXTURE'
	#Location
	mapping.inputs[1].default_value = (-1.0, -1.0, 1.0)
	#Rotation
	mapping.inputs[2].default_value = (0.0, 0.0, 0.0)
	#Scale
	mapping.inputs[3].default_value = (2.0, 2.0, -2.0)
	
	
	
	
	#Set locations
	image_texture_001.location = (-658.6141967773438, 372.88507080078125)
	gamma.location = (420.29791259765625, 367.7361145019531)
	material_output.location = (624.8310546875, 362.5605773925781)
	vector_transform.location = (-104.94386291503906, 330.3135070800781)
	mapping.location = (145.96263122558594, 450.2762451171875)
	normal_map.location = (-337.320068359375, 296.4747619628906)
	
	#Set dimensions
	image_texture_001.width, image_texture_001.height = 240.0, 100.0
	gamma.width, gamma.height = 140.0, 100.0
	material_output.width, material_output.height = 140.0, 100.0
	vector_transform.width, vector_transform.height = 140.0, 100.0
	mapping.width, mapping.height = 140.0, 100.0
	normal_map.width, normal_map.height = 150.0, 100.0
	
	#initialize normal_render links
	#image_texture_001.Color -> normal_map.Color
	normal_render.links.new(image_texture_001.outputs[0], normal_map.inputs[1])
	#normal_map.Normal -> vector_transform.Vector
	normal_render.links.new(normal_map.outputs[0], vector_transform.inputs[0])
	#gamma.Color -> material_output.Surface
	normal_render.links.new(gamma.outputs[0], material_output.inputs[0])
	#vector_transform.Vector -> mapping.Vector
	normal_render.links.new(vector_transform.outputs[0], mapping.inputs[0])
	#mapping.Vector -> gamma.Color
	normal_render.links.new(mapping.outputs[0], gamma.inputs[0])
	return normal_render

