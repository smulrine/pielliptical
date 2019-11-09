#!/usr/bin/env python3

import dbus
import dbus.exceptions
import dbus.mainloop.glib
import dbus.service
import array
from gi.repository import GLib
import functools
import time
import board
import busio
import adafruit_adxl34x

milli_time = lambda: int(round(time.time() * 1000))

mainloop = None

BLUEZ_SERVICE_NAME = 'org.bluez'
GATT_MANAGER_IFACE = 'org.bluez.GattManager1'
DBUS_OM_IFACE =      'org.freedesktop.DBus.ObjectManager'
DBUS_PROP_IFACE =    'org.freedesktop.DBus.Properties'

GATT_SERVICE_IFACE = 'org.bluez.GattService1'
GATT_CHRC_IFACE =    'org.bluez.GattCharacteristic1'
GATT_DESC_IFACE =    'org.bluez.GattDescriptor1'
LE_ADVERTISING_MANAGER_IFACE = 'org.bluez.LEAdvertisingManager1'
LE_ADVERTISEMENT_IFACE = 'org.bluez.LEAdvertisement1'

class InvalidArgsException(dbus.exceptions.DBusException):
    _dbus_error_name = 'org.freedesktop.DBus.Error.InvalidArgs'

class NotSupportedException(dbus.exceptions.DBusException):
    _dbus_error_name = 'org.bluez.Error.NotSupported'

class NotPermittedException(dbus.exceptions.DBusException):
    _dbus_error_name = 'org.bluez.Error.NotPermitted'

class InvalidValueLengthException(dbus.exceptions.DBusException):
    _dbus_error_name = 'org.bluez.Error.InvalidValueLength'

class FailedException(dbus.exceptions.DBusException):
    _dbus_error_name = 'org.bluez.Error.Failed'

class Advertisement(dbus.service.Object):
    PATH_BASE = '/org/bluez/example/advertisement'

    def __init__(self, bus, index, advertising_type):
        self.path = self.PATH_BASE + str(index)
        self.bus = bus
        self.ad_type = advertising_type
        self.service_uuids = None
        self.include_tx_power = None
        dbus.service.Object.__init__(self, bus, self.path)

    def get_properties(self):
        properties = dict()
        properties['Type'] = self.ad_type
        if self.service_uuids is not None:
            properties['ServiceUUIDs'] = dbus.Array(self.service_uuids,
                                                    signature='s')
        if self.include_tx_power is not None:
            properties['IncludeTxPower'] = dbus.Boolean(self.include_tx_power)

        return {LE_ADVERTISEMENT_IFACE: properties}

    def get_path(self):
        return dbus.ObjectPath(self.path)

    def add_service_uuid(self, uuid):
        if not self.service_uuids:
            self.service_uuids = []
        self.service_uuids.append(uuid)

    @dbus.service.method(DBUS_PROP_IFACE,
                         in_signature='s',
                         out_signature='a{sv}')
    def GetAll(self, interface):
        if interface != LE_ADVERTISEMENT_IFACE:
            raise InvalidArgsException()
        return self.get_properties()[LE_ADVERTISEMENT_IFACE]

    @dbus.service.method(LE_ADVERTISEMENT_IFACE,
                         in_signature='',
                         out_signature='')
    def Release(self):
        print('%s: Released!' % self.path)

class RSCAdvertisement(Advertisement):

    def __init__(self, bus, index):
        Advertisement.__init__(self, bus, index, 'peripheral')
        self.add_service_uuid('1814') # Running Speed and Cadence
        self.include_tx_power = True

def register_ad_cb():
    print('Advertisement registered')

def register_ad_error_cb(error):
    global mainloop
    print('Failed to register advertisement: ' + str(error))
    mainloop.quit()

