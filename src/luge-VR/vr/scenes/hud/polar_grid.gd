class_name PolarGrid extends Control
## A control used for visual represantation of data on a polar grid.
##
## A control used for visual represantation of data on a polar grid.
## Creates a round measuring scale (like a speedometer).
##

## Minimum value of the scale.
@export var min_value: int = 0
## Maximum value of the scale.
@export var max_value: int = 150
## How many units is each tick mark.
@export var units_per_tick: int = 5
## Every [member major_tick_every] tick mark is drawn as a major tick.
@export var tick_major_every: int = 5

## Start angle of the scale in radians.
const START_ANGLE = deg_to_rad(-220)
## End angle of the scale in radians.
const END_ANGLE = deg_to_rad(40)

func _draw() -> void:
	var center = size * 0.5
	var radius = min(size.x, size.y) * 0.5
	draw_circle(center, radius, Color.hex(0x1F1F1F96), true)
	
	var value_range = max_value - min_value
	
	# How far from centre marks should be.
	var radius_outer = radius - 2
	var radius_ticks = radius_outer - 10
	var radius_ticks_major = radius_outer - 20
	
	var tick_count = 1
	for value in range(min_value, max_value+1, units_per_tick):
		# Where the tick mark will be.
		var t = float(value - min_value) / value_range
		var angle = lerp(START_ANGLE, END_ANGLE, t)
		var direction = Vector2(cos(angle), sin(angle))
		
		var outer_point = center + direction * radius_outer
		var inner_point = center + direction * radius_ticks
		var thickness = 2
		
		if tick_count == tick_major_every or (tick_major_every != 0 and value == min_value):
			inner_point = center + direction * radius_ticks_major
			thickness = 4
			tick_count = 1
			
			# Numbers.
			var text_pos = center + (direction - Vector2(0.1, -0.05)) * (radius_ticks_major - 20)
			draw_string(get_theme_font("Open Sans SemiBold"), text_pos, str(value))
		else:
			tick_count += 1
		
		draw_line(inner_point, outer_point, Color.WHITE, thickness)
