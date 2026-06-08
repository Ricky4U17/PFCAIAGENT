c = open('app/agents/controller_selection_agent.py', encoding='utf-8').read()

new_controllers = '''        n_phases = state.get("selected_channels", 2) or 2
        controllers = [
            {"name": "UCC28070A (TI)", "type": "analog",
             "reason": "2-phase interleaved CCM PFC. Built-in interleaving. Recommended for N=2."},
            {"name": "NCP1631 (ON Semi)", "type": "analog",
             "reason": "2-phase interleaved CCM PFC dedicated IC."},
            {"name": "FAN9612 (ON Semi)", "type": "analog",
             "reason": "2-phase interleaved CCM PFC with PFC master/slave."},
            {"name": "FAN9613 (ON Semi)", "type": "analog",
             "reason": "3-phase interleaved CCM PFC dedicated IC. Use for N=3."},
            {"name": "TI UC3854", "type": "analog",
             "reason": "Classic single-phase CCM boost PFC analog controller."},
            {"name": "Infineon ICE3PCS01G", "type": "analog",
             "reason": "Dedicated CCM PFC controller with integrated gate drive."},
            {"name": "TI C2000", "type": "digital",
             "reason": "Flexible DSP for adaptive tuning and digital PFC."},
            {"name": "STM32G4 + X-CUBE-MCSDK", "type": "digital",
             "reason": "Cost-effective digital option with PFC support libraries."},
            {"name": "Designer supplied controller", "type": "analog_or_digital",
             "reason": "Use your existing platform."},
        ]'''

old = '        controllers = ['
c = c.replace(old, new_controllers, 1)
open('app/agents/controller_selection_agent.py', 'w', encoding='utf-8').write(c)
print('Done')