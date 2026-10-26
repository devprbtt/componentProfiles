"""Build standalone Savant XMLs for the Hisense native TCP/7310 service.

Python is only a build tool; the generated profiles need no Python at runtime.
"""
import copy
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from native_serial_probe import frame

ROOT = Path(__file__).resolve().parent
ET.register_namespace('xsi', 'http://www.w3.org/2001/XMLSchema-instance')

BUTTONS = {
    'PowerToggle': 1012, 'Play': 1016, 'Pause': 1018, 'Stop': 1020,
    'Rewind': 1015, 'ScanDown': 1015, 'FastForward': 1017, 'ScanUp': 1017,
    'Home': 1039, 'Apps': 1039, 'SmartHub': 1039, 'Internet@TV': 1039,
    'Menu': 1038, 'Exit': 1046, 'Back': 1045, 'Return': 1045,
    'ExitSmartTVMenu': 1045, 'Select': 1040, 'Enter': 1040, 'NumberEnter': 1040,
    'OSDCursorUp': 1041, 'OSDCursorDown': 1042,
    'OSDCursorLeft': 1043, 'OSDCursorRight': 1044,
    'IncreaseVolume': 1033, 'DecreaseVolume': 1032,
    'ChannelAnalogUp': 1034, 'ChannelDigitalUp': 1034,
    'ChannelAnalogDown': 1035, 'ChannelDigitalDown': 1035,
    'Red': 1050, 'Green': 1051, 'Blue': 1052, 'Yellow': 1053,
    'ATriangle': 1050, 'BSquare': 1051, 'CCircle': 1053, 'DDiamond': 1052,
    'A': 1050, 'B': 1051, 'C': 1053, 'D': 1052,
    'Dash': 1010, 'Source': 1036, 'ClosedCaptions': 1027,
    'MediaPlayer': 1023, 'MTS': 1054,
    'SelectInternalInputMediaPlayer': 1039, 'SelectInputInput Smart TV': 1039,
}
for i, word in enumerate(('Zero', 'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight', 'Nine')):
    BUTTONS['Number' + word] = 1000 + i

STATIC = {
    'PowerOn': ('POWR', '0001'), 'PowerOff': ('POWR', '0000'),
    'MuteOn': ('MUTE', '0001'), 'MuteOff': ('MUTE', '0000'),
    'SelectInputHDMI1': ('INPT', '0009'), 'SelectInputHDMI2': ('INPT', '0010'),
    'SelectInputHDMI3': ('INPT', '0011'), 'SelectInputHDMI4': ('INPT', '0012'),
    'SelectInputTVTuner': ('INPT', '0001'), 'SelectInputAV1': ('INPT', '0004'),
    'SelectInputComponent': ('INPT', '0003'),
}


def element(parent, tag, text=None, **attrs):
    e = ET.SubElement(parent, tag, attrs)
    e.text = text
    return e


def call(action, name, delay=0):
    return element(action, 'execute_action_after_delay', ms_delay=str(delay),
                   action_name=name, action_type='CUSTOM')


