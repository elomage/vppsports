class_name TrackDebug extends Node
## A helper class for visual track debugging.
##
## Stores functions to visualize features of the drack.

static func draw_data_curve(curve: Curve, centerline: Curve3D, parent: Node3D):
	var immesh = ImmediateMesh.new()
	
	var material = StandardMaterial3D.new()
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	material.vertex_color_use_as_albedo = true
	
	immesh.surface_begin(Mesh.PRIMITIVE_LINE_STRIP, material)
		
	var points = centerline.get_baked_points()
	print(points)
	var Sx = 0.0
	for i in range(1, points.size()):
		var position = points[i]
		var value = curve.sample(Sx / (centerline.get_baked_length()))
		
		Sx += position.distance_to(points[i - 1])
		position.y = value
		
		var c = Color(value, value, value)
		immesh.surface_set_color(c)
		immesh.surface_add_vertex(position)
	
	immesh.surface_end()

	var mesh = MeshInstance3D.new()
	mesh.mesh = immesh
	parent.add_child(mesh)
