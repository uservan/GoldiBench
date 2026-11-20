"""Run inside Blender (blender -b scene.blend --python blender_state.py): prints `BENCH_STATE {json}`, the scene
properties the Blender GUI bench compares between START and the agent's saved .blend. Keys are '<tool>:<property>' for the
library's tools (ops_blender.OPS) and 'other:<property>' for everything else a user could change that alters the render
(the gate in app_envs.BlenderEnv: at L1 / L2 every changed key's tool must be allowed)."""
import bpy,json,math
s=bpy.context.scene;v=s.view_settings;st={}
def r(x,n=4):
    try:return round(float(x),n)
    except (TypeError,ValueError):return str(x)
st['exposure:ev']=r(v.exposure);st['gamma:gamma']=r(v.gamma)
st['white_balance:on']=bool(getattr(v,'use_white_balance',False))
st['white_balance:temperature']=r(getattr(v,'white_balance_temperature',6500));st['white_balance:tint']=r(getattr(v,'white_balance_tint',10))
st['other:view_transform']=v.view_transform;st['other:look']=v.look;st['other:display']=s.display_settings.display_device
w=s.world
if w and w.use_nodes:
    for n in w.node_tree.nodes:
        if n.type=='BACKGROUND':st['world:strength']=r(n.inputs['Strength'].default_value)
        elif n.type=='MAPPING':st['world:rotation']=[r(x) for x in n.inputs['Rotation'].default_value]
    st['other:world_nodes']=sorted(n.bl_idname for n in w.node_tree.nodes)
lights=[o for o in s.objects if o.type=='LIGHT']
st['sun:lights']=sorted((o.data.type,r(o.data.energy,3),[r(x,3) for x in o.rotation_euler]) for o in lights)
g=bpy.data.materials.get('ground')
if g and g.use_nodes:
    b=next((n for n in g.node_tree.nodes if n.type=='BSDF_PRINCIPLED'),None)
    if b:st['floor:base_color']=[r(x) for x in b.inputs['Base Color'].default_value];st['floor:roughness']=r(b.inputs['Roughness'].default_value)
haze=[o for o in s.objects if o.type=='MESH' and any(m and m.use_nodes and any(n.type=='PRINCIPLED_VOLUME' or n.type=='VOLUME_SCATTER' or n.type=='VOLUME_ABSORPTION' for n in m.node_tree.nodes) for m in o.data.materials)]
st['haze:volumes']=sorted((o.name.split('.')[0],[r(n.inputs['Density'].default_value) for m in o.data.materials if m and m.use_nodes for n in m.node_tree.nodes if 'Density' in n.inputs]) for o in haze)
model=[o for o in s.objects if o.get('bench_model')]
mats={m for o in model for m in o.data.materials if m}
st['other:model_materials']=sorted((m.name,len(m.node_tree.nodes) if m.use_nodes else 0,
    [r(i.default_value) for n in (m.node_tree.nodes if m.use_nodes else []) if n.type in ('BSDF_PRINCIPLED','HUE_SAT') for i in n.inputs if i.type=='VALUE']) for m in mats)
others=[o for o in s.objects if o.type=='MESH' and o not in haze]
st['other:objects']=sorted((o.name,[r(x,3) for x in o.matrix_world.translation],[r(x,3) for x in o.scale]) for o in others)
cam=s.camera
if cam:st['other:camera']=[[r(x,3) for x in cam.matrix_world.translation],[r(x,3) for x in cam.rotation_euler],r(cam.data.lens),
                           bool(cam.data.dof.use_dof),r(cam.data.dof.aperture_fstop)]
st['other:render']=[s.render.engine,s.render.resolution_x,s.render.resolution_y,s.render.resolution_percentage,
                    getattr(s.cycles,'samples',None),bool(s.use_nodes)]
print('BENCH_STATE '+json.dumps(st,sort_keys=True))
