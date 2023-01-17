#!/usr/bin/python3

import paho.mqtt.client as mqtt
import time
import json
import os
from enum import Enum
import RPi.GPIO as gpio
from threading import Timer
import setproctitle

SENSOR_PIN = 12
OPENER_PIN = 26

class State(Enum):
    UNKNOWN = 0
    CLOSED = 1
    OPEN = 2
    CLOSING = 3
    OPENING = 4

# https://stackoverflow.com/a/48741004
class RepeatTimer(Timer):
    def run(self):
        while not self.finished.wait(self.interval):
            self.function(*self.args, **self.kwargs)

class GarageDoor:
    def __init__(self, client, name = "Garage Door"):
        self.client = client 
        self.sensor_state = False
        self.last_sensor_state = False
        self.debounced_sensor_state = False
        self.name = name
        self.timeLastChanged = time.time_ns()
        self.state = State.UNKNOWN
    
    def read(self):
        self.sensor_state = gpio.input(SENSOR_PIN)
        # Fancy logic to ensure that the state is stable before reporting it as changed
        if self.sensor_state != self.last_sensor_state:
            self.timeLastChanged = time.time()
        if (time.time_ns() - self.timeLastChanged) > 2000000000: # nanoseconds
            if self.debounced_sensor_state != self.sensor_state:
                self.debounced_sensor_state = self.sensor_state
                self.report()
        self.last_sensor_state = self.sensor_state
        
    def trigger(self):
        # Just trigger the relay, could be open or close
        gpio.output(OPENER_PIN, gpio.HIGH)
        time.sleep(0.100)
        gpio.output(OPENER_PIN, gpio.LOW)
        pass
          
    def register(self):
        name_normalized = self.name.lower().replace(" ", "_")
        print("Registering %s with Home Assistant..." % name_normalized)
        device = {
            "identifiers": name_normalized,
            "name": "Garage Door",
            "model": "Garage Door",
            "manufacturer": "",
        }
        topic = "homeassistant/cover/%s/config" % name_normalized
        data = {
            "name": self.name, 
            "device_class": "garage",
            "unique_id": "garagedoor",
            "command_topic": "homeassistant/garage_door/%s/command" % name_normalized,
            "state_topic": "homeassistant/garage_door/%s/state" % name_normalized,
            "device": device,
        }
        try:
            self.client.publish(topic, json.dumps(data), retain=True)
        except:
            pass
        return
        
    def report(self):
        # For this sensor, high means closed
        name_normalized = self.name.lower().replace(" ", "_")
        #print("%s: %s = %s" % \
        #    (name_normalized, self.debouncedState, "open" if self.debouncedState else "closed"))
        topic = "homeassistant/garage_door/%s/state" % name_normalized
        data = ""
        if not self.debounced_sensor_state and self.state != State.OPENING:
            self.state = State.CLOSED
        if self.debounced_sensor_state and self.state != State.CLOSING:
            self.state = State.OPEN
        # Determine string
        data = "unknown"
        if self.state == State.OPEN:
            data = "open"
        elif self.state == State.OPENING:
            data = "opening"
        elif self.state == State.CLOSED:
            data = "closed"
        elif self.state == State.CLOSING:
            data = "closing"
        try:
            print("Reporting: %s" % data)
            self.client.publish(topic, data)
        except:
            pass
        return

    def on_message(self, client, userdata, msg):
        if msg.topic == "homeassistant/register":
            self.register()
        else:
            name_normalized = self.name.lower().replace(" ", "_")
            if msg.topic == ("homeassistant/garage_door/%s/command" % name_normalized):
                data = msg.payload.decode()
                print("Received command: %s" % data)
                if data == "OPEN":
                    if not (self.state == State.OPEN or self.state == State.OPENING):
                        self.state = State.OPENING
                        self.trigger()
                elif data == "CLOSE":
                    if not (self.state == State.CLOSED or self.state == State.CLOSING):
                        self.state = State.CLOSING
                        self.trigger()
                elif data == "STOP":
                    if (self.state == State.OPENING or self.state == State.CLOSING):
                        self.state = State.OPEN
                        self.trigger()
                self.report()

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
    