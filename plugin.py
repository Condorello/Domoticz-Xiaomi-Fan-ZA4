### by TheCondor, 2020 ###
### https://github.com/Condorello/Domoticz-Xiaomi-Fan-ZA4 ###

"""
<plugin key="xiaomi-fanza4-plugin" name="Xiaomi FanZA4" author="TheCondor" version="0.1" wikilink="https://github.com/Condorello/Domoticz-Xiaomi-Fan-ZA4" externallink="">
    <params>
        <param field="Mode6" label="MIIOServer host:port" width="200px" required="true" default="127.0.0.1:22223"/>
        <param field="Mode2" label="Update interval (sec)" width="30px" required="true" default="15"/>
        <param field="Mode4" label="Debug" width="75px">
            <options>
                <option label="True" value="Debug" default="true"/>
                <option label="False" value="Normal"/>
            </options>
        </param>
    </params>
</plugin>
"""


import os
import sys

module_paths = [x[0] for x in os.walk( os.path.join(os.path.dirname(__file__), '.', '.env/lib/') ) if x[0].endswith('site-packages') ]
for mp in module_paths:
    sys.path.append(mp)

import Domoticz
import msgpack


class BasePlugin:
    angleOptions = {
        "LevelActions": "||||",
        "LevelNames": "Off|30|60|90|120",
        "LevelOffHidden": "false",
        "SelectorStyle": "0"
    }

    modeOptions = {
        "LevelActions": "||",
        "LevelNames": "Off|Direct|Natural",
        "LevelOffHidden": "true",
        "SelectorStyle": "0"
    }

    customSensorOptions = {"Custom": "1;%"}

    statusUnit = 1
    angleControlUnit = 2
    fanDimmerUnit = 3
    fanSelectorUnit = 4
#    batteryUnit = 5
    modeControlUnit = 10

    states = {
        'direct': 'Direct',
        'natural': 'Natural'
    }


    def __init__(self):
        self.heartBeatCnt = 0
        self.subHost = None
        self.subPort = None
        self.tcpConn = None
        self.unpacker = msgpack.Unpacker(encoding='utf-8')

    def onStart(self):
        if Parameters['Mode4'] == 'Debug':
            Domoticz.Debugging(1)
            DumpConfigToLog()

        self.heartBeatCnt = 0
        self.subHost, self.subPort = Parameters['Mode6'].split(':')

        self.tcpConn = Domoticz.Connection(Name='MIIOServer', Transport='TCP/IP', Protocol='None',
                                           Address=self.subHost, Port=self.subPort)


        if self.statusUnit not in Devices:
            Domoticz.Device(Name='Status', Unit=self.statusUnit, Type=17, Switchtype=17).Create()

        if self.angleControlUnit not in Devices:
            Domoticz.Device(Name='Oscillation Angle', Unit=self.angleControlUnit, TypeName='Selector Switch', Options=self.angleOptions).Create()

        if self.fanDimmerUnit not in Devices:
            Domoticz.Device(Name='Fan Level', Unit=self.fanDimmerUnit, Type=244, Subtype=73, Switchtype=7).Create()

        if self.modeControlUnit not in Devices:
            Domoticz.Device(Name='Mode Control', Unit=self.modeControlUnit, TypeName='Selector Switch',  Options=self.modeOptions).Create()

#        if self.batteryUnit not in Devices:
#            Domoticz.Device(Name='Battery', Unit=self.batteryUnit, TypeName='Custom', Image=iconID, Options=self.customSensorOptions).Create()

        Domoticz.Heartbeat(int(Parameters['Mode2']))


    def onStop(self):
        pass

    def onConnect(self, Connection, Status, Description):
        Domoticz.Debug("MIIOServer connection status is [%s] [%s]" % (Status, Description))

    def onMessage(self, Connection, Data):
        try:
            self.unpacker.feed(Data)
            for result in self.unpacker:

                Domoticz.Debug("Got: %s" % result)

                if 'exception' in result: return

                if result['cmd'] == 'status':

                    UpdateDevice(self.statusUnit, (1 if result['power_state'] in ['on'] else 0), self.states.get(result['fan_mode_state'], 'Undefined'))

