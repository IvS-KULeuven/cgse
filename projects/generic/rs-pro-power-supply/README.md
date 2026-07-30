# RS-PRO RS-3305P Power Supply

## Local Settings

This is what you need to add to your local settings file:

```yaml
RS-PRO RS-D3305P Controller:
    <arbitrary name to refer to the device>:
        SERIAL_NUMBER:      <serial number of the device, between quotes, e.g. "123456789">

RS-PRO RS-D3305P Control Server:
    PROTOCOL:     tcp
    <same arbitrary name to refer to the device>:
        SERVICE_TYPE:   <same arbitrary name to refer to the device>
        PROCESS_NAME:   <same arbitrary name to refer to the device>
        HOST:           <hostname on which the CS is running, e.g. "localhost">
        STORAGE_MNEMONIC: <same arbitrary name to refer to the device>

```

## Limitations

Initially, the idea was to connect to the RS-3305P power supply via an Ethernet cable and do the commanding via TCP/IP.  However, this only works for write commands and not for read commands.   Therefore, we use a serial connection instead.

The RS-3305P power supply has a USB port that can be used to connect to a computer via a USB cable.  The USB connection is recognised as a virtual COM port, which allows for serial communication with the power supply.

## Reference Documents

- RS-D3305P IP LAN Communication Protocol
- RS-D3305P Series Multiple Channel Remote Control Syntax v4.0
- RS-D3305P DC Power Supply Series User Manual
- [RS Pro D3305P - Python GUI Remote Controller](https://github.com/LucarVicti/rs-d3305p-gui-controller)
