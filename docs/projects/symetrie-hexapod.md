
# The Symétrie Hexapods


## Settings up your system for the PUNA Hexapod

!!! Warning

    We need some work here... we want to be able to use multiple hexapods in the same Setup and 
    they can be the same type or different types. So, how do we specify two PUNA hexapods used 
    to position two different parts of your test equiopment?  

The system needs to know the following information on the hexapod:

- device name: specified in the Setup under `setup.gse.hexapod.device_args.device_name`
- device id: specified in the Setup under `setup.gse.hexapod.device_args.device_id`

These above settings can olso be specified in the environment variables:

- SYMETRIE_HEXAPOD_NAME
- SYMETRIE_HEXAPOD_ID
