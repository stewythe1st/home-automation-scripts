import paho.mqtt.client as mqtt
import time
import json
import os
import RPi.GPIO as gpio
from threading import Timer

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
        self.name = name
        self.time = time.time()
        self.timing = False
        self.trigger_time = time.time()
    
    def read(self):
        self.state = gpio.input(SENSOR_PIN)
        # Fancy logic to ensure that the state is stable before reporting it as changed
        if self.timing:
            if self.state != self.last_state:
                # If state changed, reset timer 
                self.time = time.time()
            else:
                # If no state change, see if enough seconds have 
                # passed since last state change
                if (time.time() - self.time) > 3:
                    self.timing = False
                    self.report()
        else:
            # Start timer
            self.timing = True
            self.time = time.time()
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
            "icon": "mdi:garage-variant",
            "device_class": "garage_door",
            "state_topic": "homeassistant/garage_door/%s" % name_normalized,
            "value_template": "{{ value_json.state }}"
        }
        try:
            self.client.publish(topic, json.dumps(data))
        except:
            pass
        return
        
    def report(self):
        if self.timing:
            return
        # For a garage door in home assistant, "on" means open, "off" means closed
        # For this sensor, low means closed, high means open
        name_normalized = self.name.lower().replace(" ", "_")
        print("%s: %s = %s" % \
            (name_normalized, self.state, "open" if self.state else "closed"))
        topic = "homeassistant/garage_door/%s" % name_normalized
        data = {
            "state": "ON" if self.state else "OFF"
        }
        self.client.publish(topic, json.dumps(data))

    def on_message(self, client, userdata, msg):
        message_name = msg.topic.replace("homeassistant/garage_door/", "")
        name_normalized = self.name.lower().replace(" ", "_")
        if message_name == name_normalized:
            data = json.loads(msg.payload)
            if "command" in data:
                if data["command"].lower() == "on":
                    if (time.time() - self.trigger_time) > 5:
                        print("Trigger!")
                        self.trigger()

def main():
    # Must be in this order: create client, define callbacks, connect, 
    # subscribe, start loop or proceed to do other things
    client = mqtt.Client("mqtt_garden_%u" % os.getpid())
    garage_door = GarageDoor(client)
    client.on_message = garage_door.on_message
    client.connect("192.168.1.9", 1883)
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
        time.sleep(0.1)

if __name__ == "__main__":
    main()
    