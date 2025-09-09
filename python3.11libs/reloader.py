import sys

#DEFAULT_RELOAD_PACKAGES = ['hmq', 'hmq.gui', 'hmq.utils']
#DEFAULT_RELOAD_PACKAGES = ['hmq_editor']


DEFAULT_RELOAD_PACKAGES = ['gui', 'core']


def unload(silent=True, packages=None):
    """
    Performs unloading of specified packages from sys.modules.

    Args:
        silent (bool): If True, suppresses printing of unloaded modules. If False, prints each unloaded module.
        packages (list or None): List of package names to unload. If None, uses DEFAULT_RELOAD_PACKAGES.
    """
    
    if packages is None:
        packages = DEFAULT_RELOAD_PACKAGES
        
    # construct reload list
    reloadList = [] 
    for i in sys.modules.keys():
        for package in packages:
            if i.startswith(package):
                reloadList.append(i)

    # unload everything
    for i in reloadList:
        try:
            if sys.modules[i] is not None:
                del(sys.modules[i])
                if not silent:
                    print("unloaded ", i)
        except:
            print("failed to unload ", i)