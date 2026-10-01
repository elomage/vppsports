extends CanvasLayer

# To rotate the round measure scale arrow.
const START_ANGLE = deg_to_rad(-130)
const END_ANGLE = deg_to_rad(130)

@onready var speed = $Speed
@onready var speed_num = $Speed/Speed
@onready var speed_mark = $Speed/Line
func _on_speed_signal(value):
	speed_num.text = str(value)
	
	var value_range = speed.max_value - speed.min_value
	var t = clampf(
		float(value - speed.min_value) / value_range,
		0.0, 1.0
	)
	speed_mark.rotation = lerp(START_ANGLE, END_ANGLE, t)

@onready var angle = $Rotation
@onready var rotation_num = $Rotation/Angle
@onready var rotation_mark = $Rotation/Line
func _on_rotation_signal(value):
	rotation_num.text = str(roundf(value))
	
	var value_range = angle.max_value - angle.min_value
	var t = clampf(
		float(value - angle.min_value) / value_range,
		0.0, 1.0
	)
	rotation_mark.rotation = lerp(START_ANGLE, END_ANGLE, t)

@onready var distance_num = $Speed/Distance/Distance
func _on_distance_signal(dist):
	distance_num.text = str(dist)

@onready var steer_right = $Steering/RightBar
@onready var steer_left = $Steering/LeftBar
func _on_steering_signal(value):
	steer_left.value = 0.0
	steer_right.value = 0.0
	
	if value < 0.0:
		steer_left.value = abs(value)  
	else:
		steer_right.value = abs(value)
