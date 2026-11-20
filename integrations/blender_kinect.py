"""Kinect Hoard live armature and animation recorder. Run in Blender's Text Editor or --python."""
import json
import os
import queue
import sys
import threading
import time
import urllib.request

import bpy
from mathutils import Matrix, Vector

bl_info = {"name": "Kinect Hoard", "author": "Luissalet", "version": (1, 0, 0),
           "blender": (3, 6, 0), "location": "View3D > Sidebar > Kinect", "category": "Animation"}
PAIRS = [("SpineBase", "SpineMid"), ("SpineMid", "SpineShoulder"), ("SpineShoulder", "Neck"), ("Neck", "Head")]
for side in ("Left", "Right"):
    PAIRS += [("SpineShoulder", "Shoulder" + side), ("Shoulder" + side, "Elbow" + side),
              ("Elbow" + side, "Wrist" + side), ("Wrist" + side, "Hand" + side),
              ("Hand" + side, "HandTip" + side), ("Wrist" + side, "Thumb" + side),
              ("SpineBase", "Hip" + side), ("Hip" + side, "Knee" + side),
              ("Knee" + side, "Ankle" + side), ("Ankle" + side, "Foot" + side)]
frames = queue.Queue(maxsize=1)
stop = threading.Event()
status = "Esperando articulaciones"
ENDPOINT = os.environ.get("KINECT_HOARD_URL", "http://127.0.0.1:64321").rstrip("/") + "/api/camera/frame"
last_sequence = None
record_start = None
record_frame = 1


def point(joint):
    # Kinect X-right/Y-up/Z-forward -> Blender X-right/Y-away/Z-up, metres.
    return Vector((joint["X"], joint["Z"], joint["Y"]))


def apply_frame(frame, record=False):
    global status, record_start, record_frame
    bodies = [body for body in frame.get("bodies") or [] if body.get("Joints")]
    if not bodies:
        status = "Sin cuerpo visible"
        return 0
    for body in bodies:
        joints = {joint["Name"]: joint for joint in body["Joints"] if joint["TrackingState"] > 0}
        name = "Kinect_" + str(body["TrackingId"])
        obj = bpy.data.objects.get(name)
        if obj is None:
            obj = bpy.data.objects.new(name, bpy.data.armatures.new(name))
            bpy.context.collection.objects.link(obj)
            bpy.context.view_layer.objects.active = obj
            obj.select_set(True)
            bpy.ops.object.mode_set(mode="EDIT")
            for start, end in PAIRS:
                if start not in joints or end not in joints:
                    continue
                head, tail = point(joints[start]), point(joints[end])
                if (tail - head).length < .001:
                    continue
                bone = obj.data.edit_bones.new(end)
                bone.head, bone.tail = head, tail
            bpy.ops.object.mode_set(mode="OBJECT")
            obj.show_in_front = True
            obj.data.display_type = "STICK"
        for start, end in PAIRS:
            if start not in joints or end not in joints or end not in obj.pose.bones:
                continue
            head, tail = point(joints[start]), point(joints[end])
            direction = tail - head
            if direction.length < .001:
                continue
            bone = obj.pose.bones[end]
            bone.rotation_mode = "QUATERNION"
            bone.matrix = Matrix.LocRotScale(head, direction.to_track_quat("Y", "Z"), Vector((1, direction.length / bone.bone.length, 1)))
            if record:
                for path in ("location", "rotation_quaternion", "scale"):
                    bone.keyframe_insert(data_path=path, frame=record_frame, group=end)
    if record:
        bpy.context.scene.frame_end = max(bpy.context.scene.frame_end, record_frame)
        record_frame += 1
    status = f"{len(bodies)} cuerpo(s) · fotograma {frame.get('sequence', '?')} · coordenadas en metros"
    return len(bodies)


