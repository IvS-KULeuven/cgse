# Developer Guide

Welcome to the CGSE developer guide! An in-depth reference on how to contribute to the CGSE.

First thing to know is that this repository is actually a monorepo, meaning it contains a bunch of
related but self-standing packages with a minimum of interdependencies. A monorepo can grow quite
big and can contain a lot of packages that even different groups are working on. What they have in
common is that they use the same guidelines and have the same or a very similar development 
workflow.

Don't confuse a monorepo with a _monolith_ or a _monolithic architecture_. While a monorepo holds
multiple related but more-or-less independent projects, a monolith is a traditional software
application or architecture which is an often huge, self-contained and independent unit of code that
is highly coupled and difficult to maintain.

Don't confuse a monorepo with microservices either. A microservice architecture contains units that
run independently and are developed, scaled and deployed without affecting the other units or
services. You can set up a monorepo containing all of your microservices with ease, one does not
need the other, but they can perfectly go together.