def command(parent, operation, opcode, value, query=None, ack_updates=()):
    interface = parent.find("command_interface[@interface='ip']")
    if interface is None:
        interface = element(parent, 'command_interface', interface='ip')
    cmd = element(interface, 'command', response_required='yes', response_time_length_ms='1500')
    # Fixed frames avoid assuming an undocumented Savant checksum algorithm.
    element(cmd, 'command_string', frame(operation, opcode, value).hex().upper(), type='hex')
    codes = element(cmd, 'response_codes')
    rsp = element(codes, 'rspmessage', status='success', name='Hisense' + (query or 'Ack'))
    # receive_start_condition consumes ALL: and discards the command echo.
    element(rsp, 'constant', 'OkAY', type='character')
    if query:
        data = element(rsp, 'data', type='character', constant_length='4')
        if query == 'Volume':
            element(data, 'update', state='CurrentVolume', type='integer')
        elif query in ('Power', 'Mute'):
            binding = 'CurrentPowerStatus' if query == 'Power' else 'CurrentMuteStatus'
            data_map = element(data, 'data_map', match_required='yes')
            for raw, state in [('0000', 'OFF'), ('0001', 'ON')]:
                match = element(data_map, 'map', key=raw)
                element(match, 'update', state, state=binding, type='string')
        else:
            element(data, 'update', state='NativeInput', type='string')
    elif ack_updates:
        data = element(rsp, 'data', type='character', constant_length='4')
        mapping = element(data, 'data_map', match_required='yes')
        match = element(mapping, 'map', key='####')
        for binding, value in ack_updates:
            element(match, 'update', value, state=binding, type='string')
    else:
        element(rsp, 'constant', '####', type='character')
    failure = element(codes, 'rspmessage', status='failure', name='HisenseError')
    element(failure, 'constant', 'EROR', type='character')
    element(cmd, 'delay', ms_delay='100')
    return cmd


