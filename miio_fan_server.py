#!/usr/bin/python3

### by TheCondor, 2020 ###
### https://github.com/Condorello/Domoticz-Xiaomi-Fan-ZA4 ###

import sys
import os

module_paths = [x[0] for x in os.walk( os.path.join(os.path.dirname(__file__), '.', '.env/lib/') ) if x[0].endswith('site-packages') ]
for mp in module_paths:
    sys.path.append(mp)

from gevent import monkey
monkey.patch_all()

import msgpack
from gevent.queue import Queue
from gevent.pool import Group
from gevent.server import StreamServer
import argparse
from miio import FanZA4, DeviceException
from msgpack import Unpacker
import time
import signal
from logging.handlers import RotatingFileHandler
import logging

parser = argparse.ArgumentParser()
parser.add_argument('ip', type=str, help='fan ip address', default='192.168.0.110"')
parser.add_argument('token', type=str, help='token', default='xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx')
parser.add_argument('--host', type=str, default='127.0.0.1')
parser.add_argument('--port', type=int, default=22223)
args = parser.parse_args()

send = Queue()
receive = Queue()
sockets = {}

#### LOGGING

# fh = RotatingFileHandler(os.path.join(os.path.dirname(__file__), '.', 'log/server.log'), maxBytes=1024 * 1024, backupCount=5)
# fh.setLevel(logging.DEBUG)
# fh.setFormatter(logging.Formatter("%(asctime)s [%(process)s]:%(levelname)s:%(name)-10s| %(message)s", datefmt='%Y-%m-%d %H:%M:%S'))

s = logging.StreamHandler(sys.stdout)
s.setLevel(logging.DEBUG)
s.setFormatter(logging.Formatter("server: %(message)s"))

logger = logging.getLogger('server')
logger.setLevel(logging.DEBUG)
# logger.addHandler(fh)
logger.addHandler(s)

#### ./LOGGING

### for run as service
def signal_handler(signum=None, frame=None):
    time.sleep(1)
    sys.exit(0)
for sig in [signal.SIGTERM, signal.SIGINT, signal.SIGHUP, signal.SIGQUIT]:
    signal.signal(sig, signal_handler)
### ./for run as service


def socket_incoming_connection(socket, address):

    logger.debug('connected %s', address)

    sockets[address] = socket

    unpacker = Unpacker(encoding='utf-8')
    while True:
        data = socket.recv(4096)

        if not data:
            logger.debug('closed connection %s', address)
            break

        unpacker.feed(data)

        for msg in unpacker:
            receive.put(InMsg(msg, address))
            logger.debug('got socket msg: %s', msg)

    sockets.pop(address)


def socket_msg_sender(sockets, q):
    while True:
        msg = q.get()
        if isinstance(msg, OutMsg) and msg.to in sockets:
            sockets[msg.to].sendall(msgpack.packb(msg, use_bin_type=True))
            logger.debug('send reply %s', msg.to)



def Fan_commands_handler(ip, token, q):
    fan = FanZA4(ip, token)
    fan.manual_seqnum = 0

    while True:
        msg = q.get()
        try:
            cmd = msg.pop(0)
            if hasattr(FanCommand, cmd):
                result = getattr(FanCommand, cmd)(fan, *msg)
            else:
                result = {'exception': 'command [%s] not found' % cmd}
        except (DeviceException, Exception) as e:
            result = {'exception': 'python-miio: %s' % e}
        finally:
            result.update({'cmd': cmd})
            logger.debug('fan result %s', result)
            send.put(OutMsg(result, msg.to))



class FanCommand(object):

    @classmethod
    def status(cls, fan):
        res = fan.status()
        if not res:
            return {
                'exception': 'no response'
            }

        return {
            'power_state': res.power,
            'battery': res.battery_charge,
#            'fan_level_direct': res.direct_speed,
#            'fan_level_natural': res.natural_speed,
            'fan_level': res.natural_speed if res.natural_speed != 0 else res.direct_speed,
            'oscillate_state': res.oscillate,
            'angle_state': res.angle,
            'fan_mode_state': 'natural' if res.natural_speed != 0 else 'direct'
        }

    @classmethod
    def start(cls, fan):
        return {'code': fan.on()}

    @classmethod
    def stop(cls, fan):
        return {'code': fan.off()}

    @classmethod
    def oscillate_off(cls, fan):
        if fan.status().oscillate == True:
           return {'code': fan.set_oscillate(False)}
### toggle option, act as on/off on a single switch
#        elif fan.status().oscillate == False:
#           return {'code': fan.set_oscillate(True)}

    @classmethod
    def oscillate_30(cls, fan):
        return {'code': fan.set_angle(30)}

    @classmethod
    def oscillate_60(cls, fan):
        return {'code': fan.set_angle(60)}

    @classmethod
    def oscillate_90(cls, fan):
        return {'code': fan.set_angle(90)}

    @classmethod
    def oscillate_120(cls, fan):
        return {'code': fan.set_angle(120)}

    @classmethod
    def set_fan_level(cls, fan, level):
        if fan.status().natural_speed != 0:
           return {'code': fan.set_natural_speed(int(level))}
        elif fan.status().natural_speed == 0:
           return {'code': fan.set_direct_speed(int(level))}

class InMsg(list):
    def __init__(self, data, to, **kwargs):
        super(InMsg, self).__init__(**kwargs)
        self.extend(data)
        self.to = to


class OutMsg(dict):
    def __init__(self, data, to, **kwargs):
        super(OutMsg, self).__init__(**kwargs)
        self.update(data)
        self.to = to


if __name__ == '__main__':

    server = StreamServer((args.host, args.port), socket_incoming_connection)
    logger.debug('Starting server on %s %s' % (args.host, args.port))

    services = Group()
    services.spawn(server.serve_forever)
    services.spawn(Fan_commands_handler, args.ip, args.token, receive)
    services.spawn(socket_msg_sender, sockets, send)
    services.join()
