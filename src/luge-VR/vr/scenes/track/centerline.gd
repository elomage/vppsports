extends Path3D

func create_centerline(track: TrackData):
	var direction = Vector3.FORWARD
	# Because -Z is forward.
	var point = Vector3(0.0, 0.0, -track.start_at)
	var slope = track.get_slope(track.normalize(track.start_at))
	
	curve.add_point(point)
	
	var Sx = 0.0
	for segment in track.segments:
		if segment.type == track.SegmentTypes.STRAIGHT:
			Sx = segment.Sx_end
			slope = track.get_slope(track.normalize(Sx))
			
			point += direction * segment.length
			point.y -= slope * segment.length
			
			curve.add_point(point)
		
		# NOTE: The most difficult part is understanding, how long is each clothoid.
		# Different methods could be used, if more parameters were kown.
		elif segment.type == track.SegmentTypes.CURVE:
			Sx = segment.Sx_start
			
			var curvature_max = (1 / segment.R_min) * segment.turn
			var L_clothoid = segment.length - (segment.angle / abs(curvature_max))
			var L_arc = segment.length - (2 * L_clothoid)
				
			var point_count_clothoid = floori(L_clothoid / curve.bake_interval)
			var point_count_arc = floori(L_arc / curve.bake_interval)
			
			## NOTE: Probably it is possible to refactor this.
			for i in range(point_count_clothoid):
				var curvature = lerp(0.0, curvature_max, float(i)/point_count_clothoid)
				track.curvature.add_point(Vector2(
					track.normalize(Sx), curvature
				))
				var angle_step = curvature * curve.bake_interval
				direction = direction.rotated(Vector3.UP, angle_step)
				
				point += direction * curve.bake_interval
				point.y -= slope * curve.bake_interval
				curve.add_point(point)
				
				Sx += curve.bake_interval
				slope = track.get_slope(track.normalize(Sx))
			
			for i in range(point_count_arc):
				var angle_step = curvature_max * curve.bake_interval
				direction = direction.rotated(Vector3.UP, angle_step)
				
				track.curvature.add_point(Vector2(
					track.normalize(Sx), curvature_max
				))
				
				point += direction * curve.bake_interval
				point.y -= slope * curve.bake_interval
				curve.add_point(point)
				
				Sx += curve.bake_interval
				slope = track.get_slope(track.normalize(Sx))
			
			for i in range(point_count_clothoid):
				var curvature = lerp(curvature_max, 0.0, float(i)/point_count_clothoid)
				track.curvature.add_point(Vector2(
					track.normalize(Sx), curvature
				))
				var angle_step = curvature * curve.bake_interval
				direction = direction.rotated(Vector3.UP, angle_step)
				
				point += direction * curve.bake_interval
				point.y -= slope * curve.bake_interval
				curve.add_point(point)
				
				Sx += curve.bake_interval
				slope = track.get_slope(track.normalize(Sx))
		
	track.curvature.bake()