class Application(dbus.service.Object):
    """
    org.bluez.GattApplication1 interface implementation
    """
    def __init__(self, bus):
        self.path = '/'
        self.services = []
        dbus.service.Object.__init__(self, bus, self.path)
        self.add_service(RunningSpeedService(bus, 0))
    
    def get_path(self):
        return dbus.ObjectPath(self.path)
    
    def add_service(self, service):
        self.services.append(service)
    
    @dbus.service.method(DBUS_OM_IFACE, out_signature='a{oa{sa{sv}}}')
    def GetManagedObjects(self):
        response = {}
        
        for service in self.services:
            response[service.get_path()] = service.get_properties()
            chrcs = service.get_characteristics()
            for chrc in chrcs:
                response[chrc.get_path()] = chrc.get_properties()
                descs = chrc.get_descriptors()
                for desc in descs:
                    response[desc.get_path()] = desc.get_properties()
        
        return response

class Service(dbus.service.Object):
    """
    org.bluez.GattService1 interface implementation
    """
    PATH_BASE = '/org/bluez/example/service'
    
    def __init__(self, bus, index, uuid, primary):
        self.path = self.PATH_BASE + str(index)
        self.bus = bus
        self.uuid = uuid
        self.primary = primary
        self.characteristics = []
        dbus.service.Object.__init__(self, bus, self.path)
    
    def get_properties(self):
        return {
                GATT_SERVICE_IFACE: {
                        'UUID': self.uuid,
                        'Primary': self.primary,
                        'Characteristics': dbus.Array(
                                self.get_characteristic_paths(),
                                signature='o')
                }
        }
    
    def get_path(self):
        return dbus.ObjectPath(self.path)
    
    def add_characteristic(self, characteristic):
        self.characteristics.append(characteristic)
    
    def get_characteristic_paths(self):
        result = []
        for chrc in self.characteristics:
            result.append(chrc.get_path())
        return result
    
    def get_characteristics(self):
        return self.characteristics
    
    @dbus.service.method(DBUS_PROP_IFACE,
                         in_signature='s',
                         out_signature='a{sv}')
    def GetAll(self, interface):
        if interface != GATT_SERVICE_IFACE:
            raise InvalidArgsException()
        
        return self.get_properties()[GATT_SERVICE_IFACE]

class Characteristic(dbus.service.Object):
    """
    org.bluez.GattCharacteristic1 interface implementation
    """
    def __init__(self, bus, index, uuid, flags, service):
        self.path = service.path + '/char' + str(index)
        self.bus = bus
        self.uuid = uuid
        self.service = service
        self.flags = flags
        self.descriptors = []
        dbus.service.Object.__init__(self, bus, self.path)
    
    def get_properties(self):
        return {
                GATT_CHRC_IFACE: {
                        'Service': self.service.get_path(),
                        'UUID': self.uuid,
                        'Flags': self.flags,
                        'Descriptors': dbus.Array(
                                self.get_descriptor_paths(),
                                signature='o')
                }
        }
    
    def get_path(self):
        return dbus.ObjectPath(self.path)
    
    def add_descriptor(self, descriptor):
        self.descriptors.append(descriptor)
    
    def get_descriptor_paths(self):
        result = []
        for desc in self.descriptors:
            result.append(desc.get_path())
        return result
    
    def get_descriptors(self):
        return self.descriptors
    
    @dbus.service.method(DBUS_PROP_IFACE,
                         in_signature='s',
                         out_signature='a{sv}')
    def GetAll(self, interface):
        if interface != GATT_CHRC_IFACE:
            raise InvalidArgsException()
        
        return self.get_properties()[GATT_CHRC_IFACE]
    
    @dbus.service.method(GATT_CHRC_IFACE,
                        in_signature='a{sv}',
                        out_signature='ay')
    def ReadValue(self, options):
        print('Default ReadValue called, returning error')
        raise NotSupportedException()
    
    @dbus.service.method(GATT_CHRC_IFACE, in_signature='aya{sv}')
    def WriteValue(self, value, options):
        print('Default WriteValue called, returning error')
        raise NotSupportedException()
    
    @dbus.service.method(GATT_CHRC_IFACE)
    def StartNotify(self):
        print('Default StartNotify called, returning error')
        raise NotSupportedException()
    
    @dbus.service.method(GATT_CHRC_IFACE)
    def StopNotify(self):
        print('Default StopNotify called, returning error')
        raise NotSupportedException()
    
    @dbus.service.signal(DBUS_PROP_IFACE,
                         signature='sa{sv}as')
    def PropertiesChanged(self, interface, changed, invalidated):
        pass

