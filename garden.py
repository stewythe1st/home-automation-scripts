import paho.mqtt.client as mqtt
import time
import json
import os
from threading import Timer
import RPi.GPIO as gpio
import Adafruit_ADS1x15 as ads

WET_VOLTAGE = 2.200
DRY_VOLTAGE = 3.700
OVERRIDE_PIN = 24
STATUS_PIN = 23
VALVE_PIN = 21

# https://stackoverflow.com/a/48741004
class RepeatTimer(Timer):
    def run(self):
        while not self.finished.wait(self.interval):
            self.function(*self.args, **self.kwargs)

def scale(value, inMin, inMax, outMin, outMax):
    percentage = (value - inMin) / (inMin - inMax)
    return (percentage) * (outMin - outMax) + outMin
    
def rotate(l, n = 1):
    return l[-n:] + l[:-n]

class Sensor:
    def __init__(self, client, adc, channel = 0):
        self.adc = adc
        self.channel = channel
        self.voltage = 0.000
        self.moisture = 0.0
        self.buffer_size = 10
        self.value = [0] * self.buffer_size
        number = (((self.adc._device._address - 0x48) * 4) + (self.channel + 1))
        self.name = "Garden Moisture %u" % number
        self.client = client
        for i in range(self.buffer_size):
            self.read()
        
    def read(self):
        self.value = rotate(self.value)
        try:
            value = self.adc.read_adc(self.channel, gain=1)
        except:
            self.value[0] = 0
            self.voltage = 0
            self.moisture = 0
            return
        #number = (((self.adc._device._address - 0x48) * 4) + (self.channel + 1))
        #if number <= 4:
            #print("%u: %0.3fV" % (number, value  * (5.00 / 32767)))
        self.value[0] = value
        average = sum(self.value) / len(self.value)
        self.voltage = average * (5.00 / 32767)
        #self.voltage = min(max(self.voltage, WET_VOLTAGE), DRY_VOLTAGE)
        self.moisture = scale(self.voltage, WET_VOLTAGE, DRY_VOLTAGE, 100, 0)
    
    def register(self):
        name_normalized = self.name.lower().replace(" ", "_")
        print("Registering %s with Home Assistant..." % name_normalized)
        topic = "homeassistant/sensor/%s/config" % name_normalized
        data = {
            "name": self.name, 
            "icon": "mdi:water-percent",
            "unit_of_measurement": "V",
            "state_topic": "homeassistant/garden/%s" % name_normalized,
            "value_template": "{{ value_json.voltage }}"
        }
        try:
            self.client.publish(topic, json.dumps(data), retain=True)
        except:
            pass
        return
        
    def report(self):
        name_normalized = self.name.lower().replace(" ", "_")
        #print("%s: %s" % (name_normalized, round(self.moisture, 1)))
        topic = "homeassistant/garden/%s" % name_normalized
        data = {
            "moisture": round(self.moisture, 1),
            "voltage": round(self.voltage, 3)
        }
        try:
            self.client.publish(topic, json.dumps(data))
        except:
            pass
        return   
        
class Valve:
    def __init__(self, client, pin):
        self.pin = pin
        self.state = False
        self.water_mode = False # Triggered by moisture sensors
        self.override_mode = False # Manual override by switch
        self.name = "Garden Watering Valve"
        self.client = client
        gpio.setup(self.pin, gpio.OUT)
    
    def register(self):
        name_normalized = self.name.lower().replace(" ", "_")
        print("Registering %s with Home Assistant..." % name_normalized)
        topic = "homeassistant/switch/%s/config" % name_normalized
        data = {
            "name": self.name, 
            "icon": "mdi:pipe-valve",
            "state_topic": "homeassistant/garden/%s" % name_normalized,
            "command_topic": "homeassistant/garden/%s/command" % name_normalized,
            "value_template": "{{ value_json.state }}"
        }
        try:
            self.client.publish(topic, json.dumps(data), retain=True)
        except:
            pass
        return
        
    def report(self):
        #self.update()
        name_normalized = self.name.lower().replace(" ", "_")
        topic = "homeassistant/garden/%s" % name_normalized
        data = {
            "state": "ON" if self.state else "OFF",
            "override": self.override_mode
        }
        try:
            self.client.publish(topic, json.dumps(data))
        except:
            pass
        return
    
    def update(self):
        self.state = self.water_mode or self.override_mode
        gpio.output(VALVE_PIN, self.state)
        
    def override_switched(self, pin):
        self.override_mode = gpio.input(OVERRIDE_PIN)
        print("Overriding to %s" % "ON" if self.override_mode else "OFF")
        self.update()
        self.report()
        
def on_message(client, userdata, msg):
    if msg.topic == "homeassistant/register":
        for sensor in sensors:
            sensor.register()
        
def blink():
    global status_led
    status_led = not status_led
    gpio.output(STATUS_PIN, status_led)

def main():
    # Set up MQTT
    client = mqtt.Client("mqtt_garden_%u" % os.getpid())
    client.on_message = on_message
    client.connect("192.168.1.9", 1883)
    client.subscribe("homeassistant/register")
    client.loop_start()
    # Set up GPIO
    gpio.setmode(gpio.BCM)
    # Set up valve
    valve = Valve(client, VALVE_PIN)
    valve.register()
    # Blink LED to indicate program is running
    gpio.setup(STATUS_PIN, gpio.OUT)
    global status_led
    status_led = False
    timer = RepeatTimer(0.750, blink)
    timer.start()
    # Set up override mode switch
    gpio.setup(OVERRIDE_PIN, gpio.IN, pull_up_down=gpio.PUD_DOWN)
    gpio.add_event_detect(OVERRIDE_PIN, gpio.BOTH, callback=valve.override_switched)
    valve.override_switched(OVERRIDE_PIN)
    # Set up moisture sensors
    global sensors
    sensors = []
    adc48 = ads.ADS1115(address=0x48)
    sensors.append(Sensor(client, adc48, 0))
    sensors.append(Sensor(client, adc48, 1))
    sensors.append(Sensor(client, adc48, 2))
    sensors.append(Sensor(client, adc48, 3))
    adc49 = ads.ADS1115(address=0x49)
    sensors.append(Sensor(client, adc49, 0))
    sensors.append(Sensor(client, adc49, 1))
    sensors.append(Sensor(client, adc49, 2))
    sensors.append(Sensor(client, adc49, 3))
    adc4A = ads.ADS1115(address=0x4A)
    sensors.append(Sensor(client, adc4A, 0))
    sensors.append(Sensor(client, adc4A, 1))
    sensors.append(Sensor(client, adc4A, 2))
    sensors.append(Sensor(client, adc4A, 3))
    for sensor in sensors:
        sensor.register()
        sensor.report()
    while(1):
        # Report every 15 seconds
        for i in range(5):
            # Take readings every 1 second
            for sensor in sensors:
                sensor.read()
            time.sleep(1)
        for sensor in sensors:
            sensor.report()
        valve.report()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        gpio.cleanup()
        os._exit(0)
    