# Python BLE GATT Server for Raspberry Pi Zero W and ADXL345 accelerometer
This GATT server uses acceleration data from the ADXL345 to provide a Running Speed and Cadence service which works with Zwift.

## Requirements
- Raspberry Pi Zero W / WH installed with (at least) Raspbian Buster Lite
- ADXL345 accelerometer connected to Raspberry Pi
- Elliptical trainer or similar (tested with New Image Maxi-Glider 360)
- Power source (e.g. USB power bank)

Older versions of Raspbian may work but they will most likely require to have Bluez updated. The code may also work perfectly well on a different model of Raspberry Pi with a BLE dongle.

## Setup
The accelerometer should be attached to one of the footrests and oriented in such a way that the acceleration is detected on the X-axis. (For both models of ADXL345 I have tried - one with pins at both ends, and one with a single row of pins - the pins should be parallel with the footrest.) I also have the Pi taped securely to the underside of the footrest along with a nano-suction power bank.

(Optionally) update the Pi:
```
apt-get update
apt-get dist-upgrade
```

Install the required packages:
```
apt-get -y install python3-pip
pip3 install adafruit-circuitpython-adxl34x
```

Place *pielliptical.py* in */usr/local/bin* and make it executable:
```
mv pielliptical.py /usr/local/bin
chmod 755 /usr/local/bin/pielliptical.py
```

Using ```raspi-config``` enable **I2C** under *Interfacing Options*. I also set *Desktop / CLI* to **Console** under *Boot Options*, and *Memory Split* to **16** under *Advanced Options* as I don't require a graphical login. The Pi will need to be rebooted for these changes to take effect.

## Usage
Run **/usr/local/bin/pielliptical.py** to test the script and verify that the device shows up (probably as *raspberrypi* followed by a number) within Zwift when searching for a *Run Speed* device. It can take a few seconds for initial detection. The raspberrypi device does not need to be calibrated within Zwift.

The device has been tested successfully with the following configurations:
- Zwift on Windows 10 + Zwift Companion on Wileyfox Swift 2X running LineageOS 15.1
- Zwift on Windows 10 + Zwift Companion on Amazon Fire 7 running LineageOS 14.1
- Zwift on Wileyfox Swift 2X running LineageOS 15.1

To have the service run automatically on boot, edit */etc/rc.local* and insert the following before *exit 0*:
```
/usr/local/bin/pielliptical.py > /dev/null 2>&1
```

I also added ``tvservice --off`` above this line as I don't need HDMI output.

## Troubleshooting
If the raspberrypi device still hasn't shown up in Zwift after a minute or so, try killing Zwift Companion entirely and restarting it, or restarting the Android device it is running on. (BLE seems to be less reliable than ANT+ in this regard.)

## Advanced Usage
- Configure Pi to run entirely in read-only mode so it can be powered off safely
- Disable wi-fi entirely for faster startup

## Notes
It should be possible to complete running workouts successfully with a minimum of practice.

I estimated that a cadence of 120 steps per minute was equivalent in effort to a 6-minute mile. It is suitably hard to maintain for a long period of time, even if it is easier than actually running due to the non-impact nature of an elliptical trainer. A simple formula is applied to the detected cadence to make it look more like an actual running cadence.

## Bugs
- There is probably something wrong with the Bluetooth advertisement, since the Pi cannot be detected in Zwift on Windows using a Bluetooth adapter, and is slow to be detected from Zwift on Android or via Zwift Companion.

## Licence
The code in this repository is based on code taken from the [BlueZ](http://www.bluez.org/) project. It is licensed under GPL 2.0.
