c = open('app/agents/controller_selection_agent.py', encoding='utf-8').read()

old = '        controllers = ['

new = '''        topo = (topology or '').lower()
        is_interleaved = 'interleaved' in topo
        is_crcm = 'crcm' in topo or 'crm' in topo
        is_dcm  = 'dcm' in topo
        n_phases = state.get('selected_channels', 2) or 2

        if is_crcm:
            controllers = [
                {"name": "L6563 (ST)", "type": "analog",
                 "reason": "Dedicated CrCM/TM PFC controller. Fixed off-time control."},
                {"name": "NCP1607 (ON Semi)", "type": "analog",
                 "reason": "Transition-mode PFC controller. Good for 200-600W."},
                {"name": "FAN6961 (ON Semi)", "type": "analog",
                 "reason": "CrCM PFC controller with green-mode standby."},
                {"name": "UCC28051 (TI)", "type": "analog",
                 "reason": "Transition-mode PFC. Simple implementation."},
            ]
        elif is_dcm:
            controllers = [
                {"name": "NCP1606 (ON Semi)", "type": "analog",
                 "reason": "DCM PFC controller. Best for low power under 150W."},
                {"name": "L6561 (ST)", "type": "analog",
                 "reason": "DCM/TM PFC controller. Simple and low cost."},
                {"name": "UCC28051 (TI)", "type": "analog",
                 "reason": "Supports DCM operation. Flexible frequency."},
            ]
        elif is_interleaved and n_phases == 3:
            controllers = [
                {"name": "FAN9613 (ON Semi)", "type": "analog",
                 "reason": "Dedicated 3-phase interleaved CCM PFC. Built-in 120 deg phase shift. No external sync needed."},
                {"name": "UCC28070A x3 + sync (TI)", "type": "analog",
                 "reason": "Three UCC28070A with external 120 deg RC phase-shift network."},
            ]
        elif is_interleaved and n_phases == 2:
            controllers = [
                {"name": "UCC28070A (TI)", "type": "analog",
                 "reason": "Dedicated 2-phase interleaved CCM PFC. 180 deg phase shift hardwired."},
                {"name": "NCP1631 (ON Semi)", "type": "analog",
                 "reason": "2-phase interleaved CCM PFC with dead-time and OVP/OCP."},
                {"name": "FAN9612 (ON Semi)", "type": "analog",
                 "reason": "Master-slave 2-phase interleaved CCM PFC."},
            ]
        else:
            controllers = ['''

c = c.replace(old, new, 1)
open('app/agents/controller_selection_agent.py', 'w', encoding='utf-8').write(c)
print('Done')