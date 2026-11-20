"""Runs INSIDE Blender 4.5 (blender -b ... -P blender_bench.py -- <mode> <json>), started by ops_blender.py.

  build   {"model": gltf, "hdri": hdr, "rotation": deg, "out": .blend}
          start scene: the model scaled to 1 unit high on a grey ground plane, the HDRI as world light (Mapping node
          rotation about Z), a 50 mm camera framing the model from 12 deg above (horizon in frame); Cycles CPU, 64 samples + OIDN, seed 0,
          AgX view transform. Saved as the start .blend.
  render  {"blend": .blend, "steps": [[tool, {field: value}], ...], "out": png, "size": px, "save": .blend or null}
          applies the program through the same properties a user edits in the GUI (Color Management, World, a Sun
          light, a Hue/Saturation/Value node before every model material's Base Color, Principled roughness, camera
          depth of field, compositor Glare) and renders. With "save", the edited scene is written there (the edit state).
"""
import json,math,sys
import bpy
from mathutils import Vector

def args():
    a=sys.argv[sys.argv.index('--')+1:];return a[0],json.loads(a[1])

def build(c):
    bpy.ops.wm.read_factory_settings(use_empty=True);s=bpy.context.scene
    bpy.ops.import_scene.gltf(filepath=c['model'])
    objs=[o for o in s.objects if o.type=='MESH']
    for o in objs:o['bench_model']=True
    lo=Vector((min(min((o.matrix_world@Vector(b))[i] for b in o.bound_box) for o in objs) for i in range(3)))
    hi=Vector((max(max((o.matrix_world@Vector(b))[i] for b in o.bound_box) for o in objs) for i in range(3)))
    root=bpy.data.objects.new('bench_root',None);s.collection.objects.link(root)
    for o in s.objects:
        if o.parent is None and o is not root:o.parent=root
    k=1.0/max(hi.z-lo.z,1e-6);root.scale=(k,k,k);root.location=(-(lo.x+hi.x)/2*k,-(lo.y+hi.y)/2*k,-lo.z*k)
    bpy.ops.mesh.primitive_plane_add(size=40);g=bpy.context.object;g.name='bench_ground'
    m=bpy.data.materials.new('ground');m.use_nodes=True;b=m.node_tree.nodes['Principled BSDF']
    b.inputs['Base Color'].default_value=(0.35,0.35,0.35,1);b.inputs['Roughness'].default_value=0.8;g.data.materials.append(m)
    w=bpy.data.worlds.new('World');s.world=w;w.use_nodes=True;nt=w.node_tree
    env=nt.nodes.new('ShaderNodeTexEnvironment');env.image=bpy.data.images.load(c['hdri'])
    mp=nt.nodes.new('ShaderNodeMapping');mp.name='bench_world_mapping';tc=nt.nodes.new('ShaderNodeTexCoord')
    mp.inputs['Rotation'].default_value=(0,0,math.radians(c['rotation']))
    nt.links.new(tc.outputs['Generated'],mp.inputs['Vector']);nt.links.new(mp.outputs['Vector'],env.inputs['Vector'])
    nt.links.new(env.outputs['Color'],nt.nodes['Background'].inputs['Color'])
    size=(hi-lo)*k;half=math.atan(18/50)   # 50 mm lens on a 36 mm sensor: half the horizontal field of view
    r=c.get('fill',0.85)*max(size.x,size.y,1.0)/math.tan(half)   # 0.85: the model fills about 60 % of the frame height; smaller = closer
    cam=bpy.data.objects.new('bench_camera',bpy.data.cameras.new('cam'));s.collection.objects.link(cam);s.camera=cam
    cam.data.lens=50;el=math.radians(12);az=math.radians(35)   # low enough that the HDRI horizon is in frame
    target=Vector((0,0,0.45));cam.location=target+Vector((math.cos(el)*math.sin(az),-math.cos(el)*math.cos(az),math.sin(el)))*r
    cam.rotation_euler=(target-cam.location).to_track_quat('-Z','Y').to_euler()
    cam.data.dof.focus_distance=(target-cam.location).length
    s.render.engine='CYCLES';s.cycles.device='CPU';s.cycles.samples=64;s.cycles.use_denoising=True;s.cycles.seed=0
    s.render.resolution_x,s.render.resolution_y=1024,768;s.view_settings.view_transform='AgX'
    bpy.ops.wm.save_as_mainfile(filepath=c['out'])

def hsv_node(mat):
    nt=mat.node_tree;n=nt.nodes.get('bench_hsv')
    if n:return n
    b=next((x for x in nt.nodes if x.type=='BSDF_PRINCIPLED'),None)
    if b is None:return None
    n=nt.nodes.new('ShaderNodeHueSaturation');n.name='bench_hsv';sock=b.inputs['Base Color']
    if sock.is_linked:src=sock.links[0].from_socket;nt.links.new(src,n.inputs['Color'])
    else:n.inputs['Color'].default_value=sock.default_value
    nt.links.new(n.outputs['Color'],sock);return n