def receive():
    global status
    while not stop.is_set():
        try:
            with urllib.request.urlopen(ENDPOINT, timeout=1) as response:
                frame = json.load(response)
            if frames.full():
                try: frames.get_nowait()
                except queue.Empty: pass
            frames.put_nowait(frame)
        except Exception as exc:
            status = "Esperando Hoard / Esqueleto: " + str(exc)[:120]
        stop.wait(.04)


def tick():
    global last_sequence
    if stop.is_set():
        return None
    try:
        frame = frames.get_nowait()
    except queue.Empty:
        return .04
    if frame.get("sequence") != last_sequence:
        apply_frame(frame, bpy.context.scene.kinect_hoard_record)
        last_sequence = frame.get("sequence")
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == "VIEW_3D": area.tag_redraw()
    return .04


class KINECT_OT_connect(bpy.types.Operator):
    bl_idname = "kinect_hoard.connect"
    bl_label = "Conectar / reconectar"
    def execute(self, context):
        if not bpy.app.timers.is_registered(tick):
            stop.clear()
            threading.Thread(target=receive, daemon=True).start()
            bpy.app.timers.register(tick)
        return {"FINISHED"}


class KINECT_OT_stop(bpy.types.Operator):
    bl_idname = "kinect_hoard.stop"
    bl_label = "Detener seguimiento"
    def execute(self, context):
        stop.set()
        return {"FINISHED"}


class KINECT_PT_panel(bpy.types.Panel):
    bl_label = "Kinect Hoard"
    bl_idname = "KINECT_PT_hoard"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Kinect"
    def draw(self, context):
        for line in status.split(" · "): self.layout.label(text=line)
        if status == "Sin cuerpo visible": self.layout.label(text="Colócate delante de la One")
        self.layout.prop(context.scene, "kinect_hoard_record", text="Grabar movimiento")
        self.layout.operator("kinect_hoard.connect")
        self.layout.operator("kinect_hoard.stop")


def register():
    for cls in (KINECT_OT_connect, KINECT_OT_stop, KINECT_PT_panel): bpy.utils.register_class(cls)
    bpy.types.Scene.kinect_hoard_record = bpy.props.BoolProperty(name="Grabar movimiento", default=False)
    if not bpy.app.background:
        # Only this launched process; do not save or overwrite the user's preferences.
        bpy.context.preferences.view.show_splash = False
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == "VIEW_3D": area.spaces.active.show_region_ui = True
        bpy.app.timers.register(show_panel, first_interval=.5)


def show_panel():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == "VIEW_3D":
                for region in area.regions:
                    if region.type == "UI" and hasattr(region, "active_panel_category") and not region.is_property_readonly("active_panel_category"):
                        region.active_panel_category = "Kinect"
    return None


def unregister():
    stop.set()
    if bpy.app.timers.is_registered(tick): bpy.app.timers.unregister(tick)
    for cls in reversed((KINECT_OT_connect, KINECT_OT_stop, KINECT_PT_panel)): bpy.utils.unregister_class(cls)
    del bpy.types.Scene.kinect_hoard_record


if __name__ == "__main__":
    register()
    if "--" in sys.argv:
        args = sys.argv[sys.argv.index("--") + 1:]
        if args and args[0] == "test":
            with open(args[1], encoding="utf-8") as source: fixture = json.load(source)
            for frame in fixture: assert apply_frame(frame, True) > 0
            bpy.context.view_layer.update()
            obj = next(obj for obj in bpy.data.objects if obj.type == "ARMATURE" and obj.name.startswith("Kinect_"))
            assert obj.animation_data and obj.animation_data.action
            head = obj.pose.bones["Head"].head
            expected = Vector(fixture[-1]["expected_head_blender"])
            assert (head - expected).length < 1e-4, (head, expected)
            with open(args[2], "w", encoding="utf-8") as output: json.dump({"bones": len(obj.pose.bones), "frames": len(fixture), "animation": True, "position_error": (head - expected).length}, output)
    else:
        bpy.ops.kinect_hoard.connect()
