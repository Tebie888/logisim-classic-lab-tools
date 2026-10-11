"""Readable tunnel stubs and fan-out for closely spaced runtime ports."""
from collections import defaultdict

def plans(s,runtime,offset,spacing):
    result={}
    for c in runtime['components']:
        if c['name']=='Tunnel':continue
        b=c['bounds'];by_side=defaultdict(list)
        for port in c['ports']:
            x,y=s.xy(port['loc'])
            distances={'west':abs(x-b['x']),'east':abs(x-(b['x']+b['width'])),'north':abs(y-b['y']),'south':abs(y-(b['y']+b['height']))}
            side=min(distances,key=distances.get)
            # Bottom/top control pins can lie at a corner of a component.
            hint=(port.get('tooltip') or '').lower()
            if any(word in hint for word in ('clock','clear','preset','select','enable')):
                vertical=min(('north','south'),key=distances.get)
                if distances[vertical]==distances[side]:side=vertical
            axis=y if side in ('west','east') else x
            by_side[side].append((axis,port))
        groups={}
        for side,entries in by_side.items():
            entries.sort(key=lambda item:(item[0],item[1]['index']))
            # Preserve naturally separated ports; fan out only a genuinely dense group.
            separated=len(entries)<2 or all(b[0]-a[0]>=spacing for a,b in zip(entries,entries[1:]))
            center=round((entries[0][0]+entries[-1][0])/20)*10
            targets=[e[0] for e in entries] if separated else [center+(i-(len(entries)-1)/2)*spacing for i in range(len(entries))]
            targets=[round(v/10)*10 for v in targets]
            groups[side]=(entries,targets)
        for side,(entries,targets) in groups.items():
            upward=[i for i,(axis,p) in enumerate(entries) if targets[i]<axis]
            downward=[i for i,(axis,p) in enumerate(entries) if targets[i]>axis]
            ranks={i:j for j,i in enumerate(upward)}
            ranks.update({i:j for j,i in enumerate(reversed(downward))})
            # Keep the bends past adjacent sides' fan-out ranges. Otherwise a
            # bottom stub can land on a left-side bend around a dense corner.
            adjacent=('north','south') if side in ('west','east') else ('west','east')
            other_targets=[v for adjacent_side in adjacent for v in groups.get(adjacent_side,([],[]))[1]]
            boundary={'west':b['x'],'east':b['x']+b['width'],'north':b['y'],'south':b['y']+b['height']}[side]
            extension=(boundary-min(other_targets)) if side in ('west','north') and other_targets else (max(other_targets)-boundary) if other_targets else 0
            base=max(10,extension+10)
            required=base+10*max([*ranks.values(),0])
            distance=max(offset,required+20)
            for i,(axis,port) in enumerate(entries):
                x,y=s.xy(port['loc']);target=targets[i];lane=base+10*ranks.get(i,0)
                sign=-1 if side in ('west','north') else 1
                if side in ('west','east'):
                    point=(x+sign*distance,target)
                    coords=[(x,y),(x+sign*lane,y),(x+sign*lane,target),point] if axis!=target else [(x,y),point]
                else:
                    point=(target,y+sign*distance)
                    coords=[(x,y),(x,y+sign*lane),(target,y+sign*lane),point] if axis!=target else [(x,y),point]
                clean=[]
                for p in coords:
                    if not clean or p!=clean[-1]:clean.append(p)
                facing={'west':'east','east':'west','north':'south','south':'north'}[side]
                result[s.norm_xy(port['loc'])]={'loc':f'({point[0]},{point[1]})','facing':facing,'points':[f'({p[0]},{p[1]})' for p in clean]}
    return result

def overlaps(runtime,limit=20):
    tunnels=[c for c in runtime['components'] if c['name']=='Tunnel'];pairs=[];total=0
    for i,a in enumerate(tunnels):
        ab=a['bounds']
        for b in tunnels[i+1:]:
            bb=b['bounds']
            if min(ab['x']+ab['width'],bb['x']+bb['width'])>max(ab['x'],bb['x']) and min(ab['y']+ab['height'],bb['y']+bb['height'])>max(ab['y'],bb['y']):
                total+=1
                if len(pairs)<limit:pairs.append({'labels':[a['attributes']['label'],b['attributes']['label']],'locations':[a['loc'],b['loc']]})
    return {'tunnel_overlap_count':total,'overlaps':pairs,'truncated':total>limit}

def image_overlaps(runtime,limit=20):
    """Use propagated display bounds, including Probe values expanded by bit width."""
    report=overlaps(runtime,limit)
    tunnels=[c for c in runtime['components'] if c['name']=='Tunnel']
    others=[c for c in runtime['components'] if c['name']!='Tunnel']
    pairs=[];total=0
    for tunnel in tunnels:
        a=tunnel['bounds']
        for component in others:
            b=component['bounds']
            if min(a['x']+a['width'],b['x']+b['width'])>max(a['x'],b['x']) and min(a['y']+a['height'],b['y']+b['height'])>max(a['y'],b['y']):
                total+=1
                if len(pairs)<limit:
                    pairs.append({'tunnel_label':tunnel['attributes'].get('label',''),'tunnel_loc':tunnel['loc'],'component':component['name'],'component_label':component['attributes'].get('label',''),'component_loc':component['loc']})
    return {**report,'tunnel_component_overlap_count':total,'component_overlaps':pairs,'component_overlaps_truncated':total>limit,'bounds_state':'simulated','scope':'Tunnel labels versus Tunnel labels and component bodies; excludes external labels and wires'}
