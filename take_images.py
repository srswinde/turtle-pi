#!/usr/bin/python3
import datetime
import asyncio
import json
import datetime
from shutil import copyfile
import os
import time
from pathlib import Path
import redis










async def idle_procs():

       
    latest = f'plots/turtle.jpg'
    remote_latest = '/mnt/turtle/latest/backyard.jpg'
    while 1:
        try:
            dtnow = datetime.datetime.now()
            now=int(time.time())
            remote_nowpic = Path('/mnt/turtle/imgs/backyard')
            remote_nowpic/= dtnow.strftime("%Y")
            remote_nowpic/= dtnow.strftime("%b")
            remote_nowpic/= dtnow.strftime("%d")
            remote_nowpic.mkdir(parents=True, exist_ok=True)
            remote_nowpic/=f'{now}.jpg'
            remote_nowpic = str(remote_nowpic)
            nowpic = Path('/mnt/turtle/imgs/backyard/latest.jpg')
            

            success = False
            resp = await asyncio.create_subprocess_exec(
                    "raspistill", '-e', 'jpg', '-q', '10', '-o', remote_nowpic
                    )
            success = True

            print(remote_nowpic)

            await asyncio.sleep(10)
            if success:
                
                copyfile(remote_nowpic, nowpic)
                rconn = redis.Redis( host="cabinet.local")
                data = {
                        "time": dtnow.ctime(),
                        "name": remote_nowpic,
                        "timestamp": dtnow.timestamp()
                        }

                rconn.publish("backyard_image", json.dumps(data))
                rconn.set("backyard_image", json.dumps(data))
        except Exception as error:
            print(f"Error:{error}")
            await asyncio.sleep(5.0)


#ioloop = tornado.ioloop.IOLoop.current()
#ioloop.add_callback(idle_procs)
#ioloop.start()

asyncio.run(idle_procs())





