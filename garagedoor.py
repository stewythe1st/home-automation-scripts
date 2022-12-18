#!/usr/bin/python3

import paho.mqtt.client as mqtt
import time
import json
import os
import RPi.GPIO as gpio
from threading import Timer
import setproctitle

SENSOR_PIN = 12
OPENER_PIN = 26

# https://stackoverflow.com/a/48741004
class RepeatTimer(Timer):
    def run(self):
        while not self.finished.wait(self.interval):
            self.function(*self.args, **self.kwargs)

class GarageDoor:
    def __init__(self, client, name = "Garage Door"):
        self.client = client 
        self.state = False
        self.last_state = False
        self.debouncedState = False
        self.name = name
        self.timeLastChanged = time.time_ns()
    
    def read(self):
        self.state = gpio.input(SENSOR_PIN)
        # Fancy logic to ensure that the state is stable before reporting it as changed
        if self.state != self.last_state:
            self.timeLastChanged = time.time()
        if (time.time_ns() - self.timeLastChanged) > 1500000000: # nanoseconds
            if self.debouncedState != self.state:
                self.debouncedState = self.state
                self.report()
        self.last_state = self.state
        
    def trigger(self):
        # Just trigger the relay, could be open or close
        gpio.output(OPENER_PIN, gpio.HIGH)
        time.sleep(0.100)
        gpio.output(OPENER_PIN, gpio.LOW)        
          
    def register(self):
        name_normalized = self.name.lower().replace(" ", "_")
        print("Registering %s with Home Assistant..." % name_normalized)
        topic = "homeassistant/binary_sensor/%s/config" % name_normalized
        data = {
            "name": self.name, 
            "device_class": "garage_door",
            "state_topic": "homeassistant/garage_door/%s" % name_normalized,
            "value_template": "{{ value_json.state }}"
        }
        try:
            self.client.publish(topic, json.dumps(data), retain=True)
        except:
            pass
        return
        
    def report(self):
        # For a garage door in home assistant, "on" means open, "off" means closed
        # For this sensor, low means closed, high means open
        name_normalized = self.name.lower().replace(" ", "_")
        #print("%s: %s = %s" % \
        #    (name_normalized, self.debouncedState, "open" if self.debouncedState else "closed"))
        topic = "homeassistant/garage_door/%s" % name_normalized
        data = {
            "state": "ON" if self.debouncedState else "OFF"
        }
        try:
            self.client.publish(topic, json.dumps(data))
        except:
            pass
        return

    def on_message(self, client, userdata, msg):
        if msg.topic == "homeassistant/register":
            self.register()
        else:
            message_name = msg.topic.replace("homeassistant/garage_door/", "")
            name_normalized = self.name.lower().replace(" ", "_")
            if message_name == name_normalized:
                data = json.loads(msg.payload)
                if "command" in data:
                    if data["command"].lower() == "on":
                        print("Trigger!")
                        self.trigger()

def main():
    setproctitle.setproctitle('garagedoor')
    # Must be in this order: create client, define callbacks, connect, 
    # subscribe, start loop or proceed to do other things
    client = mqtt.Client("mqtt_garden_%u" % os.getpid())
    garage_door = GarageDoor(client)
    client.on_message = garage_door.on_message
    client.connect("192.168.1.9", 1883)
    client.subscribe("homeassistant/register")
    client.subscribe("homeassistant/garage_door/#")
    client.loop_start()
    gpio.setmode(gpio.BCM)
    gpio.setup(SENSOR_PIN, gpio.IN, pull_up_down=gpio.PUD_UP)
    gpio.setup(OPENER_PIN, gpio.OUT)
    gpio.output(OPENER_PIN, gpio.LOW)
    garage_door.register()
    # Use the repeating timer to send the reports every 15 seconds
    timer = RepeatTimer(15, garage_door.report)
    timer.daemon = True
    timer.start()
    # Take readings as often as possible
    garage_door.read()
    garage_door.report()
    while(1):
        garage_door.read()
        time.sleep(0.05)

if __name__ == "__main__":
    main()
    