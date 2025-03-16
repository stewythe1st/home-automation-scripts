#!/usr/bin/env python3
import paho.mqtt.client as mqtt
import json
import time

# help with docker
# docker build -t stewythe1st/home-automation-scripts-acurite .
# docker tag stewythe1st/home-automation-scripts-acurite:latest stewythe1st/home-automation-scripts-acurite:v0.0.x
# docker push stewythe1st/home-automation-scripts-acurite:v0.0.x

client = mqtt.Client()

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("Connected")
        client.subscribe("#")
    else:
        print("Error connecting (%i)" % rc)

def on_message(client, userdata, msg):
    if msg.topic == "rtl_433":
        try:
            data = str(msg.payload.decode("utf-8", "ignore"))
            data = json.loads(data)
        except:
            print("Error decoding json: %s" % str(msg.payload))
        if "model" in data:
            if data["model"] == "Acurite-Tower":
                acurite_handle_data(data)
            if data["model"] == "Generic-Remote":
                door_sensor_handle_data(data)
            if data["model"] == "Smoke-GS558":
                button_handle_data(data)
    elif msg.topic == "homeassistant/register":
        print("Re-registering all...")
        acurite_register_all()
        door_sensor_register_all()
        button_register_all()

acurite_known_ids = []
def acurite_handle_data(data):
    if "id" in data:
        id = data["id"]
        if id not in acurite_known_ids:
            acurite_register(id)
            acurite_known_ids.append(id)
        temp_f = data["temperature_C"] * 9/5 + 32
        if temp_f < 120 and temp_f > -20:
            print("Forwarding data from Acurite %s" % id)
            topic = "homeassistant/acurite-tower/%s" % id
            client.publish(topic, json.dumps(data))

def acurite_register_all():
    for id in acurite_known_ids:
        acurite_register(id)

def acurite_register(id):
    print("Registering Acurite %s with Home Assistant" % id)
    unique_id = "acurite-tower-%s" % id
    device = {
        "identifiers": unique_id,
        "name": "Acurite Thermometer %s" % id,
        "model": "Acurite-Tower",
        "manufacturer": "Acurite",
    }
    # Temperature
    topic = "homeassistant/sensor/%s-temperature/config" % unique_id
    data = {
        "name": "Temperature",
        "icon": "mdi:thermometer",
        "device_class": "temperature",
        "unique_id": "%s-temperature" % unique_id,
        "object_id": "%s-temperature" % unique_id,
        "state_topic": "homeassistant/acurite-tower/%s" % id,
        "state_class": "measurement",
        "unit_of_measurement": "°C",
        "value_template": "{{ value_json.temperature_C }}",
        "device": device,
    }
    client.publish(topic, json.dumps(data))
    # Humidity
    topic = "homeassistant/sensor/%s-humidity/config" % unique_id
    data = {
        "name": "Humidity",
        "icon": "mdi:cloud-percent",
        "device_class": "humidity",
        "unique_id": "%s-humidity" % unique_id,
        "object_id": "%s-humidity" % unique_id,
        "state_topic": "homeassistant/acurite-tower/%s" % id,
        "state_class": "measurement",
        "unit_of_measurement": "%",
        "value_template": "{{ value_json.humidity }}",
        "device": device,
    }
    client.publish(topic, json.dumps(data))
    # Battery
    topic = "homeassistant/binary_sensor/%s-battery/config" % unique_id
    data = {
        "name": "Battery",
        "icon": "mdi:battery-charging",
        "device_class": "battery",
        "unique_id": "%s-battery" % unique_id,
        "object_id": "%s-battery" % unique_id,
        "state_topic": "homeassistant/acurite-tower/%s" % id,
        "payload_on": "0",  # battery low
        "payload_off": "1", # battery normal
        "value_template": "{{ value_json.battery_ok }}",
        "device": device,
    }
    client.publish(topic, json.dumps(data))

door_sensor_known_ids = []
def door_sensor_handle_data(data):
    if "id" in data:
        id = data["id"]
        if id not in door_sensor_known_ids:
            door_sensor_register(id)
            door_sensor_known_ids.append(id)
        print("Forwarding data from Door Sensor %s" % id)
        topic = "homeassistant/generic-remote/%s" % id
        client.publish(topic, json.dumps(data))

def door_sensor_register_all():
    for id in door_sensor_known_ids:
        door_sensor_register(id)
        # Send a 'closed' message
        topic = "homeassistant/generic-remote/%s" % id
        data = {
            "cmd": 121
        }
        client.publish(topic, json.dumps(data))

def door_sensor_register(id):
    print("Registering Door Sensor %s with Home Assistant" % id)
    topic = "homeassistant/binary_sensor/door-sensor-%s/config" % id
    unique_id = "door-sensor-%s" % id
    device = {
        "identifiers": unique_id,
        "name": "Door Sensor %s" % id,
        "model": "Generic-Remote",
        "manufacturer": "",
    }
    data = {
        "name": "Door",
        "device_class": "door",
        "unique_id": unique_id,
        "state_topic": "homeassistant/generic-remote/%s" % id,
        "payload_on": 115,
        "payload_off": 121,
        "value_template": "{{ value_json.cmd }}",
        "device": device,
    }
    client.publish(topic, json.dumps(data))

button_known_ids = []
def button_handle_data(data):
    if "id" in data:
        id = data["id"]
        if id not in button_known_ids:
            button_register(id)
            button_known_ids.append(id)
        data["press"] = True
        print("Forwarding data from Button %s" % id)
        topic = "homeassistant/button/%s" % id
        client.publish(topic, json.dumps(data))
        data["press"] = False
        client.publish(topic, json.dumps(data))

def button_register_all():
    for id in button_known_ids:
        button_register(id)

def button_register(id):
    print("Registering Button %s with Home Assistant" % id)
    topic = "homeassistant/binary_sensor/button-%s/config" % id
    unique_id = "button-%s" % id
    device = {
        "identifiers": unique_id,
        "name": "Button %s" % id,
        "model": "Button",
        "manufacturer": "",
    }
    data = {
        "name": "Button",
        "device_class": None,
        "unique_id": unique_id,
        "state_topic": "homeassistant/button/%s" % id,
        "payload_on": True,
        "payload_off": False,
        "value_template": "{{ value_json.press }}",
        "device": device,
    }
    client.publish(topic, json.dumps(data))
    # send a dummy message saying unpressed
    topic = "homeassistant/button/%s" % id
    data = {
        "model": "Smoke-GS558",
        "id": "%s" % id,
        "press": False,
    }
    client.publish(topic, json.dumps(data))

def main():
    client.on_message = on_message
    client.on_connect = on_connect
    connected = False
    while not connected:
        try:
            client.connect("192.168.1.9", 1883)
        except ConnectionRefusedError:
            print("Unable to connect... retrying...")
            time.sleep(2)
        else:
            connected = True
    client.loop_forever()

if __name__ == "__main__":
    main()