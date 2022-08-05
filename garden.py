import paho.mqtt.client as mqtt
import time
import json
import os
import Adafruit_ADS1x15 as ads

WET_VOLTAGE = 1.400
DRY_VOLTAGE = 3.100

def scale(value, inMin, inMax, outMin, outMax):
    percentage = (value - inMin) / (inMin - inMax)
    return (percentage) * (outMin - outMax) + outMin
    
def rotate(l, n = 1):
    return l[-n:] + l[:-n]

class Sensor:
    def __init__(self, adc, channel = 0):
        self.adc = adc
        self.channel = channel
        self.voltage = 0.000
        self.moisture = 0.0
        self.buffer_size = 50
        self.value = [0] * self.buffer_size
        number = (((self.adc._device._address - 0x48) * 4) + (self.channel + 1))
        self.name = "Garden Moisture %u" % number
        
    def read(self):
        self.value = rotate(self.value)
        try:
            value = self.adc.read_adc(self.channel, gain=1)
        except:
            self.value[0] = 0
            self.voltage = 0
            self.moisture = 0
            return
        self.value[0] = value
        average = sum(self.value) / len(self.value)
        self.voltage = average * (5.00 / 32767)
        voltage_saturated = min(max(self.voltage, WET_VOLTAGE), DRY_VOLTAGE)
        self.moisture = scale(voltage_saturated, WET_VOLTAGE, DRY_VOLTAGE, 100, 0)
    
    def register(self, client):
        name_normalized = self.name.lower().replace(" ", "_")
        print("Registering %s with Home Assistant..." % name_normalized)
        topic = "homeassistant/sensor/%s/config" % name_normalized
        data = {
            "name": self.name, 
            "icon": "mdi:water-percent",
            "unit_of_measurement": "%",
            "state_topic": "homeassistant/garden/%s" % name_normalized,
            "value_template": "{{ value_json.moisture }}"
        }
        try:
            client.publish(topic, json.dumps(data))
        except:
            pass
        return
        
    def report(self, client):
        name_normalized = self.name.lower().replace(" ", "_")
        print("%s: %s" % (name_normalized, round(self.moisture, 1)))
        topic = "homeassistant/garden/%s" % name_normalized
        data = {
            "moisture": round(self.moisture, 1),
            "voltage": round(self.voltage, 3)
        }
        try:
            client.publish(topic, json.dumps(data))
        except:
            pass
        return   

def main():
    client = mqtt.Client("mqtt_garden_%u" % os.getpid())
    client.connect("192.168.1.9", 1883)
    client.loop_start()
    sensors = []
    adc48 = ads.ADS1115(address=0x48)
    sensors.append(Sensor(adc48, 0))
    sensors.append(Sensor(adc48, 1))
    sensors.append(Sensor(adc48, 2))
    sensors.append(Sensor(adc48, 3))
    adc49 = ads.ADS1115(address=0x49)
    sensors.append(Sensor(adc49, 0))
    sensors.append(Sensor(adc49, 1))
    sensors.append(Sensor(adc49, 2))
    sensors.append(Sensor(adc49, 3))
    adc4A = ads.ADS1115(address=0x4A)
    sensors.append(Sensor(adc4A, 0))
    sensors.append(Sensor(adc4A, 1))
    sensors.append(Sensor(adc4A, 2))
    sensors.append(Sensor(adc4A, 3))
    for sensor in sensors:
        sensor.register(client)
    while(1):
        # Report every 15 seconds
        for i in range(15):
            # Take readings every 1 second
            for sensor in sensors:
                sensor.read()
            time.sleep(1)
        for sensor in sensors:
            sensor.report(client)

if __name__ == "__main__":
    main()
    