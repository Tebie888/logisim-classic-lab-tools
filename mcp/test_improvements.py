"""Regression cases for the dense-port, short-circuit and export upgrade."""
import json
from pathlib import Path
import struct
import unittest
from test_server import CircuitFixture, s, BASE

class DiagnosticTests(unittest.TestCase):
    def test_repeated_legacy_marker_is_summarized_but_real_e_survives(self):
        t=s.parse_tty_table('Q\n0    Error！\nE    Error！\n1    Error！halted due to halt pin\n')
        self.assertEqual(t['rows'],[['0'],['E'],['1']])
        self.assertEqual(t['legacy_marker']['count'],3)
        self.assertEqual(t['diagnostics'],[])
        self.assertEqual(t['unparsed_trailing_tokens'],[])
    def test_unrecognized_diagnostic_tail_is_retained(self):
        t=s.parse_tty_table('Q\n1    Error！ additional diagnostic\n')
        self.assertEqual(len(t['diagnostics']),1)

class ImprovedToolTests(CircuitFixture):
    def test_dense_ports_use_readable_labels_and_separated_stubs(self):
        self.file.unlink()
        nodes=[{'id':'dec','name':'Decoder','loc':'(300,300)','attrs':{'select':2}}]
        nodes += [{'id':f'p{i}','name':'Pin','loc':f'(600,{200+i*100})','attrs':{'output':True,'label':f'Q{i}'}} for i in range(4)]
        nets=[{'name':f'SEL{i}','endpoints':[{'id':'dec','port':i},{'id':f'p{i}','port':0}]} for i in range(4)]
        r=self.call('build_circuit',components=nodes,nets=nets,layout='readable',tunnel_offset=80,label_spacing=40)
        self.assertEqual([n['tunnel_label'] for n in r['nets']],[f'SEL{i}' for i in range(4)])
        p=s.parse_project(self.file)['circuits'][0]
        self.assertGreater(len(p['wires']),0)
        locations=[s.xy(c['loc']) for c in p['components'] if c['name']=='Tunnel' and s.xy(c['loc'])[0]<500]
        ys=sorted(y for x,y in locations)
        self.assertTrue(all(b-a>=40 for a,b in zip(ys,ys[1:])),locations)
        check=self.call('check_connections')
        self.assertTrue(check['ok'],check)
    def test_existing_tunnel_name_does_not_join_new_net(self):
        text=BASE.replace('  </circuit>','<comp lib="0" name="Tunnel" loc="(500,500)"><a name="label" val="Q"/></comp>\n  </circuit>',1)
        self.file.write_text(text,encoding='utf-8')
        r=self.call('build_circuit',components=[{'id':'a','name':'Power','loc':'(100,300)'},{'id':'b','name':'Pin','loc':'(400,300)','attrs':{'output':True}}],nets=[{'name':'Q','endpoints':[{'id':'a','port':0},{'id':'b','port':0}]}])
        self.assertNotEqual(r['nets'][0]['tunnel_label'],'Q')
        self.assertTrue(r['nets'][0]['tunnel_label'].startswith('Q'))
    def test_runtime_validation_finds_short_and_reports_real_ports(self):
        self.file.write_text(BASE.replace('<comp lib="0" loc="(100,100)" name="Power"/>','<comp lib="0" loc="(100,100)" name="Clock"/><comp lib="0" loc="(150,100)" name="Ground"/>'),encoding='utf-8')
        self.assertTrue(self.call('validate_circuit')['ok'])
        r=self.call('validate_circuit',runtime=True)
        self.assertFalse(r['ok'],r)
        f=next(x for x in r['findings'] if x['code']=='multiple_drivers')
        self.assertEqual({p['name'] for p in f['ports']},{'Clock','Ground'})
        self.assertTrue(f['wires'])
    def test_crossing_without_endpoint_does_not_join(self):
        self.file.write_text('''<project source="2.15.0.2" version="1.0"><lib name="0" desc="#Wiring"/><main name="main"/><circuit name="main">
<comp lib="0" name="Power" loc="(100,200)"/><comp lib="0" name="Pin" loc="(300,200)"><a name="output" val="true"/></comp>
<comp lib="0" name="Ground" loc="(200,100)"/><comp lib="0" name="Pin" loc="(200,300)"><a name="output" val="true"/></comp>
<wire from="(100,200)" to="(300,200)"/><wire from="(200,100)" to="(200,300)"/></circuit></project>''',encoding='utf-8')
        self.assertTrue(self.call('check_connections')['ok'])
        self.file.write_text(self.file.read_text().replace('</circuit>','<wire from="(200,200)" to="(250,200)"/></circuit>'),encoding='utf-8')
        self.assertFalse(self.call('check_connections')['ok'])
    def test_expected_networks_find_unintended_input_branch(self):
        self.file.write_text(BASE.replace('  </circuit>','<comp lib="0" loc="(150,100)" name="Pin"><a name="output" val="true"/></comp>\n  </circuit>',1),encoding='utf-8')
        r=self.call('check_connections',expected_nets=[{'name':'stop','endpoints':[{'name':'Power','loc':'(100,100)','port':0},{'name':'Pin','loc':'(200,100)','port':0}]}])
        self.assertFalse(r['ok'],r)
        self.assertIn('unexpected_port',{x['code'] for x in r['findings']})
    def test_export_png_state_read_only_and_existing_output_protection(self):
        before=self.file.read_bytes();output=self.root/'图.png'
        r=self.call('export_circuit_image',output=str(output),scale=2)
        self.assertEqual(before,self.file.read_bytes())
        raw=output.read_bytes();self.assertEqual(raw[:8],b'\x89PNG\r\n\x1a\n')
        self.assertEqual(tuple(struct.unpack('>II',raw[16:24])),(r['width'],r['height']))
        self.assertEqual(r['pin_values']['halt'],'1')
        self.rejected('export_circuit_image',output=str(output))
        self.assertEqual(raw,output.read_bytes())
    def test_export_finds_probe_value_overlap_after_simulation(self):
        # Empty Probe bounds are 20px; 16-bit hex display expands only after propagation.
        self.file.write_text('''<project source="2.15.0.2" version="1.0"><lib name="0" desc="#Wiring"/><main name="main"/><circuit name="main">
<comp lib="0" name="Constant" loc="(100,300)"><a name="width" val="16"/><a name="value" val="0x1829"/></comp>
<comp lib="0" name="Probe" loc="(300,300)"><a name="facing" val="east"/><a name="radix" val="16"/><a name="label" val="Q"/></comp>
<comp lib="0" name="Tunnel" loc="(270,300)"><a name="facing" val="west"/><a name="width" val="16"/><a name="label" val="Q"/></comp>
<wire from="(100,300)" to="(300,300)"/></circuit></project>''',encoding='utf-8')
        before=self.file.read_bytes()
        r=self.call('export_circuit_image',output=str(self.root/'probe.png'))
        self.assertEqual(before,self.file.read_bytes())
        report=r['layout_report']
        self.assertGreater(report['tunnel_component_overlap_count'],0,report)
        self.assertTrue(any(pair['component']=='Probe' for pair in report['component_overlaps']),report)
        self.assertEqual(report['bounds_state'],'simulated')
        # Spacing out the same components removes the observable overlap.
        self.file.write_text(self.file.read_text().replace('(270,300)','(220,300)'),encoding='utf-8')
        clear=self.call('export_circuit_image',output=str(self.root/'clear.png'))
        self.assertEqual(clear['layout_report']['tunnel_component_overlap_count'],0,clear)

    def test_export_inputs_and_steps_use_real_register_state(self):
        self.file.unlink()
        nodes=[{'id':'r','name':'Register','loc':'(500,400)','attrs':{'width':16}},
               {'id':'zero','name':'Ground','loc':'(200,700)'}]
        for i,(label,width,output) in enumerate([('CLK',1,False),('WE',1,False),('WD',16,False),('DA',16,True),('DB',16,True)]):
            nodes.append({'id':label,'name':'Pin','loc':f'({100 if not output else 900},{100+i*150})','attrs':{'label':label,'width':width,'output':output}})
        def net(name,*ends):return {'name':name,'endpoints':[{'id':ident,'port':port} for ident,port in ends]}
        self.call('build_circuit',components=nodes,nets=[net('CLK',('CLK',0),('r',2)),net('WE',('WE',0),('r',4)),net('WD',('WD',0),('r',1)),net('Q',('r',0),('DA',0),('DB',0)),net('ZERO',('zero',0),('r',3),('r',5),('r',6))])
        r=self.call('export_circuit_image',output=str(self.root/'register.png'),inputs={'CLK':0,'WE':1,'WD':'0x1829'},steps=[{'CLK':1}])
        self.assertEqual(r['pin_values']['DA'],'1829')
        self.assertEqual(r['pin_values']['DB'],'1829')
        self.rejected('export_circuit_image',output=str(self.root/'bad.png'),inputs={'DA':1})
        self.rejected('export_circuit_image',output=str(self.root/'bad2.png'),inputs={'WD':'0x10000'})

if __name__=='__main__':unittest.main(verbosity=2)