#                    UpdateDevice(self.batteryUnit, result['battery'], str(result['battery']), result['battery'], AlwaysUpdate=(self.heartBeatCnt % 100 == 0))

                    UpdateDevice(self.fanDimmerUnit, 2, str(result['fan_level']))

                    if result['oscillate_state'] == True:
                       level = {30: 10, 60: 20, 90: 30, 120: 40}.get(result['angle_state'], None)
                       if level: UpdateDevice(self.angleControlUnit, 1, str(level))
                    elif result['oscillate_state'] == False:
                       UpdateDevice(self.angleControlUnit, 0, str("Off"))

                    UpdateDevice(self.modeControlUnit, 1, self.states.get(result['fan_mode_state'], 'Undefined'))


        except msgpack.UnpackException as e:
            Domoticz.Error('Unpacker exception [%s]' % str(e))

    def onCommand(self, Unit, Command, Level, Hue):
        Domoticz.Debug("onCommand called for Unit " + str(Unit) + ": Command '" + str(Command) + "', Level: " + str(Level))

        if self.statusUnit not in Devices:
            Domoticz.Error('Status device is required')
            return

        sDevice = Devices[self.statusUnit]


        if self.statusUnit == Unit:
            if 'On' == Command and self.isOFF:
                if self.apiRequest('start'): UpdateDevice(Unit, 1)

            elif 'Off' == Command and self.isON:
                if self.apiRequest('stop'): UpdateDevice(Unit, 0)


        elif self.angleControlUnit == Unit:
            if Level == 0 and self.isON: # Oscillation off
                self.apiRequest('oscillate_off')

            if Level == 10 and self.isON: # Oscillate 30 degrees
                self.apiRequest('oscillate_30')

            elif Level == 20 and self.isON: # Oscillate 60 degrees
                self.apiRequest('oscillate_60')

            elif Level == 30 and self.isON: # Oscillate 90 degress
                self.apiRequest('oscillate_90')

            elif Level == 40 and self.isON: # Oscillate 120 degrees
                self.apiRequest('oscillate_120')


        elif self.fanDimmerUnit == Unit and self.isON:
           if sDevice.sValue == self.states['direct']:
              Level = 1 if Level == 0 else 100 if Level > 100 else Level
              if self.apiRequest('set_fan_level_direct', Level): UpdateDevice(self.fanDimmerUnit, 2, str(Level))

           if sDevice.sValue == self.states['natural']:
              Level = 1 if Level == 0 else 100 if Level > 100 else Level
              if self.apiRequest('set_fan_level_natural', Level): UpdateDevice(self.fanDimmerUnit, 2, str(Level))


        elif self.modeControlUnit == Unit and self.isON:
            if Level == 10 and sDevice.sValue == self.states['natural']: # turn on direct mode
                Level = int(Devices[self.fanDimmerUnit].sValue)
                self.apiRequest('set_fan_level_direct', Level)

            if Level == 20 and sDevice.sValue == self.states['direct']: # turn on direct mode
                Level = int(Devices[self.fanDimmerUnit].sValue)
                self.apiRequest('set_fan_level_natural', Level)


    def onNotification(self, Name, Subject, Text, Status, Priority, Sound, ImageFile):
        Domoticz.Debug("Notification: " + Name + "," + Subject + "," + Text + "," + Status + "," + str(Priority) + "," + Sound + "," + ImageFile)

    def onDisconnect(self, Connection):
        Domoticz.Debug("MIIOServer disconnected")

    def onHeartbeat(self):
        if not self.tcpConn.Connecting() and not self.tcpConn.Connected():
            self.tcpConn.Connect()
            Domoticz.Debug("Trying connect to MIIOServer %s:%s" % (self.subHost, self.subPort))

        elif self.tcpConn.Connecting():
            Domoticz.Debug("Still connecting to MIIOServer %s:%s" % (self.subHost, self.subPort))

        elif self.tcpConn.Connected():
            self.apiRequest('status')
            self.heartBeatCnt += 1


    @property
    def isON(self):
        return Devices[self.statusUnit].nValue == 1

    @property
    def isOFF(self):
        return Devices[self.statusUnit].nValue == 0

    def apiRequest(self, cmd_name, cmd_value=None):
        if not self.tcpConn.Connected(): return False
        cmd = [cmd_name]
        if cmd_value: cmd.append(cmd_value)
        try:
            self.tcpConn.Send(msgpack.packb(cmd, use_bin_type=True))
            return True
        except msgpack.PackException as e:
            Domoticz.Error('Pack exception [%s]' % str(e))
            return False


def UpdateDevice(Unit, nValue, sValue, BatteryLevel=255, AlwaysUpdate=False):
    if Unit not in Devices: return
    if Devices[Unit].nValue != nValue\
        or Devices[Unit].sValue != sValue\
        or Devices[Unit].BatteryLevel != BatteryLevel\
        or AlwaysUpdate == True:

        Devices[Unit].Update(nValue, str(sValue), BatteryLevel=BatteryLevel)

        Domoticz.Debug("Update %s: nValue %s - sValue %s - BatteryLevel %s" % (
            Devices[Unit].Name,
            nValue,
            sValue,
            BatteryLevel
        ))



global _plugin
_plugin = BasePlugin()

def onStart():
    global _plugin
    _plugin.onStart()

def onStop():
    global _plugin
    _plugin.onStop()

def onConnect(Connection, Status, Description):
    global _plugin
    _plugin.onConnect(Connection, Status, Description)

def onMessage(Connection, Data, Status=None, Extra=None):
    global _plugin
    _plugin.onMessage(Connection, Data)

def onCommand(Unit, Command, Level, Hue):
    global _plugin
    _plugin.onCommand(Unit, Command, Level, Hue)

def onNotification(Name, Subject, Text, Status, Priority, Sound, ImageFile):
    global _plugin
    _plugin.onNotification(Name, Subject, Text, Status, Priority, Sound, ImageFile)

def onDisconnect(Connection):
    global _plugin
    _plugin.onDisconnect(Connection)

def onHeartbeat():
    global _plugin
    _plugin.onHeartbeat()

    # Generic helper functions
def DumpConfigToLog():
    for x in Parameters:
        if Parameters[x] != "":
            Domoticz.Debug( "'" + x + "':'" + str(Parameters[x]) + "'")
    Domoticz.Debug("Device count: " + str(len(Devices)))
    for x in Devices:
        Domoticz.Debug("Device:           " + str(x) + " - " + str(Devices[x]))
        Domoticz.Debug("Device ID:       '" + str(Devices[x].ID) + "'")
        Domoticz.Debug("Device Name:     '" + Devices[x].Name + "'")
        Domoticz.Debug("Device nValue:    " + str(Devices[x].nValue))
        Domoticz.Debug("Device sValue:   '" + Devices[x].sValue + "'")
        Domoticz.Debug("Device LastLevel: " + str(Devices[x].LastLevel))
    return
