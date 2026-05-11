from egse.hexapod.symetrie.joran import JoranProxy, JoranSimulator

print("HEX 1 - CONNECING TO Joran Hexapod")
hex1id = "JORAN_01"
hex1hw = JoranProxy(hex1id)
try:
    hex1hw.connect_cs()
    print(f"HEX 1 - CONNECTED TO REAL HARDWARE : {hex1hw.device_id}")
except ConnectionError:
    hex1hw = JoranSimulator(hex1id)
    print(f"HEX 1 - CONNECTED TO SIMULATOR : {hex1hw.device_id}")

if isinstance(hex1hw, JoranProxy):
    hex1hw.disconnect_cs()
    print(f"HEX 1 - DISCONNECTED FROM REAL HARDWARE : {hex1hw.device_id}")
