c = open('app/agents/controller_selection_agent.py', encoding='utf-8').read()

# Find the start and end of the broken controllers block
start = c.find('        if is_crcm:')
end = c.find('        reasons: List')

new_block = """        if is_crcm:
            controllers = [
                {"name": "L6563 (ST)", "type": "analog",
                 "reason": "Dedicated CrCM/TM PFC controller. Fixed off-time control."},
                {"name": "NCP1607 (ON Semi)", "type": "analog",
                 "reason": "Transition-mode PFC controller. Good for 200-600W."},
                {"name": "FAN6961 (ON Semi)", "type": "analog",
                 "reason": "CrCM PFC controller with green-mode standby."},
                {"name": "TI C2000", "type": "digital",
                 "reason": "Digital option for variable frequency CrCM control."},
            ]
        elif is_dcm:
            controllers = [
                {"name": "NCP1606 (ON Semi)", "type": "analog",
                 "reason": "DCM PFC controller. Best for low power under 150W."},
                {"name": "L6561 (ST)", "type": "analog",
                 "reason": "DCM/TM PFC controller. Simple and low cost."},
                {"name": "TI C2000", "type": "digital",
                 "reason": "Digital option for DCM control."},
            ]
        elif is_interleaved and n_phases == 3:
            controllers = [
                {"name": "FAN9613 (ON Semi)", "type": "analog",
                 "reason": "Dedicated 3-phase interleaved CCM PFC. Built-in 120 deg phase shift."},
                {"name": "UCC28070A x3 + sync (TI)", "type": "analog",
                 "reason": "Three UCC28070A with external 120 deg RC phase-shift network."},
                {"name": "TI C2000", "type": "digital",
                 "reason": "Digital option for 3-phase interleaved PFC."},
            ]
        elif is_interleaved and n_phases == 2:
            controllers = [
                {"name": "UCC28070A (TI)", "type": "analog",
                 "reason": "Dedicated 2-phase interleaved CCM PFC. 180 deg phase shift hardwired."},
                {"name": "NCP1631 (ON Semi)", "type": "analog",
                 "reason": "2-phase interleaved CCM PFC with dead-time and OVP/OCP."},
                {"name": "FAN9612 (ON Semi)", "type": "analog",
                 "reason": "Master-slave 2-phase interleaved CCM PFC."},
                {"name": "TI C2000", "type": "digital",
                 "reason": "Digital option for 2-phase interleaved PFC."},
            ]
        else:
            controllers = [
                {"name": "TI UC3854", "type": "analog",
                 "reason": "Classic single-phase CCM boost PFC analog controller."},
                {"name": "Infineon ICE3PCS01G", "type": "analog",
                 "reason": "Dedicated CCM PFC controller with integrated gate drive."},
                {"name": "ON NCP1654", "type": "analog",
                 "reason": "Fixed-frequency CCM PFC controller with burst mode."},
                {"name": "TI C2000", "type": "digital",
                 "reason": "Flexible DSP for adaptive tuning and digital PFC."},
                {"name": "STM32G4 + X-CUBE-MCSDK", "type": "digital",
                 "reason": "Cost-effective digital option with PFC support libraries."},
            ]
        """

c = c[:start] + new_block + c[end:]
open('app/agents/controller_selection_agent.py', 'w', encoding='utf-8').write(c)
print('Done')