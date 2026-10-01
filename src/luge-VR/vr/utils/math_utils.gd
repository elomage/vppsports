class_name MathUtils extends Node
## A class containing math functions. 
##
## A helper class for implementing mathematical concepts.
##

## Returns a list of linear interpolation values instead of a single value.
## Number of elements is passed to parameter [param elements].
static func lerp_list(from: float, to: float, elements: int) -> PackedFloat32Array:
	var result = PackedFloat32Array()
	result.resize(elements)
	
	for i in range(elements):
		result[i] = lerpf(from ,to, float(i)/elements)
	return result

## Quadratic Bezier curve implementation.[br]
## Source: [url]https://docs.godotengine.org/en/stable/tutorials/math/beziers_and_curves.html#quadratic-bezier[/url]
static func quadratic_bezier(p0: Vector2, p1: Vector2, p2: Vector2, t: float) -> Vector3:
	var q0 = p0.lerp(p1, t)
	var q1 = p1.lerp(p2, t)
	var result = q0.lerp(q1, t)
	return Vector3(result[0], result[1], 0.0) 

## Cubic Bezier curve implementation.[br]
## Source: [url]https://docs.godotengine.org/en/stable/tutorials/math/beziers_and_curves.html#cubic-bezier[/url]
static func cubic_bezier(p0: Vector2, p1: Vector2, p2: Vector2, p3: Vector2, t: float) -> Vector3:
	var q0 = p0.lerp(p1, t)
	var q1 = p1.lerp(p2, t)
	var q2 = p2.lerp(p3, t)
	
	var r0 = q0.lerp(q1, t)
	var r1 = q1.lerp(q2, t)
	
	var result = r0.lerp(r1, t)
	return Vector3(result[0], result[1], 0.0)