class Descriptor(dbus.service.Object):
    """
    org.bluez.GattDescriptor1 interface implementation
    """
    def __init__(self, bus, index, uuid, flags, characteristic):
        self.path = characteristic.path + '/desc' + str(index)
        self.bus = bus
        self.uuid = uuid
        self.flags = flags
        self.chrc = characteristic
        dbus.service.Object.__init__(self, bus, self.path)
    
    def get_properties(self):
        return {
                GATT_DESC_IFACE: {
                        'Characteristic': self.chrc.get_path(),
                        'UUID': self.uuid,
                        'Flags': self.flags,
                }
        }
    
    def get_path(self):
        return dbus.ObjectPath(self.path)
    
    @dbus.service.method(DBUS_PROP_IFACE,
                         in_signature='s',
                         out_signature='a{sv}')
    def GetAll(self, interface):
        if interface != GATT_DESC_IFACE:
            raise InvalidArgsException()
        
        return self.get_properties()[GATT_DESC_IFACE]
    
    @dbus.service.method(GATT_DESC_IFACE,
                        in_signature='a{sv}',
                        out_signature='ay')
    def ReadValue(self, options):
        print ('Default ReadValue called, returning error')
        raise NotSupportedException()
    
    @dbus.service.method(GATT_DESC_IFACE, in_signature='aya{sv}')
    def WriteValue(self, value, options):
        print('Default WriteValue called, returning error')
        raise NotSupportedException()

class sensorLocationChrc(Characteristic):
    SENSOR_LOCATION_UUID = '2a5d'

    def __init__(self, bus, index, service):
        Characteristic.__init__(
                self, bus, index,
                self.SENSOR_LOCATION_UUID,
                ['read'],
                service)

    def ReadValue(self, options):
        return [ 0x01 ]

class RunningSpeedService(Service):
    RSC_SVC_UUID = '1814'

    def __init__(self, bus, index):
        Service.__init__(self, bus, index, self.RSC_SVC_UUID, True)
        self.add_characteristic(RSCMeasurementChrc(bus, 0, self))
        self.add_characteristic(sensorLocationChrc(bus, 1, self))

