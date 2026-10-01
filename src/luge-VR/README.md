# Luge simulation

This project is an attempt to construct a simulation that can be used to simulate the sport of luge.
The attempt still has significant room for improvement, but the baseline functionality has been laid down.

Simulation was made using Godot game engine, more specifically, version 4.5.

## Contents:

* `blender_src ` - blender source files
* `luge_vr` - virtual environment for luge
  * `data` - configuration data
  * `scenes` - Godot scenes and their scripts
  * `utils` - debug utilities and file/math functions

 ## Known limitations

Obviously, for any sort of physics simulation to behave correctly, it is also important to model the track geometry properly.

Here lies one known limitation: cross-section generation. Although it works well for straight walls, curved wall generation may produce overly steep curves when more extreme parameters are present.

## Inspiration

In case someone gets inspired and wants to read a few interesting articles on the topic, here are some:
* https://www.sciencedirect.com/science/article/pii/S259012302601385X - a quite recent article discussing track generation from control points.
* https://arxiv.org/abs/1212.4901 - interesting research on luge track safety.

### Authors
This repository originally created by [Ārija Kalniņa](https://github.com/ArijaK)
