class_name TrackData extends Node
## A data structure for storing track generation parameters.
##
## A data structure that stores and processes track generation parameters. 
## Expects parameters to be passed as a [Dictionary] containing following key-value pairs:
## [br][br]
##  • [b]length[/b] — track length starting from the start line.[br]
##  • [b]width[/b] — track width.[br]
##  • [b]default_height[/b] — base height of side walls.[br]
##  • [b]segments[/b]:[br]
##  ----• [b]slopes[/b]:[br]
##  --------• [b]Sx_entrance[/b] — distance from the start line.[br]
##  --------• [b]length[/b] — slope segment length.[br]
##  --------• [b]slope[/b] — slope percentage.[br]
##  ----• [b]curves[/b]:[br]
##  --------• [b]Sx_entrance[/b] — distance from the start line.[br]
##  --------• [b]length[/b] — curve segment length.[br]
##  --------• [b]radius[/b] — minimum curvature radius.[br]
##  --------• [b]turn[/b] — 1 for left, -1 for right.[br]
##  --------• [b]angle[/b] — angle of the curve (degrees).[br]
##  ---• [b]heights[/b]:[br]
##  --------• [b]Sx_entrance[/b] — position of the height point (distance from the start line).[br]
##  --------• [b]height[/b] — height value.[br]
##

## All types of track segments.
enum SegmentTypes {STRAIGHT, CURVE}
## All turn directions of track segments.
enum Directions {FORWARD, LEFT, RIGHT=-1}

## A data structure for storing track segments.
##
## A data structure that represents a segment of a track. 
class Segment:
	## Type of the segment.
	var type: SegmentTypes = SegmentTypes.STRAIGHT
	## Start of the segment (distance from the start line of the track).
	var Sx_start: float = 0.0
	## End of the segment (distance from the start line of the track).
	var Sx_end: float = 0.0
	## Length of the segment.
	var length: float = 0.0
	## Minimum radius of a curvature, if the segment is a curve.
	var R_min: float = 0.0
	## Turn direction of the segment. Matters, if the segment is a curve.
	var turn: Directions = Directions.FORWARD
	## Deflection angle (radians).
	var angle: float = 0.0

## Point count for the cross section of the track. 
## The more points, the smoother are the side walls of the track.
@export var cross_section_points: int = 32

## Total length of the construction. Includes length before the start line.
var length: float = 0.0
## Width of the track.
var width: float  = 0.0
## Base height of side walls in meters.
var default_height: float = 0.0
## Position of the starting point of the construction (distance from the start line).[br]
## The construction may start before the start line.
var start_at: float = 0.0
## Radius of track fillets in meters.
var R_fillet: float = 0.15
## Length of safety barrier for curved walls in meters.
var length_barrier: float = 0.5
## Radius of safety barrier's for curved walls circular arc in meters.
var R_barrier: float = 1
## Slope along the track.
var slope: Curve = Curve.new()
## Side wall height along the track.[br]
## [b]Note:[/b] Height only changes for the outer wall of the curved track segment.
var height: Curve = Curve.new()
## Curvature along the track (without direction).
var curvature: Curve = Curve.new()
## Segments of the track.
var segments: Array[Segment] = []

## Normalizes position to value in range from 0 to 1.
## Necessary to get correct [member curvature], [member height] and [member slope] values.
func normalize(at: float) -> float:
	return (at - start_at) / length

# Fills segment array with provided and processed data of track segments.
func _create_segments(data: Dictionary):
	var curves = data["curves"]
	var Sx = start_at
	
	for c in curves:
		var Sx_curr = c.Sx_entrance
		if Sx != Sx_curr:
			var seg_straight = Segment.new()
			seg_straight.type = SegmentTypes.STRAIGHT
			seg_straight.Sx_start = Sx
			seg_straight.Sx_end = Sx_curr
			seg_straight.length = abs(Sx - Sx_curr)
			segments.append(seg_straight)
		
		Sx = c.Sx_entrance
		var seg = Segment.new()
		seg.type = SegmentTypes.CURVE
		seg.Sx_start = Sx
		seg.Sx_end = Sx + c.length
		seg.length = c.length
		seg.R_min = c.radius
		seg.turn = c.turn
		seg.angle = deg_to_rad(c.angle)
		
		segments.push_back(seg)
		Sx = seg.Sx_end

# Fills height curve with provided height points.
func _create_height(heights: Array):
	var h_values = heights.map(func(x): return x["height"])
	
	height.bake_resolution = 1000
	height.max_value = h_values.max()
	height.min_value = h_values.min()
	
	height.add_point(Vector2(0.0, 0.0))
	for h in heights:
		height.add_point(Vector2(
			normalize(h.Sx_entrance), h.height
		))
	height.add_point(Vector2(1.0, 0.0))
	
	height.bake()