class RSCMeasurementChrc(Characteristic):
    RSC_MSRMT_UUID = '2a53'
    STOPPING = -3
    STARTING = 3

    def __init__(self, bus, index, service):
        i2c = busio.I2C(board.SCL, board.SDA)
        self.accelerometer = adafruit_adxl34x.ADXL345(i2c)
        self.accelerometer.range = adafruit_adxl34x.Range.RANGE_4_G
        self.accelerometer.enable_motion_detection(threshold=16)
        self.stopped = True
        self.moving = False
        self.at_rest_counter = 0
        self.changed_direction = False
        self.starting_from_stopped = -1
        self.t0 = milli_time()
        self.max_acceleration = 0
        self.speed = 0
        self.spm = 0
        Characteristic.__init__(
                self, bus, index,
                self.RSC_MSRMT_UUID,
                ['notify', 'broadcast'],
                service)
        self.notifying = False
        # change this to True to test elliptical speed without BLE connection
        # and uncomment the following line
        #GLib.timeout_add(10, self.rsc_msrmt_cb)

    def rsc_msrmt_cb(self):
        changed = False
        if self.accelerometer.events['motion'] == False:
            self.at_rest_counter += 1
        if self.at_rest_counter == 20:
            print('\033cstopped')
            self.at_rest_counter += 1
            self.starting_from_stopped = -1
            self.speed = 0
            self.spm = 0
            changed = True
        x_acceleration = self.accelerometer.acceleration[0]
        if x_acceleration > self.max_acceleration:
            self.max_acceleration = x_acceleration
        if x_acceleration > self.STARTING:
            self.at_rest_counter = 0
            if self.changed_direction == True or self.stopped == True:
                self.changed_direction = False
                self.stopped = False
        elif x_acceleration < self.STOPPING:
            self.at_rest_counter = 0
            if self.changed_direction == False:
                self.changed_direction = True
                self.stopped = False
                t1 = milli_time()
                if self.starting_from_stopped != 1:
                    self.starting_from_stopped += 1
                else:
                    cadence = 60000 / (t1 - self.t0)
                    # attempt to penalise low max_acceleration with high RPM
                    self.speed = (cadence + (self.max_acceleration * 1.5)) / 18
                    if self.speed < 0:
                        self.speed = 0
                    print('\033cSpeed: %.2f mph' % self.speed)
                    print('Actual RPM: %d' % cadence)
                    self.spm = int((120 + cadence * 8) / 6 )
                    print('Simulated RPM: %d' % self.spm)
                    changed = True
                self.t0 = t1
                self.max_acceleration = 0
        elif self.speed != 0:
            t1 = milli_time()
            if t1 - self.t0 > 2000:
                self.spm = 0
                self.speed = 0
                changed = True
                self.t0 = t1
                print('\033cSpeed: 0 mph')
        if changed:
            rsc_speed = self.speed * 114.44
            self.PropertiesChanged(GATT_CHRC_IFACE, { 'Value': [ dbus.Byte(0x00), dbus.Byte(int(rsc_speed) & 0xff), dbus.Byte((int(rsc_speed) >> 8) & 0xff), dbus.Byte(int(self.spm) & 0xff) ] }, [])
        return self.notifying

    def _update_rsc_msrmt_simulation(self):
        print('Update RSC Measurement Simulation')

        if not self.notifying:
            return

        GLib.timeout_add(10, self.rsc_msrmt_cb)

    def StartNotify(self):
        if self.notifying:
            return

        self.notifying = True
        self._update_rsc_msrmt_simulation()

    def StopNotify(self):
        if not self.notifying:
            return

        self.notifying = False
        self._update_rsc_msrmt_simulation()

def register_app_cb():
    print('GATT application registered')

def register_app_error_cb(error):
    global mainloop
    print('Failed to register application: ' + str(error))
    mainloop.quit()

def find_adapter(bus):
    remote_om = dbus.Interface(bus.get_object(BLUEZ_SERVICE_NAME, '/'),
                               DBUS_OM_IFACE)
    objects = remote_om.GetManagedObjects()
    
    for o, props in objects.items():
        if LE_ADVERTISING_MANAGER_IFACE in props and GATT_MANAGER_IFACE in props:
            return o
    
    return None

def main():
    global mainloop
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()
    mainloop = GLib.MainLoop()

    adapter = find_adapter(bus)
    if not adapter:
        print('LEAdvertisingManager1 interface not found')
        return
    adapter_props = dbus.Interface(bus.get_object(BLUEZ_SERVICE_NAME, adapter),
                                   "org.freedesktop.DBus.Properties");

    adapter_props.Set("org.bluez.Adapter1", "Powered", dbus.Boolean(1))

    adapter_props.Set("org.bluez.Adapter1", "Discoverable", dbus.Boolean(1))

    adapter_props.Set("org.bluez.Adapter1", "DiscoverableTimeout", dbus.UInt32(0))

    ad_manager = dbus.Interface(bus.get_object(BLUEZ_SERVICE_NAME, adapter),
                                LE_ADVERTISING_MANAGER_IFACE)

    rsc_advertisement = RSCAdvertisement(bus, 0)

    ad_manager.RegisterAdvertisement(rsc_advertisement.get_path(), {},
                                     reply_handler=register_ad_cb,
                                     error_handler=register_ad_error_cb)

    service_manager = dbus.Interface(
            bus.get_object(BLUEZ_SERVICE_NAME, adapter),
            GATT_MANAGER_IFACE)
    
    app = Application(bus)
    
    print('Registering GATT application...')
    
    service_manager.RegisterApplication(app.get_path(), {},
                                    reply_handler=register_app_cb,
                                    error_handler=register_app_error_cb)

    try:
        mainloop.run()
    except KeyboardInterrupt:
        rsc_advertisement.Release()
        mainloop.quit()

if __name__ == '__main__':
    main()