def apply(s,steps):
    v=s.view_settings;mats={m for o in s.objects if o.get('bench_model') for m in o.data.materials if m and m.use_nodes}
    for tool,f in steps:
        if tool=='exposure':v.exposure=f.get('ev',0.0)
        elif tool=='gamma':v.gamma=f.get('gamma',1.0)
        elif tool=='white_balance':
            v.use_white_balance=True;v.white_balance_temperature=f.get('temperature',6500.0);v.white_balance_tint=f.get('tint',10.0)
        elif tool=='world':
            s.world.node_tree.nodes['Background'].inputs['Strength'].default_value=f.get('strength',1.0)
            mp=s.world.node_tree.nodes['bench_world_mapping'];rz=mp.inputs['Rotation'].default_value[2]
            mp.inputs['Rotation'].default_value=(0,0,rz+math.radians(f.get('rotation',0.0)))
        elif tool=='sun':
            o=bpy.data.objects.new('bench_sun',bpy.data.lights.new('sun','SUN'));s.collection.objects.link(o)
            o.data.energy=f.get('strength',0.0);o.data.angle=math.radians(2)
            o.rotation_euler=(math.radians(90-f.get('elevation',45.0)),0,math.radians(f.get('azimuth',0.0)))
        elif tool=='material':
            for m in mats:
                n=hsv_node(m)
                if n is None:continue
                n.inputs['Hue'].default_value=f.get('hue',0.5);n.inputs['Saturation'].default_value=f.get('saturation',1.0)
                n.inputs['Value'].default_value=f.get('value',1.0)
        elif tool=='gloss':
            for m in mats:
                for b in (x for x in m.node_tree.nodes if x.type=='BSDF_PRINCIPLED'):
                    r=b.inputs['Roughness']
                    if r.is_linked:   # textured roughness: offset it with a Math node
                        mt=m.node_tree;add=mt.nodes.new('ShaderNodeMath');add.operation='ADD';add.use_clamp=True
                        mt.links.new(r.links[0].from_socket,add.inputs[0]);add.inputs[1].default_value=-f.get('amount',0.0);mt.links.new(add.outputs[0],r)
                    else:r.default_value=min(1,max(0,r.default_value-f.get('amount',0.0)))
        elif tool=='dof':
            a=f.get('amount',0.0);s.camera.data.dof.use_dof=a>0;s.camera.data.dof.aperture_fstop=max(0.25/a,0.05) if a>0 else 128
        elif tool=='floor':   # the ground plane's material (a large part of the frame)
            g=next(x for x in bpy.data.materials['ground'].node_tree.nodes if x.type=='BSDF_PRINCIPLED')
            import colorsys
            r_,g_,b_=colorsys.hsv_to_rgb(f.get('hue',0.0),f.get('saturation',0.0),f.get('value',0.35))
            g.inputs['Base Color'].default_value=(r_,g_,b_,1);g.inputs['Roughness'].default_value=f.get('roughness',0.8)
        elif tool=='haze':   # a fog sphere centred on the camera (Principled Volume); an unbounded World volume swallowed the
            # HDRI light, and the first fog box (12x12x6) showed its faces as hard lines on the floor and in glossy reflections
            # (review 2026-11-02 01:25). Radius 30 covers the whole 40x40 ground, so no fog edge is on screen and every ray to
            # the background crosses the same thickness of fog.
            bpy.ops.mesh.primitive_uv_sphere_add(segments=64,ring_count=32,radius=30,location=s.camera.location)
            o=bpy.context.object;o.name='bench_haze'
            m=bpy.data.materials.new('haze');m.use_nodes=True;nt=m.node_tree;nt.nodes.remove(nt.nodes['Principled BSDF'])
            vol=nt.nodes.new('ShaderNodeVolumePrincipled');vol.inputs['Density'].default_value=f.get('density',0.0)
            nt.links.new(vol.outputs['Volume'],nt.nodes['Material Output'].inputs['Volume']);o.data.materials.append(m)
        elif tool=='glare':
            s.use_nodes=True;nt=s.node_tree;rl=nt.nodes.get('Render Layers') or nt.nodes.new('CompositorNodeRLayers')
            out=nt.nodes.get('Composite') or nt.nodes.new('CompositorNodeComposite')
            g=nt.nodes.new('CompositorNodeGlare');g.glare_type='FOG_GLOW';g.inputs['Threshold'].default_value=f.get('threshold',1.0)
            g.inputs['Strength'].default_value=f.get('strength',0.0)
            nt.links.new(rl.outputs['Image'],g.inputs['Image']);nt.links.new(g.outputs['Image'],out.inputs['Image'])
        else:raise ValueError(tool)

def render(c):
    bpy.ops.wm.open_mainfile(filepath=c['blend']);s=bpy.context.scene;apply(s,c['steps'])
    k=c['size']/max(s.render.resolution_x,s.render.resolution_y);s.render.resolution_percentage=round(100*k)
    s.render.image_settings.file_format='PNG';s.render.filepath=c['out'];bpy.ops.render.render(write_still=True)
    if c.get('save'):bpy.ops.wm.save_as_mainfile(filepath=c['save'],copy=True)

mode,c=args();{'build':build,'render':render}[mode](c)
