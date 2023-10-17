#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Wed Sep  9 17:19:47 2020

@author: pierre
"""
import numpy as np
from egse.state import GlobalState
from egse.coordinates.point import Points


def is_avoidance_ok(hexusr,hexobj,setup=None,verbose=False):
    """
    is_avoidance_ok(hexusr,hexobj,setup=None)
    
    INPUT
    hexusr : ReferenceFrame 
             xy plane = maximal height of the FPA_SEN
             z axis  pointing away from the FPA
             
    hexobj : ReferenceFrame
             xy plane = FPA_SEN
             z axis pointing towards L6
             
    setup  : GlobalSetup.setup, optional
             if not provided, GlobalState.setup is used
    
    
    OUTPUT :  Boolean indicating wheather or not the FPA is outside of the avoidance volume around L6
    """
        
    if setup is None:
        setup = GlobalState.setup
    
    """
    A. HORIZONTAL AVOIDANCE
    Ensure that the center of L6, materialised by HEX_USR (incl. z-direction security wrt TOU_L6)
    stays within a given radius of the origin of FPA_SEN
    """

    # Clearance = the tolerance in every horizontal direction (3 mm; PLATO-KUL-PL-ICD-0001 v1.2)
    clearance_xy = setup.camera.fpa.avoidance.clearance_xy
    
    # l6xy = the projection of the origin of HEX_USR on the X-Y plane of FPA_SEN
    l6xy = hexusr.getOrigin().expressIn(hexobj)[:2]
    
    # !! This is a verification of the current situation --> need to replace by a simulation of the forthcoming movement in the building block
    horizontal_check = ((l6xy[0]**2.+l6xy[1]**2.) < clearance_xy*clearance_xy)
    
    
    """
    B. VERTICAL AVOIDANCE
    Ensure that the CCD never hits L6.
    The definition of HEX_USR includes a tolerance below L6 (1.65 mm)
    We include a tolerance above FPA_SEN here (0.3 mm)
    We define a collection of points to act at the vertices of the avoidance volume above the FPA
    """

    # Clearance = vertical uncertainty on the CCD location (0.3 mm; PLATO-KUL-PL-ICD-0001 v1.2)
    clearance_z = setup.camera.fpa.avoidance.clearance_z
    
    # Vertices = Points representing the vertices of the avoidance volume above the FPA (60)
    vertices_nb     = setup.camera.fpa.avoidance.vertices_nb
    # All vertices are on a circle of radius 'vertices_radius' (100 mm)
    vertices_radius = setup.camera.fpa.avoidance.vertices_radius
    
    angles = np.linspace(0,np.pi * 2,vertices_nb,endpoint=False)
    vertices_x = np.cos(angles) * vertices_radius
    vertices_y = np.sin(angles) * vertices_radius
    vertices_z = np.ones_like(angles) * clearance_z
    
    # The collection of Points defining the avoidance volume around FPA_SEN
    vert_obj = Points(coordinates=np.array([vertices_x,vertices_y,vertices_z]),ref=hexobj,name="vert_obj")
    
    # Their coordinates in HEX_USR
    # NB: vert_obj is a Points, vert_usr is an array
    vert_usr = vert_obj.expressIn(hexusr)
    
    
    # !! Same as above : this is verifying the current situation, not the one after a planned movement
    # Verify that all vertices ("protecting" FPA_SEN) are below the x-y plane of HEX_USR ("protecting" L6)
    vertical_check = (np.all(vert_usr[2,:] < 0.))
    
    if verbose:
        printdict = {True:"OK", False:"NOT OK"}
        print(f"HORIZONTAL AVOIDANCE: {printdict[horizontal_check]}")
        print(f" VERTICAL  AVOIDANCE: {printdict[vertical_check]}")
    
    if verbose > 1:
        print(f"Points Coordinates")
        coobj = vert_obj.coordinates
        for i in range(vertices_nb):
            print(f"{i} OBJ {np.round(coobj[:3,i],6)} --> USR {np.round(vert_usr[:3,i],6)}")
        vert_z = vert_usr[2,:]
        vert_zi = np.where(vert_z==np.max(vert_z))
        print(f"#vertices at max z : {len(vert_zi[0])}")
        print(f"First one: vertex {vert_zi[0][0]} : {np.round(vert_usr[:3,vert_zi[0][0]],6)}")

    return horizontal_check and vertical_check



