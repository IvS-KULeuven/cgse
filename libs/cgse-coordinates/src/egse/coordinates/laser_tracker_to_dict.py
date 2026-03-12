import sys
import pandas

from egse.setup import Setup


def laser_tracker_to_dict(file_xls: str, setup: Setup):
    """Reads the laser tracker file and returns a dictionary of reference frames.

    Args:
        file_xls (str): Path to the laser tracker file.  This is an excell sheet provided by CSL.
        setup (Setup): Setup object containing the default reference frames.

    Known Features:
        - no link can be included:
                the links are not in the xls file
                hardcoding them would cause trouble when ingesting a partial model
        - the ReferenceFrames references are included, but they are based
          on a hardcoded model.
          In particular, it is assumed that gliso is the master!

        - a "Master" ReferenceFrame is enforced, with the name "Master" (capital)

        - the names of the reference frames are returned lowercase, without '_'
          ("Master" is an exception)

    Returns:
        Dictionary of reference frames compatible with egse.coordinates.dict_to_ref_model.
    """

    # Predefined model -- gliso ~ master

    """
    predef_refs={}
    predef_refs['gltab']  = 'glfix'
    predef_refs['glfix']  = 'glrot'
    predef_refs['glrot']  = 'gliso'

    predef_refs['gliso']  = 'Master'
    predef_refs['Master'] = 'Master'

    predef_refs['hexiso'] = 'gliso'
    predef_refs['hexmec'] = 'hexiso'
    predef_refs['hexplt'] ='hexmec'
    predef_refs['hexobj'] = 'hexplt'
    predef_refs['hexobusr'] = 'hexusr'
    predef_refs['hexusr'] = 'hexmec'
    predef_refs['fpaaln'] = 'gliso'
    predef_refs['fpasen'] = 'fpaaln'
    predef_refs['fpamec'] = 'fpaaln'
    predef_refs['toumec'] = 'gliso'
    predef_refs['toul6'] = 'toumec'
    predef_refs['toualn'] = 'toumec'
    predef_refs['touopt'] = 'toualn'
    predef_refs['marialn'] = 'toualn'
    predef_refs['cammec'] = 'toualn'
    predef_refs['cambor'] = 'toualn'
    """

    predef_refs = setup.csl_model.default_refs

    # Read input file

    pan = pandas.read_excel(file_xls, sheet_name="Data", usecols="A:D", names=["desc", "x", "y", "z"])

    num_rows = pan.shape[0]

    desc = pan["desc"].values
    colx = pan["x"].values
    coly = pan["y"].values
    colz = pan["z"].values

    reference_frames = dict()
    reference_frames["Master"] = (
        "ReferenceFrame//([0.0000,0.0000,0.0000 | [0.0000,0.0000,0.0000 | Master | Master | [])"
    )

    links = "[]"

    i, frame = -1, -1
    while i < num_rows:
        i += 1

        try:
            frame = desc[i].find("Frame")
        except:
            frame = -1
            continue

        if frame >= 0:
            try:
                name = desc[i][desc[i].find("::") + 2 :].lower().replace("_", "")

                if (desc[i + 2].lower().find("translation") < 0) or (desc[i + 3].lower().find("rotation") < 0):
                    raise Exception(f"Unexpected File Structure after row {i} : {desc[i]}")

                translation = f"[{float(colx[i + 2]):.6f},{float(coly[i + 2]):.6f},{float(colz[i + 2]):.6f}"
                rotation = f"[{float(colx[i + 3]):.6f},{float(coly[i + 3]):.6f},{float(colz[i + 3]):.6f}"

                if name in predef_refs.keys():
                    ref = predef_refs[name]
                else:
                    ref = "None"

                reference_frames[name] = f"ReferenceFrame//({translation} | {rotation} | {name} | {ref} | {links})"

            except:
                print(f"Frame extraction issue after row {i} : {desc[i]}")
                print(sys.exc_info())

    return reference_frames
