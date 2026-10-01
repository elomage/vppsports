extends Node

@onready var hud = $Control
@onready var player = $World/Player/Sled

func _ready():
	player.speed_signal.connect(hud._on_speed_signal)
	player.angle_signal.connect(hud._on_rotation_signal)
	player.distance_signal.connect(hud._on_distance_signal)
	player.steering_signal.connect(hud._on_steering_signal)
