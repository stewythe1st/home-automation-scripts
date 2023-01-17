#!/usr/bin/python3

import paho.mqtt.client as mqtt
import time
import json
import os
from threading import Timer
import schedule
import Adafruit_ADS1x15 as ads
import setproctitle

# https://stackoverflow.com/a/48741004
class RepeatTimer(Timer):
    def run(self):
        while not self.finished.wait(self.interval):
            self.function(*self.args, **self.kwargs)

class Doorbell:
    def __init__(self, client, adc, channel = 0, name = "Doorbell"):
        self.client = client
        self.adc = adc
        self.channel = channel
        self.value = 0
        self.voltage = 0.000
        self.baseline = 0.000
        self.variance = 0.000
        self.state = False
        self.last_state = False
        self.name = name
        self.count = 0
    
    def read(self):
        try:
            self.value = self.adc.read_adc(0, gain=1)
        except:
            self.value = 0
            self.voltage = 0
            self.state = False
            self.last_state = False
            return
        self.voltage = self.value * (5.00 / 32767)
        #print("%s" % round(self.voltage, 3))
        if self.baseline != 0:
            detection_factor = 5.5
            state = (self.voltage > (self.baseline + (self.variance * detection_factor))) or \
                    (self.voltage < (self.baseline - (self.variance * detection_factor)))
            #print("%0.3fV - %s" % (self.voltage, "RING" if state else "----"))
            # Wait until signal stabilizes before signaling a on->off transition
            if not state and self.last_state:
                self.count = self.count + 1
                if self.count > 20:
                    self.state = False
                    self.last_state = False
                    self.count = 0
                    self.report()
            # Immediately signal a off->on transition
            if state and not self.last_state:
                self.state = True
                self.last_state = True
                print("Ring!!!")
                self.report()
            # Otherwise just update state
            if not state and not self.last_state:
                self.state = False
                self.last_state = False
            if state and self.last_state:
                self.state = True
                self.last_state = True
        else:
            self.state = False
            self.last_state = False
    
    def get_baseline(self, sampleTime = 10.0, numSamples = 100):
        print("Gathering baseline...")
        samples = [0] * numSamples
        for i in range(numSamples):
            self.read()
            samples[i] = self.voltage
            time.sleep(sampleTime / numSamples)
        self.baseline = sum(samples) / len(samples)
        self.variance = max(abs(self.baseline - max(samples)), \
                            abs(self.baseline - min(samples)))
        print("Baseline voltage reading: %sV +/- %sV" % \
              (round(self.baseline, 3), round(self.variance, 3)))
          
    def register(self):
        name_normalized = self.name.lower().replace(" ", "_")
        print("Registering %s with Home Assistant..." % name_normalized)
        device = {
            "identifiers": name_normalized,
            "name": "Doorbell",
            "model": "Doorbell",
            "manufacturer": "",
        }
        topic = "homeassistant/binary_sensor/%s/config" % name_normalized
        data = {
            "name": self.name, 
            "icon": "mdi:doorbell",
            "unique_id": "doorbell",
            "state_topic": "homeassistant/doorbell/%s" % name_normalized,
            "value_template": "{{ value_json.state }}",
            "device": device,
        }
        try:
            self.client.publish(topic, json.dumps(data), retain=True)
        except:
            pass
        return
        
    def report(self):
        name_normalized = self.name.lower().replace(" ", "_")
        #print("%s: %s" % (name_normalized, self.state))
        topic = "homeassistant/doorbell/%s" % name_normalized
        data = {
            "state": "ON" if self.state else "OFF",
            "voltage": round(self.voltage, 3)
        }
        try:
            self.client.publish(topic, json.dumps(data))
        except:
            pass
        return
        
    def on_message(self, client, userdata, msg):
        if msg.topic == "homeassistant/register":
            self.register()
        
def main():
    setproctitle.setproctitle('doorbell')
    client = mqtt.Client("mqtt_garden_%u" % os.getpid())
    adc = ads.ADS1115(address=0x48)
    doorbell = Doorbell(client, adc, 0) 
    client.on_message = doorbell.on_message
    client.connect("192.168.1.9", 1883)
    client.subscribe("homeassistant/register")
    client.loop_start()
    doorbell.register()
    doorbell.get_baseline()
    # Use schedule to re-acquire baseline nightly
    schedule.every().day.at("04:00").do(doorbell.get_baseline)
    # Use the repeating timer to send the reports every 15 seconds
    timer = RepeatTimer(15, doorbell.report)
    timer.daemon = True
    timer.start()
    # Take readings as often as possible
    doorbell.read()
    doorbell.report()
    while(1):
        doorbell.read()
        schedule.run_pending()
        time.sleep(0.01)

if __name__ == "__main__":
    main()
    
