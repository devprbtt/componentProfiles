"""Offline checks; these do not replace Savant XSD/Blueprint validation."""
import unittest
from pathlib import Path
import xml.etree.ElementTree as ET

from native_serial_probe import frame

ROOT = Path(__file__).resolve().parent


class NativeProfiles(unittest.TestCase):
    def test_known_documented_frames(self):
        self.assertEqual(frame('S', 'POWR', '0001').hex(), '53414c4c504f575230303031cb0d')
        self.assertEqual(frame('Q', 'VOLM', '????').hex(), '51414c4c564f4c4d3f3f3f3f9c0d')
        self.assertEqual(frame('S', 'INPT', '0009').hex(), '53414c4c494e505430303039d00d')

    def profiles(self):
        paths = [ROOT.parents[1] / p.name for p in (ROOT / 'original').glob('*.xml')]
        self.assertEqual(len(paths), 2)
        for p in paths:
            yield p, ET.parse(p).getroot()

    def test_all_frames_have_correct_lengths_and_checksums(self):
        for p, root in self.profiles():
            for command in root.findall('.//command_string'):
                packet = bytes.fromhex(command.text)
                self.assertEqual(command.get('type'), 'hex', p.name)
                self.assertEqual(len(packet), 14, p.name)
                self.assertEqual(packet[-1], 13, p.name)
                self.assertEqual(sum(packet[:-1]) % 256, 0, p.name)

    def test_routing_graph_is_preserved(self):
        def shape(node):
            attrs = dict(node.attrib)
            if node.tag == 'control':
                attrs.pop('port', None)
            return node.tag, attrs, (node.text or '').strip(), [shape(n) for n in node]
        for p, root in self.profiles():
            source = ROOT / 'original' / p.name
            original = ET.parse(source).getroot()
            self.assertEqual(shape(root.find('media_interfaces')), shape(original.find('media_interfaces')))
            self.assertEqual([shape(n) for n in root.findall('.//implementation')],
                             [shape(n) for n in original.findall('.//implementation')])

    def test_references_resolve(self):
        for p, root in self.profiles():
            custom = root.find('.//custom_component_actions')
            names = [a.get('name') for a in custom]
            self.assertEqual(len(names), len(set(names)), p.name)
            all_names = {a.get('name') for a in root.findall('.//action')}
            for ref in root.findall('.//action_to_select'):
                self.assertIn(ref.get('name'), all_names, p.name)
            for ref in root.findall('.//execute_action_after_delay'):
                self.assertIn(ref.get('action_name'), names, p.name)

    def test_absolute_volume_dispatch(self):
        for p, root in self.profiles():
            action = root.find(".//resource_component_actions[@resource_type='AV_VOLUMECONTROL_FUNCTION']/action[@name='SetVolume']")
            calls = {c.get('action_name') for c in action.findall('execute_action_after_delay')}
            for level in range(101):
                name = f'NativeVolume{level:03d}'
                self.assertIn(name, calls)
                helper = root.find(f".//custom_component_actions/action[@name='{name}']")
                guard = helper.find('execute_on_state_variable_condition')
                self.assertEqual(guard.get('name'), 'NativeRequestedVolume')
                self.assertEqual(guard.get('test_condition'), 'equal')
                self.assertEqual(guard.text, str(level))
                packet = bytes.fromhex(helper.find('.//command_string').text)
                self.assertEqual(packet, frame('S', 'VOLM', f'{level:04d}'))

    def test_transport_and_reply_framing(self):
        for p, root in self.profiles():
            ip = root.find('./control_interfaces/ip')
            self.assertEqual(ip.get('protocol'), 'tcp')
            self.assertEqual(ip.get('port'), '7310')
            self.assertEqual(ip.find('receive_start_condition').text, 'ALL:')
            self.assertEqual(ip.find('receive_end_condition').text, '0D0A')
            self.assertIsNone(ip.find('send_postfix'))  # already included in each frame
            self.assertIsNone(root.find('.//retry'))  # relative keys must not double-send
            self.assertIsNone(root.find('.//smart_tv_setup'))
            self.assertIsNone(root.find(".//state_variable[@name='AccessToken']"))


if __name__ == '__main__':
    unittest.main()
