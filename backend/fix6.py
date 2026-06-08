c = open('app/agents/controller_selection_agent.py', encoding='utf-8').read()

old = """        else:
            controllers = [
            {"name": "UCC28070A (TI)", "type": "analog",
             "reason": "2-phase interleaved CCM PFC. Built-in interleaving. Recommended for N=2."},
            {"name": "NCP1631 (ON Semi)", "type": "analog",
             "reason": "2-phase interleaved CCM PFC dedicated IC."},
            {"name": "FAN9612 (ON Semi)", "type": "analog",
             "reason": "2-phase interleaved CCM PFC with PFC master/slave."},
            {"name": "FAN9613 (ON Semi)", "type": "analog",
             "reason": "3-phase interleaved CCM PFC dedicated IC. Use for N=3."},"""

new = """        else:
            controllers = [
                {"name": "TI UC3854", "type": "analog",
                 "reason": "Classic single-phase CCM boost PFC analog controller."},
                {"name": "Infineon ICE3PCS01G", "type": "analog",
                 "reason": "Dedicated CCM PFC controller with integrated gate drive."},
                {"name": "ON NCP1654", "type": "analog",
                 "reason": "Fixed-frequency CCM PFC controller with burst mode."},"""

if old in c:
    c = c.replace(old, new, 1)
    open('app/agents/controller_selection_agent.py', 'w', encoding='utf-8').write(c)
    print('Done')
else:
    print('Pattern not found - printing context')
    idx = c.find('else:\n            controllers = [')
    print(repr(c[idx:idx+400]))