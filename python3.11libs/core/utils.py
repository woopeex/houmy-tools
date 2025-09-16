from __future__ import print_function
import hou


# This script contains helper functions for linking parameters in Houdini.
# This script contains the optimized xferLinkParm function and its dependencies,
# extracted and refactored from the original pyro2.py script.

def isIterable(possibleIterable):
    ''' A quick utility to test whether the argument is iterable. '''
    try:
        iter(possibleIterable)
        return True
    except TypeError:
        return False


def xferTestCircular(src, dst):
    ''' Tests for a circular reference between parameters "src" and "dst". '''
    try:
        # Check if the destination parameter's path is in the source's expression
        if f'{dst.node().name()}/{dst.name()}' in src.expression():
            return True
    except:
        # An error can occur if the parameter does not have an expression
        pass
    return False


def xferDeanimateParm(dst):
    ''' De-animates a parameter by deleting all its keyframes. '''
    if dst.parmTemplate().type() == hou.parmTemplateType.Ramp:
        # For ramps, also de-animate all of its multi-parameter instances
        for p in dst.multiParmInstances():
            p.deleteAllKeyframes()

    # Preserve the current value for non-ramp parameters before removing keyframes
    if dst.parmTemplate().type() != hou.parmTemplateType.Ramp:
        currentValue = dst.eval()
        dst.deleteAllKeyframes()
        dst.set(currentValue)
    else:
        # For ramps, the value is held by the multi-parms, so just clear the parent
        dst.deleteAllKeyframes()


def xferRampMultiParmNames(parm):
    ''' Returns the names of the multi-parm components for a given ramp type. '''
    names = {
        hou.rampParmType.Float: ("pos", "value", "interp"),
        hou.rampParmType.Color: ("pos", "cr", "cg", "cb", "interp")
    }
    return names.get(parm.parmTemplate().parmType(), ())


def xferClearMultiParms(parm):
    ''' Clears all multi-parameter instances from a ramp parameter. '''
    mNames = xferRampMultiParmNames(parm)
    pName = parm.name()

    # Construct and execute an hscript command to clear the multi-parms
    hscriptCommand = f'opmultiparm {parm.node().path()} '
    for mn in mNames:
        hscriptCommand += f'"{pName}#{mn}" "" '

    hou.hscript(hscriptCommand)


def xferKillRampCircular(src, dst):
    ''' Resolves a circular reference between two ramp parameters. '''
    for p in src.multiParmInstances():
        p.deleteAllKeyframes()
    xferClearMultiParms(src)
    xferDeanimateParm(src)
    src.set(dst.eval())


def xferKillCircular(src, dst):
    ''' Resolves a circular reference between parameters. '''
    sourceParms = src if isIterable(src) else (src,)
    destParms = dst if isIterable(dst) else (dst,)

    for sParm in sourceParms:
        for dParm in destParms:
            if xferTestCircular(sParm, dParm):
                if sParm.parmTemplate().type() == hou.parmTemplateType.Ramp:
                    xferKillRampCircular(sParm, dParm)
                else:
                    xferDeanimateParm(sParm)
                # Once resolved for sParm, move to the next source parameter
                break


def xferLinkPath(src, dst, relPath=False):
    ''' Gets the path to a 'src' parameter, optionally relative to 'dst'. '''
    if relPath:
        sNode = src.node() if isinstance(src, hou.Parm) else src
        dNode = dst.node() if isinstance(dst, hou.Parm) else dst
        path = dNode.relativePathTo(sNode)
        if isinstance(src, hou.Parm):
            path += f'/{src.name()}'
    else:
        path = src.path()
    return path


def xferAlreadyLinked(src, dst):
    ''' Checks if the destination parameter is already referencing the source. '''
    return dst.getReferencedParm() == src


def xferLinkRampMultiParms(src, dst, relPath):
    ''' Links the multi-parameter instances of two ramp parameters. '''
    if dst.parmTemplate().parmType() != src.parmTemplate().parmType():
        return

    mpNames = xferRampMultiParmNames(dst)
    dstName = dst.name()
    srcPath = xferLinkPath(src, dst, relPath)

    # Add an underscore if the name ends in '#' or a digit to avoid ambiguity
    if dstName[-1] == '#' or dstName[-1].isdigit():
        dstName += '_'
    if srcPath[-1] == '#' or srcPath[-1].isdigit():
        srcPath += '_'

    # Construct and execute an hscript command to link the multi-parms
    hscriptCommand = f'opmultiparm {dst.node().path()} '
    for mn in mpNames:
        hscriptCommand += f'"{dstName}#{mn}" "{srcPath}#{mn}" '

    hou.hscript(hscriptCommand)


def xferLinkRamp(src, dst, relPath=False):
    ''' Links a destination ramp parameter to a source ramp parameter. '''
    xferKillCircular(src, dst)
    if xferAlreadyLinked(src, dst):
        return

    xferClearMultiParms(dst)
    xferDeanimateParm(dst)

    linkPath = xferLinkPath(src, dst, relPath)
    dst.setExpression(f'parm("{linkPath}").evalAsInt()', hou.exprLanguage.Python, True)
    dst.set(src.eval())

    # Link the individual multi-parm instances
    for pDst, pSrc in zip(dst.multiParmInstances(), src.multiParmInstances()):
        instanceLinkPath = xferLinkPath(pSrc, pDst, relPath)
        pDst.setExpression(f'ch("{instanceLinkPath}")', hou.exprLanguage.Hscript, True)

    xferLinkRampMultiParms(src, dst, relPath)


def xferLinkParm(src, dst, relPath=False):
    ''' Makes a destination parameter reference a source parameter. '''
    if xferAlreadyLinked(src, dst):
        return

    xferKillCircular(src, dst)
    xferDeanimateParm(dst)

    if dst.parmTemplate().type() == hou.parmTemplateType.Ramp:
        xferLinkRamp(src, dst, relPath)
    else:
        linkPath = xferLinkPath(src, dst, relPath)
        dst.setExpression(f'ch("{linkPath}")', hou.exprLanguage.Hscript, True)


# -- New Simplified Function --

def linkParameters(sourceParm, destParm, useRelativePath=False):
    """
    A simplified, high-level function to create a parameter link from a source to a destination.

    This function safely handles both standard parameter types (float, int, string)
    and complex multi-parameter ramps, ensuring that circular references are resolved
    and existing animations on the destination parameter are cleared.

    Args:
        sourceParm (hou.Parm): The parameter to be referenced.
        destParm (hou.Parm): The parameter that will reference the source.
        useRelativePath (bool): If True, the generated expression will use a
                                  relative path from destParm's node to sourceParm's node.
                                  Defaults to False (absolute path).
    """
    if not isinstance(sourceParm, hou.Parm) or not isinstance(destParm, hou.Parm):
        return

    # Use the robust, underlying xferLinkParm function to perform the link
    xferLinkParm(sourceParm, destParm, relPath=useRelativePath)
