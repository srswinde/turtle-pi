#!/usr/bin/env python
from io import BytesIO
import time
from time import sleep
from picamera import PiCamera
from PIL import Image
from pyindi.device import device
import asyncio
import time
import os
import glob
import redis
import datetime
import json
import asyncio

try:
    os.system('modprobe w1-gpio')
    os.system('modprobe w1-therm')
     
    base_dir = '/sys/bus/w1/devices/'
    device_folder = glob.glob(base_dir + '28*')[0]
    device_file = device_folder + '/w1_slave'
    TEMPSENSOR=True
except Exception as error:
    TEMPSENSOR=False

def read_temp_raw():
    f = open(device_file, 'r')
    lines = f.readlines()
    f.close()
    return lines
 
def read_temp():
    lines = read_temp_raw()
    while lines[0].strip()[-3:] != 'YES':
        time.sleep(0.2)
        lines = read_temp_raw()
    equals_pos = lines[1].find('t=')
    if equals_pos != -1:
        temp_string = lines[1][equals_pos+2:]
        temp_c = float(temp_string) / 1000.0
        temp_f = temp_c * 9.0 / 5.0 + 32.0
        return temp_c, temp_f

def update_temp(c, f):
    rconn = redis.Redis(host="192.168.0.148")
    dtnow = datetime.datetime.now()
    now = int(time.time())
    print(f"{dtnow.ctime()}\t{now}\t{f}")
    data = dict(
            time=dtnow.ctime(),
            temp=f,
            humid=0,
            timestamp=dtnow.timestamp()
            )
    rconn.publish("turtle_conditions", json.dumps(data))
    rconn.set("turtle_conditions", json.dumps(data))

class PiCam(device):
    camera = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.expose_queue = asyncio.Queue()
        self.temp_queue = asyncio.Queue()


    def ISGetProperties(self, device=None):
        if self.camera is None:
            self.camera = PiCamera()

    async def asyncInitProperties(self, device=None):
        
        
        vec = self.vectorFactory(
                "Switch",
                dict(
                    device=self.device,
                    name="exposure",
                    label="exposure",
                    state="Idle",
                    rule="OneOfMany",
                    perm="rw",
                    group="Main"
                    ),
                [
                    dict(
                        name="expose",
                        label="Expose",
                        state="Off"
                        )
                ]
                )

        self.IDDef(vec)
        blob = self.vectorFactory(
            "BLOB",
            dict(
                device=self.device,
                name="image",
                state="Idle",
                perm="rw",
                group="Main"

                ),
            [
               dict(
                    name="image",
                    label="Cassini Image",
                    format="jpg"
                )
            ]
        )
        self.IDDef(blob)

        temp = self.vectorFactory(
                "Number",
                dict ( 
                    device=self.device,
                    name="temperature",
                    state="Idle",
                    perm='ro',
                    label="Temperature",
                    group='Conditions',
                    ),
                [
                    dict(
                        name="house_side",
                        format="%f",
                        min=-1000,
                        max=1000,
                        step=0.1,
                        value=0,
                        label="House Side"
                        )
                    ]
                )
        self.IDDef(temp)

        temp_switch = self.vectorFactory(
                "Switch",
                dict(
                    device=self.device,
                    name="gettemp",
                    label="Get Temperature",
                    state="Idle",
                    rule="OneOfMany",
                    perm="rw",
                    group="Conditions"
                    ),
                [
                    dict(
                        name="gettemp",
                        label="Get Temp",
                        state="Off"
                        )
                ]
                )
        self.IDDef(temp_switch)

        time = self.vectorFactory(
                "Number",
                dict ( 
                    device=self.device,
                    name="last_image_time",
                    state="Idle",
                    perm='ro',
                    label="Last Image Time",
                    group='Main',
                    ),
                [
                    dict(
                        name="time",
                        format="%i",
                        min=0,
                        max=100000000,
                        step=1,
                        value=0,
                        label="Time"
                        )
                    ]
                )
        self.IDDef(time)
       

        self.exp_task = asyncio.create_task(self.expose_loop())
        self.temp_task = asyncio.create_task(self.get_temp_loop())

    @device.NewVectorProperty("exposure")
    def take_exposure(self, device, name, states, names):
        self.expose_queue.put_nowait(True)


    @device.NewVectorProperty("gettemp")
    def gettemp(self, device, name, states, names):
        self.temp_queue.put_nowait(True)

    async def get_temp_loop(self):
        loop = asyncio.get_running_loop()
        while self.running:
            rq = await self.temp_queue.get()
            c, f = await loop.run_in_executor(None, read_temp)
            temp = self.IUFind("temperature")
            temp['house_side'].value = f
            self.IDMessage(f"Getting temperature {c}c {f}f")
            self.IDSet(temp)

            await loop.run_in_executor(None, update_temp, c, f)

    async def expose_loop(self):
        self.running = True
        exp_button = self.IUFind("exposure")

        while self.running:
            new_image = await self.expose_queue.get()
            self.IDMessage(f"new image {new_image}")
            
            exp_button.state = "Busy"
            exp_button['expose'].value = "On"
            self.IDSet(exp_button)

            loop = asyncio.get_running_loop()
            try:
                imdata = await loop.run_in_executor(None, self.expose)
                lt = self.IUFind("last_image_time")
                now = int(time.time())
                lt['time'].value = int(time.time())

                self.IDSet(lt)
                self.IDMessage(now)
            except Exception as error:
                imdata = None
                self.IDMessage(f"Error taking exposure {error}")

            self.IDMessage("Image taken")

            exp_button.state = "Idle"
            exp_button['expose'].value = "Off"
            self.IDSet(exp_button)

            if imdata is not None:
                blob=self.IUFind("image")
                blob['image'].value = imdata
                self.IDSetBLOB(blob)

    def expose(self):

        # Create the in-memory stream
        self.IDMessage("enter expose")
        stream = BytesIO()
        self.camera.capture(stream, format='jpeg')
        stream.seek(0)

        return stream.read()

    @device.repeat(15000)
    async def idletime(self):
        loop = asyncio.get_running_loop()
        self.expose_queue.put_nowait(True)
        self.temp_queue.put_nowait(True)
            






async def main():
    p = PiCam()
    await p.astart()

asyncio.run(main())
