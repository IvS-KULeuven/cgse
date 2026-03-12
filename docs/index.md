---
hide:
    - toc
    - navigation
---

!!! tip inline end

    See the navigation links in the header or side-bar.

    Click :octicons-three-bars-16: (top left) on mobile.

# Welcome

Welcome to the [CGSE](https://github.com/IvS-KULeuven/cgse) framework
documentation.

[Get started](./getting_started.md){ .md-button .md-button--primary } or go
straight to the [Tutorial](./tutorial.md)

## What is the CGSE?

The CGSE (Common-EGSE) is a comprehensive framework for managing and operating
test equipment in laboratory environments. EGSE stands for Electrical Ground
Support Equipment, encompassing all hardware and software systems used to test,
calibrate, and validate space instruments throughout their development
lifecycle.

The CGSE architecture typically includes:

- Computing infrastructure: A dedicated server running the CGSE software suite
  for test execution, data collection, and archiving, paired with client
  workstations that provide user interfaces for equipment control and monitoring

- Temperature control systems: Precision controllers that regulate thermal
  conditions by managing heaters and continuously monitoring temperature
  sensors, essential for thermal vacuum testing and temperature calibration
  procedures

- Mechanism controllers: Specialized systems that operate positioning equipment
  such as hexapods (six-degree-of-freedom motion platforms), linear stages,
  rotation stages, and other mechanical actuators with high precision

- Optical test equipment: Controllers for various optical instruments including
  lasers, light sources, attenuators, spectrometers, and optical power meters
  used in optical alignment and performance verification

- Additional instrumentation: Any measurement or control device with network
  connectivity (Ethernet, USB) and an accessible API, including power supplies,
  signal generators, multimeters, oscilloscopes, and custom test fixtures

The CGSE framework provides standardized interfaces, automated test sequences,
data management capabilities, and synchronization between these diverse systems,
enabling reproducible and efficient testing campaigns.
