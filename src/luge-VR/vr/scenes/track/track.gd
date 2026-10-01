extends Node3D

@onready var track_data = $TrackData
@onready var centerline = $Centerline
@onready var track = $StaticBody3D
@onready var mesh_instance = $StaticBody3D/MeshInstance3D
@onready var collision_shape = $StaticBody3D/CollisionShape3D
@onready var surroundings = $Surroundings
@onready var path = $Centerline/PathFollow3D

# Updates child node parameters.
func _set_config(config: ConfigFile):
	track.physics_material_override.friction = config.get_value("track", "friction", track.physics_material_override.friction)
	centerline.curve.bake_interval = config.get_value("track", "bake_interval", centerline.curve.bake_interval)
	track_data.cross_section_points = config.get_value("track", "cross_section_points", track_data.cross_section_points)

func _ready() -> void:
	var cfg = FileUtils.load_config("res://config.cfg")
	_set_config(cfg)
	
	# NOTE: Expects already sorted data.
	var data = FileUtils.parse_json(cfg.get_value("track", "segments_path"))
	
	track_data.fill(data)
	centerline.create_centerline(track_data)
	
	if centerline.curve.point_count > 0:
		mesh_instance.create_mesh(centerline.curve, track_data)
		collision_shape.shape = mesh_instance.mesh.create_trimesh_shape()
		
		var material = StandardMaterial3D.new()
		material.albedo_color = Color(0.815, 0.906, 0.973, 1.0)
		material.roughness = 0.95
		material.metallic = 0.05
		
		mesh_instance.set_surface_override_material(0, material)
		
		# Add surrounding objects along the track.
		surroundings.multimesh.instance_count = centerline.curve.point_count
		for i in range(surroundings.multimesh.instance_count):
			path.progress_ratio = float(i) / surroundings.multimesh.instance_count
			surroundings.multimesh.set_instance_transform(i, path.global_transform)
