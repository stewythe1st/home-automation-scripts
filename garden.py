#!/usr/bin/python3

import paho.mqtt.client as mqtt
import time
import json
import os
from threading import Timer
import RPi.GPIO as gpio
import board
import busio
import adafruit_ads1x15.ads1115 as ads
from adafruit_ads1x15.analog_in import AnalogIn
import setproctitle

WET_VOLTAGE = 1.000
DRY_VOLTAGE = 4.100
OVERRIDE_PIN = 24
STATUS_PIN = 23
VALVE_PIN = 21

client = mqtt.Client("mqtt_garden_%u" % os.getpid())

# https://stackoverflow.com/a/48741004
class RepeatTimer(Timer):
    def run(self):
        while not self.finished.wait(self.interval):
            self.function(*self.args, **self.kwargs)

def scale(value, inMin, inMax, outMin, outMax):
    percentage = (value - inMin) / (inMin - inMax)
    outValue = (percentage) * (outMin - outMax) + outMin
    outValue = max(min(outValue, outMax), outMin)
    return outValue
    
def rotate(l, n = 1):
    return l[-n:] + l[:-n]
    
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("Connected")
        client.subscribe("homeassistant/register")
        client.subscribe("homeassistant/garden/#")
    else:
        print("Error connecting (%i)" % rc)
        
def on_disconnect(client, userdata,  rc):
	try_connect()

def try_connect():
    connected = False
    while not connected:
        try:
            client.connect("192.168.1.9", 1883)
        except:
            print("Unable to connect... retrying...")
            time.sleep(2)
        else:
            connected = True

class Sensor:
    def __init__(self, client, adc, channel):
        self.channel = AnalogIn(adc, channel);
        self.voltage = 0.000
        self.moisture = 0.0
        self.buffer_size = 100
        self.voltage = [0] * self.buffer_size
        self.name = "Garden Moisture %u" % (channel + 1)
        self.client = client
        for i in range(self.buffer_size):
            self.read()
        
    def read(self):
        self.voltage = rotate(self.voltage)
        self.voltage[0] = self.channel.voltage
        average = sum(self.voltage) / len(self.voltage)
        self.moisture = scale(average, DRY_VOLTAGE, WET_VOLTAGE, 0, 100);
        #if self.name == "Garden Moisture 4":
        #    print("%s: %0.3fV - %0.3fV - %3.1f%%" % (self.name, self.voltage[0], average, self.moisture))
    
    def register(self):
        name_normalized = self.name.lower().replace(" ", "_")
        print("Registering %s with Home Assistant..." % name_normalized)
        device = {
            "identifiers": "Garden-Watering-System",
            "name": "Garden Watering System",
            "model": "Garden Watering System",
            "manufacturer": "",
        }
        topic = "homeassistant/sensor/%s/config" % name_normalized
        data = {
            "name": self.name,
            "device_class": "moisture",
            "unique_id": name_normalized,
            "icon": "mdi:water-percent",
            "unit_of_measurement": "%",
            "state_topic": "homeassistant/garden/%s" % name_normalized,
            "value_template": "{{ value_json.moisture }}",
            "device": device,
        }
        try:
            self.client.publish(topic, json.dumps(data))
        except:
            pass
        return
        
    def report(self):
        name_normalized = self.name.lower().replace(" ", "_")
        topic = "homeassistant/garden/%s" % name_normalized
        average = sum(self.voltage) / len(self.voltage)
        data = {
            "moisture": round(self.moisture, 2),
            "voltage_average": round(average, 3),
            "voltage": round(self.voltage[0], 3)
        }
        try:
            self.client.publish(topic, json.dumps(data))
        except:
            print("MQTT error")
            pass
        return   
        
class Valve:
    def __init__(self, client, pin):
        self.pin = pin
        self.state = False
        self.water_mode = False # Triggered by moisture sensors
        self.override_mode = False # Manual override
        self.name = "Garden Watering Valve"
        self.client = client
        gpio.setup(self.pin, gpio.OUT)
        self.update()
    
    def register(self):
        name_normalized = self.name.lower().replace(" ", "_")
        print("Registering %s with Home Assistant..." % name_normalized)
        device = {
            "identifiers": "Garden-Watering-System",
            "name": "Garden Watering System",
            "model": "Garden Watering System",
            "manufacturer": "",
        }
        topic = "homeassistant/switch/%s/config" % name_normalized
        data = {
            "name": self.name,
            "device_class": "switch",
            "unique_id": name_normalized,
            "icon": "mdi:pipe-valve",
            "state_topic": "homeassistant/garden/%s" % name_normalized,
            "command_topic": "homeassistant/garden/%s/command" % name_normalized,
            "value_template": "{{ value_json.state }}",
            "device": device,
        }
        try:
            self.client.publish(topic, json.dumps(data))
        except:
            pass
        return
        
    def report(self):
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
    else:
        name_normalized = valve.name.lower().replace(" ", "_")
        command_topic = "homeassistant/garden/%s/command" % name_normalized
        if msg.topic == command_topic:
            data = msg.payload.decode().lower()
            if data == "on":
                valve.override_mode = True
            elif data == "off":
                valve.override_mode = False
            print(msg.payload.lower())
            print(valve.override_mode)
            valve.update()
            valve.report()
        
def blink():
    global status_led
    status_led = not status_led
    gpio.output(STATUS_PIN, status_led)

def main():
    setproctitle.setproctitle('garden')
    # Set up MQTT
    client.on_message = on_message
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    try_connect()
    client.loop_start()
    # Set up GPIO
    gpio.setmode(gpio.BCM)
    # Set up valve
    global valve
    valve = Valve(client, VALVE_PIN)
    valve.register()
    # Blink LED to indicate program is running
    gpio.setup(STATUS_PIN, gpio.OUT)
    global status_led
    status_led = False
    timer = RepeatTimer(0.750, blink)
    timer.start()
    # Set up override mode switch
    #gpio.setup(OVERRIDE_PIN, gpio.IN, pull_up_down=gpio.PUD_DOWN)
    #gpio.add_event_detect(OVERRIDE_PIN, gpio.BOTH, callback=valve.override_switched)
    #valve.override_switched(OVERRIDE_PIN)
    # Set up moisture sensors
    i2c = busio.I2C(board.SCL, board.SDA)
    global sensors
    sensors = []
    adc48 = ads.ADS1115(i2c, address=0x48)
    sensors.append(Sensor(client, adc48, 0))
    sensors.append(Sensor(client, adc48, 1))
    sensors.append(Sensor(client, adc48, 2))
    sensors.append(Sensor(client, adc48, 3))
    # adc49 = ads.ADS1115(i2c, address=0x49)
    # sensors.append(Sensor(client, adc49, 0))
    # sensors.append(Sensor(client, adc49, 1))
    # sensors.append(Sensor(client, adc49, 2))
    # sensors.append(Sensor(client, adc49, 3))
    # adc4A = ads.ADS1115(i2c, address=0x4A)
    # sensors.append(Sensor(client, adc4A, 0))
    # sensors.append(Sensor(client, adc4A, 1))
    # sensors.append(Sensor(client, adc4A, 2))
    # sensors.append(Sensor(client, adc4A, 3))
    for sensor in sensors:
        sensor.register()
        sensor.report()
    while(1):
        # Report every x seconds
        for i in range(15):
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
    
