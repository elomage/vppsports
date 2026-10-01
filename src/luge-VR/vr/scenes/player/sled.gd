class_name Sled extends RigidBody3D
## A class for luge sleds. 
##
## A class for luge sled implementation.
## Contains steering logic, parameter processing and physics.
##

## Sled speed notifications.
signal speed_signal(speed: int)
## Sled banking angle notifications.
signal angle_signal(angle: float)
## Distance ridden notifications.
signal distance_signal(distance: int)
## Steering input notifications.
signal steering_signal(strength: float)

## Maximum steering force.
## Steering force is calculated, multiplying this value with steering input (0-1).
@export var max_steer_force: float = 100
## Whether to load steering input from a file.
@export var preload_input: bool = false
## Whether to save last ride parameters.
@export var save_ride_params: bool = false
## Where to write parameters of the last ride.
## [b]Note:[/b] All previous content of the file will be deleted
@export var ride_params_path: String = "res://data/results.txt"
## Where to store trajectory of the last ride.[br]
## [b]Note:[/b] All previous content of the file will be deleted!
@export var ride_trajectory_path: String = "res://data/results_traj.txt"

## Timestamp of the start of the ride in seconds.
var start_time: float = 0
## Distance ridden up to this moment.
var distance: float = 0
## Preloaded steering input values.
var steering_values: Array = []
## Preloaded steering input timestamps.
var stamps = PackedFloat32Array()
## Maximum possible preloaded steering input.
var steering_max: float = 0
## Minimum possible preloaded steering input.
var steering_min: float = 0
## Parameters of the ride to store into a file.
var ride_params: Array = []
## Trajectory of the ride to store into a file.
var ride_trajectory_poses: Array = []

func _notification(what: int) -> void:
	if what == NOTIFICATION_EXIT_TREE or what == NOTIFICATION_WM_CLOSE_REQUEST:
		if save_ride_params:
			FileUtils.save_csv(ride_params, ride_params_path)
			FileUtils.save_csv(ride_trajectory_poses, ride_trajectory_path)

## Finds steering input at specific time from preloaded input values.
## Uses linear interpolation between closest input values.
func find_steer_input(time: float) -> float:
	for i in range(stamps.size() - 1):
		var before = stamps[i]
		var after = stamps[i + 1]

		if time >= before and time <= after:
			var t = (time - before) / (after - before)
			return lerp(steering_values[i], steering_values[i+1], t)

	return steering_values[-1]

# Loads steering input from file into class variables.
func _parse_steering_txt(file: FileAccess):
	while not file.eof_reached():
		var line = file.get_line().strip_edges()
		if line.is_empty():
			break
		
		var parts = line.split(",")
		var value = int(parts[0].split("=")[1].strip_edges())
		var time = int(parts[1].split("=")[1].strip_edges())
		
		steering_values.append(value)
		stamps.append(time/ 1000000.0)
	
	steering_max = steering_values.max()
	steering_min = steering_values.min()

# For initial acceleration.
func _apply_pushing():	
	if Input.is_action_just_pressed("ui_accept"):
		linear_velocity.z += -10.0

# Steering input processing.
# NOTE: Steering is inverse, that is, one uses left input to steer right and vice versa.
func _apply_steering() -> float:
	var steer_input = Input.get_axis("steer_left", "steer_right") + Input.get_axis("steer_right_second", "steer_left_second")
	var steer_force = steer_input * max_steer_force

	# Linear movement (sideways).
	var forward = linear_velocity.normalized()
	var side = Vector3.UP.cross(forward).normalized()
	apply_central_force(side * steer_force)
	# Rotational movement.
	apply_torque(Vector3.UP * steer_force * 0.15)
	
	return steer_input

func _physics_process(delta: float) -> void:
	var current_time = (Time.get_ticks_msec() / 1000.0) - start_time
	# Because forward is -Z and speed is m/s (so * -3.6).
	var speed = linear_velocity.length() * 3.6
	distance += linear_velocity.length() * delta
	
	var steer_input = 0.0
	if not preload_input:
		steer_input = _apply_steering()
	else:
		var input = find_steer_input(current_time)
		# Normalizes in range from 0 to 1. Later is normalized in range from -1 to 1.
		var input_norm = (input - steering_min) / float(steering_max - steering_min)
		steer_input = ((input_norm * 2.0) - 1.0) * max_steer_force
	
	_apply_pushing()
	
	# Saving ride parameters.
	if save_ride_params:
		ride_params.append([
			current_time,
			steer_input,
			speed,
			rotation_degrees.x,
			distance
		])
		ride_trajectory_poses.append([
			transform.basis.x.x, transform.basis.y.x, transform.basis.z.x, transform.origin.x,
			transform.basis.x.y, transform.basis.y.y, transform.basis.z.x, transform.origin.y,
			transform.basis.x.z, transform.basis.y.z, transform.basis.z.x, transform.origin.z,
			0.0, 0.0, 0.0, 1.0
		])
	
	steering_signal.emit(steer_input)
	speed_signal.emit(int(speed))
	angle_signal.emit(rotation_degrees.x)
	distance_signal.emit(int(distance))

# Updates node parameters.
func _set_config(config: ConfigFile):
	preload_input = config.get_value("player", "preload_input")
	max_steer_force = config.get_value("player", "max_steer_force")
	mass = config.get_value("player", "mass")
	save_ride_params = config.get_value("player", "save_ride_params")
	ride_params_path = config.get_value("player", "ride_params_path")
	ride_trajectory_path = config.get_value("player", "ride_trajectory_path")	

func _ready() -> void:
	var cfg = FileUtils.load_config("res://config.cfg")
	_set_config(cfg)
	
	if save_ride_params:
		ride_params.append(["timestamp","steering_input","speed","rotation","distance"])
	
	if preload_input:
		## NOTE: Currently expects already sorted data
		var input_path = cfg.get_value("player", "input_path")
		var input_file = FileAccess.open(input_path, FileAccess.READ)
		
		if input_file == null:
			push_error("Cannot open file " + input_path)
			return
		
		_parse_steering_txt(input_file)
		input_file.close()
	
	start_time = Time.get_ticks_msec() / 1000.0

func _integrate_forces(state: PhysicsDirectBodyState3D) -> void:
	# Makes collisions less dramatic
	for i in range(state.get_contact_count()):
		var normal = state.get_contact_local_normal(i)
		var impulse = state.get_contact_impulse(i)
		
		apply_central_impulse(-normal * impulse.length() * 0.2)
		   
		var tangent = state.linear_velocity.slide(normal)
		apply_central_force(-tangent * 0.2)
