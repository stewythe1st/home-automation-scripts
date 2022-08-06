import paho.mqtt.client as mqtt
import time
import json
import os
from threading import Timer
import Adafruit_ADS1x15 as ads

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
    
    def read(self):
        try:
            self.value = self.adc.read_adc(0, gain=1)
        except:
            self.value = 0
            self.voltage = 0
            self.state = False;
            self.last_state = False;
            return
        self.voltage = self.value * (5.00 / 32767)
        #print("%s" % round(self.voltage, 3))
        if self.baseline != 0:
            detection_factor = 3.0
            self.state = (self.voltage > (self.baseline + (self.variance * detection_factor))) or \
                         (self.voltage < (self.baseline - (self.variance * detection_factor)))
            if self.state != self.last_state:
                self.report()
                if self.state:
                    print("Ring!!!")
        else:
            self.state = False
        self.last_state = self.state
    
    def get_baseline(self, sampleTime = 10.0, numSamples = 100):
        print("Gathering baseline...")
        samples = [0] * numSamples
        for i in range(numSamples):
            self.read()
            samples[i] = self.voltage
            #print(samples)
            time.sleep(sampleTime / numSamples)
        self.baseline = sum(samples) / len(samples)
        self.variance = max(abs(self.baseline - max(samples)), \
                            abs(self.baseline - min(samples)))
        print("Baseline voltage reading: %sV +/- %sV" % \
              (round(self.baseline, 3), round(self.variance, 3)))
          
    def register(self):
        name_normalized = self.name.lower().replace(" ", "_")
        print("Registering %s with Home Assistant..." % name_normalized)
        topic = "homeassistant/binary_sensor/%s/config" % name_normalized
        data = {
            "name": self.name, 
            "icon": "mdi:doorbell",
            "state_topic": "homeassistant/doorbell/%s" % name_normalized,
            "value_template": "{{ value_json.state }}"
        }
        try:
            self.client.publish(topic, json.dumps(data))
        except:
            pass
        return
        
    def report(self):
        name_normalized = self.name.lower().replace(" ", "_")
        print("%s: %s" % (name_normalized, self.state))
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
          

def main():
    client = mqtt.Client("mqtt_garden_%u" % os.getpid())
    client.connect("192.168.1.9", 1883)
    client.loop_start()
    adc = ads.ADS1115(address=0x48)
    doorbell = Doorbell(client, adc, 0) 
    doorbell.register()
    doorbell.get_baseline()
    # Use the repeating timer to send the reports every 15 seconds
    timer = RepeatTimer(15, doorbell.report)
    timer.daemon = True
    timer.start()
    # Take readings as often as possible
    doorbell.read()
    doorbell.report()
    while(1):
        doorbell.read()

if __name__ == "__main__":
    main()
    