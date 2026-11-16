
# The Symétrie Hexapods


## Settings up your system for the PUNA Hexapod

!!! Warning

    We need some work here... we want to be able to use multiple hexapods in the same Setup and 
    they can be the same type or different types. So, how do we specify two PUNA hexapods used 
    to position two different parts of your test equiopment?  

The system needs to know the following information on the hexapod, in its node in the Setup (see
[The Setup](../libs/cgse-common/setup.md)):

- device name: `setup.gse.hexapod.device_name`
- device id: `setup.gse.hexapod.device_id`, the argument of `cgse puna start <device_id>`, e.g. `PUNA_01`

These above settings can olso be specified in the environment variables:

- SYMETRIE_HEXAPOD_NAME
- SYMETRIE_HEXAPOD_ID