def build(source):
    tree = ET.parse(source)
    root = tree.getroot()
    root.set('model', root.get('model') + ' (Native IP)')
    root.set('alias', root.get('alias') + ' Native IP')
    root.set('rpm_xml_version', '10.0')
    root.find('notes').text = '''
Native IP candidate: direct persistent TCP to the TV on port 7310.
Enable Settings > Channels & Inputs > External Inputs > Serial/IP Control Port.
No bridge, Android TV pairing code, or Samsung AccessToken is used.
Both profile instances use the same TV IP address. The media routing is retained.
Do not use non-persistentTCP or open/close a socket per command: this TV's service
stopped responding after early disconnects during discovery. If it stops accepting
connections, toggle Serial/IP Control Port off/on using the physical remote.
No automatic command retries: a retry can double a relative volume/navigation key.
The TV echoes requests and replies with case-sensitive ALL:OkAY, not ALL:OKAY.
Power/volume/mute/input queries update states from actual TV responses.
Absolute volume uses 101 guarded static-frame helpers (0-100), avoiding assumptions
about the engine's checksum algorithms. Helper actions are not user controls.
Apps/SmartHub opens Home; direct app launch and other absent actions are unsupported.
Other HDMI ports, tuner and legacy keys need validation.
Validated on the live TV: volume read/set, volume +/- buttons, mute on/off/read,
power read/off, HDMI 1, Home; two simultaneous TCP sessions. See docs/hisense-native-ip.md.
Standby disabled TCP networking. A single broadcast Wake-on-LAN packet to UDP 9
woke this TV and power query then returned 0001 without a TCP power-on command.
Configure Savant's wake workflow with the TV MAC before TCP PowerOn; these XMLs
do not yet emit WOL themselves. TCP PowerOn alone cannot wake this TV in standby.
These XMLs still require validation with the installed Savant schema and Blueprint.
'''
    properties = root.find('component_properties')
    setup = properties.find('smart_tv_setup')
    if setup is not None:
        properties.remove(setup)
    interfaces = root.find('control_interfaces')
    interfaces.clear()
    interfaces.set('preferred', 'ip')
    ip = element(interfaces, 'ip', port='7310', protocol='tcp',
                 response_time_length_ms='1500', name_on_component='LAN')
    element(ip, 'receive_start_condition', 'ALL:', type='character', test_condition='data')
    # CR alone may also occur in the checksum. The TV terminates ACKs with CRLF.
    element(ip, 'receive_end_condition', '0D0A', type='hex', test_condition='data')
    for control in root.findall("./media_interfaces/data[@name_on_component='LAN']//control"):
        control.set('port', '7310')
    variables = root.find('state_variable_list')
    token = variables.find("state_variable[@name='AccessToken']")
    if token is not None:
        variables.remove(token)
    for name, default in [('NativeRequestedVolume', '-1'), ('NativeInput', 'UNKNOWN')]:
        element(variables, 'state_variable', default, name=name, owning_logical_component='HD_monitor',
                state_center_binding=name, state_center_type='integer' if name.endswith('Volume') else 'string')
    logical = root.find('logical_component')
    custom = logical.find('custom_component_actions')
    omitted = []
    mapped = []
    for group in list(logical):
        if not group.tag.endswith('component_actions'):
            continue
        for action in list(group):
            name = action.get('name')
            if name not in BUTTONS and name not in STATIC and name != 'SetVolume':
                omitted.append({'group': group.get('resource_type', group.tag), 'action': name})
                group.remove(action)
                continue
            arguments = [copy.deepcopy(x) for x in action.findall('action_argument')]
            action.clear()
            action.set('name', name)
            for argument in arguments:
                action.append(argument)
            if name == 'SetVolume':
                action.find('action_argument').set('note', 'TV volume 0-100, integer')
                element(action, 'update_state_variable', 'VolumeValue', name='NativeRequestedVolume',
                        update_type='set', update_source='action_argument')
                for level in range(101):
                    call(action, f'NativeVolume{level:03d}')
                call(action, 'QueryVolumeStatus', 500)
            else:
                opcode, value = STATIC.get(name, ('BTTN', str(BUTTONS.get(name, 0))))
                updates = [('CurrentPowerStatus', 'OFF' if name == 'PowerOff' else 'ON')] if name in ('PowerOn', 'PowerOff') else ()
                command(action, 'S', opcode, value, ack_updates=updates)
                if name in ('PowerOn', 'PowerOff', 'PowerToggle'):
                    call(action, 'QueryPowerStatus', 1500)
                elif name in ('IncreaseVolume', 'DecreaseVolume'):
                    call(action, 'QueryVolumeStatus', 300)
                elif name in ('MuteOn', 'MuteOff'):
                    call(action, 'QueryMuteStatus', 300)
                elif opcode == 'INPT':
                    call(action, 'QueryInputStatus', 1000)
            mapped.append({'group': group.get('resource_type', group.tag), 'action': name})
    # Repair selection references already missing from the source profiles.
    for name in ('SelectInternalInputMediaPlayer', 'SelectInputInput Smart TV'):
        if root.find(f".//action_to_select[@name='{name}']") is not None:
            action = element(custom, 'action', name=name)
            command(action, 'S', 'BTTN', '1039')
    for name, opcode, kind in [('QueryPowerStatus', 'POWR', 'Power'),
                               ('QueryVolumeStatus', 'VOLM', 'Volume'),
                               ('QueryMuteStatus', 'MUTE', 'Mute'),
                               ('QueryInputStatus', 'INPT', 'Input')]:
        action = element(custom, 'action', name=name)
        command(action, 'Q', opcode, '????', query=kind)
    poll = element(custom, 'action', name='NativePollStatus')
    element(poll, 'execute_on_schedule', period_ms='5000')
    for opcode, kind in [('POWR', 'Power'), ('VOLM', 'Volume'), ('MUTE', 'Mute')]:
        command(poll, 'Q', opcode, '????', query=kind)
    for level in range(101):
        action = element(custom, 'action', name=f'NativeVolume{level:03d}')
        element(action, 'execute_on_state_variable_condition', str(level),
                name='NativeRequestedVolume', test_condition='equal')
        command(action, 'S', 'VOLM', f'{level:04d}')
    destination = ROOT.parents[1] / source.name
    destination.parent.mkdir(exist_ok=True)
    ET.indent(tree, space='    ')
    tree.write(destination, encoding='UTF-8', xml_declaration=True)
    return {'file': destination.name, 'mapped': mapped, 'unsupported': omitted}


if __name__ == '__main__':
    reports = [build(p) for p in sorted((ROOT / 'original').glob('*.xml'))]
    (ROOT / 'coverage.json').write_text(json.dumps(reports, indent=2), encoding='utf-8')
    for report in reports:
        print(report['file'], len(report['mapped']), 'mapped;', len(report['unsupported']), 'unsupported')
