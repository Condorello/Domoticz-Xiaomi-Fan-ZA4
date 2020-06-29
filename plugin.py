#       
#       Xiaomi Fan ZA4 Plugin
#       Author: TheCondor, 2020
#       
"""
<plugin key="xiaomi-fanza4-vacuum" name="Xiaomi FanZA4" author="TheCondor" version="0.1" wikilink="https://github.com/mrin/domoticz-mirobot-plugin" externallink="">
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
    controlOptions = {
        "LevelActions": "|||||",
        "LevelNames": "Off|30|60|90|120",
        "LevelOffHidden": "False",
        "SelectorStyle": "0"
    }

    customSensorOptions = {"Custom": "1;%"}

    iconName = 'xiaomi-mi-robot-vacuum-icon'

    statusUnit = 1
    controlUnit = 2
    fanDimmerUnit = 3
    fanSelectorUnit = 4
    batteryUnit = 5
    cMainBrushUnit = 6
    cSideBrushUnit = 7
    cSensorsUnit = 8
    cFilterUnit = 9
    cResetControlUnit = 10

    # statuses by protocol
    # https://github.com/marcelrv/XiaomiRobotVacuumProtocol/blob/master/StatusMessage.md
    states = {
        'on': 'Acceso',
        'off': 'Spento',
        5: 'Oscillando',
        6: 'Non oscillando',
        7: 'Direct',
        8: 'Natural'
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

        if self.iconName not in Images: Domoticz.Image('icons.zip').Create()
        iconID = Images[self.iconName].ID

        if self.statusUnit not in Devices:
            Domoticz.Device(Name='Status', Unit=self.statusUnit, Type=17, Switchtype=17, Image=iconID).Create()

        if self.controlUnit not in Devices:
            Domoticz.Device(Name='Oscillate', Unit=self.controlUnit, TypeName='Selector Switch', Image=iconID, Options=self.controlOptions).Create()

        if self.fanDimmerUnit not in Devices:
            Domoticz.Device(Name='Fan Level', Unit=self.fanDimmerUnit, Type=244, Subtype=73, Switchtype=7, Image=iconID).Create()

        if self.batteryUnit not in Devices:
            Domoticz.Device(Name='Battery', Unit=self.batteryUnit, TypeName='Custom', Image=iconID, Options=self.customSensorOptions).Create()

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

                    UpdateDevice(self.statusUnit, (1 if result['power_state'] in ['on'] else 0), self.states.get(result['power_state'], 'Undefined'))

                    UpdateDevice(self.batteryUnit, result['battery'], str(result['battery']), result['battery'], AlwaysUpdate=(self.heartBeatCnt % 100 == 0))

                    UpdateDevice(self.fanDimmerUnit, 2, str(result['fan_level_direct'])) # nValue=2 for show percentage, instead ON/OFF state

                    if ['oscillate_state'] == True:
                       level = {30: 10, 60: 20, 90: 30, 120: 40}.get(result['angle_state'], None)
                       if level: UpdateDevice(self.controlUnit, 1, str(level))
                    elif ['oscillate_state'] == False:
                       UpdateDevice(self.controlUnit, 0, Off)

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
                if self.apiRequest('start'): UpdateDevice(Unit, 1, self.states [1])

            elif 'Off' == Command and self.isON:
                if self.apiRequest('stop'): UpdateDevice(Unit, 0, self.states [0])

        elif self.controlUnit == Unit:
            if Level == 0: # oscillation_off
                self.apiRequest('oscillate_off')

            if Level == 10: # Oscillate 30
                self.apiRequest('oscillate_30') # and self.isON:

            elif Level == 20: # Oscillate 60
                self.apiRequest('oscillate_60')
#                if self.apiRequest('home') and sDevice.sValue in [self.states[5], self.states[3], self.states[10]]: # Cleaning, Waiting, Paused
#                    UpdateDevice(self.statusUnit, 1, self.states[6])  # Back to home

            elif Level == 30: # Oscillate 90
                self.apiRequest('oscillate_90')
#                if self.apiRequest('spot') and self.isOFF and sDevice.sValue != self.states[8]: # Spot cleaning will not start if Charging
#                    UpdateDevice(self.statusUnit, 1, self.states[11])  # Spot cleaning

            elif Level == 40: # Oscillate 120
                self.apiRequest('oscillate_120')
#                if self.apiRequest('pause') and self.isON:
#                    if sDevice.sValue == self.states[11]: # For Spot cleaning - Pause treats as Stop
#                        UpdateDevice(self.statusUnit, 0, self.states[3])  # Waiting
#                    else:
#                        UpdateDevice(self.statusUnit, 0, self.states[10])  # Paused

        elif self.fanDimmerUnit == Unit:
            Level = 1 if Level == 0 else 100 if Level > 100 else Level
            if self.apiRequest('set_fan_level_direct', Level): UpdateDevice(self.fanDimmerUnit, 2, str(Level))

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


def UpdateIcon(Unit, iconID):
    if Unit not in Devices: return
    d = Devices[Unit]
    if d.Image != iconID: d.Update(d.nValue, d.sValue, Image=iconID)

def cPercent(used, max):
    return 100 - round(used / 3600 * 100 / max)


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
