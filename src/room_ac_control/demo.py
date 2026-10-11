"""Fictional rooms for the public, account-free design preview."""
from copy import deepcopy


def devices():
    modes = {"Auto":"0","Cool":"1","Dry":"2","Heat":"4","Fan":"6"}
    fans = {"Auto":"0","Low":"5","Medium":"3","High":"1"}
    def enum(key,label,options,value):
        return {"key":key,"label":label,"kind":"enum","options":options,"value":value,"reported":True}
    toggle = {"Off":"0","On":"1"}
    controls = {
        "machMode":enum("machMode","Mode",modes,"1"),
        "windSpeed":enum("windSpeed","Fan speed",fans,"0"),
        "silentSleepStatus":enum("silentSleepStatus","Sleep",toggle,"0"),
        "ecoMode":enum("ecoMode","Eco Mode",toggle,"0"),
        "windDirectionVertical":enum("windDirectionVertical","Vertical airflow",{"Fixed":"0","Swing":"8"},"8"),
        "tempSel":{"key":"tempSel","label":"Target temperature","kind":"range","min":16,"max":32,"step":1,"value":23,"reported":True},
    }
    room = {"id":"preview-living-room","name":"Living room","model":"DEMO-AC","power":"On","mode":"Cool",
            "room":23,"target":23,"fan":"Auto","connection":"CONNECTED","fetched":"Preview",
            "controls":controls,"modes":modes,"fans":fans,"temperatures":[str(n) for n in range(16,33)],"commands":{}}
    bedroom = deepcopy(room)
    bedroom.update(id="preview-bedroom",name="Bedroom",power="Off",room=22)
    return [room,bedroom]
