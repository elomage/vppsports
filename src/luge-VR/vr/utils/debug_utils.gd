class_name DebugUtils extends Node
## A class containing methods for easier debugging.
##
## A helper class containing methods for easier debugging.
##

static var enabled = true

## Visualizes curve by making a mesh out of it.
static func draw_curve3d(curve: Curve3D, parent: Node3D):
	var immesh = ImmediateMesh.new()

	var material = StandardMaterial3D.new()
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	material.albedo_color = Color.ORCHID

	immesh.surface_begin(Mesh.PRIMITIVE_LINE_STRIP, material)
	for point in curve.get_baked_points():
		immesh.surface_add_vertex(point)
	immesh.surface_end()

	var mesh = MeshInstance3D.new()
	mesh.mesh = immesh
	parent.add_child(mesh)
