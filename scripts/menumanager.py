'''
{
    'locked_parms': (), 
    'parms': (<hou.Parm slider in /obj/geo1/attribwrangle1>,), 
    'toolname': 'h.pane.parms.m_one', 
    'altclick': False, 
    'ctrlclick': False, 
    'shiftclick': False, 
    'cmdclick': False}

'''

print(f"Toolname: {kwargs['toolname']}")

for parm in kwargs['parms']:
    print(parm, type(parm))
    print(parm.parmTemplate())

    