# Fills slope curve with points created from provided slope segments.
func _create_slope(slopes: Array):
	slope.bake_resolution = 1000
	slope.min_value = -1.0
	slope.max_value = 1.0
	
	slope.add_point(Vector2(0.0, 0.0))
	
	for s in slopes:
		slope.add_point(Vector2(
			normalize(s.Sx_entrance), 
			s.slope/100
		))
		slope.add_point(Vector2(
			normalize(s.Sx_entrance + s.length), 
			s.slope/100
		))
	
	slope.add_point(Vector2(1.0, 0.0))
	slope.bake()
	
## Fills data structure with track parameters.
func fill(data: Dictionary):
	start_at = min(
		data["segments"]["slopes"][0].Sx_entrance, 
		data["segments"]["curves"][0].Sx_entrance,
		0
	)
	length = data["length"] - start_at
	width = data["width"]
	default_height = data["default_height"]
	R_fillet = data["fillet_radius"]
	length_barrier = data["length_curve_barrier"]
	R_barrier = data["radius_curve_barrier"]
	
	_create_segments(data["segments"])
	_create_slope(data["segments"]["slopes"])
	_create_height(data["segments"]["heights"])
	
	curvature.bake_resolution = 1000
	curvature.min_value = 0.0
	curvature.max_value = 1.0
	curvature.add_point(Vector2(0.0, 0.0))
	curvature.add_point(Vector2(1.0, 0.0))

## Get [member height] value at specific position on the track.
func get_height(at: float) -> float:
	return height.sample(at)

## Get [member slope] value at specific position on the track.
func get_slope(at: float) -> float:
	return slope.sample(at)
	
## Get [member curvature] value at specific position on the track.
func get_curvature(at: float) -> float:
	return curvature.sample(at)

## Get a track segment that the specific position on the track belongs to.
func get_segment(at: float) -> Segment: 
	for s in segments:
		if at >= s.Sx_start and at <= s.Sx_end:
			return s
	return Segment.new()

## Get cross section points at specific position on the track.
func get_cross_section_points(at: float) -> PackedVector3Array:
	var points = PackedVector3Array()
	points.resize(cross_section_points)
	
	var half_width = width * 0.5
	# Middle of the shape - centerline point.
	var middlepoint = floori(cross_section_points * 0.5)
	# NOTE: Assuming fillet is 90 degrees and leaving 3 points for the top points of the wall.
	var fillet_angles = MathUtils.lerp_list(deg_to_rad(-90), deg_to_rad(0), middlepoint-3)
	var fillet_center = Vector2(half_width, R_fillet)
	
	var straight_wall = PackedVector3Array()
	
	for angle in fillet_angles:
		var p = Vector3(
			fillet_center.x + R_fillet * cos(angle),
			fillet_center.y + R_fillet * sin(angle),
			0.0
		) 
		straight_wall.append(p)
	
	straight_wall.append(Vector3(half_width + R_fillet, default_height, 0.0))
	straight_wall.append(Vector3(half_width + R_fillet + length_barrier * 0.5, default_height, 0.0))
	straight_wall.append(Vector3(half_width + R_fillet + length_barrier, default_height, 0.0))
	straight_wall.reverse()
	
	var segment = get_segment(at)
	# If it is a curve.
	if segment.type == SegmentTypes.CURVE:
		var c_norm = get_curvature(normalize(at)) / (1/segment.R_min)
		var banking_start = clamp(c_norm*0.5, 0.0, 0.5)
		var h = get_height(normalize(at))
		#var t_b = abs((inverse_lerp(segment.Sx_start, segment.Sx_end, at)*2)-1)
		
		# NOTE: This definitely needs serious update.
		var p0 = Vector2(half_width, 0.0)
		var p1 = Vector2(half_width + 0.5 - banking_start, h * 0.25)
		var p2 = Vector2(half_width + 1 + banking_start, h * 0.8)
		var p3 = Vector2(half_width + 0.25 + banking_start, h)
		
		var curve_points = []
		for i in range(middlepoint):
			var t = i / float(middlepoint - 1)
			curve_points.append(MathUtils.cubic_bezier(p0, p1, p2, p3, t))
		
		if segment.turn < 0:
			for i in range(middlepoint):
				points[i] = Vector3(-curve_points[middlepoint-1-i].x, curve_points[middlepoint-1-i].y, curve_points[middlepoint-1-i].z)
				points[cross_section_points-1-i] = straight_wall[i]
		else:
			for i in range(middlepoint):
				points[i] = Vector3(-straight_wall[i].x, straight_wall[i].y, straight_wall[i].z)
				points[cross_section_points-1-i] = curve_points[middlepoint-1-i]
	# If it is a straight trajectory.
	else:
		for i in range(middlepoint):
			points[i] = Vector3(-straight_wall[i].x, straight_wall[i].y, straight_wall[i].z)
			points[cross_section_points-1-i] = straight_wall[i]
	
	return points
